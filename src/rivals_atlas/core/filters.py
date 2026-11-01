"""One filter for every view. It compiles to a SQL condition on the tracked player's own match rows, so stats,
insights and the API can never disagree about which matches are in play.

Aliases in the condition: p = the tracked player's match_players row, m = matches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class Filter:
    mode: int = 2                       # 2 ranked, 1 quick play, 0 both
    season_from: int | None = None
    season_to: int | None = None
    hero: int | None = None
    map_id: int | None = None
    with_players: tuple[str, ...] = field(default_factory=tuple)   # teammates who must be on the tracked player's side

    def cond(self) -> tuple[str, list[Any]]:
        parts: list[str] = []
        args: list[Any] = []
        if self.mode:                   # 0 means every mode
            parts.append("m.mode_id = ?")
            args.append(self.mode)
        if self.season_from is not None:
            parts.append("m.season >= ?"); args.append(self.season_from)
        if self.season_to is not None:
            parts.append("m.season <= ?"); args.append(self.season_to)
        if self.hero is not None:
            parts.append("p.hero_id = ?"); args.append(self.hero)
        if self.map_id is not None:
            from rivals_atlas.core.names import (
                same_map_ids,  # late: names uses queries, which uses this module
            )
            ids = same_map_ids(self.map_id)                           # a map is the same map in ranked and in quick play
            parts.append(f"m.map_id IN ({','.join('?' * len(ids))})")
            args.extend(ids)
        for h in self.with_players:
            parts.append("EXISTS (SELECT 1 FROM match_players t WHERE t.match_uid = p.match_uid "
                         "AND t.player_id = ? AND t.camp = p.camp)")
            args.append(h)
        return " AND ".join(parts) or "1=1", args       # no condition at all (mode 0, nothing else chosen)

    @property
    def active(self) -> bool:
        return any((self.season_from, self.season_to, self.hero, self.map_id, self.with_players))

    def query(self, **over) -> str:
        """URL query string for this filter with some fields replaced (None removes a field)."""
        d = {"mode": self.mode, "season_from": self.season_from, "season_to": self.season_to,
             "hero": self.hero, "map_id": self.map_id, "with": list(self.with_players)}
        d.update(over)
        flat = [(k, x) for k, v in d.items() for x in (v if isinstance(v, list) else [v]) if x not in (None, "", [])]
        return urlencode(flat)

    def replace(self, **kw) -> Filter:
        d = {**self.__dict__, **kw}
        return Filter(**d)
