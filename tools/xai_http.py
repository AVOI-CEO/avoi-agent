"""Shared helpers for direct xAI HTTP integrations."""

from __future__ import annotations


def avoi_xai_user_agent() -> str:
    """Return a stable Hermes-specific User-Agent for xAI HTTP calls."""
    try:
        from avoi_cli import __version__
    except Exception:
        __version__ = "unknown"
    return f"AVOIAgent/{__version__}"
