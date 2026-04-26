#!/usr/bin/env python3
"""
Full whitelabel rebrand: Hermes/Nous -> AVOI/Avoi/avoi

This script handles ALL occurrences including:
  - Imports (from hermes_xxx import ...)
  - Internal variable/class names (HermesCLI, hermes_xxx)
  - Constants (HERMES_HOME, get_hermes_home())
  - File references (~/.hermes/, .hermes/, hermes/)
  - User-facing display strings
  - Env vars (HERMES_xxx)
  - URLs pointing to NousResearch or hermes-agent
  - Package metadata

SKIPS: venv/, node_modules/, .git/, __pycache__/, .egg-info/
"""

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Files/dirs to skip entirely ─────────────────────────────────────
SKIP_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "node_modules",
    ".egg-info", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache",
}

# ── Rename mapping for imports and internal identifiers ─────────────
# hermes_XXX -> avoi_XXX for core modules
IMPORT_RENAMES = {
    "hermes_constants": "avoi_constants",
    "hermes_logging": "avoi_logging",
    "hermes_state": "avoi_state",
    "hermes_time": "avoi_time",
    "hermes_cli": "avoi_cli",
}

# ── String replacements for user-facing text ────────────────────────
DISPLAY_REPLACEMENTS = {
    # Product names
    "Hermes Agent": "AVOI Agent",
    "hermes agent": "avoi agent",
    "Hermes agent": "avoi agent",
    "Hermes Agent\\": "AVOI Agent\\",
    "HERMES Agent": "AVOI Agent",
    "hermes-agent": "avoi-agent",
    "the agent that grows with you": "the agent that grows with you",
    
    # Organization refs
    "Built by Nous Research": "Built by AVOI AI",
    "Nous Research": "AVOI AI",
    "NousResearch": "avoi-ai",
    "nousresearch": "avoi-ai",
    "nous_research": "avoi_ai",
    "nous.": "avoi.",
    "nous_": "avoi_",
    
    # URLs
    "hermes-agent.nousresearch.com": "avoi.ai",
    "hermes-agent.nousresearch": "avoi.ai",
    "github.com/NousResearch/hermes-agent": "github.com/AVOI-CEO/avoi-agent",
    "nousresearch.com": "avoi.ai",
    "nousresearch": "avoi-ai",
    
    # CLI identity
    "'hermes'": "'avoi'",
    '"hermes"': '"avoi"',
    "hermes_": "avoi_",
    "HERMES_": "AVOI_",
    "`hermes`": "`avoi`",
    "hermes ": "avoi ",
    "hermes.": "avoi.",
    "/hermes": "/avoi",
    "hermes/": "avoi/",
    
    # Internal paths
    ".hermes/": ".avoi/",
    "~/.hermes": "~/.avoi",
    "HERMES_HOME": "AVOI_HOME",
    "hermes_home": "avoi_home",
    
    # Config keys
    "hermes": "avoi",
    
    # Version display
    "hermes Agent": "avoi Agent",
    "Hermes agent": "AVOI agent",
}

# ── File patterns to process ────────────────────────────────────────
PROCESS_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json", ".toml",
                      ".cfg", ".ini", ".sh", ".ps1", ".txt", ".html",
                      ".css", ".js", ".ts", ".tsx", ".jsx"}

def should_skip(filepath: Path) -> bool:
    """Check if a file should be skipped."""
    for part in filepath.parts:
        if part in SKIP_DIRS:
            return True
    # Skip files in copied docs/ dir from upstream (we have avoi/docs/)
    if "website/" in str(filepath) or "/web/" in str(filepath):
        return True
    # Skip the rebrand scripts themselves
    if "avoi/scripts/rebrand" in str(filepath):
        return True
    return False

def count_replacements(content: str, replacements: dict) -> dict:
    """Count how many replacements would be made (for reporting)."""
    counts = {}
    for old, new in replacements.items():
        count = content.count(old)
        if count > 0:
            counts[old] = count
    return counts

def apply_replacements(content: str, replacements: dict) -> str:
    """Apply all replacements to content text."""
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content

def rebrand_file(filepath: Path) -> tuple[int, dict]:
    """
    Rebrand a single file. Returns (replacements_made, details_dict).
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return 0, {}

    original = content
    details = {}
    
    # Apply import renames first (more targeted)
    for old_name, new_name in IMPORT_RENAMES.items():
        # Handle "from hermes_xxx import" -> "from avoi_xxx import"
        content = content.replace(f"from {old_name} ", f"from {new_name} ")
        content = content.replace(f"import {old_name}", f"import {new_name}")
        # Handle module references in strings
        content = content.replace(old_name, new_name)
    
    # Apply display replacements
    content = apply_replacements(content, DISPLAY_REPLACEMENTS)
    
    if content == original:
        return 0, {}
    
    # Count what changed
    for old, new in {**IMPORT_RENAMES, **DISPLAY_REPLACEMENTS}.items():
        # Can't count precisely after transformations, do approximate
        pass
    
    total_changed = sum(1 for old, new in {**IMPORT_RENAMES, **DISPLAY_REPLACEMENTS}.items() 
                        if content.count(new) > original.count(new) or content.count(old) < original.count(old))
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"  ERROR writing {filepath}: {e}")
        return 0, {}
    
    return max(total_changed, 1), {"old_size": len(original), "new_size": len(content)}


def main():
    print("=" * 60)
    print("AVOI Full Rebrand — Hermes/Nous -> AVOI")
    print(f"Root: {REPO_ROOT}")
    print("=" * 60)
    
    total_files = 0
    total_replacements = 0
    extensions = PROCESS_EXTENSIONS
    
    for ext in [".py", ".md", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".sh", ".ps1"]:
        for filepath in sorted(REPO_ROOT.rglob(f"*{ext}")):
            if should_skip(filepath):
                continue
            count, details = rebrand_file(filepath)
            if count > 0:
                total_files += 1
                total_replacements += count
                old_size = details.get("old_size", 0)
                new_size = details.get("new_size", 0)
                delta = new_size - old_size
                print(f"  [{count:3d} changes] {filepath.relative_to(REPO_ROOT)}")
    
    print()
    print("=" * 60)
    print(f"Total files modified: {total_files}")
    print(f"Total replacements:  {total_replacements}")
    print("=" * 60)
    
    # Final verification
    print("\n=== Verification: Remaining 'hermes'/'nous' references ===")
    remaining_hermes = 0
    remaining_nous = 0
    for ext in [".py", ".md", ".yaml", ".yml", ".json", ".toml"]:
        for filepath in REPO_ROOT.rglob(f"*{ext}"):
            if should_skip(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                hermes_count = content.count("hermes") + content.count("Hermes") + content.count("HERMES")
                nous_count = content.count("nous") + content.count("Nous") + content.count("NOUS")
                if hermes_count > 0:
                    remaining_hermes += 1
                    if hermes_count < 5:
                        for i, line in enumerate(content.split("\n"), 1):
                            if "hermes" in line.lower():
                                print(f"  {filepath.relative_to(REPO_ROOT)}:{i}: {line.strip()[:120]}")
                if nous_count > 0:
                    remaining_nous += 1
                    if nous_count < 5:
                        for i, line in enumerate(content.split("\n"), 1):
                            if "nous" in line.lower():
                                print(f"  {filepath.relative_to(REPO_ROOT)}:{i}: {line.strip()[:120]}")
            except Exception:
                pass
    
    print(f"\nFiles still with 'hermes': {remaining_hermes}")
    print(f"Files still with 'nous': {remaining_nous}")
    
    if remaining_hermes == 0 and remaining_nous == 0:
        print("\n✨ WHITELABEL COMPLETE — no remaining Hermes/Nous references!")
    else:
        print(f"\n⚠️  {remaining_hermes + remaining_nous} files still need attention above.")
    
    return 0 if (remaining_hermes == 0 and remaining_nous == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
