"""
Core tests for the Vivioo Memory System.
Tests the pipeline without requiring Ollama (uses keyword fallback).

Run: python -m pytest tests/test_core.py -v
Or:  cd vivioo-memory && python tests/test_core.py
"""

import os
import sys
import json
import shutil
import tempfile

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestSetup:
    """Create a temporary test environment."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vivioo_test_")
        self.branches_dir = os.path.join(self.tmpdir, "branches")
        self.vectors_dir = os.path.join(self.tmpdir, "vectors")
        self.config_path = os.path.join(self.tmpdir, "config.json")
        self.master_index_path = os.path.join(self.tmpdir, "master_index.json")

        os.makedirs(self.branches_dir, exist_ok=True)
        os.makedirs(self.vectors_dir, exist_ok=True)

        # Write config
        config = {
            "security_tiers": {},
            "defaults": {
                "default_tier": "open",
                "min_similarity_threshold": 0.65,
                "recency_weight": 0.15,
                "recency_fade_days": 90,
                "outdated_penalty": 0.5,
                "confidence_threshold": 0.75,
                "ambiguity_gap": 0.1,
                "embedding_model": "nomic-embed-text",
            },
            "branch_security": {},
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f)

        # Patch module paths
        import branch_manager
        import entry_manager
        import privacy_filter

        branch_manager.BASE_DIR = self.branches_dir
        branch_manager.MASTER_INDEX_PATH = self.master_index_path
        privacy_filter.CONFIG_PATH = self.config_path

    def cleanup(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def test_privacy_filter():
    """Privacy filter splits entries by tier correctly."""
    from privacy_filter import filter_for_llm, set_tier, load_config

    env = TestSetup()
    try:
        config = load_config(env.config_path)
        set_tier("company-1", "local", config, env.config_path)
        set_tier("health", "locked", config, env.config_path)
        config = load_config(env.config_path)

        entries = [
            {"id": "1", "branch": "knowledge-base", "content": "public info"},
            {"id": "2", "branch": "company-1", "content": "private revenue"},
            {"id": "3", "branch": "health", "content": "medical data"},
        ]

        llm, local = filter_for_llm(entries, config)

        # LLM should only see open entries
        assert len(llm) == 1, f"LLM should see 1 entry, got {len(llm)}"
        assert llm[0]["id"] == "1"
        assert llm[0]["_tier"] == "open"

        # Local should see open + local (not locked)
        assert len(local) == 2, f"Local should see 2 entries, got {len(local)}"
        local_ids = {e["id"] for e in local}
        assert "1" in local_ids  # open
        assert "2" in local_ids  # local
        assert "3" not in local_ids  # locked — blocked

        print("  PASS: Privacy filter splits correctly")
    finally:
        env.cleanup()


def test_tier_inheritance():
    """Sub-branches inherit parent tier."""
    from privacy_filter import get_tier, set_tier, load_config

    env = TestSetup()
    try:
        config = load_config(env.config_path)
        set_tier("company-1", "local", config, env.config_path)
        config = load_config(env.config_path)

        # Sub-branch should inherit
        tier = get_tier("company-1/finances", config)
        assert tier == "local", f"Expected 'local', got '{tier}'"

        # Unrelated branch should be default
        tier = get_tier("knowledge-base", config)
        assert tier == "open", f"Expected 'open', got '{tier}'"

        print("  PASS: Tier inheritance works")
    finally:
        env.cleanup()


def test_branch_creation():
    """Creating branches builds correct directory structure."""
    from branch_manager import create_branch, load_branch_index, list_branches

    env = TestSetup()
    try:
        create_branch("knowledge-base", aliases=["kb"], summary="General knowledge")
        create_branch("knowledge-base/marketing", aliases=["marketing", "growth"],
                       summary="Marketing strategies")

        # Check index
        idx = load_branch_index("knowledge-base")
        assert idx["summary"] == "General knowledge"
        assert "kb" in idx["aliases"]

        idx2 = load_branch_index("knowledge-base/marketing")
        assert "marketing" in idx2["aliases"]

        # Check listing
        branches = list_branches()
        assert "knowledge-base" in branches
        assert "knowledge-base/marketing" in branches

        print("  PASS: Branch creation works")
    finally:
        env.cleanup()


def test_alias_routing():
    """Alias matching finds the right branch."""
    from branch_manager import create_branch, find_branch_by_alias

    env = TestSetup()
    try:
        create_branch("knowledge-base/marketing", aliases=["marketing", "growth"])
        create_branch("company-1", aliases=["alias-1"])

        assert find_branch_by_alias("marketing") == "knowledge-base/marketing"
        assert find_branch_by_alias("alias-1") == "company-1"
        assert find_branch_by_alias("unknown") is None

        print("  PASS: Alias routing works")
    finally:
        env.cleanup()


def test_entry_crud():
    """Add, get, update, delete entries."""
    from branch_manager import create_branch
    from entry_manager import add_memory, get_entry, update_memory, delete_memory, list_entries

    env = TestSetup()
    try:
        create_branch("test-branch")

        # Add
        entry = add_memory("test-branch", "First memory", tags=["test"])
        assert entry["content"] == "First memory"
        assert entry["id"].startswith("mem-")

        # Get
        fetched = get_entry(entry["id"], "test-branch")
        assert fetched is not None
        assert fetched["content"] == "First memory"

        # Update
        updated = update_memory(entry["id"], "test-branch", "Updated memory")
        assert updated["content"] == "Updated memory"

        # List
        entries = list_entries("test-branch")
        assert len(entries) == 1

        # Delete
        assert delete_memory(entry["id"], "test-branch")
        assert get_entry(entry["id"], "test-branch") is None

        print("  PASS: Entry CRUD works")
    finally:
        env.cleanup()


def test_mark_outdated():
    """Outdated marking and unmarking."""
    from branch_manager import create_branch
    from entry_manager import add_memory, mark_outdated, unmark_outdated, list_entries

    env = TestSetup()
    try:
        create_branch("test-branch")
        entry = add_memory("test-branch", "Will be outdated")

        # Mark outdated
        updated = mark_outdated(entry["id"], "test-branch", "Info changed")
        assert updated["_outdated"] is True
        assert updated["_outdated_reason"] == "Info changed"

        # Exclude from listing
        active = list_entries("test-branch", include_outdated=False)
        assert len(active) == 0

        # Include in listing
        all_entries = list_entries("test-branch", include_outdated=True)
        assert len(all_entries) == 1

        # Unmark
        restored = unmark_outdated(entry["id"], "test-branch")
        assert restored["_outdated"] is False

        print("  PASS: Outdated marking works")
    finally:
        env.cleanup()


def test_keyword_search():
    """Keyword fallback search works."""
    from branch_manager import create_branch
    from entry_manager import add_memory, search_entries

    env = TestSetup()
    try:
        create_branch("test-branch")
        add_memory("test-branch", "The builder prefers story-first marketing campaigns")
        add_memory("test-branch", "Budget for Q1 was higher than expected")
        add_memory("test-branch", "New marketing strategy focuses on video")

        # Search
        results = search_entries("marketing", "test-branch")
        assert len(results) >= 2, f"Expected 2+ results, got {len(results)}"
        # All results should contain "marketing"
        for r in results:
            assert "marketing" in r["content"].lower()

        # Search with no match
        results = search_entries("zebra", "test-branch")
        assert len(results) == 0

        print("  PASS: Keyword search works")
    finally:
        env.cleanup()


def test_enriched_text():
    """Enriched text includes branch labels."""
    from entry_manager import get_enriched_text

    entry = {
        "branch": "knowledge-base/marketing",
        "content": "The builder prefers story-first campaigns",
        "tags": ["strategy"],
    }
    enriched = get_enriched_text(entry)
    assert "knowledge base" in enriched
    assert "marketing" in enriched
    assert "strategy" in enriched
    assert "The builder prefers" in enriched

    print("  PASS: Enriched text works")


def test_quality_filter():
    """Quality filter applies threshold, recency, and outdated penalty."""
    from recall import apply_quality_filters
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=80)).isoformat()

    results = [
        {"id": "1", "score": 0.85, "stored_at": yesterday, "_outdated": False,
         "content": "Fresh relevant memory"},
        {"id": "2", "score": 0.82, "stored_at": old, "_outdated": True,
         "content": "Old outdated memory"},
        {"id": "3", "score": 0.40, "stored_at": yesterday, "_outdated": False,
         "content": "Low relevance memory"},
    ]

    config = {
        "defaults": {
            "min_similarity_threshold": 0.65,
            "recency_weight": 0.15,
            "recency_fade_days": 90,
            "outdated_penalty": 0.5,
        }
    }

    filtered = apply_quality_filters(results, config)

    # Entry 3 should be dropped (below threshold)
    assert len(filtered) == 2, f"Expected 2 results, got {len(filtered)}"

    # Entry 1 should rank first (fresh + not outdated)
    assert filtered[0]["id"] == "1"

    # Entry 2 should rank second (outdated penalty)
    assert filtered[1]["id"] == "2"
    assert filtered[1]["score"] < filtered[0]["score"]

    print("  PASS: Quality filter works correctly")


def test_no_match_detection():
    """When all results are below threshold, no_match is True."""
    from recall import apply_quality_filters

    results = [
        {"id": "1", "score": 0.30, "stored_at": "2026-03-12T00:00:00+00:00",
         "_outdated": False, "content": "Irrelevant"},
    ]

    config = {"defaults": {"min_similarity_threshold": 0.65,
                           "recency_weight": 0.15, "recency_fade_days": 90,
                           "outdated_penalty": 0.5}}

    filtered = apply_quality_filters(results, config)
    assert len(filtered) == 0, "All results should be dropped"

    print("  PASS: No-match detection works")


def test_conflict_detection_keyword():
    """Conflict detection finds similar entries by keyword overlap."""
    from branch_manager import create_branch
    from entry_manager import add_memory, find_conflicts, list_entries

    env = TestSetup()
    try:
        create_branch("test-branch")

        # Add an entry
        add_memory("test-branch", "Costs guide has 6 sections including security and trust",
                   auto_resolve=False)

        # Check conflict with very similar content
        conflicts = find_conflicts(
            "test-branch",
            "Costs guide has 7 sections including security trust and the myth"
        )
        assert len(conflicts) >= 1, f"Expected 1+ conflicts, got {len(conflicts)}"
        assert conflicts[0].get("conflict_score", 0) >= 0.6

        # Check no conflict with unrelated content
        no_conflicts = find_conflicts("test-branch", "The weather is nice today in Paris")
        assert len(no_conflicts) == 0, f"Expected 0 conflicts, got {len(no_conflicts)}"

        print("  PASS: Conflict detection (keyword) works")
    finally:
        env.cleanup()


def test_auto_resolve_on_add():
    """Adding a similar memory auto-outdates the old one."""
    from branch_manager import create_branch
    from entry_manager import add_memory, get_entry, list_entries

    env = TestSetup()
    try:
        create_branch("test-branch")

        # Add original
        old = add_memory("test-branch",
                         "Deploy command uses vercel with temp directory and prod flag",
                         auto_resolve=False)

        # Add updated version — should auto-resolve the old one
        import time; time.sleep(0.01)  # ensure different timestamp
        new = add_memory("test-branch",
                         "Deploy command uses vercel with temp directory and prod flag and api folder",
                         auto_resolve=True)

        # Old entry should now be outdated
        old_entry = get_entry(old["id"], "test-branch")
        assert old_entry["_outdated"] is True, "Old entry should be outdated"
        assert new["id"] in (old_entry.get("_outdated_reason", "")), \
            "Outdated reason should reference the new entry"

        # New entry should link back
        assert old["id"] in new.get("_supersedes", []), \
            "New entry should list old in _supersedes"

        # Old entry should have forward link
        assert new["id"] in old_entry.get("_superseded_by", []), \
            "Old entry should have _superseded_by link"

        print("  PASS: Auto-resolve on add works")
    finally:
        env.cleanup()


def test_supersedes_chain():
    """Multiple updates create a chain: A → B → C."""
    from branch_manager import create_branch
    from entry_manager import add_memory, get_entry

    env = TestSetup()
    try:
        create_branch("test-branch")

        a = add_memory("test-branch",
                        "Project has 10 pages with React and Tailwind styling",
                        auto_resolve=False)
        import time; time.sleep(0.01)
        b = add_memory("test-branch",
                        "Project has 15 pages with React and Tailwind styling",
                        auto_resolve=True)
        time.sleep(0.01)
        c = add_memory("test-branch",
                        "Project has 20 pages with React and Tailwind styling",
                        auto_resolve=True)

        # A should be outdated (superseded by B)
        a_entry = get_entry(a["id"], "test-branch")
        assert a_entry["_outdated"] is True

        # B should be outdated (superseded by C)
        b_entry = get_entry(b["id"], "test-branch")
        assert b_entry["_outdated"] is True

        # C should be active
        c_entry = get_entry(c["id"], "test-branch")
        assert c_entry["_outdated"] is False

        print("  PASS: Supersedes chain works")
    finally:
        env.cleanup()


def test_importance_auto_score():
    """Importance scoring assigns higher scores to decision-heavy content."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch")

        # High importance: agent source + decision language
        high = add_memory(
            "test-branch",
            "Switched from session auth to JWT tokens and deployed the fix",
            source="agent", tags=["security", "auth"],
            auto_resolve=False
        )
        assert high["_importance"] >= 3, f"Expected 3+, got {high['_importance']}"
        assert high["_importance_source"] == "auto"
        assert "source:agent" in high.get("_importance_signals", [])

        # Low importance: auto-capture, no decision words
        low = add_memory(
            "test-branch",
            "Session started at 10am",
            source="auto-capture",
            auto_resolve=False
        )
        assert low["_importance"] <= 2, f"Expected <=2, got {low['_importance']}"

        # High should score higher than low
        assert high["_importance"] > low["_importance"]

        print("  PASS: Importance auto-scoring works")
    finally:
        env.cleanup()


def test_importance_manual_override():
    """Manual importance override takes precedence."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch")

        entry = add_memory(
            "test-branch", "Some routine info",
            importance=5, auto_resolve=False
        )
        assert entry["_importance"] == 5
        assert entry["_importance_source"] == "manual"

        print("  PASS: Manual importance override works")
    finally:
        env.cleanup()


def test_pin_memory():
    """Pinning sets importance to 5, unpinning re-scores."""
    from branch_manager import create_branch
    from entry_manager import add_memory, pin_memory, unpin_memory

    env = TestSetup()
    try:
        create_branch("test-branch")

        entry = add_memory(
            "test-branch", "Session started at noon",
            source="auto-capture", auto_resolve=False
        )
        original_score = entry["_importance"]

        # Pin it
        pinned = pin_memory(entry["id"], "test-branch")
        assert pinned["_importance"] == 5
        assert pinned["_importance_source"] == "pinned"

        # Unpin it
        unpinned = unpin_memory(entry["id"], "test-branch")
        assert unpinned["_importance_source"] == "auto"
        assert unpinned["_importance"] <= 3  # Should go back down

        print("  PASS: Pin/unpin memory works")
    finally:
        env.cleanup()


def test_importance_in_recall():
    """Higher importance entries rank higher in recall results."""
    from recall import apply_quality_filters
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    results = [
        {"id": "low", "score": 0.80, "stored_at": now,
         "_outdated": False, "_importance": 1, "content": "Low importance"},
        {"id": "high", "score": 0.80, "stored_at": now,
         "_outdated": False, "_importance": 5, "content": "High importance"},
    ]

    config = {
        "defaults": {
            "min_similarity_threshold": 0.65,
            "recency_weight": 0.15,
            "recency_fade_days": 90,
            "outdated_penalty": 0.5,
            "importance_weight": 0.10,
        }
    }

    filtered = apply_quality_filters(results, config)
    assert len(filtered) == 2
    # High importance should rank first (same similarity, same recency)
    assert filtered[0]["id"] == "high", f"Expected 'high' first, got '{filtered[0]['id']}'"
    assert filtered[0]["score"] > filtered[1]["score"]

    print("  PASS: Importance affects recall ranking")


def test_garbage_collect_report():
    """Garbage collection report finds outdated entries."""
    from branch_manager import create_branch
    from entry_manager import add_memory, mark_outdated

    env = TestSetup()
    try:
        # Patch garbage_collect paths too
        import garbage_collect
        garbage_collect.ARCHIVE_DIR = os.path.join(env.tmpdir, "archive")

        create_branch("test-branch")
        e1 = add_memory("test-branch", "Old info", auto_resolve=False)
        add_memory("test-branch", "Current info", auto_resolve=False)
        mark_outdated(e1["id"], "test-branch", "replaced")

        report = garbage_collect.generate_report()
        assert report["outdated_entries"] == 1
        assert report["active_entries"] == 1
        assert report["total_entries"] == 2

        print("  PASS: Garbage collection report works")
    finally:
        env.cleanup()


def test_archive_entry():
    """Archiving moves entry from active to archive dir."""
    from branch_manager import create_branch
    from entry_manager import add_memory, mark_outdated, get_entry

    env = TestSetup()
    try:
        import garbage_collect
        garbage_collect.ARCHIVE_DIR = os.path.join(env.tmpdir, "archive")

        create_branch("test-branch")
        entry = add_memory("test-branch", "Will be archived", auto_resolve=False)
        mark_outdated(entry["id"], "test-branch", "old")

        # Archive it
        result = garbage_collect.archive_entry(entry)
        assert result is True, "Archive should succeed"

        # Entry should be gone from active
        assert get_entry(entry["id"], "test-branch") is None

        # Entry should exist in archive
        archive_path = os.path.join(
            garbage_collect.ARCHIVE_DIR, "test-branch", f"{entry['id']}.json"
        )
        assert os.path.exists(archive_path), "Archive file should exist"

        print("  PASS: Archive entry works")
    finally:
        env.cleanup()


def test_recall_tracking():
    """Recall hits are recorded and stats work."""
    from branch_manager import create_branch
    from entry_manager import add_memory, search_entries
    from recall import _record_recall_hit, get_recall_stats, RECALL_LOG_PATH

    env = TestSetup()
    try:
        # Patch recall log path
        import recall
        old_path = recall.RECALL_LOG_PATH
        recall.RECALL_LOG_PATH = os.path.join(env.tmpdir, "recall_log.json")

        create_branch("test-branch")
        e1 = add_memory("test-branch", "Marketing strategy for Q1", auto_resolve=False)
        e2 = add_memory("test-branch", "Budget allocation for ads", auto_resolve=False)

        # Simulate recall hits
        _record_recall_hit(e1["id"], "test-branch", "marketing strategy")
        _record_recall_hit(e1["id"], "test-branch", "Q1 plans")
        _record_recall_hit(e2["id"], "test-branch", "budget")

        stats = get_recall_stats()
        assert stats["total_recalls"] == 3
        assert stats["most_recalled"][0]["hit_count"] == 2  # e1 hit twice

        # Single entry stats
        e1_stats = get_recall_stats(e1["id"], "test-branch")
        assert e1_stats["hit_count"] == 2

        recall.RECALL_LOG_PATH = old_path
        print("  PASS: Recall tracking works")
    finally:
        env.cleanup()


def test_briefing_generator():
    """Briefing generator produces structured output."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch", summary="Test project")
        add_memory("test-branch", "Deployed new auth system", source="agent",
                   auto_resolve=False)
        add_memory("test-branch", "Fixed login bug on mobile", source="manual",
                   auto_resolve=False)

        from briefing import generate_briefing
        brief = generate_briefing()

        assert "text" in brief
        assert "recent_changes" in brief
        assert "top_priorities" in brief
        assert len(brief["recent_changes"]) >= 2
        assert "SESSION BRIEFING" in brief["text"]
        assert brief["branch_health"]["test-branch"]["active"] == 2

        print("  PASS: Briefing generator works")
    finally:
        env.cleanup()


def test_timeline():
    """Timeline captures add, outdated, and supersede events."""
    from branch_manager import create_branch
    from entry_manager import add_memory, mark_outdated

    env = TestSetup()
    try:
        create_branch("test-branch")
        e1 = add_memory("test-branch", "Old deploy command uses temp dir",
                         auto_resolve=False)
        e2 = add_memory("test-branch", "Switched deploy and launched Docker containers to replace old system",
                         auto_resolve=False)
        mark_outdated(e1["id"], "test-branch", "replaced by docker")

        from timeline import get_timeline, format_timeline
        events = get_timeline(days=1)

        # Should have at least: 2 added + 1 outdated + 1 decision (for "switched")
        types = [e["type"] for e in events]
        assert "added" in types, f"Expected 'added' in {types}"
        assert "outdated" in types, f"Expected 'outdated' in {types}"
        assert "decision" in types, f"Expected 'decision' in {types}"

        # Format should produce readable text
        text = format_timeline(events)
        assert len(text) > 0

        print("  PASS: Timeline works")
    finally:
        env.cleanup()


def test_weekly_digest():
    """Weekly digest summarizes event counts."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("proj-a")
        create_branch("proj-b")
        add_memory("proj-a", "Launched new feature", auto_resolve=False)
        add_memory("proj-b", "Fixed critical bug", auto_resolve=False)

        from timeline import get_weekly_digest
        digest = get_weekly_digest()

        assert digest["total_events"] >= 2
        assert "proj-a" in digest["branches_touched"]
        assert "proj-b" in digest["branches_touched"]

        print("  PASS: Weekly digest works")
    finally:
        env.cleanup()


def test_auto_expiry_on_add():
    """New entries get auto-expiry based on content."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch")

        # Pricing content — should get short expiry (30 days)
        pricing = add_memory("test-branch",
                              "Claude API pricing is $15 per million tokens",
                              auto_resolve=False)
        assert pricing.get("_expires_at") is not None, "Should have expiry"
        assert pricing.get("_expiry_days") == 30, \
            f"Expected 30 days, got {pricing.get('_expiry_days')}"

        # Architecture content — should get longer expiry (90 days)
        arch = add_memory("test-branch",
                           "The architecture uses a three-tier design pattern",
                           auto_resolve=False)
        assert arch.get("_expiry_days") == 90, \
            f"Expected 90 days, got {arch.get('_expiry_days')}"

        # Status content — should get shortest expiry (14 days)
        status = add_memory("test-branch",
                             "Task status: blocked waiting on API key",
                             auto_resolve=False)
        assert status.get("_expiry_days") == 14, \
            f"Expected 14 days, got {status.get('_expiry_days')}"

        print("  PASS: Auto-expiry on add works")
    finally:
        env.cleanup()


def test_refresh_entry():
    """Refreshing resets the expiry clock."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch")

        entry = add_memory("test-branch", "Current pricing is $20/month",
                            auto_resolve=False)
        original_expires = entry.get("_expires_at")
        assert original_expires is not None

        from expiry import refresh_entry
        refreshed = refresh_entry(entry["id"], "test-branch")

        assert refreshed["_last_refreshed"] is not None
        assert refreshed["_refresh_count"] == 1
        # New expiry should be later than original (reset from now)
        assert refreshed["_expires_at"] >= original_expires

        print("  PASS: Refresh entry works")
    finally:
        env.cleanup()


def test_refresh_queue():
    """Refresh queue finds expired entries."""
    from branch_manager import create_branch
    from entry_manager import add_memory, get_entry, get_entries_dir

    env = TestSetup()
    try:
        create_branch("test-branch")

        # Create entry with already-past expiry
        entry = add_memory("test-branch", "Old pricing data costs money",
                            auto_resolve=False)

        # Manually set expiry to the past
        entry_data = get_entry(entry["id"], "test-branch")
        entry_data["_expires_at"] = "2020-01-01T00:00:00+00:00"
        entry_path = os.path.join(get_entries_dir("test-branch"),
                                   f"{entry['id']}.json")
        with open(entry_path, "w") as f:
            json.dump(entry_data, f, indent=2)

        from expiry import get_refresh_queue
        queue = get_refresh_queue()

        assert len(queue["needs_refresh"]) >= 1, \
            f"Expected 1+ in needs_refresh, got {len(queue['needs_refresh'])}"
        assert queue["needs_refresh"][0]["entry_id"] == entry["id"]

        print("  PASS: Refresh queue works")
    finally:
        env.cleanup()


def test_event_hooks():
    """Event hooks fire on memory operations."""
    from branch_manager import create_branch
    from entry_manager import add_memory, mark_outdated, pin_memory
    from hooks import register_hook, get_event_log

    env = TestSetup()
    try:
        # Clear any existing hooks
        import hooks
        hooks._hooks = {}
        hooks._event_log = []

        events_received = []

        def capture(event_data):
            events_received.append(event_data)

        register_hook("memory_added", capture)
        register_hook("memory_outdated", capture)
        register_hook("memory_pinned", capture)

        create_branch("test-branch")

        # Add triggers memory_added
        e1 = add_memory("test-branch", "Test hook entry", auto_resolve=False)
        assert len(events_received) >= 1, f"Expected 1+ events, got {len(events_received)}"
        assert events_received[-1]["event"] == "memory_added"

        # Mark outdated triggers memory_outdated
        mark_outdated(e1["id"], "test-branch", "test reason")
        assert events_received[-1]["event"] == "memory_outdated"

        # Pin triggers memory_pinned
        e2 = add_memory("test-branch", "Pin this one", auto_resolve=False)
        pin_memory(e2["id"], "test-branch")
        assert events_received[-1]["event"] == "memory_pinned"

        # Event log should have entries too
        log = get_event_log()
        assert len(log) >= 3

        print("  PASS: Event hooks work")
    finally:
        hooks._hooks = {}
        hooks._event_log = []
        env.cleanup()


def test_file_hooks():
    """File-based hooks append JSONL."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        import hooks
        hooks._hooks = {}
        hooks._file_hooks = {}
        hooks._event_log = []

        log_path = os.path.join(env.tmpdir, "events.jsonl")
        hooks.register_file_hook("memory_added", log_path)

        create_branch("test-branch")
        add_memory("test-branch", "File hook test entry", auto_resolve=False)

        # Check file was written
        assert os.path.exists(log_path), "JSONL file should exist"
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        event = json.loads(lines[0])
        assert event["event"] == "memory_added"

        print("  PASS: File hooks work")
    finally:
        hooks._hooks = {}
        hooks._file_hooks = {}
        hooks._event_log = []
        env.cleanup()


def test_auto_summary():
    """Auto-summary generates branch summaries from entries."""
    from branch_manager import create_branch, load_branch_index
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("test-branch", summary="Old summary")
        add_memory("test-branch", "Marketing strategy focuses on video content",
                    auto_resolve=False)
        add_memory("test-branch", "Budget allocated for video production team",
                    auto_resolve=False)
        add_memory("test-branch", "Video content outperforms static posts",
                    auto_resolve=False)

        from auto_summary import update_summary, needs_update

        # Should need update (count mismatch)
        assert needs_update("test-branch"), "Should need update"

        result = update_summary("test-branch")
        assert result["changed"] is True
        assert "3 entries" in result["new_summary"]
        assert "video" in result["new_summary"].lower()
        assert len(result["top_themes"]) > 0

        # After update, should not need update
        assert not needs_update("test-branch"), "Should not need update after refresh"

        print("  PASS: Auto-summary works")
    finally:
        env.cleanup()


def test_summary_health():
    """Summary health check identifies stale summaries."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    env = TestSetup()
    try:
        create_branch("fresh-branch", summary="0 entries — empty")
        create_branch("stale-branch", summary="Old manual summary")
        add_memory("stale-branch", "New entry that makes summary stale",
                    auto_resolve=False)

        from auto_summary import get_summary_health
        health = get_summary_health()

        assert "stale-branch" in health["stale_branches"]
        assert health["stale_count"] >= 1

        print("  PASS: Summary health check works")
    finally:
        env.cleanup()


def test_bulk_import_text():
    """Bulk import splits text into paragraph entries."""
    from branch_manager import create_branch

    env = TestSetup()
    try:
        from bulk_import import import_text

        text = """First paragraph about marketing strategy and growth plans.

Second paragraph about budget allocation and spending for the team.

Third paragraph about technical architecture and system design patterns."""

        result = import_text(text, branch="imported", source="test")

        assert result["imported"] == 3, f"Expected 3, got {result['imported']}"
        assert result["branch"] == "imported"
        assert len(result["entries"]) == 3

        # Verify entries exist
        from entry_manager import list_entries
        entries = list_entries("imported")
        assert len(entries) == 3
        assert entries[0].get("source") == "test"

        print("  PASS: Bulk import text works")
    finally:
        env.cleanup()


def test_bulk_import_markdown():
    """Bulk import splits markdown by headings."""
    env = TestSetup()
    try:
        # Write a temp markdown file
        md_path = os.path.join(env.tmpdir, "test.md")
        with open(md_path, "w") as f:
            f.write("""# Marketing Strategy

Our marketing strategy focuses on video content and social media engagement.

# Budget Planning

Budget for Q1 is $50,000 allocated across video production and paid ads.

# Technical Notes

The system uses a three-tier architecture with React frontend and Python backend.
""")

        from bulk_import import import_file

        result = import_file(md_path, branch="docs")

        assert result["imported"] == 3, f"Expected 3, got {result['imported']}"

        from entry_manager import list_entries
        entries = list_entries("docs")
        assert len(entries) == 3

        # Check that headings became tags
        all_tags = []
        for e in entries:
            all_tags.extend(e.get("tags", []))
        tag_str = " ".join(all_tags)
        assert "section:" in tag_str, "Headings should become section tags"

        print("  PASS: Bulk import markdown works")
    finally:
        env.cleanup()


def test_bulk_import_json():
    """Bulk import handles JSON arrays."""
    env = TestSetup()
    try:
        json_path = os.path.join(env.tmpdir, "test.json")
        with open(json_path, "w") as f:
            json.dump([
                {"content": "First structured entry from JSON import", "tags": ["test"]},
                {"content": "Second structured entry from JSON import", "source": "api"},
            ], f)

        from bulk_import import import_file

        result = import_file(json_path, branch="structured")

        assert result["imported"] == 2, f"Expected 2, got {result['imported']}"

        print("  PASS: Bulk import JSON works")
    finally:
        env.cleanup()


if __name__ == "__main__":
    print("\n=== Vivioo Memory System — Core Tests ===\n")

    tests = [
        test_privacy_filter,
        test_tier_inheritance,
        test_branch_creation,
        test_alias_routing,
        test_entry_crud,
        test_mark_outdated,
        test_keyword_search,
        test_enriched_text,
        test_quality_filter,
        test_no_match_detection,
        test_conflict_detection_keyword,
        test_auto_resolve_on_add,
        test_supersedes_chain,
        test_importance_auto_score,
        test_importance_manual_override,
        test_pin_memory,
        test_importance_in_recall,
        test_garbage_collect_report,
        test_archive_entry,
        test_recall_tracking,
        test_briefing_generator,
        test_timeline,
        test_weekly_digest,
        test_auto_expiry_on_add,
        test_refresh_entry,
        test_refresh_queue,
        test_event_hooks,
        test_file_hooks,
        test_auto_summary,
        test_summary_health,
        test_bulk_import_text,
        test_bulk_import_markdown,
        test_bulk_import_json,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__} — {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("All tests passed!")
    print()
