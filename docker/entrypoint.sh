#!/bin/bash
# Docker/Podman entrypoint: bootstrap config files into the mounted volume, then run avoi.
set -e

AVOI_HOME="${AVOI_HOME:-/opt/data}"
INSTALL_DIR="/opt/avoi"

# --- Privilege dropping via gosu ---
# When started as root (the default for Docker, or fakeroot in rootless Podman),
# optionally remap the avoi user/group to match host-side ownership, fix volume
# permissions, then re-exec as avoi.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$AVOI_UID" ] && [ "$AVOI_UID" != "$(id -u avoi)" ]; then
        echo "Changing avoi UID to $AVOI_UID"
        usermod -u "$AVOI_UID" avoi
    fi

    if [ -n "$AVOI_GID" ] && [ "$AVOI_GID" != "$(id -g avoi)" ]; then
        echo "Changing avoi GID to $AVOI_GID"
        # -o allows non-unique GID (e.g. macOS GID 20 "staff" may already exist
        # as "dialout" in the Debian-based container image)
        groupmod -o -g "$AVOI_GID" avoi 2>/dev/null || true
    fi

    # Fix ownership of the data volume. When AVOI_UID remaps the avoi user,
    # files created by previous runs (under the old UID) become inaccessible.
    # Always chown -R when UID was remapped; otherwise only if top-level is wrong.
    actual_avoi_uid=$(id -u avoi)
    needs_chown=false
    if [ -n "$AVOI_UID" ] && [ "$AVOI_UID" != "10000" ]; then
        needs_chown=true
    elif [ "$(stat -c %u "$AVOI_HOME" 2>/dev/null)" != "$actual_avoi_uid" ]; then
        needs_chown=true
    fi
    if [ "$needs_chown" = true ]; then
        echo "Fixing ownership of $AVOI_HOME to avoi ($actual_avoi_uid)"
        # In rootless Podman the container's "root" is mapped to an unprivileged
        # host UID — chown will fail.  That's fine: the volume is already owned
        # by the mapped user on the host side.
        chown -R avoi:avoi "$AVOI_HOME" 2>/dev/null || \
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
mkdir -p "$AVOI_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# .env
if [ ! -f "$AVOI_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$AVOI_HOME/.env"
fi

# config.yaml
if [ ! -f "$AVOI_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$AVOI_HOME/config.yaml"
fi

# Ensure the main config file remains accessible to the avoi runtime user
# even if it was edited on the host after initial ownership setup.
if [ -f "$AVOI_HOME/config.yaml" ]; then
    chown avoi:avoi "$AVOI_HOME/config.yaml"
    chmod 640 "$AVOI_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$AVOI_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$AVOI_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

# Final exec: two supported invocation patterns.
#
#   docker run <image>                 -> exec `avoi` with no args (legacy default)
#   docker run <image> chat -q "..."   -> exec `avoi chat -q "..."` (legacy wrap)
#   docker run <image> sleep infinity  -> exec `sleep infinity` directly
#   docker run <image> bash            -> exec `bash` directly
#
# If the first positional arg resolves to an executable on PATH, we assume the
# caller wants to run it directly (needed by the launcher which runs long-lived
# `sleep infinity` sandbox containers — see tools/environments/docker.py).
# Otherwise we treat the args as a avoi subcommand and wrap with `avoi`,
# preserving the documented `docker run <image> <subcommand>` behavior.
if [ $# -gt 0 ] && command -v "$1" >/dev/null 2>&1; then
    exec "$@"
fi
exec avoi "$@"
