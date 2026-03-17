"""
Vivioo Memory — Briefing Generator
Generates a concise session briefing for agents starting work.

Instead of raw memory dumps, this produces a structured brief:
  - What changed since last session
  - Top priorities (by importance)
  - What's blocked or expiring
  - Branch health overview

Usage:
    from briefing import generate_briefing
    brief = generate_briefing()                          # general briefing
    brief = generate_briefing(since="2026-03-12")        # since specific date
    brief = generate_briefing(branch="vivioo")           # branch-specific
    print(brief["text"])                                 # ready-to-read text
"""

import os
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from branch_manager import list_branches, load_branch_index, load_master_index
from entry_manager import list_entries
from recall import get_recall_stats
from privacy_filter import load_config as _load_privacy_config, get_tier as _get_tier
from content_guard import get_warning_banner, load_blocklist


def generate_briefing(since: str = None, branch: str = None,
                      max_items: int = 10) -> dict:
    """
    Generate a session briefing.

    Args:
        since: ISO date string — show changes after this date.
               Defaults to 24 hours ago.
        branch: limit to one branch. None = all branches.
        max_items: max entries per section.

    Returns:
        {
            "text": "Ready-to-read briefing text",
            "recent_changes": [...],
            "top_priorities": [...],
            "expiring_soon": [...],
            "never_recalled": [...],
            "branch_health": {...},
            "generated_at": "ISO timestamp",
        }
    """
    if since is None:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    branches_to_check = [branch] if branch else list_branches()

    # 1. Recent changes — entries added or updated since last session
    recent = _get_recent_changes(branches_to_check, since, max_items)

    # 2. Top priorities — highest importance active entries
    priorities = _get_top_priorities(branches_to_check, max_items)

    # 3. Expiring soon — high-importance entries approaching staleness
    expiring = _get_expiring(branches_to_check, max_items)

    # 4. Never recalled — entries that exist but nobody ever searched for
    stats = get_recall_stats(branch=branch)
    never_recalled = stats.get("never_recalled", [])[:max_items]

    # 5. Branch health
    health = _get_branch_health(branches_to_check)

    # Tag entries with their privacy tier
    privacy_config = _load_privacy_config()
    for entry_list in [recent, priorities, expiring]:
        for entry in entry_list:
            entry["_tier"] = _get_tier(entry.get("branch", ""), privacy_config)

    # Generate text
    text = _format_briefing(recent, priorities, expiring, never_recalled, health, since)

    # Split into LLM-safe and local-only briefing
    llm_recent = [e for e in recent if e.get("_tier") == "open"]
    llm_priorities = [e for e in priorities if e.get("_tier") == "open"]
    local_recent = list(recent)   # Agent sees everything
    local_priorities = list(priorities)

    return {
        "text": text,
        "recent_changes": recent,
        "top_priorities": priorities,
        "expiring_soon": expiring,
        "never_recalled": never_recalled,
        "branch_health": health,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # LLM-safe versions — strip Local/Locked entries
        "llm_recent": llm_recent,
        "llm_priorities": llm_priorities,
    }


def _get_recent_changes(branches: List[str], since: str,
                        max_items: int) -> List[dict]:
    """Get entries added or updated after `since`."""
    recent = []

    for branch in branches:
        for entry in list_entries(branch, include_outdated=True):
            stored = entry.get("stored_at", "")
            if stored > since:
                recent.append({
                    "id": entry["id"],
                    "branch": entry.get("branch", branch),
                    "content": entry["content"][:120],
                    "stored_at": stored,
                    "importance": entry.get("_importance", 3),
                    "outdated": entry.get("_outdated", False),
                    "source": entry.get("source", "manual"),
                    "supersedes": entry.get("_supersedes", []),
                })

    recent.sort(key=lambda e: e["stored_at"], reverse=True)
    return recent[:max_items]


def _get_top_priorities(branches: List[str], max_items: int) -> List[dict]:
    """Get highest importance active entries."""
    all_entries = []

    for branch in branches:
        for entry in list_entries(branch, include_outdated=False):
            importance = entry.get("_importance", 3)
            all_entries.append({
                "id": entry["id"],
                "branch": entry.get("branch", branch),
                "content": entry["content"][:120],
                "importance": importance,
                "pinned": entry.get("_importance_source") == "pinned",
                "source": entry.get("source", "manual"),
            })

    all_entries.sort(key=lambda e: e["importance"], reverse=True)
    return all_entries[:max_items]


def _get_expiring(branches: List[str], max_items: int,
                  warn_days: int = 30) -> List[dict]:
    """
    Find high-importance entries that are getting old.
    These need a "still true?" check.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=warn_days)).isoformat()
    expiring = []

    for branch in branches:
        for entry in list_entries(branch, include_outdated=False):
            importance = entry.get("_importance", 3)
            stored = entry.get("stored_at", "")

            # Only flag important entries (3+) that are aging
            if importance >= 3 and stored and stored < cutoff:
                # Check if it has an expiry set
                expires_at = entry.get("_expires_at")
                days_old = _days_since(stored)

                expiring.append({
                    "id": entry["id"],
                    "branch": entry.get("branch", branch),
                    "content": entry["content"][:120],
                    "importance": importance,
                    "days_old": days_old,
                    "expires_at": expires_at,
                    "needs_refresh": True,
                })

    expiring.sort(key=lambda e: e["days_old"], reverse=True)
    return expiring[:max_items]


def _get_branch_health(branches: List[str]) -> dict:
    """Quick health check per branch."""
    health = {}

    for branch in branches:
        all_entries = list_entries(branch, include_outdated=True)
        active = [e for e in all_entries if not e.get("_outdated")]
        outdated = [e for e in all_entries if e.get("_outdated")]

        avg_importance = 0
        if active:
            avg_importance = sum(e.get("_importance", 3) for e in active) / len(active)

        health[branch] = {
            "active": len(active),
            "outdated": len(outdated),
            "avg_importance": round(avg_importance, 1),
        }

    return health


def _days_since(iso_str: str) -> int:
    """Calculate days since an ISO timestamp."""
    try:
        stored = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (now - stored).days)
    except (ValueError, TypeError):
        return 0


def _format_briefing(recent, priorities, expiring, never_recalled,
                     health, since) -> str:
    """Format all sections into readable text."""
    lines = []
    lines.append("=== SESSION BRIEFING ===")
    lines.append("")

    # Privacy reminder — injected every session, no memory required
    try:
        banner = get_warning_banner()
        if banner:
            lines.append("--- Privacy Reminder ---")
            lines.append(f"  {banner}")
            lines.append("")
    except Exception:
        pass

    # Recent changes
    if recent:
        lines.append(f"--- What Changed (since {since[:10]}) ---")
        for r in recent:
            status = "OUTDATED" if r["outdated"] else "NEW"
            replaced = f" (replaces {len(r['supersedes'])} older)" if r["supersedes"] else ""
            private = " [LOCAL-ONLY]" if r.get("_tier") == "local" else ""
            lines.append(f"  [{status}]{private} [{r['branch']}] {r['content']}{replaced}")
        lines.append("")
    else:
        lines.append("--- No changes since last session ---")
        lines.append("")

    # Top priorities
    if priorities:
        lines.append("--- Top Priorities ---")
        for p in priorities[:5]:
            pin = " [PINNED]" if p["pinned"] else ""
            private = " [LOCAL-ONLY]" if p.get("_tier") == "local" else ""
            lines.append(f"  [{p['importance']}/5{pin}]{private} [{p['branch']}] {p['content']}")
        lines.append("")

    # Expiring
    if expiring:
        lines.append("--- Needs Refresh (still true?) ---")
        for e in expiring[:5]:
            lines.append(f"  [{e['days_old']}d old, importance {e['importance']}] "
                         f"[{e['branch']}] {e['content']}")
        lines.append("")

    # Never recalled
    if never_recalled:
        lines.append(f"--- Never Recalled ({len(never_recalled)} entries) ---")
        lines.append("  These memories exist but no one has ever searched for them.")
        for nr in never_recalled[:5]:
            lines.append(f"  [{nr['branch']}] {nr['entry_id']}")
        lines.append("")

    # Branch health
    if health:
        lines.append("--- Branch Health ---")
        for branch, h in health.items():
            lines.append(f"  {branch}: {h['active']} active, "
                         f"{h['outdated']} outdated, "
                         f"avg importance {h['avg_importance']}")
        lines.append("")

    return "\n".join(lines)
