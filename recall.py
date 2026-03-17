"""
Vivioo Memory — Recall (Step 6)
THE FRONT DOOR. The agent calls one function, gets everything it needs.

recall() ties together:
  routing → search → load → quality filter → privacy filter → return

Quality improvements built in:
  - Minimum similarity threshold (no garbage results)
  - Recency weighting (recent memories get a small boost)
  - Outdated penalty (stale entries rank lower)
  - No-match detection (tells the agent when it has no memory of something)
"""

import time
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone

from branch_manager import (
    load_master_index, load_branch_index, list_branches,
    find_branch_by_alias, find_branches_by_query
)
from entry_manager import get_entry, list_entries, search_entries, get_enriched_text
from vector_store import init_store, search as vector_search, search_by_branch_summary
from embedding import embed_text, check_ollama
from privacy_filter import load_config, filter_for_llm, count_blocked, get_tier
from content_guard import inject_warnings, scan_for_llm, load_blocklist


# ─── QUALITY SCORING ─────────────────────────────────────────

def score_with_recency(similarity: float, stored_at: str,
                       recency_weight: float = 0.15,
                       fade_days: int = 90) -> float:
    """
    Blend similarity score with recency.

    A memory from yesterday about "marketing" ranks higher than a
    memory from 3 months ago — IF both are similarly relevant.

    Args:
        similarity: raw similarity score from vector search (0-1)
        stored_at: ISO timestamp of when the entry was stored
        recency_weight: how much recency matters (0.15 = 15%)
        fade_days: how many days until recency bonus fully fades

    Returns:
        Blended score (0-1)

    Example:
        similarity=0.82, stored yesterday → ~0.84
        similarity=0.82, stored 90 days ago → ~0.82
        similarity=0.72, stored yesterday → ~0.74
    """
    try:
        stored_time = datetime.fromisoformat(stored_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_old = max(0, (now - stored_time).total_seconds() / 86400)
        recency_bonus = max(0, 1 - (days_old / fade_days))
    except (ValueError, TypeError):
        recency_bonus = 0

    return similarity * (1 - recency_weight) + recency_bonus * recency_weight


def apply_quality_filters(results: List[dict], config: dict = None) -> List[dict]:
    """
    Apply all quality filters to search results:
    1. Minimum similarity threshold — drop garbage results
    2. Recency weighting — boost recent memories
    3. Outdated penalty — penalize stale entries
    4. Importance boost — high-importance memories surface first

    Args:
        results: list of search results with "score" and entry data
        config: loaded config dict

    Returns:
        Filtered and re-scored results, sorted by adjusted score
    """
    if config is None:
        config = load_config()

    defaults = config.get("defaults", {})
    min_threshold = defaults.get("min_similarity_threshold", 0.65)
    recency_weight = defaults.get("recency_weight", 0.15)
    fade_days = defaults.get("recency_fade_days", 90)
    outdated_penalty = defaults.get("outdated_penalty", 0.5)
    importance_weight = defaults.get("importance_weight", 0.10)

    filtered = []
    for result in results:
        raw_score = result.get("score", 0)

        # 1. Drop below threshold
        if raw_score < min_threshold:
            continue

        # 2. Apply recency weighting
        stored_at = result.get("stored_at", result.get("metadata", {}).get("stored_at", ""))
        adjusted_score = score_with_recency(raw_score, stored_at, recency_weight, fade_days)

        # 3. Penalize outdated entries
        is_outdated = result.get("_outdated", result.get("metadata", {}).get("_outdated", False))
        if is_outdated:
            adjusted_score *= outdated_penalty

        # 4. Importance boost — scale 1-5 mapped to 0-1 bonus
        importance = result.get("_importance", 3)  # default to mid
        importance_bonus = (importance - 1) / 4  # 1→0, 3→0.5, 5→1.0
        adjusted_score = adjusted_score * (1 - importance_weight) + importance_bonus * importance_weight

        result["raw_score"] = raw_score
        result["score"] = round(adjusted_score, 4)
        result["_quality_filtered"] = True
        filtered.append(result)

    # Re-sort by adjusted score
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered


# ─── MAIN RECALL ─────────────────────────────────────────────

def recall(query: str, top_k: int = 5, branch: str = None,
           override: bool = False) -> dict:
    """
    THE MAIN FUNCTION — The agent's single entry point for memory search.

    Args:
        query: natural language question or search text
        top_k: number of results to return (default 5)
        branch: search only this branch (auto-routes if None)
        override: skip summary tier, go straight to entries (thorough mode)

    Returns:
        {
            "llm_context": [entries safe for the LLM — 🟢 Open only],
            "local_context": [entries the agent reads privately — 🟢 + 🔒],
            "blocked_count": number of 🔴 Locked entries hidden,
            "branch_used": which branch was searched,
            "confidence": routing confidence score,
            "query": original query echoed back,
            "override": whether override mode was used,
            "search_mode": "semantic" or "keyword",
            "no_match": True if nothing relevant was found,
            "result_count": total results before privacy split,
        }
    """
    config = load_config()
    search_mode = "semantic"
    routing_confidence = 1.0
    branch_used = branch or "all"

    # 1. ROUTE (if branch not specified)
    if branch is None:
        routing = route_query(query)
        if routing["branch"]:
            branch_used = routing["branch"]
            branch = routing["branch"]
        routing_confidence = routing["confidence"]

    # 2. CHECK SUMMARY (if not override mode)
    summary_entry = None
    if not override and branch:
        branch_index = load_branch_index(branch)
        summary_text = branch_index.get("summary", "")
        if summary_text:
            summary_entry = {
                "id": "_summary",
                "branch": branch,
                "content": summary_text,
                "preview": "Branch summary",
                "_tier": get_tier(branch, config),
                "_is_summary": True,
            }

    # 3. SEARCH
    results = []
    try:
        # Try semantic search first
        query_embedding = embed_text(query)
        if query_embedding:
            init_store()
            raw_results = vector_search(query_embedding, top_k * 2, branch)
            # Load full entries from JSON (source of truth)
            for r in raw_results:
                entry = get_entry(r["id"], r.get("metadata", {}).get("branch", branch or ""))
                if entry:
                    entry["score"] = r["score"]
                    results.append(entry)
        else:
            raise RuntimeError("Embedding failed")
    except Exception:
        # Fallback to keyword search
        search_mode = "keyword"
        results = search_entries(query, branch)

    # 4. APPLY QUALITY FILTERS
    results = apply_quality_filters(results, config)

    # Limit to top_k
    results = results[:top_k]

    # 5. ADD SUMMARY if we have one
    all_entries = list(results)
    if summary_entry:
        all_entries.insert(0, summary_entry)

    # 6. PRIVACY FILTER
    llm_context, local_context = filter_for_llm(all_entries, config)
    blocked = count_blocked(all_entries, config)

    # 6b. INJECT WARNINGS on Local-tier entries
    # Every time the agent reads private data, it sees the warning banner.
    # It doesn't have to remember — the warning is glued to the data.
    local_context = inject_warnings(local_context)

    # 7. NO-MATCH DETECTION
    no_match = len(results) == 0

    # 8. TRACK RECALL HITS — every returned entry gets a hit recorded
    for entry in results:
        _record_recall_hit(entry.get("id"), entry.get("branch", branch_used), query)

    return {
        "llm_context": llm_context,
        "local_context": local_context,
        "blocked_count": blocked,
        "branch_used": branch_used,
        "confidence": round(routing_confidence, 4),
        "query": query,
        "override": override,
        "search_mode": search_mode,
        "no_match": no_match,
        "result_count": len(results),
    }


# ─── STARTUP RECALL ──────────────────────────────────────────

def startup_recall(recent_context: str = None, top_k: int = 10) -> dict:
    """
    Called at session start — loads the most relevant memories.

    If recent_context is provided, biases toward related memories.
    If not, returns most recently updated entries.

    Returns same format as recall().
    """
    if recent_context:
        return recall(recent_context, top_k=top_k)

    # No context — return most recent entries across all branches
    config = load_config()
    all_entries = []

    for branch_path in list_branches():
        entries = list_entries(branch_path, include_outdated=False)
        all_entries.extend(entries)

    # Sort by stored_at, newest first
    all_entries.sort(key=lambda e: e.get("stored_at", ""), reverse=True)
    recent = all_entries[:top_k]

    # Apply privacy filter
    llm_context, local_context = filter_for_llm(recent, config)
    blocked = count_blocked(recent, config)

    # Include master index overview
    master = load_master_index()

    return {
        "llm_context": llm_context,
        "local_context": local_context,
        "blocked_count": blocked,
        "branch_used": "all",
        "confidence": 1.0,
        "query": recent_context or "(startup — most recent)",
        "override": False,
        "search_mode": "recency",
        "no_match": len(recent) == 0,
        "result_count": len(recent),
        "branches_overview": {
            path: info.get("summary", "")
            for path, info in master.get("branches", {}).items()
        },
    }


# ─── SUMMARY RECALL ──────────────────────────────────────────

def recall_from_summary(branch_path: str) -> dict:
    """
    Load just the branch summary — no entry search.
    Fast — no embedding, no search, just file read.
    """
    config = load_config()
    branch_index = load_branch_index(branch_path)
    tier = get_tier(branch_path, config)

    if tier == "locked":
        from encryption import is_unlocked
        if not is_unlocked(branch_path):
            return {"error": "Branch is locked", "branch": branch_path}

    entries_dir_path = None
    try:
        from branch_manager import get_entries_dir
        import os
        entries_dir_path = get_entries_dir(branch_path)
        entry_count = len([
            f for f in os.listdir(entries_dir_path) if f.endswith(".json")
        ]) if os.path.exists(entries_dir_path) else 0
    except Exception:
        entry_count = 0

    branch_dir = None
    try:
        from branch_manager import get_branch_dir
        import os
        branch_dir = get_branch_dir(branch_path)
        sub_branches = [
            d for d in os.listdir(branch_dir)
            if os.path.isdir(os.path.join(branch_dir, d))
            and d != "entries" and not d.startswith(".")
        ] if os.path.exists(branch_dir) else []
    except Exception:
        sub_branches = []

    return {
        "summary": branch_index.get("summary", ""),
        "entry_count": entry_count,
        "branch": branch_path,
        "tier": tier,
        "sub_branches": sub_branches,
    }


def recall_deep(query: str, branch_path: str, top_k: int = 10) -> dict:
    """
    Deep search within a specific branch — thorough mode.
    Equivalent to recall(query, top_k=10, branch=branch_path, override=True)
    """
    return recall(query, top_k=top_k, branch=branch_path, override=True)


# ─── WHAT DO I KNOW? ─────────────────────────────────────────

def what_do_i_know(topic: str = None) -> dict:
    """
    High-level overview of the agent's knowledge.

    If topic provided: find the most relevant branch and its details.
    If no topic: return the full Master Index overview.
    """
    config = load_config()
    master = load_master_index()

    if not topic:
        branches = []
        for path, info in master.get("branches", {}).items():
            tier = get_tier(path, config)
            branches.append({
                "path": path,
                "summary": info.get("summary", "") if tier != "locked" else "(locked)",
                "entry_count": info.get("entry_count", 0),
                "tier": tier,
                "sub_branches": info.get("sub_branches", []),
            })

        return {
            "total_entries": master.get("total_entries", 0),
            "total_branches": len(branches),
            "branches": branches,
        }

    # Topic provided — find the best matching branch
    routing = route_query(topic)
    if routing["branch"]:
        summary = recall_from_summary(routing["branch"])
        summary["confidence"] = routing["confidence"]
        summary["related_branches"] = [
            {"branch": alt["branch"], "score": alt["score"]}
            for alt in routing.get("alternatives", [])
        ]
        return summary

    # No good match
    return {
        "no_match": True,
        "query": topic,
        "message": "I don't have a specific branch for this topic.",
    }


# ─── ROUTING ─────────────────────────────────────────────────

def route_query(query: str) -> dict:
    """
    Determine which branch a query should be routed to.

    Method priority:
    1. Alias match (exact keyword → branch, fast)
    2. Semantic match (meaning → branch, requires embedding)
    3. No match → search all branches

    Returns:
        {
            "branch": "path/to/branch" or None,
            "confidence": 0.0-1.0,
            "method": "alias" | "semantic" | "none",
            "alternatives": [{branch, score}],
            "should_ask": True if ambiguous
        }
    """
    config = load_config()
    defaults = config.get("defaults", {})
    confidence_threshold = defaults.get("confidence_threshold", 0.75)
    ambiguity_gap = defaults.get("ambiguity_gap", 0.1)

    # 1. Try alias match first
    alias_matches = find_branches_by_query(query)
    if alias_matches:
        return {
            "branch": alias_matches[0],
            "confidence": 1.0,
            "method": "alias",
            "alternatives": [{"branch": m, "score": 1.0} for m in alias_matches[1:]],
            "should_ask": len(alias_matches) > 1,
        }

    # 2. Try semantic routing
    try:
        query_embedding = embed_text(query)
        if query_embedding:
            # Get all branch summaries and embed them
            branch_embeddings = {}
            for branch_path in list_branches():
                branch_index = load_branch_index(branch_path)
                summary = branch_index.get("summary", "")
                if summary:
                    summary_emb = embed_text(summary)
                    if summary_emb:
                        branch_embeddings[branch_path] = summary_emb

            if branch_embeddings:
                matches = search_by_branch_summary(query_embedding, branch_embeddings)
                if matches:
                    best = matches[0]
                    alternatives = matches[1:3]  # top 2 alternatives

                    # Check confidence
                    should_ask = False
                    if best["score"] < confidence_threshold:
                        # Low confidence — search all
                        return {
                            "branch": None,
                            "confidence": best["score"],
                            "method": "semantic",
                            "alternatives": alternatives,
                            "should_ask": True,
                        }

                    # Check for ambiguity
                    if len(matches) > 1:
                        gap = best["score"] - matches[1]["score"]
                        if gap < ambiguity_gap:
                            should_ask = True

                    return {
                        "branch": best["branch"],
                        "confidence": best["score"],
                        "method": "semantic",
                        "alternatives": alternatives,
                        "should_ask": should_ask,
                    }
    except Exception:
        pass

    # 3. No match
    return {
        "branch": None,
        "confidence": 0.0,
        "method": "none",
        "alternatives": [],
        "should_ask": False,
    }


# ─── FORMATTING ──────────────────────────────────────────────

def format_for_context(llm_context: List[dict], include_branch: bool = True) -> str:
    """
    Format llm_context entries into text ready for the LLM context window.

    This is what actually goes to the LLM.
    Includes a last-line blocklist scan — if any private data somehow
    made it through the privacy filter, it gets redacted here.
    """
    if not llm_context:
        return ""

    parts = []
    for entry in llm_context:
        if entry.get("_is_summary"):
            parts.append(f"[{entry['branch']} — summary] {entry['content']}")
        elif include_branch:
            parts.append(f"[{entry.get('branch', 'unknown')}] {entry.get('content', '')}")
        else:
            parts.append(entry.get("content", ""))

    text = "\n\n".join(parts)

    # LAST-LINE DEFENSE: scan for blocklist terms before LLM sees this
    cleaned, violations = scan_for_llm(text)
    if violations:
        # Log the violation (best-effort) so we know if the filter has gaps
        try:
            from entry_manager import _fire_event
            _fire_event("content_guard_redacted", {
                "violations": [v["term"] for v in violations],
                "context": "format_for_context",
            })
        except Exception:
            pass
    return cleaned


def format_for_agent(local_context: List[dict]) -> str:
    """
    Format local_context entries for the agent's internal reasoning.
    Marks LOCAL entries with clear warnings.
    """
    if not local_context:
        return ""

    parts = []
    for entry in local_context:
        tier = entry.get("_tier", "open")
        branch = entry.get("branch", "unknown")
        content = entry.get("content", "")

        if tier == "local":
            parts.append(f"[LOCAL — do not send to LLM] [{branch}] {content}")
        elif entry.get("_is_summary"):
            parts.append(f"[{tier.upper()}] [{branch} — summary] {content}")
        else:
            parts.append(f"[{tier.upper()}] [{branch}] {content}")

    return "\n\n".join(parts)


# ─── RECALL TRACKING ────────────────────────────────────────

import os as _os

RECALL_LOG_PATH = _os.path.join(_os.path.dirname(__file__), "recall_log.json")


def _record_recall_hit(entry_id: str, branch: str, query: str) -> None:
    """
    Record that an entry was returned by recall().
    Stores: entry_id, branch, query, timestamp.
    This data feeds back into importance scoring over time.
    """
    if not entry_id or entry_id == "_summary":
        return

    log = _load_recall_log()

    key = f"{branch}/{entry_id}"
    if key not in log:
        log[key] = {"entry_id": entry_id, "branch": branch,
                     "hit_count": 0, "queries": [], "first_hit": None, "last_hit": None}

    now = _recall_now()
    record = log[key]
    record["hit_count"] += 1
    record["last_hit"] = now
    if record["first_hit"] is None:
        record["first_hit"] = now

    # Keep last 10 queries (don't bloat the log)
    record["queries"].append({"q": query[:100], "at": now})
    record["queries"] = record["queries"][-10:]

    _save_recall_log(log)


def get_recall_stats(entry_id: str = None, branch: str = None) -> dict:
    """
    Get recall statistics.

    If entry_id + branch: stats for one entry.
    If branch only: stats for all entries in that branch.
    If neither: global stats.

    Returns:
        {
            "total_recalls": int,
            "most_recalled": [{"entry_id", "branch", "hit_count"}],
            "never_recalled": [{"entry_id", "branch"}],
            "entries": {key: {hit_count, last_hit, ...}}
        }
    """
    log = _load_recall_log()

    if entry_id and branch:
        key = f"{branch}/{entry_id}"
        return log.get(key, {"hit_count": 0, "queries": []})

    # Filter by branch if specified
    entries = log
    if branch:
        entries = {k: v for k, v in log.items() if v.get("branch") == branch}

    total_recalls = sum(v["hit_count"] for v in entries.values())
    sorted_by_hits = sorted(entries.values(), key=lambda x: x["hit_count"], reverse=True)

    # Find entries that exist but were never recalled
    never_recalled = []
    try:
        from entry_manager import list_entries as _list_entries
        branches_to_check = [branch] if branch else list_branches()
        for b in branches_to_check:
            for entry in _list_entries(b, include_outdated=False):
                key = f"{b}/{entry['id']}"
                if key not in log:
                    never_recalled.append({"entry_id": entry["id"], "branch": b})
    except Exception:
        pass

    return {
        "total_recalls": total_recalls,
        "most_recalled": sorted_by_hits[:10],
        "never_recalled": never_recalled[:20],
        "entry_count_tracked": len(entries),
    }


def _load_recall_log() -> dict:
    """Load the recall log from disk."""
    if not _os.path.exists(RECALL_LOG_PATH):
        return {}
    try:
        with open(RECALL_LOG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_recall_log(log: dict) -> None:
    """Save the recall log to disk."""
    with open(RECALL_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def _recall_now() -> str:
    return datetime.now(timezone.utc).isoformat()
