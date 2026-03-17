# Auto-Capture Spec — v0.5

**Problem:** The agent has to manually call `add_memory()` every time it learns something. It forgets to save most of what matters. Result: fish memory.

**Solution:** Intercept conversation events and automatically extract + file memories. The agent stops thinking about saving — the system does it automatically.

**Inspired by:** claude-mem (silent interceptor), OpenViking (lifecycle monitoring)

---

## How It Works

```
Conversation happens
       ↓
Auto-capture intercepts the exchange
       ↓
Classifier: "Is this worth remembering?"
       ↓
  NO → discard (most messages)
  YES → extract memory + pick branch + save
       ↓
add_memory() runs (scoring, conflict detection, hooks all fire)
       ↓
The agent never had to think about it
```

---

## What Gets Captured (and What Doesn't)

### CAPTURE — things worth remembering:

| Signal | Example | Why |
|--------|---------|-----|
| Decisions | "Let's go with Next.js" | Changes what's true |
| Preferences | "I prefer iterative building" | Shapes future work |
| Facts about people | "The builder is learning Python" | Personal context |
| Project state changes | "Deployed to Vercel" | Status update |
| Rules/constraints | "Never say human in content" | Must follow |
| New information | "MiniMax costs $50/month" | Knowledge |
| Corrections | "No, the color is #9A7B4F not gold" | Overrides old info |
| Explicit "remember this" | "Remember: the password is..." | Direct instruction |

### SKIP — noise that wastes memory:

| Signal | Example | Why skip |
|--------|---------|----------|
| Greetings | "Hey" | No information |
| Acknowledgments | "ok", "thanks", "cool" | No information |
| Questions without answers | "What should we do?" | Incomplete — wait for answer |
| Code output / logs | Stack traces, build output | Too noisy, changes fast |
| Repetition | Same thing said differently | Already captured |
| Temporary planning | "Let me think about this..." | Process, not knowledge |

---

## The Classifier

A simple rules-based classifier (no LLM needed for v1):

```python
def should_capture(message: str, role: str) -> dict:
    """
    Returns: {
        "capture": True/False,
        "confidence": 0.0-1.0,
        "reason": "why",
        "suggested_branch": "branch-name" or None
    }
    """
```

### Decision signals (high confidence → capture):

```python
DECISION_PATTERNS = [
    r"let's (go with|use|switch to|try)",
    r"(decided|choosing|picked|going with)",
    r"from now on",
    r"(always|never|must|rule:)",
    r"remember (this|that|:)",
    r"(important|critical|note to self)",
]
```

### Preference signals (medium confidence → capture):

```python
PREFERENCE_PATTERNS = [
    r"(i|we) prefer",
    r"(i|we) (like|don't like|hate|love)",
    r"(better|worse) (than|approach)",
    r"(my|our) (style|approach|way)",
]
```

### Fact signals (medium confidence → capture):

```python
FACT_PATTERNS = [
    r"(is|are|was|were|costs?|uses?|runs? on)",
    r"(deployed|launched|shipped|released|live at)",
    r"(changed|updated|switched|migrated|moved) (to|from)",
    r"\b(https?://|@\w+|#[A-Fa-f0-9]{6})\b",  # URLs, handles, hex colors
]
```

### Skip signals (discard):

```python
SKIP_PATTERNS = [
    r"^(ok|yes|no|sure|thanks|cool|got it|sounds good)\.?$",
    r"^(hey|hi|hello|morning|night)",
    r"^(let me|i'll|give me a)",
    r"(```[\s\S]*```)",  # code blocks
]
```

### Confidence scoring:

```
0.9+ → Auto-capture (decision + explicit "remember")
0.7-0.9 → Auto-capture with low importance (facts, preferences)
0.5-0.7 → Queue for review (might be worth saving)
<0.5 → Skip
```

---

## Branch Routing

When auto-capture fires, it needs to decide WHERE to file. Uses the existing filing rules:

```python
def route_to_branch(content: str, context: dict) -> str:
    """
    1. Check if we're in a known project context → shared-projects/{project}
    2. Check for company/client keywords → company-1 or company-2
    3. Check for personal info about the builder → about-builder
    4. Check topic keywords → knowledge-base/{topic}
    5. If confidence < 0.6 → file in a "inbox" branch for manual review
    """
```

### The Inbox Branch

New concept: `_inbox` — a temporary holding branch for memories the system isn't sure about.

- Auto-capture puts uncertain memories here
- The agent (or the builder) reviews periodically and moves them to the right branch
- Keeps the real branches clean
- Gets a briefing line: "You have 3 memories in inbox waiting for filing"

---

## Integration Points

### For OpenClaw (your agent's current setup):

Auto-capture hooks into the agent's conversation flow:

```python
# In the agent's session handler (or as an OpenClaw hook):
from auto_capture import process_exchange

def on_message(user_message, agent_response):
    # After every exchange, check if anything is worth saving
    captures = process_exchange(
        user_message=user_message,
        agent_response=agent_response,
        session_context={
            "project": "vivioo",        # current project context
            "topic": "website design",   # current topic if known
        }
    )

    for capture in captures:
        # Each capture is already saved via add_memory()
        # Just log it so the agent knows what was auto-saved
        print(f"Auto-saved: {capture['branch']} — {capture['content'][:60]}...")
```

### For Claude Code:

Could hook into Claude Code's hook system (post-tool events):

```json
// .claude/hooks.json
{
  "postToolUse": [
    {
      "matcher": "Write|Edit",
      "command": "python3 /path/to/vivioo-memory/auto_capture.py --event file_changed --path $FILE_PATH"
    }
  ]
}
```

### For any LLM agent:

Simple API — pass in the conversation turn, get back what was captured:

```python
from auto_capture import process_exchange

result = process_exchange(
    user_message="Let's switch to SQLite instead of JSON files",
    agent_response="Good idea. I'll update the storage layer."
)
# result: [{
#     "captured": True,
#     "content": "Decision: switching from JSON files to SQLite for storage",
#     "branch": "shared-projects/memory-system",
#     "importance": 4,
#     "reason": "decision_pattern: 'switch to'"
# }]
```

---

## What Gets Extracted

The classifier doesn't just save the raw message. It extracts a clean memory:

**Raw exchange:**
> User: "ok so the gold color is #9A7B4F not just 'gold', and we use system fonts not google fonts"
> Agent: "Got it, I'll update the design system."

**Extracted memories:**
1. `"Vivioo gold accent color is #9A7B4F"` → `shared-projects/vivioo` [tags: design, colors]
2. `"Vivioo uses system fonts, not Google Fonts"` → `shared-projects/vivioo` [tags: design, fonts]

**Rules for extraction:**
- One fact per memory (split compound statements)
- Remove filler words ("ok so", "I think", "basically")
- Keep specifics (numbers, names, URLs, colors)
- Add context if the raw message is ambiguous
- Max 80 words per extracted memory

---

## Deduplication

Before saving, check if we already know this:

```python
def is_duplicate(content: str, branch: str) -> bool:
    """
    1. Search existing entries in the branch
    2. If similarity > 0.85 with any active entry → duplicate
    3. If similarity > 0.75 AND same tags → probably duplicate
    4. Otherwise → new information
    """
```

This uses the existing `find_conflicts()` in entry_manager.py — auto-capture just calls it.

---

## Session Summary Capture

At the end of a session (or periodically), auto-capture generates a session summary:

```python
def capture_session_summary(exchanges: list, session_context: dict):
    """
    Looks at ALL exchanges in the session and extracts:
    1. Decisions made (highest priority)
    2. New facts learned
    3. State changes (deployed, fixed, broke)
    4. Open questions (for next session)

    Saves as a single "session summary" entry in the relevant branch
    with tag ["session-summary", "YYYY-MM-DD"]
    """
```

This is the safety net — even if individual message capture misses something, the session summary catches the big picture.

---

## Configuration

```python
# auto_capture_config.json
{
    "enabled": True,
    "min_confidence": 0.7,          # Below this → inbox
    "auto_file_confidence": 0.85,   # Above this → auto-file to branch
    "inbox_branch": "_inbox",
    "max_captures_per_exchange": 3,  # Don't over-capture
    "skip_roles": ["system"],        # Don't capture system messages
    "session_summary": True,         # Generate end-of-session summary
    "dedup_threshold": 0.85,         # Similarity threshold for "already know this"
    "extract_mode": "clean",         # "clean" = rewrite, "raw" = save as-is
    "quiet_mode": False              # True = don't log captures (stealth)
}
```

---

## Multi-Agent Prep

This design prepares for multi-agent by:

1. **`session_context` parameter** — each agent passes its own context, so captures are tagged by source agent
2. **`_inbox` branch** — shared inbox that any agent can write to, one agent (or the builder) reviews
3. **Event hooks** — other agents can listen to `memory_added` events from auto-capture
4. **Source tracking** — every auto-captured entry has `source: "auto-capture/{agent-name}"`

When you're ready for multi-agent:
- Each agent gets its own capture pipeline
- Shared branches have entries from multiple agents (tagged by source)
- Private branches only get captures from their owning agent
- A "coordinator" agent (or the builder) reviews the inbox

---

## Build Order

### Phase 1: Core classifier (build now)
- `auto_capture.py` — classifier + extractor + router
- `auto_capture_config.json` — settings
- Create `_inbox` branch
- Tests for classify, extract, route

### Phase 2: Integration (when the agent is stable)
- Hook into your agent's conversation loop
- Test with 1 day of real conversations
- Tune confidence thresholds based on results

### Phase 3: Session summaries
- End-of-session capture
- Periodic capture (every N exchanges)

### Phase 4: Multi-agent
- Per-agent capture pipelines
- Shared vs private branch routing
- Cross-agent event listening

---

## File Structure

```
vivioo-memory/
├── auto_capture.py              ← NEW: classifier + extractor + router
├── auto_capture_config.json     ← NEW: settings
├── tests/
│   └── test_auto_capture.py     ← NEW: tests
└── branches/
    └── _inbox/                  ← NEW: holding branch for uncertain captures
        └── index.json
```

---

## Success Metrics

After 1 week of auto-capture:
- **Capture rate:** 5-15 memories per day (from ~0 today when the agent forgets)
- **Precision:** 80%+ of auto-captures are actually worth keeping
- **Inbox size:** <10 items waiting for review at any time
- **Duplicate rate:** <5% duplicates getting through
- **Branch accuracy:** 85%+ filed in the correct branch automatically

---

*"The best memory system is one the agent doesn't have to think about."*
