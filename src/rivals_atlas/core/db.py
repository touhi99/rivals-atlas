"""SQLite store: canonical schema, independent of the source site."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_uid    TEXT PRIMARY KEY,
    played_at    INTEGER NOT NULL,          -- unix seconds
    duration     REAL,
    mode_id      INTEGER NOT NULL,          -- 1 quick play, 2 ranked, others kept as is
    season       INTEGER,                   -- NULL until the history list covers the match
    map_id       INTEGER,
    winner_side  INTEGER,
    score_0      REAL,
    score_1      REAL,
    mvp_id     TEXT,
    svp_id     TEXT,
    has_history  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS match_players (
    match_uid    TEXT NOT NULL REFERENCES matches(match_uid) ON DELETE CASCADE,
    player_id  TEXT NOT NULL,             -- the site's id for the player
    camp         INTEGER NOT NULL,
    hero_id      INTEGER NOT NULL,          -- main hero: most play time
    result       TEXT NOT NULL,             -- win | loss | draw | unknown
    k INTEGER, d INTEGER, a INTEGER,
    damage REAL, heal REAL, taken REAL,
    solo_kills INTEGER, last_kills INTEGER, hit_rate REAL,
    add_score REAL, new_score REAL,         -- rank points won or lost, score after
    level INTEGER, new_level INTEGER,       -- rank tier level before and after (see names.tier)
    is_self INTEGER NOT NULL DEFAULT 0,
    escaped INTEGER,                        -- own line only
    PRIMARY KEY (match_uid, player_id)
);
CREATE INDEX IF NOT EXISTS ix_mp_self ON match_players(is_self, match_uid);
CREATE INDEX IF NOT EXISTS ix_mp_player ON match_players(player_id);
CREATE TABLE IF NOT EXISTS match_hero_lines (
    match_uid    TEXT NOT NULL REFERENCES matches(match_uid) ON DELETE CASCADE,
    player_id  TEXT NOT NULL,
    ord          INTEGER NOT NULL,          -- position in the source list
    hero_id      INTEGER NOT NULL,
    play_time    REAL,
    k INTEGER, d INTEGER, a INTEGER,
    PRIMARY KEY (match_uid, player_id, ord)
);
CREATE TABLE IF NOT EXISTS ban_picks (
    match_uid    TEXT NOT NULL REFERENCES matches(match_uid) ON DELETE CASCADE,
    idx          INTEGER NOT NULL,
    hero_id      INTEGER,
    is_pick      INTEGER,
    battle_side  INTEGER,
    round_idx    INTEGER,
    vote_type    INTEGER,
    PRIMARY KEY (match_uid, idx)
);
CREATE TABLE IF NOT EXISTS player_names (
    player_id TEXT PRIMARY KEY,           -- only regulars (many games together); local, switchable, never exported
    name TEXT NOT NULL,
    seen_at INTEGER NOT NULL                -- match time the name was last seen
);
CREATE TABLE IF NOT EXISTS graph_edges (
    src INTEGER NOT NULL, rel TEXT NOT NULL, dst INTEGER NOT NULL, mode_id INTEGER NOT NULL,
    n INTEGER NOT NULL, wins INTEGER NOT NULL, lo REAL, hi REAL,   -- decided games, wins, Wilson 95%
    PRIMARY KEY (src, rel, dst, mode_id)
);
CREATE TABLE IF NOT EXISTS graph_facts (
    subj_type TEXT NOT NULL, subj_id TEXT NOT NULL, pred TEXT NOT NULL, obj_type TEXT NOT NULL, obj_id TEXT NOT NULL,
    props TEXT NOT NULL DEFAULT '{}',       -- JSON: numbers that belong to the edge (games, win percent, ...)
    source TEXT NOT NULL,                   -- where the fact came from, e.g. rivalsmeta:meta.json
    asserted_at INTEGER NOT NULL,           -- when the source was read (unix seconds)
    PRIMARY KEY (subj_type, subj_id, pred, obj_type, obj_id, source)
);
CREATE INDEX IF NOT EXISTS ix_facts_obj ON graph_facts(obj_type, obj_id);
CREATE TABLE IF NOT EXISTS raw_index (
    kind TEXT NOT NULL, key TEXT NOT NULL, path TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    return con


def connect_readonly(path: Path | str) -> sqlite3.Connection:
    # One connection per request, used one call at a time; FastAPI may run the dependency and the handler on different
    # worker threads, which sqlite3 refuses by default.
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con
