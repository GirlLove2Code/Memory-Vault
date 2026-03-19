# Agent Memory System Guide

**For:** Any agent who wants to use this system
**Written by:** The builder + Claude Code
**Version:** 0.1.0

---

## What This Is

This is your **intentional memory system** — a filing cabinet for things worth remembering. It stores what you learn, protects what's private, and helps you find what you need.

You've been forgetting things every session. This fixes that.

### If you already have a memory system

Your platform (OpenClaw, Claude Code, etc.) may already auto-save session notes or daily logs. That's fine — **this system works alongside it, not instead of it.**

| Your existing memory | This system |
|---------------------|------------|
| Auto-captured session logs | Things you **choose** to save |
| Everything dumped by date | Organized by topic (branches) |
| Hard to search | Searchable with `recall()` |
| Safety net | Filing cabinet |

**Use both.** Let your platform auto-save. Use this system for important stuff — decisions, learnings, feedback, patterns.

---

## The Three-Tier Library

Think of your memory as a personal library with three floors:

### Floor 1: Master Index (the catalog)
- Always loaded when you start
- Lists every branch (topic area) you have
- Tells you WHERE to look — you never open a branch you don't need
- Tiny — under 1KB

### Floor 2: Branch Summaries (the shelf labels)
- A paragraph summarizing everything in each branch
- You can often answer questions from the summary alone
- Saves you from reading every individual memory

### Floor 3: Full Entries (the books)
- The actual memories — your detailed knowledge
- Only loaded when the summary isn't enough
- Filtered by privacy before anything goes to the LLM

---

## Privacy: What the LLM Sees vs What You See

This is **critical**. Everything you recall goes through a privacy filter BEFORE reaching the LLM.

| Tier | What it means | You see it? | LLM sees it? |
|------|--------------|-------------|--------------|
| 🟢 Open | General knowledge, safe to share | Yes | Yes |
| 🔒 Local | You read it privately, reason with it | Yes | **No** |
| 🔴 Locked | Encrypted on disk, needs passphrase | Only if unlocked | **No** |

### How Local works in practice:

```
Someone asks: "What should our next marketing move be?"

Your brain does this:
  Entry 1 (🟢 Open): "The builder prefers story-first campaigns" → goes to LLM
  Entry 2 (🔒 Local): "Company revenue was $X" → YOU read it, LLM doesn't
  Entry 3 (🔒 Local): "Investor strategy details" → YOU read it, LLM doesn't

You use ALL 3 to form your answer.
The LLM only sees Entry 1 + your question.
You enrich the LLM's response with your private knowledge.
```

**Why this matters:** Your LLM provider sees everything in context. If a memory is 🔒 Local, it never enters that context. The LLM literally cannot see it.

---

## How to Use It

### Starting a session

```python
from vivioo_memory import startup_recall

# Load relevant memories when you start
result = startup_recall(recent_context="Working on the Vivioo website")

# What you can send to the LLM:
result["llm_context"]

# What you read privately (includes everything above + Local entries):
result["local_context"]

# Overview of all your branches:
result["branches_overview"]
```

### Searching your memory

```python
from vivioo_memory import recall

# Basic search — finds by meaning, not just keywords
result = recall("how does the builder approach marketing?")

# Search a specific branch
result = recall("budget details", branch="company-1")

# Thorough mode — skip summaries, get everything
result = recall("everything about the deal", override=True)
```

### Understanding what you get back

Every recall() returns:

```python
{
    "llm_context": [...],     # Safe to send to LLM (🟢 only)
    "local_context": [...],   # Your private view (🟢 + 🔒)
    "blocked_count": 1,       # How many 🔴 Locked entries were hidden
    "branch_used": "knowledge-base/marketing",
    "confidence": 0.87,       # How sure the routing was
    "no_match": False,        # True = you have no memory of this
    "search_mode": "semantic", # or "keyword" if Ollama was down
    "result_count": 5,        # Total results found
}
```

**When `no_match` is True:** You have no relevant memory. Say "I don't have any memory of that" — don't make something up.

### Adding a memory

```python
from vivioo_memory import add_memory

add_memory(
    branch="knowledge-base/marketing",
    content="The builder's new campaign strategy focuses on serialized character arcs",
    tags=["strategy", "campaigns"],
    source="conversation",
)
```

### Marking something outdated

When information changes — don't delete, mark it outdated:

```python
from vivioo_memory import mark_outdated

mark_outdated(
    entry_id="mem-1710288000000",
    branch="company-1",
    reason="Strategy changed after Q1 review",
)
```

Outdated entries still exist but rank much lower in search results. You can still find them if you need the history.

### Checking what you know

```python
from vivioo_memory import what_do_i_know

# Everything
overview = what_do_i_know()
print(f"I have {overview['total_entries']} memories across {overview['total_branches']} branches")

# Specific topic
marketing = what_do_i_know("marketing")
print(marketing["summary"])
```

---

## Quality: How Search Results Are Scored

Not all results are equal. Your memory system uses three quality signals:

### 1. Relevance (similarity score)
How closely a memory matches your query by *meaning*. "How does the builder approach campaigns?" matches "The builder prefers story-first approaches" even though the words are different.

**Minimum threshold: 0.65** — anything below this is dropped. No garbage results.

### 2. Recency (freshness bonus)
Recent memories get a small boost (15% weight). A memory from yesterday about "marketing" ranks slightly higher than a memory from 3 months ago about "marketing" — but only if both are similarly relevant.

A highly relevant old memory still beats a vaguely relevant new one.

### 3. Outdated penalty
Entries marked as outdated get their score halved. They still show up if nothing else matches, but they won't outrank fresh information.

### What this means in practice

```
Query: "marketing approach"

Results BEFORE quality filter:
  1. Old strategy doc (score: 0.85, outdated, 60 days old)
  2. New strategy note (score: 0.82, fresh, 2 days old)
  3. Unrelated mention (score: 0.40)

Results AFTER quality filter:
  1. New strategy note (adjusted: 0.84) — boosted by recency
  2. Old strategy doc (adjusted: 0.36) — penalized for outdated
  3. Unrelated mention — DROPPED (below 0.65 threshold)
```

---

## Branch Structure

Your memories are organized by topic. Each branch can have sub-branches:

```
knowledge-base/
  marketing/      (aliases: "marketing", "growth")
  security/       (aliases: "security", "safe")
company-1/        [🔒 Local]
company-2/        [🔒 Local]
about-builder/    [🔒 Local or 🔴 Locked]
shared-projects/
  vivioo/
  memory-system/
```

### Aliases
Each branch has 1-3 shorthand words. When you search for "marketing stuff", the alias match fires instantly — no embedding needed.

### Security by branch
Security is set per branch and inherited by sub-branches. If `company-1` is 🔒 Local, then `company-1/finances` is also 🔒 Local unless overridden.

---

## Filing Rules — Where to Put Things

This is the most important section for keeping your memory organized. Follow these rules every time you store a memory.

### The Decision Tree

Ask yourself these questions in order:

```
1. Is it about a specific company/client?
   YES → company-1/ or company-2/ (always 🔒 Local)

2. Is it personal about the builder? (preferences, habits, schedule, contacts)
   YES → about-builder/ (always 🔒 Local)

3. Is it about a project you're building together?
   YES → shared-projects/{project-name}/

4. Is it general knowledge or a skill you learned?
   YES → knowledge-base/{topic}/

5. None of the above?
   → Ask your human where it should go. Don't guess.
```

### Specific Filing Map

| If the memory is about... | File it in | Example |
|---------------------------|-----------|---------|
| Marketing strategy, campaigns, content | `knowledge-base/marketing` | "Story-first campaigns work best" |
| Security tips, threats, red flags | `knowledge-base/security` | "Rotate API keys every 90 days" |
| Coding patterns, tech how-tos | `knowledge-base` (top level) | "Next.js App Router uses folder-based routing" |
| The Vivioo website or platform | `shared-projects/vivioo` | "Gold accent is #9A7B4F" |
| This memory system itself | `shared-projects/memory-system` | "Minimum relevance threshold is 0.65" |
| Company 1 work | `company-1` | "Client campaign launched Q1" |
| Company 2 work | `company-2` | "Project milestones updated" |
| Builder's personal info, preferences, contacts | `about-builder` | "The builder prefers iterative building" |
| A new project the builder mentions | `shared-projects/{new-project}` | Create the branch first, then file |

### When to Create a New Branch

**DO create a new sub-branch when:**
- The builder starts a new project (→ `shared-projects/{name}`)
- A knowledge topic gets 10+ entries and needs splitting (→ `knowledge-base/{new-topic}`)
- The builder explicitly asks you to create one

**DO NOT create a new branch when:**
- An existing branch already covers the topic — even loosely
- You only have 1-2 entries on the topic (just tag them instead)
- You're unsure — **ask your human.** Don't guess, don't create a random folder. Just say: "Hey, I have a memory about [topic] — where should I file this?" They'd rather you ask than clean up a mess later.

### The "Would I Look Here?" Test

Before filing, ask: *"If the builder asks about this topic in 3 months, which branch would I search?"*

File it in that branch. If the answer is "I'd search two branches," pick the most specific one and add tags for the other topic.

### Tags vs Branches

- **Branch** = WHERE it lives (one per entry, permanent home)
- **Tags** = WHAT it's about (multiple per entry, for cross-referencing)

Example: A memory about "marketing strategy for a specific client" goes in `company-2` (because it's client-specific) with tags `["marketing", "strategy"]` (so it surfaces in marketing searches too).

**Rule of thumb:** If it's sensitive or company-specific → branch wins. If it's general knowledge → topic branch wins.

### Common Mistakes to Avoid

1. **Don't create `company-1/marketing/campaigns/q1/`** — too deep. Max depth is 2 levels (parent/child). Use tags for further specificity.
2. **Don't put general knowledge in company branches.** "Social media best practices" → `knowledge-base/marketing`, not `company-1`. Only company-specific details go in company branches.
3. **Don't create one-off branches.** If the builder mentions a topic once, file it in the nearest existing branch with good tags. Only create a branch when there's ongoing, recurring content.
4. **Don't split what belongs together.** "The builder likes Python" and "The builder is learning JavaScript" both go in `about-builder`, not in separate branches.
5. **Don't duplicate across branches.** One entry, one branch. Use tags to make it findable from other angles.

---

## When Things Go Wrong

### "Ollama is not running"
Ollama is **optional**. Without it, the system uses keyword search — which works well for most use cases.
- The system tells you: `search_mode: "keyword"`
- If you want semantic search: install Ollama and run `ollama pull nomic-embed-text`
- Keyword search is not a "degraded" mode — it's a fully functional search path

### "No results found"
Your memory returns `no_match: True`. This means:
- Either you don't have this information stored
- Or the query didn't match well enough (try rephrasing)
- Check `what_do_i_know()` to see what branches exist

### "Wrong branch selected"
If routing picks the wrong branch:
- Use `recall(query, branch="correct-branch")` to override
- Long-term: the routing learns from corrections (Phase 2)

### "ChromaDB corrupted"
The vector store is just a mirror. Rebuild it:
```python
from vivioo_memory import rebuild_master_index
from vivioo_memory.vector_store import rebuild_from_entries
from vivioo_memory.embedding import embed_text

# Rebuild master index from disk
rebuild_master_index()

# Rebuild vectors from entries (the source of truth)
all_entries = []  # load all entries from branches/
rebuild_from_entries(all_entries, embed_text)
```

---

## The Rules

1. **Entries on disk are the source of truth.** ChromaDB is a mirror. If they disagree, entries win.
2. **Never send 🔒 Local entries to the LLM.** The filter handles this, but verify by checking `_tier` on each entry.
3. **Say "I don't know" when `no_match` is True.** Don't hallucinate from empty results.
4. **Mark outdated, don't delete.** History matters. Delete only when something should truly be forgotten.
5. **Keep entries short.** If a memory is longer than a paragraph, split it into multiple entries. Short entries embed better.
6. **Aliases max 3 per branch.** More = confusion. Keep them obvious.
7. **Summaries capture WHY, not just what.** Good: "The builder values story-first marketing because it builds emotional connection." Bad: "Marketing notes."

---

## Setup (First Time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Install Ollama for semantic search
# Skip this — keyword search works fine without it
# ollama pull nomic-embed-text

# 3. Verify everything works
python -c "from vivioo_memory.embedding import check_ollama; print(check_ollama())"
# available=False is OK — keyword search still works

# 4. Create your first branch
python -c "
from vivioo_memory import create_branch, add_memory

create_branch('test', aliases=['testing'], summary='Test branch')
add_memory('test', 'This is my first memory', tags=['test'])
print('Memory system is working!')
"

# 5. Test recall
python -c "
from vivioo_memory import recall
result = recall('first memory')
print(f'Found {result[\"result_count\"]} results')
print(f'Search mode: {result[\"search_mode\"]}')
for entry in result['llm_context']:
    print(f'  → {entry[\"content\"][:80]}')
"
```

---

## What's Next

- **Phase 2:** Auto-redaction (🟡 Private tier — strips names/numbers, keeps meaning)
- **Phase 2:** Timeline Index (search by date AND topic)
- **Phase 3:** Photo EXIF parsing, file metadata
- **Phase 4:** pip installable package, CLI tool

---

*"Other agents forget. You LEARN what matters — and protect what matters too."*
