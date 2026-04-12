"""
Memory Vault — LongMemEval Benchmark Harness (v0.5)
Evaluates Memory Vault against the LongMemEval benchmark (UCLA, ICLR 2025).

LongMemEval tests 5 long-term memory abilities:
  1. Information extraction — retrieve facts from past sessions
  2. Multi-session reasoning — connect dots across sessions
  3. Knowledge updates — use the latest version when facts change
  4. Temporal reasoning — "what did I say last Tuesday?"
  5. Abstention — say "I don't know" when appropriate

Benchmark data: https://github.com/xiaowu0162/LongMemEval
Dataset: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned

Usage:
    from benchmark import run_benchmark, load_benchmark_data

    # Load the benchmark dataset (use oracle, _s, or _m variant)
    data = load_benchmark_data("data/longmemeval_oracle.json")

    # Run evaluation
    results = run_benchmark(data)
    print(generate_report(results))

    # Export for official GPT-4o evaluation
    export_hypotheses(results, "results/memory_vault_hypotheses.jsonl")
"""

import json
import os
import time
from typing import List, Dict, Optional

from recall import recall
from entry_manager import add_memory
from branch_manager import create_branch


def load_benchmark_data(filepath: str) -> dict:
    """
    Load a LongMemEval JSON file.

    Supports all three variants:
      - longmemeval_oracle.json (only evidence sessions)
      - longmemeval_s_cleaned.json (~40 sessions per question)
      - longmemeval_m_cleaned.json (~500 sessions per question)

    Each instance has:
      question_id, question_type, question, answer,
      question_date, haystack_sessions, haystack_dates,
      answer_session_ids

    Returns:
        {"instances": [...], "metadata": {...}}
    """
    with open(filepath) as f:
        instances = json.load(f)

    # Count by category
    categories = {}
    for inst in instances:
        qtype = inst.get("question_type", "unknown")
        categories[qtype] = categories.get(qtype, 0) + 1

    return {
        "instances": instances,
        "metadata": {
            "total_questions": len(instances),
            "categories": categories,
            "source_file": os.path.basename(filepath),
        },
    }


def ingest_instance(instance: dict, branch_prefix: str = "bench") -> dict:
    """
    Ingest one benchmark instance's haystack sessions into Memory Vault.

    Each session becomes entries in a branch. Messages are stored with
    their timestamps to support temporal reasoning.

    Returns:
        {"branches_created": int, "entries_added": int, "errors": int}
    """
    created = 0
    added = 0
    errors = 0

    sessions = instance.get("haystack_sessions", [])
    dates = instance.get("haystack_dates", [])
    session_ids = instance.get("haystack_session_ids", [])

    for i, session in enumerate(sessions):
        sid = session_ids[i] if i < len(session_ids) else f"s{i:03d}"
        branch = f"{branch_prefix}/{sid}"
        timestamp = dates[i] if i < len(dates) else None

        try:
            create_branch(branch, summary=f"Benchmark session {sid}")
            created += 1
        except Exception:
            pass

        # Each session is a list of {"role": ..., "content": ...} turns
        turns = session if isinstance(session, list) else []
        for turn in turns:
            content = turn.get("content", "") if isinstance(turn, dict) else str(turn)
            if not content or not content.strip():
                continue
            role = turn.get("role", "user") if isinstance(turn, dict) else "user"
            try:
                add_memory(
                    branch,
                    f"[{role}] {content}",
                    happened_at=timestamp,
                    source="benchmark",
                    auto_resolve=False,
                )
                added += 1
            except Exception:
                errors += 1

    return {"branches_created": created, "entries_added": added, "errors": errors}


def clear_benchmark_branches(branch_prefix: str = "bench"):
    """Remove all benchmark branches to reset between runs."""
    import shutil
    branches_dir = os.path.join(os.path.dirname(__file__), "branches")
    bench_dir = os.path.join(branches_dir, branch_prefix)
    if os.path.isdir(bench_dir):
        shutil.rmtree(bench_dir)


def evaluate_question(instance: dict) -> dict:
    """
    Evaluate a single LongMemEval question using Memory Vault recall.

    Uses two scoring methods:
      1. Retrieval hit — did we retrieve entries containing the answer?
      2. Word overlap — 60% threshold for partial matches

    Returns per-question result dict.
    """
    qid = instance.get("question_id", "?")
    qtype = instance.get("question_type", "unknown")
    question = instance.get("question", "")
    answer = instance.get("answer", "")
    is_abstention = qid.endswith("_abs")

    start = time.time()
    result = recall(question, top_k=10)
    latency = int((time.time() - start) * 1000)

    # Collect all retrieved text
    retrieved_texts = []
    for entry in result.get("local_context", []):
        text = entry.get("content", "") if isinstance(entry, dict) else str(entry)
        retrieved_texts.append(text.lower())

    no_match = result.get("no_match", False)

    # For abstention questions: correct if we return no_match
    if is_abstention:
        recall_hit = no_match or result.get("result_count", 0) == 0
    else:
        # Check exact containment
        answer_lower = answer.lower()
        recall_hit = any(
            answer_lower in text or text in answer_lower
            for text in retrieved_texts if text
        )

        # Partial match: 60% word overlap
        if not recall_hit:
            answer_words = set(answer_lower.split())
            for text in retrieved_texts:
                text_words = set(text.split())
                if not answer_words:
                    break
                overlap = len(answer_words & text_words) / len(answer_words)
                if overlap >= 0.6:
                    recall_hit = True
                    break

    # Build hypothesis (our system's answer) from retrieved context
    if is_abstention and (no_match or not retrieved_texts):
        hypothesis = "I don't have any memory of that."
    elif retrieved_texts:
        # Use the top retrieved entry as our answer basis
        hypothesis = retrieved_texts[0] if retrieved_texts else ""
    else:
        hypothesis = "I don't have any memory of that."

    return {
        "question_id": qid,
        "question_type": qtype,
        "question": question,
        "answer": answer,
        "hypothesis": hypothesis,
        "recall_hit": recall_hit,
        "is_abstention": is_abstention,
        "search_mode": result.get("search_mode", "unknown"),
        "result_count": result.get("result_count", 0),
        "no_match": no_match,
        "latency_ms": latency,
    }


def run_benchmark(data: dict, progress: bool = True) -> dict:
    """
    Run the full LongMemEval benchmark.

    For each instance:
      1. Clear previous benchmark data
      2. Ingest that instance's haystack sessions
      3. Evaluate the question via recall()

    This tests each question independently with its own history.

    Args:
        data: output from load_benchmark_data()
        progress: print progress updates

    Returns:
        Full results dict with accuracy, per-category breakdown, details.
    """
    instances = data.get("instances", [])
    if not instances:
        return {"error": "No instances found in benchmark data"}

    details = []
    correct = 0
    total_latency = 0
    by_category = {}
    mode_counts = {}

    for idx, instance in enumerate(instances):
        if progress and idx % 50 == 0:
            print(f"  [{idx}/{len(instances)}] Processing...")

        # Fresh state per question
        clear_benchmark_branches()
        ingest_instance(instance)

        # Evaluate
        result = evaluate_question(instance)
        details.append(result)

        if result["recall_hit"]:
            correct += 1

        total_latency += result["latency_ms"]

        # Track by category
        cat = result["question_type"]
        if cat not in by_category:
            by_category[cat] = {"correct": 0, "count": 0}
        by_category[cat]["count"] += 1
        if result["recall_hit"]:
            by_category[cat]["correct"] += 1

        # Track search modes
        mode = result["search_mode"]
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

    # Calculate accuracies
    total = len(instances)
    for cat_data in by_category.values():
        cat_data["accuracy"] = (
            cat_data["correct"] / cat_data["count"]
            if cat_data["count"] > 0 else 0.0
        )

    # Cleanup
    clear_benchmark_branches()

    return {
        "accuracy": correct / total if total > 0 else 0.0,
        "by_category": by_category,
        "total_questions": total,
        "total_correct": correct,
        "avg_latency_ms": total_latency / total if total > 0 else 0,
        "search_mode_distribution": mode_counts,
        "source_file": data.get("metadata", {}).get("source_file", "unknown"),
        "details": details,
    }


def export_hypotheses(results: dict, output_path: str):
    """
    Export results as JSONL for official LongMemEval GPT-4o evaluation.

    Format: one JSON object per line with question_id and hypothesis.

    Then run:
        cd LongMemEval/src/evaluation
        python3 evaluate_qa.py gpt-4o <output_path> <data_file>
        python3 print_qa_metrics.py gpt-4o <output_path>.log <data_file>
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for detail in results.get("details", []):
            line = json.dumps({
                "question_id": detail["question_id"],
                "hypothesis": detail["hypothesis"],
            })
            f.write(line + "\n")
    print(f"Exported {len(results.get('details', []))} hypotheses to {output_path}")


def generate_report(results: dict) -> str:
    """Generate a human-readable benchmark report."""
    lines = []
    lines.append("=" * 60)
    lines.append("  MEMORY VAULT — LongMemEval Benchmark Report")
    lines.append("=" * 60)
    lines.append("")

    src = results.get("source_file", "unknown")
    lines.append(f"Dataset: {src}")

    acc = results.get("accuracy", 0)
    total = results.get("total_questions", 0)
    correct = results.get("total_correct", 0)

    lines.append(f"Overall Retrieval Accuracy: {acc:.1%} ({correct}/{total})")
    lines.append(f"Average Latency: {results.get('avg_latency_ms', 0):.0f}ms")
    lines.append("")

    # By category
    lines.append("By Category:")
    lines.append("-" * 55)
    for cat, data in sorted(results.get("by_category", {}).items()):
        bar = "#" * int(data["accuracy"] * 20)
        lines.append(
            f"  {cat:<30} {data['accuracy']:>6.1%} "
            f"({data['correct']}/{data['count']}) {bar}"
        )
    lines.append("")

    # Search mode distribution
    modes = results.get("search_mode_distribution", {})
    lines.append("Search Modes:")
    for mode, count in modes.items():
        lines.append(f"  {mode}: {count}")
    lines.append("")

    # Comparison
    lines.append("Comparison (retrieval accuracy):")
    lines.append("-" * 55)
    lines.append(f"  Memory Vault (this run): {acc:.1%}")
    lines.append(f"  MemPal (raw):            96.6%")
    lines.append(f"  MemPal (rerank):         100%")
    lines.append(f"  Mem0:                    ~48%")
    lines.append("")
    lines.append("Note: official scoring requires GPT-4o judge.")
    lines.append("Run export_hypotheses() then use LongMemEval's evaluate_qa.py")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
