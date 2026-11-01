"""Graph projection in LadybugDB. Derived from SQLite, never edited by hand.

SQLite stays the store of truth. `build` writes a NEW database file from the tables, so the web app can open the old one
read-only meanwhile and swap files afterwards (LadybugDB allows one read-write opener or many read-only ones, never both).

Shape: (Match)-[:HAS_LINE]->(Line)-[:USED]->(Hero); Match -ON_MAP-> Map, -IN-> Season, -IN_MODE-> Mode; Match -BANNED{side,round}-> Hero;
Hero -MEMBER_OF-> TeamUp. A Line is one of the 12 players of a match with that player's numbers. Match properties carry the
derived attributes (time block, weekday, session position, the tracked player's result and rank change).
"""
from __future__ import annotations

import csv
import re
import sqlite3
import tempfile
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import ladybug as lb

from rivals_atlas.analysis import patterns, stats
from rivals_atlas.core import names, queries

SCHEMA = [
    "CREATE NODE TABLE Hero(id INT64 PRIMARY KEY, name STRING, role INT64, role_name STRING)",
    "CREATE NODE TABLE Map(id INT64 PRIMARY KEY, name STRING)",
    "CREATE NODE TABLE Season(n INT64 PRIMARY KEY, label STRING)",
    "CREATE NODE TABLE Mode(id INT64 PRIMARY KEY, name STRING)",
    "CREATE NODE TABLE TeamUp(id STRING PRIMARY KEY, matches INT64, win DOUBLE)",
    ("CREATE NODE TABLE Match(uid STRING PRIMARY KEY, ts INT64, mode INT64, season INT64, map INT64, duration DOUBLE, "
     "block INT64, weekday INT64, session_pos INT64, regulars INT64, winner_side INT64, self_result STRING, rank_delta DOUBLE, comp STRING, enemy_comp STRING)"),
    ("CREATE NODE TABLE Line(id STRING PRIMARY KEY, player STRING, camp INT64, result STRING, k INT64, d INT64, a INT64, "
     "damage DOUBLE, heal DOUBLE, taken DOUBLE, is_self BOOLEAN)"),
    "CREATE REL TABLE ON_MAP(FROM Match TO Map)",
    "CREATE REL TABLE IN_SEASON(FROM Match TO Season)",
    "CREATE REL TABLE IN_MODE(FROM Match TO Mode)",
    "CREATE REL TABLE HAS_LINE(FROM Match TO Line)",
    "CREATE REL TABLE USED(FROM Line TO Hero)",
    "CREATE REL TABLE BANNED(FROM Match TO Hero, side INT64, round INT64)",
    "CREATE REL TABLE MEMBER_OF(FROM Hero TO TeamUp)",
]


def _csv(d: Path, name: str, header: list[str], rows: Any) -> Path:
    p = d / f"{name}.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return p


def _one(c: Any, query: str) -> Any:
    """First value of the first row."""
    res = c.execute(query)
    return (res[0] if isinstance(res, list) else res).get_all()[0][0]


def _comps(con: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Per match: the role mix of the tracked player's side and of the other side, as 'V-D-S' counts ('2-2-2' = two vanguards,
    two duelists, two strategists). Computed once here so a query is a plain property match."""
    sides: dict[str, dict[int, list[int]]] = {}
    own_camp: dict[str, int] = {}
    for r in queries.sides_of_matches(con):
        role = names.role_id(r["hero_id"]) or 0
        counts = sides.setdefault(r["match_uid"], {}).setdefault(r["camp"], [0, 0, 0, 0])
        counts[role] += 1
        if r["is_self"]:
            own_camp[r["match_uid"]] = r["camp"]
    out = {}
    for uid, camp in own_camp.items():
        mine = sides[uid][camp]
        theirs = next((c for k, c in sides[uid].items() if k != camp), [0, 0, 0, 0])
        out[uid] = tuple("-".join(map(str, c[1:])) for c in (mine, theirs))
    return out  # type: ignore[return-value]


def build(con: sqlite3.Connection, path: Path | str, meta: dict[str, Any] | None = None) -> dict[str, int]:
    """Write a fresh LadybugDB file at `path` (must not exist). Returns counts of what was loaded."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists: build a new file and swap it in")
    db = lb.Database(str(path))
    c = lb.Connection(db)
    for s in SCHEMA:
        c.execute(s)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        heroes = queries.graph_hero_ids(con)
        maps = queries.distinct_map_ids(con)
        seasons = queries.distinct_seasons(con)
        modes = queries.distinct_modes(con)
        load: dict[str, tuple[list[str], list[tuple[Any, ...]]]] = {
            "Hero": (["id", "name", "role", "role_name"], [(h, names.hero_name(h), names.role_id(h) or 0, names.role_name(h)) for h in heroes]),
            "Map": (["id", "name"], [(m, names.map_name(m)) for m in maps]),
            "Season": (["n", "label"], [(s, names.season_label(s)) for s in seasons]),
            "Mode": (["id", "name"], [(m, stats.MODES.get(m, f"mode {m}")) for m in modes]),
        }
        # derived match attributes: session position is numbered per mode over the tracked player's own matches
        own = queries.own_results_by_mode(con)
        pos: dict[str, int] = {}
        for mode in modes:
            rows = [r for r in own if r["mode_id"] == mode]
            for r, k in zip(rows, patterns.session_positions([r["played_at"] for r in rows]), strict=True):
                pos[r["match_uid"]] = k
        self_info = {r["match_uid"]: (r["result"], r["add_score"]) for r in own}
        # regular teammates (players kept in player_names) on the tracked player's side: 0 = no known regular, 1 = duo, 2 = trio ...
        regulars = queries.regular_teammates_per_match(con)
        comps = _comps(con)
        match_rows = []
        for m in queries.all_matches(con):
            t = datetime.fromtimestamp(m["played_at"])
            res, add = self_info.get(m["match_uid"], ("", None))
            match_rows.append((m["match_uid"], m["played_at"], m["mode_id"], m["season"] if m["season"] is not None else -1,
                               m["map_id"] if m["map_id"] is not None else -1, m["duration"] or 0, t.hour // 6, t.weekday(),
                               pos.get(m["match_uid"], 0), regulars.get(m["match_uid"], 0), m["winner_side"] if m["winner_side"] is not None else -1, res,
                               add if add is not None else 0, *comps.get(m["match_uid"], ("", ""))))
        load["Match"] = (["uid", "ts", "mode", "season", "map", "duration", "block", "weekday", "session_pos", "regulars", "winner_side",
                          "self_result", "rank_delta", "comp", "enemy_comp"], match_rows)
        lines = list(queries.player_lines(con))
        load["Line"] = (["id", "player", "camp", "result", "k", "d", "a", "damage", "heal", "taken", "is_self"],
                        [(f"{r['match_uid']}|{r['player_id']}", r["player_id"], r["camp"], r["result"], r["k"] or 0, r["d"] or 0,
                          r["a"] or 0, r["damage"] or 0, r["heal"] or 0, r["taken"] or 0, bool(r["is_self"])) for r in lines])
        teamups = (meta or {}).get("teamups") or []
        tu_ids = {"-".join(map(str, sorted(t["heroes"]))): t for t in teamups}
        load["TeamUp"] = (["id", "matches", "win"], [(i, t["matches"], t["win"]) for i, t in tu_ids.items()])
        for name, (hdr, data) in load.items():
            c.execute(f"COPY {name} FROM '{_csv(d, name, hdr, data)}' (HEADER=true)")
        rel: dict[str, tuple[list[str], list[tuple[Any, ...]]]] = {
            "ON_MAP": (["from", "to"], queries.match_map_pairs(con)),
            "IN_SEASON": (["from", "to"], queries.match_season_pairs(con)),
            "IN_MODE": (["from", "to"], queries.match_mode_pairs(con)),
            "HAS_LINE": (["from", "to"], [(r["match_uid"], f"{r['match_uid']}|{r['player_id']}") for r in lines]),
            "USED": (["from", "to"], [(f"{r['match_uid']}|{r['player_id']}", r["hero_id"]) for r in lines]),
            "BANNED": (["from", "to", "side", "round"],
                       [(r[0], r[1], r[2] if r[2] is not None else -1, r[3] if r[3] is not None else -1)
                        for r in queries.ban_rows(con)]),
            "MEMBER_OF": (["from", "to"], [(h, i) for i in tu_ids for h in map(int, i.split("-")) if h in set(heroes)]),
        }
        for name, (hdr, data) in rel.items():
            c.execute(f"COPY {name} FROM '{_csv(d, name, hdr, data)}' (HEADER=true)")
    counts = {n: _one(c, f"MATCH (x:{n}) RETURN count(*)") for n in load}
    c.close()
    db.close()
    return counts


_DATABASES: dict[Path, tuple[tuple[int, int], Any]] = {}
_LOCK = threading.Lock()


def open_readonly(path: Path | str) -> Any:
    """A connection on a read-only database shared by the whole process.

    LadybugDB asks for one Database object per file inside a process; connections made from it are cheap and may be used
    from several threads (Haystack runs tools in worker threads). The object is replaced when the file is swapped by
    `rebuild`, detected through the file's inode and modification time."""
    p = Path(path).resolve()
    st = p.stat()
    key = (st.st_ino, st.st_mtime_ns)
    with _LOCK:
        cached = _DATABASES.get(p)
        if cached is None or cached[0] != key:
            _DATABASES[p] = (key, lb.Database(str(p), read_only=True))
        return lb.Connection(_DATABASES[p][1])


def is_current(con: sqlite3.Connection) -> bool:
    """False when the graph file no longer matches the database (matches added, or seasons and maps filled in later).
    Compares counts of matches, matches with a season and matches with a map, per mode."""
    path = graph_path(con)
    if not path.exists():
        return False
    sql = queries.mode_signature(con)
    try:
        res = _rows(open_readonly(path), "MATCH (m:Match) RETURN m.mode, count(m), sum(CASE WHEN m.season >= 0 THEN 1 ELSE 0 END), "
                    "sum(CASE WHEN m.map >= 0 THEN 1 ELSE 0 END), sum(CASE WHEN m.comp <> '' THEN 1 ELSE 0 END)", {})
    except RuntimeError:                      # a file built before a schema change lacks the property: it is stale
        return False
    return sql == {(r[0], r[1], r[2], r[3]) for r in res}


def close_all() -> None:
    """Drop the shared read-only database objects (frees the memory they map; the next reader reopens the file)."""
    with _LOCK:
        _DATABASES.clear()


def rebuild(con: sqlite3.Connection, path: Path | str, meta: dict[str, Any] | None = None) -> dict[str, int]:
    """Build a new file next to `path` and swap it in, so readers of the old file are never left with a half-built one.
    (On Windows the swap fails while another process still has the old file open.)"""
    path = Path(path)
    tmp = path.with_name(path.name + ".new")
    for stale in (tmp, tmp.with_name(tmp.name + ".wal")):
        stale.unlink(missing_ok=True)
    counts = build(con, tmp, meta)
    tmp.replace(path)
    tmp.with_name(tmp.name + ".wal").unlink(missing_ok=True)
    return counts


GRAPH_FILE = "graph.lbdb"


def graph_path(sqlite_con: sqlite3.Connection) -> Path:
    """The projection lives beside the SQLite file it was built from."""
    return Path(queries.database_file(sqlite_con)).with_name(GRAPH_FILE)


SPEC_KEYS = ("mode", "season", "map_id", "hero", "role", "banned", "ban_state", "block", "weekday", "session_pos", "regulars",
             "comp", "enemy_comp")
_BAN_EXISTS = "EXISTS { MATCH (m)-[:BANNED]->(:Hero {id: $ban}) }"


def _where(mode: int = 2, season: int | None = None, season_from: int | None = None, season_to: int | None = None,
           map_id: int | None = None, hero: int | None = None,
           role: int | None = None, banned: int | list[int] | None = None, ban_state: str = "present",
           not_banned: list[int] | None = None, block: int | None = None,
           weekday: int | None = None, session_pos: int | None = None,
           regulars: int | None = None, comp: str | None = None,
           enemy_comp: str | None = None) -> tuple[str, dict[str, Any]]:
    """WHERE clause and parameters for a pattern. Fixed clauses only, every value is a bound parameter.
    `session_pos` 5 means the fifth game or later; `ban_state` is 'present' or 'absent' for hero `banned`."""
    if ban_state not in ("present", "absent"):
        raise ValueError("ban_state must be 'present' or 'absent'")
    where: list[str] = ["m.mode = $mode"] if mode else ["m.mode >= 0"]          # mode 0 means every mode
    params: dict[str, Any] = {"mode": mode} if mode else {}
    if map_id is not None:                                  # a map is the same map in ranked and in quick play
        where.append("m.map IN $maps")
        params["maps"] = list(names.same_map_ids(map_id))
    for clause, key, value in (("m.season = $season", "season", season), ("m.season >= $season_from", "season_from", season_from),
                               ("m.season <= $season_to", "season_to", season_to),
                               ("h.id = $hero", "hero", hero), ("h.role = $role", "role", role),
                               ("m.block = $block", "block", block), ("m.weekday = $weekday", "weekday", weekday),
                               ("m.regulars = $regulars", "regulars", regulars)):
        if value is not None:
            where.append(clause)
            params[key] = value
    for clause, key, text in (("m.comp = $comp", "comp", comp), ("m.enemy_comp = $enemy_comp", "enemy_comp", enemy_comp)):
        if text is not None:
            if not re.fullmatch(r"[0-6]-[0-6]-[0-6]", text):
                raise ValueError("a composition looks like 2-2-2 (vanguards-duelists-strategists)")
            where.append(clause)
            params[key] = text
    if session_pos is not None:
        where.append("m.session_pos >= $pos" if session_pos >= 5 else "m.session_pos = $pos")
        params["pos"] = session_pos
    bans = [banned] if isinstance(banned, int) else list(banned or [])            # every one of these was banned ...
    for i, hero_id in enumerate(bans):
        clause = _BAN_EXISTS.replace("$ban", f"$ban{i}")
        where.append(clause if ban_state == "present" else f"NOT {clause}")
        params[f"ban{i}"] = hero_id
    for i, hero_id in enumerate(not_banned or []):                               # ... and none of these
        where.append("NOT " + _BAN_EXISTS.replace("$ban", f"$nban{i}"))
        params[f"nban{i}"] = hero_id
    return " AND ".join(where), params


def _rows(conn: Any, query: str, params: dict[str, Any]) -> list[list[Any]]:
    res = conn.execute(query, params)
    return (res[0] if isinstance(res, list) else res).get_all()


_HEAD = "MATCH (m:Match)-[:HAS_LINE]->(me:Line {is_self: true})-[:USED]->(h:Hero) WHERE "
_FIELDS = ["uid", "result", "ts", "hero", "role", "map", "season", "block", "weekday", "session_pos", "rank_delta"]


def pattern_rows(conn: Any, **spec: Any) -> list[dict[str, Any]]:
    """The tracked player's matches that satisfy every given condition, oldest first, one dict per match (see _FIELDS)."""
    where, params = _where(**spec)
    q = (_HEAD + where + " RETURN m.uid, me.result, m.ts, h.id, h.role, m.map, m.season, m.block, m.weekday, m.session_pos, "
         "m.rank_delta ORDER BY m.ts")
    return [dict(zip(_FIELDS, r, strict=True)) for r in _rows(conn, q, params)]


def comp_rows(conn: Any, side: str = "own", **spec: Any) -> list[dict[str, Any]]:
    """Decided matches grouped by role mix: one dict per composition with its wins and losses. `side` is 'own' (the tracked
    player's side) or 'enemy'. Any other condition of the spec applies (hero played, map, season ...)."""
    if side not in ("own", "enemy"):
        raise ValueError("side must be 'own' or 'enemy'")
    prop = "m.comp" if side == "own" else "m.enemy_comp"
    where, params = _where(**spec)
    q = (_HEAD + where + f" AND {prop} <> '' AND me.result IN ['win', 'loss'] RETURN {prop} AS comp, "
         "count(DISTINCT m) AS n, sum(CASE WHEN me.result = 'win' THEN 1 ELSE 0 END) AS wins, collect(DISTINCT m.uid) AS uids "
         "ORDER BY n DESC, comp")
    return [{"comp": r[0], "n": int(r[1]), "wins": int(r[2]), "uids": r[3]} for r in _rows(conn, q, params)]


def hero_lines(conn: Any, hero: int, mode: int = 2, season: int | None = None) -> list[dict[str, Any]]:
    """Every player line (all 12 players of every match) on one hero, with match length: the material for comparing the tracked
    player with everybody else on that hero."""
    where, params = "h.id = $hero", {"hero": hero}
    if mode:                                   # 0 means every mode
        where += " AND m.mode = $mode"
        params["mode"] = mode
    if season is not None:
        where += " AND m.season = $season"
        params["season"] = season
    q = ("MATCH (m:Match)-[:HAS_LINE]->(l:Line)-[:USED]->(h:Hero) WHERE " + where +
         " RETURN m.uid, l.is_self, l.result, l.k, l.d, l.a, l.damage, l.heal, l.taken, m.duration")
    keys = ["uid", "is_self", "result", "k", "d", "a", "damage", "heal", "taken", "duration"]
    return [dict(zip(keys, r, strict=True)) for r in _rows(conn, q, params)]


def pattern_bans(conn: Any, **spec: Any) -> list[dict[str, Any]]:
    """Same matches, one row per hero banned in the match: lets a caller ask which bans go with wins. A match with
    three bans appears three times. Any `banned` condition in the spec still applies to the match."""
    where, params = _where(**spec)
    q = (_HEAD + where + " WITH m, me, h MATCH (m)-[:BANNED]->(b:Hero) RETURN m.uid, me.result, b.id ORDER BY m.ts")
    return [{"uid": r[0], "result": r[1], "banned_hero": r[2]} for r in _rows(conn, q, params)]


# --- free-form read queries (used by the Cartographer agent) -------------------------------------------------------------

GLOSSARY = """Meaning of the data:
- One Match node per game. Match.mode: 1 quick play, 2 ranked. Match.ts is a unix time; block = hour // 6 (0 night .. 3 evening);
  weekday 0 = Monday; session_pos = game number inside a play session (5 means 5th or later); regulars = known regular teammates.
- Match.self_result is the tracked player's result: 'win', 'loss' or 'draw'. Match.rank_delta is the rank score change.
- Each match has 12 Line nodes (one per player) via HAS_LINE. The tracked player's line has is_self = true.
  Line.camp is 0 or 1 (the side); two lines are teammates when camp is equal, opponents when camp differs.
  Line.result is that player's own result. Every line points to the hero used (USED), at the end of the match.
- Hero.name is the English name ('Loki', 'Black Panther'); Hero.role 1 Vanguard, 2 Duelist, 3 Strategist.
- Match.comp / Match.enemy_comp: role mix of the tracked player's side / the other side as 'V-D-S' counts, '2-2-2' = two Vanguard,
  two Duelist, two Strategist. Match.comp = '' when unknown.
- Bans: (Match)-[:BANNED {side, round}]->(Hero). Map and Season nodes hang off ON_MAP and IN_SEASON.
- Count matches with count(DISTINCT m). Rates are wins / (wins + losses); leave draws out."""

EXAMPLES = """Examples (copy the shape):
Q: how many times did I win and lose as Loki against Black Panther?
MATCH (m:Match)-[:HAS_LINE]->(me:Line {is_self: true})-[:USED]->(:Hero {name: 'Loki'}),
      (m)-[:HAS_LINE]->(o:Line)-[:USED]->(:Hero {name: 'Black Panther'})
WHERE o.camp <> me.camp
RETURN CASE WHEN m.mode = 2 THEN 'ranked' ELSE 'quick play' END AS mode, me.result AS result, count(DISTINCT m) AS matches
ORDER BY mode, result
Q: which teammates' heroes do I win most with when I play Loki (ranked)?
MATCH (m:Match {mode: 2})-[:HAS_LINE]->(me:Line {is_self: true})-[:USED]->(:Hero {name: 'Loki'}),
      (m)-[:HAS_LINE]->(t:Line)-[:USED]->(h:Hero)
WHERE t.camp = me.camp AND t.is_self = false
RETURN h.name AS hero, count(DISTINCT m) AS matches, sum(CASE WHEN me.result = 'win' THEN 1 ELSE 0 END) AS wins
ORDER BY matches DESC LIMIT 10"""


def schema_prompt() -> str:
    """Everything a model needs to write a query: the real table definitions (taken from SCHEMA, so they cannot drift), the
    meaning of the fields, two worked examples, and the hero and map names."""
    heroes = ", ".join(sorted(h for h in names.hero_names() if h))
    return "\n\n".join(["Graph schema (Cypher, LadybugDB):\n" + "\n".join(SCHEMA), GLOSSARY, EXAMPLES,
                         "Hero names: " + heroes, "Map names: " + ", ".join(sorted(names.map_names()))])


_WRITE = re.compile(r"\b(create|set|delete|detach|merge|remove|drop|alter|copy|load|install|attach|detach|call|export|import|"
                    r"begin|commit|rollback|checkpoint|use)\b", re.IGNORECASE)
ROW_CAP = 200
TIMEOUT_MS = 5000


def _plain(v: Any) -> Any:
    """sum() comes back from LadybugDB as a Decimal; make it a number JSON and the evidence check can use."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def check_read_only(cypher: str) -> str:
    """The query text without its trailing semicolon, or ValueError. The read-only database is the real guard; this gives
    the model a clear message and refuses multiple statements."""
    q = cypher.strip().rstrip(";").strip()
    if not q or ";" in q:
        raise ValueError("send exactly one statement")
    if not re.match(r"(match|optional match|with|unwind|return)\b", q, re.IGNORECASE):
        raise ValueError("a query must start with MATCH, WITH, UNWIND or RETURN")
    bad = _WRITE.search(re.sub(r"'[^']*'|\"[^\"]*\"", "''", q))
    if bad:
        raise ValueError(f"only read queries are allowed ({bad.group(0).upper()} is not)")
    return q


def run_read(conn: Any, cypher: str, params: dict[str, Any] | None = None, row_cap: int = ROW_CAP,
             timeout_ms: int = TIMEOUT_MS) -> tuple[list[str], list[list[Any]], bool]:
    """Run one guarded read query on a read-only connection. Returns column names, at most `row_cap` rows, and whether more
    rows existed. A query that runs longer than `timeout_ms` fails."""
    q = check_read_only(cypher)
    conn.set_query_timeout(timeout_ms)
    res = conn.execute(q, params or {})
    res = res[0] if isinstance(res, list) else res
    rows: list[list[Any]] = []
    while res.has_next() and len(rows) < row_cap:
        rows.append([_plain(v) for v in res.get_next()])
    return res.get_column_names(), rows, res.has_next()
