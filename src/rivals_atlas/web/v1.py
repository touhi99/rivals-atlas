"""A small, versioned, read-only API for other local tools that want the stored matches without
fetching from rivalsmeta.com themselves. Only the tracked player's own lines are served, never teammates or opponents.
Keep the shapes stable: add fields, do not rename or remove them."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from rivals_atlas.core import config, names, queries
from rivals_atlas.core.filters import Filter
from rivals_atlas.ingest import meta

router = APIRouter(prefix="/api/v1")
MAX_LIMIT = 1000


def _con():
    from rivals_atlas.web.api import get_con  # late: api.py includes this router
    yield from get_con()


Con = Depends(_con)


def _iso(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, UTC).isoformat().replace("+00:00", "Z") if t is not None else None


@router.get("/status")
def status(con: sqlite3.Connection = Con) -> dict[str, Any]:
    row = con.execute(
        "SELECT COUNT(*) n, MIN(m.played_at) first, MAX(m.played_at) last FROM match_players p "
        "JOIN matches m USING(match_uid) WHERE p.is_self=1").fetchone()
    me = con.execute("SELECT player_id FROM match_players WHERE is_self=1 LIMIT 1").fetchone()
    return {"version": 1, "player_id": me[0] if me else None, "matches": row["n"],
            "first_played_at": _iso(row["first"]), "last_played_at": _iso(row["last"]),
            "per_mode": {str(k): v for k, v in queries.matches_per_mode(con).items()}}


@router.get("/matches")
def matches(since: int | None = Query(None, description="unix seconds; only matches played after this"),
            mode: int | None = None, season: int | None = None,
            limit: int = Query(200, ge=1, le=MAX_LIMIT), offset: int = Query(0, ge=0),
            con: sqlite3.Connection = Con) -> dict[str, Any]:
    """The player's own match lines, oldest first. Page with `offset`, or poll with `since` set to the last `played_at`."""
    where, args = ["p.is_self=1"], []
    for col, val in (("m.mode_id", mode), ("m.season", season)):
        if val is not None:
            where.append(f"{col}=?")
            args.append(val)
    if since is not None:
        where.append("m.played_at>?")
        args.append(since)
    cond = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(*) FROM match_players p JOIN matches m USING(match_uid) WHERE {cond}", args).fetchone()[0]
    rows = con.execute(
        "SELECT m.match_uid, m.played_at, m.season, m.mode_id, m.map_id, m.duration, m.mvp_id, m.svp_id, "
        "p.player_id, p.hero_id, p.result, p.k, p.d, p.a, p.add_score, p.new_score, p.new_level, p.escaped "
        f"FROM match_players p JOIN matches m USING(match_uid) WHERE {cond} ORDER BY m.played_at, m.match_uid LIMIT ? OFFSET ?",
        [*args, limit, offset]).fetchall()
    ranked = lambda r: r["mode_id"] == 2
    return {"total": total, "offset": offset, "matches": [{
        "match_uid": r["match_uid"], "played_at": _iso(r["played_at"]), "played_at_unix": r["played_at"],
        "season": r["season"], "mode_id": r["mode_id"], "map_id": r["map_id"],
        "map": names.map_name(r["map_id"]) if r["map_id"] is not None else None,
        "duration": r["duration"], "hero_id": r["hero_id"], "hero": names.hero_name(r["hero_id"]),
        "result": r["result"], "k": r["k"], "d": r["d"], "a": r["a"], "escaped": bool(r["escaped"]),
        "mvp": r["mvp_id"] == r["player_id"], "svp": r["svp_id"] == r["player_id"],
        "rank_delta": r["add_score"] if ranked(r) else None, "rank_score": r["new_score"] if ranked(r) else None,
        "rank": names.tier_name(r["new_level"]) if ranked(r) and r["new_level"] is not None else None,
    } for r in rows]}


@router.get("/ranks")
def ranks(mode: int = 2, con: sqlite3.Connection = Con) -> dict[str, Any]:
    """Where every season ended, and its highest point."""
    pts = queries.rank_points(con, Filter(mode=mode))
    last: dict[int, Any] = {}
    high: dict[int, Any] = {}
    for r in pts:
        last[r["season"]] = r
        if r["season"] not in high or r["new_score"] > high[r["season"]]["new_score"]:
            high[r["season"]] = r
    return {"mode_id": mode, "seasons": [
        {"season": s, "label": names.season_label(s), "rank_score": r["new_score"], "rank": names.tier_name(r["new_level"]),
         "ended_at": _iso(r["played_at"]), "high_score": high[s]["new_score"], "high_rank": names.tier_name(high[s]["new_level"])}
        for s, r in sorted(last.items(), key=lambda kv: (kv[0] is None, kv[0]))]}


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    """Every known hero with its name, role and portrait link (the link is empty when images are switched off)."""
    return {"heroes": [_hero(int(h)) for h in sorted(names._heroes(), key=int)]}


def _hero(hid: int) -> dict[str, Any]:
    return {"id": hid, "hero": names.hero_name(hid), "role": names.role_name(hid), "icon_url": names.hero_icon(hid)}


@router.get("/meta")
def hero_meta() -> dict[str, Any]:
    """The site's hero meta as last stored: pick, win and ban rate per hero and rank group, and team-up win rates.
    Empty (`available: false`) until a fetch has read it."""
    m = meta.load(config.data_dir())
    if not m:
        return {"available": False}
    stamp = m.get("updated_at")
    return {"available": True, "season": m.get("season"), "season_label": names.season_label(m["season"]) if m.get("season") else None,
            "ranks": m["ranks"], "updated_at": _iso(stamp) if isinstance(stamp, int | float) else None,
            "fetched_at": _iso(m.get("fetched_at")),
            "heroes": [{**_hero(h["id"]), "by_rank": h["by_rank"]} for h in m["heroes"]],
            "teamups": [{**t, "heroes": [_hero(x) for x in t["heroes"]]} for t in m["teamups"]]}


@router.get("/heroes")
def heroes(mode: int = 2, season: int | None = None, con: sqlite3.Connection = Con) -> dict[str, Any]:
    """The player's win rate per hero (decided games, 95% range) for one mode, optionally one season."""
    from rivals_atlas.analysis import stats
    f = Filter(mode=mode, season_from=season, season_to=season)
    return {"mode_id": mode, "season": season, "heroes": [{
        "hero_id": h["hero_id"], "hero": names.hero_name(h["hero_id"]), "role": names.role_name(h["hero_id"]),
        "games": h["games"], "wins": h["wins"], "rate": h["rate"], "lo": h["lo"], "hi": h["hi"],
        "enough": h["enough"], "kda": h.get("kda")} for h in stats.heroes(con, f)]}
