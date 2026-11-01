"""The JSON the React app shows, one function per page. Plain functions over the analysis code that only reshape
the result for the browser. The routes are in `api.py`."""
from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

from rivals_atlas.agents import tools
from rivals_atlas.analysis import explore as ex
from rivals_atlas.analysis import insights, stats
from rivals_atlas.analysis import patterns as pat
from rivals_atlas.core import names, queries
from rivals_atlas.core.filters import Filter
from rivals_atlas.graph import network as graph
from rivals_atlas.ingest import meta


def hero(hid: int) -> dict[str, Any]:
    return {"id": hid, "name": names.hero_name(hid), "icon": names.hero_icon(hid), "role": names.role_name(hid)}


def map_(mid: int) -> dict[str, Any]:
    full = names.map_name(mid)
    place, _, mode = full.partition(" · ")
    return {"id": mid, "name": full, "place": place, "mode": mode or None, "icon": names.map_icon(mid)}


def career(con: sqlite3.Connection) -> dict[int, int]:
    """Games per hero over the whole stored history (every mode and season, no filter): what mastery is based on."""
    return queries.career_games(con)


def stat(r: dict[str, Any]) -> dict[str, Any]:
    """The numbers every row carries. Rates and interval ends are fractions; kda is None without data."""
    return {"games": r["games"], "draws": r.get("draws", 0), "n": r["n"], "wins": r["wins"], "rate": r["rate"],
            "lo": r["lo"], "hi": r["hi"], "enough": r["enough"], "kda": r.get("kda")}


def shell(con: sqlite3.Connection, f: Filter) -> dict[str, Any]:
    """What the sidebar and the filter bar need: modes, and every hero, map and season that can be chosen."""
    base = f.replace(hero=None, map_id=None, with_players=(), season_from=None, season_to=None)
    played = {h["hero_id"] for h in stats.heroes(con, base)}
    known = sorted({int(k) for k in names._heroes()} | played, key=names.hero_name)
    seasons = queries.season_starts(con, f.mode)
    counts = queries.matches_per_mode(con)
    return {
        "has_data": sum(counts.values()) > 0,
        "modes": [{"id": 2, "label": "ranked", "matches": counts.get(2, 0)}, {"id": 1, "label": "quick play", "matches": counts.get(1, 0)},
                  {"id": 0, "label": "all", "matches": sum(counts.values())}],
        "heroes": [hero(h) for h in known],
        "maps": [map_(m["map_id"]) for m in stats.maps(con, base)],
        "seasons": [{"id": r["season"], "label": names.season_label(r["season"]),
                     "when": datetime.fromtimestamp(r["t0"], UTC).strftime("%b %Y")} for r in seasons],
        "players": [{"id": h, "name": names.player_label(con, h)} for h in f.with_players],
    }


def heroes(con: sqlite3.Connection, f: Filter, meta_ctx: dict[str, Any]) -> dict[str, Any]:
    """Every hero with the tracked player's numbers and, when the site's meta is fetched, everyone's win/pick/ban."""
    played = {h["hero_id"]: h for h in stats.heroes(con, f)}
    m, group = meta_ctx["meta"], meta_ctx["meta_group"]
    life = career(con)
    rows = []
    for hid in sorted({int(k) for k in names._heroes()} | set(played)):
        if hid == 0:                       # a game left before any hero was played is not a hero
            continue
        p = played.get(hid)
        mm = meta.for_hero(m, hid, group) if m else None
        rows.append({**hero(hid), "career": life.get(hid, 0), "mine": stat(p) if p else None,
                     "meta": ({"win": mm.get("win"), "pick": mm.get("pick"), "ban": mm.get("ban")} if mm else None)})
    rows.sort(key=lambda r: (-(r["mine"]["games"] if r["mine"] else 0), r["name"]))
    stand = insights.compute(con, f)
    return {
        "heroes": rows, "meta_label": meta_ctx["meta_label"] if m else None,
        "stands": {"checked": stand["checked"], "flagged": stand["flagged"], "findings": [
            {"title": x["title"], "direction": x["direction"], "rate": x["rate"], "base": x["base"], "n": x["n"],
             "hero": hero(x["hero_id"]) if x.get("hero_id") else None} for x in stand["findings"]]},
    }


def maps(con: sqlite3.Connection, f: Filter) -> dict[str, Any]:
    """Per-map results plus the hero x map grid (rows heroes, columns maps; cells keyed 'hero:map')."""
    grid = stats.hero_map_grid(con, f, heroes=14, maps=12)
    return {
        "maps": [{**map_(x["map_id"]), **stat(x), "first_season": x["first_season"], "last_season": x["last_season"],
                  "minutes": x["minutes"]} for x in stats.maps(con, f)],
        "grid": {"heroes": [{**hero(h), "games": grid["hero_games"][h]} for h in grid["heroes"]],
                 "maps": [map_(x) for x in grid["maps"]],
                 "cells": {f"{h}:{x}": {**stat(c), "games": c["games"]} for (h, x), c in grid["cells"].items()}},
        "min_games": stats.MIN_GAMES,
    }


def overview(con: sqlite3.Connection, f: Filter, d: dict[str, Any]) -> dict[str, Any]:
    """`d` is the page's own overview data (api.overview_data); this only reshapes it."""
    ov = stats.overview(con)
    hs = d["heroes"]
    rm = d["rank_main"]
    by_season = [{"season": r["season"], "label": names.season_label(r["season"]), "wins": r["wins"], "losses": r["losses"],
                  **{k: v for k, v in stats.rate(r["wins"], r["losses"]).items() if k in ("rate", "lo", "hi", "enough")}}
                 for r in queries.wins_losses_by_season(con, f.replace(season_from=None, season_to=None))]
    form = queries.latest_results(con, f, 30)
    roles: dict[str, int] = {}
    for h in hs:
        if h["hero_id"] > 0:
            roles[names.role_name(h["hero_id"])] = roles.get(names.role_name(h["hero_id"]), 0) + h["games"]
    return {
        "by_season": by_season, "form": form, "roles": [{"role": k, "games": v} for k, v in sorted(roles.items(), key=lambda x: -x[1])],
        "has_data": ov["n"] > 0, "total": stat({**d["tot"], "games": d["tot"]["games"], "kda": None}),
        "losses": d["tot"]["losses"], "top_heroes": [{**hero(h["hero_id"]), "career": career(con).get(h["hero_id"], 0), "mine": stat(h)} for h in hs if h["hero_id"] > 0][:5],
        "rank": ({"tier": rm["tier"], "score": rm["new_score"], "peak": d["rank_peak"], "level": rm["new_level"]} if rm else None),
        "journey": {"points": [{"t": p["t"], "score": p["score"], "delta": p["delta"], "level": p["level"], "tier": p["tier"],
                                "season": p["season"], "ladder": p["ladder"], "result": p["result"]} for p in d["rank_pts"]],
                    "tiers": d["rank_tiers"], "seasons": d["rank_seasons"]},
        "facts": [{"kind": x.get("kind", ""), "label": x["label"], "value": x["value"], "sub": x["sub"], "data": x.get("data", {})}
                  for x in d["pat"]["facts"]],
    }


def hero_detail(con: sqlite3.Connection, f: Filter, hero_id: int, meta_ctx: dict[str, Any]) -> dict[str, Any]:
    fh = f.replace(hero=hero_id)
    mine = next(iter(stats.heroes(con, fh)), None)
    seasons = [{"label": names.season_label(r["season"]), **stats.rate(r["wins"], r["losses"])}
               for r in queries.wins_losses_by_season(con, fh)]
    recent = [{**dict(r), "add_score": r["add_score"] if r["mode_id"] == 2 else None} for r in queries.latest_matches(con, fh, 12)]

    def split(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        own = [e for e in edges if e["source"] == hero_id]
        pick = lambda es: [{**hero(e["target"]), "n": e["n"], "rate": e["rate"], "lo": e["lo"], "hi": e["hi"]} for e in es]
        return {"best": pick(sorted((e for e in own if e["rate"] > 0.5), key=lambda e: -e["lo"])[:5]),
                "worst": pick(sorted((e for e in own if e["rate"] <= 0.5), key=lambda e: e["hi"])[:3])}

    try:
        bench = tools.hero_benchmark(con, hero_id, mode=f.mode, season=None)
        bench_out: dict[str, Any] | None = {
            "items": bench.items, "tracked_matches": bench.value["tracked_matches"], "other_lines": bench.value["other_lines"],
            "rate": bench.rate, "n": bench.n, "others_rate": bench.value["others_rate"], "enough": bench.enough}
    except ValueError:                      # the graph file is not built yet
        bench_out = None
    m, group = meta_ctx["meta"], meta_ctx["meta_group"]
    mg, ma = (meta.for_hero(m, hero_id, group), meta.for_hero(m, hero_id, "all")) if m else (None, None)
    return {
        "hero": hero(hero_id), "career": career(con).get(hero_id, 0), "mine": stat(mine) if mine else None, "meta_label": meta_ctx["meta_label"] if m else None,
        "meta": {"group": mg, "all": ma} if mg else None, "seasons": seasons, "bench": bench_out,
        "maps": [{**map_(x["map_id"]), **stat(x)} for x in stats.maps(con, fh)],
        "with": split(graph.lens(con, fh, "teammates", 5)["edges"]), "against": split(graph.lens(con, fh, "enemies", 5)["edges"]),
        "teamups": [{"heroes": [hero(h) for h in t["heroes"]], "win": t["win"], "matches": t["matches"]}
                    for t in (m or {}).get("teamups", []) if hero_id in t["heroes"]][:6],
        "recent": [{**r, "map": map_(r["map_id"]) if r["map_id"] else None} for r in recent],
    }


def patterns(con: sqlite3.Connection, f: Filter) -> dict[str, Any]:
    d = pat.compute(con, f)
    mode_n = queries.match_count(con, f.mode)
    since = int(time.time()) - 182 * 86400
    days = [{"day": r["day"], "games": r["games"], "wins": r["wins"], "losses": r["losses"]} for r in queries.daily_results(con, f, since)]
    return {**d, "days": days, "mode_n": mode_n, "mode_label": {**stats.MODES, 0: "all"}.get(f.mode, "")}


MAX_PARTY = 5          # the table has 2^n rows, so more than this stops being readable


def squad(con: sqlite3.Connection, f: Filter) -> dict[str, Any]:
    """Regular teammates, and every combination of the ticked ones (up to MAX_PARTY) that was played. Nothing is ticked by
    default, so the combinations stay empty until the page's reader picks teammates."""
    nowith = f.replace(with_players=())
    regulars = stats.squad(con, nowith)
    ticked = list(f.with_players)
    cols = ticked[:MAX_PARTY]
    label = {s["player_id"]: s["player"] for s in regulars}
    combos = stats.party_combos(con, nowith, cols) if cols else []
    return {
        "ticked": ticked, "max_party": MAX_PARTY, "cols": [{"id": h, "name": label.get(h, h[:6])} for h in cols],
        "regulars": [{"id": s["player_id"], "name": s["player"], "last_played": s["last_played"], **stat({**s, "games": s["games"]})}
                     for s in regulars[:24]],
        "combos": [{"members": c["members"], "kind": c["kind"], "names": [label.get(h, h[:6]) for h in c["members"]],
                    **stat({**c, "games": c["n"]})} for c in combos],
    }


def explore(con: sqlite3.Connection, query: Any, default_min: Any, stale: bool) -> dict[str, Any]:
    """The Explore page: the conditions as the page holds them, the option lists, and the result for those conditions."""
    spec, group_by = ex.parse_spec(query)
    asked = any(k in query for k in ex.SPEC_INTS + ("group_by", "go"))
    result, error = None, ""
    try:
        result = ex.run(con, spec, group_by)
    except ValueError as e:
        error = str(e)
    ch = ex.choices(con, spec["mode"])
    out: dict[str, Any] = {
        "spec": spec, "group_by": group_by, "asked": asked, "error": error, "graph_stale": stale,
        "chips": [{"label": c["label"], "drop": c["drop"]} for c in ex.chips(spec, group_by)],
        "choices": {k: [{"value": v, "label": t} for v, t in ch[k]] for k in
                    ("heroes", "maps", "seasons", "roles", "blocks", "weekdays", "positions", "regulars", "groups")},
        "result": None,
    }
    if result:
        p = result["panels"]
        out["result"] = {
            "total": result["total"], "games": result["games"], "draws": result["draws"], "group_title": result["group_title"],
            "groups": result["groups"],
            "panels": {**p, "heroes": [{**h, "icon": names.hero_icon(h["id"]), "role": names.role_name(h["id"])} for h in p["heroes"]],
                       "maps": [{**m, "icon": names.map_icon(m["id"])} for m in p["maps"]],
                       "trend": ({"points": [{"week": q["week"], "rate": q["rate"], "n": q["n"]} for q in p["trend"]["points"]]}
                                 if p["trend"] else None)},
        }
        out["default_min"] = default_min(result["games"], "teammates")
    return out
