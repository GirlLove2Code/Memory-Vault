# vivioo-memory v0.4.0 — What's New

**For the builder and the agent.** This is everything that changed since the original v0.1 build.

---

## Quick Summary

The memory system went from "searchable notes" to a system that:
- **Knows when info is outdated** and auto-replaces it
- **Scores what matters** without you telling it
- **Expires stale info** and asks "still true?"
- **Generates briefings** so you don't start sessions blind
- **Tracks what gets used** so unused memories get cleaned up
- **Fires events** that other tools (PM tracker) can listen to
- **Imports docs in bulk** — markdown, text, JSON

---

## For the Builder — What You Need to Know

### You don't score importance
The system auto-scores every memory 1-5 based on:
- Source (agent observation > manual note > auto-log)
- Decision language ("switched to", "deployed", "blocked")
- Specificity (short + focused > long + vague)
- Tags (tagged = someone cared)
- Uniqueness (only memory on this topic = high value)

**Override:** `pin_memory(entry_id, branch)` → locks importance to 5.

### Memories expire automatically
- Pricing, costs → 30 days
- Task status → 14 days
- API/model info → 45 days
- Architecture decisions → 90 days
- Pinned → never

Run `get_refresh_queue()` to see what needs a "still true?" check.
Run `refresh_entry(entry_id, branch)` to confirm it's still valid.

### Bulk import your docs
```python
from bulk_import import import_file
import_file("session-notes.md", branch="sessions")
import_file("research.json", branch="research")
```

### Garbage collection
```bash
python3 garbage_collect.py              # see what's stale
python3 garbage_collect.py --apply      # archive outdated entries
```

---

## For the Agent — What Changed in Your Workflow

### Session start: use the briefing
Instead of loading raw memories:
```python
from briefing import generate_briefing
brief = generate_briefing()
print(brief["text"])
```

This gives you:
- What changed since your last session
- Top priorities by importance
- Entries needing refresh
- Branch health

### Your recall now tracks usage
Every time you call `recall()`, it logs which entries came back. Over time this means:
- `get_recall_stats()` shows what's actually useful
- Never-recalled entries surface in briefings as potential cleanup targets

### Conflicts resolve automatically
When you `add_memory()` with content similar to an existing entry:
1. The old entry gets auto-marked outdated
2. A forward link is added (old → new)
3. A backward link is added (new lists what it replaced)

You don't need to manually hunt for duplicates.

### Timeline for "what happened?"
```python
from timeline import get_timeline, get_decision_log
events = get_timeline(days=7)           # everything this week
decisions = get_decision_log(days=30)   # just the choices
```

### Hooks — connect to other tools
```python
from hooks import register_hook, register_file_hook

# Get notified in-memory
def on_new(event):
    print(f"New memory: {event['content'][:50]}")
register_hook("memory_added", on_new)

# Or write to a file the PM tracker watches
register_file_hook("*", "/path/to/events.jsonl")
```

Events fired: `memory_added`, `memory_outdated`, `memory_expired`, `memory_pinned`, `memory_conflict`, `memory_refreshed`, `memory_archived`

### Auto-summary keeps routing accurate
```python
from auto_summary import update_all_summaries
update_all_summaries()   # regenerate all branch summaries from entries
```

Run this periodically or after bulk imports.

---

## What's NOT Tested Yet

Semantic search quality — needs Ollama running with nomic-embed-text.

Everything else (45 tests) passes with keyword fallback. But the real power of the RAG is semantic search. To test:

```bash
# Check if Ollama is running
python3 -c "from embedding import check_ollama; print(check_ollama())"

# If not installed:
# 1. Install Ollama: https://ollama.ai
# 2. Pull the model: ollama pull nomic-embed-text
# 3. Run integration tests with semantic mode:
python3 tests/test_integration.py --semantic
```

---

## Full Module Map

| Module | Functions | Purpose |
|--------|-----------|---------|
| `recall.py` | recall, startup_recall, recall_deep, get_recall_stats | Search + tracking |
| `entry_manager.py` | add_memory, find_conflicts, score_importance, pin_memory | CRUD + intelligence |
| `branch_manager.py` | create_branch, list_branches, rebuild_master_index | Organization |
| `privacy_filter.py` | set_tier, get_tier, filter_for_llm | 3-tier privacy |
| `embedding.py` | embed_text, check_ollama | Local embeddings |
| `vector_store.py` | search, rebuild_from_entries | ChromaDB |
| `briefing.py` | generate_briefing | Session briefs |
| `timeline.py` | get_timeline, get_decision_log, get_weekly_digest | Knowledge changelog |
| `expiry.py` | set_expiry, refresh_entry, get_refresh_queue | Active staleness fight |
| `hooks.py` | register_hook, register_file_hook, fire_hooks | Event system |
| `auto_summary.py` | update_summary, needs_update, get_summary_health | Branch summaries |
| `bulk_import.py` | import_file, import_text, import_entries | Batch import |
| `garbage_collect.py` | generate_report, archive_entry | Cleanup |

---

*v0.4.0 — built by the builder + Claude, 2026-03-12*
