"""
Automated rebranding script.
Replaces user-facing strings with AVOI branding.
Only touches:
  - CLI display strings
  - Banner text
  - Documentation references
  - Setup wizard text
"""

import os
import re

# Only rebrand these file patterns (user-facing text)
TARGET_PATTERNS = [
    "**/*.md",
    "**/cli.py",
    "**/display.py",
    "**/skin_engine.py",
]

# String replacements (display text only, not code identifiers)
# Maps old product names/refs to AVOI equivalents
REPLACEMENTS = {
    "AVOI Agent": "AVOI Agent",
    "AVOI agent": "AVOI agent",
    "AVOI agent": "AVOI agent",
    "Built by AVOI AI": "Built by AVOI AI",
    "AVOI AI": "AVOI AI",
    "docs.avoi.in": "docs.avoi.in",
    "AVOI-CEO": "avoi-ai",
}

# Files to NEVER touch
SKIP_PATTERNS = [
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    "avoi/",
]

def should_skip(filepath: str) -> bool:
    return any(skip in filepath for skip in SKIP_PATTERNS)

def rebrand_file(filepath: str) -> int:
    """Rebrand a single file. Returns number of replacements made."""
    if should_skip(filepath):
        return 0

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IsADirectoryError):
        return 0

    original = content
    for old, new in REPLACEMENTS.items():
        content = content.replace(old, new)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        count = sum(content.count(new) - original.count(new) for old, new in REPLACEMENTS.items())
        return max(count, 1)
    return 0

def main():
    """Walk the project and rebrand user-facing strings."""
    import glob

    total = 0
    for pattern in TARGET_PATTERNS:
        for filepath in glob.glob(pattern, recursive=True):
            count = rebrand_file(filepath)
            if count:
                print(f"  Rebranded: {filepath} ({count} replacements)")
                total += count

    print(f"\nTotal replacements: {total}")

if __name__ == "__main__":
    main()
