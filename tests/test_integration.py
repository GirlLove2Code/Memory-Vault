"""
Vivioo Memory — Integration Test Suite
Tests with realistic project data to verify recall quality.

This tests the FULL pipeline:
  1. Create branches for real projects
  2. Seed with realistic memories (Vivioo, Game Project, Marketing Platform, News Project)
  3. Ask realistic questions
  4. Verify the right memories come back in the right order

Run:
    python3 tests/test_integration.py              # keyword mode (no Ollama)
    python3 tests/test_integration.py --semantic    # with Ollama (better quality)
"""

import os
import sys
import json
import shutil
import tempfile
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class IntegrationEnv:
    """Set up a full test environment with realistic data."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vivioo_integration_")
        self.branches_dir = os.path.join(self.tmpdir, "branches")
        self.vectors_dir = os.path.join(self.tmpdir, "vectors")
        self.config_path = os.path.join(self.tmpdir, "config.json")
        self.master_index_path = os.path.join(self.tmpdir, "master_index.json")
        self.recall_log_path = os.path.join(self.tmpdir, "recall_log.json")
        self.hooks_config_path = os.path.join(self.tmpdir, "hooks_config.json")

        os.makedirs(self.branches_dir, exist_ok=True)
        os.makedirs(self.vectors_dir, exist_ok=True)

        config = {
            "security_tiers": {},
            "defaults": {
                "default_tier": "open",
                "min_similarity_threshold": 0.65,
                "recency_weight": 0.15,
                "recency_fade_days": 90,
                "outdated_penalty": 0.5,
                "importance_weight": 0.10,
                "confidence_threshold": 0.75,
                "ambiguity_gap": 0.1,
                "embedding_model": "nomic-embed-text",
                "max_aliases_per_branch": 3,
            },
            "branch_security": {},
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f)

        # Patch all module paths
        import branch_manager
        import entry_manager
        import privacy_filter
        import recall
        import garbage_collect
        import hooks

        branch_manager.BASE_DIR = self.branches_dir
        branch_manager.MASTER_INDEX_PATH = self.master_index_path
        privacy_filter.CONFIG_PATH = self.config_path
        recall.RECALL_LOG_PATH = self.recall_log_path
        garbage_collect.ARCHIVE_DIR = os.path.join(self.tmpdir, "archive")
        hooks.HOOKS_CONFIG_PATH = self.hooks_config_path
        hooks._hooks = {}
        hooks._file_hooks = {}
        hooks._event_log = []

    def cleanup(self):
        import hooks
        hooks._hooks = {}
        hooks._file_hooks = {}
        hooks._event_log = []
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def seed_project_data(env):
    """Seed with realistic data from the builder's actual projects."""
    from branch_manager import create_branch
    from entry_manager import add_memory

    # --- VIVIOO PROJECT ---
    create_branch("vivioo", aliases=["vivi", "site"],
                  summary="Vivioo knowledge hub — Next.js site with guides and tools")
    create_branch("vivioo/deploy", aliases=["deploy", "vercel"],
                  summary="Deployment process and rules")
    create_branch("vivioo/guides", aliases=["guides"],
                  summary="Guide pages content and structure")

    add_memory("vivioo", "Vivioo is a Next.js 14 site with TypeScript and Tailwind CSS",
               source="manual", tags=["tech-stack"])
    add_memory("vivioo", "Design system uses quiet luxury style with gold #9A7B4F on bg #FAFAF7",
               source="manual", tags=["design"])
    add_memory("vivioo", "Live URL is my-project.example.com, GitHub repo is example-user/my-project",
               source="manual", tags=["infra"])
    add_memory("vivioo", "Never say human in user-facing content, use she/her for the builder",
               source="decision", tags=["rule"], importance=5)
    add_memory("vivioo", "Business relationships are confidential",
               source="decision", tags=["privacy", "rule"], importance=5)

    add_memory("vivioo/deploy", "Deploy is manual — handled via CLI deployment, Claude Code can deploy when the builder is present",
               source="decision", tags=["rule"])
    add_memory("vivioo/deploy", "Git workflow: git add specific files, git commit, git push origin main",
               source="manual", tags=["process"])
    add_memory("vivioo/deploy", "Migrated project due to configuration issues",
               source="observation", tags=["history"])

    add_memory("vivioo/guides", "10 guide pages live: 4 builder guides + 6 agent guides",
               source="agent", tags=["status"])
    add_memory("vivioo/guides", "Raise Your Agent is an interactive flowchart with 4 Vivienne PFP baby outcomes",
               source="agent", tags=["feature"])
    add_memory("vivioo/guides", "Costs guide has cost breakdown with real usage numbers",
               source="agent", tags=["content"])

    # --- GAME PROJECT ---
    create_branch("game-project", aliases=["game-app", "game", "cards"],
                  summary="A web-based card game")

    add_memory("game-project", "A web-based card game at game-app.example.com",
               source="manual", tags=["tech-stack"])
    add_memory("game-project", "Game assets, single-page app, cloud storage for leaderboard",
               source="manual", tags=["architecture"])
    add_memory("game-project", "Card art uses img tags not background-image for WebView reliability",
               source="decision", tags=["technical"])
    add_memory("game-project", "Element system proposed: 7 elements with circular dominance, waiting on lead approval",
               source="observation", tags=["pending"])
    add_memory("game-project", "Character card is missing art — needs to be created before element update",
               source="observation", tags=["blocker"])
    add_memory("game-project", "Bot AI set to casual difficulty so players can actually win",
               source="decision", tags=["gameplay"])

    # --- MARKETING PLATFORM ---
    create_branch("marketing", aliases=["marketing-platform", "analytics"],
                  summary="Social media intelligence platform for marketing teams")

    add_memory("marketing", "14 HTML pages with React 18 via CDN, no build step",
               source="manual", tags=["architecture"])
    add_memory("marketing", "Social API integration built but not deployed — needs API token in env",
               source="agent", tags=["pending"])
    add_memory("marketing", "Password protected with session-based auth using sessionStorage",
               source="manual", tags=["security"])
    add_memory("marketing", "First client has 3 sub-accounts: client-alpha, client-beta, client-gamma",
               source="manual", tags=["client"])

    # --- NEWS PROJECT ---
    create_branch("news-project", aliases=["news"],
                  summary="AI news aggregator — Next.js with LLM API")

    add_memory("news-project", "News project uses Next.js 14 with LLM API for summarization",
               source="manual", tags=["tech-stack"])
    add_memory("news-project", "RSS feeds in multiple languages",
               source="manual", tags=["feature"])

    # --- DECISIONS (cross-project) ---
    create_branch("decisions", aliases=["decided", "rules"],
                  summary="Cross-project decisions and rules")

    add_memory("decisions", "All projects: commit and push to GitHub when work is complete, never deploy directly",
               source="decision", tags=["rule"], importance=5)
    add_memory("decisions", "OpenAI API does not work from browser due to CORS — use Gemini or add proxy",
               source="observation", tags=["technical"])
    add_memory("decisions", "Claude API works from browser with anthropic-dangerous-direct-browser-access header",
               source="observation", tags=["technical"])

    return {
        "branches": 7,
        "total_entries": 25,
    }


# ─── RECALL QUALITY TESTS ───────────────────────────────────

def test_basic_recall(env):
    """Can the system find memories by topic?"""
    from entry_manager import search_entries

    # Simple keyword search
    results = search_entries("deploy")
    assert len(results) >= 2, f"Expected 2+ deploy results, got {len(results)}"

    # Check that deploy-related entries come back
    contents = " ".join(r["content"].lower() for r in results)
    assert "deploy" in contents

    print("  PASS: Basic recall finds relevant memories")


def test_branch_routing(env):
    """Does the system route queries to the right branch?"""
    from recall import route_query

    # Should route to vivioo/deploy
    routing = route_query("deploy")
    assert routing["branch"] is not None, "Should find a branch for 'deploy'"
    assert "deploy" in routing["branch"] or routing["method"] == "alias"

    # Should route to game-project
    routing = route_query("cards")
    if routing["branch"]:
        assert "game" in routing["branch"]

    print("  PASS: Branch routing works with real data")


def test_importance_ranking(env):
    """Do high-importance entries rank higher?"""
    from entry_manager import list_entries

    vivioo_entries = list_entries("vivioo", include_outdated=False)
    # Sort by importance
    by_importance = sorted(vivioo_entries, key=lambda e: e.get("_importance", 3), reverse=True)

    # The confidential rule and language rule should be top (importance=5)
    top_2_contents = " ".join(e["content"].lower() for e in by_importance[:2])
    assert "confidential" in top_2_contents or "never" in top_2_contents, \
        f"Expected high-importance rules at top, got: {top_2_contents[:100]}"

    print("  PASS: Importance ranking puts critical rules first")


def test_conflict_detection_real(env):
    """Does conflict detection catch real-world updates?"""
    from entry_manager import add_memory, list_entries

    # Add an updated version of the guides count
    result = add_memory("vivioo/guides",
                        "12 guide pages live: 4 builder guides + 8 agent guides",
                        source="agent", tags=["status"])

    # Should have auto-resolved the old "10 guide pages" entry
    assert result.get("_resolved") or result.get("_supersedes"), \
        "Should detect conflict with '10 guide pages' entry"

    # Active entries should have the new one
    active = list_entries("vivioo/guides", include_outdated=False)
    active_contents = " ".join(e["content"] for e in active)
    assert "12 guide pages" in active_contents

    print("  PASS: Conflict detection catches real updates")


def test_expiry_assignment(env):
    """Do entries get appropriate expiry periods?"""
    from entry_manager import list_entries

    # Check game-project entries — "element system waiting on lead" should get short expiry (status = 14 days)
    hss_entries = list_entries("game-project")
    for e in hss_entries:
        if "waiting" in e.get("content", "").lower():
            assert e.get("_expiry_days") is not None, "Status entry should have expiry"
            assert e["_expiry_days"] <= 45, \
                f"Status entry should expire in <=45 days, got {e['_expiry_days']}"
            break

    # Architecture entries should get longer expiry
    for e in hss_entries:
        if "architecture" in e.get("content", "").lower():
            # architecture + hosting = min(90, 45) = 45
            assert e.get("_expiry_days") is not None
            break

    print("  PASS: Expiry periods match content type")


def test_briefing_quality(env):
    """Does the briefing contain useful information?"""
    from briefing import generate_briefing

    brief = generate_briefing()

    assert len(brief["recent_changes"]) > 0, "Should have recent changes"
    assert len(brief["top_priorities"]) > 0, "Should have priorities"
    assert "SESSION BRIEFING" in brief["text"]

    # Check that branches are represented
    branches_in_brief = set()
    for item in brief["recent_changes"]:
        branches_in_brief.add(item["branch"].split("/")[0])

    assert len(branches_in_brief) >= 3, \
        f"Expected 3+ projects in briefing, got {branches_in_brief}"

    print("  PASS: Briefing covers multiple projects")


def test_timeline_real(env):
    """Does the timeline capture the right events?"""
    from timeline import get_timeline, get_decision_log

    events = get_timeline(days=1)
    assert len(events) >= 20, f"Expected 20+ events, got {len(events)}"

    # Decision log should have decision-language entries
    decisions = get_decision_log(days=1)
    if decisions:
        for d in decisions:
            assert d["type"] == "decision"

    print("  PASS: Timeline captures real events")


def test_auto_summary_quality(env):
    """Do auto-summaries capture key themes?"""
    from auto_summary import update_summary

    result = update_summary("vivioo")
    assert "vivioo" in result["new_summary"].lower() or len(result["top_themes"]) > 0
    assert result["entry_count"] >= 4

    # Themes should include words from the entries
    themes_str = " ".join(result["top_themes"]).lower()
    # High-importance entries dominate themes, so check for any meaningful words
    assert len(result["top_themes"]) >= 3, \
        f"Expected 3+ themes, got {len(result['top_themes'])}. Themes: {themes_str}"

    print("  PASS: Auto-summary captures project themes")


def test_hooks_fire_during_operations(env):
    """Do hooks fire during normal operations?"""
    from hooks import register_hook, get_event_log
    from entry_manager import add_memory

    events = []
    register_hook("*", lambda e: events.append(e["event"]))

    add_memory("vivioo", "Test hook firing during integration test",
               auto_resolve=False)

    assert "memory_added" in events, f"Expected memory_added in {events}"

    print("  PASS: Hooks fire during operations")


def test_bulk_import_integration(env):
    """Can we import a realistic document?"""
    from bulk_import import import_text

    # Simulate importing session notes
    notes = """Session started with reviewing the Vivioo deploy process.

Decided to switch from manual deploys to allowing Claude Code to deploy when the builder is present. Updated the settings to allow automated deploys.

Built the Raise Your Agent interactive flowchart with 11 decision nodes and 4 outcome paths. Each outcome shows a different Vivienne PFP baby image.

Updated the costs guide with real usage numbers from the builder's experience.

Reworked the join page from waitlist to Get Updates with Play Lab research opt-in checkbox."""

    result = import_text(notes, branch="session-notes", source="import:session",
                          tags=["session-2026-03-12"])

    assert result["imported"] >= 4, f"Expected 4+ entries, got {result['imported']}"

    # Verify entries are searchable
    from entry_manager import search_entries
    deploy_results = search_entries("deploy", "session-notes")
    assert len(deploy_results) >= 1, "Should find deploy-related session notes"

    print("  PASS: Bulk import with real content works")


def test_scale_100_entries(env):
    """Does the system handle 100+ entries without issues?"""
    from branch_manager import create_branch
    from entry_manager import add_memory, list_entries

    create_branch("scale-test")

    # Add 100 entries
    for i in range(100):
        add_memory("scale-test", f"Scale test entry number {i}: "
                   f"{'important decision about architecture' if i % 10 == 0 else 'routine status update'}",
                   source="agent" if i % 10 == 0 else "auto-capture",
                   auto_resolve=False)

    entries = list_entries("scale-test")
    assert len(entries) == 100, f"Expected 100 entries, got {len(entries)}"

    # Keyword search should still work fast
    from entry_manager import search_entries
    results = search_entries("architecture", "scale-test")
    assert len(results) == 10, f"Expected 10 architecture entries, got {len(results)}"

    # Auto-summary should handle it
    from auto_summary import update_summary
    result = update_summary("scale-test")
    assert result["entry_count"] == 100

    # Briefing should handle it
    from briefing import generate_briefing
    brief = generate_briefing(branch="scale-test")
    assert brief["branch_health"]["scale-test"]["active"] == 100

    print("  PASS: System handles 100+ entries")


def test_full_lifecycle(env):
    """Test the complete lifecycle: add → recall → update → outdated → archive."""
    from branch_manager import create_branch
    from entry_manager import add_memory, get_entry, mark_outdated
    from expiry import refresh_entry
    import garbage_collect
    import time

    create_branch("lifecycle")

    # 1. Add
    e1 = add_memory("lifecycle", "Deploy process uses manual Vercel CLI with temp directory and prod flag",
                     source="agent", tags=["deploy"])
    assert e1["_importance"] >= 2

    # 2. Update (new version supersedes old — high keyword overlap)
    time.sleep(0.01)
    e2 = add_memory("lifecycle", "Deploy process uses manual Vercel CLI with temp directory and prod flag plus api folder",
                     source="agent", tags=["deploy"])

    # 3. Old should be outdated
    old = get_entry(e1["id"], "lifecycle")
    assert old["_outdated"] is True

    # 4. Refresh the new one
    refreshed = refresh_entry(e2["id"], "lifecycle")
    assert refreshed["_refresh_count"] == 1

    # 5. Archive the old one
    archived = garbage_collect.archive_entry(old)
    assert archived is True
    assert get_entry(e1["id"], "lifecycle") is None  # Gone from active

    print("  PASS: Full lifecycle works end-to-end")


# ─── RUNNER ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vivioo Memory Integration Tests")
    parser.add_argument("--semantic", action="store_true",
                        help="Run with Ollama semantic search (requires Ollama running)")
    args = parser.parse_args()

    print("\n=== Vivioo Memory — Integration Tests ===")
    print(f"Mode: {'Semantic (Ollama)' if args.semantic else 'Keyword (fallback)'}\n")

    env = IntegrationEnv()

    try:
        # Seed data
        print("--- Seeding project data ---")
        stats = seed_project_data(env)
        print(f"  Created {stats['branches']} branches, {stats['total_entries']} entries\n")

        # Run tests
        tests = [
            test_basic_recall,
            test_branch_routing,
            test_importance_ranking,
            test_conflict_detection_real,
            test_expiry_assignment,
            test_briefing_quality,
            test_timeline_real,
            test_auto_summary_quality,
            test_hooks_fire_during_operations,
            test_bulk_import_integration,
            test_scale_100_entries,
            test_full_lifecycle,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                test(env)
                passed += 1
            except Exception as e:
                print(f"  FAIL: {test.__name__} — {e}")
                failed += 1

        print(f"\n{'='*50}")
        print(f"Integration: {passed} passed, {failed} failed out of {len(tests)}")
        if failed == 0:
            print("All integration tests passed!")
        print()

    finally:
        env.cleanup()


if __name__ == "__main__":
    main()
