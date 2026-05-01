"""
memory_store.py — UserMemoryStore for the Second Brain.

Handles:
  - retrieveRelevant: FTS5 search + ranking + context injection
  - remember: merge, conflict resolution, auto-tiering (active vs durable)
  - consolidate: profile summary + active summary + reflection synthesis
  - prune: decay, stale dismissal, promotion to durable
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugins.memory.second_brain.second_brain_db import SecondBrainDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

VALID_TYPES = frozenset({
    "identity", "preference", "goal", "project", "habit",
    "decision", "constraint", "relationship", "episode", "reflection",
})

MIN_CONFIDENCE = 0.55


# ---------------------------------------------------------------------------
# UserMemoryStore
# ---------------------------------------------------------------------------

class UserMemoryStore:
    """Autonomous structured user memory with search, merge, consolidate, prune."""

    def __init__(
        self,
        db: SecondBrainDB,
        user_key: str = "user:owner",
        max_records: int = 50,
    ):
        self._db = db
        self._user_key = user_key
        self._max_records = max_records
        self._last_consolidate_at: float = 0
        self._consolidate_throttle_ms = 5 * 60 * 1000  # 5 min

    # -- Profile / summary ---------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        by_type = self._db.count_by_type(self._user_key)
        return {
            "total": self._db.total_active(self._user_key),
            "by_type": by_type,
            "learning_paused": self.is_learning_paused(),
            "profile_summary": self._db.get_meta(f"{self._user_key}:profile_summary") or "",
            "active_summary": self._db.get_meta(f"{self._user_key}:active_summary") or "",
        }

    def get_profile(self) -> str:
        return self._db.get_meta(f"{self._user_key}:profile_summary") or ""

    def get_active_summary(self) -> str:
        return self._db.get_meta(f"{self._user_key}:active_summary") or ""

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._db.get_active(self._user_key)[:limit]

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self._db.search_fts(self._user_key, query, limit)

    def get_by_type(self, type: str) -> List[Dict[str, Any]]:
        return self._db.get_by_type(self._user_key, type)

    # -- Retrieval (pre-message injection) -----------------------------------

    def retrieve_relevant(
        self,
        query: str,
        *,
        max_records: int = 5,
        max_chars: int = 900,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Search and rank relevant memories for the given query.

        Returns (records_list, context_string) where context_string is ready
        to inject as a user message.
        """
        fts_results = self._db.search_relevant(
            self._user_key, query, max(max_records * 2, 10)
        )
        ranked = self._score_and_rank(fts_results, query)

        selected: List[Dict[str, Any]] = []
        current_length = 0
        for row in ranked:
            line = f"- [{row['type']}] {row['summary']}"
            if len(selected) >= max_records:
                break
            if len(selected) > 0 and current_length + len(line) > max_chars:
                break
            selected.append(row)
            current_length += len(line) + 1

        if not selected:
            profile = self.get_profile().strip()
            if not profile:
                return [], ""
            context = (
                f"{'User active state:' if self.get_active_summary() else ''}"
                f"{'- ' + self.get_active_summary() if self.get_active_summary() else ''}"
                f"{chr(10) if self.get_active_summary() else ''}"
                f"User profile summary:{chr(10)}- {profile}"
            )
            return [], context

        context_lines = []
        active_summary = self.get_active_summary()
        if active_summary:
            context_lines.append("User active state:")
            context_lines.append(f"- {active_summary}")
            context_lines.append("")
        profile_summary = self.get_profile()
        if profile_summary:
            context_lines.append("User profile summary:")
            context_lines.append(f"- {profile_summary}")
            context_lines.append("")
        context_lines.append("Relevant user memory:")
        context_lines.extend(f"- [{r['type']}] {r['summary']}" for r in selected)

        self._mark_used([r["id"] for r in selected], query)
        return selected, "\n".join(context_lines)

    # -- Remember (post-message extraction) ----------------------------------

    def remember(
        self,
        candidates: List[Dict[str, Any]],
        source: str = "conversation",
    ) -> List[Dict[str, Any]]:
        """Store memory candidates with merge, conflict resolution, auto-tiering."""
        if self.is_learning_paused():
            return []

        remembered: List[Dict[str, Any]] = []
        for candidate in candidates:
            if not self._should_store(candidate):
                continue

            terms = _normalize(candidate["summary"]).split()
            terms = [t for t in terms if len(t) > 2]

            # Try merge
            merge_target = self._db.find_merge_candidate(
                self._user_key, candidate["type"], terms,
            )
            if merge_target and _overlap_score(
                _normalize(merge_target["summary"]),
                _normalize(candidate["summary"]),
            ) >= 0.74:
                merged = self._merge_record(merge_target, candidate)
                if merged:
                    remembered.append(merged)
                continue

            # Try conflict resolution
            conflict_target = self._db.find_conflict_candidate(
                self._user_key, candidate["type"], terms,
            )
            if conflict_target:
                winner = self._resolve_conflict(conflict_target, candidate)
                if winner == "existing":
                    continue

            # Insert new
            record = self._insert_record(candidate, source)
            if record:
                remembered.append(record)

        self._enforce_max_records()
        return remembered

    # -- Consolidation -------------------------------------------------------

    def consolidate(self) -> Dict[str, Any]:
        """Re-synthesize profile summary, active summary, and reflections."""
        now = time.time() * 1000
        if now - self._last_consolidate_at < self._consolidate_throttle_ms and self._last_consolidate_at > 0:
            return {"profile_updated": False, "reflection_count": 0}
        self._last_consolidate_at = now

        all_active = self._db.get_active(self._user_key)
        non_reflection = [r for r in all_active if r["type"] != "reflection"]

        profile_summary = _build_profile_summary(non_reflection)
        active_summary = _build_active_summary(non_reflection)

        old_profile = self._db.get_meta(f"{self._user_key}:profile_summary") or ""
        old_active = self._db.get_meta(f"{self._user_key}:active_summary") or ""
        profile_updated = profile_summary != old_profile or active_summary != old_active

        self._db.set_meta(f"{self._user_key}:profile_summary", profile_summary)
        self._db.set_meta(f"{self._user_key}:active_summary", active_summary)

        reflections = _build_reflection_candidates(non_reflection)
        reflection_count = 0
        for ref in reflections:
            same_type = self._db.get_by_type(self._user_key, "reflection")
            existing = _find_merge_target_raw(same_type, ref)
            if existing:
                self._db.update({
                    "id": existing["id"],
                    "summary": ref["summary"],
                    "detail": ref.get("detail") or existing.get("detail"),
                    "confidence": max(existing["confidence"], ref["confidence"]),
                    "importance": max(existing["importance"], ref["importance"]),
                    "durability": max(existing["durability"], ref["durability"]),
                    "updated_at": int(now),
                    "last_seen_at": int(now),
                })
            else:
                self._insert_reflection(ref)
            reflection_count += 1

        return {"profile_updated": profile_updated, "reflection_count": reflection_count}

    # -- Pruning -------------------------------------------------------------

    def prune(self) -> Dict[str, int]:
        promoted = self._db.promote_to_durable(self._user_key)
        active_pruned, durable_pruned = self._db.prune_stale(self._user_key)
        hard_deleted = self._db.hard_delete_dismissed(self._user_key)
        return {
            "active_pruned": active_pruned,
            "durable_pruned": durable_pruned,
            "promoted": promoted,
            "hard_deleted": hard_deleted,
        }

    # -- Learning pause ------------------------------------------------------

    def set_learning_paused(self, paused: bool) -> None:
        self._db.set_meta(f"{self._user_key}:learning_paused", "1" if paused else "0")

    def is_learning_paused(self) -> bool:
        return self._db.get_meta(f"{self._user_key}:learning_paused") == "1"

    # -- Clear ---------------------------------------------------------------

    def clear(self) -> int:
        return self._db.clear_by_type(self._user_key)

    def close(self) -> None:
        self._db.close()

    # -- Internal ------------------------------------------------------------

    def _should_store(self, candidate: Dict[str, Any]) -> bool:
        summary = candidate.get("summary", "").strip()
        if len(summary) < 12 or len(summary) > 220:
            return False
        if candidate.get("confidence", 0) < MIN_CONFIDENCE:
            return False
        if candidate.get("durability", 0) < 0.4 and candidate.get("importance", 0) < 0.7:
            return False
        return True

    def _insert_record(
        self, candidate: Dict[str, Any], source: str
    ) -> Optional[Dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        rid = _generate_id("mem")

        scope = "active" if candidate["type"] in ("goal", "project", "decision", "episode") else "durable"

        self._db.insert({
            "id": rid,
            "user_key": self._user_key,
            "type": candidate["type"],
            "summary": candidate["summary"].strip(),
            "detail": (candidate.get("detail") or "").strip() or None,
            "scope": scope,
            "evidence_kind": candidate.get("evidenceKind", "inferred"),
            "source": source,
            "confidence": _clamp(candidate.get("confidence", 0.7), 0, 1),
            "importance": _clamp(candidate.get("importance", 0.7), 0, 1),
            "durability": _clamp(candidate.get("durability", 0.7), 0, 1),
            "evidence_count": 1,
            "provenance": (candidate.get("detail") or "").strip() or None,
            "dismissed": 0,
            "superseded_by": None,
            "created_at": now_ms,
            "updated_at": now_ms,
            "last_seen_at": now_ms,
            "last_used_at": None,
            "last_used_query": None,
        })

        row = self._db.get_by_id(rid)
        return row

    def _insert_reflection(self, candidate: Dict[str, Any]) -> None:
        now_ms = int(time.time() * 1000)
        rid = _generate_id("mem")
        self._db.insert({
            "id": rid,
            "user_key": self._user_key,
            "type": "reflection",
            "summary": candidate["summary"],
            "detail": (candidate.get("detail") or "").strip() or None,
            "scope": "durable",
            "evidence_kind": "system",
            "source": "system",
            "confidence": _clamp(candidate.get("confidence", 0.85), 0, 1),
            "importance": _clamp(candidate.get("importance", 0.85), 0, 1),
            "durability": _clamp(candidate.get("durability", 0.85), 0, 1),
            "evidence_count": 1,
            "provenance": None,
            "dismissed": 0,
            "superseded_by": None,
            "created_at": now_ms,
            "updated_at": now_ms,
            "last_seen_at": now_ms,
            "last_used_at": None,
            "last_used_query": None,
        })

    def _merge_record(
        self, existing: Dict[str, Any], candidate: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        updated_at = int(time.time() * 1000)
        self._db.update({
            "id": existing["id"],
            "summary": _pick_better_summary(existing["summary"], candidate["summary"]),
            "detail": candidate.get("detail") or existing.get("detail"),
            "provenance": candidate.get("detail") or existing.get("provenance"),
            "evidence_kind": candidate.get("evidenceKind", "inferred"),
            "confidence": _clamp(max(existing["confidence"], candidate.get("confidence", 0)), 0, 1),
            "importance": _clamp(max(existing["importance"], candidate.get("importance", 0)), 0, 1),
            "durability": _clamp(max(existing["durability"], candidate.get("durability", 0)), 0, 1),
            "evidence_count": existing["evidence_count"] + 1,
            "updated_at": updated_at,
            "last_seen_at": updated_at,
        })
        return self._db.get_by_id(existing["id"])

    def _resolve_conflict(
        self, existing: Dict[str, Any], candidate: Dict[str, Any]
    ) -> str:
        incoming_confidence = candidate.get("confidence", 0)
        existing_confidence = existing["confidence"]

        if incoming_confidence > existing_confidence:
            self._db.update({
                "id": existing["id"],
                "dismissed": 1,
                "superseded_by": "auto_resolved",
                "updated_at": int(time.time() * 1000),
            })
            return "incoming"

        if incoming_confidence < existing_confidence:
            return "existing"

        # Equal confidence — newer wins
        self._db.update({
            "id": existing["id"],
            "dismissed": 1,
            "superseded_by": "auto_resolved",
            "updated_at": int(time.time() * 1000),
        })
        return "incoming"

    def _enforce_max_records(self) -> None:
        total = self._db.total_active(self._user_key)
        if total <= self._max_records:
            return

        all_active = self._db.get_active(self._user_key)
        scored = [(r, _memory_health_score(r)) for r in all_active]
        scored.sort(key=lambda x: x[1], reverse=True)
        to_dismiss = scored[self._max_records:]

        for row, _ in to_dismiss:
            self._db.soft_delete(row["id"])

        if to_dismiss:
            logger.debug(
                "Enforced max records: dismissed %d memories",
                len(to_dismiss),
            )

    def _mark_used(self, ids: List[str], query: Optional[str] = None) -> None:
        now = int(time.time() * 1000)
        for rid in ids:
            self._db.update({
                "id": rid,
                "last_used_at": now,
                "last_used_query": query or "",
                "updated_at": now,
            })

    def _score_and_rank(
        self, rows: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        now = time.time() * 1000
        tokens = [t.lower() for t in query.split() if len(t) > 0]
        scored = []
        for row in rows:
            score = 0.0
            score += row["confidence"] * 0.3
            score += row["importance"] * 0.25
            score += row["durability"] * 0.15
            age_days = (now - row["updated_at"]) / (1000 * 60 * 60 * 24)
            score += max(0, 0.2 - age_days * 0.005)
            lower_text = (row["summary"] + " " + (row.get("detail") or "")).lower()
            match_count = sum(1 for t in tokens if t in lower_text)
            if tokens:
                score += (match_count / len(tokens)) * 0.1
            scored.append((row, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [r for r, _ in scored]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _tokenize(input_str: str) -> List[str]:
    return [
        t for t in input_str.lower().split()
        if len(t) >= 3 and any(c.isalnum() for c in t)
    ]

def _normalize(input_str: str) -> str:
    return " ".join(_tokenize(input_str))

def _overlap_score(a: str, b: str) -> float:
    a_set = set(a.split()) if a else set()
    b_set = set(b.split()) if b else set()
    if not a_set or not b_set:
        return 0.0
    overlap = len(a_set & b_set)
    return overlap / max(len(a_set), len(b_set))

def _pick_better_summary(existing: str, incoming: str) -> str:
    incoming = incoming.strip()
    existing = existing.strip()
    if len(incoming) > len(existing) and len(incoming) <= 220:
        return incoming
    return existing

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def _generate_id(prefix: str = "mem") -> str:
    ts = int(time.time() * 1000)
    r = random.randint(0, 2**31)
    return f"{prefix}_{ts:x}{r:x}"


def _memory_health_score(row: Dict[str, Any]) -> float:
    return (
        row["importance"] * 0.35
        + row["durability"] * 0.25
        + _effective_confidence(row) * 0.25
        + (min(row["evidence_count"], 5) / 5) * 0.15
        + (0.08 if row["scope"] == "active" else 0)
        - (0.3 if row.get("superseded_by") else 0)
        - (0.12 if _is_stale(row) else 0)
    )

def _effective_confidence(row: Dict[str, Any]) -> float:
    age_days = (time.time() * 1000 - row["updated_at"]) / (1000 * 60 * 60 * 24)
    confidence = row["confidence"]
    if row["evidence_kind"] == "inferred":
        confidence -= min(0.2, age_days / 365)
    elif row["evidence_kind"] == "manual":
        confidence += 0.06
    elif row["evidence_kind"] == "direct":
        confidence += 0.03
    if row["scope"] == "active":
        confidence -= min(0.18, age_days / 120)
    return _clamp(confidence, 0, 1)

def _is_stale(row: Dict[str, Any]) -> bool:
    age_days = (time.time() * 1000 - row["updated_at"]) / (1000 * 60 * 60 * 24)
    if row["scope"] == "active":
        return age_days > 21
    if row["evidence_kind"] == "inferred":
        return age_days > 120
    return age_days > 365

def _find_merge_target_raw(
    rows: List[Dict[str, Any]], candidate: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    norm_cand = _normalize(candidate["summary"])
    for row in rows:
        if row["type"] != candidate["type"]:
            continue
        if _has_conflict(row["summary"], candidate["summary"]):
            continue
        norm_row = _normalize(row["summary"])
        if norm_row == norm_cand or _overlap_score(norm_row, norm_cand) >= 0.74:
            return row
    return None

def _has_conflict(a: str, b: str) -> bool:
    left = a.lower()
    right = b.lower()
    if left == right:
        return False

    polarity_pairs = [
        ("prefers", "does not prefer"),
        ("likes", "does not like"),
        ("wants", "does not want"),
        ("uses", "does not use"),
        ("enabled", "disabled"),
    ]
    for positive, negative in polarity_pairs:
        left_pos_right_neg = positive in left and negative in right
        left_neg_right_pos = negative in left and positive in right
        if left_pos_right_neg or left_neg_right_pos:
            clean_left = _normalize(left.replace(positive, "").replace(negative, ""))
            clean_right = _normalize(right.replace(positive, "").replace(negative, ""))
            if _overlap_score(clean_left, clean_right) >= 0.5:
                return True

    left_has_neg = bool(set(("not", "never", "no longer", "avoid", "against", "disabled")) & set(left.split()))
    right_has_neg = bool(set(("not", "never", "no longer", "avoid", "against", "disabled")) & set(right.split()))
    if left_has_neg != right_has_neg:
        return _overlap_score(_normalize(left), _normalize(right)) >= 0.7

    return False

def _build_profile_summary(records: List[Dict[str, Any]]) -> str:
    selected: List[str] = []
    preferred_types = ["identity", "preference", "goal", "project", "constraint", "habit"]
    for typ in preferred_types:
        matches = [r for r in records if r["type"] == typ]
        if matches:
            best = max(matches, key=lambda r: _memory_health_score(r))
            if best["summary"] not in selected:
                selected.append(best["summary"])
        if len(selected) >= 4:
            break
    return " ".join(selected)[:420].strip()

def _build_active_summary(records: List[Dict[str, Any]]) -> str:
    cutoff = time.time() * 1000 - (14 * 24 * 60 * 60 * 1000)
    active_types = {"goal", "project", "decision", "episode"}
    candidates = [
        r for r in records
        if not r.get("superseded_by")
        and not _is_stale(r)
        and r["updated_at"] >= cutoff
        and r["type"] in active_types
    ]
    candidates.sort(key=lambda r: (r["updated_at"], _memory_health_score(r)), reverse=True)
    top = candidates[:3]
    return " ".join(r["summary"] for r in top)[:360].strip()

def _build_reflection_candidates(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        groups.setdefault(r["type"], []).append(r)

    pref_group = groups.get("preference", [])
    if len(pref_group) >= 2:
        top = sorted(pref_group, key=lambda r: _memory_health_score(r), reverse=True)[:2]
        candidates.append({
            "type": "reflection",
            "summary": f"User consistently shows these preferences: {' '.join(r['summary'] for r in top)}"[:220],
            "detail": "\n".join(r["summary"] for r in top),
            "confidence": 0.86,
            "importance": 0.86,
            "durability": 0.9,
        })

    goal_project = [
        *(groups.get("goal", [])),
        *(groups.get("project", [])),
    ]
    if len(goal_project) >= 2:
        top = sorted(goal_project, key=lambda r: _memory_health_score(r), reverse=True)[:2]
        candidates.append({
            "type": "reflection",
            "summary": f"Current long-term direction: {' '.join(r['summary'] for r in top)}"[:220],
            "detail": "\n".join(r["summary"] for r in top),
            "confidence": 0.84,
            "importance": 0.9,
            "durability": 0.86,
        })

    habit_constraint = [
        *(groups.get("habit", [])),
        *(groups.get("constraint", [])),
    ]
    if len(habit_constraint) >= 2:
        top = sorted(habit_constraint, key=lambda r: _memory_health_score(r), reverse=True)[:2]
        candidates.append({
            "type": "reflection",
            "summary": f"Working style pattern: {' '.join(r['summary'] for r in top)}"[:220],
            "detail": "\n".join(r["summary"] for r in top),
            "confidence": 0.82,
            "importance": 0.8,
            "durability": 0.82,
        })

    return candidates
