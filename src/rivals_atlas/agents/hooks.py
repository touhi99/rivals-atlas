"""Haystack hooks: checks that run inside the Agent loop whatever the model decides to call.

A hook changes a run only by writing to `State`. The ledger of the run arrives through `hook_context` (request-scoped, never
serialised), so the hooks themselves stay plain, serialisable functions.
"""
from __future__ import annotations

from haystack.components.agents.state import State
from haystack.hooks import Hook, HookPoint, hook

from rivals_atlas.agents import evidence

STATE_SCHEMA = {"unverified_numbers": {"type": list[str]}}
HOOKS: dict[HookPoint, list[Hook]] = {}      # filled below: hook point -> hooks


@hook
def check_numbers(state: State) -> None:
    """on_exit: list the numbers in the final text that no tool result contains (see evidence.unverified_numbers)."""
    ctx = state.data.get("hook_context") or {}
    ledger = ctx.get("ledger")
    messages = state.get("messages") or []
    if ledger is None or not messages:
        return
    findings, _ = ledger.snapshot()
    state.set("unverified_numbers", evidence.unverified_numbers(messages[-1].text or "", findings, ctx.get("question", "")))


HOOKS["on_exit"] = [check_numbers]
