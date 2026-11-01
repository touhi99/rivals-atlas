"""Hero graph derived from stored matches: synergy (same team) and counter (opposite teams) edges.

Edges are rebuilt from the match tables at any time. Each carries mode, decided games, wins and a
Wilson interval; draws are left out. Nodes are heroes. Uses all 12 players of every stored match.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import networkx as nx

from rivals_atlas.analysis.stats import heroes as hero_stats
from rivals_atlas.analysis.stats import maps as map_stats
from rivals_atlas.analysis.stats import wilson
from rivals_atlas.core import queries

PAIRS = {
    "SYNERGY": "a.camp = b.camp AND a.hero_id < b.hero_id",
    "COUNTER": "a.camp != b.camp AND a.hero_id != b.hero_id",   # directed: wins are a's
}


def build(con: sqlite3.Connection) -> int:
    """Recompute every edge. Returns the number of edges stored."""
    queries.clear_edges(con)
    for rel, cond in PAIRS.items():
        for r in queries.pair_edge_rows(con, cond):
            lo, hi = wilson(r["wins"], r["n"])
            queries.insert_edge(con, (r["src"], rel, r["dst"], r["mode_id"], r["n"], r["wins"], lo, hi))
    con.commit()
    return queries.edge_count(con)


def hero_games(con: sqlite3.Connection, mode: int) -> dict[int, dict[str, int]]:
    """The tracked player's own games per hero (node size and colour)."""
    return {r["hero_id"]: dict(r) for r in queries.own_games_per_hero(con, mode)}


def load(con: sqlite3.Connection, mode: int, rel: str = "SYNERGY", min_n: int = 10) -> nx.Graph:
    """In-memory NetworkX graph of one relation in one mode, edges with at least min_n decided games."""
    g: nx.Graph = nx.DiGraph() if rel == "COUNTER" else nx.Graph()
    own = hero_games(con, mode)
    for r in queries.edges_of_relation(con, rel, mode, min_n):
        for h in (r["src"], r["dst"]):
            if h not in g:
                g.add_node(h, **own.get(h, {"games": 0, "wins": 0, "losses": 0}))
        g.add_edge(r["src"], r["dst"], n=r["n"], wins=r["wins"], rate=r["wins"] / r["n"], lo=r["lo"], hi=r["hi"])
    return g


def best_path(g: nx.Graph, a: int, b: int) -> list[int] | None:
    try:
        return nx.shortest_path(g, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def lens(con: sqlite3.Connection, f: Any, rel: str = "teammates", min_n: int = 15) -> dict[str, Any]:
    """The hero map for the tracked player. Nodes are heroes; the size of a node is the games played as that
    hero. An edge links the hero played with a hero that was on the same team ('teammates') or on the other team
    ('enemies'), with the player's own results in those matches. 'lobby' uses every player of every stored
    match instead (not only the tracked player). Everything follows the filter, so season, map and teammate
    filters apply. The page lays the heroes out in rings by games played."""
    own = {h["hero_id"]: h for h in hero_stats(con, f)}
    edges: list[dict[str, Any]] = []
    map_games: dict[int, Any] = {}
    if rel == "maps":
        # heroes and maps as nodes; a map node has a negative id so it can never collide with a hero id
        map_games = {m["map_id"]: m for m in map_stats(con, f)}
        for r in queries.hero_map_links(con, f, min_n):
            lo, hi = wilson(r["w"], r["n"])
            edges.append({"source": r["h"], "target": -r["mp"], "n": r["n"], "wins": r["w"], "lo": lo, "hi": hi, "kind": "maps"})
    elif rel == "lobby":
        for r in queries.edges_in_mode(con, f.mode, min_n):
            edges.append({"source": r["src"], "target": r["dst"], "n": r["n"], "wins": r["wins"], "lo": r["lo"],
                          "hi": r["hi"], "kind": "pair" if r["rel"] == "SYNERGY" else "versus"})
    else:
        for r in queries.own_pair_results(con, f, rel, min_n):
            lo, hi = wilson(r["w"], r["n"])
            edges.append({"source": r["h"], "target": r["o"], "n": r["n"], "wins": r["w"], "lo": lo, "hi": hi,
                          "kind": rel})
    for e in edges:
        e["rate"] = e["wins"] / e["n"]
    linked = {e["source"] for e in edges} | {e["target"] for e in edges}
    ids = linked | queries.all_hero_ids(con)          # every hero stays findable
    if rel == "maps":
        ids |= {-m for m in queries.map_ids_in_mode(con, f.mode)}
    nodes = []
    for h in sorted(ids):
        if h < 0:                                   # a map node
            mg = map_games.get(-h)
            nodes.append({"id": h, "kind": "map", "games": mg["games"] if mg else 0, "wins": mg["wins"] if mg else 0,
                          "n": mg["n"] if mg else 0, "rate": mg["rate"] if mg else None, "lo": mg["lo"] if mg else None,
                          "hi": mg["hi"] if mg else None, "linked": h in linked})
            continue
        o = own.get(h)
        nodes.append({"id": h, "games": o["games"] if o else 0, "wins": o["wins"] if o else 0,
                      "n": o["n"] if o else 0, "rate": o["rate"] if o else None,
                      "lo": o["lo"] if o else None, "hi": o["hi"] if o else None, "linked": h in linked})
    return {"rel": rel, "min_n": min_n, "nodes": nodes, "edges": edges,
            "played": sorted(own, key=lambda h: -own[h]["games"])}


def lens_for_matches(con: sqlite3.Connection, rows: list[dict[str, Any]], rel: str = "teammates", min_n: int = 15) -> dict[str, Any]:
    """The same hero map as `lens`, but over an explicit set of the tracked player's matches (the rows an Explore
    query returned, each with `uid`, `hero`, `map`, `result`). Every pair is counted only inside those matches, so
    the graph follows whatever conditions the page holds. 'lobby' pairs every two players of the matched matches."""
    def tally(keys: list[tuple[int, int | None, str]]) -> dict[Any, list[int]]:
        out: dict[Any, list[int]] = {}
        for k, _, res in keys:
            x = out.setdefault(k, [0, 0, 0])
            x[0] += 1
            x[1] += res == "win"
            x[2] += res == "loss"
        return out
    own: dict[int, list[int]] = tally([(r["hero"], None, r["result"]) for r in rows])           # games, wins, losses
    maps: dict[int, list[int]] = tally([(r["map"], None, r["result"]) for r in rows if r["map"] >= 0])
    edges: list[dict[str, Any]] = []

    def add(src: int, dst: int, w: int, n: int, kind: str) -> None:
        if n >= min_n:
            lo, hi = wilson(w, n)
            edges.append({"source": src, "target": dst, "n": n, "wins": w, "lo": lo, "hi": hi, "kind": kind, "rate": w / n})

    if rel == "maps":
        pair: dict[tuple[int, int], list[int]] = {}
        for r in rows:
            if r["map"] >= 0 and r["result"] in ("win", "loss"):
                x = pair.setdefault((r["hero"], r["map"]), [0, 0])
                x[0] += 1
                x[1] += r["result"] == "win"
        for (h, mp), (n, w) in pair.items():
            add(h, -mp, w, n, "maps")
    elif rows:
        queries.select_matches(con, [r["uid"] for r in rows])
        if rel == "lobby":
            for pr in queries.selected_lobby_pairs(con):
                add(pr["s"], pr["d"], pr["w"], pr["n"], "pair" if pr["same"] else "versus")
        else:
            for pr in queries.selected_own_pairs(con, rel):
                add(pr["h"], pr["o"], pr["w"], pr["n"], rel)
    linked = {e["source"] for e in edges} | {e["target"] for e in edges}
    ids = linked | queries.all_hero_ids(con)          # every hero stays findable
    if rel == "maps":
        ids |= {-m for m in maps}

    def node(i: int, games: int, w: int, losses: int) -> dict[str, Any]:
        n = w + losses
        r = wilson(w, n) if n else (None, None)
        return {"id": i, "games": games, "wins": w, "n": n, "rate": w / n if n else None, "lo": r[0], "hi": r[1], "linked": i in linked}
    nodes = []
    for i in sorted(ids):
        if i < 0:
            nodes.append({**node(i, *maps[-i]), "kind": "map"})
        else:
            nodes.append(node(i, *own[i]) if i in own else node(i, 0, 0, 0))
    return {"rel": rel, "min_n": min_n, "nodes": nodes, "edges": edges, "played": sorted(own, key=lambda h: -own[h][0])}
