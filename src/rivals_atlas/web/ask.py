"""The Ask page's backend: one question runs the agents in a worker thread; the page polls for steps and the answer.

Everything shown as a number comes from the Ledger (tool results and checked claims). The model's own words are sent
separately and labelled unchecked.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from rivals_atlas import agents
from rivals_atlas.agents import llm
from rivals_atlas.agents.tools import describe_args
from rivals_atlas.core import config
from rivals_atlas.ingest import meta
from rivals_atlas.web.guard import require_app_header

router = APIRouter()
MAX_JOBS = 20            # finished jobs kept in memory
MAX_QUESTION = 500
AGENT = "cartographer"   # direct: the Coordinator step costs two more model calls (about 7 s)
JOBS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _db_path() -> Path:
    return Path(os.environ.get("RIVALS_ATLAS_DB") or config.data_dir() / "rivals.db")


def _steps(ledger: agents.Ledger) -> dict[str, Any]:
    findings, verdicts = ledger.snapshot()
    return {
        "queries": [f.args["cypher"] for f in findings if f.tool == "cypher_query"],
        "calls": [{"tool": f.tool, "cypher": f.args.get("cypher") if f.tool == "cypher_query" else None, "label": describe_args(f.args),
                   "n": f.n, "text": f.describe(), "rows": f.items[:60] if f.tool == "cypher_query" else []} for f in findings],
        "results": list(dict.fromkeys(f.describe() for f in findings)),
        "checked": [{"text": v.text, "matches": v.finding.match_ids[:5] if v.finding else []} for v in verdicts if v.shown],
        "removed": sum(not v.shown for v in verdicts),
    }


def _run(job_id: str, question: str) -> None:
    job = JOBS[job_id]
    ledger: agents.Ledger = job["ledger"]
    try:
        base = config.data_dir()
        ans = agents.ask_specialist(AGENT, question, llm.make_generator(), _db_path(), meta.load(base), ledger)
        job.update(state="done", framing=ans.framing, unverified=ans.unverified, model=llm.setting(base))
    except Exception as e:  # noqa: BLE001                                           # a model or network problem must reach the page
        job.update(state="error", error=f"{type(e).__name__}: {str(e)[:300]}")
    job["finished_at"] = time.time()


@router.post("/api/ask/start")
async def ask_start(request: Request):
    require_app_header(request)
    question = str((await request.json()).get("question", "")).strip()
    if not question:
        raise HTTPException(400, "Type a question first.")
    if len(question) > MAX_QUESTION:
        raise HTTPException(400, f"Keep the question under {MAX_QUESTION} characters.")
    with _lock:
        if any(j["state"] == "running" for j in JOBS.values()):
            raise HTTPException(409, "A question is already running.")
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"state": "running", "question": question, "ledger": agents.Ledger(), "started_at": time.time()}
        for old in sorted(JOBS, key=lambda k: JOBS[k]["started_at"])[:-MAX_JOBS]:
            del JOBS[old]
        threading.Thread(target=_run, args=(job_id, question), daemon=True).start()
    return {"id": job_id}


@router.get("/api/ask/{job_id}")
def ask_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown question")
    out = {k: v for k, v in job.items() if k != "ledger"}
    return {**out, **_steps(job["ledger"]), "seconds": round((job.get("finished_at") or time.time()) - job["started_at"], 1)}
