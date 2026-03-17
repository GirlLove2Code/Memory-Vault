"""
Vivioo Memory — Entry Manager (Steps 2-3)
CRUD operations for individual memory entries.

Each entry is a JSON file in its branch's entries/ directory.
Entries are the "books" in the library — the full memory content.
"""

import os
import json
import re
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone

from branch_manager import (
    get_entries_dir, load_branch_index, save_branch_index,
    _update_master_index_entry, _now
)


def add_memory(branch: str, content: str, happened_at: str = None,
               tags: List[str] = None, source: str = None,
               auto_resolve: bool = True,
               importance: int = None) -> dict:
    """
    Add a new memory entry to a branch.

    If auto_resolve is True (default), checks for conflicting entries
    in the same branch. If a highly similar entry exists, it gets
    auto-marked as outdated and linked to the new entry.

    Importance is auto-scored (1-5) unless manually set.

    Args:
        branch: branch path, e.g. "knowledge-base/marketing"
        content: the memory text
        happened_at: when this actually happened (ISO string)
                     defaults to now if not provided
        tags: optional tags for extra context
        source: where this memory came from (e.g. "conversation", "observation")
        auto_resolve: if True, detect and auto-outdated conflicting entries
        importance: manual override (1-5). None = auto-score.

    Returns:
        The created entry dict with id.
        If conflicts were resolved, entry["_resolved"] lists outdated entry IDs.
    """
    # --- CONTENT GUARD: check for private data in Open branches ---
    try:
        from content_guard import check_before_save
        guard_result = check_before_save(content, branch)
        if not guard_result["allowed"]:
            raise ValueError(guard_result["warning"])
    except ImportError:
        pass  # content_guard not installed — skip check

    entries_dir = get_entries_dir(branch)
    os.makedirs(entries_dir, exist_ok=True)

    now = _now()
    entry_id = f"mem-{int(time.time() * 1000)}"

    entry = {
        "id": entry_id,
        "branch": branch,
        "content": content,
        "stored_at": now,
        "happened_at": happened_at or now,
        "tags": tags or [],
        "source": source or "manual",
        "_outdated": False,
        "_outdated_reason": None,
        "_supersedes": [],  # IDs of entries this one replaces
    }

    # --- IMPORTANCE SCORING ---
    if importance is not None:
        entry["_importance"] = max(1, min(5, importance))
        entry["_importance_source"] = "manual"
    else:
        score_result = score_importance(entry, branch)
        entry["_importance"] = score_result["score"]
        entry["_importance_source"] = "auto"
        entry["_importance_signals"] = score_result["signals"]

    # --- CONFLICT DETECTION ---
    resolved_ids = []
    if auto_resolve:
        conflicts = find_conflicts(branch, content)
        for conflict in conflicts:
            old_id = conflict["id"]
            mark_outdated(
                old_id, branch,
                reason=f"Superseded by {entry_id}"
            )
            # Link the old entry to the new one
            _link_superseded(old_id, branch, entry_id)
            resolved_ids.append(old_id)
            entry["_supersedes"].append(old_id)

    # --- AUTO-EXPIRY ---
    try:
        from expiry import _detect_expiry_days
        from datetime import timedelta as _td
        expiry_days = _detect_expiry_days(content)
        stored_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        entry["_expires_at"] = (stored_dt + _td(days=expiry_days)).isoformat()
        entry["_expiry_days"] = expiry_days
    except Exception:
        entry["_expires_at"] = None
        entry["_expiry_days"] = None

    # Save entry
    entry_path = os.path.join(entries_dir, f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    # Sync to vector store (if embeddings available)
    _sync_to_vectors(entry)

    # Update branch index
    branch_index = load_branch_index(branch)
    branch_index["last_updated"] = now
    save_branch_index(branch, branch_index)

    # Update master index
    _update_master_index_entry(branch, branch_index)

    if resolved_ids:
        entry["_resolved"] = resolved_ids

    # --- FIRE HOOKS ---
    _fire_event("memory_added", {
        "entry_id": entry_id, "branch": branch,
        "content": content[:150], "source": entry["source"],
        "importance": entry.get("_importance", 3),
    })
    if resolved_ids:
        _fire_event("memory_conflict", {
            "entry_id": entry_id, "branch": branch,
            "resolved_ids": resolved_ids, "content": content[:150],
        })

    return entry


def get_entry(entry_id: str, branch: str) -> Optional[dict]:
    """
    Get a single entry by ID and branch.

    Args:
        entry_id: the entry's unique ID
        branch: the branch path

    Returns:
        Entry dict or None if not found
    """
    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    if not os.path.exists(entry_path):
        return None

    with open(entry_path, "r") as f:
        return json.load(f)


def update_memory(entry_id: str, branch: str, content: str) -> Optional[dict]:
    """
    Update an entry's content.

    Args:
        entry_id: the entry's unique ID
        branch: the branch path
        content: new content text

    Returns:
        Updated entry dict or None if not found
    """
    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    entry["content"] = content
    entry["stored_at"] = _now()  # update timestamp

    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    return entry


def delete_memory(entry_id: str, branch: str) -> bool:
    """
    Delete an entry permanently.

    Args:
        entry_id: the entry's unique ID
        branch: the branch path

    Returns:
        True if deleted, False if not found
    """
    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    if not os.path.exists(entry_path):
        return False

    os.remove(entry_path)

    # Update branch and master index
    branch_index = load_branch_index(branch)
    branch_index["last_updated"] = _now()
    save_branch_index(branch, branch_index)
    _update_master_index_entry(branch, branch_index)

    return True


def mark_outdated(entry_id: str, branch: str, reason: str = None) -> Optional[dict]:
    """
    Mark an entry as outdated WITHOUT deleting it.

    The entry stays in the store but:
    - Gets deprioritized in search results (scored lower)
    - Tagged with _outdated: True
    - The agent can still access it but knows it's old info

    Use when: info changed, correction happened, strategy shifted.

    Args:
        entry_id: the entry's unique ID
        branch: the branch path
        reason: why it's outdated (optional)

    Returns:
        Updated entry dict or None if not found
    """
    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    entry["_outdated"] = True
    entry["_outdated_reason"] = reason
    entry["_outdated_at"] = _now()

    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    _fire_event("memory_outdated", {
        "entry_id": entry_id, "branch": branch,
        "reason": reason, "content": entry.get("content", "")[:150],
    })

    return entry


def unmark_outdated(entry_id: str, branch: str) -> Optional[dict]:
    """Remove the outdated flag — entry becomes active again."""
    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    entry["_outdated"] = False
    entry["_outdated_reason"] = None
    entry.pop("_outdated_at", None)

    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    return entry


def pin_memory(entry_id: str, branch: str) -> Optional[dict]:
    """
    Pin a memory — sets importance to 5 (max) permanently.
    Use for critical decisions, architecture choices, rules that must persist.
    """
    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    entry["_importance"] = 5
    entry["_importance_source"] = "pinned"
    entry["_pinned_at"] = _now()

    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    _fire_event("memory_pinned", {
        "entry_id": entry_id, "branch": branch,
        "content": entry.get("content", "")[:150],
    })

    return entry


def unpin_memory(entry_id: str, branch: str) -> Optional[dict]:
    """Unpin a memory — re-scores importance automatically."""
    entry = get_entry(entry_id, branch)
    if entry is None:
        return None

    score_result = score_importance(entry, branch)
    entry["_importance"] = score_result["score"]
    entry["_importance_source"] = "auto"
    entry["_importance_signals"] = score_result["signals"]
    entry.pop("_pinned_at", None)

    entry_path = os.path.join(get_entries_dir(branch), f"{entry_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)

    return entry


# ─── IMPORTANCE SCORING ─────────────────────────────────────

# Decision words — content with these likely records a choice that matters
_DECISION_PATTERNS = [
    r'\bswitched\s+(to|from)\b', r'\bchanged\s+to\b', r'\breplaced\b',
    r'\bdecided\b', r'\bchose\b', r'\bmoved\s+(to|from)\b',
    r'\bremoved\b', r'\badded\b', r'\bdeployed\b', r'\bshipped\b',
    r'\blaunched\b', r'\bfixed\b', r'\bbroke\b', r'\bblocked\b',
    r'\bcritical\b', r'\bmust\b', r'\bnever\b', r'\balways\b',
    r'\brule:\b', r'\brequirement\b',
]

# High-value sources — agents observing > manual notes > auto-logs
_SOURCE_SCORES = {
    "agent": 1.0,          # Agent observed this directly
    "agent-observation": 1.0,
    "observation": 0.8,
    "decision": 1.0,       # Explicit decision record
    "manual": 0.5,         # Someone typed this in
    "conversation": 0.3,   # Captured from chat
    "auto-capture": 0.0,   # Routine log, lowest value
    "auto": 0.0,
}


def score_importance(entry: dict, branch: str) -> dict:
    """
    Auto-score a memory's importance (1-5) based on signals.

    Signals checked:
    1. Source type (agent observation > manual > auto)
    2. Decision language (contains words like "switched", "deployed", "critical")
    3. Specificity (short + dense > long + vague)
    4. Has tags (someone cared enough to categorize)
    5. Uniqueness (fewer entries in branch = each one matters more)

    Returns:
        {"score": 1-5, "signals": ["source:agent", "decision_language", ...]}
    """
    content = entry.get("content", "")
    source = entry.get("source", "manual")
    tags = entry.get("tags", [])

    raw_score = 1.0  # Base score — everything starts at 1
    signals = []

    # Signal 1: Source type
    source_bonus = _SOURCE_SCORES.get(source, 0.3)
    if source_bonus >= 0.8:
        raw_score += 1.0
        signals.append(f"source:{source}")
    elif source_bonus >= 0.5:
        raw_score += 0.5
        signals.append(f"source:{source}")

    # Signal 2: Decision language
    content_lower = content.lower()
    decision_matches = sum(
        1 for p in _DECISION_PATTERNS if re.search(p, content_lower)
    )
    if decision_matches >= 3:
        raw_score += 1.5
        signals.append("strong_decision_language")
    elif decision_matches >= 1:
        raw_score += 0.75
        signals.append("decision_language")

    # Signal 3: Specificity — short and dense beats long and vague
    words = content.split()
    word_count = len(words)
    if 10 <= word_count <= 80:
        # Sweet spot — specific enough to be useful, not a wall of text
        raw_score += 0.5
        signals.append("specific")
    elif word_count > 200:
        # Very long — probably a dump, less focused
        raw_score -= 0.5
        signals.append("verbose")

    # Signal 4: Has tags
    if tags:
        raw_score += 0.5
        signals.append(f"tagged:{len(tags)}")

    # Signal 5: Uniqueness — if branch has few entries, each matters more
    try:
        existing = list_entries(branch, include_outdated=False)
        active_count = len(existing)
        if active_count <= 3:
            raw_score += 0.75
            signals.append("rare_in_branch")
        elif active_count <= 10:
            raw_score += 0.25
            signals.append("moderate_branch")
    except Exception:
        pass

    # Clamp to 1-5
    final_score = max(1, min(5, round(raw_score)))

    return {"score": final_score, "signals": signals}


def list_entries(branch: str, include_outdated: bool = True) -> List[dict]:
    """
    List all entries in a branch.

    Args:
        branch: the branch path
        include_outdated: if False, excludes outdated entries

    Returns:
        List of entry dicts, sorted by stored_at (newest first)
    """
    entries_dir = get_entries_dir(branch)
    if not os.path.exists(entries_dir):
        return []

    entries = []
    for filename in os.listdir(entries_dir):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(entries_dir, filename), "r") as f:
            entry = json.load(f)
            if not include_outdated and entry.get("_outdated"):
                continue
            entries.append(entry)

    entries.sort(key=lambda e: e.get("stored_at", ""), reverse=True)
    return entries


def _stem(word: str) -> str:
    """
    Simple suffix-stripping stemmer. No dependencies required.
    Reduces words to a root form so 'launching' matches 'launch'.
    """
    if len(word) <= 3:
        return word
    # Order matters — check longest suffixes first
    for suffix in ("ation", "ting", "ment", "ness", "able", "ible", "ally",
                   "ful", "less", "ing", "ied", "ies", "ion", "ous",
                   "ive", "ers", "est", "ely", "ity",
                   "ly", "ed", "er", "al", "en", "es", "ty", "ry", "or", "ar",
                   "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


# Common stop words to skip during keyword search
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "than",
    "after", "before", "between", "through", "during", "and", "but",
    "or", "nor", "not", "so", "yet", "both", "either", "neither",
    "it", "its", "i", "me", "my", "we", "our", "you", "your", "he",
    "she", "they", "them", "his", "her", "this", "that", "what", "how",
})


def search_entries(query: str, branch: str = None) -> List[dict]:
    """
    Keyword search across entries — FALLBACK when vector search is unavailable.

    Features:
    - Case-insensitive matching
    - Partial/stem matching ('launch' finds 'launching')
    - Tag matching (query words checked against entry tags)
    - Stop word filtering (ignores 'the', 'is', 'a', etc.)

    Args:
        query: search text
        branch: if provided, search only this branch. Otherwise search all.

    Returns:
        List of matching entries with a basic relevance score
    """
    from branch_manager import list_branches

    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if w not in _STOP_WORDS]
    if not query_words:
        query_words = query_lower.split()  # If all stop words, use them anyway
    query_stems = [_stem(w) for w in query_words]

    results = []
    branches_to_search = [branch] if branch else list_branches()

    for b in branches_to_search:
        for entry in list_entries(b):
            content_lower = entry.get("content", "").lower()
            content_words = content_lower.split()
            content_stems = [_stem(w.strip(".,;:!?\"'()[]")) for w in content_words]
            tags_lower = [t.lower() for t in entry.get("tags", [])]

            score = 0.0
            matched = 0

            for i, qw in enumerate(query_words):
                qs = query_stems[i]

                # Exact substring match (strongest signal)
                if qw in content_lower:
                    score += 1.0
                    matched += 1
                # Stem match ('launch' matches 'launching')
                elif qs in content_stems:
                    score += 0.75
                    matched += 1
                # Tag match
                elif qw in tags_lower or qs in [_stem(t) for t in tags_lower]:
                    score += 0.5
                    matched += 1

            if matched > 0:
                # Normalize by query length, bonus for matching more words
                relevance = score / len(query_words)
                coverage = matched / len(query_words)
                final_score = relevance * 0.7 + coverage * 0.3
                results.append({**entry, "score": round(final_score, 4)})

    # Sort by score descending
    results.sort(key=lambda e: e.get("score", 0), reverse=True)
    return results


def find_conflicts(branch: str, content: str,
                    threshold: float = 0.82) -> List[dict]:
    """
    Find existing entries in a branch that conflict with new content.

    Uses two strategies:
    1. Semantic similarity (if Ollama available) — finds entries that say
       roughly the same thing, even with different wording.
    2. Keyword overlap fallback — checks if >60% of significant words match.

    Only checks active (non-outdated) entries.

    Args:
        branch: the branch to search
        content: the new memory content to check against
        threshold: similarity score above which = conflict (default 0.82)

    Returns:
        List of conflicting entry dicts, sorted by similarity (highest first).
        Each entry gets a "conflict_score" field added.
    """
    active_entries = list_entries(branch, include_outdated=False)
    if not active_entries:
        return []

    conflicts = []

    # Strategy 1: Semantic similarity
    try:
        from embedding import embed_text
        new_embedding = embed_text(content)
        if new_embedding:
            for entry in active_entries:
                enriched = get_enriched_text(entry)
                entry_embedding = embed_text(enriched)
                if entry_embedding:
                    score = _cosine_similarity(new_embedding, entry_embedding)
                    if score >= threshold:
                        entry["conflict_score"] = round(score, 4)
                        conflicts.append(entry)
            if conflicts:
                conflicts.sort(key=lambda e: e["conflict_score"], reverse=True)
                return conflicts
            # Semantic search worked but found no conflicts
            return []
    except Exception:
        pass

    # Strategy 2: Keyword overlap fallback
    new_words = _significant_words(content)
    if not new_words:
        return []

    for entry in active_entries:
        old_words = _significant_words(entry.get("content", ""))
        if not old_words:
            continue
        overlap = len(new_words & old_words) / max(len(new_words), len(old_words))
        if overlap >= 0.6:
            entry["conflict_score"] = round(overlap, 4)
            conflicts.append(entry)

    conflicts.sort(key=lambda e: e["conflict_score"], reverse=True)
    return conflicts


def _significant_words(text: str, min_length: int = 4) -> set:
    """Extract significant words (skip short common words)."""
    stop_words = {
        "this", "that", "with", "from", "have", "been", "were", "they",
        "their", "about", "would", "could", "should", "into", "also",
        "more", "than", "then", "when", "what", "which", "there",
        "some", "other", "just", "only", "very", "will", "each",
    }
    words = set()
    for word in text.lower().split():
        # Strip punctuation
        cleaned = ''.join(c for c in word if c.isalnum())
        if len(cleaned) >= min_length and cleaned not in stop_words:
            words.add(cleaned)
    return words


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _link_superseded(old_id: str, branch: str, new_id: str) -> None:
    """Add a forward link on the old entry pointing to what replaced it."""
    entry = get_entry(old_id, branch)
    if entry is None:
        return
    entry.setdefault("_superseded_by", [])
    if new_id not in entry["_superseded_by"]:
        entry["_superseded_by"].append(new_id)
    entry_path = os.path.join(get_entries_dir(branch), f"{old_id}.json")
    with open(entry_path, "w") as f:
        json.dump(entry, f, indent=2)


def _sync_to_vectors(entry: dict) -> None:
    """Sync a new entry to the vector store if embeddings are available."""
    try:
        from embedding import embed_text
        from vector_store import init_store, add_entry as vs_add_entry

        enriched = get_enriched_text(entry)
        embedding = embed_text(enriched)
        if embedding:
            init_store()
            metadata = {
                "branch": entry.get("branch", ""),
                "stored_at": entry.get("stored_at", ""),
                "happened_at": entry.get("happened_at", ""),
                "tags": entry.get("tags", []),
                "_outdated": entry.get("_outdated", False),
            }
            vs_add_entry(entry["id"], embedding, metadata, enriched)
    except Exception:
        pass  # Vector sync is best-effort — JSON is source of truth


def get_enriched_text(entry: dict) -> str:
    """
    Create enriched text for embedding — blends branch labels into content.

    Example:
        Raw: "The builder prefers story-first campaigns"
        Enriched: "knowledge base, marketing: The builder prefers story-first campaigns"

    This ensures semantic search works even when queries don't use
    the exact branch terminology.
    """
    branch = entry.get("branch", "")
    content = entry.get("content", "")
    tags = entry.get("tags", [])

    # Convert branch path to readable labels
    labels = branch.replace("/", ", ").replace("-", " ")

    # Add tags if present
    if tags:
        labels += ", " + ", ".join(tags)

    return f"{labels}: {content}"


# ─── HOOK HELPER ────────────────────────────────────────────

def _fire_event(event: str, data: dict) -> None:
    """Fire hooks if the hooks module is available. Best-effort."""
    try:
        from hooks import fire_hooks
        fire_hooks(event, data)
    except Exception:
        pass  # Hooks are optional — never break core operations
