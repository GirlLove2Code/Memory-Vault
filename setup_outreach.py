#!/usr/bin/env python3
"""
Setup outreach branches for a YouTube comment outreach workflow.
Template script — customize CLIENTS list with your own client names.

Run once:
    python setup_outreach.py

Creates branches for each client product with proper structure for
storing video research, comment performance, creator profiles, and
learning what works.
"""

import os
import sys

# Add parent dir to path if running standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from branch_manager import create_branch, list_branches, load_master_index
from entry_manager import add_memory

# Replace with your actual client names
CLIENTS = ["client-a", "client-b", "client-c"]

BRANCHES = {
    # Per-client branches
    "outreach/{client}/videos": "YouTube videos researched for {client}. Stores video URL, title, channel, view count, relevance notes, and date found. Prevents duplicate suggestions.",
    "outreach/{client}/comments": "Comment performance data for {client}. Tracks which comments were posted, engagement (likes, replies), what angles worked, and lessons learned.",
    "outreach/{client}/creators": "YouTube creator/channel profiles relevant to {client}. Stores channel name, subscriber count, content focus, audience overlap, posting frequency, and best time to engage.",
    "outreach/{client}/talking-points": "Product talking points and messaging for {client}. Key features, differentiators, community angles, and approved language. Updated by E.",

    # Shared branches (not per-client)
    "outreach/strategy": "Outreach strategy and patterns that work across all clients. Best comment angles, optimal video characteristics, timing insights, and general lessons.",
    "outreach/blacklist": "Videos and channels to avoid. Includes competitor channels, controversial creators, and any that E has flagged as off-limits.",
}


def setup():
    print("Setting up outreach branches...\n")

    created = 0
    skipped = 0

    for template, summary_template in BRANCHES.items():
        if "{client}" in template:
            for client in CLIENTS:
                branch = template.replace("{client}", client)
                summary = summary_template.replace("{client}", client)
                try:
                    create_branch(branch, summary=summary)
                    print(f"  + {branch}")
                    created += 1
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  ~ {branch} (already exists)")
                        skipped += 1
                    else:
                        print(f"  ! {branch} — ERROR: {e}")
        else:
            branch = template
            summary = summary_template
            try:
                create_branch(branch, summary=summary)
                print(f"  + {branch}")
                created += 1
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  ~ {branch} (already exists)")
                    skipped += 1
                else:
                    print(f"  ! {branch} — ERROR: {e}")

    print(f"\nDone! Created {created}, skipped {skipped} (already exist)")
    print(f"Total outreach branches: {created + skipped}")

    # Seed strategy branch with initial entry
    try:
        add_memory(
            branch="outreach/strategy",
            content="""## Outreach Comment Strategy — What Works

### Best Comment Angles (ranked by typical engagement):
1. **Community builder** — ask a question, invite discussion. Gets replies.
2. **Technical credibility** — share a specific insight. Gets likes from devs.
3. **Curiosity hook** — mention something interesting without hard selling. Gets profile visits.
4. **Product tie-in** — natural connection to video topic. Good for awareness.
5. **Thought leader** — position brand as expert. Good for credibility.

### Video Selection Criteria:
- 100K+ views preferred, but 50K+ with active comments works
- Recent (last 30 days) or evergreen content
- Active comment section (not just views — check if people are discussing)
- Creator has credibility in the niche
- Topic naturally connects to the product

### What NOT to Do:
- Don't post the same comment on multiple videos
- Don't include links (YouTube often filters them)
- Don't mention competitors negatively
- Don't sound like a brand account — sound like a person
- Don't post on videos with disabled or toxic comments
- Don't engage with controversial or political content

### Timing:
- Post within 24-48 hours of video upload for best visibility
- Evergreen videos: any time, but check if comments are still active
- Avoid posting multiple comments on same channel in one day""",
            importance=4,
            tags=["strategy", "playbook"],
            source="setup",
        )
        print("\nSeeded strategy branch with initial playbook.")
    except Exception:
        print("\nStrategy seed already exists or failed — that's OK.")


if __name__ == "__main__":
    setup()
