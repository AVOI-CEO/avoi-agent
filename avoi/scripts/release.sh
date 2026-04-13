#!/bin/bash
# AVOI Release Script
# Creates a tagged release on the avoi/main branch

set -e

VERSION=$1
if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh v0.1.0"
    exit 1
fi

echo "Creating AVOI release $VERSION..."

# Ensure we're on avoi/dev
git checkout avoi/dev

# Run tests
echo "Running tests..."
python -m pytest tests/ -q
python -m pytest avoi/tests/ -q

# Merge to avoi/main
git checkout avoi/main
git merge avoi/dev --no-ff -m "Release $VERSION"

# Tag
git tag -a "$VERSION" -m "AVOI $VERSION"

# Push
git push origin avoi/main
git push origin "$VERSION"

# Back to dev
git checkout avoi/dev

echo ""
echo "✓ Released AVOI $VERSION"
echo "  Clients can update with: cd ~/avoi-agent && git pull"
