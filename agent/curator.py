"""
AVOI Curator — background skill maintenance orchestrator.

The curator is an auxiliary-model task that periodically reviews agent-created
skills and maintains the collection. It runs inactivity-triggered (no cron
daemon): when the agent is idle and the last curator run was longer than
``interval_hours`` ago, ``maybe_run_curator()`` spawns a forked AIAgent to do
the review.

Responsibilities:
  - Auto-transition lifecycle states based on derived skill activity timestamps
  - Spawn a background review agent that can pin / archive / consolidate /
    patch agent-created skills via skill_manage
  - Persist curator state (last_run_at, paused, etc.) in .curator_state

Strict invariants:
  - Only touches agent-created skills (see tools.skill_usage.is_agent_created)
  - Never auto-deletes — only archives. Archive is recoverable.
  - Pinned skills bypass all auto-transitions
  - Uses the auxiliary client; never touches the main session's prompt cache
"""

from __future__ import annotations

import json
import logging
import os
import re
import tarfile
import tempfile
import threading
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set

from avoi_constants import get_avoi_home
from tools import skill_usage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_INTERVAL_HOURS = 24 * 7  # 7 days
DEFAULT_MIN_IDLE_HOURS = 2
DEFAULT_STALE_AFTER_DAYS = 30
DEFAULT_ARCHIVE_AFTER_DAYS = 90
DEFAULT_BACKUP_KEEP = 5


# ---------------------------------------------------------------------------
# .curator_state — persistent scheduler + status
# ---------------------------------------------------------------------------

def _state_file() -> Path:
    return get_avoi_home() / "skills" / ".curator_state"


def _default_state() -> Dict[str, Any]:
    return {
        "last_run_at": None,
        "last_run_duration_seconds": None,
        "last_run_summary": None,
        "last_report_path": None,
        "paused": False,
        "run_count": 0,
    }


def load_state() -> Dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _default_state()
            base.update({k: v for k, v in data.items() if k in base or k.startswith("_")})
            return base
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to read curator state: %s", e)
    return _default_state()


def save_state(data: Dict[str, Any]) -> None:
    path = _state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".curator_state_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.debug("Failed to save curator state: %s", e, exc_info=True)


def set_paused(paused: bool) -> None:
    state = load_state()
    state["paused"] = bool(paused)
    save_state(state)


def is_paused() -> bool:
    return bool(load_state().get("paused"))


# ---------------------------------------------------------------------------
# Config access
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    try:
        from avoi_cli.config import load_config
        cfg = load_config()
    except Exception as e:
        logger.debug("Failed to load config for curator: %s", e)
        return {}
    if not isinstance(cfg, dict):
        return {}
    cur = cfg.get("curator") or {}
    if not isinstance(cur, dict):
        return {}
    return cur


def is_enabled() -> bool:
    cfg = _load_config()
    return bool(cfg.get("enabled", True))


def get_interval_hours() -> int:
    cfg = _load_config()
    try:
        return int(cfg.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_HOURS


def get_min_idle_hours() -> float:
    cfg = _load_config()
    try:
        return float(cfg.get("min_idle_hours", DEFAULT_MIN_IDLE_HOURS))
    except (TypeError, ValueError):
        return DEFAULT_MIN_IDLE_HOURS


def get_stale_after_days() -> int:
    cfg = _load_config()
    try:
        return int(cfg.get("stale_after_days", DEFAULT_STALE_AFTER_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_STALE_AFTER_DAYS


def get_archive_after_days() -> int:
    cfg = _load_config()
    try:
        return int(cfg.get("archive_after_days", DEFAULT_ARCHIVE_AFTER_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_ARCHIVE_AFTER_DAYS


# ---------------------------------------------------------------------------
# Idle / interval check
# ---------------------------------------------------------------------------

def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def should_run_now(now: Optional[datetime] = None) -> bool:
    if not is_enabled():
        return False
    if is_paused():
        return False
    state = load_state()
    last = _parse_iso(state.get("last_run_at"))
    if last is None:
        if now is None:
            now = datetime.now(timezone.utc)
        try:
            state["last_run_at"] = now.isoformat()
            state["last_run_summary"] = (
                "deferred first run — curator seeded, will run after one "
                "interval; use `avoi curator run --dry-run` to preview now"
            )
            save_state(state)
        except Exception:
            pass
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    interval = timedelta(hours=get_interval_hours())
    return (now - last) >= interval


# ---------------------------------------------------------------------------
# Auto-transitions (pure, no LLM)
# ---------------------------------------------------------------------------

def apply_automatic_transitions(now: Optional[datetime] = None) -> Dict[str, int]:
    from tools import skill_usage as _u
    if now is None:
        now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=get_stale_after_days())
    archive_cutoff = now - timedelta(days=get_archive_after_days())
    counts = {"marked_stale": 0, "archived": 0, "reactivated": 0, "checked": 0}
    for row in _u.agent_created_report():
        counts["checked"] += 1
        name = row["name"]
        if row.get("pinned"):
            continue
        last_activity = _parse_iso(row.get("last_activity_at"))
        anchor = last_activity or _parse_iso(row.get("created_at")) or now
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        current = row.get("state", _u.STATE_ACTIVE)
        if anchor <= archive_cutoff and current != _u.STATE_ARCHIVED:
            ok, _msg = _u.archive_skill(name)
            if ok:
                counts["archived"] += 1
        elif anchor <= stale_cutoff and current == _u.STATE_ACTIVE:
            _u.set_state(name, _u.STATE_STALE)
            counts["marked_stale"] += 1
        elif anchor > stale_cutoff and current == _u.STATE_STALE:
            _u.set_state(name, _u.STATE_ACTIVE)
            counts["reactivated"] += 1
    return counts


# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------

CURATOR_DRY_RUN_BANNER = (
    "═══════════════════════════════════════════════════════════════\n"
    "DRY-RUN — REPORT ONLY. DO NOT MUTATE THE SKILL LIBRARY.\n"
    "═══════════════════════════════════════════════════════════════\n"
    "\n"
    "This is a PREVIEW pass. Follow every instruction below EXCEPT:\n"
    "\n"
    "  • DO NOT call skill_manage with action=patch, create, delete, "
    "write_file, or remove_file.\n"
    "  • DO NOT call terminal to mv skill directories into .archive/. \n"
    "  • DO NOT call terminal to mv, cp, rm, or rewrite any file under "
    "~/.avoi/skills/. \n"
    "  • skills_list and skill_view are FINE — read as much as you need.\n"
    "\n"
    "Your output IS the deliverable. Produce the exact same "
    "human-readable summary and structured YAML block you would "
    "produce on a live run — but describe the actions you WOULD take, "
    "not actions you took. A downstream reviewer will read the report "
    "and decide whether to approve a live run.\n"
    "\n"
    "If you accidentally take a mutating action, say so explicitly in "
    "the summary so the reviewer can revert it.\n"
    "═══════════════════════════════════════════════════════════════"
)

CURATOR_REVIEW_PROMPT = (
    "You are running as the AVOI skill CURATOR. This is an "
    "UMBRELLA-BUILDING consolidation pass, not a passive audit.\n\n"
    "The goal of the skill collection is a LIBRARY OF CLASS-LEVEL "
    "INSTRUCTIONS AND EXPERIENTIAL KNOWLEDGE. A collection of hundreds of "
    "narrow skills where each one captures one session's specific bug is "
    "a FAILURE of the library. One broad umbrella "
    "skill with labeled subsections beats five narrow siblings for "
    "discoverability.\n\n"
    "The right target shape is CLASS-LEVEL skills with rich SKILL.md "
    "bodies + references/, templates/, and scripts/ subfiles for "
    "session-specific detail.\n\n"
    "Hard rules:\n"
    "1. DO NOT touch bundled or hub-installed skills.\n"
    "2. DO NOT delete any skill. Archiving (moving to .archive/) is the maximum.\n"
    "3. DO NOT touch pinned skills.\n"
    "4. DO NOT use usage counters as a reason to skip consolidation.\n"
    "5. 'keep' is legitimate only when the skill is already class-level.\n\n"
    "How to work:\n"
    "1. Scan the full candidate list. Identify PREFIX CLUSTERS.\n"
    "2. For each cluster with 2+ members, ask 'what is the umbrella class?'\n"
    "3. Three ways to consolidate:\n"
    "   a. MERGE INTO EXISTING UMBRELLA — patch it, archive siblings.\n"
    "   b. CREATE A NEW UMBRELLA — write a class-level skill.\n"
    "   c. DEMOTE — move content into references/templates/scripts.\n"
    "4. Iterate. Don't stop after 3 merges.\n\n"
    "Your toolset: skills_list, skill_view, skill_manage (patch/create/write_file), terminal\n\n"
    "When done, write a human summary AND this structured block EXACTLY:\n"
    "## Structured summary (required)\n"
    "```yaml\n"
    "consolidations:\n"
    "  - from: <old-skill-name>\n"
    "    into: <umbrella-skill-name>\n"
    "    reason: <short sentence>\n"
    "prunings:\n"
    "  - name: <skill-name>\n"
    "    reason: <short sentence>\n"
    "```"
)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _reports_root() -> Path:
    root = get_avoi_home() / "logs" / "curator"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.debug("Curator reports dir create failed: %s", e)
    return root


def _classify_removed_skills(
    removed: List[str], added: List[str],
    after_names: Set[str], tool_calls: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    consolidated: List[Dict[str, Any]] = []
    pruned: List[Dict[str, Any]] = []
    parsed_calls: List[Dict[str, Any]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict) or tc.get("name") != "skill_manage":
            continue
        raw = tc.get("arguments") or ""
        args: Dict[str, Any] = {}
        if isinstance(raw, dict):
            args = raw
        elif isinstance(raw, str):
            try:
                args = json.loads(raw)
            except Exception:
                args = {"_raw": raw}
        if not isinstance(args, dict):
            continue
        parsed_calls.append(args)
    destinations = set(after_names) | set(added or [])
    for name in removed:
        if not name:
            continue
        into: Optional[str] = None
        evidence: Optional[str] = None
        needles = {name, name.replace("-", "_"), name.replace("_", "-")}
        for args in parsed_calls:
            target = args.get("name")
            if not isinstance(target, str) or not target or target == name:
                continue
            if target not in destinations:
                continue
            haystacks: List[tuple[str, str]] = []
            for key in ("file_path", "file_content", "content", "new_string", "_raw"):
                v = args.get(key)
                if isinstance(v, str):
                    haystacks.append((key, v))
            hit = False
            for key, hay in haystacks:
                for needle in needles:
                    if not needle:
                        continue
                    if key == "file_path":
                        if _needle_in_path_component(needle, hay):
                            hit = True
                            evidence = f"skill_manage action={args.get('action','?')} on '{target}'"
                            break
                    else:
                        if re.search(rf'\b{re.escape(needle)}\b', hay):
                            hit = True
                            evidence = f"skill_manage action={args.get('action','?')} on '{target}'"
                            break
                if hit:
                    break
            if hit:
                into = target
                break
        if into:
            consolidated.append({"name": name, "into": into, "evidence": evidence or ""})
        else:
            pruned.append({"name": name})
    return {"consolidated": consolidated, "pruned": pruned}


def _needle_in_path_component(needle: str, path: str) -> bool:
    norm_needle = needle.replace("-", "_")
    for part in path.replace("\\", "/").split("/"):
        if not part:
            continue
        stem = part.rsplit(".", 1)[0] if "." in part else part
        if stem.replace("-", "_") == norm_needle:
            return True
    return False


def _write_run_report(
    *, started_at: datetime, elapsed_seconds: float,
    auto_counts: Dict[str, int], auto_summary: str,
    before_report: List[Dict[str, Any]], before_names: Set[str],
    after_report: List[Dict[str, Any]], llm_meta: Dict[str, Any],
) -> Optional[Path]:
    root = _reports_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    stamp = started_at.strftime("%Y%m%d-%H%M%S")
    run_dir = root / stamp
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = root / f"{stamp}-{suffix}"
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except Exception:
        return None
    
    after_by_name = {r.get("name"): r for r in after_report if isinstance(r, dict)}
    after_names = set(after_by_name.keys())
    removed = sorted(before_names - after_names)
    added = sorted(after_names - before_names)
    
    heuristic = _classify_removed_skills(removed, added, after_names, llm_meta.get("tool_calls", []) or [])
    
    payload = {
        "started_at": started_at.isoformat(),
        "duration_seconds": round(elapsed_seconds, 2),
        "model": llm_meta.get("model", ""),
        "provider": llm_meta.get("provider", ""),
        "auto_transitions": auto_counts,
        "counts": {
            "before": len(before_names),
            "after": len(after_names),
            "delta": len(after_names) - len(before_names),
            "archived_this_run": len(removed),
            "added_this_run": len(added),
            "consolidated_this_run": len(heuristic.get("consolidated", [])),
            "pruned_this_run": len(heuristic.get("pruned", [])),
        },
        "archived": removed,
        "consolidated": heuristic.get("consolidated", []),
        "pruned": heuristic.get("pruned", []),
        "llm_final": llm_meta.get("final", ""),
        "llm_summary": llm_meta.get("summary", ""),
        "llm_error": llm_meta.get("error"),
        "tool_calls": llm_meta.get("tool_calls", []),
    }
    try:
        (run_dir / "run.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass
    try:
        md = _render_report_markdown(payload)
        (run_dir / "REPORT.md").write_text(md, encoding="utf-8")
    except Exception:
        pass
    return run_dir


def _render_report_markdown(p: Dict[str, Any]) -> str:
    lines = []
    started = p.get("started_at", "")
    duration = p.get("duration_seconds", 0) or 0
    mins, secs = divmod(int(duration), 60)
    dur_label = f"{mins}m {secs}s" if mins else f"{secs}s"
    lines.append(f"# Curator run — {started}\n")
    model = p.get("model") or "(not resolved)"
    prov = p.get("provider") or "(not resolved)"
    counts = p.get("counts") or {}
    lines.append(f"Model: `{model}` via `{prov}` · Duration: {dur_label} · Agent-created skills: {counts.get('before', 0)} → {counts.get('after', 0)} ({counts.get('delta', 0):+d})\n")
    error = p.get("llm_error")
    if error:
        lines.append(f"> ⚠ LLM pass error: `{error}`\n")
    auto = p.get("auto_transitions") or {}
    lines.append("## Auto-transitions\n")
    lines.append(f"- checked: {auto.get('checked', 0)}")
    lines.append(f"- marked stale: {auto.get('marked_stale', 0)}")
    lines.append(f"- archived: {auto.get('archived', 0)}")
    lines.append(f"- reactivated: {auto.get('reactivated', 0)}\n")
    lines.append(f"**{counts.get('consolidated_this_run', 0)} consolidated, {counts.get('pruned_this_run', 0)} pruned**\n")
    consolidated = p.get("consolidated") or []
    if consolidated:
        lines.append(f"### Consolidated ({len(consolidated)})\n")
        for entry in consolidated[:50]:
            n = entry.get("name", "?")
            into = entry.get("into", "?")
            evidence = entry.get("evidence", "")
            lines.append(f"- `{n}` → `{into}`" + (f" — {evidence[:100]}" if evidence else ""))
        lines.append("")
    pruned = p.get("pruned") or []
    if pruned:
        lines.append(f"### Pruned ({len(pruned)})\n")
        for entry in pruned[:50]:
            n = entry.get("name", "?")
            lines.append(f"- `{n}`")
        lines.append("")
    final = (p.get("llm_final") or "").strip()
    if final:
        lines.append("## LLM summary\n")
        lines.append(final + "\n")
    lines.append("## Recovery\n")
    lines.append("- Restore: `avoi curator restore <name>`")
    lines.append("- Archives: `~/.avoi/skills/.archive/`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _render_candidate_list() -> str:
    rows = skill_usage.agent_created_report()
    if not rows:
        return "No agent-created skills to review."
    lines = [f"Agent-created skills ({len(rows)}):\n"]
    for r in rows:
        lines.append(
            f"- {r['name']}  state={r['state']}  pinned={'yes' if r.get('pinned') else 'no'}  "
            f"activity={r.get('activity_count', 0)}  use={r.get('use_count', 0)}  "
            f"view={r.get('view_count', 0)}  patches={r.get('patch_count', 0)}  "
            f"last_activity={r.get('last_activity_at') or 'never'}"
        )
    return "\n".join(lines)


def run_curator_review(
    on_summary: Optional[Callable[[str], None]] = None,
    synchronous: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    start = datetime.now(timezone.utc)
    if dry_run:
        try:
            report = skill_usage.agent_created_report()
            counts = {"checked": len(report), "marked_stale": 0, "archived": 0, "reactivated": 0}
        except Exception:
            counts = {"checked": 0, "marked_stale": 0, "archived": 0, "reactivated": 0}
    else:
        try:
            from agent import curator_backup as _bkp
            _bkp.snapshot_skills(reason="pre-curator-run")
        except Exception as e:
            logger.debug("Curator pre-run snapshot failed: %s", e)
        counts = apply_automatic_transitions(now=start)
    
    auto_parts = []
    if counts["marked_stale"]:
        auto_parts.append(f"{counts['marked_stale']} marked stale")
    if counts["archived"]:
        auto_parts.append(f"{counts['archived']} archived")
    if counts["reactivated"]:
        auto_parts.append(f"{counts['reactivated']} reactivated")
    auto_summary = ", ".join(auto_parts) if auto_parts else "no changes"
    
    state = load_state()
    if not dry_run:
        state["last_run_at"] = start.isoformat()
        state["run_count"] = int(state.get("run_count", 0)) + 1
    prefix = "dry-run auto: " if dry_run else "auto: "
    state["last_run_summary"] = f"{prefix}{auto_summary}"
    save_state(state)
    
    def _llm_pass():
        nonlocal auto_summary
        try:
            before_report = skill_usage.agent_created_report()
        except Exception:
            before_report = []
        before_names = {r.get("name") for r in before_report if isinstance(r, dict)}
        llm_meta: Dict[str, Any] = {}
        try:
            candidate_list = _render_candidate_list()
            if "No agent-created skills" in candidate_list:
                llm_meta = {"final": "", "summary": "skipped (no candidates)", "model": "", "provider": "", "tool_calls": [], "error": None}
            else:
                prompt = f"{CURATOR_DRY_RUN_BANNER}\n\n{CURATOR_REVIEW_PROMPT}\n\n{candidate_list}" if dry_run else f"{CURATOR_REVIEW_PROMPT}\n\n{candidate_list}"
                llm_meta = _run_llm_review(prompt)
            final_summary = f"{prefix}{auto_summary}; llm: {llm_meta.get('summary', 'no change')}"
        except Exception as e:
            final_summary = f"{prefix}{auto_summary}; llm: error ({e})"
            llm_meta = {"final": "", "summary": f"error ({e})", "model": "", "provider": "", "tool_calls": [], "error": str(e)}
        
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        state2 = load_state()
        state2["last_run_duration_seconds"] = elapsed
        state2["last_run_summary"] = final_summary
        try:
            after_report = skill_usage.agent_created_report()
        except Exception:
            after_report = []
        try:
            report_path = _write_run_report(
                started_at=start, elapsed_seconds=elapsed,
                auto_counts=counts, auto_summary=auto_summary,
                before_report=before_report, before_names=before_names,
                after_report=after_report, llm_meta=llm_meta,
            )
            if report_path is not None:
                state2["last_report_path"] = str(report_path)
        except Exception:
            pass
        save_state(state2)
        if on_summary:
            try:
                on_summary(f"curator: {final_summary}")
            except Exception:
                pass
    
    if synchronous:
        _llm_pass()
    else:
        t = threading.Thread(target=_llm_pass, daemon=True, name="curator-review")
        t.start()
    
    return {"started_at": start.isoformat(), "auto_transitions": counts, "summary_so_far": auto_summary}


def _run_llm_review(prompt: str) -> Dict[str, Any]:
    import contextlib
    result_meta: Dict[str, Any] = {"final": "", "summary": "", "model": "", "provider": "", "tool_calls": [], "error": None}
    try:
        from run_agent import AIAgent
    except Exception as e:
        result_meta["error"] = f"AIAgent import failed: {e}"
        result_meta["summary"] = result_meta["error"]
        return result_meta
    
    _api_key = None
    _base_url = None
    _api_mode = None
    _resolved_provider = None
    _model_name = ""
    try:
        from avoi_cli.config import load_config
        from avoi_cli.runtime_provider import resolve_runtime_provider
        _cfg = load_config()
        _main = _cfg.get("model", {}) if isinstance(_cfg.get("model"), dict) else {}
        _main_provider = _main.get("provider") or "auto"
        _main_model = _main.get("default") or _main.get("model") or ""
        _cur = _cfg.get("curator", {}) if isinstance(_cfg.get("curator"), dict) else {}
        _aux = _cur.get("auxiliary", {}) if isinstance(_cur.get("auxiliary"), dict) else {}
        _task_provider = str(_aux.get("provider") or "") if "provider" in _aux else None
        _task_model = str(_aux.get("model") or "") if "model" in _aux else None
        if _task_provider and _task_provider != "auto" and _task_model:
            _provider, _model_name = _task_provider, _task_model
        else:
            _provider, _model_name = _main_provider, _main_model
        
        _rp = resolve_runtime_provider(requested=_provider, target_model=_model_name)
        _api_key = _rp.get("api_key")
        _base_url = _rp.get("base_url")
        _api_mode = _rp.get("api_mode")
        _resolved_provider = _rp.get("provider") or _provider
    except Exception as e:
        logger.debug("Curator provider resolution failed: %s", e)
    
    result_meta["model"] = _model_name
    result_meta["provider"] = _resolved_provider or ""
    
    review_agent = None
    try:
        review_agent = AIAgent(
            model=_model_name, provider=_resolved_provider,
            api_key=_api_key, base_url=_base_url, api_mode=_api_mode,
            max_iterations=9999, quiet_mode=True,
            platform="curator", skip_context_files=True, skip_memory=True,
        )
        review_agent._memory_nudge_interval = 0
        review_agent._skill_nudge_interval = 0
        with open(os.devnull, "w") as _devnull, contextlib.redirect_stdout(_devnull), contextlib.redirect_stderr(_devnull):
            conv_result = review_agent.run_conversation(user_message=prompt)
        final = ""
        if isinstance(conv_result, dict):
            final = str(conv_result.get("final_response") or "").strip()
        result_meta["final"] = final
        result_meta["summary"] = (final[:240] + "…") if len(final) > 240 else (final or "no change")
        _calls = []
        for msg in getattr(review_agent, "_session_messages", []) or []:
            if not isinstance(msg, dict):
                continue
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args_raw = fn.get("arguments") or ""
                if isinstance(args_raw, str) and len(args_raw) > 400:
                    args_raw = args_raw[:400] + "…"
                _calls.append({"name": name, "arguments": args_raw})
        result_meta["tool_calls"] = _calls
    except Exception as e:
        result_meta["error"] = f"error: {e}"
        result_meta["summary"] = result_meta["error"]
    finally:
        if review_agent is not None:
            try:
                review_agent.close()
            except Exception:
                pass
    return result_meta


def maybe_run_curator(*, idle_for_seconds: Optional[float] = None, on_summary: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, Any]]:
    try:
        if not should_run_now():
            return None
        if idle_for_seconds is not None:
            min_idle_s = get_min_idle_hours() * 3600.0
            if idle_for_seconds < min_idle_s:
                return None
        return run_curator_review(on_summary=on_summary)
    except Exception as e:
        logger.debug("maybe_run_curator failed: %s", e, exc_info=True)
        return None