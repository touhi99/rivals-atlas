"""Hero meta from the data site's hero page: pick rate, win rate and ban rate per hero and per rank group, and
team-up win rates. Read at most once a day when the user fetches (two requests: the page for its build id, then the
payload). The payload is in Nuxt's 'devalue' format and is decoded here, then summarised and stored as
raw/meta.json."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

MIN_TEAMUP = 200          # matches across all ranks before a team-up's win rate is shown
DAY = 86400
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef", "NuxtError"}
BUILD = re.compile(r'buildId:"([^"]+)"')
RANK_GROUPS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Grandmaster", "Celestial", "Eternity", "One Above All"]


def devalue(flat: list[Any]) -> Any:
    """Decode Nuxt's payload format: one flat array where containers hold the indexes of their members; index 0 is the
    root and negative numbers are special values."""
    done: dict[int, Any] = {}

    def at(i: Any) -> Any:
        if not isinstance(i, int) or isinstance(i, bool):
            return i
        if i < 0:
            return None
        if i in done:
            return done[i]
        v = flat[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and (v[0] in _WRAPPERS or v[0] in ("Set", "Date", "Map")):
                kind = v[0]
                out = (v[1] if kind == "Date" else [at(x) for x in v[1:]] if kind == "Set"
                       else {str(at(v[k])): at(v[k + 1]) for k in range(1, len(v) - 1, 2)} if kind == "Map"
                       else at(v[1]) if len(v) > 1 else None)
                done[i] = out
                return out
            items: list[Any] = []
            done[i] = items
            items.extend(at(x) for x in v)
            return items
        if isinstance(v, dict):
            obj: dict[str, Any] = {}
            done[i] = obj
            obj.update((k, at(x)) for k, x in v.items())
            return obj
        return v

    return at(0)


def summarize(doc: dict[str, Any]) -> dict[str, Any]:
    """Per hero and rank group (plus 'all'): pick, win and ban rate in percent; team-ups with their win rate."""
    groups = {str(r["rank"]): r["heroes"] for r in doc["heroes"]}
    games = {g: sum(h["matches"] for h in hs if h.get("hero_id")) / 12 for g, hs in groups.items()}
    games["all"] = sum(games.values())
    ban_games = {str(r["rank"]): r["matches"] for r in doc.get("ban_matches") or []}
    ban_games["all"] = sum(ban_games.values())
    bans: dict[tuple[str, Any], int] = {}
    for r in doc.get("bans") or []:
        for b in r["bans"]:
            bans[str(r["rank"]), b["hero_id"]] = b["bans"]
            bans["all", b["hero_id"]] = bans.get(("all", b["hero_id"]), 0) + b["bans"]
    totals: dict[Any, dict[str, dict[str, int]]] = {}
    for g, hs in groups.items():
        for h in hs:
            if not h.get("hero_id"):
                continue
            row = totals.setdefault(h["hero_id"], {})
            row[g] = {k: h.get(k) or 0 for k in ("matches", "wr_matches", "wr_wins")}
            al = row.setdefault("all", {"matches": 0, "wr_matches": 0, "wr_wins": 0})
            for k in al:
                al[k] += row[g][k]
    heroes = []
    for hid, row in totals.items():
        by = {}
        for g, t in row.items():
            if not t["matches"] or not games.get(g):
                continue
            by[g] = {"pick": round(100 * t["matches"] / games[g], 1),
                     "win": round(100 * t["wr_wins"] / t["wr_matches"], 1) if t["wr_matches"] else None,
                     "ban": round(100 * bans.get((g, hid), 0) / ban_games[g], 1) if ban_games.get(g) else None,
                     "matches": t["matches"]}
        heroes.append({"id": hid, "by_rank": by})
    heroes.sort(key=lambda h: -h["by_rank"].get("all", {}).get("pick", 0))
    pairs: dict[str, list[int]] = {}
    for r in doc.get("teamups") or []:
        for t in r["teamups"].values():
            if not isinstance(t, dict):
                continue
            variants: Any = t.get("variants") or {}
            for combo, v in variants.items():
                p = pairs.setdefault(combo, [0, 0])
                p[0] += v.get("matches") or 0
                p[1] += v.get("wins") or 0
    teamups: list[dict[str, Any]] = sorted(({"heroes": [int(x) for x in combo.split(",")], "matches": m, "win": round(100 * w / m, 1)}
                      for combo, (m, w) in pairs.items() if m >= MIN_TEAMUP), key=lambda t: -t["win"])
    return {"season": int(doc.get("season") or 0) or None,
            "ranks": {str(i + 1): name for i, name in enumerate(RANK_GROUPS)}, "heroes": heroes, "teamups": teamups}


def path(base: Path) -> Path:
    return base / "raw" / "meta.json"


def save(base: Path, out: dict[str, Any]) -> None:
    """Write the current meta and keep one dated copy per day (raw/meta_history/YYYY-MM-DD.json), so tier lists can be
    compared over time. A second read on the same day replaces that day's copy."""
    path(base).parent.mkdir(parents=True, exist_ok=True)
    path(base).write_text(json.dumps(out))
    hist = path(base).parent / "meta_history"
    hist.mkdir(exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.localtime(out.get("fetched_at", time.time())))
    (hist / f"{day}.json").write_text(json.dumps(out))


def history(base: Path) -> list[dict[str, Any]]:
    """Stored dated snapshots, oldest first."""
    hist = path(base).parent / "meta_history"
    return [json.loads(f.read_text()) for f in sorted(hist.glob("*.json"))] if hist.exists() else []


def load(base: Path) -> dict[str, Any] | None:
    f = path(base)
    return json.loads(f.read_text()) if f.exists() else None


def fresh(base: Path) -> bool:
    m = load(base)
    return m is not None and time.time() - m.get("fetched_at", 0) < DAY


def group_for_level(level: int | None, meta: dict[str, Any]) -> str:
    """The rank group (a key of meta['ranks']) a tier level belongs to: three levels per group, capped at the
    highest group the data has."""
    top = max((int(k) for h in meta["heroes"] for k in h["by_rank"] if k.isdigit()), default=1)
    return str(max(1, min(((level or 1) - 1) // 3 + 1, top)))


def for_hero(meta: dict[str, Any] | None, hero_id: int, group: str = "all") -> dict[str, Any] | None:
    if not meta:
        return None
    h = next((x for x in meta["heroes"] if x["id"] == hero_id), None)
    return h["by_rank"].get(group) if h else None
