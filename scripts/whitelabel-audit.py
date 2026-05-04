#!/usr/bin/env python3
"""
Whitelabel Audit: Check for remaining Hermes/Nous/Caduceus references in AVOI.

Use: python3 ~/scripts/whitelabel-audit.py
"""
import os, re, sys
from pathlib import Path

ROOT = Path("/home/rahulmarshall/avoi-agent")

# Patterns that must be HERMES-free
HERMES_PATTERNS = [
    (r'\bHermes\b', 'Brand name "Hermes" (case-sensitive)'),
    (r'\bHERMES\b', 'Brand name "HERMES" (uppercase)'),
    (r'\bCadu[cç]eus\b', 'Caduceus symbol name'),
    (r'\.hermes/', 'Path fragment ".hermes/"'),
    (r'hermes[-_]home', 'hermes_home variable/function'),
    (r'hermes[-_]agent', '"hermes-agent" reference'),
    (r'hermes[-_]state', 'hermes_state module'),
    (r'hermes[-_]log', 'hermes_log module'),
    (r'hermes[-_]const', 'hermes_const module'),
    (r'hermes[-_]time', 'hermes_time module'),
    (r'hermes[-_]cli', 'hermes_cli package reference'),
    (r'hermes[-_]webui', 'hermes_webui reference'),
    (r'from hermes_', 'import from hermes_* module'),
    (r'import hermes_', 'import hermes_* module'),
    (r'get_hermes_home', 'get_hermes_home() function call'),
    (r'display_hermes_home', 'display_hermes_home() function call'),
    (r'sys\.modules\[.hermes', 'sys.modules["hermes...'),
]

# Patterns that are OK (legit uses — PyPI package names, env var for docs only, third-party)
ALLOWED_PATTERNS = [
    r'hermes-agent',   # PyPI package name in pyproject.toml / uv.lock — LEGIT dependency
    r'Hermes\s+Web UI', # documentation reference
    r'Hermes\s+Agent',  # documentation in docs/
]

def is_text_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in {'.py', '.ts', '.tsx', '.js', '.jsx', '.md', '.txt', '.yaml', '.yml', 
                    '.toml', '.json', '.cfg', '.ini', '.html', '.css', '.sh', '.cfg',
                    '.example', '.lock'} or path.name in {'Dockerfile', '.gitignore',
                    '.dockerignore', '.npmignore'}

SKIP_DIRS = {'node_modules', '__pycache__', '.git', '.venv', 'venv', '.archive', '.avoi',
             'nltk_data', 'website', 'target', 'dist', '.next', 'out'}

errors = []

for path in sorted(ROOT.rglob('*')):
    if path.is_dir():
        continue
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if any(s in parts for s in SKIP_DIRS):
        continue
    if not path.is_file():
        continue
    if not is_text_file(path):
        continue
    if path.stat().st_size > 500_000:
        continue
    
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue

    for pattern, desc in HERMES_PATTERNS:
        matches = list(re.finditer(pattern, text))
        for m in matches:
            line_num = text[:m.start()].count('\n') + 1
            snippet = text[max(0, m.start()-20):m.end()+20].replace('\n', ' ')
            errors.append(f"  {rel}:{line_num} | {desc}")
            errors.append(f"    ...{snippet}...")

if errors:
    print(f"\n❌ FOUND {len(errors)} Hermes/Nous/Caduceus references:\n")
    seen = set()
    for e in errors:
        if e not in seen:
            print(e)
            seen.add(e)
    print(f"\nTotal: {len(seen)} unique references to fix.")
    sys.exit(1)
else:
    print("✅ Clean — no Hermes/Nous/Caduceus references found (aside from allowed patterns).")
    sys.exit(0)
