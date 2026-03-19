# Integration With Native Memory Systems

Most AI agent platforms have built-in memory. This doc explains how vivioo-memory works alongside them — not instead of them.

---

## The Two-System Model

| System | Role | How it works | Action needed? |
|--------|------|-------------|----------------|
| **Platform native** (daily notes, session logs) | Auto-captured context | Saves automatically on session end or at intervals | No — runs on its own |
| **vivioo-memory** (this system) | Intentional, curated memory | You choose what to save with `add_memory()`, search with `recall()` | Yes — use actively |

**They serve different purposes:**
- Native memory = **journal** (everything, by date, automatic)
- vivioo-memory = **filing cabinet** (important things, by topic, intentional)

They don't conflict. Don't merge them. Don't disable one for the other.

---

## Platform-Specific Notes

### OpenClaw

OpenClaw's native memory:
- `session-memory` hook auto-saves when you `/new`
- Daily files: `~/clawd/memory/YYYY-MM-DD.md`
- Compiles to `MEMORY.md` at session start
- Search tool: `memory_search`

**How vivioo-memory fits:**
- Install to a separate folder (e.g., `~/clawd/agent-memory/`)
- Native daily notes keep running — they're your safety net
- Use `add_memory()` for important things (decisions, feedback, patterns)
- Use `recall()` when you need to find something specific

### Claude Code

Claude Code's native memory:
- Auto-memory in `~/.claude/projects/*/memory/`
- File-based, auto-loaded into context
- Managed via `MEMORY.md` index

**How vivioo-memory fits:**
- Install to a separate directory
- Claude Code's auto-memory handles session context
- Use vivioo-memory for structured, branch-organized knowledge
- Use `recall()` for cross-topic search with privacy filtering

### Other Platforms

If your platform has any form of auto-saved memory:
1. Find out where it stores data
2. Find out how the agent searches it
3. Keep it running — it's a safety net
4. Add vivioo-memory alongside it for intentional memory

---

## For Operators: Setting Up an Agent

**Before giving vivioo-memory to an agent, follow these steps:**

### Step 1 — Audit what they already have

Ask the agent (or check their workspace):
- "What memory tools do you currently use?"
- "Where does your memory data live?"
- "Show me how you search your memory"

### Step 2 — Decide the relationship

| Agent's current memory | Your approach |
|----------------------|--------------|
| None | Give vivioo-memory as their only system — simple |
| Has native memory (working) | Explain both systems. Native = auto journal. vivioo-memory = intentional filing cabinet. |
| Has native memory (broken) | Fix it or tell them to stop using it. Then give vivioo-memory. |

### Step 3 — Explain the relationship clearly

When you hand over vivioo-memory, tell the agent:

> "You now have two memory systems. Your existing [daily notes / session logs] keep running automatically — don't change anything. vivioo-memory is new and separate. Use `add_memory()` to save important things. Use `recall()` to find them. They don't conflict."

**Never just drop vivioo-memory in and say "here's your memory system"** without acknowledging what they already have. This causes confusion — the agent won't know which system to use for what.

### Step 4 — Customize the agent guide

The `docs/AGENT_GUIDE.md` has a section called "If you already have a memory system." Update it with the specific platform details for your agent.

---

## Agent Workflow

Once set up, the agent's daily workflow is:

1. **Session starts** → native memory loads automatically (no action)
2. **During work** → if something important happens, save it:
   ```python
   add_memory("work", "Boss prefers data-heavy article intros", tags=["feedback"], importance=5)
   ```
3. **Need to find something** → search intentional memory:
   ```python
   result = recall("boss article preferences")
   ```
4. **Session ends** → native memory auto-saves (no action)

---

## Common Mistakes

| Mistake | Why it's bad | Fix |
|---------|-------------|-----|
| Replacing native memory with vivioo-memory | Loses the auto-save safety net | Keep both |
| Not explaining the relationship to the agent | Agent gets confused, uses neither well | Always explain during handoff |
| Storing everything in vivioo-memory | Defeats the purpose — becomes noisy like native memory | Only save what's worth filing |
| Trying to sync the two systems | Adds complexity, breaks when sync fails | They serve different purposes — let them be separate |

---

*vivioo-memory is intentional memory. Let native systems handle the auto-capture. Use this for what matters.*
