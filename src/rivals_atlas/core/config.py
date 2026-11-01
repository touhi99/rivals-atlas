"""Where data lives. One folder holds the raw files and the database."""
from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    d = Path(os.environ.get("RIVALS_ATLAS_DATA", "data")).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "settings.json"


def load_settings(base: Path | None = None) -> dict:
    f = settings_path(base)
    return json.loads(f.read_text()) if f.exists() else {}


def save_settings(values: dict, base: Path | None = None) -> dict:
    cur = {**load_settings(base), **values}
    f = settings_path(base)
    f.write_text(json.dumps(cur, indent=1))
    f.chmod(0o600)
    return cur


def load_env(path: Path | str = ".env") -> list[str]:
    """Read KEY=value lines from a .env file into the environment. Variables that are already set win. Returns the names
    that were set (never the values). Quotes around a value are removed; `#` starts a comment line."""
    f = Path(path)
    if not f.is_file():
        return []
    done = []
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("\"'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            done.append(key)
    return done
