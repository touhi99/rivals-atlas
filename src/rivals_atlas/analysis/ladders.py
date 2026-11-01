"""Parallel rank ladders. An account linked across platforms keeps one rank per platform, so its ranked matches
form two chains that run at the same time on different tiers (the data has no platform field).

Rule: inside one season, matches are chained by score (a match starts where the previous match of its chain
ended). A chain is a second ladder when it has at least MIN_MATCHES matches, the main chain has matches both before
and after it (the main ladder was paused and resumed, so the two ran in parallel), and its median tier is at least
MIN_GAP tiers away from the main chain. The first ~10 matches of a season (placement) form their own short chain at similar tiers, are not
interleaved with the main chain, and so are not flagged.
"""
from __future__ import annotations

import statistics
from typing import Any

TOL = 1.6          # points: a chain continues when start score == previous end score, within this
MIN_MATCHES = 3
MIN_GAP = 3        # tiers


def assign(points: list[dict[str, Any]]) -> list[str]:
    """'main' or 'other' for each point; points need season, t, score, delta, level and must be in time order."""
    out = ["main"] * len(points)
    by_season: dict[Any, list[int]] = {}
    for i, p in enumerate(points):
        by_season.setdefault(p["season"], []).append(i)
    for idxs in by_season.values():
        chains: list[dict[str, Any]] = []
        for i in idxs:
            p = points[i]
            start = p["score"] - p["delta"]
            hit = min((c for c in chains if abs(c["last"] - start) <= TOL), key=lambda c: abs(c["last"] - start), default=None)
            if hit is None:
                hit = {"last": p["score"], "idx": []}
                chains.append(hit)
            hit["last"] = p["score"]
            hit["idx"].append(i)
        if len(chains) < 2:
            continue
        main = max(chains, key=lambda c: len(c["idx"]))
        main_levels = statistics.median(points[i]["level"] for i in main["idx"])
        for c in chains:
            if c is main or len(c["idx"]) < MIN_MATCHES:
                continue
            t0, t1 = points[c["idx"][0]]["t"], points[c["idx"][-1]]["t"]
            # the main ladder was paused and resumed around this chain: it has matches before AND after it
            interleaved = (any(points[i]["t"] < t0 for i in main["idx"]) and any(points[i]["t"] > t1 for i in main["idx"]))
            gap = abs(statistics.median(points[i]["level"] for i in c["idx"]) - main_levels)
            if interleaved and gap >= MIN_GAP:
                for i in c["idx"]:
                    out[i] = "other"
    return out
