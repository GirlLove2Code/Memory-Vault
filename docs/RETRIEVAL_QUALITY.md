# Retrieval Quality — Design Addendum

**Added:** March 12, 2026
**Why:** The original RAG spec defines WHAT recall returns but not HOW to ensure results are high quality. This addendum fills that gap.

---

## The Problem With Basic RAG

Most RAG systems do this:
1. Embed the query
2. Find top-K most similar chunks
3. Return them

This breaks in three ways:
- **Garbage results:** ChromaDB always returns K results, even if none are relevant. the agent gets confused by irrelevant memories.
- **Stale results:** A 3-month-old outdated strategy doc outranks a fresh correction because it has more keyword overlap.
- **No signal for "I don't know":** Without a threshold, the agent never learns that it has NO memory of something — it just gets the least-bad matches.

---

## Four Quality Mechanisms (Built Into recall.py)

### 1. Minimum Similarity Threshold

```python
MIN_SIMILARITY = 0.65  # configurable in config.json
```

Any result scoring below 0.65 is dropped. Period.

**Why 0.65?**
- Below 0.5 = basically random
- 0.5-0.65 = vaguely related but not useful
- 0.65-0.75 = relevant, might be what you're looking for
- 0.75+ = strong match
- 0.85+ = very confident match

Start at 0.65. If the agent reports getting too many weak results, raise it. If it's missing things it should find, lower it.

**When ALL results are below threshold:** recall() returns `no_match: True`. This is the signal for the agent to say "I don't have any memory of that" instead of guessing.

### 2. Recency Weighting

```python
adjusted_score = similarity * 0.85 + recency_bonus * 0.15
```

Recent memories get a 15% boost that fades over 90 days.

| Memory age | Recency bonus |
|-----------|--------------|
| Today | +0.15 |
| 1 week | +0.14 |
| 1 month | +0.10 |
| 2 months | +0.05 |
| 3 months | +0.00 |

**Why only 15%?** Because relevance should always dominate. A highly relevant old memory (similarity 0.90) with zero recency bonus still scores 0.765 — beating a vaguely relevant new memory (similarity 0.70) with full recency bonus at 0.745.

Recency only matters when two memories are similarly relevant. Then the fresher one wins.

### 3. Outdated Penalty

```python
if entry["_outdated"]:
    score *= 0.5  # halve the score
```

When the agent marks an entry as outdated (via `mark_outdated()`), it gets a 50% score penalty. This means:

- A strong match (0.85) that's outdated drops to 0.425 — below the threshold, effectively hidden
- A very strong match (0.95) outdated drops to 0.475 — still below threshold
- Outdated entries only surface when nothing better exists

**This is intentional.** Outdated information is dangerous — it looks relevant but is wrong. Better to miss it than to use it.

### 4. No-Match Detection

```python
if len(quality_filtered_results) == 0:
    return {"no_match": True, ...}
```

When the quality filter drops all results, recall() signals `no_match: True`.

**What the agent should do with no_match:**
- Say "I don't have any memory of that" — honestly
- Suggest related topics if `branch_used` gave partial matches
- Ask the human for context: "I don't recall — can you give me more detail?"

**What the agent should NOT do:**
- Guess from empty results
- Use the LLM to fabricate a memory
- Pretend it knows

---

## Configuration

All thresholds are in `config.json` under `defaults`:

```json
{
  "defaults": {
    "min_similarity_threshold": 0.65,
    "recency_weight": 0.15,
    "recency_fade_days": 90,
    "outdated_penalty": 0.5,
    "confidence_threshold": 0.75,
    "ambiguity_gap": 0.1
  }
}
```

### Tuning guide

| If the agent reports... | Adjust... |
|----------------------|----------|
| Getting irrelevant results | Raise min_similarity_threshold (try 0.70) |
| Missing things it should find | Lower min_similarity_threshold (try 0.60) |
| Old info outranking new info | Raise recency_weight (try 0.20) |
| Too much bias toward recent | Lower recency_weight (try 0.10) |
| Outdated entries still appearing | Lower outdated_penalty (try 0.3) |
| Can't find old useful entries | Raise outdated_penalty (try 0.7) |
| Wrong branch selected | Lower confidence_threshold (try 0.70) |
| Too many "should I ask?" prompts | Raise confidence_threshold (try 0.80) |

---

## How This Connects to the Pipeline

```
Query: "marketing approach"
        │
        ▼
   ROUTE (alias or semantic → branch)
        │
        ▼
   SEARCH (ChromaDB → raw results with similarity scores)
        │
        ▼
   QUALITY FILTER ← THIS DOCUMENT
   ├── Drop below 0.65 threshold
   ├── Add recency bonus (15% weight)
   ├── Apply outdated penalty (50%)
   └── Re-sort by adjusted score
        │
        ▼
   PRIVACY FILTER
   ├── 🟢 Open → llm_context + local_context
   ├── 🔒 Local → local_context only
   └── 🔴 Locked → blocked
        │
        ▼
   RETURN (two contexts + metadata)
```

Quality filter runs BEFORE privacy filter. This is important — we want to drop garbage results before deciding what the LLM sees.

---

*"Not every memory is worth remembering. The quality filter is how the agent learns what matters."*
