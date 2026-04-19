#!/bin/bash
# Docker/Podman entrypoint: bootstrap config files into the mounted volume, then run avoi.
set -e

avoi_HOME="${avoi_HOME:-/opt/data}"
INSTALL_DIR="/opt/avoi"

# --- Privilege dropping via gosu ---
# When started as root (the default for Docker, or fakeroot in rootless Podman),
# optionally remap the avoi user/group to match host-side ownership, fix volume
# permissions, then re-exec as avoi.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$avoi_UID" ] && [ "$avoi_UID" != "$(id -u avoi)" ]; then
        echo "Changing avoi UID to $avoi_UID"
        usermod -u "$avoi_UID" avoi
    fi

    if [ -n "$avoi_GID" ] && [ "$avoi_GID" != "$(id -g avoi)" ]; then
        echo "Changing avoi GID to $avoi_GID"
        # -o allows non-unique GID (e.g. macOS GID 20 "staff" may already exist
        # as "dialout" in the Debian-based container image)
        groupmod -o -g "$avoi_GID" avoi 2>/dev/null || true
    fi

    actual_avoi_uid=$(id -u avoi)
    if [ "$(stat -c %u "$avoi_HOME" 2>/dev/null)" != "$actual_avoi_uid" ]; then
        echo "$avoi_HOME is not owned by $actual_avoi_uid, fixing"
        # In rootless Podman the container's "root" is mapped to an unprivileged
        # host UID — chown will fail.  That's fine: the volume is already owned
        # by the mapped user on the host side.
        chown -R avoi:avoi "$avoi_HOME" 2>/dev/null || \
            echo "Warning: chown failed (rootless container?) — continuing anyway"
    fi

    echo "Dropping root privileges"
    exec gosu avoi "$0" "$@"
fi

# --- Running as avoi from here ---
source "${INSTALL_DIR}/.venv/bin/activate"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_avoi_dir().
# The "home/" subdirectory is a per-profile HOME for subprocesses (git,
# ssh, gh, npm …).  Without it those tools write to /root which is
# ephemeral and shared across profiles.  See issue #4426.
mkdir -p "$avoi_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$avoi_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$avoi_HOME/.env"
fi

# config.yaml
if [ ! -f "$avoi_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$avoi_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$avoi_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$avoi_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec avoi "$@"
