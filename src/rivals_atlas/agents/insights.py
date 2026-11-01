"""Insights: the Coordinator asks the Coach and the Tilt guard what stands out in the matches. They write observations; the app
checks each one (see observations.py) and saves the ones that hold, with the numbers they rest on, for the Insights tab of the
Agents page."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from rivals_atlas import agents
from rivals_atlas.agents import llm
from rivals_atlas.agents.tools import Finding, describe_args
from rivals_atlas.analysis import stats
from rivals_atlas.core import config, db, names, queries

FILE = "insights.json"
QUESTION = ("What stands out in the player's matches? Ask the coach about heroes against each other, against 50% and against the "
            "site's figures, in ranked and in quick play, and ask the tilt guard whether results change with the game number in a "
            "session. Ask both.")
def path(base: Path | None = None) -> Path:
    return (base or config.data_dir()) / FILE


def load(base: Path | None = None) -> dict[str, Any] | None:
    p = path(base)
    data = json.loads(p.read_text()) if p.exists() else None
    if data and "observations" not in data:
        return None                                       # an older format; run the agents again
    return data


def _save(data: dict[str, Any], base: Path) -> None:
    tmp = path(base).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path(base))


def record_error(message: str, base: Path | None = None) -> None:
    """Keep the last good insights and note why the newest run failed."""
    base = base or config.data_dir()
    _save({**(load(base) or {}), "last_error": message, "last_error_at": time.time()}, base)


def match_count(db_path: Path | str) -> int:
    return int(db.connect_readonly(db_path).execute("SELECT COUNT(*) FROM matches").fetchone()[0])


def _row(f: Finding) -> dict[str, Any]:
    """One tool result as the numbers the page draws."""
    a = f.args
    season = names.season_label(a["season_from"]) if a.get("season_from") is not None and a.get("season_from") == a.get("season_to") else None
    row: dict[str, Any] = {"tool": f.tool, "label": describe_args(f.args), "n": f.n, "wins": f.wins, "rate": f.rate, "lo": f.lo,
                           "hi": f.hi, "enough": f.enough, "mode": stats.MODES.get(a.get("mode", 2), "ranked"), "season": season,
                           "earlier": a.get("season_to") is not None and a.get("season_from") is None}
    hero = f.args.get("hero")
    if hero is not None:
        row["hero"] = {"id": hero, "name": names.hero_name(hero), "icon": names.hero_icon(hero)}
    if f.args.get("map_id") is not None:
        row["map"] = {"name": names.map_name(f.args["map_id"]), "icon": names.map_icon(f.args["map_id"])}
    if f.tool == "session_stats":
        row["position"] = f.args["position"]
    if f.tool == "rank_journey":
        row["rank"] = f.value
    if f.tool == "compare_to_meta":
        row["site_rate"] = f.value.get("site_rate")
    return row


def generate(db_path: Path | str, base: Path, meta: dict[str, Any] | None = None, generators: dict[str, Any] | None = None) -> dict[str, Any]:
    con = db.connect_readonly(db_path)
    seasons = queries.seasons_in_mode(con, 2)
    if not seasons:
        raise ValueError("There are no ranked matches yet.")
    ledger = agents.Ledger()
    agents.ask(QUESTION, generators or llm.generators(), db_path, meta, ledger, insights=True)
    found = [{"text": o.text, "relation": o.relation, "badge": o.badge, "evidence": [_row(f) for f in o.findings]}
             for o in ledger.observations]
    data = {"generated_at": time.time(), "model": llm.setting(base), "scope": "Ranked and quick play",
            "matches": match_count(db_path), "observations": found, "dropped": ledger.dropped}
    _save(data, base)
    return data
