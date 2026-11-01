"""Network adapter for rivalsmeta (opt-in). Pages the history list, then fetches each match document.

Rules it keeps: raw files are stored before parsing; one request at a time with a pause; a block (403/429) or
a changed shape stops the run at once with no retry; files already stored are skipped, so a run can be
repeated or resumed; robots.txt is read with this tool's own User-Agent and honoured.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rivals_atlas.core import db
from rivals_atlas.graph import network as graph
from rivals_atlas.graph import store as lbug_store
from rivals_atlas.ingest import meta
from rivals_atlas.ingest.importer import import_folder

HOST = "https://rivalsmeta.com"
UA = "rivals-atlas/0.1 (personal hobby project; one request every few seconds)"
PAGE = 20
Progress = Callable[[dict[str, Any]], None]

PACES = {"normal": 1.0, "gentle": 3.0}   # seconds between requests

NOTICE = """What this does
- Reads one public player profile from rivalsmeta.com, using the endpoints that site's own pages use.
- One request every 3 seconds by default: a profile with a long history takes hours the first time.
- Stores the raw files in the local data folder, then builds a local database. Nothing is sent anywhere else.
- Stops at the first refusal and never retries. The site may change or block this at any time.
- Ranked is fetched by default; quick play only when chosen. Please credit rivalsmeta.com if this tool or its data is used elsewhere.
- Following the site's terms of use is the responsibility of whoever runs this."""


class FetchError(Exception):
    """Anything that stops a run; the message is safe to show to the user."""


class Blocked(FetchError):
    """The site refused or rate-limited the request (403/429)."""


class FormatChanged(FetchError):
    """The site answered in a shape this version does not know."""


def _urllib(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError) as e:
        raise FetchError(f"Network error: {e}") from e


class Http:
    def __init__(self, pause: float = 1.0, transport: Callable[[str], tuple[int, bytes]] = _urllib) -> None:
        self.pause, self.transport = pause, transport

    def get(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        url = HOST + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        status, body = self.transport(url)
        time.sleep(self.pause)
        if status in (403, 429):
            raise Blocked(f"The site answered HTTP {status}. Stop and wait before trying again.")
        if status == 404:
            raise FetchError("Not found (HTTP 404). Check the profile id.")
        if status != 200:
            raise FetchError(f"Unexpected answer from the site (HTTP {status}).")
        return body

    def json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return json.loads(self.get(path, params))
        except json.JSONDecodeError as e:
            raise FormatChanged("The site did not answer with JSON.") from e


def parse_profile(text: str | None) -> str | None:
    """A profile id from what a user pastes: the number itself, or the address of the player's page."""
    t = (text or "").strip()
    if t.isdigit():
        return t
    m = re.search(r"/player/(\d+)", t)
    return m.group(1) if m else None


def check_robots(http: Http, path: str) -> None:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(http.get("/robots.txt").decode("utf-8", "replace").splitlines())
    if not rp.can_fetch(UA, HOST + path):
        raise FetchError("The site's robots.txt does not allow this path for this tool. Nothing was fetched.")


def current_season(doc: dict[str, Any]) -> int:
    seasons = [int(m["match_season"]) for m in doc.get("match_history") or [] if str(m.get("match_season")).isdigit()]
    info = (doc.get("player") or {}).get("info") or {}
    ranked = [int(k.rsplit("2001", 1)[1]) for k in info if k.startswith("rank_game_2001") and k.rsplit("2001", 1)[1].isdigit()]
    return max([*seasons, *ranked], default=0)


OLD_PAGE = re.compile(r"^s(\d+)_skip(\d+)\.json$")


def migrate_history_names(folder: Path) -> int:
    """Older versions named pages `s<season>_skip<n>.json` for every mode, so a quick play run overwrote ranked pages.
    Rename each old page after the mode of its rows; a page with no rows or mixed modes is left alone. Returns renames."""
    n = 0
    for f in folder.glob("s*_skip*.json"):
        m = OLD_PAGE.match(f.name)
        if not m:
            continue
        try:
            modes = {r.get("game_mode_id") for r in json.loads(f.read_text())}
        except (json.JSONDecodeError, AttributeError):
            continue
        if len(modes) == 1 and None not in modes:
            target = folder / f"m{modes.pop()}_s{m.group(1)}_skip{m.group(2)}.json"
            if not target.exists():
                f.rename(target)
                n += 1
    return n


def fetch_history(http: Http, profile: str, mode: int, raw: Path, progress: Progress) -> list[str]:
    """Store every history page of the mode, newest season first. Returns the match uids found."""
    doc = http.json(f"/api/player/{profile}")
    if not isinstance(doc, dict) or "player" not in doc:
        raise FormatChanged("The player document has an unknown shape.")
    vis = doc.get("visibility") or {}
    if vis and not vis.get("match_history", True):
        raise FetchError("This profile hides its match history, so there is nothing to fetch.")
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "player.json").write_text(json.dumps(doc))      # kept as received: it may hold platform and visibility info
    top = current_season(doc)
    if top == 0:
        raise FetchError("No seasons found for this profile. Check the id, or the profile may be private.")
    out = raw / "history"
    out.mkdir(parents=True, exist_ok=True)
    migrate_history_names(out)
    uids: list[str] = []
    # A season's later pages may come from disk only after a run has read them while a newer season already existed:
    # from then on nothing can be added to it. Until then (the current season, or a season that was still running at
    # the last run) every page is read again, because new matches shift all pages.
    marker = raw / f"final_seasons_m{mode}.json"
    final: set[int] = set(json.loads(marker.read_text())) if marker.exists() else set()
    for done, season in enumerate(range(top, 0, -1), 1):
        skip = 0
        while True:
            f = out / f"m{mode}_s{season}_skip{skip}.json"      # the mode is part of the name: modes never share a page
            cached = json.loads(f.read_text()) if f.exists() and skip != 0 and season in final else None
            if isinstance(cached, list) and all(m.get("game_mode_id") == mode for m in cached):
                page = cached
            else:
                page = http.json(f"/api/player-match-history/{profile}",
                                 {"skip": skip, "game_mode_id": mode, "hero_id": 0, "season": season})
                if not isinstance(page, list):
                    raise FormatChanged("The match history has an unknown shape.")
                if any(m.get("game_mode_id") != mode for m in page):
                    raise FormatChanged("The mode filter was not honoured.")
                f.write_text(json.dumps(page))
            uids += [str(m["match_uid"]) for m in page if "match_uid" in m]
            progress({"stage": "history", "done": done, "total": top, "message": f"Season {season}: {len(uids)} matches listed"})
            if len(page) < PAGE:
                break
            skip += PAGE
        if season < top:
            final.add(season)
            marker.write_text(json.dumps(sorted(final)))
    return uids


def fetch_matches(http: Http, uids: list[str], raw: Path, limit: int | None, progress: Progress) -> int:
    out = raw / "matches"
    out.mkdir(parents=True, exist_ok=True)
    todo = [u for u in uids if not (out / f"{u}.json").exists()]
    if limit is not None:
        todo = todo[:limit]
    for i, uid in enumerate(todo, 1):
        doc = http.json(f"/api/matches/{uid}")
        if not isinstance(doc, dict) or "match_players" not in doc:
            raise FormatChanged("A match document has an unknown shape.")
        (out / f"{uid}.json").write_text(json.dumps(doc))
        progress({"stage": "matches", "done": i, "total": len(todo), "message": f"Match {i} of {len(todo)}"})
    return len(todo)


def fetch_meta(http: Http, base: Path, progress: Progress) -> bool:
    """Read the hero meta (pick, win and ban rate per rank group, team-ups) unless it is less than a day old."""
    if meta.fresh(base):
        return False
    progress({"stage": "meta", "done": 0, "total": 1, "message": "Reading the hero meta"})
    page = http.get("/characters").decode("utf-8", "replace")
    m = meta.BUILD.search(page)
    if not m:
        raise FormatChanged("The heroes page has an unknown shape.")
    payload = http.json("/characters/_payload.json", {"_b": m.group(1)})
    data = (meta.devalue(payload) or {}).get("data") or {}
    doc = next((v for k, v in data.items() if k.startswith("heroes-stats")), None)
    if not isinstance(doc, dict) or not doc.get("heroes"):
        raise FormatChanged("The hero stats have an unknown shape.")
    out = {**meta.summarize(doc), "fetched_at": time.time(), "updated_at": doc.get("timestamp")}
    meta.save(base, out)
    return True


def run(profile: str, mode: int, base: Path, limit: int | None = None, http: Http | None = None,
        progress: Progress = lambda p: None, pace: str = "normal") -> dict[str, Any]:
    """Fetch, then import. Raises FetchError (or a subclass) with a message fit for the user."""
    http = http or Http(pause=PACES.get(pace, 1.0))
    raw = base / "raw"
    check_robots(http, "/api/matches/x")
    uids = fetch_history(http, profile, mode, raw, progress)
    if not uids:
        raise FetchError("No matches found for this profile and mode.")
    new = fetch_matches(http, uids, raw, limit, progress)
    meta_note = None
    try:
        fetch_meta(http, base, progress)
    except Blocked:
        raise
    except FetchError as e:
        meta_note = str(e)                         # the hero meta is a bonus: a changed page must not lose the matches
    progress({"stage": "import", "done": 0, "total": 1, "message": "Importing"})
    con = db.connect(base / "rivals.db")
    rep = import_folder(con, raw, None)
    graph.build(con)
    lbug_store.rebuild(con, base / lbug_store.GRAPH_FILE, meta.load(base))
    con.close()
    progress({"stage": "done", "done": 1, "total": 1, "message": f"Done: {rep.matches} matches in the database"})
    return {"listed": len(uids), "fetched": new, "imported": rep.matches, "with_history": rep.with_history,
            "meta_note": meta_note}
