#!/usr/bin/env bash
# breadcrumb-audit.sh — Search for any remaining Hermes/Nous/OpenClaw references
set -uo pipefail

FOUND=0
PATTERNS=("hermes" "HERMES" "nousresearch" "NousResearch" "openclaw" "OpenClaw" "clawdbot" "Clawdbot" "moldbot" "NOUS_")
EXTENSIONS=("*.py" "*.md" "*.yaml" "*.yml" "*.json" "*.sh" "*.toml" "*.txt" "*.html" "*.css" "*.ts" "*.js" "*.rb" "*.svg" "*.cfg" "*.ini")

for pattern in "${PATTERNS[@]}"; do
    hits=$(grep -rl "${pattern}" . \
        --include='*.py' --include='*.md' --include='*.yaml' --include='*.yml' \
        --include='*.json' --include='*.sh' --include='*.toml' --include='*.txt' \
        --include='*.html' --include='*.css' --include='*.ts' --include='*.js' \
        --include='*.rb' --include='*.svg' --include='*.cfg' --include='*.ini' \
        --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=venv 2>/dev/null || true)
    if [ -n "$hits" ]; then
        echo "FOUND '$pattern' in:"
        echo "$hits"
        echo ""
        FOUND=1
    fi
done

if [ "$FOUND" -eq 1 ]; then
    echo "BREADCRUMBS FOUND — manual cleanup required"
    exit 1
else
    echo "CLEAN — no breadcrumbs found"
    exit 0
fi
