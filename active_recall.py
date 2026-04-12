"""
Vivioo Memory — Active Recall (v0.5)
Forces agents to engage with memories, not just load them.

The LOAD ≠ READ problem: injecting context into an agent's prompt doesn't
mean the agent processes it. Agent B proved this — 52-point gap between
self-assessment and reality, despite having all context loaded.

Active recall solves this by requiring the agent to:
1. Retrieve relevant memories
2. Retrieve relevant corrections
3. Generate a verification summary
4. Proceed only with verified context

Usage:
    from active_recall import pre_task_recall, verify_recall

    # Before starting any task
    context = pre_task_recall("Redesign the landing page", branch="marketing")

    # context["corrections"]  → corrections that apply
    # context["memories"]     → relevant memories
    # context["verification"] → structured summary for agent to confirm
    # context["should_warn"]  → True if critical corrections exist

    # After agent confirms understanding
    verified = verify_recall(context["recall_id"])
"""

import time
import json
import os
from typing import List, Dict, Optional
from datetime import datetime, timezone

from recall import recall
from corrections import recall_corrections, get_corrections


# In-memory tracking of active recall sessions
_recall_sessions = {}


def pre_task_recall(task_description: str, branch: str = None,
                    top_k_memories: int = 5,
                    top_k_corrections: int = 10) -> dict:
    """
    The main entry point — call this before starting any task.

    Retrieves relevant memories AND corrections, structures them
    for the agent to review before proceeding.

    Args:
        task_description: what the agent is about to do
        branch: limit search to this branch (None = all)
        top_k_memories: max memories to surface
        top_k_corrections: max corrections to surface

    Returns:
        {
            "recall_id": unique ID for this recall session,
            "task": the task description,
            "corrections": [relevant corrections — ALWAYS shown first],
            "memories": [relevant memories],
            "verification": {
                "correction_count": int,
                "memory_count": int,
                "critical_corrections": [corrections with source="boss"],
                "summary_prompt": text the agent should read and confirm,
            },
            "should_warn": True if boss corrections exist for this topic,
            "verified": False (set to True after verify_recall()),
        }
    """
    recall_id = f"ar-{int(time.time() * 1000)}"

    # 1. Get relevant corrections (highest priority)
    corrections = recall_corrections(task_description, branch, top_k_corrections)

    # 2. Get relevant memories
    memory_result = recall(task_description, top_k=top_k_memories, branch=branch)
    memories = memory_result.get("local_context", [])

    # 3. Identify critical corrections (from boss/owner)
    critical = [c for c in corrections if c.get("source") in ("boss", "system")]

    # 4. Build verification prompt
    summary_parts = []

    if critical:
        summary_parts.append("CRITICAL CORRECTIONS (from owner):")
        for i, c in enumerate(critical, 1):
            summary_parts.append(f"  {i}. {c['content']}")
            if c.get("context"):
                summary_parts.append(f"     Context: {c['context']}")

    if corrections:
        non_critical = [c for c in corrections if c not in critical]
        if non_critical:
            summary_parts.append("\nOther corrections:")
            for c in non_critical:
                summary_parts.append(f"  - {c['content']}")

    if memories:
        summary_parts.append(f"\nRelevant memories ({len(memories)} found):")
        for m in memories[:3]:
            content = m.get("content", "")[:100]
            summary_parts.append(f"  - [{m.get('branch', '?')}] {content}")

    if not corrections and not memories:
        summary_parts.append("No relevant corrections or memories found for this task.")

    summary_prompt = "\n".join(summary_parts)

    result = {
        "recall_id": recall_id,
        "task": task_description,
        "corrections": corrections,
        "memories": memories,
        "verification": {
            "correction_count": len(corrections),
            "memory_count": len(memories),
            "critical_corrections": critical,
            "summary_prompt": summary_prompt,
        },
        "should_warn": len(critical) > 0,
        "verified": False,
    }

    # Track the session
    _recall_sessions[recall_id] = {
        "task": task_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verified": False,
        "correction_count": len(corrections),
        "memory_count": len(memories),
    }

    return result


def verify_recall(recall_id: str, agent_notes: str = None) -> dict:
    """
    Mark a recall session as verified — the agent confirmed it read
    and understood the corrections and context.

    Args:
        recall_id: the recall session ID from pre_task_recall()
        agent_notes: optional notes from the agent about what it learned

    Returns:
        {"verified": True, "recall_id": ..., "verified_at": ...}
    """
    if recall_id not in _recall_sessions:
        return {"verified": False, "error": "Unknown recall session"}

    session = _recall_sessions[recall_id]
    session["verified"] = True
    session["verified_at"] = datetime.now(timezone.utc).isoformat()
    if agent_notes:
        session["agent_notes"] = agent_notes

    return {
        "verified": True,
        "recall_id": recall_id,
        "verified_at": session["verified_at"],
    }


def get_session_status(recall_id: str) -> Optional[dict]:
    """Check status of a recall session."""
    return _recall_sessions.get(recall_id)


def get_all_corrections_brief(branch: str = None) -> str:
    """
    Get a formatted text of all active corrections.
    Useful for session startup — inject this into agent context.

    Args:
        branch: filter to branch (None = all)

    Returns:
        Formatted text with all corrections, grouped by branch.
    """
    corrections = get_corrections(branch)
    if not corrections:
        return "No active corrections."

    # Group by branch
    by_branch = {}
    for c in corrections:
        b = c.get("branch", "general")
        by_branch.setdefault(b, []).append(c)

    lines = ["=== ACTIVE CORRECTIONS ===", ""]
    for b, cors in sorted(by_branch.items()):
        lines.append(f"[{b}]")
        for c in cors:
            source = c.get("source", "unknown")
            lines.append(f"  [{source}] {c['content']}")
            if c.get("context"):
                lines.append(f"         Context: {c['context']}")
        lines.append("")

    lines.append(f"Total: {len(corrections)} active corrections")
    return "\n".join(lines)
