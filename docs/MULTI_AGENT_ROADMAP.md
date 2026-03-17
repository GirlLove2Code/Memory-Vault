# Multi-Agent Roadmap — Phase 2 (Future)

**Status:** Not started. Document this so a future Claude Code session can pick it up.
**Prerequisite:** Phase 1 (auto-capture) must be working and tested first.
**Inspired by:** OpenViking (ByteDance), claude-mem — reviewed March 2026

---

## Context for Future Claude Code Agent

If you're reading this, the builder wants to expand vivioo-memory from single-agent to multi-agent. Here's what you need to know about what's already built and what needs to change.

### What Exists Today (v0.4)

The system is 13 Python modules, ~4,500 lines, 45+ tests. Key files:

| File | What it does | Multi-agent relevance |
|------|-------------|----------------------|
| `recall.py` | Search front door — routing, quality filters, privacy split | Needs per-agent context |
| `entry_manager.py` | CRUD + importance scoring + conflict detection | Needs source agent tagging |
| `branch_manager.py` | Branch tree + master index | Needs workspace isolation |
| `privacy_filter.py` | 3-tier privacy (open/local/locked) | Needs per-agent access control |
| `hooks.py` | Event system (memory_added, memory_conflict, etc.) | Ready — agents can listen to events |
| `auto_capture.py` | Auto-capture from conversations (Phase 1) | Needs per-agent capture pipelines |
| `vector_store.py` | ChromaDB semantic search | May need per-agent collections |
| `briefing.py` | Session briefing generator | Needs multi-agent awareness |
| `config.json` | All thresholds and settings | Needs per-agent overrides |

### What Works Well (Don't Break These)

1. **JSON files = source of truth.** ChromaDB is a mirror. This is correct and should stay.
2. **Privacy filter baked into recall().** Never bypassed. Keep this.
3. **Hook system is extensible.** Adding new events is trivial — just call `fire_hooks(event, data)`.
4. **Branch structure is hierarchical.** Already supports parent/child — extend, don't replace.
5. **Graceful degradation.** No Ollama? Keyword search. No ChromaDB? Fallback. Keep this pattern.

### What Needs to Change

See the three features below. Build them in order.

---

## Feature 1: `.abstract` + `.overview` Per Branch

**What:** Formalized L0/L1 layers inspired by OpenViking's file system paradigm.

**Why:** Right now, the master index has branch names + entry counts. Branch summaries are auto-generated text blobs. For multi-agent, any agent needs to quickly scan what a branch contains WITHOUT loading entries. The current summary is okay for one agent but too unstructured for multiple agents to route efficiently.

**How it works:**

```
branches/
  knowledge-base/
    .abstract        ← L0: 1-2 lines, <100 tokens. "What is this branch?"
    .overview        ← L1: structured summary, <500 tokens. Key themes, entry count, last updated.
    index.json       ← existing metadata
    entries/         ← L2: full entries (loaded on demand)
      mem-123.json
    marketing/
      .abstract
      .overview
      index.json
      entries/
```

**`.abstract` format:**
```json
{
  "branch": "knowledge-base/marketing",
  "one_liner": "Marketing strategies, campaigns, and growth approaches",
  "entry_count": 12,
  "last_updated": "2026-03-12T...",
  "security": "open"
}
```

**`.overview` format:**
```json
{
  "branch": "knowledge-base/marketing",
  "themes": ["story-first campaigns", "content strategy", "growth hacking", "community building"],
  "top_entries": ["mem-abc (importance 5): ...", "mem-def (importance 4): ..."],
  "avg_importance": 3.8,
  "sources": {"manual": 4, "agent": 6, "auto-capture": 2},
  "freshness": "8 of 12 entries updated within 30 days",
  "security": "open"
}
```

**Integration points:**
- `auto_summary.py` already generates summaries — extend it to write `.abstract` and `.overview` files
- `branch_manager.py` `create_branch()` should generate initial `.abstract`
- `recall.py` `route_query()` should read `.abstract` files for faster routing (instead of loading full index)
- Master index rebuild should regenerate all `.abstract` + `.overview` files

**Effort:** Low-medium. Mostly extending existing `auto_summary.py` logic.

**Can build now:** Yes, this is safe to add without breaking anything. Just new files alongside existing ones.

---

## Feature 2: Private vs Shared Workspaces

**What:** Agent-specific directories alongside shared ones. Agent A's private notes don't pollute Agent B's memory.

**Why:** When multiple agents work on the same project, they each accumulate their own context (draft ideas, failed approaches, intermediate results). Without isolation, Agent B's recall results include Agent A's scratch notes, creating noise and potential confusion.

**How it works:**

```
branches/
  _shared/                    ← All agents can read and write
    knowledge-base/
    shared-projects/
  _agents/
    agent-1/                  ← Only Agent 1 reads/writes
      scratch/                ← Its working notes
      about-builder/          ← Its private knowledge about the builder
    agent-2/                  ← Only Agent 2 reads/writes
      scratch/
      task-notes/
  _inbox/                     ← Auto-capture holding area (any agent writes, builder reviews)
```

**Access control model:**

```python
# New concept: agent identity
class AgentContext:
    agent_id: str           # "agent-1", "agent-2"
    can_read: list[str]     # ["_shared/*", "_agents/agent-1/*"]
    can_write: list[str]    # ["_shared/*", "_agents/agent-1/*"]

# recall() gets an agent_context parameter
def recall(query, agent_context=None, ...):
    # If no context → legacy mode (reads everything, like today)
    # If context → only search branches the agent can read
```

**Migration from current structure:**
- Current branches become `_shared/` (backwards compatible)
- The primary agent's private branches (`about-builder`, `company-1`, `company-2`) move to `_agents/agent-1/`
- The privacy_filter.py still handles Open/Local/Locked — workspace isolation is a SEPARATE layer on top

**Key decision:** Workspace isolation (which agent can see which branch) is different from privacy tiers (what the LLM sees). They stack:
1. First: workspace check — can this agent access this branch?
2. Then: privacy check — can the LLM see this entry?

**Effort:** Medium. Requires changes to branch_manager, recall, privacy_filter, and config.

**Do NOT build until:** Phase 1 auto-capture is stable AND you have a second agent to test with.

---

## Feature 3: Pointer Passing Between Agents

**What:** When Agent A needs to share context with Agent B, it passes a branch path (pointer) — not the full text. Agent B then loads only what it needs.

**Why:** In traditional multi-agent setups, Agent A dumps its entire context into Agent B's prompt. This wastes tokens and pollutes context. OpenViking showed that passing a pointer like `branch://marketing/strategy` and letting Agent B load L0 → L1 → L2 on demand cuts token usage by 96%.

**How it works:**

```python
# Agent A finishes research and wants to hand off:
handoff = create_handoff(
    from_agent="agent-1",
    to_agent="agent-2",
    branch="shared-projects/vivioo",
    message="Website redesign research is done. Key findings in this branch.",
    highlight_entries=["mem-abc", "mem-def"]  # Optional: specific entries to look at first
)

# Agent B receives the handoff:
# 1. Reads .abstract (10 tokens) — "Is this relevant?"
# 2. Reads .overview (100 tokens) — "What are the key themes?"
# 3. Loads specific entries only if needed (on demand)
context = receive_handoff(handoff, agent_context=agent_2_context)
```

**The handoff object:**
```json
{
  "from": "agent-1",
  "to": "agent-2",
  "branch": "shared-projects/vivioo",
  "message": "Website redesign research is done.",
  "highlights": ["mem-abc", "mem-def"],
  "timestamp": "2026-03-12T...",
  "token_budget": 500
}
```

**Token budget:** The receiving agent specifies how many tokens it's willing to spend loading context. The system returns the best content within that budget:
- L0 (.abstract) always loaded (~10 tokens)
- L1 (.overview) loaded if budget allows (~100 tokens)
- L2 (entries) loaded selectively, highest importance first, until budget exhausted

**Integration with hooks:**
```python
# Agent B can listen for handoffs:
register_hook("handoff_received", agent_b_handler)
```

**Effort:** Medium-high. Requires Feature 1 (.abstract/.overview) and Feature 2 (workspaces) to be built first.

**Do NOT build until:** Features 1 and 2 are stable, and you have a real multi-agent use case to test with.

---

## Build Order Summary

```
Phase 1: Auto-capture (CURRENT — spec in AUTO_CAPTURE_SPEC.md)
  ↓ test with your primary agent for 1-2 weeks
Phase 2a: .abstract + .overview files (Feature 1)
  ↓ low risk, can add anytime
Phase 2b: Workspace isolation (Feature 2)
  ↓ needs a second agent to test
Phase 2c: Pointer passing (Feature 3)
  ↓ needs Features 1 + 2 working first
```

---

## Research References

These screenshots from a Chinese tech review (RedNote ID: 117418109, March 2026) are saved locally.

**claude-mem** — single-agent memory with:
- Silent lifecycle interceptor (auto-capture from conversation)
- SQLite + ChromaDB dual storage
- 3-tier retrieval: L0 index → L1 timeline → L2 full details
- Web UI console
- Claims 10x token cost reduction

**OpenViking** — multi-agent context database by ByteDance/Volcengine:
- File System Paradigm (tree-structured, not flat vector)
- `.abstract` + `.overview` per directory (L0/L1/L2 tiered loading)
- Private + shared workspaces per agent
- Pointer passing (paths, not full text)
- Visual retrieval traces for debugging
- Benchmarks: 51.23% task completion (up from 35.65%), 96% token reduction (2M vs 24.6M)

**Key insight from the article:** Traditional flat RAG doesn't scale for agents. The more memories you add, the noisier results get. Structured, tiered retrieval with access control is the path forward. vivioo-memory already has the tiered approach (master index → summary → entries) — the multi-agent features above extend this pattern.

---

## What NOT to Change

When building multi-agent features, preserve these principles:

1. **JSON files remain source of truth** — ChromaDB/vectors are always rebuildable
2. **Privacy filter stays in recall()** — never bypass it, never move it
3. **Hooks are best-effort** — core never breaks if a hook fails
4. **Graceful degradation** — system works without Ollama, without ChromaDB, without embeddings
5. **Branch aliases max 3** — don't increase this, it causes routing confusion
6. **Entries stay short** — one fact per entry, max paragraph length
7. **No database** — SQLite is tempting but JSON files are inspectable and portable

---

*Written March 12, 2026. For future Claude Code agent: read AUTO_CAPTURE_SPEC.md first, then this file. Phase 1 must be stable before starting any of this.*
