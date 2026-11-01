"""The evidence rule: a claim is only shown if re-running its query gives the same numbers.

A claim names the tool and arguments behind it, the sample size and the matches it cites. The checker runs the
tool again and compares. Same numbers and enough games: shown with its sample size, interval and receipts.
Same numbers but too few games: rewritten as 'not enough games'. Different numbers, a failed query or matches
the query does not return: dropped. No model is involved, so it holds whatever wrote the claim.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from rivals_atlas.agents import tools
from rivals_atlas.analysis import stats

RATE_TOLERANCE = 0.005   # a claim rounded to a whole percent still matches


@dataclass
class Claim:
    text: str
    tool: str
    args: dict[str, Any]
    n: int
    wins: int | None = None
    rate: float | None = None
    match_ids: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    status: str                        # "ok" | "insufficient" | "dropped"
    text: str                          # what may be shown ("" when dropped)
    reason: str
    claim: Claim
    finding: tools.Finding | None = None

    @property
    def shown(self) -> bool:
        return self.status != "dropped"


def _drop(claim: Claim, reason: str, finding: tools.Finding | None = None) -> Verdict:
    return Verdict("dropped", "", reason, claim, finding)


def check(con: sqlite3.Connection, claim: Claim, meta: dict[str, Any] | None = None) -> Verdict:
    try:
        fresh = tools.run(con, claim.tool, claim.args, meta)
    except (KeyError, TypeError, ValueError) as e:
        return _drop(claim, f"query could not run: {e}")
    if fresh.n != claim.n:
        return _drop(claim, f"sample size differs: claimed {claim.n}, query gives {fresh.n}", fresh)
    if claim.wins is not None and claim.wins != fresh.wins:
        return _drop(claim, f"wins differ: claimed {claim.wins}, query gives {fresh.wins}", fresh)
    if claim.rate is not None and (fresh.rate is None or abs(claim.rate - fresh.rate) > RATE_TOLERANCE):
        got = "none" if fresh.rate is None else f"{fresh.rate:.3f}"
        return _drop(claim, f"rate differs: claimed {claim.rate:.3f}, query gives {got}", fresh)
    stray = sorted(set(claim.match_ids) - set(fresh.match_ids))
    if stray:
        return _drop(claim, f"cites {len(stray)} match(es) the query does not return", fresh)
    if fresh.tool == "cypher_query":
        stray_numbers = _numbers_not_in_rows(claim, fresh)
        if stray_numbers:
            return _drop(claim, f"number(s) {', '.join(stray_numbers)} are not in the query's rows", fresh)
    if not fresh.enough:
        return Verdict("insufficient", f"Not enough games to say (n={fresh.n}, at least {stats.MIN_GAMES} needed).",
                       "sample below the minimum", claim, fresh)
    text = claim.text.rstrip(". ")
    if fresh.tool == "cypher_query":                       # n is a row count there, not a sample size
        return Verdict("ok", text + ".", "", claim, fresh)
    if f"n={fresh.n}" not in text:                         # the model often writes it itself: do not repeat
        text += f" (n={fresh.n}" + (f", 95% interval {fresh.lo:.0%} to {fresh.hi:.0%}" if fresh.lo is not None else "") + ")"
    return Verdict("ok", text + ".", "", claim, fresh)


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers_not_in_rows(claim: Claim, fresh: tools.Finding) -> list[str]:
    """For free-form graph queries: every number the claim text states must be a value in the returned rows, the row count,
    or digits that are part of the query itself (a map called 'Tokyo 2099'). Totals the model added up are refused: it
    records one claim per row instead."""
    allowed = {str(fresh.n)}
    for row in fresh.items:
        for v in row.values():
            if isinstance(v, int | float) and not isinstance(v, bool):
                allowed.add(str(int(v)) if float(v).is_integer() else str(v))
    allowed |= set(_NUMBER.findall(str(claim.args.get("cypher", ""))))
    text = re.sub(r"n\s*=\s*\d+", "", claim.text)
    return [x for x in dict.fromkeys(_NUMBER.findall(text)) if x not in allowed
            and not (x.endswith("0") and "." in x and x.rstrip("0").rstrip(".") in allowed)]


_TEXT_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


def unverified_numbers(text: str, findings: list[tools.Finding], question: str = "") -> list[str]:
    """Numbers in free model text that no tool result contains. This is the check that holds even when the model never records
    a claim: each number the text states must appear in a result (a count, a rate as a percent, a value in a row) or in the
    question. A total the model added up is listed too: it may be right, but the data did not state it."""
    allowed: set[float] = set()
    for f in findings:
        for token in _TEXT_NUMBER.findall(json.dumps(f.to_dict(), default=str)):
            allowed.add(float(token.rstrip("%")))
        for v in (f.rate, f.lo, f.hi):
            if v is not None:
                allowed.add(round(v * 100))
        for item in f.items:
            for v in item.values():
                if isinstance(v, float) and 0 <= v <= 1:
                    allowed.add(round(v * 100))
    allowed |= {float(x.rstrip("%")) for x in _TEXT_NUMBER.findall(question)}
    out = []
    for token in dict.fromkeys(_TEXT_NUMBER.findall(text)):
        value = float(token.rstrip("%"))
        if value not in allowed and not (token.endswith("%") and round(value) in allowed):
            out.append(token)
    return out
