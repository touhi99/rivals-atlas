"""Insights routes: the saved result, a Run button, and the job that runs the agents (also started after a fetch)."""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from rivals_atlas.agents import insights
from rivals_atlas.core import config
from rivals_atlas.ingest import meta
from rivals_atlas.web.guard import require_app_header

router = APIRouter()
JOB: dict[str, Any] = {"state": "idle"}
_lock = threading.Lock()


def _run(mode: int) -> None:
    base = config.data_dir()
    try:
        insights.generate(config.db_path(), base, meta.load(base), mode=mode)
        JOB.update(state="done")
    except Exception as e:  # noqa: BLE001                      # a model or network problem must reach the page, never the fetch
        insights.record_error(f"{type(e).__name__}: {str(e)[:300]}", base, mode)
        JOB.update(state="error", error=f"{type(e).__name__}: {str(e)[:300]}")
    JOB["finished_at"] = time.time()


def start_job(mode: int = 0) -> bool:
    """Start the agents in the background. False if a run is already going."""
    with _lock:
        if JOB.get("state") == "running":
            return False
        JOB.clear()
        JOB.update(state="running", started_at=time.time(), mode=mode)
        threading.Thread(target=_run, args=(mode,), daemon=True).start()
    return True


@router.get("/api/insights")
def insights_status(mode: int = 0):
    if mode not in insights.SCOPES:
        raise HTTPException(422, "mode must be 0 (all), 1 (quick play) or 2 (ranked)")
    data = insights.load(mode=mode)
    stale = bool(data and data.get("matches") != insights.match_count(config.db_path()))
    return {"data": data, "stale": stale, "job": dict(JOB)}


@router.post("/api/insights/run")
async def insights_run(request: Request, mode: int = 0):
    require_app_header(request)
    if mode not in insights.SCOPES:
        raise HTTPException(422, "mode must be 0 (all), 1 (quick play) or 2 (ranked)")
    if not start_job(mode):
        raise HTTPException(409, "The agents are already running.")
    return {"job": dict(JOB)}
