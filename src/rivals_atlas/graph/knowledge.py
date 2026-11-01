"""Knowledge graph, stage 1: the ontology and the facts that come from outside the player's own matches.

Facts are edges (subject, predicate, object) with numbers on the edge and a source. They live in the `graph_facts`
table and are checked against the ontology before they are written, so a typo cannot create a new kind of node.

Match, Player and the tracked player's results are *not* copied here: they stay in `matches` and `match_players`, and
`ONTOLOGY` says how they map to nodes (a match is a row). Only knowledge from other sources
is stored as facts: team-ups today; abilities and similar facts later.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from typing import Any

from rivals_atlas.core import queries

# node type -> where its identity comes from
NODE_TYPES: dict[str, str] = {
    "Hero": "hero id (seed/heroes.json, match_players.hero_id)",
    "Map": "map id (seed/maps.json, matches.map_id); an id is one map in one mode",
    "Mode": "mode id (matches.mode_id): 1 quick play, 2 ranked",
    "Season": "the site's season number (matches.season, seed/seasons.json)",
    "TeamUp": "sorted hero ids joined by '-', e.g. 1028-1042",
    "Match": "match_uid (row in matches; not copied into facts)",
    "Player": "the site's player id (match_players.player_id; not copied into facts)",
}

# predicate -> (subject type, object type, meaning). The only edges the fact table accepts.
PREDICATES: dict[str, tuple[str, str, str]] = {
    "HAS_MEMBER": ("TeamUp", "Hero", "this hero is part of the team-up; props: matches, win (percent)"),
    "SEEN_IN": ("TeamUp", "Season", "the site's figures for this team-up were read in this season"),
}

SOURCE_META = "rivalsmeta:meta.json"


def teamup_id(heroes: Iterable[int]) -> str:
    return "-".join(str(h) for h in sorted(heroes))


def add_fact(con: sqlite3.Connection, subj: tuple[str, Any], pred: str, obj: tuple[str, Any], source: str,
             asserted_at: int | None = None, **props: Any) -> None:
    if pred not in PREDICATES:
        raise ValueError(f"unknown predicate {pred!r}; known: {sorted(PREDICATES)}")
    st, ot, _ = PREDICATES[pred]
    if (subj[0], obj[0]) != (st, ot):
        raise ValueError(f"{pred} links {st} to {ot}, not {subj[0]} to {obj[0]}")
    queries.insert_fact(con, (subj[0], str(subj[1]), pred, obj[0], str(obj[1]), json.dumps(props, sort_keys=True), source,
                              int(asserted_at if asserted_at is not None else time.time())))


def load_meta(con: sqlite3.Connection, meta: dict[str, Any]) -> int:
    """Replace the facts from meta.json (team-ups) with the current ones. Returns the number of facts written."""
    queries.delete_facts_from(con, SOURCE_META)
    at = int(meta.get("fetched_at") or time.time())
    for t in meta.get("teamups") or []:
        tid = teamup_id(t["heroes"])
        for h in t["heroes"]:
            add_fact(con, ("TeamUp", tid), "HAS_MEMBER", ("Hero", h), SOURCE_META, at, matches=t["matches"], win=t["win"])
        if meta.get("season"):
            add_fact(con, ("TeamUp", tid), "SEEN_IN", ("Season", meta["season"]), SOURCE_META, at)
    con.commit()
    return queries.count_facts_from(con, SOURCE_META)
