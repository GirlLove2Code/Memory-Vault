#!/usr/bin/env python3
"""
Tests for v0.5 features: Corrections, Active Recall, TF-IDF.
Run: python3 tests/test_v05.py
"""

import os
import sys
import json
import shutil
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSED = 0
FAILED = 0
TEST_DIR = None


def setup():
    """Create a clean test environment."""
    global TEST_DIR
    TEST_DIR = tempfile.mkdtemp(prefix="memvault_v05_")

    # Point branch_manager to test directory
    import branch_manager
    branch_manager.BRANCHES_DIR = os.path.join(TEST_DIR, "branches")
    branch_manager.MASTER_INDEX_PATH = os.path.join(TEST_DIR, "master_index.json")
    os.makedirs(branch_manager.BRANCHES_DIR, exist_ok=True)

    # Create a test branch
    branch_manager.create_branch("test-branch", summary="Test branch for v0.5")
    branch_manager.create_branch("marketing", summary="Marketing strategies")


def teardown():
    """Clean up test environment."""
    global TEST_DIR
    if TEST_DIR and os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)


def test(name):
    """Test decorator."""
    def decorator(func):
        global PASSED, FAILED
        try:
            func()
            print(f"  PASS: {name}")
            PASSED += 1
        except Exception as e:
            print(f"  FAIL: {name} — {e}")
            FAILED += 1
        return func
    return decorator


# ─── TF-IDF TESTS ──────────────────────────────────────────

@test("TF-IDF: basic search")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "The agent prefers story-first marketing campaigns")
    idx.add("d2", "Deploy the server to Vercel with environment variables")
    idx.add("d3", "Marketing budget is fifty thousand for Q2")

    results = idx.search("marketing strategy")
    assert len(results) >= 1, f"Expected results, got {len(results)}"
    assert results[0][0] in ("d1", "d3"), f"Expected marketing doc, got {results[0][0]}"


@test("TF-IDF: empty index returns nothing")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    results = idx.search("anything")
    assert results == [], f"Expected empty, got {results}"


@test("TF-IDF: add and remove")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "Hello world")
    assert idx.doc_count == 1
    idx.remove("d1")
    assert idx.doc_count == 0


@test("TF-IDF: update existing document")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "Old content about cats")
    idx.add("d1", "New content about dogs")
    assert idx.doc_count == 1
    results = idx.search("dogs")
    assert len(results) == 1 and results[0][0] == "d1"


@test("TF-IDF: stemming works")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "The agent is launching new campaigns")
    results = idx.search("launch campaign")
    assert len(results) == 1, f"Stemming should match, got {len(results)}"


@test("TF-IDF: stop words filtered")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "The quick brown fox")
    idx.add("d2", "A slow red car")
    # "the" and "a" are stop words — should match on content words
    results = idx.search("quick fox")
    assert results[0][0] == "d1"


@test("TF-IDF: relevance ranking")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "Python machine learning data science")
    idx.add("d2", "Python web development flask django")
    idx.add("d3", "JavaScript react frontend development")

    results = idx.search("Python data science machine learning")
    assert results[0][0] == "d1", f"d1 should rank first, got {results[0][0]}"


@test("TF-IDF: clear index")
def _():
    from tfidf import TFIDFIndex
    idx = TFIDFIndex()
    idx.add("d1", "Test content")
    idx.add("d2", "More content")
    idx.clear()
    assert idx.doc_count == 0
    assert idx.search("test") == []


# ─── CORRECTIONS TESTS ─────────────────────────────────────

@test("Corrections: add correction")
def _():
    from corrections import add_correction
    entry = add_correction(
        "test-branch",
        "Never use stock photos",
        context="Boss reviewed landing page",
        source="boss",
        tags=["design"],
    )
    assert entry["_type"] == "correction"
    assert entry["_importance"] == 5
    assert entry["_expires_at"] is None
    assert entry["source"] == "boss"


@test("Corrections: get corrections")
def _():
    from corrections import get_corrections
    cors = get_corrections("test-branch")
    assert len(cors) >= 1
    assert all(c["_type"] == "correction" for c in cors)


@test("Corrections: get all corrections (no branch filter)")
def _():
    from corrections import add_correction, get_corrections
    add_correction("marketing", "Always A/B test headlines", source="self")
    cors = get_corrections()  # all branches
    assert len(cors) >= 2  # at least the two we added


@test("Corrections: resolve correction")
def _():
    from corrections import add_correction, resolve_correction, get_corrections
    entry = add_correction("test-branch", "Temporary correction to resolve")
    resolved = resolve_correction(entry["id"], "test-branch", "Applied and verified")
    assert resolved["_outdated"] is True
    assert "_resolved_at" in resolved

    # Should not appear in active corrections
    active = get_corrections("test-branch")
    ids = [c["id"] for c in active]
    assert entry["id"] not in ids


@test("Corrections: recall corrections by keyword")
def _():
    from corrections import add_correction, recall_corrections
    add_correction("marketing", "Use real screenshots not stock photos", tags=["design"])
    results = recall_corrections("screenshots for the landing page")
    assert len(results) >= 1


@test("Corrections: never expire")
def _():
    from corrections import add_correction
    entry = add_correction("test-branch", "This should never expire")
    assert entry["_expires_at"] is None
    assert entry["_expiry_days"] is None


# ─── ACTIVE RECALL TESTS ───────────────────────────────────

@test("Active recall: pre_task_recall returns structure")
def _():
    from active_recall import pre_task_recall
    result = pre_task_recall("Redesign the landing page", branch="test-branch")
    assert "recall_id" in result
    assert "corrections" in result
    assert "memories" in result
    assert "verification" in result
    assert "should_warn" in result
    assert result["verified"] is False


@test("Active recall: verify_recall")
def _():
    from active_recall import pre_task_recall, verify_recall
    result = pre_task_recall("Some task")
    assert result["verified"] is False

    verified = verify_recall(result["recall_id"], agent_notes="Understood")
    assert verified["verified"] is True


@test("Active recall: corrections brief")
def _():
    from active_recall import get_all_corrections_brief
    brief = get_all_corrections_brief()
    assert "ACTIVE CORRECTIONS" in brief or "No active corrections" in brief


@test("Active recall: boss corrections trigger warning")
def _():
    from corrections import add_correction
    from active_recall import pre_task_recall
    add_correction("test-branch", "CRITICAL: never deploy on Friday", source="boss")
    result = pre_task_recall("Deploy the new version", branch="test-branch")
    assert result["should_warn"] is True
    assert len(result["verification"]["critical_corrections"]) >= 1


# ─── INTEGRATION: RECALL WITH CORRECTIONS ───────────────────

@test("Recall includes corrections field")
def _():
    from recall import recall
    result = recall("marketing strategy")
    assert "corrections" in result


@test("Recall 3-tier fallback works")
def _():
    from entry_manager import add_memory
    add_memory("marketing", "Story-first campaigns work best for our audience",
               tags=["strategy"])
    from recall import recall
    result = recall("campaign strategy")
    assert result["search_mode"] in ("semantic", "tfidf", "keyword")
    assert result["result_count"] >= 0


# ─── MAIN ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  Memory Vault v0.5 Tests")
    print("=" * 50)
    print()

    setup()

    print("TF-IDF:")
    # TF-IDF tests run above via decorators

    print("\nCorrections:")
    # Correction tests run above

    print("\nActive Recall:")
    # Active recall tests run above

    print("\nIntegration:")
    # Integration tests run above

    teardown()

    print()
    print("=" * 50)
    print(f"Results: {PASSED} passed, {FAILED} failed out of {PASSED + FAILED}")
    if FAILED == 0:
        print("All tests passed!")
    else:
        print(f"{FAILED} test(s) failed.")
        sys.exit(1)
