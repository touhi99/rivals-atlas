"""Breakdowns that always show: win rate split by time of day, session position, streak, match length,
season, party and hero swaps. Each card carries every bucket with its games and interval, and a plain
verdict. 'Clear difference' needs one bucket to differ from the rest after a Bonferroni correction across
the buckets of that card; otherwise the card says 'no clear difference'. Draws are left out.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from rivals_atlas.analysis import stats
from rivals_atlas.analysis.insights import MIN_N, two_prop_p
from rivals_atlas.analysis.stats import wilson
from rivals_atlas.core import names, queries
from rivals_atlas.core.filters import Filter

SESSION_GAP = 90 * 60   # seconds between matches that starts a new session


def session_positions(times: list[int]) -> list[int]:
    """Game number inside its session for matches in time order; a gap above SESSION_GAP starts a new session."""
    out, last, k = [], None, 0
    for t in times:
        k = 1 if last is None or t - last > SESSION_GAP else k + 1
        out.append(k)
        last = t
    return out


def _bucket(label: str, w: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(w, n)
    return {"label": label, "n": n, "wins": w, "rate": (w / n if n else None), "lo": lo, "hi": hi, "enough": n >= MIN_N}


def _card(pid: str, title: str, note: str, groups: dict[str, list[int]], order: list[str] | None = None,
          caveat: str = "") -> dict[str, Any]:
    keys = [k for k in (order or list(groups)) if k in groups and groups[k][1] > 0]
    W = sum(groups[k][0] for k in keys)
    N = sum(groups[k][1] for k in keys)
    buckets = [_bucket(k, *groups[k]) for k in keys]
    best: tuple[float, str, float, float, int] | None = None
    for k in keys:
        w, n = groups[k]
        if n >= MIN_N and N - n >= MIN_N:
            p = two_prop_p(w, n, W - w, N - n) * len(keys)        # Bonferroni across this card's buckets
            if best is None or p < best[0]:
                best = (min(p, 1.0), k, w / n, (W - w) / (N - n), n)
    lead, detail, lead_label = "", "all buckets are close to the overall rate", ""
    if best is not None and best[0] < 0.05:
        lead_label = best[1]
        lead = f"{best[1]} {best[2]:.0%} · rest {best[3]:.0%}"
        detail = f"{best[1]}: {best[2]:.0%} in {best[4]} games vs {best[3]:.0%} in the rest"
    clear = bool(lead)
    return {"id": pid, "title": title, "note": note, "buckets": buckets,
            "verdict": "clear difference" if clear else "no clear difference", "clear": clear, "detail": detail,
            "lead": lead, "lead_label": lead_label, "caveat": caveat}


def compute(con: sqlite3.Connection, f: Filter) -> dict[str, Any]:
    rows = queries.pattern_rows(con, f)
    dec = [r for r in rows if r["result"] in ("win", "loss")]
    if len(dec) < 2 * MIN_N:
        return {"cards": [], "facts": [], "n": len(dec)}

    def tally(keyf, rs=dec) -> dict[str, list[int]]:
        g: dict[str, list[int]] = {}
        for i, r in enumerate(rs):
            k = keyf(i, r)
            if k is not None:
                x = g.setdefault(k, [0, 0])
                x[0] += r["result"] == "win"
                x[1] += 1
        return g

    cards = []
    hour = lambda r: datetime.fromtimestamp(r["played_at"]).hour
    tod = ["Night 0–6", "Morning 6–12", "Afternoon 12–18", "Evening 18–24"]
    cards.append(_card("tod", "Time of day", "local time of this computer", tally(lambda i, r: tod[hour(r) // 6]), tod))
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cards.append(_card("dow", "Day of the week", "local time of this computer",
                       tally(lambda i, r: days[datetime.fromtimestamp(r["played_at"]).weekday()]), days))

    # session position: a new session starts after a gap of SESSION_GAP seconds (any result, draws included)
    pos, sessions = {}, []
    for r, k in zip(rows, session_positions([r["played_at"] for r in rows]), strict=True):
        if k == 1:
            sessions.append({"t": r["played_at"], "games": []})
        sessions[-1]["games"].append({"r": {"win": "w", "loss": "l"}.get(r["result"], "d"), "t": r["played_at"]})
        pos[r["match_uid"]] = k
    lab = lambda n: str(n) if n < 5 else "5+"
    cards.append(_card("sess", "Game number in a session", f"a gap of {SESSION_GAP // 3600}h30 starts a new session",
                       tally(lambda i, r: lab(pos[r["match_uid"]])), ["1", "2", "3", "4", "5+"]))

    # result right after a streak
    streak = []
    run = 0
    for r in dec:
        streak.append(run)
        run = run + 1 if r["result"] == "loss" else 0
    sl = ["after a win", "after 1 loss", "after 2 losses in a row", "after 3+ in a row"]
    cards.append(_card("streak", "After a streak of losses", "ranked decided games in order",
                       tally(lambda i, r: sl[min(streak[i], 3)]), sl))

    ml = ["under 8 min", "8–11 min", "11–14 min", "14+ min"]
    cards.append(_card("len", "Match length", "short matches are often one-sided",
                       tally(lambda i, r: ml[0 if (r["duration"] or 0) < 480 else 1 if r["duration"] < 660 else 2 if r["duration"] < 840 else 3]), ml))
    cards.append(_card("swap", "Hero swaps", "was the hero changed during the match?",
                       tally(lambda i, r: "swapped heroes" if r["swaps"] > 1 else "stayed on one hero"),
                       caveat="Players tend to swap when a match is already going badly, so a swap is more likely a sign of a losing match than a cause."))
    seasons = sorted({r["season"] for r in dec if r["season"] is not None})
    cards.append(_card("season", "Season by season", "win rate inside each season",
                       tally(lambda i, r: names.season_label(r["season"]) if r["season"] is not None else None),
                       [names.season_label(s) for s in seasons]))
    # party: every combination of the two most frequent teammates that was played, named
    sq = stats.squad(con, f.replace(with_players=()))[:2]
    if sq:
        label = {s_["player_id"]: s_["player"] for s_ in sq}
        combos = stats.party_combos(con, f.replace(with_players=()), list(label))
        groups = {(" + ".join(label[h] for h in c_["members"]) if c_["members"] else "Neither"): [c_["wins"], c_["n"]]
                  for c_ in combos}
        cards.append(_card("party", "Who is on the team", "the two most frequent teammates and every combination played",
                           groups, list(groups)))
    # facts
    facts: list[dict[str, Any]] = []
    hours = sum(r["duration"] or 0 for r in rows) / 3600
    days_active = len({datetime.fromtimestamp(r["played_at"]).date() for r in rows})
    facts.append({"kind": "time", "label": "Time in matches", "value": f"{hours:,.0f} h", "sub": f"{len(rows)} matches on {days_active} days",
                  "data": {"hours": hours, "matches": len(rows), "days": days_active}})
    best_w = best_l = cw = cl = 0
    for r in dec:
        cw = cw + 1 if r["result"] == "win" else 0
        cl = cl + 1 if r["result"] == "loss" else 0
        best_w, best_l = max(best_w, cw), max(best_l, cl)
    facts.append({"kind": "streak", "label": "Longest streaks", "value": f"{best_w} wins · {best_l} losses",
                  "sub": f"now: {cw} win{'s' if cw != 1 else ''}" if cw else f"now: {cl} loss{'es' if cl != 1 else ''}",
                  "data": {"best_win": best_w, "best_loss": best_l, "now": cw or cl, "now_result": "win" if cw else "loss"}})
    # rank points only exist in ranked; quick play carries a hidden rating that is not shown as a rank
    gains = [r["add_score"] for r in rows if r["mode_id"] == 2 and r["result"] == "win" and r["add_score"] is not None]
    losses = [r["add_score"] for r in rows if r["mode_id"] == 2 and r["result"] == "loss" and r["add_score"] is not None]
    if gains and losses:
        facts.append({"kind": "points", "label": "Rank points", "value": f"+{sum(gains)/len(gains):.1f} / {sum(losses)/len(losses):.1f}",
                      "sub": "average per win / per loss", "data": {"gain": sum(gains) / len(gains), "loss": sum(losses) / len(losses)}})
    by_hero: dict[int, int] = {}
    for r in rows:
        by_hero[r["hero_id"]] = by_hero.get(r["hero_id"], 0) + 1
    top3 = sum(sorted(by_hero.values(), reverse=True)[:3]) / len(rows)
    facts.append({"kind": "pool", "label": "Hero pool", "value": f"{len(by_hero)} heroes", "sub": f"top 3 = {top3:.0%} of games",
                  "data": {"heroes": len(by_hero), "top3": top3}})
    mv = sum(1 for r in rows if r["mvp"]); sv = sum(1 for r in rows if r["svp"])
    facts.append({"kind": "medals", "label": "MVP / SVP", "value": f"{mv} / {sv}", "sub": f"{mv/len(rows):.0%} and {sv/len(rows):.0%} of matches",
                  "data": {"mvp": mv, "svp": sv, "mvp_share": mv / len(rows), "svp_share": sv / len(rows)}})
    swp = sum(1 for r in rows if r["swaps"] > 1)
    facts.append({"kind": "swaps", "label": "Hero swaps", "value": f"{swp/len(rows):.0%}", "sub": "of matches use more than one hero",
                  "data": {"share": swp / len(rows)}})
    heat: dict[tuple[int, int], list[int]] = {}
    for r in rows:
        t = datetime.fromtimestamp(r["played_at"])
        x = heat.setdefault((t.weekday(), t.hour // 4), [0, 0, 0])     # games, decided games, wins
        x[0] += 1
        x[1] += r["result"] in ("win", "loss")
        x[2] += r["result"] == "win"
    cells = []
    for (d, b), (g, n, w) in sorted(heat.items()):
        lo, hi = wilson(w, n)
        cells.append({"d": d, "b": b, "games": g, "n": n, "wins": w, "rate": w / n if n else None, "lo": lo, "hi": hi,
                      "enough": n >= MIN_N})
    won = sum(r["result"] == "win" for r in dec)
    return {"cards": cards, "facts": facts, "n": len(dec), "overall": won / len(dec), "min_n": MIN_N,
            "heat": {"days": days, "blocks": ["0–4", "4–8", "8–12", "12–16", "16–20", "20–24"], "cells": cells},
            "sessions": sessions[-20:][::-1]}
