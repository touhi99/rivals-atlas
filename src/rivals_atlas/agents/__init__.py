"""Agents on Haystack 3.x. A Coordinator delegates to specialists through AgentTool.

All numbers reach the player through the Ledger: tools record the Findings they return, `record_claim` runs the evidence
checker at once, and `Ledger.report()` prints only checked claims. The model's own prose is kept but labelled unchecked.
Tools open their own read-only connection per call because Haystack runs tools in worker threads.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from haystack.components.agents import Agent
from haystack.tools import AgentTool, Tool, create_tool_from_function

from rivals_atlas.agents import evidence, tools
from rivals_atlas.agents.hooks import HOOKS, STATE_SCHEMA
from rivals_atlas.agents.toolset import RivalsToolset
from rivals_atlas.core import db
from rivals_atlas.graph import store as lbug_store

PROMPTS = Path(__file__).parent.parent / "prompts"
MAX_STEPS = 12   # per agent run: a cap on model calls, so one question cannot loop and run up cost


def prompt(name: str) -> str:
    text = (PROMPTS / f"{name}.md").read_text().strip()
    if name == "cartographer":                       # the schema is generated, never copied by hand
        text += "\n\n" + lbug_store.schema_prompt()
    rules = "_rules_cartographer.md" if name == "cartographer" else "_rules.md"      # it has no claim tool, so no claim rule
    return text + "\n\n" + (PROMPTS / rules).read_text().strip()


@dataclass
class Ledger:
    """What happened during one question: every tool result and every checked claim. Shared by all agents of the run."""
    findings: list[tools.Finding] = field(default_factory=list)
    verdicts: list[evidence.Verdict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> tuple[list[tools.Finding], list[evidence.Verdict]]:
        with self._lock:
            return list(self.findings), list(self.verdicts)

    def add_finding(self, f: tools.Finding) -> None:
        with self._lock:
            self.findings.append(f)

    def add_verdict(self, v: evidence.Verdict) -> None:
        with self._lock:
            self.verdicts.append(v)

    def report(self) -> str:
        """Two parts, both built from data: what the tools returned (printed from the numbers themselves, so it holds
        even when a small model never records a claim) and the model's statements that passed the evidence check."""
        results = list(dict.fromkeys(f.describe() for f in self.findings))      # unique, in order
        checked = self._checked()
        parts = []
        if results:
            parts.append("From the data:\n" + "\n".join(f"- {r}" for r in results))
        if checked:
            parts.append("Checked statements:\n" + checked)
        return "\n\n".join(parts) or "No claim could be supported by the data."

    def _checked(self) -> str:
        shown = [v for v in self.verdicts if v.shown]
        dropped = len(self.verdicts) - len(shown)
        lines = []
        for v in shown:
            ids = v.finding.match_ids if v.status == "ok" and v.finding else []
            lines.append(f"- {v.text}" + (f" Matches: {', '.join(ids[:5])}{' ...' if len(ids) > 5 else ''}" if ids else ""))
        if dropped:
            lines.append(f"({dropped} claim{'s' if dropped != 1 else ''} removed because the numbers did not match the data.)")
        return "\n".join(lines)


def claim_tool(db_path: Path | str, ledger: Ledger, meta: dict[str, Any] | None = None) -> Tool:
    def record_claim(text: str, tool: str, args: dict[str, Any], n: int, wins: int | None = None, rate: float | None = None,
                     match_ids: list[str] | None = None) -> str:
        """Record one statement for the answer. The app re-runs `tool` with `args` and compares n, wins, rate and match ids."""
        v = evidence.check(db.connect_readonly(db_path), evidence.Claim(text, tool, args, n, wins, rate, match_ids or []), meta)
        ledger.add_verdict(v)
        return f"{v.status}: {v.reason or 'accepted'}"
    return create_tool_from_function(record_claim)


SPECIALISTS = {
    "coach": ("Recap of play: heroes, maps, rank score, session positions.",
              ("hero_stats", "map_stats", "rank_journey", "session_stats", "compare_to_meta", "match_lookup", "graph_pattern",
               "hero_benchmark")),
    "tilt_guard": ("Checks whether results change by position in a session.",
                   ("session_stats", "hero_stats", "rank_journey")),
    "cartographer": ("Any question about matches, heroes, opponents, teammates, comps: writes a read-only graph query.",
                     ("cypher_query", "comp_stats", "hero_benchmark", "graph_pattern", "match_lookup")),
}


def specialist(name: str, chat_generator: Any, db_path: Path | str, ledger: Ledger, meta: dict[str, Any] | None = None) -> Agent:
    _, names = SPECIALISTS[name]
    # The Cartographer's rows are printed from the data by `Ledger.report`; asking the model to also write one claim per row
    # cost about 6 s of output tokens for nothing, so it has no claim tool.
    claims = [] if name == "cartographer" else [claim_tool(db_path, ledger, meta)]
    return Agent(chat_generator=chat_generator, system_prompt=prompt(name), max_agent_steps=MAX_STEPS,
                 tools=[RivalsToolset(db_path, names, meta, ledger), *claims], hooks=HOOKS, state_schema=STATE_SCHEMA)


def coordinator(chat_generators: dict[str, Any], db_path: Path | str, ledger: Ledger,
                meta: dict[str, Any] | None = None) -> Agent:
    """chat_generators: one per agent name ('coordinator', 'coach', 'tilt_guard'); tests pass MockChatGenerators."""
    team = [AgentTool(specialist(n, chat_generators[n], db_path, ledger, meta), name=n, description=SPECIALISTS[n][0])
            for n in SPECIALISTS]
    return Agent(chat_generator=chat_generators["coordinator"], system_prompt=prompt("coordinator"), tools=team,
                 max_agent_steps=MAX_STEPS, hooks=HOOKS, state_schema=STATE_SCHEMA)


@dataclass
class Answer:
    framing: str       # the model's own words: not checked
    report: str        # checked claims only
    ledger: Ledger
    unverified: list[str] = field(default_factory=list)   # numbers in the model's text that no tool result contains


def ask(question: str, chat_generators: dict[str, Any], db_path: Path | str, meta: dict[str, Any] | None = None,
        ledger: Ledger | None = None) -> Answer:
    """`ledger` may be passed in so a caller (the web page) can watch findings arrive while the agents run."""
    from haystack.dataclasses import ChatMessage
    ledger = ledger or Ledger()
    out = coordinator(chat_generators, db_path, ledger, meta).run(
        messages=[ChatMessage.from_user(question)], hook_context={"ledger": ledger, "question": question})
    return Answer(out["last_message"].text or "", ledger.report(), ledger, out.get("unverified_numbers", []))


def ask_specialist(name: str, question: str, chat_generator: Any, db_path: Path | str,
                   meta: dict[str, Any] | None = None, ledger: Ledger | None = None) -> Answer:
    """Run one specialist directly, without the Coordinator: two model calls fewer (about 7 s with Haiku)."""
    from haystack.dataclasses import ChatMessage
    ledger = ledger or Ledger()
    out = specialist(name, chat_generator, db_path, ledger, meta).run(
        messages=[ChatMessage.from_user(question)], hook_context={"ledger": ledger, "question": question})
    return Answer(out["last_message"].text or "", ledger.report(), ledger, out.get("unverified_numbers", []))
