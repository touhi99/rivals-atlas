"""Observations: what the Coach and the Tilt guard say about their findings, in a form code can check.

The model writes one short sentence and names the tool calls it rests on, never a number. The app runs those calls itself and
decides whether the stated relation holds; an observation that fails is thrown away. So the numbers are always the data's, and a
difference is only claimed when the 95% ranges really are apart. What code cannot check is the wording: a sentence can still say
"worse" about a pair the bars show the other way. The card puts the bars next to the sentence for that reason.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rivals_atlas.agents import evidence, tools

MAX_SIMILAR_WIDTH = 0.2          # 95% range width: about 100 games


@dataclass
class Observation:
    text: str
    relation: str
    badge: str                      # what the check established, in words
    findings: list[tools.Finding]
    agent: str = ""                 # which specialist wrote it


def _ranged(*fs: tools.Finding) -> str | None:
    if any(f.rate is None or f.lo is None or f.hi is None for f in fs):
        return "the evidence has no win rate"
    return None


def _higher(a: tools.Finding, b: tools.Finding) -> str | None:
    return _ranged(a, b) or (None if a.lo > b.hi else "the 95% ranges overlap")      # type: ignore[operator]


def _lower(a: tools.Finding, b: tools.Finding) -> str | None:
    return _ranged(a, b) or (None if a.hi < b.lo else "the 95% ranges overlap")      # type: ignore[operator]


def _similar(a: tools.Finding, b: tools.Finding) -> str | None:
    """Overlapping ranges only mean 'similar' when both are narrow; two small samples overlap because they say nothing."""
    bad = _ranged(a, b)
    if bad:
        return bad
    if any(f.hi - f.lo > MAX_SIMILAR_WIDTH for f in (a, b)):    # type: ignore[operator]
        return "the samples are too small to call them similar"
    return None if a.lo <= b.hi and b.lo <= a.hi else "the 95% ranges are apart"    # type: ignore[operator]


def _above_even(f: tools.Finding) -> str | None:
    return _ranged(f) or (None if f.lo > 0.5 else "the range reaches 50%")            # type: ignore[operator]


def _below_even(f: tools.Finding) -> str | None:
    return _ranged(f) or (None if f.hi < 0.5 else "the range reaches 50%")            # type: ignore[operator]


def _meta(sign: int) -> Callable[[tools.Finding], str | None]:
    def test(f: tools.Finding) -> str | None:
        if f.tool != "compare_to_meta" or "outside_interval" not in f.value:
            return "needs compare_to_meta with a site figure"
        d = f.value.get("difference")
        return None if f.value["outside_interval"] and d is not None and d * sign > 0 else "the site figure is inside the player's range"
    return test


# relation -> (evidence items needed, test, badge)
RELATIONS: dict[str, tuple[int, Callable[..., str | None], str]] = {
    "higher": (2, _higher, "clear difference"),
    "lower": (2, _lower, "clear difference"),
    "similar": (2, _similar, "no clear difference"),
    "above_even": (1, _above_even, "above 50%"),
    "below_even": (1, _below_even, "below 50%"),
    "above_site": (1, _meta(1), "above the site figure"),
    "below_site": (1, _meta(-1), "below the site figure"),
}


def check(con: sqlite3.Connection, text: str, relation: str, evidence_items: Any, meta: dict[str, Any] | None = None) -> Observation | str:
    """The observation if it holds, otherwise the reason it was dropped."""
    if relation not in RELATIONS:
        return f"unknown relation {relation!r}"
    need, test, badge = RELATIONS[relation]
    if not isinstance(evidence_items, list) or len(evidence_items) != need:
        return f"{relation} needs exactly {need} evidence item(s)"
    findings = []
    for item in evidence_items:
        try:
            findings.append(tools.run(con, str(item["tool"]), dict(item.get("args") or {}), meta))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            return f"an evidence query could not run: {e}"
    if any(not f.enough for f in findings):
        return "too few games in the evidence"
    reason = test(*findings)
    if reason:
        return reason
    stray = evidence.unverified_numbers(text, findings)
    if stray:
        return "the text states numbers: " + ", ".join(stray)
    return Observation(text.strip(), relation, badge, findings)
