"""Resolve AVOI_HOME for standalone skill scripts.

Skill scripts may run outside the Hermes process (e.g. system Python,
nix env, CI) where ``avoi_constants`` is not importable.  This module
provides the same ``get_avoi_home()`` and ``display_avoi_home()``
contracts as ``avoi_constants`` without requiring it on ``sys.path``.

When ``avoi_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``avoi_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``AVOI_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from avoi_constants import display_avoi_home as display_avoi_home
    from avoi_constants import get_avoi_home as get_avoi_home
except (ModuleNotFoundError, ImportError):

    def get_avoi_home() -> Path:
        """Return the Hermes home directory (default: ~/.avoi).

        Mirrors ``avoi_constants.get_avoi_home()``."""
        val = os.environ.get("AVOI_HOME", "").strip()
        return Path(val) if val else Path.home() / ".avoi"

    def display_avoi_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``avoi_constants.display_avoi_home()``."""
        home = get_avoi_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
