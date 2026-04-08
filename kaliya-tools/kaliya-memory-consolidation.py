#!/usr/bin/env python3
"""
KALIYA Memory Consolidation — Episodic → Semantic/Procedural
Scans daily logs for REPEATED learnings and auto-promotes them to permanent memory.

Like human brain's "dreaming" — consolidates what was learned into long-term memory.

Usage:
    python3 kaliya-memory-consolidation.py [--dry-run] [--stats] [--force]

Runs automatically from session-start every 72 hours.
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# Paths
HOME = Path.home()
GLOBAL_MEMORY = HOME / ".claude" / "projects" / "-Users-niwash" / "memory"
PROCEDURES_DIR = GLOBAL_MEMORY / "procedures"
PREFERENCES_FILE = GLOBAL_MEMORY / "malik-preferences.md"
AUTO_CAPTURED = PROCEDURES_DIR / "auto-captured.md"
STATE_FILE = Path("/tmp/kaliya-consolidation-state.json")

# All project memory directories
PROJECT_MEMORY_BASE = HOME / ".claude" / "projects"

# Consolidation thresholds
MIN_REPETITIONS = 2  # Mentioned 2+ times across sessions → promote
MIN_DAYS_SPAN = 2    # Must span at least 2 different days
MAX_AGE_DAYS = 30    # Only scan last 30 days of daily logs


def load_state():
    """Load last consolidation timestamp."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {"last_run": 0, "promoted": []}


def save_state(state):
    """Save consolidation state."""
    state["last_run"] = time.time()
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def find_daily_logs():
    """Find all daily log files across all projects."""
    daily_files = []
    if not PROJECT_MEMORY_BASE.exists():
        return daily_files

    for proj_dir in PROJECT_MEMORY_BASE.iterdir():
        if not proj_dir.is_dir():
            continue
        daily_dir = proj_dir / "memory" / "daily"
        if not daily_dir.exists():
            continue

        for f in daily_dir.iterdir():
            if f.suffix == '.md' and re.match(r'\d{4}-\d{2}-\d{2}', f.stem):
                # Check age
                try:
                    file_date = datetime.strptime(f.stem, "%Y-%m-%d")
                    age_days = (datetime.now() - file_date).days
                    if age_days <= MAX_AGE_DAYS:
                        daily_files.append({
                            "path": f,
                            "date": f.stem,
                            "project": proj_dir.name,
                            "age_days": age_days,
                        })
                except ValueError:
                    continue

    return sorted(daily_files, key=lambda x: x["date"], reverse=True)


def extract_learnings(daily_files):
    """Extract key learnings from daily logs."""
    learnings = []

    for df in daily_files:
        try:
            content = df["path"].read_text(encoding='utf-8')
        except Exception:
            continue

        # Extract lines that look like learnings/rules/procedures
        for line in content.split('\n'):
            line = line.strip()
            if len(line) < 20:
                continue

            # Match patterns that indicate a learning
            is_learning = False

            # "- [ALWAYS]" or "- [NEVER]" patterns
            if re.match(r'^-\s*\[(ALWAYS|NEVER|PROCEDURE|LEARNING)\]', line):
                is_learning = True

            # "MUST" / "NEVER" / "ALWAYS" / "MANDATORY" in the line
            if re.search(r'\b(MUST|NEVER|ALWAYS|MANDATORY|CRITICAL|IMPORTANT)\b', line) and line.startswith('-'):
                is_learning = True

            # "karo" / "mat karo" / "chahiye" patterns
            if re.search(r'\b(hamesha|kabhi nahi|zaroori|chahiye|mandatory)\b', line.lower()):
                is_learning = True

            if is_learning:
                learnings.append({
                    "text": line[:200],
                    "date": df["date"],
                    "project": df["project"],
                    "source": str(df["path"]),
                })

    return learnings


def find_repeated_learnings(learnings):
    """Find learnings that appear multiple times (same concept, different days)."""
    # Group by normalized text (lowercase, stripped)
    groups = defaultdict(list)

    for l in learnings:
        # Normalize: lowercase, remove timestamps, trim
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '', l["text"].lower())
        normalized = re.sub(r'\(\d{2}:\d{2}\)', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Use first 80 chars as key (catches similar but not identical)
        key = normalized[:80]
        groups[key].append(l)

    # Filter: must appear on 2+ different days
    repeated = []
    for key, items in groups.items():
        unique_days = set(i["date"] for i in items)
        if len(unique_days) >= MIN_REPETITIONS:
            repeated.append({
                "key": key,
                "count": len(items),
                "days": sorted(unique_days),
                "example": items[0]["text"],
                "projects": list(set(i["project"] for i in items)),
            })

    return sorted(repeated, key=lambda x: x["count"], reverse=True)


def promote_to_permanent(repeated, state, dry_run=False):
    """Promote repeated learnings to permanent memory."""
    promoted_keys = set(state.get("promoted", []))
    new_promotions = []

    for r in repeated:
        if r["key"] in promoted_keys:
            continue  # Already promoted

        if dry_run:
            print(f"  [DRY RUN] Would promote ({r['count']}x, {len(r['days'])} days): {r['example'][:100]}")
            new_promotions.append(r["key"])
            continue

        # Determine where to save
        text = r["example"]

        # Save to auto-captured procedures
        try:
            timestamp = time.strftime("%Y-%m-%d")
            entry = f"- [CONSOLIDATED {r['count']}x] ({timestamp}) {text}\n"

            if not AUTO_CAPTURED.exists():
                AUTO_CAPTURED.write_text("# Auto-Captured Procedures\n\n> Auto-captured and consolidated from repeated learnings.\n\n")

            # Check for duplicates
            existing = AUTO_CAPTURED.read_text(encoding='utf-8')
            if text[:50] not in existing:
                with open(AUTO_CAPTURED, 'a', encoding='utf-8') as f:
                    f.write(entry)
                print(f"  [PROMOTED] ({r['count']}x across {len(r['days'])} days): {text[:100]}")
                new_promotions.append(r["key"])
        except Exception as e:
            print(f"  [ERROR] Failed to promote: {e}")

    return new_promotions


def show_stats(daily_files, learnings, repeated):
    """Show consolidation statistics."""
    print(f"\n  Memory Consolidation Stats")
    print(f"  {'=' * 40}")
    print(f"  Daily logs scanned:    {len(daily_files)}")
    print(f"  Learnings extracted:   {len(learnings)}")
    print(f"  Repeated (2+ days):    {len(repeated)}")
    print(f"  Procedure files:       {len(list(PROCEDURES_DIR.glob('*.md'))) if PROCEDURES_DIR.exists() else 0}")

    if repeated:
        print(f"\n  Top Repeated Learnings:")
        for r in repeated[:10]:
            print(f"    [{r['count']}x] {r['example'][:80]}...")

    print()


def main():
    dry_run = "--dry-run" in sys.argv
    stats_only = "--stats" in sys.argv
    force = "--force" in sys.argv

    state = load_state()

    # Check if we need to run (every 72 hours unless forced)
    if not force and not stats_only:
        hours_since = (time.time() - state.get("last_run", 0)) / 3600
        if hours_since < 72:
            print(f"  Consolidation ran {hours_since:.0f}h ago (next in {72-hours_since:.0f}h). Use --force to override.")
            return

    # Step 1: Find daily logs
    daily_files = find_daily_logs()
    if not daily_files:
        print("  No daily logs found.")
        return

    # Step 2: Extract learnings
    learnings = extract_learnings(daily_files)

    # Step 3: Find repeated learnings
    repeated = find_repeated_learnings(learnings)

    if stats_only:
        show_stats(daily_files, learnings, repeated)
        return

    # Step 4: Promote to permanent
    print(f"\n  KALIYA Memory Consolidation")
    print(f"  {'=' * 40}")
    print(f"  Scanned: {len(daily_files)} daily logs, {len(learnings)} learnings found")
    print(f"  Repeated: {len(repeated)} learnings appeared on 2+ different days\n")

    new_promotions = promote_to_permanent(repeated, state, dry_run)

    if not dry_run:
        state["promoted"] = list(set(state.get("promoted", []) + new_promotions))
        save_state(state)

    if new_promotions:
        print(f"\n  {len(new_promotions)} learnings promoted to permanent memory.")
    else:
        print(f"\n  No new learnings to promote (all already captured or too recent).")


if __name__ == "__main__":
    main()
