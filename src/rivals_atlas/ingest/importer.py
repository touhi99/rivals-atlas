"""File-import adapter (tier A): reads raw history pages and match documents from a folder, no network."""
from __future__ import annotations

import bisect
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rivals_atlas.core import queries
from rivals_atlas.ingest.parse import FormatChanged, Match, apply_history, parse_match


@dataclass
class Report:
    matches: int = 0
    with_history: int = 0
    self_found: int = 0
    skipped: list[str] = field(default_factory=list)
    self_uid_source: str = ""

    def lines(self) -> list[str]:
        out = [f"imported {self.matches} matches",
               f"  with history (map, season): {self.with_history} / {self.matches}",
               f"  own line identified: {self.self_found} / {self.matches} ({self.self_uid_source})"]
        out += [f"  skipped: {s}" for s in self.skipped[:10]]
        return out


def read_history(folder: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for f in sorted(folder.glob("*.json")):
        page = json.loads(f.read_text())
        if not isinstance(page, list):
            raise FormatChanged(f"{f.name}: history page is not a list")
        for r in page:
            if "match_uid" in r:
                rows[str(r["match_uid"])] = r
    return rows


def infer_self(history: dict[str, dict[str, Any]]) -> Any:
    c = Counter(r["match_player"]["player_uid"] for r in history.values() if r.get("match_player"))
    return c.most_common(1)[0][0] if c else None



def import_folder(con: sqlite3.Connection, raw: Path, self_uid: Any = None) -> Report:
    hist = read_history(raw / "history") if (raw / "history").exists() else {}
    rep = Report()
    if self_uid is None:
        self_uid, rep.self_uid_source = infer_self(hist), "inferred from the history pages"
    else:
        rep.self_uid_source = "configured"
    nicks: dict[str, tuple[int, str]] = {}
    for f in sorted((raw / "matches").glob("*.json")):
        try:
            m = parse_match(json.loads(f.read_text()), self_uid)
            if m.match_uid in hist:
                apply_history(m, hist[m.match_uid])
        except (FormatChanged, KeyError, ValueError) as e:
            rep.skipped.append(f"{f.name}: {e}")
            continue
        store(con, m, f)
        for p in m.players:
            if p.get("nick") and nicks.get(p["player_id"], (0,))[0] <= m.played_at:
                nicks[p["player_id"]] = (m.played_at, p["nick"])
        rep.matches += 1
        rep.with_history += m.has_history
        rep.self_found += any(p["is_self"] for p in m.players)
    store_names(con, nicks)
    infer_seasons(con)
    con.commit()
    return rep


def infer_seasons(con: sqlite3.Connection) -> int:
    """Give a match the history list does not cover yet (no season) the season of its neighbours in time, when the
    nearest known match before and after it agree. Seasons are unbroken stretches of time, so such a match cannot belong
    to another season. These matches keep `has_history = 0`, so they still count as "without map" and a later
    import that finds them in the list replaces the guess. Returns how many were filled in."""
    known = queries.known_seasons(con)
    unknown = queries.matches_without_season(con)
    times = [k[0] for k in known]
    done = 0
    for uid, t in unknown:
        i = bisect.bisect_left(times, t)
        if 0 < i < len(known) and known[i - 1][1] == known[i][1]:
            queries.set_season(con, uid, known[i][1])
            done += 1
    return done


def store_names(con: sqlite3.Connection, nicks: dict[str, tuple[int, str]]) -> None:
    """Keep the latest display name the site showed for every player."""
    queries.clear_player_names(con)
    queries.insert_player_names(con, [(h, n, t) for h, (t, n) in nicks.items()])


def store(con: sqlite3.Connection, m: Match, src: Path) -> None:
    queries.delete_match(con, m.match_uid)
    queries.insert_match(con, {**{k: getattr(m, k) for k in ("match_uid", "played_at", "duration", "mode_id", "season", "map_id",
                                                             "winner_side", "score_0", "score_1", "mvp_id", "svp_id")},
                               "has_history": int(m.has_history)})
    queries.insert_match_players(con, [{**p, "match_uid": m.match_uid} for p in m.players])
    queries.insert_hero_lines(con, [{**h, "match_uid": m.match_uid} for h in m.hero_lines])
    queries.insert_ban_picks(con, [{**b, "match_uid": m.match_uid} for b in m.bans])
    queries.index_raw_match(con, m.match_uid, src.name)
