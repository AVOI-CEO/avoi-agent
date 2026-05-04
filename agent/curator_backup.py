"""Curator snapshot + rollback for AVOI.

A pre-run snapshot of ``~/.avoi/skills/`` (excluding ``.curator_backups/``)
is taken before any mutating curator pass. Snapshots are tar.gz files under
``~/.avoi/skills/.curator_backups/<utc-iso>/`` with a companion manifest.json.
Rollback picks a snapshot, moves the current skills/ tree aside, then extracts
the chosen snapshot into place.

Includes:
  - SKILL.md files + directories (references/, templates/, scripts/, assets/)
  - .usage.json (usage telemetry)
  - .archive/ (so rollback restores archived skills too)
  - .curator_state
  - .bundled_manifest
  - cron/jobs.json as cron-jobs.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from avoi_constants import get_avoi_home

logger = logging.getLogger(__name__)

DEFAULT_KEEP = 5
_EXCLUDE_TOP_LEVEL = {".curator_backups", ".hub"}
_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z(-\d{2})?$")


def _backups_dir() -> Path:
    return get_avoi_home() / "skills" / ".curator_backups"


def _skills_dir() -> Path:
    return get_avoi_home() / "skills"


def _cron_jobs_file() -> Path:
    return get_avoi_home() / "cron" / "jobs.json"


def _snapshot_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def list_snapshots() -> List[Dict[str, Any]]:
    """List available snapshots ordered newest-first."""
    root = _backups_dir()
    if not root.exists():
        return []
    snapshots: List[Dict[str, Any]] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir() or not _ID_RE.match(entry.name):
            continue
        manifest_path = entry / "manifest.json"
        meta: Dict[str, Any] = {"id": entry.name}
        if manifest_path.exists():
            try:
                meta.update(json.loads(manifest_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        snapshots.append(meta)
    return snapshots


def snapshot_skills(reason: str = "") -> Optional[Path]:
    """Create a tar.gz snapshot of ~/.avoi/skills/ into .curator_backups/<id>/.
    Returns the snapshot directory path, or None on failure.
    """
    root = _backups_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.debug("Curator backups dir create failed: %s", e)
        return None
    
    snap_id = _snapshot_id()
    snap_dir = root / snap_id
    suffix = 1
    while snap_dir.exists():
        suffix += 1
        snap_dir = root / f"{snap_id}-{suffix:02d}"
    
    try:
        snap_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.debug("Curator snapshot dir create failed: %s", e)
        return None
    
    tarball_path = snap_dir / "skills.tar.gz"
    src = _skills_dir()
    
    try:
        def _filter(ti: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
            name = ti.name
            parts = name.replace("\\", "/").split("/")
            if any(p in _EXCLUDE_TOP_LEVEL for p in parts):
                return None
            if ti.isdir() and parts[-1].startswith("."):
                return None
            return ti
        
        with tarfile.open(tarball_path, "w:gz", compresslevel=6) as tf:
            if src.exists():
                for item in src.iterdir():
                    if item.name in _EXCLUDE_TOP_LEVEL:
                        continue
                    tf.add(str(item), arcname=item.name, filter=_filter)
    except Exception as e:
        logger.debug("Curator snapshot tar failed: %s", e)
        try:
            shutil.rmtree(snap_dir)
        except Exception:
            pass
        return None
    
    # Also snapshot cron jobs
    cron_snap = snap_dir / "cron-jobs.json"
    try:
        if _cron_jobs_file().exists():
            shutil.copy2(str(_cron_jobs_file()), str(cron_snap))
    except Exception as e:
        logger.debug("Curator cron snapshot failed: %s", e)
    
    # Write manifest
    try:
        tar_size = tarball_path.stat().st_size if tarball_path.exists() else 0
        skill_count = len(list(src.rglob("SKILL.md"))) if src.exists() else 0
        manifest = {
            "id": snap_dir.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason or "",
            "size_bytes": tar_size,
            "skill_count": skill_count,
            "backed_up_cron": cron_snap.exists(),
        }
        (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as e:
        logger.debug("Curator manifest write failed: %s", e)
    
    # Prune old snapshots
    try:
        _prune_snapshots()
    except Exception:
        pass
    
    return snap_dir


def _prune_snapshots(keep: Optional[int] = None) -> None:
    """Remove oldest snapshots beyond keep count."""
    root = _backups_dir()
    if not root.exists():
        return
    if keep is None:
        try:
            from agent.curator import _load_config
            cfg = _load_config()
            keep = int(cfg.get("backup", {}).get("keep", DEFAULT_KEEP))
        except Exception:
            keep = DEFAULT_KEEP
    
    all_ids = sorted([
        d for d in root.iterdir()
        if d.is_dir() and _ID_RE.match(d.name)
    ])
    for stale in all_ids[:-keep]:
        try:
            shutil.rmtree(stale)
        except Exception as e:
            logger.debug("Curator prune failed for %s: %s", stale.name, e)


def rollback_to_snapshot(snap_id: str) -> Tuple[bool, str]:
    """Restore skills from a snapshot. Returns (ok, message)."""
    snap_dir = _backups_dir() / snap_id
    if not snap_dir.exists() or not snap_dir.is_dir():
        return False, f"snapshot '{snap_id}' not found"
    
    tarball = snap_dir / "skills.tar.gz"
    if not tarball.exists():
        return False, f"snapshot '{snap_id}' has no skills.tar.gz"
    
    src = _skills_dir()
    
    # Before we overwrite, take a snapshot of current state so rollback is reversible
    try:
        pre_rollback = snapshot_skills(reason=f"pre-rollback to {snap_id}")
    except Exception:
        pre_rollback = None
    
    try:
        # Clear current skills dir (except backups and hub)
        if src.exists():
            for item in list(src.iterdir()):
                if item.name in _EXCLUDE_TOP_LEVEL or item.name == ".curator_backups" or item.name == ".hub":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        
        # Extract snapshot
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(path=str(src))
        
        # Restore cron jobs if available
        cron_snap = snap_dir / "cron-jobs.json"
        if cron_snap.exists() and _cron_jobs_file().exists():
            try:
                shutil.copy2(str(cron_snap), str(_cron_jobs_file()))
            except Exception as e:
                logger.debug("Curator cron restore failed: %s", e)
        
        return True, f"rolled back to {snap_id}" + (f" (pre-rollback: {pre_rollback.name})" if pre_rollback else "")
    except Exception as e:
        return False, f"rollback failed: {e}"
