# AVOI Upgrade Guide

## Updating AVOI

When new versions are released:

```bash
cd ~/avoi-agent
git pull origin avoi/main
pip install -e ".[all]"
```

## For Maintainers

### Syncing and releasing

```bash
# Get latest changes
git checkout avoi/dev
git merge origin/main

# Re-run rebranding if any strings need updating
python3 avoi/scripts/rebrand.py

# Test
python3 -m pytest avoi/tests/ -q

# Commit and push
git push origin avoi/dev
```

### Releasing a version

```bash
python3 avoi/scripts/release.py v0.X.Y
```

This merges `avoi/dev` into `avoi/main`, tags the release, and pushes.
