# vivioo-memory

> Memory that actually works between sessions — no cloud, no API keys, just results.

A local, privacy-first memory system for AI agents. Built from two months of real experience building with an AI agent who needed persistent memory.

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
| Data | YouTube + social platform research |
| Both Sides | Human + Agent perspective |
| Tested | 30-day production experiment |
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
result["corrections"]    # Relevant corrections — always included
result["no_match"]       # True if no relevant memory found
```

### Corrections — the most important memory type (v0.5)

```python
from vivioo_memory import add_correction, pre_task_recall

# Save corrections from the owner — never expire, always surface
add_correction("marketing", "Don't use stock photos — use real screenshots",
               context="Boss reviewed the landing page", source="boss")

# Before starting work: check corrections + memories
context = pre_task_recall("Redesign the landing page", branch="marketing")
context["corrections"]     # → corrections that apply
context["should_warn"]     # → True if boss corrections exist
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

## Works Without Ollama. No Cloud. No Lock-In.

- **Zero required external services** — TF-IDF search works out of the box, no API keys needed
- **No runtime code fetching** — all dependencies are installed at build time, nothing pulled at runtime
- **No OpenAI required** — zero cloud dependencies
- **No LLM lock-in** — works with Claude, OpenAI, Gemini, local models, or anything else
- **Runs 100% locally** — your data never leaves your machine

### Requirements

- Python 3.9+
- No required external services — works out of the box with TF-IDF search

```bash
pip install -r requirements.txt
```

**Optional upgrades:**
- Install [ChromaDB](https://docs.trychroma.com/) for vector search: `pip install chromadb>=0.4.0`
- Install [Ollama](https://ollama.ai) with `nomic-embed-text` for semantic search: `ollama pull nomic-embed-text`

**Search fallback:** Semantic (Ollama+ChromaDB) → TF-IDF (zero-dep) → Keyword. Each level works independently.

---

## Alongside Native Memory Systems

Most AI agent platforms (OpenClaw, Claude Code, etc.) have their own built-in memory — auto-saved session notes, daily logs, context summaries. **This system complements those. It does not replace them.**

| System | Role | Analogy |
|--------|------|---------|
| **Platform's native memory** (daily notes, session logs) | Auto-captured, everything saved | Journal — safety net |
| **vivioo-memory** (this system) | Intentional, curated, organized | Filing cabinet — what you actually search |

They don't conflict. Let the native system auto-save. Use vivioo-memory for things worth organizing — decisions, learnings, feedback, patterns.

**For operators:** Before giving this to an agent that already has a memory system, explain the relationship. See [INTEGRATION_WITH_NATIVE_SYSTEMS.md](docs/INTEGRATION_WITH_NATIVE_SYSTEMS.md) for a setup guide.

---

## For Agent Owners: Making Your Agent Actually Use This

Installing Memory Vault is step one. Making your agent **use it every session** is step two — and it's the step most people skip.

Agents reload from their startup files each session. If Memory Vault isn't mentioned in those files, your agent won't know it exists after the first session.

### What to do after installing

**1. Find your agent's startup files.** These are the files your agent reads at the beginning of every session — typically named things like `IDENTITY.md`, `SYSTEM.md`, `INSTRUCTIONS.md`, or similar. Check your agent platform's docs for where these live.

**2. Add a memory block to the startup/identity file:**

```
## Memory System
You have a memory system at [path where you installed Memory Vault].
- Use recall() to search your memory before starting any task
- Use add_memory() to save important learnings, instructions, and decisions
- You do NOT need Ollama or any API key — keyword search works automatically
- If you see "Ollama not reachable" — ignore it, keyword search handles it
```

**3. Add a save routine to any periodic check file** (heartbeat, maintenance loop, etc.):

```
## Memory Check
- Did I learn something this session? Save it: add_memory("branch", "what I learned", importance=4)
- Did my owner give me an instruction? Save it with importance=5
- Did I make a mistake? Save what went wrong so I don't repeat it
```

**4. Tell your agent which branches exist** so they search by topic, not everything at once. List the branches relevant to your agent's work in the startup file.

### Why this matters

Without these steps, your agent will:
- Forget Memory Vault exists next session
- Never save anything (0 entries = no memory)
- Think they need an API key if they see Ollama error messages

This is the most common setup mistake. The code works. The agent just doesn't know it's there.

---

## Quick Start

```bash
# Clone
git clone https://github.com/vivioo-io/Memory-Vault.git
cd Memory-Vault

# Install
pip install -r requirements.txt

# Run tests (no Ollama needed)
python3 tests/test_core.py

# Optional: check if semantic search is available
python3 -c "from embedding import check_ollama; print(check_ollama())"
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
├── vector_store.py     ← ChromaDB vector storage + search (optional)
├── tfidf.py            ← Zero-dep TF-IDF search (default fallback)
├── corrections.py      ← Correction memory type (never expire, always surface)
├── active_recall.py    ← Forced active recall before tasks
├── benchmark.py        ← LongMemEval benchmark harness
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
│   ├── test_v05.py          ← 20 v0.5 tests (corrections, active recall, TF-IDF)
│   └── test_integration.py  ← 12 integration tests
└── docs/
    ├── ARCHITECTURE.md        ← Code-level architecture map
    ├── AGENT_GUIDE.md         ← Guide for agents using this system (includes filing rules)
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

### Corrections (v0.5)

| Function | What it does |
|----------|-------------|
| `add_correction(branch, correction, context, source)` | Save a correction. Importance 5, never expires. |
| `get_corrections(branch)` | List active corrections. |
| `resolve_correction(entry_id, branch, reason)` | Mark correction as applied. |
| `recall_corrections(query, branch)` | Find corrections relevant to a query. |

### Active Recall (v0.5)

| Function | What it does |
|----------|-------------|
| `pre_task_recall(task, branch)` | Get corrections + memories before starting work. |
| `verify_recall(recall_id)` | Confirm agent read and understood the context. |
| `get_all_corrections_brief(branch)` | Text dump of all active corrections. |

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

### v0.5 — Corrections, Active Recall, TF-IDF (current)
Built from production experience with two AI agents:
- **Corrections store** — never-expiring, always-surfacing correction memories
- **Active recall** — forced pre-task context verification (solves LOAD ≠ READ)
- **TF-IDF search** — zero-dependency search fallback (fixes ClawHub supply chain flag)
- **LongMemEval benchmark harness** — test against the UCLA standard
- **ChromaDB now optional** — TF-IDF handles search when ChromaDB isn't installed

See [WHATS_NEW_v05.md](docs/WHATS_NEW_v05.md) for full details.

### v0.6 — Multi-Agent (next)
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

## Limitations

- **Python only** — requires Python 3.9+. No JavaScript/TypeScript port yet.
- **Setup required** — not a pip-installable package yet (v0.5 goal). Clone the repo and install deps manually.
- **Single machine** — memory lives on disk. No built-in sync across devices or agents (multi-agent support in v0.5).
- **Keyword search without Ollama** — works well but semantic search (with Ollama) is more accurate for meaning-based queries.
- **Manual curation** — this is intentional memory, not auto-capture. The agent must actively call `add_memory()`. If they don't save it, it's not remembered.

---

## License

MIT — use it, fork it, build on it. If your agent stops forgetting, we did our job.

---

*v0.5.0 — 17 modules, 75+ functions, 53 tests. Built from real problems, not theory. — [vivioo.io](https://vivioo.io)*
