#!/usr/bin/env bash
# ingest-hermes-update.sh — Pull updates from Hermes, clean references, merge into AVOI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_POINT="$PROJECT_ROOT/.hermes-sync-point"
UPSTREAM="hermes-upstream"
BRANCH="main"

cd "$PROJECT_ROOT"

if ! git remote get-url "$UPSTREAM" &>/dev/null; then
    echo "ERROR: Remote '$UPSTREAM' not found."
    echo "Add it with: git remote add hermes-upstream https://github.com/nousresearch/hermes-agent.git"
    exit 1
fi

echo "=== AVOI Hermes Update Ingestion ==="
echo ""

# 1. Fetch latest Hermes
echo "[1/7] Fetching latest from $UPSTREAM..."
git fetch "$UPSTREAM" 2>/dev/null

# 2. Get sync point
HEAD_COMMIT=$(git rev-parse "$UPSTREAM/$BRANCH")
LAST_SYNC=$(cat "$SYNC_POINT" 2>/dev/null || echo "")

if [ "$LAST_SYNC" = "$HEAD_COMMIT" ]; then
    echo "Already up to date (sync point: ${HEAD_COMMIT:0:8})"
    exit 0
fi

echo "Last sync: ${LAST_SYNC:0:8:-${#LAST_SYNC}+8}"
echo "New head:   ${HEAD_COMMIT:0:8}"
echo ""

# 3. Show diff stats
echo "[2/7] Changes since last sync:"
if [ -n "$LAST_SYNC" ]; then
    git log --oneline "${LAST_SYNC}..${HEAD_COMMIT}" 2>/dev/null || echo "(unable to show log)"
else
    git log --oneline -10 "${HEAD_COMMIT}" 2>/dev/null || echo "(unable to show log)"
fi
echo ""

# 4. Create temp branch
TEMP_BRANCH="hermes-sync/$(date +%Y%m%d-%H%M%S)"
echo "[3/7] Creating temp branch: $TEMP_BRANCH"
git checkout -b "$TEMP_BRANCH" 2>/dev/null || {
    echo "ERROR: Could not create branch. Stash or commit your changes first."
    exit 1
}

# 5. Merge Hermes main
echo "[4/7] Merging $UPSTREAM/$BRANCH..."
if ! git merge "$UPSTREAM/$BRANCH" --no-edit; then
    echo ""
    echo "CONFLICTS DETECTED — resolve manually:"
    echo "  1. Fix conflicts listed above"
    echo "  2. git add -A && git commit"
    echo "  3. Continue with step 5 below"
    echo ""
    echo "After resolving conflicts, run the cleanup:"
    echo "  bash scripts/ingest-hermes-update.sh --clean-only"
    exit 1
fi

# 6. Automated find-replace cleanup
echo "[5/7] Running automated reference cleanup..."

# File/directory renames
find . -name 'hermes*' -not -path './.git/*' -not -path '*/node_modules/*' | while read -r f; do
    newname=$(echo "$f" | sed 's/hermes/avoi/g; s/Hermes/Avoi/g')
    if [ "$f" != "$newname" ]; then
        git mv "$f" "$newname" 2>/dev/null || true
    fi
done

find . -name 'hermes_cli' -not -path './.git/*' -type d | while read -r f; do
    git mv "$f" "$(dirname "$f")/avoi_cli" 2>/dev/null || true
done

# Content replacements across all text files
grep -rl --include='*.py' --include='*.md' --include='*.yaml' --include='*.yml' \
    --include='*.json' --include='*.sh' --include='*.toml' --include='*.txt' \
    --include='*.html' --include='*.css' --include='*.ts' --include='*.js' \
    --include='*.rb' --include='*.svg' --include='*.cfg' --include='*.ini' \
    -i 'hermes' . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=venv 2>/dev/null | \
    while read -r f; do
        sed -i \
            -e 's/hermes/avoi/gI' \
            -e 's/HERMES/AVOI/g' \
            -e 's/nousresearch/AVOI-CEO/g' \
            -e 's/NousResearch/AVOI/g' \
            -e 's/nous_/avoi_/g' \
            -e 's/NOUS_/AVOI_/g' \
            -e 's/\.hermes/\.avoi/g' \
            "$f" 2>/dev/null || true
    done

echo "Cleanup complete."
echo ""

# 7. Run breadcrumb audit
echo "[6/7] Running breadcrumb audit..."
if bash "$SCRIPT_DIR/breadcrumb-audit.sh"; then
    echo "AUDIT PASSED — no breadcrumbs found."
else
    echo "AUDIT FAILED — breadcrumbs found. Fix manually before proceeding."
    echo "Run: bash scripts/breadcrumb-audit.sh"
    exit 1
fi
echo ""

# 8. Update sync point and commit
echo "${HEAD_COMMIT}" > "$SYNC_POINT"
git add -A
git commit -m "Ingest Hermes update $(date +%Y-%m-%d) — auto-cleaned references" || true

echo ""
echo "=== DONE ==="
echo "Branch: $TEMP_BRANCH"
echo "Sync point: ${HEAD_COMMIT:0:8}"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff main..$TEMP_BRANCH"
echo "  2. If good, merge: git checkout main && git merge $TEMP_BRANCH"
echo "  3. If bad, abort:  git checkout main && git branch -D $TEMP_BRANCH"
