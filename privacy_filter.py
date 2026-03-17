"""
Vivioo Memory — Privacy Filter (Step 1)
The bouncer. Controls what the LLM sees and what stays private.

Three tiers:
  🟢 Open   — safe to send to LLM
  🔒 Local  — Agent reads, LLM never sees
  🔴 Locked — encrypted, requires passphrase to access

This runs LOCALLY. Nothing in this file sends data anywhere.
"""

import json
import os
from typing import List, Dict, Tuple, Optional

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

VALID_TIERS = {"open", "local", "locked"}


def load_config(config_path: str = None) -> dict:
    """Load the security config file."""
    path = config_path or CONFIG_PATH
    if not os.path.exists(path):
        return {
            "security_tiers": {
                "open": "Safe to send to LLM",
                "local": "Agent reads privately",
                "locked": "Encrypted, requires passphrase",
            },
            "defaults": {
                "default_tier": "open",
            },
            "branch_security": {},
        }
    with open(path, "r") as f:
        return json.load(f)


def save_config(config: dict, config_path: str = None) -> None:
    """Save the security config file."""
    path = config_path or CONFIG_PATH
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def get_tier(branch_path: str, config: dict = None) -> str:
    """
    Get the security tier for a branch.

    Checks branch_security map in config. If not set, returns default_tier.
    Also checks parent branches — if 'company-1' is 'local',
    then 'company-1/finances' inherits 'local' unless overridden.

    Args:
        branch_path: e.g. "company-1/finances"
        config: loaded config dict (loads from file if None)

    Returns:
        "open", "local", or "locked"
    """
    if config is None:
        config = load_config()

    branch_security = config.get("branch_security", {})
    default_tier = config.get("defaults", {}).get("default_tier", "open")

    # Check exact match first
    if branch_path in branch_security:
        return branch_security[branch_path]

    # Walk up the path to check parent branches
    parts = branch_path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        parent = "/".join(parts[:i])
        if parent in branch_security:
            return branch_security[parent]

    return default_tier


def set_tier(branch_path: str, tier: str, config: dict = None,
             config_path: str = None) -> dict:
    """
    Set the security tier for a branch.

    Args:
        branch_path: e.g. "company-1"
        tier: "open", "local", or "locked"
        config: loaded config dict (loads from file if None)
        config_path: path to config file

    Returns:
        Updated config dict

    Raises:
        ValueError: if tier is not valid
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")

    if config is None:
        config = load_config(config_path)

    config.setdefault("branch_security", {})[branch_path] = tier
    save_config(config, config_path)
    return config


def filter_for_llm(entries: List[Dict], config: dict = None) -> Tuple[List[Dict], List[Dict]]:
    """
    THE MAIN FILTER — splits entries into what the LLM sees vs what stays private.

    Args:
        entries: list of memory entries, each with at least:
                 {"id", "branch", "content", ...}
        config: loaded config dict

    Returns:
        (llm_context, local_context)

        llm_context:  entries the LLM can see (🟢 Open only)
        local_context: entries the agent reads privately (🟢 Open + 🔒 Local)

        🔴 Locked entries are excluded from BOTH unless unlocked this session.

    Each returned entry has '_tier' added to it so the agent knows the tier.
    """
    if config is None:
        config = load_config()

    llm_context = []
    local_context = []

    for entry in entries:
        branch = entry.get("branch", "")
        tier = get_tier(branch, config)
        entry_with_tier = {**entry, "_tier": tier}

        if tier == "open":
            llm_context.append(entry_with_tier)
            local_context.append(entry_with_tier)
        elif tier == "local":
            # Agent reads it, LLM doesn't
            local_context.append(entry_with_tier)
        elif tier == "locked":
            # Check if unlocked this session
            if entry.get("_unlocked"):
                local_context.append(entry_with_tier)
            # Otherwise: blocked entirely
            # (blocked_count is calculated by the caller)

    return llm_context, local_context


def count_blocked(entries: List[Dict], config: dict = None) -> int:
    """Count how many entries are blocked (locked and not unlocked)."""
    if config is None:
        config = load_config()

    count = 0
    for entry in entries:
        branch = entry.get("branch", "")
        tier = get_tier(branch, config)
        if tier == "locked" and not entry.get("_unlocked"):
            count += 1
    return count


def is_safe_for_llm(entry: Dict, config: dict = None) -> bool:
    """Check if a single entry is safe to send to the LLM."""
    if config is None:
        config = load_config()
    tier = get_tier(entry.get("branch", ""), config)
    return tier == "open"
