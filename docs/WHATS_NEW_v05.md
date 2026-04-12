# What's New in v0.5

> Corrections, Active Recall, TF-IDF Search, and LongMemEval Benchmark

Released: April 12, 2026

---

## Why v0.5

v0.4 stored memories well but had two gaps discovered in production:

1. **Corrections got forgotten.** An agent corrected once would repeat the same mistake next session. Agent A's `BOSS-CORRECTIONS.md` pattern proved that corrections need to be durable, always-surfacing, never-expiring files — not regular memories.

2. **LOAD ≠ READ.** Injecting context into an agent's prompt doesn't mean the agent processes it. Agent B proved this with a 52-point gap between self-assessment and reality. Active recall — forcing the agent to engage with retrieved context — solves this.

3. **ChromaDB was required for search.** The ClawHub security scanner flagged Memory Vault as a supply chain risk because it imported ChromaDB at runtime. TF-IDF search eliminates this dependency for the default path.

---

## New Features

### 1. Corrections Store (`corrections.py`)

A new memory type designed for instructions, feedback, and mistake-prevention:

```python
from vivioo_memory import add_correction, recall_corrections

# Save a correction — importance 5, never expires
add_correction(
    "marketing",
    "Don't use stock photos — always use real screenshots",
    context="Boss reviewed the landing page draft",
    source="boss",
)

# Before starting work, check what corrections apply
relevant = recall_corrections("I'm redesigning the landing page")
```

**Properties:**
- Importance is always 5 (max)
- Never expires
- Always surfaces in recall when the topic matches
- Four sources: `boss`, `self`, `peer`, `system`
- Can be resolved when fully integrated

### 2. Active Recall (`active_recall.py`)

Forces agents to engage with memories before acting:

```python
from vivioo_memory import pre_task_recall, verify_recall

# Before any task — retrieves corrections + memories
context = pre_task_recall("Redesign the landing page", branch="marketing")

# context["corrections"]  → corrections that apply
# context["should_warn"]  → True if boss corrections exist
# context["verification"]["summary_prompt"] → text to confirm

# After agent confirms understanding
verify_recall(context["recall_id"])
```

### 3. TF-IDF Search (`tfidf.py`)

Zero-dependency text search that replaces ChromaDB for the default path:

```python
from vivioo_memory import TFIDFIndex

index = TFIDFIndex()
index.add("doc1", "Story-first marketing campaigns")
index.add("doc2", "Deploy server to Vercel")

results = index.search("marketing strategy")
# → [("doc1", 0.82)]
```

**Search fallback order is now:** Semantic (Ollama+ChromaDB) → TF-IDF → Keyword

### 4. LongMemEval Benchmark (`benchmark.py`)

Test Memory Vault against the UCLA LongMemEval benchmark:

```python
from benchmark import load_benchmark_data, run_benchmark, generate_report

data = load_benchmark_data("/path/to/LongMemEval/data/")
results = run_benchmark(data)
print(generate_report(results))
```

---

## Breaking Changes

None. All v0.4 APIs work unchanged.

## Dependency Changes

- **ChromaDB is now optional.** `requirements.txt` only requires `cryptography`.
- Install ChromaDB for best search accuracy: `pip install chromadb>=0.4.0`
- Without ChromaDB, TF-IDF search handles all queries automatically.

## New Exports

| Function | Module | Purpose |
|----------|--------|---------|
| `add_correction()` | corrections | Save a correction |
| `get_corrections()` | corrections | List active corrections |
| `resolve_correction()` | corrections | Mark correction as applied |
| `recall_corrections()` | corrections | Find corrections for a query |
| `pre_task_recall()` | active_recall | Get context before starting work |
| `verify_recall()` | active_recall | Confirm agent read the context |
| `get_all_corrections_brief()` | active_recall | Text dump of all corrections |
| `TFIDFIndex` | tfidf | Zero-dep search index |

## `recall()` Changes

The `recall()` response now includes a `corrections` field:

```python
result = recall("marketing strategy")
result["corrections"]   # NEW — relevant corrections
result["search_mode"]   # Now can be "semantic", "tfidf", or "keyword"
```

## Test Coverage

- 33 existing tests (unchanged, all passing)
- 20 new tests for v0.5 features
- **53 total tests, 0 failures**

---

## Architecture Insight

The v0.5 features come from real production experience with two AI agents:

| Pattern | Source | Lesson |
|---------|--------|--------|
| Corrections as durable files | Agent A's BOSS-CORRECTIONS.md | Corrections need architectural enforcement, not just storage |
| Forced active recall | Agent B's LOAD ≠ READ gap | Injecting context ≠ processing it |
| TF-IDF default search | ClawHub security flag | Zero-dep search eliminates supply chain concerns |
| PM agent architecture | The builder's fix for Agent B | Patch weaknesses with architecture, not prompts |
