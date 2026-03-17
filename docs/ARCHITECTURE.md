# vivioo-memory — Architecture Map

**For agents and developers reading this codebase for the first time.**

---

## How It Works (30-second version)

```
Someone asks a question
        ↓
    recall.py          ← THE FRONT DOOR (start here)
        ↓
    route_query()      ← finds the right branch (alias match → semantic match)
        ↓
    vector_search()    ← ChromaDB similarity search (or keyword fallback)
        ↓
    quality filters    ← threshold + recency + outdated penalty + importance boost
        ↓
    privacy filter     ← splits into llm_context (safe) + local_context (private)
        ↓
    recall tracking    ← logs which entries were returned
        ↓
    return results
```

---

## Module Dependency Map

```
                    ┌─────────────┐
                    │  recall.py  │  ← START HERE
                    │  (front door)│
                    └──────┬──────┘
                           │ uses
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
    ┌───────────┐  ┌──────────────┐  ┌────────────┐
    │entry_mgr  │  │branch_mgr   │  │privacy_filt│
    │(CRUD +    │  │(tree +      │  │(3 tiers)   │
    │ scoring)  │  │ routing)    │  └────────────┘
    └─────┬─────┘  └──────┬──────┘
          │ uses           │ uses
          ↓                ↓
    ┌───────────┐  ┌──────────────┐
    │embedding  │  │vector_store  │
    │(Ollama)   │──│(ChromaDB)    │
    └───────────┘  └──────────────┘

    Independent modules (don't depend on each other):

    ┌───────────┐  ┌──────────┐  ┌────────────┐
    │briefing.py│  │timeline  │  │expiry.py   │
    │(session   │  │(changelog│  │(staleness  │
    │ briefs)   │  │ events)  │  │ management)│
    └───────────┘  └──────────┘  └────────────┘

    ┌───────────┐  ┌──────────┐  ┌────────────┐
    │hooks.py   │  │auto_     │  │bulk_import │
    │(event     │  │summary   │  │(md/txt/json│
    │ system)   │  │(branch   │  │ ingest)    │
    └───────────┘  │ summaries│  └────────────┘
                   └──────────┘

    ┌────────────────┐
    │garbage_collect  │
    │(cleanup +      │
    │ archival)      │
    └────────────────┘
```

---

## File-by-File Guide

### recall.py — THE FRONT DOOR
**Read this first.** Everything starts here.

| Function | What it does | When to use |
|----------|-------------|-------------|
| `recall(query, top_k, branch)` | Main search — routes, searches, filters, returns 2 contexts | Every time you need to remember something |
| `startup_recall(recent_context)` | Load relevant memories at session start | Beginning of every session |
| `recall_deep(query, branch)` | Thorough search within one branch | When you know which branch to search |
| `recall_from_summary(branch)` | Get just the branch summary (fast, no search) | Quick overview of a topic |
| `what_do_i_know(topic)` | Overview of stored knowledge | "What do I know about X?" |
| `route_query(query)` | Find which branch a query belongs to | Internal — called by recall() |
| `apply_quality_filters(results)` | Score + filter results by quality | Internal — called by recall() |
| `get_recall_stats(entry_id, branch)` | See which entries are actually used | Periodic review, garbage collection |
| `format_for_context(entries)` | Format for LLM context window | When sending to an LLM |
| `format_for_agent(entries)` | Format for agent's private reasoning | When reading privately |

### entry_manager.py — CRUD + INTELLIGENCE
**Where memories are created, scored, and linked.**

| Function | What it does | Side effects |
|----------|-------------|--------------|
| `add_memory(branch, content, ...)` | Create a new memory | Auto-scores importance, auto-detects conflicts, auto-sets expiry, fires `memory_added` hook, syncs to vectors |
| `get_entry(entry_id, branch)` | Read one entry | None |
| `update_memory(entry_id, branch, content)` | Update content | Timestamp updated |
| `delete_memory(entry_id, branch)` | Permanently delete | Gone forever — prefer mark_outdated |
| `mark_outdated(entry_id, branch, reason)` | Soft-delete (keeps but deprioritizes) | Fires `memory_outdated` hook |
| `unmark_outdated(entry_id, branch)` | Restore an outdated entry | Back to active |
| `pin_memory(entry_id, branch)` | Lock importance to 5, never expires | Fires `memory_pinned` hook |
| `unpin_memory(entry_id, branch)` | Re-scores importance automatically | |
| `score_importance(entry, branch)` | Auto-score 1-5 based on signals | Called by add_memory automatically |
| `find_conflicts(branch, content)` | Find similar existing entries | Called by add_memory if auto_resolve=True |
| `list_entries(branch, include_outdated)` | List all entries in a branch | |
| `search_entries(query, branch)` | Keyword search fallback | Used when Ollama is unavailable |

**Importance scoring signals:**
- Source type: agent (1.0) > manual (0.5) > auto-capture (0.0)
- Decision language: "switched", "deployed", "blocked", etc.
- Specificity: 10-80 words = sweet spot
- Has tags: +0.5
- Few entries in branch: +0.75 (rare = valuable)

**Conflict detection:** When `add_memory()` is called with `auto_resolve=True` (default):
1. Checks all active entries in the same branch
2. Uses semantic similarity (threshold 0.82) if Ollama available
3. Falls back to keyword overlap (threshold 0.60)
4. Matching entries get auto-marked outdated with bidirectional links

### branch_manager.py — TREE STRUCTURE
**Organizes memories into branches (like folders).**

| Function | What it does |
|----------|-------------|
| `create_branch(path, aliases, security, summary)` | Create a new branch at any depth |
| `load_branch_index(path)` | Read a branch's metadata |
| `list_branches()` | List all branch paths |
| `find_branch_by_alias(word)` | Find branch by alias keyword |
| `find_branches_by_query(query)` | Find branches matching any word in query |
| `update_branch_summary(path, summary)` | Update a branch's summary text |
| `rebuild_master_index()` | Rebuild the full index from disk |

**Disk structure:**
```
branches/
  vivioo/
    index.json          ← summary, aliases, security
    entries/            ← memory JSON files
      mem-17100000.json
      mem-17100001.json
    deploy/
      index.json
      entries/
```

### privacy_filter.py — 3-TIER PRIVACY

| Tier | Who sees it | Use for |
|------|------------|---------|
| Open | LLM + agent | Public knowledge, guides, technical info |
| Local | Agent only (LLM never sees) | Revenue, private strategy, personal info |
| Locked | Nobody without passphrase | Medical, legal, encrypted data |

Sub-branches inherit parent tier.

### embedding.py — LOCAL EMBEDDINGS
- Uses Ollama with nomic-embed-text model
- Everything runs locally — nothing leaves the machine
- Falls back gracefully if Ollama is unavailable (keyword search takes over)

### vector_store.py — CHROMADB
- Cosine similarity search
- ChromaDB is the **mirror** — JSON files in `entries/` are the source of truth
- If ChromaDB corrupts, rebuild from entries with `rebuild_from_entries()`

### briefing.py — SESSION BRIEFINGS
```python
brief = generate_briefing()           # general
brief = generate_briefing(branch="vivioo")  # one project
brief = generate_briefing(since="2026-03-12")  # since date
print(brief["text"])
```

Sections: What Changed, Top Priorities, Needs Refresh, Never Recalled, Branch Health.

### timeline.py — KNOWLEDGE CHANGELOG
```python
events = get_timeline(days=7)         # all events this week
decisions = get_decision_log(days=30) # just decisions
digest = get_weekly_digest()          # summary counts
print(format_timeline(events))        # human-readable
```

Event types: `added`, `outdated`, `superseded`, `decision`

### expiry.py — ACTIVE STALENESS MANAGEMENT
Every entry gets auto-expiry based on content:
- Pricing/costs → 30 days
- Status/tasks → 14 days
- API/model versions → 45 days
- Architecture/rules → 90 days
- Pinned → never expires

```python
queue = get_refresh_queue()           # what needs checking?
refresh_entry(entry_id, branch)       # "yes, still true"
backfill_expiry()                     # set expiry on old entries
```

### hooks.py — EVENT SYSTEM
**The bridge to external tools (PM tracker, agents, notifications).**

Events fired automatically:
- `memory_added` — new entry created
- `memory_outdated` — entry marked stale
- `memory_pinned` — entry pinned
- `memory_conflict` — auto-resolved a conflict
- `memory_refreshed` — entry confirmed still valid
- `memory_archived` — entry moved to archive

```python
# In-memory callback
register_hook("memory_added", my_function)

# File-based (external tools watch this file)
register_file_hook("*", "/path/to/events.jsonl")
```

### auto_summary.py — BRANCH SUMMARIES
```python
update_summary("vivioo")             # regenerate one
update_all_summaries()               # regenerate all
needs_update("vivioo")               # True if stale
get_summary_health()                 # which branches need work
```

Summaries are weighted by importance — high-importance entries define the themes.

### bulk_import.py — BATCH INGEST
```python
import_file("notes.md", branch="sessions")      # markdown → entries by heading
import_file("data.json", branch="data")          # JSON array → entries
import_text("long text...", branch="notes")       # paragraphs → entries
import_entries([{"content": "..."}], branch="x")  # structured
```

All imports go through full pipeline (importance, conflict detection, expiry, hooks).

### garbage_collect.py — CLEANUP
```bash
python3 garbage_collect.py              # dry run report
python3 garbage_collect.py --apply      # archive outdated entries
python3 garbage_collect.py --days 60    # custom staleness threshold
python3 garbage_collect.py --json       # machine-readable output
```

---

## Data Flow: What happens when you add a memory

```
add_memory("vivioo", "Switched deploy to Docker")
    │
    ├─→ score_importance()        → auto-scores 1-5
    ├─→ _detect_expiry_days()     → sets expiry (e.g., 45 days for deploy content)
    ├─→ find_conflicts()          → checks for similar existing entries
    │       └─→ mark_outdated()   → old entry gets deprioritized
    │           └─→ _link_superseded() → bidirectional links created
    ├─→ save to JSON file         → entries/{entry_id}.json (SOURCE OF TRUTH)
    ├─→ _sync_to_vectors()        → ChromaDB embedding (if Ollama available)
    ├─→ update branch index       → last_updated timestamp
    ├─→ update master index       → entry counts
    └─→ fire_hooks()              → "memory_added" + "memory_conflict" if resolved
```

---

## Config: config.json

| Key | Default | What it does |
|-----|---------|-------------|
| `min_similarity_threshold` | 0.65 | Drop results below this score |
| `recency_weight` | 0.15 | How much recency matters (15%) |
| `recency_fade_days` | 90 | Days until recency bonus fully fades |
| `outdated_penalty` | 0.5 | Score multiplier for outdated entries |
| `importance_weight` | 0.10 | How much importance affects ranking (10%) |
| `confidence_threshold` | 0.75 | Minimum confidence for branch routing |
| `ambiguity_gap` | 0.1 | If top 2 branches are within this gap, ask user |
| `max_aliases_per_branch` | 3 | Max shortcut words per branch |
| `embedding_model` | nomic-embed-text | Ollama model for embeddings |

---

## Testing

```bash
# Unit tests (no Ollama needed)
python3 tests/test_core.py

# Integration tests with real project data
python3 tests/test_integration.py

# Integration with semantic search (needs Ollama running)
python3 tests/test_integration.py --semantic
```

---

*v0.4.0 — 13 modules, 60+ functions, 45 tests*
