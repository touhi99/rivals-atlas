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
from rivals_atlas.agents import observations as obs
from rivals_atlas.agents.hooks import HOOKS, STATE_SCHEMA
from rivals_atlas.agents.toolset import RivalsToolset
from rivals_atlas.analysis import stats
from rivals_atlas.core import db, names, queries
from rivals_atlas.core.filters import Filter
from rivals_atlas.graph import store as lbug_store

PROMPTS = Path(__file__).parent.parent / "prompts"
MAX_STEPS = 12   # per agent run: a cap on model calls, so one question cannot loop and run up cost


def prompt(name: str, insights: bool = False) -> str:
    if insights:                                     # the insights run: observations the app checks, not claims
        return (PROMPTS / f"insights_{name}.md").read_text().strip() + "\n\n" + (PROMPTS / "_rules_insights.md").read_text().strip()
    text = (PROMPTS / f"{name}.md").read_text().strip()
    if name == "cartographer":                       # the schema is generated, never copied by hand
        text += "\n\n" + lbug_store.schema_prompt()
    rules = "_rules_cartographer.md" if name == "cartographer" else "_rules.md"      # it has no claim tool, so no claim rule
    return text + "\n\n" + (PROMPTS / rules).read_text().strip()


def data_context(db_path: Path | str, top: int = 8, insights: bool = False) -> str:
    """What the Coach and Tilt guard cannot look up with their tools: the latest ranked season's number and the player's most
    played heroes and maps with their ids. Generated from the data, like the Cartographer's schema."""
    con = db.connect_readonly(db_path)
    seasons = queries.seasons_in_mode(con, 2)
    if not seasons:
        return ""
    s0 = seasons[0]
    f = Filter(mode=2, season_from=s0, season_to=s0)
    heroes = sorted(stats.heroes(con, f), key=lambda h: -h["games"])[:top]
    maps = sorted(stats.maps(con, f), key=lambda m: -m["games"])[:top]
    lines = [(f"The player's data: the latest ranked season is {names.season_label(s0)}. In tool calls it is season_from={s0}, "
              f"season_to={s0}, mode=2. Use these unless the question asks for something else."),
             "Most played heroes this season (hero id, games): " + ", ".join(
                 f"{names.hero_name(h['hero_id'])} (id {h['hero_id']}, {h['games']})" for h in heroes),
             "Most played maps this season (map id, games): " + ", ".join(
                 f"{names.map_name(m['map_id'])} (id {m['map_id']}, {m['games']})" for m in maps)]
    if insights:
        counts = dict(con.execute("SELECT mode_id, COUNT(*) FROM matches GROUP BY mode_id").fetchall())
        lines.append("Games stored: " + ", ".join(f"{label} {counts.get(mode, 0)}" for mode, label in ((2, "ranked"), (1, "quick play")))
                     + ". The mode with more games shows clear differences more often.")
        for mode, label in ((2, "ranked"), (1, "quick play")):
            every = sorted(stats.heroes(con, Filter(mode=mode)), key=lambda h: -h["games"])[:top]
            lines.append(f"Most played heroes over all {label} seasons, mode={mode} (hero id, games): " + ", ".join(
                f"{names.hero_name(h['hero_id'])} (id {h['hero_id']}, {h['games']})" for h in every))
        lines.append(f"For earlier ranked play use season_to={s0 - 1} and no season_from. Leave the season out to use every season.")
    return "\n\n" + "\n".join(lines)


@dataclass
class Ledger:
    """What happened during one question: every tool result and every checked claim. Shared by all agents of the run."""
    findings: list[tools.Finding] = field(default_factory=list)
    verdicts: list[evidence.Verdict] = field(default_factory=list)
    observations: list[obs.Observation] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)          # why an observation was thrown away
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

    def add_observation(self, o: obs.Observation) -> None:
        with self._lock:
            if o.text not in [x.text for x in self.observations]:
                self.observations.append(o)

    def add_dropped(self, reason: str) -> None:
        with self._lock:
            self.dropped.append(reason)

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


def observation_tool(db_path: Path | str, ledger: Ledger, meta: dict[str, Any] | None = None) -> Tool:
    def record_observation(text: str, relation: str, evidence: list[dict[str, Any]]) -> str:
        """Record one observation for the page: one short sentence with no digits, a relation (higher, lower, similar, above_even,
        below_even, above_site, below_site, rose, fell) and the tool calls it rests on, each {"tool": name, "args": {...}}. The
        app runs them and keeps the observation only if the relation holds."""
        r = obs.check(db.connect_readonly(db_path), text, relation, evidence, meta)
        if isinstance(r, str):
            ledger.add_dropped(r)
            return f"dropped: {r}"
        ledger.add_observation(r)
        return "accepted"
    return create_tool_from_function(record_observation)


SPECIALISTS = {
    "coach": ("Recap of play: heroes, maps, rank score, session positions.",
              ("hero_stats", "map_stats", "rank_journey", "session_stats", "compare_to_meta", "match_lookup", "graph_pattern",
               "hero_benchmark")),
    "tilt_guard": ("Checks whether results change by position in a session.",
                   ("session_stats", "hero_stats", "rank_journey")),
    "cartographer": ("Any question about matches, heroes, opponents, teammates, comps: writes a read-only graph query.",
                     ("cypher_query", "comp_stats", "hero_benchmark", "graph_pattern", "match_lookup")),
}


def specialist(name: str, chat_generator: Any, db_path: Path | str, ledger: Ledger, meta: dict[str, Any] | None = None,
               insights: bool = False) -> Agent:
    _, tool_names = SPECIALISTS[name]
    # The Cartographer's rows are printed from the data by `Ledger.report`; asking the model to also write one claim per row
    # cost about 6 s of output tokens for nothing, so it has no claim tool.
    if insights:
        extra = [observation_tool(db_path, ledger, meta)]
    else:
        extra = [] if name == "cartographer" else [claim_tool(db_path, ledger, meta)]
    system = prompt(name, insights) + ("" if name == "cartographer" else data_context(db_path, insights=insights))
    return Agent(chat_generator=chat_generator, system_prompt=system, max_agent_steps=MAX_STEPS * 2 if insights else MAX_STEPS,
                 tools=[RivalsToolset(db_path, tool_names, meta, ledger), *extra], hooks=HOOKS, state_schema=STATE_SCHEMA)


def coordinator(chat_generators: dict[str, Any], db_path: Path | str, ledger: Ledger,
                meta: dict[str, Any] | None = None, insights: bool = False) -> Agent:
    """chat_generators: one per agent name ('coordinator', 'coach', 'tilt_guard'); tests pass MockChatGenerators."""
    roster = [n for n in SPECIALISTS if not (insights and n == "cartographer")]
    team = [AgentTool(specialist(n, chat_generators[n], db_path, ledger, meta, insights), name=n, description=SPECIALISTS[n][0])
            for n in roster]
    system = (PROMPTS / "insights_coordinator.md").read_text().strip() if insights else prompt("coordinator")
    return Agent(chat_generator=chat_generators["coordinator"], system_prompt=system, tools=team,
                 max_agent_steps=MAX_STEPS, hooks=HOOKS, state_schema=STATE_SCHEMA)


@dataclass
class Answer:
    framing: str       # the model's own words: not checked
    report: str        # checked claims only
    ledger: Ledger
    unverified: list[str] = field(default_factory=list)   # numbers in the model's text that no tool result contains


def ask(question: str, chat_generators: dict[str, Any], db_path: Path | str, meta: dict[str, Any] | None = None,
        ledger: Ledger | None = None, insights: bool = False) -> Answer:
    """`ledger` may be passed in so a caller (the web page) can watch findings arrive while the agents run."""
    from haystack.dataclasses import ChatMessage
    ledger = ledger or Ledger()
    out = coordinator(chat_generators, db_path, ledger, meta, insights).run(
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
