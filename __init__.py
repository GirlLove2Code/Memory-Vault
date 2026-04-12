# Vivioo Memory System
# A local, privacy-first memory system for AI agents.
# Designed by the builder + Claude. Reviewed by the agent.

from .recall import (
    recall, startup_recall, recall_deep, recall_from_summary,
    what_do_i_know, get_recall_stats
)
from .entry_manager import (
    add_memory, get_entry, update_memory, delete_memory,
    mark_outdated, unmark_outdated, find_conflicts, list_entries,
    pin_memory, unpin_memory, score_importance
)
from .branch_manager import create_branch, list_branches, load_master_index, rebuild_master_index
from .privacy_filter import set_tier, get_tier, filter_for_llm
from .embedding import check_ollama
from .vector_store import init_store
from .garbage_collect import generate_report, find_stale_entries, find_duplicates, archive_entry
from .briefing import generate_briefing
from .timeline import get_timeline, get_decision_log, get_weekly_digest, format_timeline
from .expiry import (
    set_expiry, set_auto_expiry, refresh_entry,
    get_refresh_queue, backfill_expiry
)
from .hooks import register_hook, register_file_hook, fire_hooks, get_event_log, list_hooks
from .auto_summary import update_summary, update_all_summaries, needs_update, get_summary_health
from .bulk_import import import_file, import_text, import_entries

# v0.5 — Corrections, Active Recall, TF-IDF, Benchmark
from .corrections import (
    add_correction, get_corrections, resolve_correction, recall_corrections
)
from .active_recall import (
    pre_task_recall, verify_recall, get_all_corrections_brief
)
from .tfidf import TFIDFIndex

__version__ = "0.5.0"
