"""One language model for every agent, chosen by a setting (environment or data/settings.json).

    RIVALS_ATLAS_LLM = ollama:<model>     local Ollama server (default http://localhost:11434)
                       lmstudio:<model>   LM Studio's OpenAI-compatible server (default http://localhost:1234/v1)
                       anthropic:<model>  Anthropic API, needs ANTHROPIC_API_KEY
    RIVALS_ATLAS_LLM_URL overrides the server address of the local providers.

The key stays in the environment; nothing here logs it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret

from rivals_atlas.agents import usage_report
from rivals_atlas.core import config

DEFAULT = "ollama:granite4.1:3b"


def setting(base: Path | None = None) -> str:
    return os.environ.get("RIVALS_ATLAS_LLM") or config.load_settings(base).get("llm") or DEFAULT


def make_generator(spec: str | None = None, **generation_kwargs: Any) -> Any:
    """A fresh Haystack chat generator for 'provider:model'. Each agent gets its own. Its usage goes to Meter."""
    provider, _, model = (spec or setting()).partition(":")
    return usage_report.wrap(_build_generator(spec, **generation_kwargs), provider, model)


def _build_generator(spec: str | None = None, **generation_kwargs: Any) -> Any:
    provider, _, model = (spec or setting()).partition(":")
    if not model:
        raise ValueError("LLM setting must look like provider:model, for example ollama:granite4.1:3b")
    url = os.environ.get("RIVALS_ATLAS_LLM_URL")
    if provider == "ollama":
        from haystack_integrations.components.generators.ollama import OllamaChatGenerator
        return OllamaChatGenerator(model=model, url=url or "http://localhost:11434", timeout=300,
                                   generation_kwargs={"temperature": 0, **generation_kwargs})
    if provider == "lmstudio":
        return OpenAIChatGenerator(model=model, api_base_url=url or "http://localhost:1234/v1", api_key=Secret.from_token("lm-studio"),
                                   generation_kwargs={"temperature": 0, **generation_kwargs})
    if provider == "anthropic":
        from haystack_integrations.components.generators.anthropic import AnthropicChatGenerator
        return AnthropicChatGenerator(model=model, generation_kwargs=generation_kwargs or None)   # this SDK takes no temperature
    raise ValueError(f"unknown LLM provider {provider!r}; use ollama, lmstudio or anthropic")


def generators(spec: str | None = None) -> dict[str, Any]:
    """One generator per agent name, all the same model."""
    return {name: make_generator(spec) for name in ("coordinator", "coach", "tilt_guard", "cartographer", "squad_synergy", "matchup_advisor")}
