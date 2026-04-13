#!/usr/bin/env bash
# backup.sh — Create dated tarball backup + git tag
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

cd "$PROJECT_ROOT"

mkdir -p "$BACKUP_DIR"

TAG="backup/$TIMESTAMP"
git tag "$TAG"

OUTPUT="$BACKUP_DIR/avoi-agent-$TIMESTAMP.tar.gz"
git archive --format=tar.gz --prefix="avoi-agent-$(date +%Y%m%d)/" -o "$OUTPUT" HEAD

echo "Backup created:"
echo "  Tag:    $TAG"
echo "  File:   $OUTPUT"
echo "  Size:   $(du -h "$OUTPUT" | cut -f1)"
