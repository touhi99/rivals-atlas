"""Pure parsing: raw rivalsmeta documents to canonical records. No I/O, no database."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RESULTS = {1: "win", 0: "loss", 2: "draw"}


class FormatChanged(Exception):
    """A raw document no longer has the expected shape."""


def result_of(is_win: Any) -> str:
    return RESULTS.get(int(is_win), "unknown") if is_win is not None else "unknown"


def main_hero(heroes: list[dict[str, Any]], fallback: int) -> int:
    """The hero with the most play time. Ties go to the later list entry."""
    if not heroes:
        return fallback
    best = max(reversed(heroes), key=lambda h: h.get("play_time") or 0)   # on a tie the later line wins
    return int(best["hero_id"])


@dataclass
class Match:
    match_uid: str
    played_at: int
    duration: float | None
    mode_id: int
    season: int | None = None
    map_id: int | None = None
    winner_side: int | None = None
    score_0: float | None = None
    score_1: float | None = None
    mvp_id: str | None = None
    svp_id: str | None = None
    has_history: bool = False
    players: list[dict[str, Any]] = field(default_factory=list)
    hero_lines: list[dict[str, Any]] = field(default_factory=list)
    bans: list[dict[str, Any]] = field(default_factory=list)


def _need(d: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise FormatChanged(f"missing keys {missing}")


def _int(x: Any) -> int | None:
    return None if x is None else int(x)


def parse_match(doc: dict[str, Any], self_uid: Any = None) -> Match:
    _need(doc, "match_uid", "match_time_stamp", "game_mode_id", "match_players")
    m = Match(
        match_uid=str(doc["match_uid"]),
        played_at=int(doc["match_time_stamp"]),
        duration=doc.get("match_play_duration"),
        mode_id=int(doc["game_mode_id"]),
        mvp_id=str(doc["mvp_uid"]) if doc.get("mvp_uid") else None,
        svp_id=str(doc["svp_uid"]) if doc.get("svp_uid") else None,
    )
    for p in doc["match_players"]:
        _need(p, "player_uid", "camp", "cur_hero_id", "is_win", "k", "d", "a")
        ph = str(p["player_uid"])
        heroes = p.get("player_heroes") or []
        dyn = p.get("dynamic_fields") or {}
        m.players.append({
            "player_id": ph, "camp": int(p["camp"]),
            "hero_id": main_hero(heroes, int(p["cur_hero_id"])),
            "result": result_of(p["is_win"]), "k": p["k"], "d": p["d"], "a": p["a"],
            "damage": p.get("total_hero_damage"), "heal": p.get("total_hero_heal"),
            "taken": p.get("total_damage_taken"), "solo_kills": p.get("solo_kill"),
            "last_kills": p.get("last_kill"), "hit_rate": p.get("session_hit_rate"),
            "add_score": dyn.get("add_score"), "new_score": dyn.get("new_score"),
            "level": _int(dyn.get("level")), "new_level": _int(dyn.get("new_level")),
            "is_self": int(self_uid is not None and p["player_uid"] == self_uid),
            "escaped": None, "nick": p.get("nick_name"),
        })
        for i, h in enumerate(heroes):
            m.hero_lines.append({"player_id": ph, "ord": i, "hero_id": int(h["hero_id"]),
                                 "play_time": h.get("play_time"), "k": h.get("k"), "d": h.get("d"), "a": h.get("a")})
    for i, b in enumerate((doc.get("dynamic_fields") or {}).get("ban_pick_info") or []):
        m.bans.append({"idx": i, "hero_id": _int(b.get("hero_id")), "is_pick": _int(b.get("is_pick")),
                       "battle_side": _int(b.get("battle_side")), "round_idx": _int(b.get("round_idx")),
                       "vote_type": _int(b.get("vote_type"))})
    return m


def apply_history(m: Match, row: dict[str, Any]) -> None:
    """Add what only the history list has: map, season, winner, scores, the tracked player's escaped flag."""
    _need(row, "match_season", "match_map_id", "match_player")
    m.season = _int(row["match_season"])
    m.map_id = _int(row["match_map_id"])
    m.winner_side = _int(row.get("match_winner_side"))
    score = (row.get("dynamic_fields") or {}).get("score_info") or {}
    m.score_0, m.score_1 = score.get("0"), score.get("1")
    m.has_history = True
    own = row["match_player"]
    for p in m.players:
        if p["is_self"]:
            p["escaped"] = int(bool(own.get("has_escaped")))
