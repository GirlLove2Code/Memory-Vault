"""
Vivioo Memory — Corrections Store (v0.5)
The most important memory type. Corrections never expire, always surface.

Built from a real pattern: Agent A's BOSS-CORRECTIONS.md works because
corrections are durable files that surface every time the topic comes up.
Agent B's verbal corrections get forgotten — proving that corrections
need architectural enforcement, not just storage.

Usage:
    from corrections import add_correction, get_corrections, recall_corrections

    # Save a correction
    add_correction(
        branch="marketing",
        correction="Don't use stock photos — always use real screenshots",
        context="Boss said this after reviewing the landing page draft",
        source="boss",
    )

    # Get all corrections for a branch
    corrections = get_corrections("marketing")

    # Before starting work: get relevant corrections
    relevant = recall_corrections("I'm working on the landing page")
"""

import os
import json
import time
from typing import List, Optional
from datetime import datetime, timezone

from branch_manager import get_entries_dir, load_branch_index, save_branch_index
from branch_manager import _update_master_index_entry, _now


# Correction source types — who gave the correction
CORRECTION_SOURCES = {
    "boss": "From the owner/builder",
    "self": "Agent self-corrected after a mistake",
    "peer": "Another agent flagged this",
    "system": "Automated check caught an error",
}


def add_correction(branch: str, correction: str, context: str = None,
                   source: str = "boss", tags: List[str] = None) -> dict:
    """
    Add a correction to a branch. Corrections are special memories:
    - Importance is always 5 (max)
    - They never expire
    - They always surface in recall when the topic matches
    - They are pinned by default

    Args:
        branch: the branch this correction applies to
        correction: the correction itself — what to do differently
        context: why this correction was given (optional but recommended)
        source: who gave it — "boss", "self", "peer", "system"
        tags: optional tags for matching

    Returns:
        The created correction entry.
    """
    entries_dir = get_entries_dir(branch)
    os.makedirs(entries_dir, exist_ok=True)

    now = _now()
    entry_id = f"cor-{int(time.time() * 1000)}"

    entry = {
        "id": entry_id,
        "branch": branch,
        "content": correction,
        "context": context or "",
        "stored_at": now,
        "happened_at": now,
        "tags": tags or [],
        "source": source,
        "_type": "correction",
        "_outdated": False,
        "_importance": 5,
        "_importance_source": "correction",
        "_expires_at": None,
        "_expiry_days": None,
    }

    # Content guard check
    try:
        from content_guard import check_before_save
        guard = check_before_save(correction, branch)
        if not guard["allowed"]:
            raise ValueError(guard["warning"])
    except ImportError:
        pass

    # Save
    entry_path = os.path.join(entries_dir, f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    # Sync to vector store
    try:
        from embedding import embed_text
        from vector_store import init_store, add_entry as vs_add
        enriched = f"CORRECTION [{branch}]: {correction}"
        if context:
            enriched += f" (context: {context})"
        embedding = embed_text(enriched)
        if embedding:
            init_store()
            vs_add(entry_id, embedding, {
                "branch": branch,
                "stored_at": now,
                "_type": "correction",
                "_outdated": False,
            }, enriched)
    except Exception:
        pass

    # Update indexes
    branch_index = load_branch_index(branch)
    branch_index["last_updated"] = now
    save_branch_index(branch, branch_index)
    _update_master_index_entry(branch, branch_index)

    # Fire event
    _fire_event("correction_added", {
        "entry_id": entry_id,
        "branch": branch,
        "correction": correction[:150],
        "source": source,
    })

    return entry


def get_corrections(branch: str = None, include_resolved: bool = False) -> List[dict]:
    """
    Get all active corrections, optionally filtered by branch.

    Args:
        branch: filter to this branch (None = all branches)
        include_resolved: include corrections marked as resolved

    Returns:
        List of correction entries, sorted by newest first.
    """
    from branch_manager import list_branches
    from entry_manager import list_entries

    branches = [branch] if branch else list_branches()
    corrections = []

    for b in branches:
        for entry in list_entries(b, include_outdated=include_resolved):
            if entry.get("_type") == "correction":
                if not include_resolved and entry.get("_outdated"):
                    continue
                corrections.append(entry)

    corrections.sort(key=lambda e: e.get("stored_at", ""), reverse=True)
    return corrections


def resolve_correction(entry_id: str, branch: str,
                       reason: str = "Applied and verified") -> Optional[dict]:
    """
    Mark a correction as resolved — it was applied and is no longer needed.

    The correction stays in the store (for audit trail) but stops surfacing
    in active recall. Use this when a correction has been fully integrated
    into the workflow.

    Args:
        entry_id: the correction's ID
        branch: the branch path
        reason: why it's resolved

    Returns:
        Updated entry, or None if not found.
    """
    from entry_manager import get_entry, get_entries_dir as _get_entries_dir

    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    if entry.get("_type") != "correction":
        return None

    entry["_outdated"] = True
    entry["_outdated_reason"] = reason
    entry["_resolved_at"] = _now()

    entry_path = os.path.join(_get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    _fire_event("correction_resolved", {
        "entry_id": entry_id,
        "branch": branch,
        "reason": reason,
    })

    return entry


def recall_corrections(query: str, branch: str = None,
                       top_k: int = 5) -> List[dict]:
    """
    Find corrections relevant to a query. Used before starting work
    to surface past mistakes and instructions.

    This is the "forced active recall" pattern: before the agent acts,
    it checks what corrections apply to the current task.

    Args:
        query: what the agent is about to work on
        branch: limit to this branch (None = all)
        top_k: max corrections to return

    Returns:
        List of relevant corrections with match scores.
    """
    all_corrections = get_corrections(branch)
    if not all_corrections:
        return []

    # Try semantic matching first
    try:
        from embedding import embed_text
        query_emb = embed_text(query)
        if query_emb:
            scored = []
            for cor in all_corrections:
                enriched = f"CORRECTION [{cor.get('branch', '')}]: {cor['content']}"
                cor_emb = embed_text(enriched)
                if cor_emb:
                    score = _cosine_sim(query_emb, cor_emb)
                    if score >= 0.4:  # Lower threshold — corrections are important
                        scored.append({**cor, "_match_score": round(score, 4)})
            scored.sort(key=lambda x: x["_match_score"], reverse=True)
            return scored[:top_k]
    except Exception:
        pass

    # Keyword fallback
    return _keyword_match_corrections(query, all_corrections, top_k)


def _keyword_match_corrections(query: str, corrections: List[dict],
                               top_k: int) -> List[dict]:
    """Match corrections by keyword overlap."""
    query_words = set(query.lower().split())
    scored = []

    for cor in corrections:
        content_words = set(cor.get("content", "").lower().split())
        tag_words = set(t.lower() for t in cor.get("tags", []))
        all_words = content_words | tag_words

        overlap = len(query_words & all_words)
        if overlap > 0:
            score = overlap / max(len(query_words), 1)
            scored.append({**cor, "_match_score": round(score, 4)})

    scored.sort(key=lambda x: x["_match_score"], reverse=True)
    return scored[:top_k]


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _fire_event(event: str, data: dict) -> None:
    """Fire hooks if available."""
    try:
        from hooks import fire_hooks
        fire_hooks(event, data)
    except Exception:
        pass
