#!/bin/bash
# Docker entrypoint: bootstrap config files into the mounted volume, then run avoi.
set -e

AVOI_HOME="/opt/data"
INSTALL_DIR="/opt/avoi"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_avoi_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$AVOI_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$AVOI_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$AVOI_HOME/.env"
fi

# config.yaml
if [ ! -f "$AVOI_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$AVOI_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$AVOI_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$AVOI_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec avoi "$@"
