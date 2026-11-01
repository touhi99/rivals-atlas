"""The JSON API and the built React app. The database is opened read-only."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from rivals_atlas.agents import insights, llm
from rivals_atlas.analysis import explore, ladders, patterns, stats
from rivals_atlas.core import config, db, names
from rivals_atlas.core.filters import Filter
from rivals_atlas.graph import store as lbug_store
from rivals_atlas.ingest import fetch, inventory, meta
from rivals_atlas.web import ask as ask_routes
from rivals_atlas.web import insights as insights_routes
from rivals_atlas.web import payloads
from rivals_atlas.web.guard import require_app_header

app = FastAPI(title="rivals-atlas")
app.include_router(ask_routes.router)
app.include_router(insights_routes.router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def get_con() -> Iterator[sqlite3.Connection]:
    path = Path(os.environ.get("RIVALS_ATLAS_DB") or config.data_dir() / "rivals.db")
    if not path.exists():           # first run: an empty database, so every page can render its empty state
        db.connect(path).close()
    con = db.connect_readonly(path)
    try:
        yield con
    finally:
        con.close()


Con = Depends(get_con)


def get_filter(request: Request) -> Filter:
    """The one filter every endpoint and page uses; empty form values count as 'not set'."""
    q = request.query_params

    def num(k: str) -> int | None:
        v = q.get(k)
        return int(v) if v and v.lstrip("-").isdigit() else None

    mode = num("mode")
    return Filter(mode=2 if mode is None else mode, season_from=num("season_from"), season_to=num("season_to"),
                  hero=num("hero"), map_id=num("map_id"), with_players=tuple(x for x in q.getlist("with") if x))


Flt = Depends(get_filter)


@app.get("/api/shell")
def shell_json(f: Filter = Flt, con=Con):
    return payloads.shell(con, f)


@app.get("/api/heroes")
def heroes_json(f: Filter = Flt, con=Con):
    return payloads.heroes(con, f, meta_context(con, f))


@app.get("/api/overview")
def overview_json(f: Filter = Flt, con=Con):
    return payloads.overview(con, f, overview_data(con, f))


@app.get("/api/hero/{hero_id}")
def hero_json(hero_id: int, f: Filter = Flt, con=Con):
    return payloads.hero_detail(con, f, hero_id, meta_context(con, f))


@app.get("/api/patterns")
def patterns_json(f: Filter = Flt, con=Con):
    return payloads.patterns(con, f)


@app.get("/api/squad")
def squad_json(f: Filter = Flt, con=Con):
    return payloads.squad(con, f)


@app.get("/api/explore")
def explore_json(request: Request, con=Con):
    return payloads.explore(con, request.query_params, _default_min, not lbug_store.is_current(con))


@app.get("/api/maps")
def maps_json(f: Filter = Flt, con=Con):
    return payloads.maps(con, f)


def tier_ticks(pts: list[dict]) -> list[dict]:
    """One line per tier level, placed where the tracked player's own scores for that level start (10th percentile).
    The bands overlap a little near the bottom, so a fixed formula would misplace them."""
    by: dict[int, list[float]] = {}
    for p in pts:
        if p["new_level"]:
            by.setdefault(p["new_level"], []).append(p["new_score"])
    out = []
    for lv, v in sorted(by.items()):
        v.sort()
        out.append({"score": v[int(len(v) * 0.1)], "label": names.tier_name(lv), "n": len(v)})
    return out


def meta_context(con, f: Filter) -> dict:
    """The hero meta and the rank group of the tracked player's current tier (or 'all')."""
    m = meta.load(config.data_dir())
    if not m:
        return {"meta": None, "meta_group": "all", "meta_label": "all ranks"}
    level = None
    if f.mode in (0, 2):
        pts = [p for p in stats.rank_journey(con, f.replace(hero=None, map_id=None, with_players=(), season_from=None, season_to=None)) if p["new_level"]]
        main = [p for p, fl in zip(pts, ladders.assign([{"season": p["season"], "t": p["played_at"], "score": p["new_score"], "delta": p["add_score"], "level": p["new_level"]} for p in pts]), strict=True) if fl == "main"]
        level = main[-1]["new_level"] if main else None
    g = meta.group_for_level(level, m) if level else "all"
    return {"meta": m, "meta_group": g, "meta_label": m["ranks"].get(g, "all ranks") if g != "all" else "all ranks"}


def totals(hs: list[dict]) -> dict:
    wins = sum(h["wins"] for h in hs)
    losses = sum(h["n"] - h["wins"] for h in hs)
    return {**stats.rate(wins, losses), "losses": losses, "draws": sum(h["draws"] for h in hs),
            "games": sum(h["games"] for h in hs)}


def overview_data(con, f: Filter) -> dict:
    """Everything the overview shows."""
    hs = stats.heroes(con, f)
    pts = [p for p in (stats.rank_journey(con, f) if f.mode in (0, 2) else []) if p["new_level"]]
    seasons, last = [], None
    for p in pts:
        p["tier"] = names.tier_name(p["new_level"])
        p["t"], p["level"], p["score"], p["delta"] = p["played_at"], p["new_level"], p["new_score"], p["add_score"]
        if p["season"] != last:
            seasons.append({"t": p["t"], "season": p["season"], "label": names.season_label(p["season"])})
            last = p["season"]
    for p, flag in zip(pts, ladders.assign(pts), strict=True):
        p["ladder"] = flag
    main_pts = [p for p in pts if p["ladder"] == "main"] or pts
    tiers = [{"level": lv, "floor": t["score"], "label": t["label"]} for lv, t in
             zip(sorted({p["new_level"] for p in main_pts}), tier_ticks(main_pts), strict=True)]
    return {"heroes": hs, "tot": totals(hs), "pat": patterns.compute(con, f),
            "rank_peak": names.tier_name(max((p["new_level"] or 0) for p in main_pts)) if pts else "", "rank_main": main_pts[-1] if pts else None,
            "rank_pts": pts, "rank_tiers": tiers, "rank_seasons": seasons}


RELS = ("teammates", "enemies", "lobby", "maps")


@app.get("/api/map")
def map_json(request: Request, rel: str = "teammates", min_n: int = 15, con=Con):
    """The hero graph over the matches an Explore query selects (same query parameters as /api/explore)."""
    if rel not in RELS:
        raise HTTPException(400, "rel must be teammates, enemies, lobby or maps")
    spec, _ = explore.parse_spec(request.query_params)
    try:
        v = explore.graph(con, spec, rel, max(1, min(min_n, 200)))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    for n in v["nodes"]:
        is_map = n["id"] < 0
        n["name"] = names.map_name(-n["id"]) if is_map else names.hero_name(n["id"])
        n["icon"] = names.map_icon(-n["id"]) if is_map else names.hero_icon(n["id"])
        n["kind"] = "map" if is_map else "hero"
    return v


def _default_min(games: int, rel: str) -> int:
    """Games a pair needs before it is drawn: strict for a big selection, loose for a small one so the graph is not empty."""
    base = 6 if rel == "maps" else 15
    return base if games >= 400 else max(1, min(base, games // 40))


@app.get("/api/ask")
def ask_json():
    """What the Ask tab shows before the first question."""
    return {"model": llm.setting(config.data_dir()),
            "examples": ["How many times did the player win and lose as Loki against Black Panther?",
                         "Which heroes do wins come with most when Loki is played in ranked?",
                         "Win rate on each map in ranked, best first."]}


@app.get("/graph")
@app.get("/connections")
@app.get("/map")
def graph_redirect(request: Request):
    return RedirectResponse("/explore?view=graph&go=1" + ("&" + request.url.query if request.url.query else ""))


# ---- fetching from the app: one background job at a time ---------------------------------------------------
JOB: dict = {"state": "idle"}
_lock = threading.Lock()


def _run_job(profile: str, mode: int, limit: int | None, pace: str) -> None:
    def progress(p: dict) -> None:
        JOB.update(stage=p["stage"], done=p["done"], total=p["total"], message=p["message"])
    try:
        res = fetch.run(profile, mode, config.data_dir(), limit, progress=progress, pace=pace)
        JOB.update(state="done", result=res)
        if res.get("fetched") and insights.load() is not None:   # only once insights were run by hand: the model is optional
            insights_routes.start_job()
    except fetch.FetchError as e:
        JOB.update(state="error", error=str(e))
    except Exception as e:  # noqa: BLE001 - last resort so the page never shows a spinner forever
        JOB.update(state="error", error=f"Unexpected error: {type(e).__name__}")


@app.post("/api/fetch/start")
async def fetch_start(request: Request):
    require_app_header(request)
    body = await request.json()
    profile = fetch.parse_profile(str(body.get("profile", "")))
    if not profile:
        raise HTTPException(400, "Paste the address of the player's page (it ends with a number), or just the number.")
    if not body.get("consent"):
        raise HTTPException(400, "Please confirm the notice first.")
    mode = int(body.get("mode") or 2)
    limit = int(body["limit"]) if str(body.get("limit") or "").isdigit() else None
    pace = body.get("pace") if body.get("pace") in fetch.PACES else "gentle"
    with _lock:
        if JOB.get("state") == "running":
            raise HTTPException(409, "A fetch is already running.")
        st = config.load_settings()
        config.save_settings({"profile_id": profile, "consent_at": st.get("consent_at") or time.time()})
        JOB.clear()
        JOB.update(state="running", stage="starting", done=0, total=1, message="Starting", started_at=time.time())
        threading.Thread(target=_run_job, args=(profile, mode, limit, pace), daemon=True).start()
    return JOB


@app.get("/api/fetch/status")
def fetch_status():
    return JOB


@app.get("/api/data")
def data_json(con=Con):
    st = config.load_settings()
    return {"inv": inventory.inventory(con, config.data_dir()), "notice": fetch.NOTICE, "profile": st.get("profile_id", ""),
            "consented": bool(st.get("consent_at")), "matches": stats.overview(con)["n"]}


UI_DIR = Path(__file__).parent / "ui"
app.mount("/assets", StaticFiles(directory=str(UI_DIR / "assets"), check_dir=False), name="ui-assets")


def spa(request: Request):
    """The React app: one HTML file, the browser's router picks the view."""
    index = UI_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "The UI is not built yet: run ./scripts/setup.sh (or `npm run build` in frontend/)")
    from fastapi.responses import FileResponse
    return FileResponse(index)


for _path in ("/", "/heroes", "/heroes/{hero_id}", "/maps", "/patterns", "/squad", "/data", "/explore", "/agents", "/ask"):
    app.get(_path, include_in_schema=False)(spa)


@app.get("/ui/{path:path}", include_in_schema=False)
def moved_json(path: str, request: Request):
    return RedirectResponse("/" + path + ("?" + request.url.query if request.url.query else ""))
