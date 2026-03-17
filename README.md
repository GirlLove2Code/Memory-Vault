# vivioo-memory

A local, privacy-first memory system for AI agents. Built from two months of real experience working with an AI agent who forgets everything.

---

## Why This Exists

We didn't set out to build a memory system. We set out to build a website together — a person and an AI agent. But every session started the same way: re-explaining who we are, what we're building, what we decided yesterday.

Memory loss is the number one complaint from people who work with AI agents. Not hallucination, not cost, not speed — *forgetting*.

After two months of this, we stopped complaining and started designing. The builder brainstormed the architecture. The agent reviewed the design and told us what actually matters from an agent's perspective. This is the result.

---

## Our Memory System vs Traditional

| Aspect | Traditional | Our System |
|---------|------------|------------|
| Storage | Context window | Persistent store |
| Recall | Everything loaded | Query when needed |
| Structure | Flat | Hierarchical (personal, work, projects) |
| Entry | Everything | 4 criteria (impact, reusable, loss hurts, verifiable) |
| Size | Unlimited | 3KB warn, 10KB limit |
| Curation | Compression (loses info) | Curation > compression |
| Privacy | All to LLM | Can filter (Open vs Local vs Locked) |
| Control | Passive | Active management |

**The key difference:**

| Traditional | Ours |
|------------|------|
| Compress = lose stuff | Curation = keep what matters |
| Everything in context | Query when needed |
| Passive | Active |

**Our thesis: "Memory = Better Performance"**

Most memory systems just store. We RESEARCH why memory matters.

---

## What Makes This Different

**1. Three-tier recall**
Master Index → Branch Summary → Full Entry. Most agents load everything or do one flat search. This system lets the agent answer from a summary without loading hundreds of entries.

**2. Privacy filter as architecture**
Three tiers: Open (LLM sees it), Local (agent reads it privately, LLM never sees), Locked (encrypted, passphrase required). Built into `recall()` from day one — not bolted on after.

**3. Retrieval quality, not just retrieval speed**
Minimum similarity threshold (no garbage results), recency weighting (fresh beats stale), outdated penalty (old info ranks lower), and explicit no-match detection (the agent knows when to say "I don't know").

**4. Intelligence, not just storage**
Auto-scores importance (1-5), auto-detects conflicts and replaces outdated info, auto-expires stale entries, and tracks what actually gets recalled — so unused memories get cleaned up.

**5. Research-backed**

| What | Why It Matters |
|------|---------------|
| Real Stories | Play Lab — actual human-agent relationships |
| Data | YouTube + Moltbook research |
| Both Sides | Human + Agent perspective |
| Tested | Hazel_OC 30-day experiment |
| Vouchers | Real outcomes, not theories |

---

## The Vivioo Difference

| Layer | What It Is |
|-------|-----------|
| Memory System | Technical implementation |
| Play Lab | Research + stories |
| Education | How to use it |
| Community | Real experiences |

---

## How It Works

```python
from vivioo_memory import recall, add_memory, create_branch

# Create a branch
create_branch("marketing", aliases=["growth", "campaigns"],
              summary="Marketing strategies and approaches")

# Add memories
add_memory("marketing", "The builder prefers story-first campaigns",
           tags=["strategy"])

# Search by meaning — not keywords
result = recall("how do we approach marketing?")

# Two contexts returned:
result["llm_context"]    # Safe to send to the LLM (🟢 Open only)
result["local_context"]  # Agent reads privately (🟢 + 🔒 Local)
result["no_match"]       # True if no relevant memory found
```

### The Privacy Split

```
Someone asks: "What should our next marketing move be?"

recall() finds 3 entries:
  Entry 1 (🟢 Open):  "Story-first campaigns" → LLM sees this
  Entry 2 (🔒 Local): "Revenue was $500K"     → agent reads, LLM doesn't
  Entry 3 (🔴 Locked): "Investor details"     → blocked entirely

The agent uses ALL context to think.
The LLM only sees what's safe.
```

---

## Requirements

- Python 3.9+
- ChromaDB (installed via pip)

**Ollama is optional.** The system works without it — keyword search handles recall automatically. If you want semantic (meaning-based) search, install [Ollama](https://ollama.ai) with `nomic-embed-text`:

```bash
pip install -r requirements.txt
ollama pull nomic-embed-text   # optional — enables semantic search
```

No Ollama? No problem. Everything still works.

---

## Quick Start

```bash
# Clone
git clone https://github.com/your-org/vivioo-memory.git
cd vivioo-memory

# Install
pip install -r requirements.txt

# Verify Ollama
python3 -c "from embedding import check_ollama; print(check_ollama())"

# Run tests
python3 tests/test_core.py
```

---

## Architecture

```
vivioo-memory/
├── __init__.py         ← Package init
├── requirements.txt    ← Dependencies (chromadb, cryptography)
├── recall.py           ← THE FRONT DOOR — search, routing, recall tracking
├── entry_manager.py    ← CRUD + conflict detection + importance scoring
├── branch_manager.py   ← Branch tree structure + Master Index
├── privacy_filter.py   ← 3-tier privacy (open/local/locked)
├── encryption.py       ← Fernet encryption for locked branches
├── embedding.py        ← Ollama + nomic-embed-text (all local)
├── vector_store.py     ← ChromaDB vector storage + search
├── briefing.py         ← Session briefing generator
├── timeline.py         ← Knowledge changelog + decision log
├── expiry.py           ← Auto-expiry + refresh queue
├── hooks.py            ← Event system (bridge to external tools)
├── auto_summary.py     ← Branch summary auto-regeneration
├── bulk_import.py      ← Import from md/txt/json/jsonl
├── garbage_collect.py  ← Stale detection + archival
├── config.json         ← Thresholds, security settings
├── branches/           ← Memory storage (source of truth)
├── vectors/            ← ChromaDB data (rebuildable mirror)
├── tests/
│   ├── test_core.py         ← 33 unit tests
│   └── test_integration.py  ← 12 integration tests
└── docs/
    ├── ARCHITECTURE.md        ← Code-level architecture map
    ├── VIVIENNE_GUIDE.md      ← Guide for agents using this system (includes filing rules)
    ├── RETRIEVAL_QUALITY.md   ← How search quality works
    ├── WHATS_NEW_v04.md       ← Changelog
    ├── AUTO_CAPTURE_SPEC.md   ← Future spec: auto-capture from conversations
    └── MULTI_AGENT_ROADMAP.md ← Future spec: multi-agent features
```

---

## Retrieval Quality

Not every RAG is built the same. Most return the top-K results regardless of quality. This system has four quality mechanisms:

| Mechanism | What it does | Default |
|-----------|-------------|---------|
| Similarity threshold | Drops results below minimum relevance | 0.65 |
| Recency weighting | Boosts recent memories by 15% | 0.15 weight, 90-day fade |
| Outdated penalty | Halves score of stale entries | 0.5x multiplier |
| No-match detection | Returns `no_match: True` when nothing relevant exists | — |

All thresholds are configurable in `config.json`. See [RETRIEVAL_QUALITY.md](docs/RETRIEVAL_QUALITY.md) for tuning guide.

---

## API Reference

### Core

| Function | What it does |
|----------|-------------|
| `recall(query, top_k, branch, override)` | Search memory by meaning. Returns two contexts (LLM-safe + private). |
| `startup_recall(recent_context, top_k)` | Load relevant memories at session start. |
| `recall_deep(query, branch, top_k)` | Thorough search within a specific branch. |
| `what_do_i_know(topic)` | Overview of stored knowledge. |

### Memory Management

| Function | What it does |
|----------|-------------|
| `add_memory(branch, content, tags, source)` | Add a memory. Auto-scores importance, detects conflicts, sets expiry. |
| `update_memory(entry_id, branch, content)` | Update existing memory. |
| `delete_memory(entry_id, branch)` | Delete permanently. |
| `mark_outdated(entry_id, branch, reason)` | Mark as stale (deprioritized, not deleted). |
| `pin_memory(entry_id, branch)` | Lock importance to 5, never expires. |
| `find_conflicts(branch, content)` | Find similar existing entries. |
| `score_importance(entry, branch)` | Auto-score 1-5 based on signals. |

### Branch Management

| Function | What it does |
|----------|-------------|
| `create_branch(path, aliases, security, summary)` | Create a topic branch. |
| `list_branches()` | List all branches. |
| `set_tier(branch, tier)` | Set privacy tier (open/local/locked). |

### Session & Monitoring

| Function | What it does |
|----------|-------------|
| `generate_briefing(since, branch)` | Session briefing: changes, priorities, health. |
| `get_timeline(days, branch)` | Knowledge changelog. |
| `get_decision_log(days)` | Just the decisions that shaped the project. |
| `get_refresh_queue(branch)` | Entries past expiry needing review. |
| `refresh_entry(entry_id, branch)` | Confirm entry still valid, reset clock. |
| `get_recall_stats()` | Which memories are actually used. |

### Bulk Operations

| Function | What it does |
|----------|-------------|
| `import_file(path, branch)` | Import markdown, text, JSON, or JSONL. |
| `import_text(text, branch)` | Import raw text (splits by paragraph). |
| `update_all_summaries()` | Regenerate all branch summaries. |

---

## Who Built This

From [vivioo.io](https://vivioo.io) — a trusted agentic AI knowledge hub where builders and agents grow together.

Built by a builder, a coding agent, and an autonomous agent — designing something together.

---

## Roadmap

### v0.5 — Multi-Agent (next)
Inspired by [OpenViking](https://github.com/ArcticViking/OpenViking) (ByteDance) and claude-mem:
- **`.abstract` + `.overview` per branch** — L0/L1 layers so any agent can scan the index in ~10 tokens without loading full entries
- **Private vs shared workspaces** — Agent A's scratch notes don't pollute Agent B's memory
- **Pointer passing** — agents share branch paths, not full text. Receiving agent loads L0 → L1 → L2 on demand within a token budget

See [MULTI_AGENT_ROADMAP.md](docs/MULTI_AGENT_ROADMAP.md) for the full spec.

---

## Why Not Flat RAG?

Most agent memory systems use flat RAG — dump everything into a vector database, retrieve by similarity. This breaks at scale:

| Problem | Flat RAG | vivioo-memory |
|---------|----------|---------------|
| Noisy results | Returns everything above threshold | Minimum 0.65 similarity + recency + importance scoring |
| No structure | All memories equal | Hierarchical branches with summaries |
| Token waste | Loads all matches into context | 3-tier: index → summary → entries (load only what's needed) |
| No privacy | Everything sent to LLM | 3-tier privacy filter (Open / Local / Locked) |
| Gets worse with scale | More data = more noise | Quality filters + garbage collection + expiry |
| No curation | Passive storage | Active management: conflict detection, outdated marking, importance scoring |

The research is clear (see [OpenViking benchmarks](docs/MULTI_AGENT_ROADMAP.md#research-references)): structured, tiered retrieval with access control outperforms flat RAG by 96% on token efficiency and 44% on task completion.

---

## License

MIT — use it, fork it, build on it. If your agent stops forgetting, we did our job.

---

*v0.4.0 — 13 modules, 65+ functions, 45+ tests. Built from real problems, not theory. — [vivioo.io](https://vivioo.io)*
