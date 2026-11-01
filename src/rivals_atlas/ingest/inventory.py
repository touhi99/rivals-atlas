"""What is stored, for the Data page: counts at each stage, from the raw files down to the derived tables."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from rivals_atlas.analysis.stats import MODES
from rivals_atlas.core import queries
from rivals_atlas.ingest import meta as meta_mod


def _files(folder: Path) -> int:
    return len(list(folder.glob("*.json"))) if folder.exists() else 0


def inventory(con: sqlite3.Connection, base: Path | str) -> dict[str, Any]:
    base = Path(base)
    raw, db_file, m = base / "raw", base / "rivals.db", meta_mod.load(base)
    modes = {MODES.get(r[0], f"mode {r[0]}"): r[1] for r in queries.modes_by_matches(con)}
    return {
        "raw": {"matches": _files(raw / "matches"), "history": _files(raw / "history"),
                "player": (raw / "player.json").exists(), "meta": bool(m)},
        "db": {"matches": queries.stored_figure(con, "matches"), "modes": modes,
               "seasons": queries.stored_figure(con, "seasons"),
               "players": queries.stored_figure(con, "players"),
               "named": queries.stored_figure(con, "named"),
               "no_history": queries.stored_figure(con, "no_history"),
               "player_lines": queries.stored_figure(con, "player_lines"),
               "hero_lines": queries.stored_figure(con, "hero_lines"),
               "bans": queries.stored_figure(con, "bans"),
               "first": queries.stored_figure(con, "first"),
               "last": queries.stored_figure(con, "last"),
               "mb": round(db_file.stat().st_size / 1e6, 1) if db_file.exists() else 0},
        "derived": {"edges": queries.stored_figure(con, "edges"),
                    "meta_heroes": len(m["heroes"]) if m else 0, "meta_teamups": len(m["teamups"]) if m else 0,
                    "meta_age_h": round((time.time() - m.get("fetched_at", 0)) / 3600) if m else None},
    }
