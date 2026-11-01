"""Explore: any mix of conditions over the graph, with an optional breakdown. The page and the JSON endpoint share this.

One query returns the matching matches; the breakdown groups those rows in Python, so every group carries the same
numbers as everywhere else (decided games, wins, Wilson interval, minimum sample).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from rivals_atlas.analysis import stats
from rivals_atlas.core import names, queries
from rivals_atlas.graph import network as hero_graph
from rivals_atlas.graph import store as lbug_store

BLOCKS = ["Night 0–6", "Morning 6–12", "Afternoon 12–18", "Evening 18–24"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MATCH_LIMIT = 200      # rows shown in the match table
TIMELINE_LIMIT = 400   # most recent matches drawn as dots
RELATION_EDGES = 36    # strongest hero-map links drawn in the relations view
NO_MAP = "No map data"   # the site's history list does not cover the newest matches yet

# group name -> (title, label of one row)
GROUPS: dict[str, tuple[str, Callable[[dict[str, Any]], str]]] = {
    "hero": ("Hero", lambda r: names.hero_name(r["hero"])),
    "role": ("Role", lambda r: names.ROLES.get(r["role"], "Unknown role")),
    "map": ("Map", lambda r: names.map_name(r["map"]) if r["map"] >= 0 else NO_MAP),
    "season": ("Season", lambda r: names.season_label(r["season"]) if r["season"] >= 0 else "Unknown season"),
    "block": ("Time of day", lambda r: BLOCKS[r["block"]]),
    "weekday": ("Weekday", lambda r: WEEKDAYS[r["weekday"]]),
    "session_pos": ("Game in session", lambda r: str(r["session_pos"]) if r["session_pos"] < 5 else "5+"),
    "ban": ("Banned hero", lambda r: names.hero_name(r["banned_hero"])),
}


def _tally(rows: list[dict[str, Any]], label: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    wl: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])      # wins, losses, all games
    for r in rows:
        x = wl[label(r)]
        x[0] += r["result"] == "win"
        x[1] += r["result"] == "loss"
        x[2] += 1
    out = [{"label": k, "games": g, **stats.rate(w, lo)} for k, (w, lo, g) in wl.items()]
    return sorted(out, key=lambda x: (x["label"] == NO_MAP, -x["games"], x["label"]))      # unknown last


def relations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Hero-to-map links among the matched matches: who played where, with games and wins. A small graph for the page."""
    heroes: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])      # games, wins, losses
    maps: dict[int, int] = defaultdict(int)
    links: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        h = heroes[r["hero"]]
        h[0] += 1
        h[1] += r["result"] == "win"
        h[2] += r["result"] == "loss"
        if r["map"] >= 0:
            maps[r["map"]] += 1
            lk = links[(r["hero"], r["map"])]
            lk[0] += 1
            lk[1] += r["result"] == "win"
            lk[2] += r["result"] == "loss"
    top = sorted(links.items(), key=lambda kv: -kv[1][0])[:RELATION_EDGES]
    used_h = {h for (h, _), _ in top}
    used_m = {m for (_, m), _ in top}
    return {
        "heroes": [{"id": h, "name": names.hero_name(h), "games": g, **stats.rate(w, lo)} for h, (g, w, lo) in heroes.items() if h in used_h],
        "maps": [{"id": m, "name": names.map_name(m), "games": g} for m, g in maps.items() if m in used_m],
        "links": [{"hero": h, "map": m, "games": g, **stats.rate(w, lo)} for (h, m), (g, w, lo) in top],
    }


TREND_MIN = 8      # decided games a week needs before it gets a point on the trend line


def panels(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the visual Breakdown shows, from the matched rows: hero tiles, maps, roles, seasons, a weekday by
    time-of-day grid and a weekly win-rate trend. Every rate carries the same interval and minimum as elsewhere."""
    def with_id(key: str, label: Callable[[Any], str]) -> list[dict[str, Any]]:
        t = _tally([{**r, "_k": r[key]} for r in rows], lambda r: str(r["_k"]))
        ids = {str(r[key]): r[key] for r in rows}
        return [{**x, "id": ids[x["label"]], "label": label(ids[x["label"]])} for x in t]
    grid = [[[0, 0] for _ in BLOCKS] for _ in WEEKDAYS]
    weeks: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["result"] in ("win", "loss"):
            c = grid[r["weekday"]][r["block"]]
            c[0] += r["result"] == "win"
            c[1] += 1
            w = weeks[int(r["ts"]) // 604800]
            w[0] += r["result"] == "win"
            w[1] += 1
    heat = [[{**stats.rate(w, n - w), "games": n} for w, n in row] for row in grid]
    pts = [{"week": k, "rate": w / n, "n": n} for k, (w, n) in sorted(weeks.items()) if n >= TREND_MIN]
    return {"heroes": [h for h in with_id("hero", names.hero_name) if h["id"] > 0], "maps": [m for m in with_id("map", lambda m: names.map_name(m) if m >= 0 else NO_MAP) if m["id"] >= 0],
            "roles": [x for x in with_id("role", lambda r: names.ROLES.get(r, "Unknown role")) if x["id"] in names.ROLES],
            "seasons": [s for s in with_id("season", lambda s: names.season_label(s)) if s["id"] >= 0],
            "heat": heat, "weekdays": WEEKDAYS, "blocks": BLOCKS, "trend": _trend(pts)}


def _trend(pts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Weekly win rate as an SVG path in a 600 x 120 box (50% is the middle line). None when fewer than 3 weeks qualify."""
    if len(pts) < 3:
        return None
    lo_w, hi_w = pts[0]["week"], pts[-1]["week"]
    out = []
    for p in pts:
        x = 8 + (584 * (p["week"] - lo_w) / max(hi_w - lo_w, 1))
        y = 112 - 104 * p["rate"]
        out.append({"x": round(x, 1), "y": round(y, 1), "rate": round(p["rate"] * 100), "n": p["n"], "week": p["week"] * 604800})
    return {"points": out, "path": " ".join(("M" if i == 0 else "L") + f"{q['x']},{q['y']}" for i, q in enumerate(out))}


def run(con: sqlite3.Connection, spec: dict[str, Any], group_by: str | None = None) -> dict[str, Any]:
    """spec: keyword arguments of lbug_store.pattern_rows. Raises ValueError when the graph file is missing."""
    if group_by is not None and group_by not in GROUPS:
        raise ValueError(f"group_by must be one of {sorted(GROUPS)}")
    rows, bans = _cached_rows(con, spec)
    wins, losses = sum(r["result"] == "win" for r in rows), sum(r["result"] == "loss" for r in rows)
    groups: list[dict[str, Any]] = []
    if group_by == "ban":
        groups = _tally(bans(), GROUPS["ban"][1])
    elif group_by:
        groups = _tally(rows, GROUPS[group_by][1])
    shown = list(reversed(rows))[:MATCH_LIMIT]
    timeline = [{"ts": r["ts"], "result": r["result"], "hero": names.hero_name(r["hero"])} for r in rows[-TIMELINE_LIMIT:]]
    return {"spec": spec, "group_by": group_by, "total": stats.rate(wins, losses), "games": len(rows), "draws": len(rows) - wins - losses,
            "groups": groups, "panels": panels(rows), "timeline": timeline, "relations": relations(rows), "group_title": GROUPS[group_by][0] if group_by else "",
            "matches": [{**r, "hero_name": names.hero_name(r["hero"]), "map_name": names.map_name(r["map"]) if r["map"] >= 0 else NO_MAP}
                        for r in shown], "truncated": len(rows) > MATCH_LIMIT}


_CACHE: dict[tuple[Any, ...], tuple[list[dict[str, Any]], Callable[[], list[dict[str, Any]]]]] = {}


def _cached_rows(con: sqlite3.Connection, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], Callable[[], list[dict[str, Any]]]]:
    """Graph query results for a spec, kept in memory until the graph file changes (matches never change once played)."""
    path = lbug_store.graph_path(con)
    if not path.exists():
        raise ValueError("The graph is not built yet. Run `rivals-atlas graph --ladybug` or fetch again.")
    stamp = (str(path), path.stat().st_mtime_ns)
    key = (*stamp, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in spec.items())))
    if key not in _CACHE:
        for k in [k for k in _CACHE if k[:2] != stamp]:
            del _CACHE[k]                                  # a rebuilt graph file drops every old entry
        if len(_CACHE) >= 64:
            _CACHE.pop(next(iter(_CACHE)))
        conn = lbug_store.open_readonly(path)
        _CACHE[key] = (lbug_store.pattern_rows(conn, **spec), lambda: lbug_store.pattern_bans(lbug_store.open_readonly(path), **spec))
    return _CACHE[key]


def graph(con: sqlite3.Connection, spec: dict[str, Any], rel: str, min_n: int) -> dict[str, Any]:
    """The hero graph (pairs or hero-map links) over the matches the spec selects."""
    rows = _cached_rows(con, spec)[0]
    return hero_graph.lens_for_matches(con, rows, rel, min_n)


SPEC_INTS = ("mode", "season_from", "season_to", "map_id", "hero", "role", "block", "weekday", "session_pos", "regulars")
SPEC_LISTS = ("banned", "not_banned")          # up to MAX_BANS heroes each: all banned / none banned
MAX_BANS = 3


def parse_spec(query: Any) -> tuple[dict[str, Any], str | None]:
    """Spec and group_by from URL query parameters (empty values count as not set)."""
    spec: dict[str, Any] = {}
    for k in SPEC_INTS:
        v = query.get(k)
        if v and v.lstrip("-").isdigit():
            spec[k] = int(v)
    spec.setdefault("mode", 2)
    for k in SPEC_LISTS:
        ids = [int(v) for v in query.getlist(k) if v.lstrip("-").isdigit()][:MAX_BANS]
        if ids:
            spec[k] = ids
    return spec, (query.get("group_by") or None)


def choices(con: sqlite3.Connection, mode: int) -> dict[str, Any]:
    """Option lists for the form: every known hero, the maps and seasons present in this mode."""
    heroes = sorted(((int(k), v) for k, v in names._heroes().items()), key=lambda x: x[1])
    maps = list(dict.fromkeys(names.canonical_map_id(m) for m in queries.map_ids_by_games(con, mode)))   # one entry per map name
    seasons = queries.seasons_in_mode(con, mode)
    return {"heroes": heroes, "maps": [(m, names.map_name(m)) for m in maps], "seasons": [(s, names.season_label(s)) for s in seasons],
            "roles": sorted(names.ROLES.items()), "blocks": list(enumerate(BLOCKS)), "weekdays": list(enumerate(WEEKDAYS)),
            "positions": [(i, str(i) if i < 5 else "5+") for i in range(1, 6)], "regulars": [(0, "None known"), (1, "One (duo)"), (2, "Two (trio)"), (3, "Three or more")],
            "groups": [(k, v[0]) for k, v in GROUPS.items()]}


_CHIP_LABELS: dict[str, Callable[[int], str]] = {
    "mode": lambda v: stats.MODES.get(v, f"mode {v}").capitalize(), "map_id": names.map_name,
    "season_from": lambda v: f"from {names.season_label(v)}", "season_to": lambda v: f"to {names.season_label(v)}",
    "hero": lambda v: f"plays {names.hero_name(v)}", "role": lambda v: f"role {names.ROLES.get(v, '?').lower()}",
    "block": lambda v: BLOCKS[v], "weekday": lambda v: WEEKDAYS[v], "session_pos": lambda v: f"game {v if v < 5 else '5+'} in session",
    "regulars": lambda v: f"{v} regular teammate{'s' if v != 1 else ''}",
}


def chips(spec: dict[str, Any], group_by: str | None) -> list[dict[str, str]]:
    """One removable chip per condition in the spec (the mode is a choice, not a chip). `drop` is the query string without it;
    a list condition (banned, not banned) gets one chip per hero."""
    from urllib.parse import urlencode

    def query(keep: dict[str, Any]) -> str:
        if group_by:
            keep = {**keep, "group_by": group_by}
        return urlencode({**keep, "go": 1}, doseq=True)

    out = []
    for k, v in spec.items():
        if k == "mode" or v is None:
            continue
        if k in SPEC_LISTS:
            for hero_id in v:
                rest = [h for h in v if h != hero_id]
                keep = {**{a: b for a, b in spec.items() if a != k}, **({k: rest} if rest else {})}
                out.append({"label": f"{names.hero_name(hero_id)} {'banned' if k == 'banned' else 'not banned'}", "drop": query(keep)})
        else:
            out.append({"label": _CHIP_LABELS[k](v), "drop": query({a: b for a, b in spec.items() if a != k})})
    return out
