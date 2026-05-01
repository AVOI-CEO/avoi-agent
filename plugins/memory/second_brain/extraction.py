"""
extraction.py — Background memory extraction from conversations.

After each turn, a lightweight LLM call extracts 0-3 structured memory
candidates from the (user_message, assistant_response) pair. These are
fed to UserMemoryStore.remember() for merge/conflict/persistence.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trivial message detection — skip greetings, okays, etc.
# ---------------------------------------------------------------------------

_TRIVIAL_PATTERNS = (
    r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|bye|goodbye|"
    r"good morning|good evening|good night|lol|haha|nice|great|awesome"
    r")\b"
)

import re

_TRIVIAL_RE = re.compile(_TRIVIAL_PATTERNS, re.IGNORECASE)

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """You extract structured memory from conversations. Read the conversation and output a JSON array of memory candidates. Each candidate has:
- type: one of "identity", "preference", "goal", "project", "habit", "decision", "constraint", "relationship", "episode"
- summary: concise fact, 12-220 chars
- detail: optional longer explanation (omit if not needed)
- evidenceKind: "direct" for explicitly stated facts, "inferred" for patterns you notice
- confidence: 0.0-1.0
- importance: 0.0-1.0
- durability: 0.0-1.0

Extract 0-3 candidates. Only extract specific, durable, user-specific information about the USER. Do NOT extract trivial observations, greetings, or assistant behavior. Output pure JSON array, no markdown."""

VALID_TYPES = frozenset({
    "identity", "preference", "goal", "project", "habit",
    "decision", "constraint", "relationship", "episode",
})


# ---------------------------------------------------------------------------
# extract_memory — call this on a background thread
# ---------------------------------------------------------------------------

def extract_memory(
    user_message: str,
    agent_response: str,
    *,
    llm_call_fn: Callable[..., str],
    remember_fn: Callable[[List[Dict[str, Any]], str], None],
    is_learning_paused_fn: Callable[[], bool],
    token_budget_check_fn: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Extract memory candidates from a turn and store them.

    Designed to run on a background thread (fire-and-forget).

    Args:
        user_message: The user's message.
        agent_response: The agent's response.
        llm_call_fn: Function that takes (system_prompt, user_content) and returns text.
        remember_fn: Function to persist candidates (UserMemoryStore.remember).
        is_learning_paused_fn: Check if learning is paused.
        token_budget_check_fn: Optional budget check (return False to skip).
    """
    # Skip trivial messages
    if _TRIVIAL_RE.match(user_message.strip()):
        return

    if is_learning_paused_fn():
        return

    if token_budget_check_fn and not token_budget_check_fn():
        return

    try:
        result = llm_call_fn(
            _EXTRACTION_SYSTEM_PROMPT,
            f"User: {user_message}\nAssistant: {agent_response}",
        )
    except Exception as e:
        logger.debug("Memory extraction LLM call failed (non-fatal): %s", e)
        return

    if not result or not result.strip():
        return

    candidates = _parse_extraction_result(result)
    if not candidates:
        return

    # Filter and normalize
    typed = []
    for c in candidates:
        summary = c.get("summary", "").strip()
        if len(summary) < 12 or len(summary) > 220:
            continue
        if c.get("type") not in VALID_TYPES:
            continue
        typed.append({
            "type": c["type"],
            "summary": summary,
            "detail": c.get("detail", "").strip() or None,
            "evidenceKind": "direct" if c.get("evidenceKind") == "direct" else "inferred",
            "confidence": max(0, min(1, c.get("confidence", 0.7))),
            "importance": max(0, min(1, c.get("importance", 0.7))),
            "durability": max(0, min(1, c.get("durability", 0.7))),
        })

    if typed:
        try:
            remembered = remember_fn(typed, "conversation")
            if remembered:
                logger.info(
                    "Second brain stored %d memories: %s",
                    len(remembered),
                    [r["type"] for r in remembered],
                )
        except Exception as e:
            logger.debug("Second brain remember failed (non-fatal): %s", e)


def extract_memory_background(
    user_message: str,
    agent_response: str,
    *,
    llm_call_fn: Callable[..., str],
    remember_fn: Callable[[List[Dict[str, Any]], str], None],
    is_learning_paused_fn: Callable[[], bool],
    token_budget_check_fn: Optional[Callable[[], bool]] = None,
) -> threading.Thread:
    """Fire extraction on a daemon thread. Returns the thread handle."""
    t = threading.Thread(
        target=extract_memory,
        kwargs={
            "user_message": user_message,
            "agent_response": agent_response,
            "llm_call_fn": llm_call_fn,
            "remember_fn": remember_fn,
            "is_learning_paused_fn": is_learning_paused_fn,
            "token_budget_check_fn": token_budget_check_fn,
        },
        daemon=True,
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_extraction_result(text: str) -> List[Dict[str, Any]]:
    """Parse the LLM output into a list of candidate dicts."""
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        pass

    # Fallback: line-by-line fact extraction
    facts = []
    for line in text.split("\n"):
        line = re.sub(r"^-\s*", "", line).strip()
        if 12 < len(line) < 200:
            facts.append(line)
    return [
        {
            "type": "preference",
            "summary": f,
            "confidence": 0.75,
            "importance": 0.7,
            "durability": 0.7,
            "evidenceKind": "inferred",
        }
        for f in facts[:3]
    ]
