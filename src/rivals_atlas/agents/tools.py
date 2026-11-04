"""The tool layer: plain typed functions over the database that an agent (or the UI) can call.

Every tool returns a Finding: the number, the sample size, the Wilson 95% interval for rates and the ids of the
matches behind it. Tools only read. Arguments are plain JSON types so a call can be stored, shown and re-run
by the evidence checker (see evidence.py). Nothing here calls a model.
"""
from __future__ import annotations

import itertools
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from rivals_atlas.analysis import patterns, stats
from rivals_atlas.core import names, queries
from rivals_atlas.core.filters import Filter
from rivals_atlas.graph import network as graph
from rivals_atlas.graph import store as lbug_store
from rivals_atlas.ingest import meta as meta_mod

POSITION_CAP = 5   # session position 5 means "5th game or later"


@dataclass
class Finding:
    tool: str
    args: dict[str, Any]
    n: int                                   # decided games for rates; items or points for the other tools
    wins: int | None = None
    rate: float | None = None
    lo: float | None = None
    hi: float | None = None
    enough: bool = False                     # n reaches stats.MIN_GAMES (rates) or there is anything to report
    match_ids: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    value: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def describe(self) -> str:
        """One plain line built only from this result's own numbers (no model involved)."""
        what = describe_args(self.args)
        if self.tool == "hero_benchmark":
            if not self.items:
                return f"{what}: no matches on this hero."
            top = "; ".join(f"{i['metric']} {i['tracked']:g} against {i['others']:g} for others" for i in self.items[:4])
            return (f"{what}: {self.value['tracked_matches']} matches against {self.value['other_lines']} lines from other players. {top}.")
        if self.rate is not None and self.lo is not None and self.hi is not None:
            if not self.enough:
                return f"{what}: not enough games to say (n={self.n}, at least {stats.MIN_GAMES} needed)."
            return (f"{what}: {self.rate:.0%} win rate, {self.wins} wins in {self.n} decided games "
                    f"(95% interval {self.lo:.0%} to {self.hi:.0%}).")
        if self.tool == "rank_journey" and self.value:
            v = self.value
            return f"{what}: rank score {v['start']:.0f} to {v['end']:.0f} ({v['change']:+.0f}) over {self.n} matches, peak {v['peak']:.0f}."
        if self.tool == "comp_stats":
            top = "; ".join(f"{i['label']}: {i['wins']} wins in {i['n']}" for i in self.items[:6])
            return f"{what} ({self.args['side']} side), by composition: {top or 'no decided games'}."
        if self.tool == "cypher_query":
            shown = "; ".join(", ".join(f"{k} {v}" for k, v in row.items()) for row in self.items[:10])
            return f"query returned {self.n} row{'s' if self.n != 1 else ''}: {shown}" + (" ..." if self.n > 10 else "")
        return f"{what}: {self.n} result{'s' if self.n != 1 else ''}." + (f" {self.note}" if self.note else "")


_ARG_LABELS: dict[str, Callable[[Any], str]] = {
    "hero": lambda v: names.hero_name(v), "a": lambda v: names.hero_name(v), "b": lambda v: names.hero_name(v),
    "other": lambda v: "with " + names.hero_name(v), "enemy": lambda v: "against " + names.hero_name(v),
    "map_id": lambda v: names.map_name(v), "role": lambda v: names.ROLES.get(v, "role ?"),
    "mode": lambda v: stats.MODES.get(v, f"mode {v}"), "position": lambda v: f"game {v} in a session",
    "side": lambda v: f"{v} side", "session_pos": lambda v: f"game {v} in a session", "season": lambda v: names.season_label(v),
    "season_from": lambda v: f"from {names.season_label(v)}", "season_to": lambda v: f"to {names.season_label(v)}",
}


def describe_args(args: dict[str, Any]) -> str:
    """Readable summary of a tool call's arguments, skipping unset ones and the default ranked mode."""
    if args.get("season_from") is not None and args.get("season_from") == args.get("season_to"):
        args = {k: v for k, v in args.items() if k not in ("season_from", "season_to")} | {"season": args["season_from"]}   # one season
    parts = [_ARG_LABELS.get(k, lambda x, k=k: f"{k} {x}")(v) for k, v in args.items()
             if v is not None and not (k == "mode" and v == 2) and k not in ("ban_state", "min_n", "banned")]
    if args.get("banned") is not None:
        parts.append(f"{names.hero_name(args['banned'])} {'not banned' if args.get('ban_state') == 'absent' else 'banned'}")
    return ", ".join(parts) or "all ranked games"


def _rate_finding(tool: str, args: dict[str, Any], wins: int, losses: int, ids: list[str], **value: Any) -> Finding:
    r = stats.rate(wins, losses)
    return Finding(tool, args, r["n"], wins if r["n"] else 0, r["rate"], r["lo"], r["hi"], r["enough"], ids, value=value)


def _filter(mode: int, season_from: int | None = None, season_to: int | None = None, hero: int | None = None,
            map_id: int | None = None) -> Filter:
    return Filter(mode=mode, season_from=season_from, season_to=season_to, hero=hero, map_id=map_id)


def _own_ids(con: sqlite3.Connection, f: Filter) -> list[str]:
    return queries.own_match_ids(con, f)


def hero_stats(con: sqlite3.Connection, hero: int, mode: int = 2, season_from: int | None = None,
               season_to: int | None = None, map_id: int | None = None) -> Finding:
    """The tracked player's results on one hero."""
    args = {"hero": hero, "mode": mode, "season_from": season_from, "season_to": season_to, "map_id": map_id}
    f = _filter(mode, season_from, season_to, hero, map_id)
    row = next(iter(stats.heroes(con, f)), None)
    ids = _own_ids(con, f)
    return _rate_finding("hero_stats", args, row["wins"] if row else 0, (row["n"] - row["wins"]) if row else 0, ids,
                         games=len(ids), draws=row["draws"] if row else 0, kda=row["kda"] if row else None)


def map_stats(con: sqlite3.Connection, map_id: int, mode: int = 2, season_from: int | None = None,
              season_to: int | None = None, hero: int | None = None) -> Finding:
    """The tracked player's results on one map."""
    args = {"map_id": map_id, "mode": mode, "season_from": season_from, "season_to": season_to, "hero": hero}
    f = _filter(mode, season_from, season_to, hero, map_id)
    row = next(iter(stats.maps(con, f)), None)
    ids = _own_ids(con, f)
    return _rate_finding("map_stats", args, row["wins"] if row else 0, (row["n"] - row["wins"]) if row else 0, ids,
                         games=len(ids), draws=row["draws"] if row else 0)


def session_stats(con: sqlite3.Connection, position: int, mode: int = 2, season_from: int | None = None,
                  season_to: int | None = None) -> Finding:
    """Results of the tracked player's games that were number `position` in their session (5 = fifth or later).
    A gap of patterns.SESSION_GAP seconds starts a new session; draws count for the numbering only."""
    args = {"position": position, "mode": mode, "season_from": season_from, "season_to": season_to}
    rows = queries.own_timeline(con, _filter(mode, season_from, season_to))
    pos = patterns.session_positions([r["played_at"] for r in rows])
    hit = [r for r, k in zip(rows, pos, strict=True) if min(k, POSITION_CAP) == min(position, POSITION_CAP)]
    return _rate_finding("session_stats", args, sum(r["result"] == "win" for r in hit),
                         sum(r["result"] == "loss" for r in hit), [r["match_uid"] for r in hit],
                         sessions=sum(1 for k in pos if k == 1))


def rank_journey(con: sqlite3.Connection, mode: int = 2, season_from: int | None = None,
                 season_to: int | None = None) -> Finding:
    """Rank score over time: first and last score, change and peak. n = matches that carry a score."""
    args = {"mode": mode, "season_from": season_from, "season_to": season_to}
    pts = stats.rank_journey(con, _filter(mode, season_from, season_to))
    if not pts:
        return Finding("rank_journey", args, 0, note="no rank scores stored for this filter")
    first, last = pts[0], pts[-1]
    start = first["new_score"] - (first["add_score"] or 0)
    return Finding("rank_journey", args, len(pts), enough=len(pts) >= 2, match_ids=[p["match_uid"] for p in pts],
                   value={"start": start, "end": last["new_score"], "change": last["new_score"] - start,
                          "peak": max(p["new_score"] for p in pts), "first_at": first["played_at"],
                          "last_at": last["played_at"]})


def compare_to_meta(con: sqlite3.Connection, hero: int, meta: dict[str, Any] | None, mode: int = 2,
                    rank_group: str = "all", season_from: int | None = None, season_to: int | None = None) -> Finding:
    """The tracked player's win rate on a hero against the site-wide win rate for a rank group. 'Different' only when the
    site's figure lies outside the tracked player's 95% interval."""
    args = {"hero": hero, "mode": mode, "rank_group": rank_group, "season_from": season_from, "season_to": season_to}
    own = hero_stats(con, hero, mode, season_from, season_to)
    site = meta_mod.for_hero(meta, hero, rank_group)
    f = Finding("compare_to_meta", args, own.n, own.wins, own.rate, own.lo, own.hi, own.enough, own.match_ids)
    if not site or site.get("win") is None:
        f.note = "no site figure for this hero and rank group"
        return f
    site_rate = site["win"] / 100
    f.value = {"site_rate": site_rate, "site_matches": site.get("matches"),
               "difference": (own.rate - site_rate) if own.rate is not None else None,
               "outside_interval": own.n > 0 and not (own.lo <= site_rate <= own.hi)}
    return f


def match_lookup(con: sqlite3.Connection, ids: list[str]) -> Finding:
    """The receipts: one line per stored match id. Unknown ids are listed, not guessed."""
    args = {"ids": list(ids)}
    items, found = [], []
    for uid in ids:
        r = queries.match_receipt(con, uid)
        if r:
            found.append(uid)
            items.append({**dict(r), "hero": names.hero_name(r["hero_id"]), "map": names.map_name(r["map_id"]),
                          "mode": stats.MODES.get(r["mode_id"], f"mode {r['mode_id']}")})
    missing = [u for u in ids if u not in found]
    return Finding("match_lookup", args, len(items), enough=bool(items), match_ids=found, items=items,
                   value={"missing": missing})


def graph_pattern(con: sqlite3.Connection, mode: int = 2, season: int | None = None, map_id: int | None = None,
                  hero: int | None = None, role: int | None = None, banned: int | None = None, ban_state: str = "present",
                  block: int | None = None, weekday: int | None = None, session_pos: int | None = None,
                  regulars: int | None = None, comp: str | None = None, enemy_comp: str | None = None) -> Finding:
    """Win rate of the tracked player's matches that satisfy ALL the given conditions, read from the graph (any mix of them).
    role: 1 vanguard, 2 duelist, 3 strategist (the hero played). banned + ban_state ('present'/'absent'): was that hero banned
    in the match. block: hour of day // 6 (0 night .. 3 evening). weekday: 0 Monday. session_pos: game number in the session,
    5 = fifth or later. comp / enemy_comp: role mix of the tracked player's side / the other side, written
    vanguards-duelists-strategists, e.g. '2-2-2'. regulars: number of regular teammates on the tracked player's side (0 = none known, 1 = duo, 2 = trio...)."""
    args: dict[str, Any] = {"mode": mode, "season": season, "map_id": map_id, "hero": hero, "role": role, "banned": banned,
            "ban_state": ban_state, "block": block, "weekday": weekday, "session_pos": session_pos, "regulars": regulars,
            "comp": comp, "enemy_comp": enemy_comp}
    gpath = lbug_store.graph_path(con)
    if not gpath.exists():
        raise ValueError(f"the graph file {gpath.name} is not built; run `rivals-atlas graph --ladybug`")
    rows = lbug_store.pattern_rows(lbug_store.open_readonly(gpath), **args)
    return _rate_finding("graph_pattern", args, sum(r["result"] == "win" for r in rows),
                         sum(r["result"] == "loss" for r in rows), [r["uid"] for r in rows])


def cypher_query(con: sqlite3.Connection, cypher: str) -> Finding:
    """Run ONE read-only Cypher query on the match graph and return its rows (at most 200). Use it for questions the other
    tools cannot express. The query must start with MATCH/WITH/UNWIND/RETURN and return counts or named columns."""
    gpath = lbug_store.graph_path(con)
    if not gpath.exists():
        raise ValueError(f"the graph file {gpath.name} is not built; run `rivals-atlas graph --ladybug`")
    try:
        cols, rows, more = lbug_store.run_read(lbug_store.open_readonly(gpath), cypher)
    except RuntimeError as e:                       # Cypher syntax or timeout: tell the model, it may retry
        raise ValueError(f"the query failed: {e}") from e
    items = [dict(zip(cols, r, strict=True)) for r in rows]
    ids = [str(r[cols.index("uid")]) for r in rows if "uid" in cols]
    return Finding("cypher_query", {"cypher": cypher}, len(rows), enough=bool(rows), match_ids=ids, items=items,
                   value={"columns": cols}, note="more rows existed" if more else "")


def comp_stats(con: sqlite3.Connection, side: str = "own", mode: int = 2, hero: int | None = None, map_id: int | None = None,
               season: int | None = None) -> Finding:
    """Win rate by team composition (role mix written vanguards-duelists-strategists, '2-2-2' = two of each), most played first.
    side 'own' = the tracked player's side, 'enemy' = the opponents. hero = only matches where the tracked player played that hero
    (answers 'which compositions go with this hero')."""
    args: dict[str, Any] = {"side": side, "mode": mode, "hero": hero, "map_id": map_id, "season": season}
    gpath = lbug_store.graph_path(con)
    if not gpath.exists():
        raise ValueError(f"the graph file {gpath.name} is not built; run `rivals-atlas graph --ladybug`")
    rows = lbug_store.comp_rows(lbug_store.open_readonly(gpath), side, mode=mode, hero=hero, map_id=map_id, season=season)
    f = _rate_finding("comp_stats", args, sum(r["wins"] for r in rows), sum(r["n"] - r["wins"] for r in rows),
                      [u for r in rows for u in r["uids"]])
    f.items = [{"comp": r["comp"], "label": names.comp_label(r["comp"]),
                **stats.rate(r["wins"], r["n"] - r["wins"])} for r in rows]
    return f


def squad_stats(con: sqlite3.Connection, teammate: str, present: bool = True, mode: int = 2, season_from: int | None = None,
                season_to: int | None = None, hero: int | None = None, map_id: int | None = None) -> Finding:
    """The tracked player's results in matches where a regular teammate was on the same side (present=true) or was not
    (present=false). `teammate` is the id or the first characters of it, from the list of regular teammates. Add hero or map_id to
    look at one hero or map."""
    args: dict[str, Any] = {"teammate": teammate, "present": present, "mode": mode, "season_from": season_from,
                            "season_to": season_to, "hero": hero, "map_id": map_id}
    pid = queries.resolve_player(con, teammate)
    if pid is None:
        raise ValueError("teammate must be the first characters (at least 4) of exactly one teammate id")
    f = _filter(mode, season_from, season_to, hero, map_id)
    with_him = {r["uid"] for r in queries.teammates_present(con, f, [pid])}
    rows = [r for r in queries.own_results(con, f) if r["result"] in ("win", "loss") and (r["uid"] in with_him) == present]
    return _rate_finding("squad_stats", args, sum(r["result"] == "win" for r in rows), sum(r["result"] == "loss" for r in rows),
                         [r["uid"] for r in rows], teammate=names.player_label(con, pid))


def matchup_stats(con: sqlite3.Connection, enemy: int, mode: int = 2, season_from: int | None = None, season_to: int | None = None,
                  hero: int | None = None, map_id: int | None = None) -> Finding:
    """The tracked player's results in matches where `enemy` (a hero id) was on the other side. Add hero to look only at
    matches where the tracked player played that hero, or map_id for one map."""
    args: dict[str, Any] = {"enemy": enemy, "mode": mode, "season_from": season_from, "season_to": season_to, "hero": hero,
                            "map_id": map_id}
    rows = [r for r in queries.matchup_rows(con, _filter(mode, season_from, season_to, hero, map_id)) if r["enemy"] == enemy]
    return _rate_finding("matchup_stats", args, sum(r["result"] == "win" for r in rows), sum(r["result"] == "loss" for r in rows),
                         sorted({r["uid"] for r in rows}), enemy=names.hero_name(enemy))


def matchup_table(con: sqlite3.Connection, mode: int = 2, season_from: int | None = None, season_to: int | None = None,
                  hero: int | None = None, map_id: int | None = None, min_n: int = 10) -> Finding:
    """Win rate of the tracked player against each enemy hero (when that hero was on the other side), for heroes met in at
    least min_n decided games. Sorted by impact, not by win rate: `net` is wins minus losses, and `weighted` is the win rate pulled
    toward 50% as if the matchup had 16 more even games, so a 6-game 83% does not outrank a 45-game 62%. The largest |net| first
    are the matchups that moved the most games. Use it to find candidates, then check one with matchup_stats."""
    args: dict[str, Any] = {"mode": mode, "season_from": season_from, "season_to": season_to, "hero": hero, "map_id": map_id,
                            "min_n": min_n}
    tally: dict[int, list[int]] = {}
    for r in queries.matchup_rows(con, _filter(mode, season_from, season_to, hero, map_id)):
        t = tally.setdefault(r["enemy"], [0, 0])
        t[r["result"] != "win"] += 1
    k = 16
    items = sorted(({"hero_id": h, "hero": names.hero_name(h), **stats.rate(w, lo_), "net": w - lo_,
                     "weighted": (w + k / 2) / (w + lo_ + k)} for h, (w, lo_) in tally.items() if w + lo_ >= max(min_n, 1)),
                   key=lambda x: (-abs(x["weighted"] - 0.5) * x["n"], -x["n"]))
    return Finding("matchup_table", args, len(items), enough=bool(items), items=items)


# third field: True = higher is better, False = lower is better, None = neither (shown without a ranking)
BENCH_METRICS = (("damage", "damage dealt", True), ("heal", "healing", True), ("taken", "damage taken", None),
                 ("k", "kills", True), ("d", "deaths", False), ("a", "assists", True), ("dmg10", "damage per 10 minutes", True))


def _median(v: list[float]) -> float:
    s = sorted(v)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def hero_benchmark(con: sqlite3.Connection, hero: int, mode: int = 2, season: int | None = None) -> Finding:
    """The tracked player's average match on one hero next to every other player's matches on that hero (same mode, all ranks
    in the data): damage, healing, damage taken, kills, deaths, assists and damage per 10 minutes. Each row also gives the
    share of the other players' matches that the tracked average beats (for deaths: share with MORE deaths, so higher is always
    better) and the win rates of both groups."""
    args: dict[str, Any] = {"hero": hero, "mode": mode, "season": season}
    gpath = lbug_store.graph_path(con)
    if not gpath.exists():
        raise ValueError(f"the graph file {gpath.name} is not built; run `rivals-atlas graph --ladybug`")
    lines = lbug_store.hero_lines(lbug_store.open_readonly(gpath), hero, mode, season)
    lines = [ln for ln in lines if ln["damage"] or ln["heal"] or ln["taken"]]       # a line with no figures at all is missing data
    for ln in lines:
        ln["dmg10"] = ln["damage"] / ln["duration"] * 600 if ln["duration"] else 0.0
    mine = [ln for ln in lines if ln["is_self"]]
    others = [ln for ln in lines if not ln["is_self"]]

    def wins(group: list[dict[str, Any]]) -> tuple[int, int]:
        return sum(ln["result"] == "win" for ln in group), sum(ln["result"] == "loss" for ln in group)
    w, lo = wins(mine)
    f = _rate_finding("hero_benchmark", args, w, lo, [ln["uid"] for ln in mine])
    ow, ol = wins(others)
    items = []
    for key, label, higher_better in BENCH_METRICS:
        if not mine or not others:
            break
        m_mean = sum(ln[key] for ln in mine) / len(mine)
        o_vals = [ln[key] for ln in others]
        beaten = (None if higher_better is None else
                  round(sum((m_mean > v) if higher_better else (m_mean < v) for v in o_vals) / len(o_vals), 3))
        items.append({"metric": label, "tracked": round(m_mean, 1), "others": round(sum(o_vals) / len(o_vals), 1),
                      "others_median": round(_median(o_vals), 1), "beats_share": beaten, "lower_is_better": higher_better is False})
    f.items = items
    f.value = {"tracked_matches": len(mine), "other_lines": len(others), "others_wins": ow, "others_losses": ol,
               "others_rate": ow / (ow + ol) if ow + ol else None}
    f.note = "" if mine and others else "no matches on this hero"
    f.enough = len(mine) >= stats.MIN_GAMES and bool(others)
    return f


_REL_COND = {"SYNERGY": "a.camp = b.camp", "COUNTER": "a.camp != b.camp"}


def _pair_ids(con: sqlite3.Connection, a: int, b: int, rel: str, mode: int) -> list[str]:
    """Matches in which hero a and hero b (any of the 12 players) stood in this relation and the result was decided."""
    return queries.pair_match_ids(con, a, b, _REL_COND[rel], mode)


def graph_neighbors(con: sqlite3.Connection, hero: int, rel: str = "SYNERGY", mode: int = 2, min_n: int = 1,
                    other: int | None = None) -> Finding:
    """Heroes linked to `hero` in the hero graph (all 12 players of every stored match). rel is SYNERGY (same team)
    or COUNTER (opposite team; wins are `hero`'s). With `other`, returns that single pair as a rate with its match
    ids; without it, the list of neighbours (n = how many) and no match ids."""
    args = {"hero": hero, "rel": rel, "mode": mode, "min_n": min_n, "other": other}
    if rel not in _REL_COND:
        raise ValueError(f"rel must be SYNERGY or COUNTER, not {rel!r}")
    rows = queries.graph_neighbour_edges(con, hero, rel, mode, min_n)
    items = []
    for r in rows:
        o = r["dst"] if r["src"] == hero else r["src"]
        items.append({"hero_id": o, "n": r["n"], "wins": r["wins"], "rate": r["wins"] / r["n"], "lo": r["lo"],
                      "hi": r["hi"], "enough": r["n"] >= stats.MIN_GAMES})
    items.sort(key=lambda x: -x["n"])
    if other is not None:
        hit = next((i for i in items if i["hero_id"] == other), None)
        if hit is None:
            return Finding("graph_neighbors", args, 0, note="no stored decided games for this pair")
        return Finding("graph_neighbors", args, hit["n"], hit["wins"], hit["rate"], hit["lo"], hit["hi"], hit["enough"],
                       _pair_ids(con, hero, other, rel, mode))
    return Finding("graph_neighbors", args, len(items), enough=bool(items), items=items)


def graph_path(con: sqlite3.Connection, a: int, b: int, rel: str = "SYNERGY", mode: int = 2, min_n: int = 10) -> Finding:
    """Shortest chain of heroes from a to b over edges with at least min_n decided games. n = hops."""
    args = {"a": a, "b": b, "rel": rel, "mode": mode, "min_n": min_n}
    g = graph.load(con, mode, rel, min_n)
    path = graph.best_path(g, a, b)
    if path is None:
        return Finding("graph_path", args, 0, note="no chain of heroes with enough games links these two")
    hops = [{"from": x, "to": y, **{k: g[x][y][k] for k in ("n", "wins", "rate", "lo", "hi")}}
            for x, y in itertools.pairwise(path)]
    return Finding("graph_path", args, len(hops), enough=True, items=hops, value={"path": path})


TOOLS: dict[str, Callable[..., Finding]] = {f.__name__: f for f in (
    hero_stats, map_stats, session_stats, rank_journey, compare_to_meta, match_lookup, graph_neighbors, graph_path, graph_pattern, cypher_query, comp_stats, hero_benchmark,
    squad_stats, matchup_stats, matchup_table)}


def run(con: sqlite3.Connection, tool: str, args: dict[str, Any], meta: dict[str, Any] | None = None) -> Finding:
    """Call a tool by name with JSON arguments. compare_to_meta gets the meta document from here, never from the caller."""
    if tool not in TOOLS:
        raise KeyError(f"unknown tool {tool!r}")
    if tool == "compare_to_meta":
        return TOOLS[tool](con, meta=meta, **args)
    return TOOLS[tool](con, **args)

