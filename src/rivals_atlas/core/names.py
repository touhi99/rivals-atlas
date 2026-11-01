"""Hero and map names. Heroes come from a checked-in seed (id to name). Maps have no source yet:
the user can name them in <data dir>/maps.json, {"1245": "Name"}. Anything unknown shows its id."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from rivals_atlas.core import config, queries

SEED = Path(__file__).parent.parent / "seed"


@lru_cache
def _heroes() -> dict[str, str]:
    return json.loads((SEED / "heroes.json").read_text())


def hero_names() -> list[str]:
    """English hero names from the seed list."""
    return sorted(set(_heroes().values()))


def map_names() -> list[str]:
    return sorted({v for v in _maps().values() if v})


def _roles() -> dict[str, dict[str, str]]:
    return json.loads((SEED / "roles.json").read_text())


def _seed(name: str) -> dict[str, str]:
    return json.loads((SEED / name).read_text())


def _maps() -> dict[str, str]:
    """Seed names, overridden by the user's own <data dir>/maps.json."""
    out = _seed("maps.json")
    f = config.data_dir() / "maps.json"
    if f.exists():
        out.update({k: v for k, v in json.loads(f.read_text()).items() if v})
    return out


def same_map_ids(map_id: int) -> tuple[int, ...]:
    """Every map id that shows under the same name. The game gives one map in one game mode a separate id for ranked and for
    quick play, so "Yggsgard · Convoy" has two ids; they are the same map for every purpose except which mode was played."""
    name = map_name(map_id)
    ids = sorted({int(k) for k, v in _maps().items() if v == name} | {int(map_id)})
    return tuple(ids)


def canonical_map_id(map_id: int) -> int:
    """The one id that stands for all ids of the same name (the smallest)."""
    return same_map_ids(map_id)[0]


def hero_name(hero_id: int | str | None) -> str:
    return _heroes().get(str(hero_id), f"Hero {hero_id}")


def map_name(map_id: int | str | None) -> str:
    return _maps().get(str(map_id)) or f"Map {map_id}"


PORTRAIT = "https://rivalsmeta.com/_ipx/w_120&q_70/images/heroes/OriginalSkin/img_heroportrait_{id}0010_portrait.png"


def hero_icon(hero_id: int | str | None) -> str | None:
    """Link to the site's portrait (not a copy). Off with RIVALS_ATLAS_IMAGES=off, then the page loads nothing external."""
    if os.environ.get("RIVALS_ATLAS_IMAGES", "on").lower() == "off" or str(hero_id) not in _heroes():
        return None
    return PORTRAIT.format(id=hero_id)


MAP_ART = "https://rivalsmeta.com/_ipx/w_300&q_70/images/Map/{name}.png"


def map_icon(map_id: int | str | None) -> str | None:
    """Link to the site's map banner (not a copy); None when the map has no picture or images are off."""
    name = _seed("map_images.json").get(str(map_id))
    if not name or os.environ.get("RIVALS_ATLAS_IMAGES", "on").lower() == "off":
        return None
    return MAP_ART.format(name=name)


def tier_name(level: int | None) -> str:
    return _seed("tiers.json").get(str(level), f"Tier {level}") if level else "Unranked"


def season_label(season: int | None) -> str:
    return _seed("seasons.json").get(str(season), f"Season {season}") if season is not None else "?"


def player_label(con, player_id: str) -> str:
    """The tracked player's local alias for a regular teammate if stored, else a short id."""
    return queries.player_alias(con, player_id) or player_id[:6]


ROLES = {1: "Vanguard", 2: "Duelist", 3: "Strategist"}
_ROLE_IDS = {name: i for i, name in ROLES.items()}


def role_id(hero_id: int | str | None) -> int | None:
    """1 vanguard, 2 duelist, 3 strategist; None for a hero missing from seed/roles.json."""
    v = _roles().get(str(hero_id))
    return _ROLE_IDS.get(v["role"]) if v else None


def role_name(hero_id: int | str | None) -> str:
    r = role_id(hero_id)
    return ROLES[r] if r else "Unknown role"


def comp_label(comp: str) -> str:
    """'2-2-2' -> '2 Vanguard · 2 Duelist · 2 Strategist' (zero counts left out)."""
    try:
        counts = [int(x) for x in comp.split("-")]
    except ValueError:
        return comp
    return " · ".join(f"{n} {ROLES[i + 1]}" for i, n in enumerate(counts) if n) or comp
