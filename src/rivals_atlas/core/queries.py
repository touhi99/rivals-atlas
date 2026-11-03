"""Every SQL statement of the app, in one place (the table definitions are in `core/db.py`, the model-written Cypher
for the graph file is in `graph/store.py`).

Sections: statistics and pages, pattern and finding searches, option lists and counts, the agent tools, the hero graph,
the facts graph, the graph file's inputs, and the writes of the importer and the derived tables.

Rules for this file (they are what keeps the app safe from SQL injection):

* A value that comes from a request, the model or a file is always a `?` parameter, never part of the SQL text.
* An f-string may only splice in fixed fragments that are defined in this code base: the condition text compiled by
  `Filter.cond()` (which itself only holds `?` placeholders), a list of `?` marks, or a column/alias name chosen from a
  fixed set. Anything else is a bug.
* The functions return `sqlite3.Row` lists or plain values; shaping the result is the caller's job.

Aliases in filter conditions: p = the tracked player's `match_players` row, m = `matches` (see `core/filters.py`).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from rivals_atlas.core.filters import Filter

Rows = list[sqlite3.Row]

# the per-group figures every tally carries: games, decided games, kills/deaths/assists sums
AGG = ("COUNT(*) games, SUM(result='win') wins, SUM(result='loss') losses, SUM(result='draw') draws,"
       " SUM(k) k, SUM(d) d, SUM(a) a")


# ---- the tracked player's own matches, grouped (statistics) -------------------------------------------------------

def hero_tallies(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        f"SELECT p.hero_id, {AGG} FROM match_players p JOIN matches m USING(match_uid) "
        f"WHERE p.is_self=1 AND {c} GROUP BY p.hero_id ORDER BY games DESC", a).fetchall()


def map_tallies(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        f"SELECT m.map_id, MIN(m.season) s0, MAX(m.season) s1, AVG(m.duration) dur, {AGG} FROM match_players p "
        f"JOIN matches m USING(match_uid) WHERE p.is_self=1 AND m.map_id IS NOT NULL AND {c} "
        "GROUP BY m.map_id ORDER BY games DESC", a).fetchall()


def hero_map_cells(con: sqlite3.Connection, f: Filter) -> Rows:
    """Wins and losses per hero and map (the filter's own hero and map are expected to be cleared by the caller)."""
    c, a = f.cond()
    return con.execute(
        "SELECT p.hero_id h, m.map_id mp, COUNT(*) games, SUM(p.result='win') wins, SUM(p.result='loss') losses "
        "FROM match_players p JOIN matches m USING(match_uid) "
        f"WHERE p.is_self=1 AND p.hero_id > 0 AND m.map_id IS NOT NULL AND {c} GROUP BY p.hero_id, m.map_id", a).fetchall()


def rank_points(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT m.match_uid, m.played_at, m.season, p.add_score, p.new_score, p.new_level, p.result FROM match_players p "
        f"JOIN matches m USING(match_uid) WHERE p.is_self=1 AND p.new_score IS NOT NULL AND {c} "
        "ORDER BY m.played_at", a).fetchall()


def teammates(con: sqlite3.Connection, f: Filter, min_games: int) -> Rows:
    """Players on the tracked player's side by games together (hashed ids)."""
    c, a = f.cond()
    return con.execute(
        "SELECT t.player_id, COUNT(*) games, SUM(t.result='win') wins, SUM(t.result='loss') losses, "
        "MAX(m.played_at) last_played FROM match_players p JOIN match_players t "
        "ON t.match_uid=p.match_uid AND t.camp=p.camp AND t.is_self=0 JOIN matches m ON m.match_uid=p.match_uid "
        f"WHERE p.is_self=1 AND {c} GROUP BY t.player_id HAVING games>=? ORDER BY games DESC LIMIT 50",
        [*a, min_games]).fetchall()


def matchup_rows(con: sqlite3.Connection, f: Filter) -> Rows:
    """(match, result, enemy hero) for the tracked player's decided matches, one row per hero on the other side."""
    c, a = f.cond()
    return con.execute(
        "SELECT p.match_uid uid, p.result, o.hero_id enemy FROM match_players p JOIN match_players o "
        "ON o.match_uid=p.match_uid AND o.camp!=p.camp JOIN matches m ON m.match_uid=p.match_uid "
        f"WHERE p.is_self=1 AND p.result IN ('win','loss') AND o.hero_id > 0 AND {c}", a).fetchall()


def resolve_player(con: sqlite3.Connection, prefix: str) -> str | None:
    """The one teammate id that starts with `prefix` (at least 4 characters), else None."""
    if len(prefix) < 4:
        return None
    hits = [r[0] for r in con.execute(
        "SELECT DISTINCT player_id FROM match_players WHERE is_self=0 AND player_id LIKE ? LIMIT 2", (prefix.replace("%", "") + "%",))]
    return hits[0] if len(hits) == 1 else None


def own_results(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        f"SELECT p.match_uid uid, p.result FROM match_players p JOIN matches m USING(match_uid) WHERE p.is_self=1 AND {c}", a).fetchall()


def teammates_present(con: sqlite3.Connection, f: Filter, hashes: list[str]) -> Rows:
    """(match, teammate) pairs for the given teammates on the tracked player's side."""
    c, a = f.cond()
    marks = ",".join("?" * len(hashes)) or "''"
    return con.execute(
        "SELECT p.match_uid uid, t.player_id h FROM match_players p JOIN match_players t "
        "ON t.match_uid=p.match_uid AND t.camp=p.camp AND t.is_self=0 JOIN matches m ON m.match_uid=p.match_uid "
        f"WHERE p.is_self=1 AND {c} AND t.player_id IN ({marks})", [*a, *hashes]).fetchall()


def overview_counts(con: sqlite3.Connection) -> sqlite3.Row:
    return con.execute("SELECT COUNT(*) n, MIN(played_at) first, MAX(played_at) last, SUM(has_history) with_history FROM matches").fetchone()


# ---- rows the pattern and finding searches work on ------------------------------------------------------------------

def pattern_rows(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT p.match_uid, p.result, p.hero_id, p.add_score, p.k, p.d, m.mode_id, m.played_at, m.duration, m.season, "
        "(SELECT COUNT(*) FROM match_hero_lines h WHERE h.match_uid=p.match_uid AND h.player_id=p.player_id) swaps, "
        "(m.mvp_id = p.player_id) mvp, (m.svp_id = p.player_id) svp FROM match_players p "
        f"JOIN matches m USING(match_uid) WHERE p.is_self=1 AND {c} ORDER BY m.played_at", a).fetchall()


def decided_rows(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT p.match_uid, p.hero_id, p.result, p.camp, m.map_id, m.played_at FROM match_players p "
        f"JOIN matches m USING(match_uid) WHERE p.is_self=1 AND p.result IN ('win','loss') AND {c} "
        "ORDER BY m.played_at", a).fetchall()


def enemy_heroes(con: sqlite3.Connection, f: Filter) -> Rows:
    """(match, hero) for every hero on the other side of the tracked player's matches."""
    c, a = f.cond()
    return con.execute(
        "SELECT p.match_uid, o.hero_id FROM match_players p JOIN match_players o "
        "ON o.match_uid=p.match_uid AND o.camp!=p.camp JOIN matches m ON m.match_uid=p.match_uid "
        f"WHERE p.is_self=1 AND o.hero_id > 0 AND {c}", a).fetchall()


def teammate_matches(con: sqlite3.Connection, f: Filter) -> Rows:
    """(match, teammate hash) for every teammate on the tracked player's side."""
    c, a = f.cond()
    return con.execute(
        "SELECT p.match_uid, t.player_id FROM match_players p JOIN match_players t "
        "ON t.match_uid=p.match_uid AND t.camp=p.camp AND t.is_self=0 JOIN matches m ON m.match_uid=p.match_uid "
        f"WHERE p.is_self=1 AND {c}", a).fetchall()


def own_match_ids(con: sqlite3.Connection, f: Filter) -> list[str]:
    c, a = f.cond()
    return [r[0] for r in con.execute(
        f"SELECT m.match_uid FROM match_players p JOIN matches m USING(match_uid) WHERE p.is_self=1 AND {c} "
        "ORDER BY m.played_at", a)]


def own_timeline(con: sqlite3.Connection, f: Filter) -> Rows:
    """(match, time, result) in play order."""
    c, a = f.cond()
    return con.execute("SELECT m.match_uid, m.played_at, p.result FROM match_players p JOIN matches m USING(match_uid) "
                       f"WHERE p.is_self=1 AND {c} ORDER BY m.played_at", a).fetchall()


# ---- option lists, counts, labels --------------------------------------------------------------------------------

def map_ids_by_games(con: sqlite3.Connection, mode: int) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT map_id FROM matches WHERE (mode_id=? OR ?=0) AND map_id IS NOT NULL GROUP BY map_id ORDER BY COUNT(*) DESC",
        (mode, mode))]


def seasons_in_mode(con: sqlite3.Connection, mode: int) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT season FROM matches WHERE (mode_id=? OR ?=0) AND season IS NOT NULL ORDER BY season DESC", (mode, mode))]


def season_starts(con: sqlite3.Connection, mode: int) -> Rows:
    """Where each season starts in this mode (mode 0 = every mode)."""
    return con.execute(
        "SELECT season, MIN(played_at) t0 FROM matches WHERE (mode_id=? OR ?=0) AND season IS NOT NULL "
        "GROUP BY season ORDER BY season", (mode, mode)).fetchall()


def matches_per_mode(con: sqlite3.Connection) -> dict[int, int]:
    return {r[0]: r[1] for r in con.execute("SELECT mode_id, COUNT(*) FROM matches GROUP BY mode_id")}


def modes_by_matches(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT mode_id, COUNT(*) FROM matches GROUP BY mode_id ORDER BY 2 DESC").fetchall()


def match_count(con: sqlite3.Connection, mode: int) -> int:
    return int(con.execute("SELECT COUNT(*) FROM matches WHERE mode_id=? OR ?=0", (mode, mode)).fetchone()[0])


def career_games(con: sqlite3.Connection) -> dict[int, int]:
    """Games per hero over the whole stored history (every mode and season, no filter)."""
    return {r[0]: r[1] for r in con.execute("SELECT hero_id, COUNT(*) FROM match_players WHERE is_self=1 GROUP BY hero_id")}


def player_alias(con: sqlite3.Connection, player_id: str) -> str | None:
    try:
        row = con.execute("SELECT name FROM player_names WHERE player_id=?", (player_id,)).fetchone()
    except sqlite3.OperationalError:     # table missing in an old database
        return None
    return str(row[0]) if row else None


def stored_figure(con: sqlite3.Connection, name: str) -> int:
    """One of the fixed counts the Data page shows. `name` must be a key of FIGURES; it is never request data."""
    return int(con.execute(FIGURES[name]).fetchone()[0] or 0)


FIGURES = {
    "matches": "SELECT COUNT(*) FROM matches",
    "seasons": "SELECT COUNT(DISTINCT season) FROM matches WHERE season IS NOT NULL",
    "players": "SELECT COUNT(DISTINCT player_id) FROM match_players",
    "named": "SELECT COUNT(*) FROM player_names",
    "no_history": "SELECT COUNT(*) FROM matches WHERE has_history = 0",
    "player_lines": "SELECT COUNT(*) FROM match_players",
    "hero_lines": "SELECT COUNT(*) FROM match_hero_lines",
    "bans": "SELECT COUNT(*) FROM ban_picks",
    "first": "SELECT MIN(played_at) FROM matches",
    "last": "SELECT MAX(played_at) FROM matches",
    "edges": "SELECT COUNT(*) FROM graph_edges",
}


# ---- pages that need their own grouping ---------------------------------------------------------------------------

def wins_losses_by_season(con: sqlite3.Connection, f: Filter) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT m.season, SUM(p.result='win') wins, SUM(p.result='loss') losses FROM match_players p JOIN matches m "
        f"USING(match_uid) WHERE p.is_self=1 AND m.season IS NOT NULL AND {c} GROUP BY m.season ORDER BY m.season", a).fetchall()


def latest_results(con: sqlite3.Connection, f: Filter, limit: int) -> list[str]:
    """The most recent results, oldest first."""
    c, a = f.cond()
    rows = con.execute(
        f"SELECT p.result FROM match_players p JOIN matches m USING(match_uid) WHERE p.is_self=1 AND {c} "
        "ORDER BY m.played_at DESC LIMIT ?", [*a, limit]).fetchall()
    return [r["result"] for r in rows][::-1]


def latest_matches(con: sqlite3.Connection, f: Filter, limit: int) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT m.played_at, m.map_id, m.mode_id, p.result, p.k, p.d, p.a, p.add_score FROM match_players p JOIN matches m "
        f"USING(match_uid) WHERE p.is_self=1 AND {c} ORDER BY m.played_at DESC LIMIT ?", [*a, limit]).fetchall()


def daily_results(con: sqlite3.Connection, f: Filter, since: int) -> Rows:
    """Games, wins and losses per local calendar day, from the given time on."""
    c, a = f.cond()
    return con.execute(
        "SELECT date(m.played_at, 'unixepoch', 'localtime') day, COUNT(*) games, SUM(p.result='win') wins, SUM(p.result='loss') losses "
        f"FROM match_players p JOIN matches m USING(match_uid) WHERE p.is_self=1 AND m.played_at >= ? AND {c} "
        "GROUP BY day ORDER BY day", [since, *a]).fetchall()


def match_receipt(con: sqlite3.Connection, uid: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT m.match_uid, m.played_at, m.mode_id, m.season, m.map_id, m.duration, p.hero_id, p.result, p.k, p.d, p.a "
        "FROM matches m LEFT JOIN match_players p ON p.match_uid=m.match_uid AND p.is_self=1 WHERE m.match_uid=?",
        (uid,)).fetchone()


def pair_match_ids(con: sqlite3.Connection, a: int, b: int, relation_sql: str, mode: int) -> list[str]:
    """Matches in which hero a and hero b stood in a relation. `relation_sql` is one of the fixed conditions in
    agents/tools.py (_REL_COND), never request data."""
    return [r[0] for r in con.execute(
        "SELECT DISTINCT m.match_uid FROM match_players a JOIN match_players b ON a.match_uid=b.match_uid "
        f"AND {relation_sql} AND a.hero_id=? AND b.hero_id=? JOIN matches m ON m.match_uid=a.match_uid "
        "WHERE m.mode_id=? AND a.result IN ('win','loss') ORDER BY m.played_at", (a, b, mode))]


def graph_neighbour_edges(con: sqlite3.Connection, hero: int, rel: str, mode: int, min_n: int) -> Rows:
    """Stored hero-pair edges around a hero. `rel` is SYNERGY (same team, either end) or COUNTER (the hero is the source)."""
    if rel == "SYNERGY":
        return con.execute("SELECT * FROM graph_edges WHERE rel=? AND mode_id=? AND n>=? AND (src=? OR dst=?)",
                           [rel, mode, min_n, hero, hero]).fetchall()
    return con.execute("SELECT * FROM graph_edges WHERE rel=? AND mode_id=? AND n>=? AND src=?", [rel, mode, min_n, hero]).fetchall()




# ======================================================================================================================
# The hero graph (derived table graph_edges) and the lenses over the tracked player's matches
# ======================================================================================================================

# which side the second hero is on; chosen by code from the relation name, never request text
_SIDE = {"teammates": "t.camp = p.camp", "enemies": "t.camp != p.camp"}


def clear_edges(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM graph_edges")


def pair_edge_rows(con: sqlite3.Connection, relation_sql: str) -> Rows:
    """Every hero pair in one relation over all 12 players of every stored match. `relation_sql` is one of the fixed
    conditions of `graph/network.py` (PAIRS)."""
    return con.execute(
        "SELECT a.hero_id src, b.hero_id dst, m.mode_id mode_id, SUM(a.result='win') wins, "
        "SUM(a.result IN ('win','loss')) n FROM match_players a JOIN match_players b "
        f"ON a.match_uid = b.match_uid AND {relation_sql} JOIN matches m ON m.match_uid = a.match_uid "
        "WHERE a.hero_id > 0 AND b.hero_id > 0 GROUP BY a.hero_id, b.hero_id, m.mode_id HAVING n > 0").fetchall()


def insert_edge(con: sqlite3.Connection, row: tuple[Any, ...]) -> None:
    con.execute("INSERT INTO graph_edges VALUES (?,?,?,?,?,?,?,?)", row)


def edge_count(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0])


def own_games_per_hero(con: sqlite3.Connection, mode: int) -> Rows:
    return con.execute(
        "SELECT p.hero_id, COUNT(*) games, SUM(p.result='win') wins, SUM(p.result='loss') losses "
        "FROM match_players p JOIN matches m USING(match_uid) WHERE p.is_self=1 AND m.mode_id=? "
        "GROUP BY p.hero_id", (mode,)).fetchall()


def edges_of_relation(con: sqlite3.Connection, rel: str, mode: int, min_n: int) -> Rows:
    return con.execute("SELECT * FROM graph_edges WHERE rel=? AND mode_id=? AND n>=?", (rel, mode, min_n)).fetchall()


def edges_in_mode(con: sqlite3.Connection, mode: int, min_n: int) -> Rows:
    return con.execute("SELECT * FROM graph_edges WHERE mode_id=? AND n>=? AND src > 0 AND dst > 0", (mode, min_n)).fetchall()


def hero_map_links(con: sqlite3.Connection, f: Filter, min_n: int) -> Rows:
    c, a = f.cond()
    return con.execute(
        "SELECT p.hero_id h, m.map_id mp, SUM(p.result='win') w, SUM(p.result IN ('win','loss')) n FROM match_players p "
        f"JOIN matches m USING(match_uid) WHERE p.is_self=1 AND p.hero_id > 0 AND m.map_id IS NOT NULL AND {c} "
        "GROUP BY p.hero_id, m.map_id HAVING n >= ?", [*a, min_n]).fetchall()


def own_pair_results(con: sqlite3.Connection, f: Filter, rel: str, min_n: int) -> Rows:
    """The tracked player's hero with every hero on the same ('teammates') or the other ('enemies') side."""
    c, a = f.cond()
    return con.execute(
        "SELECT p.hero_id h, t.hero_id o, SUM(p.result='win') w, SUM(p.result IN ('win','loss')) n "
        f"FROM match_players p JOIN match_players t ON t.match_uid=p.match_uid AND {_SIDE[rel]} AND t.is_self=0 "
        f"JOIN matches m ON m.match_uid=p.match_uid WHERE p.is_self=1 AND p.hero_id > 0 AND t.hero_id > 0 AND {c} "
        "GROUP BY p.hero_id, t.hero_id HAVING n >= ?", [*a, min_n]).fetchall()


def all_hero_ids(con: sqlite3.Connection) -> set[int]:
    return {r[0] for r in con.execute("SELECT DISTINCT hero_id FROM match_players WHERE hero_id > 0")}


def map_ids_in_mode(con: sqlite3.Connection, mode: int) -> set[int]:
    return {r[0] for r in con.execute("SELECT DISTINCT map_id FROM matches WHERE map_id IS NOT NULL AND (mode_id=? OR ?=0)", (mode, mode))}


def select_matches(con: sqlite3.Connection, uids: list[str]) -> None:
    """Hold a set of match ids in a temporary table so the next queries can restrict to them."""
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _sel(uid TEXT PRIMARY KEY)")
    con.execute("DELETE FROM _sel")
    con.executemany("INSERT OR IGNORE INTO _sel VALUES (?)", [(u,) for u in uids])


def selected_lobby_pairs(con: sqlite3.Connection) -> Rows:
    return con.execute(
        "SELECT a.hero_id s, b.hero_id d, a.camp = b.camp same, SUM(a.result='win') w, SUM(a.result IN ('win','loss')) n "
        "FROM match_players a JOIN match_players b ON b.match_uid=a.match_uid AND b.hero_id > a.hero_id "
        "WHERE a.hero_id > 0 AND a.match_uid IN (SELECT uid FROM _sel) GROUP BY a.hero_id, b.hero_id, a.camp = b.camp").fetchall()


def selected_own_pairs(con: sqlite3.Connection, rel: str) -> Rows:
    return con.execute(
        "SELECT p.hero_id h, t.hero_id o, SUM(p.result='win') w, SUM(p.result IN ('win','loss')) n "
        f"FROM match_players p JOIN match_players t ON t.match_uid=p.match_uid AND {_SIDE[rel]} AND t.is_self=0 "
        "WHERE p.is_self=1 AND p.hero_id > 0 AND t.hero_id > 0 AND p.match_uid IN (SELECT uid FROM _sel) "
        "GROUP BY p.hero_id, t.hero_id").fetchall()


# ======================================================================================================================
# The facts graph (derived table graph_facts)
# ======================================================================================================================

def insert_fact(con: sqlite3.Connection, row: tuple[Any, ...]) -> None:
    con.execute("INSERT OR REPLACE INTO graph_facts VALUES (?,?,?,?,?,?,?,?)", row)


def delete_facts_from(con: sqlite3.Connection, source: str) -> None:
    con.execute("DELETE FROM graph_facts WHERE source=?", (source,))


def count_facts_from(con: sqlite3.Connection, source: str) -> int:
    return int(con.execute("SELECT COUNT(*) FROM graph_facts WHERE source=?", (source,)).fetchone()[0])


# ======================================================================================================================
# What the graph file is built from (graph/store.py) and checked against
# ======================================================================================================================

def sides_of_matches(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT match_uid, camp, hero_id, is_self FROM match_players").fetchall()


def graph_hero_ids(con: sqlite3.Connection) -> list[int]:
    """Every hero that played or was banned."""
    played = {r[0] for r in con.execute("SELECT DISTINCT hero_id FROM match_players")}
    banned = {r[0] for r in con.execute("SELECT DISTINCT hero_id FROM ban_picks WHERE hero_id > 0")}
    return sorted(played | banned)


def distinct_map_ids(con: sqlite3.Connection) -> list[int]:
    return [r[0] for r in con.execute("SELECT DISTINCT map_id FROM matches WHERE map_id IS NOT NULL")]


def distinct_seasons(con: sqlite3.Connection) -> list[int]:
    return [r[0] for r in con.execute("SELECT DISTINCT season FROM matches WHERE season IS NOT NULL")]


def distinct_modes(con: sqlite3.Connection) -> list[int]:
    return [r[0] for r in con.execute("SELECT DISTINCT mode_id FROM matches")]


def own_results_by_mode(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT m.match_uid, m.mode_id, m.played_at, p.result, p.add_score FROM matches m "
                       "JOIN match_players p ON p.match_uid=m.match_uid AND p.is_self=1 ORDER BY m.mode_id, m.played_at").fetchall()


REGULAR_GAMES = 5      # a teammate with at least this many games on the tracked player's side counts as a regular


def regular_teammates_per_match(con: sqlite3.Connection) -> dict[str, int]:
    """Per match: how many regular teammates (REGULAR_GAMES or more games together) stood on the tracked player's side."""
    return {r[0]: r[1] for r in con.execute(
        "SELECT p.match_uid, COUNT(t.player_id) FROM match_players p LEFT JOIN match_players t ON t.match_uid=p.match_uid "
        "AND t.camp=p.camp AND t.is_self=0 AND t.player_id IN (SELECT t2.player_id FROM match_players p2 JOIN match_players t2 "
        "ON t2.match_uid=p2.match_uid AND t2.camp=p2.camp AND t2.is_self=0 WHERE p2.is_self=1 "
        "GROUP BY t2.player_id HAVING COUNT(*) >= ?) WHERE p.is_self=1 GROUP BY p.match_uid", (REGULAR_GAMES,))}


def all_matches(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT * FROM matches").fetchall()


def player_lines(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT match_uid, player_id, camp, hero_id, result, k, d, a, damage, heal, taken, is_self FROM match_players").fetchall()


def match_map_pairs(con: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(r[0], r[1]) for r in con.execute("SELECT match_uid, map_id FROM matches WHERE map_id IS NOT NULL")]


def match_season_pairs(con: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(r[0], r[1]) for r in con.execute("SELECT match_uid, season FROM matches WHERE season IS NOT NULL")]


def match_mode_pairs(con: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(r[0], r[1]) for r in con.execute("SELECT match_uid, mode_id FROM matches")]


def ban_rows(con: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in con.execute("SELECT match_uid, hero_id, battle_side, round_idx FROM ban_picks WHERE hero_id > 0 AND is_pick=0")]


def mode_signature(con: sqlite3.Connection) -> set[tuple[Any, ...]]:
    """Per mode: matches, matches with a season, matches with a map (what the graph file is compared against)."""
    return {tuple(r) for r in con.execute("SELECT mode_id, COUNT(*), COUNT(season), COUNT(map_id) FROM matches GROUP BY mode_id")}


def database_file(con: sqlite3.Connection) -> str:
    return str(next(r[2] for r in con.execute("PRAGMA database_list") if r[1] == "main"))


# ======================================================================================================================
# Writes of the importer (ingest/importer.py)
# ======================================================================================================================

def known_seasons(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT played_at, season FROM matches WHERE season IS NOT NULL ORDER BY played_at").fetchall()


def matches_without_season(con: sqlite3.Connection) -> Rows:
    return con.execute("SELECT match_uid, played_at FROM matches WHERE season IS NULL").fetchall()


def set_season(con: sqlite3.Connection, uid: str, season: int) -> None:
    con.execute("UPDATE matches SET season=? WHERE match_uid=?", (season, uid))


def clear_player_names(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM player_names")


def insert_player_names(con: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> None:
    con.executemany("INSERT INTO player_names VALUES (?,?,?)", rows)


def delete_match(con: sqlite3.Connection, uid: str) -> None:
    con.execute("DELETE FROM matches WHERE match_uid = ?", (uid,))


def insert_match(con: sqlite3.Connection, row: dict[str, Any]) -> None:
    con.execute("INSERT INTO matches VALUES (:match_uid,:played_at,:duration,:mode_id,:season,:map_id,:winner_side,"
                ":score_0,:score_1,:mvp_id,:svp_id,:has_history)", row)


def insert_match_players(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    con.executemany(
        "INSERT INTO match_players VALUES (:match_uid,:player_id,:camp,:hero_id,:result,:k,:d,:a,:damage,:heal,"
        ":taken,:solo_kills,:last_kills,:hit_rate,:add_score,:new_score,:level,:new_level,:is_self,:escaped)", rows)


def insert_hero_lines(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    con.executemany("INSERT INTO match_hero_lines VALUES (:match_uid,:player_id,:ord,:hero_id,:play_time,:k,:d,:a)", rows)


def insert_ban_picks(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    con.executemany("INSERT INTO ban_picks VALUES (:match_uid,:idx,:hero_id,:is_pick,:battle_side,:round_idx,:vote_type)", rows)


def index_raw_match(con: sqlite3.Connection, uid: str, file_name: str) -> None:
    con.execute("INSERT OR REPLACE INTO raw_index VALUES ('match', ?, ?)", (uid, file_name))
