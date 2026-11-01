"""Statistics as pure functions over rows. Rates carry a sample size and a Wilson interval."""
from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from typing import Any

from rivals_atlas.core import names, queries
from rivals_atlas.core.filters import Filter

MIN_GAMES = 5
MODES = {1: "quick play", 2: "ranked"}


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def rate(wins: int, losses: int) -> dict[str, Any]:
    """Win rate over decided games only. Draws are counted elsewhere."""
    n = wins + losses
    lo, hi = wilson(wins, n)
    return {"n": n, "wins": wins, "rate": (wins / n if n else None), "lo": lo, "hi": hi,
            "enough": n >= MIN_GAMES}


def _tally(rows: Sequence[Any], key: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        t = rate(r["wins"], r["losses"])
        out.append({key: r[key], "games": r["games"], "draws": r["draws"], **t,
                    "kda": ((r["k"] + r["a"]) / max(r["d"], 1)) if r["k"] is not None else None})
    return out


def heroes(con: sqlite3.Connection, f: Filter) -> list[dict[str, Any]]:
    return _tally(queries.hero_tallies(con, f), "hero_id")


def _merge_maps(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """One row per map name: the ranked and the quick play id of a map are added together."""
    merged: dict[int, dict[str, Any]] = {}
    for r in rows:
        key = names.canonical_map_id(r["map_id"])
        m = merged.setdefault(key, {"map_id": key, "s0": None, "s1": None, "dur_sum": 0.0, "dur_n": 0, "games": 0, "wins": 0,
                                    "losses": 0, "draws": 0, "k": 0, "d": 0, "a": 0})
        for k in ("games", "wins", "losses", "draws"):
            m[k] += r[k] or 0
        for k in ("k", "d", "a"):
            m[k] += r[k] or 0
        m["s0"] = r["s0"] if m["s0"] is None else min(m["s0"], r["s0"])
        m["s1"] = r["s1"] if m["s1"] is None else max(m["s1"], r["s1"])
        if r["dur"]:
            m["dur_sum"] += r["dur"] * r["games"]
            m["dur_n"] += r["games"]
    out = sorted(merged.values(), key=lambda m: -m["games"])
    for m in out:
        m["dur"] = m["dur_sum"] / m["dur_n"] if m["dur_n"] else None
    return out


def maps(con: sqlite3.Connection, f: Filter) -> list[dict[str, Any]]:
    rows = _merge_maps(queries.map_tallies(con, f))
    out = _tally(rows, "map_id")
    for o, r in zip(out, rows, strict=True):
        o.update(first_season=r["s0"], last_season=r["s1"], minutes=(r["dur"] / 60 if r["dur"] else None))
    return out


def hero_map_grid(con: sqlite3.Connection, f: Filter, heroes: int = 12, maps: int = 12) -> dict[str, Any]:
    """Win rate of the most played heroes on the most played maps (the filter's hero and map are ignored): rows are heroes,
    columns are maps, each cell carries games, decided games, wins and the Wilson interval."""
    base = f.replace(hero=None, map_id=None)
    cells_by: dict[tuple[int, int], dict[str, int]] = {}
    for raw in queries.hero_map_cells(con, base):                     # a map's ranked and quick play ids count as one map
        cell = cells_by.setdefault((raw["h"], names.canonical_map_id(raw["mp"])), {"games": 0, "wins": 0, "losses": 0})
        cell["games"] += raw["games"]; cell["wins"] += raw["wins"]; cell["losses"] += raw["losses"]
    cell_rows = [{"h": h, "mp": mp, **v} for (h, mp), v in cells_by.items()]
    by_hero: dict[int, int] = {}
    by_map: dict[int, int] = {}
    for r in cell_rows:
        by_hero[r["h"]] = by_hero.get(r["h"], 0) + r["games"]
        by_map[r["mp"]] = by_map.get(r["mp"], 0) + r["games"]
    hs = sorted(by_hero, key=lambda h: -by_hero[h])[:heroes]
    ms = sorted(by_map, key=lambda m: -by_map[m])[:maps]
    cells = {(r["h"], r["mp"]): {"games": r["games"], **rate(r["wins"], r["losses"])} for r in cell_rows if r["h"] in hs and r["mp"] in ms}
    return {"heroes": hs, "maps": ms, "cells": cells, "hero_games": {h: by_hero[h] for h in hs}}


def rank_journey(con: sqlite3.Connection, f: Filter) -> list[dict[str, Any]]:
    """The rank score after each ranked match. Quick play rows carry a hidden rating that is not a rank, so the mode is
    always ranked here, whatever mode the page shows."""
    f = f.replace(mode=2)
    return [dict(r) for r in queries.rank_points(con, f)]


def squad(con: sqlite3.Connection, f: Filter, min_games: int = 2) -> list[dict[str, Any]]:
    """Players on the tracked player's side, by games together. Hashed ids; names come from names.player_names."""
    rows = queries.teammates(con, f, min_games)
    return [{"player": names.player_label(con, r["player_id"]), "player_id": r["player_id"], "games": r["games"],
             "last_played": r["last_played"], **rate(r["wins"], r["losses"])} for r in rows]


PARTY_NAMES = {0: "solo", 1: "duo", 2: "trio", 3: "quad", 4: "five"}


def party_combos(con: sqlite3.Connection, f: Filter, hashes: list[str]) -> list[dict[str, Any]]:
    """Every combination of the given teammates that was actually played together, with results.

    A match belongs to the set of those teammates on the tracked player's side ('solo' = none of them; other
    players are not visible). Draws are left out of the win rate."""
    results = queries.own_results(con, f)
    present: dict[str, set[str]] = {}
    for r in queries.teammates_present(con, f, hashes):
        present.setdefault(r["uid"], set()).add(r["h"])
    groups: dict[frozenset[str], list[int]] = {}
    for r in results:
        g = groups.setdefault(frozenset(present.get(r["uid"], ())), [0, 0])
        g[0] += r["result"] == "win"
        g[1] += r["result"] == "loss"
    out = []
    for key, (w, lo_) in groups.items():
        out.append({"members": [h for h in hashes if h in key], "size": len(key),
                    "kind": PARTY_NAMES.get(len(key), f"{len(key) + 1}-stack"), **rate(w, lo_)})
    out.sort(key=lambda x: (x["size"], -x["n"]))
    return out


def overview(con: sqlite3.Connection) -> dict[str, Any]:
    return dict(queries.overview_counts(con))
