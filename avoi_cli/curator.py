"""CLI subcommand: `avoi curator <subcommand>`.

Thin shell around agent/curator.py and tools/skill_usage.py.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Optional


def _fmt_ts(ts: Optional[str]) -> str:
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return str(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _cmd_status(args) -> int:
    from agent import curator
    from tools import skill_usage
    
    state = curator.load_state()
    enabled = curator.is_enabled()
    paused = state.get("paused", False)
    last_run = state.get("last_run_at")
    summary = state.get("last_run_summary") or "(none)"
    runs = state.get("run_count", 0)
    
    status_line = "ENABLED" if enabled and not paused else "PAUSED" if paused else "DISABLED"
    print(f"curator: {status_line}")
    print(f"  runs:           {runs}")
    print(f"  last run:       {_fmt_ts(last_run)}")
    print(f"  last summary:   {summary}")
    _report = state.get("last_report_path")
    if _report:
        print(f"  last report:    {_report}")
    _ih = curator.get_interval_hours()
    _interval_label = f"{_ih // 24}d" if _ih % 24 == 0 and _ih >= 24 else f"{_ih}h"
    print(f"  interval:       every {_interval_label}")
    print(f"  stale after:    {curator.get_stale_after_days()}d unused")
    print(f"  archive after:  {curator.get_archive_after_days()}d unused")
    
    rows = skill_usage.agent_created_report()
    if not rows:
        print("\nno agent-created skills")
        return 0
    
    by_state = {"active": [], "stale": [], "archived": []}
    pinned = []
    for r in rows:
        s = r.get("state", "active")
        by_state.setdefault(s, []).append(r)
        if r.get("pinned"):
            pinned.append(r["name"])
    
    print(f"\nagent-created skills: {len(rows)} total")
    for s in ("active", "stale", "archived"):
        bucket = by_state.get(s, [])
        print(f"  {s:10s} {len(bucket)}")
    
    if pinned:
        print(f"\npinned ({len(pinned)}): {', '.join(pinned)}")
    
    active = sorted(by_state.get("active", []), key=lambda r: r.get("last_activity_at") or r.get("created_at") or "")[:5]
    if active:
        print("\nleast recently active (top 5):")
        for r in active:
            print(f"  {r['name']:30s} last activity: {r.get('last_activity_at') or 'never'}")
    
    return 0


def _cmd_run(args) -> int:
    from agent import curator
    synchronous = getattr(args, "sync", False)
    dry_run = getattr(args, "dry_run", False)
    
    if dry_run:
        print("curator: DRY-RUN — no changes will be made")
    else:
        print("curator: starting review pass..." if not synchronous else "curator: starting review (synchronous)...")
    
    def _on_progress(msg: str):
        if not synchronous:
            print(f"  {msg}")
    
    result = curator.run_curator_review(on_summary=_on_progress, synchronous=synchronous, dry_run=dry_run)
    
    auto = result.get("auto_transitions", {})
    print(f"\ncurator: started at {result['started_at']}")
    print(f"  auto: checked {auto.get('checked', 0)}, "
          f"stale {auto.get('marked_stale', 0)}, "
          f"archived {auto.get('archived', 0)}, "
          f"reactivated {auto.get('reactivated', 0)}")
    
    if dry_run:
        state = curator.load_state()
        _rpt = state.get("last_report_path")
        if _rpt:
            print(f"\n  report: {_rpt}")
    
    if not synchronous:
        print("\n  LLM review running in background (use `avoi curator status` to check)")
    return 0


def _cmd_pause(args) -> int:
    from agent import curator
    curator.set_paused(True)
    print("curator: paused")
    return 0


def _cmd_resume(args) -> int:
    from agent import curator
    curator.set_paused(False)
    print("curator: resumed")
    return 0


def _cmd_pin(args) -> int:
    from tools import skill_usage
    name = args.skill
    skill_usage.set_pinned(name, True)
    print(f"curator: pinned '{name}'")
    return 0


def _cmd_unpin(args) -> int:
    from tools import skill_usage
    name = args.skill
    skill_usage.set_pinned(name, False)
    print(f"curator: unpinned '{name}'")
    return 0


def _cmd_backup(args) -> int:
    from agent import curator_backup as bkp
    reason = getattr(args, "reason", "") or ""
    snap = bkp.snapshot_skills(reason=reason)
    if snap:
        print(f"curator: snapshot created at {snap}")
    else:
        print("curator: snapshot failed", file=sys.stderr)
        return 1
    return 0


def _cmd_rollback(args) -> int:
    from agent import curator_backup as bkp
    
    if getattr(args, "list_snapshots", False):
        snapshots = bkp.list_snapshots()
        if not snapshots:
            print("curator: no snapshots available")
            return 0
        print("curator: available snapshots:")
        for s in snapshots:
            reason = s.get("reason", "")
            ts = s.get("created_at", s["id"])[:19]
            sz = s.get("size_bytes", 0)
            sz_str = f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / 1024 / 1024:.1f} MB"
            print(f"  {s['id']:30s}  {ts}  {sz_str:>8s}  {reason}")
        return 0
    
    snap_id = getattr(args, "snapshot_id", None) or ""
    if not snap_id:
        # Find newest
        snapshots = bkp.list_snapshots()
        if not snapshots:
            print("curator: no snapshots to roll back to", file=sys.stderr)
            return 1
        snap_id = snapshots[0]["id"]
    
    ok, msg = bkp.rollback_to_snapshot(snap_id)
    if ok:
        print(f"curator: {msg}")
    else:
        print(f"curator: {msg}", file=sys.stderr)
        return 1
    return 0


def _cmd_restore(args) -> int:
    from tools import skill_usage
    name = args.skill
    ok, msg = skill_usage.restore_skill(name)
    if ok:
        print(f"curator: restored '{name}' — {msg}")
    else:
        print(f"curator: {msg}", file=sys.stderr)
        return 1
    return 0


def register_subparser(subparsers) -> None:
    p = subparsers.add_parser("curator", help="Background skill library maintenance")
    sp = p.add_subparsers(dest="curator_command", metavar="<subcommand>")
    sp.required = True
    
    p_status = sp.add_parser("status", help="Show curator status and skill library overview")
    p_status.set_defaults(func=_cmd_status)
    
    p_run = sp.add_parser("run", help="Run a curator review pass")
    p_run.add_argument("--sync", action="store_true", help="Run synchronously (block until done)")
    p_run.add_argument("--dry-run", action="store_true", help="Preview only — no mutations")
    p_run.set_defaults(func=_cmd_run)
    
    sp.add_parser("pause", help="Pause automatic curator runs").set_defaults(func=_cmd_pause)
    sp.add_parser("resume", help="Resume automatic curator runs").set_defaults(func=_cmd_resume)
    
    p_pin = sp.add_parser("pin", help="Prevent a skill from auto-transitioning")
    p_pin.add_argument("skill", help="Skill name to pin")
    p_pin.set_defaults(func=_cmd_pin)
    
    p_unpin = sp.add_parser("unpin", help="Allow auto-transitions for a pinned skill")
    p_unpin.add_argument("skill", help="Skill name to unpin")
    p_unpin.set_defaults(func=_cmd_unpin)
    
    p_backup = sp.add_parser("backup", help="Take a manual snapshot of the skill library")
    p_backup.add_argument("--reason", default="", help="Optional reason for the snapshot")
    p_backup.set_defaults(func=_cmd_backup)
    
    p_rollback = sp.add_parser("rollback", help="Restore skills from a snapshot")
    p_rollback.add_argument("--list", dest="list_snapshots", action="store_true", help="List available snapshots")
    p_rollback.add_argument("--id", dest="snapshot_id", default="", help="Snapshot ID (default: newest)")
    p_rollback.add_argument("-y", action="store_true", dest="yes", help="Skip confirmation")
    p_rollback.set_defaults(func=_cmd_rollback)
    
    p_restore = sp.add_parser("restore", help="Restore an archived skill")
    p_restore.add_argument("skill", help="Skill name to restore")
    p_restore.set_defaults(func=_cmd_restore)


# ---------------------------------------------------------------------------
# Slash command runner (for gateway + TUI integration)
# ---------------------------------------------------------------------------

def run_slash(args_str: str = "") -> str:
    """Run a curator subcommand from a slash command and return output."""
    import io
    from contextlib import redirect_stdout
    
    parser = argparse.ArgumentParser(prog="/curator")
    sp = parser.add_subparsers(dest="curator_command")
    register_subparser(sp)
    
    parsed = parser.parse_args(args_str.split() if args_str else ["status"])
    
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = parsed.func(parsed)
        output = buf.getvalue()
        if rc != 0:
            return f"curator error:\n{output}"
        return output
    except Exception as e:
        return f"curator error: {e}"
