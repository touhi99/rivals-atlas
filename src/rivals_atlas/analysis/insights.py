"""Findings with receipts: what differs from the rest of the tracked player's games, after correcting for how many
things were checked.

Each candidate (a hero, a map, an enemy hero, a teammate, the result after a loss) is compared with all the
tracked player's other games using a two-proportion test. All p-values go through Benjamini-Hochberg at q = 0.10, so
adding more checks does not add more false alarms. Players who nearly always queue together are reported as
one party, not as separate findings. Nothing here is a prediction.
"""
from __future__ import annotations

import math
import sqlite3
from itertools import pairwise
from typing import Any

from rivals_atlas.analysis.stats import wilson
from rivals_atlas.core import names, queries
from rivals_atlas.core.filters import Filter

MIN_N = 15
Q = 0.10


def two_prop_p(w1: int, n1: int, w2: int, n2: int) -> float:
    """Two-sided p-value for 'the two win rates are equal' (pooled z test)."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(w1 / n1 - w2 / n2) / se
    return math.erfc(z / math.sqrt(2))


def benjamini_hochberg(pvals: list[float], q: float = Q) -> set[int]:
    """Indices of the tests that pass at false discovery rate q."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    cut = -1
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cut = rank
    return set(order[:cut]) if cut > 0 else set()


def _cand(kind: str, title: str, w: int, n: int, w2: int, n2: int, **extra: Any) -> dict[str, Any] | None:
    if n < MIN_N or n2 < MIN_N:
        return None
    lo, hi = wilson(w, n)
    return {"kind": kind, "title": title, "n": n, "wins": w, "rate": w / n, "base": w2 / n2, "n2": n2,
            "lo": lo, "hi": hi, "p": two_prop_p(w, n, w2, n2), "direction": "up" if w / n > w2 / n2 else "down",
            **extra}


def _rows(con: sqlite3.Connection, f: Filter) -> list[sqlite3.Row]:
    return queries.decided_rows(con, f)


def compute(con: sqlite3.Connection, f: Filter, limit: int = 12) -> dict[str, Any]:
    rows = _rows(con, f)
    N = len(rows)
    W = sum(r["result"] == "win" for r in rows)
    if N < 2 * MIN_N:
        return {"base": (W / N if N else None), "total": N, "findings": [], "checked": 0, "flagged": 0}
    cands: list[dict[str, Any] | None] = []

    def split(key: str, label, kind: str, **extra):
        groups: dict[Any, list[int]] = {}
        for r in rows:
            g = groups.setdefault(r[key], [0, 0])
            g[0] += r["result"] == "win"
            g[1] += 1
        for k, (w, n) in groups.items():
            if k is not None and not (key == "hero_id" and k == 0):      # hero 0 = a game left before any hero was played
                ex = {"hero_id": k} if kind in ("hero",) else {}
                cands.append(_cand(kind, label(k), w, n, W - w, N - n, **ex, **extra))

    split("hero_id", lambda k: f"{names.hero_name(k)} (games played as it)", "hero")
    split("map_id", lambda k: f"On {names.map_name(k)}", "map")

    # enemy heroes: games where this hero was on the other side, versus the rest
    enemy: dict[int, set[str]] = {}
    for r in queries.enemy_heroes(con, f):
        enemy.setdefault(r["hero_id"], set()).add(r["match_uid"])
    res = {r["match_uid"]: r["result"] == "win" for r in rows}
    for hid, uids in enemy.items():
        ids = [u for u in uids if u in res]
        w = sum(res[u] for u in ids)
        cands.append(_cand("enemy", f"When the enemy has {names.hero_name(hid)}", w, len(ids), W - w, N - len(ids),
                           hero_id=hid))

    # teammates, grouped into parties when they nearly always play together
    mates: dict[str, set[str]] = {}
    for r in queries.teammate_matches(con, f):
        if r["match_uid"] in res:
            mates.setdefault(r["player_id"], set()).add(r["match_uid"])
    big = sorted((h for h, u in mates.items() if len(u) >= MIN_N), key=lambda h: -len(mates[h]))
    used: set[str] = set()
    for h in big:
        if h in used:
            continue
        party = [h] + [o for o in big if o != h and o not in used and
                       len(mates[h] & mates[o]) / len(mates[h] | mates[o]) > 0.8]
        used.update(party)
        uids = set.intersection(*(mates[x] for x in party)) if len(party) > 1 else mates[h]
        w = sum(res[u] for u in uids)
        label = " & ".join(names.player_label(con, x) for x in party)
        cands.append(_cand("squad", f"With {label}", w, len(uids), W - w, N - len(uids), party=len(party)))

    # tilt: the result right after a loss, versus right after a win
    after = {"win": [0, 0], "loss": [0, 0]}
    for prev, cur in pairwise(rows):
        g = after[prev["result"]]
        g[1] += 1
        g[0] += cur["result"] == "win"
    cands.append(_cand("tilt", "Right after a loss (vs right after a win)", *after["loss"], *after["win"]))

    cs = [c_ for c_ in cands if c_]
    keep = benjamini_hochberg([c_["p"] for c_ in cs])
    out = [dict(c_, gap=abs(c_["rate"] - c_["base"])) for i, c_ in enumerate(cs) if i in keep]
    out.sort(key=lambda x: x["p"])
    return {"base": W / N, "total": N, "findings": out[:limit], "checked": len(cs), "flagged": len(out)}
