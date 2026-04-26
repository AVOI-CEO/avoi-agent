"""Tests for the Nous-Hermes-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"avoi"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``avoi-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "avoi" tag namespace.

``is_avoi_avoi_non_agentic`` should only match the actual AVOI AI
Hermes-3 / Hermes-4 chat family.
"""

from __future__ import annotations

import pytest

from avoi_cli.model_switch import (
    _AVOI_MODEL_WARNING,
    _check_avoi_model_warning,
    is_avoi_avoi_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "avoi-ai/Hermes-3-Llama-3.1-70B",
        "avoi-ai/Hermes-3-Llama-3.1-405B",
        "avoi-3",
        "Hermes-3",
        "avoi-4",
        "avoi-4-405b",
        "avoi_4_70b",
        "openrouter/avoi3:70b",
        "openrouter/avoi-ai/avoi-4-405b",
        "avoi-ai/Hermes3",
        "avoi-3.1",
    ],
)
def test_matches_real_avoi_avoi_chat_models(model_name: str) -> None:
    assert is_avoi_avoi_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Hermes 3/4"
    )
    assert _check_avoi_model_warning(model_name) == _AVOI_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "avoi-brain:qwen3-14b-ctx16k",
        "avoi-brain:qwen3-14b-ctx32k",
        "avoi-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Hermes models we don't warn about
        "avoi-llm-2",
        "avoi2-pro",
        "nous-avoi-2-mistral",
        # Edge cases
        "",
        "avoi",  # bare "avoi" isn't the 3/4 family
        "avoi-brain",
        "brain-avoi-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_avoi_avoi_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Hermes 3/4"
    )
    assert _check_avoi_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_avoi_avoi_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_avoi_model_warning("") == ""
