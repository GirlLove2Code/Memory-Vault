"""
Vivioo Memory — LongMemEval Benchmark Harness (v0.5)
Evaluates Memory Vault against the LongMemEval benchmark (UCLA, ICLR 2025).

LongMemEval tests 5 long-term memory abilities:
  1. Information extraction — retrieve facts from past sessions
  2. Multi-session reasoning — connect dots across sessions
  3. Knowledge updates — use the latest version when facts change
  4. Temporal reasoning — "what did I say last Tuesday?"
  5. Abstention — say "I don't know" when appropriate

Benchmark data: https://github.com/xiaowu0162/LongMemEval

Usage:
    from benchmark import run_benchmark, load_benchmark_data

    # Load the benchmark dataset
    data = load_benchmark_data("/path/to/LongMemEval/data/")

    # Run evaluation
    results = run_benchmark(data)
    print(f"Overall accuracy: {results['accuracy']:.1%}")
    print(f"By category: {results['by_category']}")

    # Compare with baseline
    report = generate_report(results)
    print(report)
"""

import json
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

from recall import recall
from entry_manager import add_memory, list_entries
from branch_manager import create_branch, list_branches


def load_benchmark_data(data_dir: str) -> dict:
    """
    Load LongMemEval benchmark data from disk.

    Expects the LongMemEval repository structure:
        data_dir/
        ├── sessions/          # conversation sessions
        ├── questions.json     # evaluation questions
        └── answers.json       # ground truth answers

    Args:
        data_dir: path to the LongMemEval data directory

    Returns:
        {
            "sessions": [...],
            "questions": [...],
            "answers": {...},
            "metadata": {"total_sessions": int, "total_questions": int},
        }
    """
    result = {"sessions": [], "questions": [], "answers": {}, "metadata": {}}

    # Load sessions
    sessions_dir = os.path.join(data_dir, "sessions")
    if os.path.isdir(sessions_dir):
        for fname in sorted(os.listdir(sessions_dir)):
            if fname.endswith(".json"):
                with open(os.path.join(sessions_dir, fname)) as f:
                    result["sessions"].append(json.load(f))

    # Load questions
    questions_path = os.path.join(data_dir, "questions.json")
    if os.path.isfile(questions_path):
        with open(questions_path) as f:
            result["questions"] = json.load(f)

    # Load answers
    answers_path = os.path.join(data_dir, "answers.json")
    if os.path.isfile(answers_path):
        with open(answers_path) as f:
            result["answers"] = json.load(f)

    result["metadata"] = {
        "total_sessions": len(result["sessions"]),
        "total_questions": len(result["questions"]),
    }

    return result


def ingest_sessions(sessions: List[dict], branch_prefix: str = "bench") -> dict:
    """
    Ingest benchmark sessions into Memory Vault branches.

    Each session becomes a branch, each message pair becomes an entry.
    This simulates real agent usage over time.

    Args:
        sessions: list of session dicts from load_benchmark_data()
        branch_prefix: prefix for benchmark branches

    Returns:
        {"branches_created": int, "entries_added": int, "errors": int}
    """
    created = 0
    added = 0
    errors = 0

    for i, session in enumerate(sessions):
        branch = f"{branch_prefix}/session-{i:03d}"

        try:
            summary = session.get("summary", f"Benchmark session {i}")
            create_branch(branch, summary=summary)
            created += 1
        except Exception:
            pass

        messages = session.get("messages", session.get("turns", []))
        for j, msg in enumerate(messages):
            content = msg if isinstance(msg, str) else msg.get("content", "")
            if not content:
                continue
            try:
                timestamp = session.get("timestamp")
                add_memory(
                    branch, content,
                    happened_at=timestamp,
                    source="benchmark",
                    auto_resolve=False,
                )
                added += 1
            except Exception:
                errors += 1

    return {"branches_created": created, "entries_added": added, "errors": errors}


def evaluate_question(question: dict, ground_truth: str) -> dict:
    """
    Evaluate a single benchmark question.

    Args:
        question: {"id": str, "text": str, "category": str, ...}
        ground_truth: the expected answer

    Returns:
        {
            "question_id": str,
            "category": str,
            "query": str,
            "retrieved": [entries found],
            "ground_truth": str,
            "recall_hit": True if ground truth content found in retrieved,
            "search_mode": "semantic" or "keyword",
            "result_count": int,
            "latency_ms": int,
        }
    """
    query = question.get("text", question.get("query", ""))
    category = question.get("category", "unknown")
    qid = question.get("id", "?")

    start = time.time()
    result = recall(query, top_k=10)
    latency = int((time.time() - start) * 1000)

    # Check if ground truth is in retrieved entries
    retrieved_texts = []
    for entry in result.get("local_context", []):
        retrieved_texts.append(entry.get("content", "").lower())

    ground_lower = ground_truth.lower()
    recall_hit = any(ground_lower in text or text in ground_lower
                     for text in retrieved_texts if text)

    # Also check partial match — ground truth words in retrieved
    if not recall_hit:
        gt_words = set(ground_lower.split())
        for text in retrieved_texts:
            text_words = set(text.split())
            overlap = len(gt_words & text_words) / max(len(gt_words), 1)
            if overlap >= 0.6:
                recall_hit = True
                break

    return {
        "question_id": qid,
        "category": category,
        "query": query,
        "retrieved": result.get("local_context", []),
        "ground_truth": ground_truth,
        "recall_hit": recall_hit,
        "search_mode": result.get("search_mode", "unknown"),
        "result_count": result.get("result_count", 0),
        "no_match": result.get("no_match", False),
        "latency_ms": latency,
    }


def run_benchmark(data: dict) -> dict:
    """
    Run the full benchmark evaluation.

    Args:
        data: output from load_benchmark_data()

    Returns:
        {
            "accuracy": float (0-1),
            "by_category": {category: {accuracy, count, correct}},
            "total_questions": int,
            "total_correct": int,
            "avg_latency_ms": float,
            "search_mode_distribution": {"semantic": int, "keyword": int},
            "details": [per-question results],
        }
    """
    questions = data.get("questions", [])
    answers = data.get("answers", {})

    if not questions:
        return {"error": "No questions found in benchmark data"}

    # Ingest sessions first
    sessions = data.get("sessions", [])
    if sessions:
        ingest_result = ingest_sessions(sessions)
        print(f"Ingested: {ingest_result}")

    details = []
    correct = 0
    total_latency = 0
    by_category = {}
    mode_counts = {"semantic": 0, "keyword": 0}

    for q in questions:
        qid = q.get("id", str(len(details)))
        gt = answers.get(qid, q.get("answer", ""))

        result = evaluate_question(q, gt)
        details.append(result)

        if result["recall_hit"]:
            correct += 1

        total_latency += result["latency_ms"]

        # Track by category
        cat = result["category"]
        if cat not in by_category:
            by_category[cat] = {"correct": 0, "count": 0}
        by_category[cat]["count"] += 1
        if result["recall_hit"]:
            by_category[cat]["correct"] += 1

        # Track search modes
        mode = result["search_mode"]
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

    # Calculate accuracies
    total = len(questions)
    for cat_data in by_category.values():
        cat_data["accuracy"] = (
            cat_data["correct"] / cat_data["count"]
            if cat_data["count"] > 0 else 0.0
        )

    return {
        "accuracy": correct / total if total > 0 else 0.0,
        "by_category": by_category,
        "total_questions": total,
        "total_correct": correct,
        "avg_latency_ms": total_latency / total if total > 0 else 0,
        "search_mode_distribution": mode_counts,
        "details": details,
    }


def generate_report(results: dict) -> str:
    """
    Generate a human-readable benchmark report.

    Args:
        results: output from run_benchmark()

    Returns:
        Formatted report text.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  MEMORY VAULT — LongMemEval Benchmark Report")
    lines.append("=" * 60)
    lines.append("")

    acc = results.get("accuracy", 0)
    total = results.get("total_questions", 0)
    correct = results.get("total_correct", 0)

    lines.append(f"Overall Accuracy: {acc:.1%} ({correct}/{total})")
    lines.append(f"Average Latency:  {results.get('avg_latency_ms', 0):.0f}ms")
    lines.append("")

    # By category
    lines.append("By Category:")
    lines.append("-" * 50)
    for cat, data in sorted(results.get("by_category", {}).items()):
        bar = "#" * int(data["accuracy"] * 20)
        lines.append(
            f"  {cat:<25} {data['accuracy']:>6.1%} "
            f"({data['correct']}/{data['count']}) {bar}"
        )
    lines.append("")

    # Search mode distribution
    modes = results.get("search_mode_distribution", {})
    lines.append("Search Modes:")
    for mode, count in modes.items():
        lines.append(f"  {mode}: {count}")
    lines.append("")

    # Comparison with known benchmarks
    lines.append("Comparison:")
    lines.append("-" * 50)
    lines.append(f"  Memory Vault:  {acc:.1%}")
    lines.append(f"  MemPal (raw):  96.6%")
    lines.append(f"  MemPal (rerank): 100%")
    lines.append(f"  Mem0:          ~48%")
    lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
