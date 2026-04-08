"""Daily log manager — timestamped entries, archival, retrieval."""

import os
import re
import shutil
from datetime import datetime, timedelta, timezone


VALID_CATEGORIES = {"task", "decision", "learning", "error", "note"}


class DailyLogManager:
    def __init__(self, config: dict):
        daily_cfg = config.get("daily_logs", {})
        self.archive_after_days = daily_cfg.get("archive_after_days", 30)
        self.load_days = daily_cfg.get("load_days_at_start", 2)
        compression_cfg = config.get("compression", {})
        self.compression_enabled = compression_cfg.get("enabled", True)
        self.auto_compress_after_days = compression_cfg.get("auto_compress_after_days", 14)
        self.deduplicate = compression_cfg.get("deduplicate", True)

    def get_daily_dir(self, project_memory_dir: str) -> str:
        """Return daily log directory, creating if needed."""
        daily_dir = os.path.join(os.path.expanduser(project_memory_dir), "daily")
        os.makedirs(daily_dir, exist_ok=True)
        return daily_dir

    def get_today_file(self, project_memory_dir: str) -> str:
        """Return path to today's daily log, creating with header if needed."""
        daily_dir = self.get_daily_dir(project_memory_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        file_path = os.path.join(daily_dir, f"{today}.md")

        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {today} — Daily Log\n\n")

        return file_path

    def append(self, project_memory_dir: str, content: str,
               category: str = "note") -> dict:
        """Add timestamped entry under category section in today's log."""
        if category not in VALID_CATEGORIES:
            category = "note"

        file_path = self.get_today_file(project_memory_dir)
        now = datetime.now(timezone.utc).strftime("%H:%M")
        section_header = f"## {category.capitalize()}"
        entry_line = f"- [{now}] {content}"

        # Read current content
        with open(file_path, "r", encoding="utf-8") as f:
            existing = f.read()

        # Find or create section
        if section_header in existing:
            # Insert under existing section header
            lines = existing.split("\n")
            insert_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == section_header:
                    # Find end of this section (next ## or EOF)
                    insert_idx = i + 1
                    while insert_idx < len(lines):
                        if lines[insert_idx].startswith("## ") and lines[insert_idx].strip() != section_header:
                            break
                        insert_idx += 1
                    # Back up past empty lines to insert right before next section
                    while insert_idx > i + 1 and not lines[insert_idx - 1].strip():
                        insert_idx -= 1
                    break

            if insert_idx >= 0:
                lines.insert(insert_idx, entry_line)
                new_content = "\n".join(lines)
            else:
                new_content = existing.rstrip() + f"\n\n{section_header}\n{entry_line}\n"
        else:
            new_content = existing.rstrip() + f"\n\n{section_header}\n{entry_line}\n"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Count entries in file
        entry_count = len(re.findall(r"^- \[", new_content, re.MULTILINE))

        return {
            "success": True,
            "file_path": file_path,
            "entry_number": entry_count,
        }

    def get_recent_logs(self, project_memory_dir: str, days: int = 0) -> list[dict]:
        """Return content of recent daily logs (today + N-1 previous days)."""
        if days <= 0:
            days = self.load_days

        daily_dir = self.get_daily_dir(project_memory_dir)
        results = []
        today = datetime.now(timezone.utc).date()

        for i in range(days):
            target_date = today - timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            file_path = os.path.join(daily_dir, f"{date_str}.md")

            if os.path.isfile(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                results.append({
                    "date": date_str,
                    "file_path": file_path,
                    "content": content,
                })

        return results

    def archive_old(self, project_memory_dir: str, max_age_days: int = 0):
        """Move daily logs older than max_age_days to archive subdirectory."""
        if max_age_days <= 0:
            max_age_days = self.archive_after_days

        daily_dir = self.get_daily_dir(project_memory_dir)
        archive_dir = os.path.join(daily_dir, "archive")

        cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
        date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
        archived = 0

        for fname in os.listdir(daily_dir):
            match = date_pattern.match(fname)
            if not match:
                continue

            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue

            if file_date < cutoff:
                os.makedirs(archive_dir, exist_ok=True)
                src = os.path.join(daily_dir, fname)
                dst = os.path.join(archive_dir, fname)
                shutil.move(src, dst)
                archived += 1

        return {"archived": archived, "archive_dir": archive_dir}

    def should_auto_compress(self, project_memory_dir: str) -> bool:
        """Check if any daily logs are old enough to auto-compress."""
        if not self.compression_enabled:
            return False
        daily_dir = self.get_daily_dir(project_memory_dir)
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self.auto_compress_after_days)
        date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
        for fname in os.listdir(daily_dir):
            match = date_pattern.match(fname)
            if not match:
                continue
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < cutoff:
                return True
        return False

    def compress_week(self, project_memory_dir: str, week_start_date: str = "") -> dict:
        """Merge 7 daily files into a weekly summary.
        week_start_date: YYYY-MM-DD (Monday). Default: last complete week.
        Keeps originals in archive/, summary in weekly/."""
        if not self.compression_enabled:
            return {"success": False, "error": "Compression is disabled in config."}
        daily_dir = self.get_daily_dir(project_memory_dir)
        weekly_dir = os.path.join(daily_dir, "weekly")
        archive_dir = os.path.join(daily_dir, "archive")

        if not week_start_date:
            today = datetime.now(timezone.utc).date()
            # Last complete week: go back to most recent Monday, then another 7 days
            # This ensures the week Mon-Sun is fully in the past before compressing
            last_monday = today - timedelta(days=today.weekday() + 7)
            week_start_date = last_monday.strftime("%Y-%m-%d")

        try:
            start = datetime.strptime(week_start_date, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}

        entries_by_category = {}
        files_found = []

        for i in range(7):
            day = start + timedelta(days=i)
            date_str = day.strftime("%Y-%m-%d")
            fname = f"{date_str}.md"

            # Check daily dir first, then archive
            fpath = os.path.join(daily_dir, fname)
            arch_path = os.path.join(archive_dir, fname)
            source = fpath if os.path.isfile(fpath) else arch_path if os.path.isfile(arch_path) else None

            if not source:
                continue
            files_found.append(source)
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
            self._parse_into_categories(content, entries_by_category)

        if not files_found:
            return {"success": False, "error": f"No daily files found for week starting {week_start_date}"}

        end_date = (start + timedelta(days=6)).strftime("%Y-%m-%d")
        os.makedirs(weekly_dir, exist_ok=True)
        weekly_file = os.path.join(weekly_dir, f"{week_start_date}_to_{end_date}.md")

        with open(weekly_file, "w", encoding="utf-8") as f:
            f.write(f"# Weekly Summary: {week_start_date} to {end_date}\n\n")
            for cat in ["task", "decision", "learning", "error", "note"]:
                entries = entries_by_category.get(cat, [])
                if not entries:
                    continue
                unique = self._deduplicate_entries(entries) if self.deduplicate else entries
                f.write(f"## {cat.capitalize()}\n")
                for entry in unique:
                    f.write(f"- {entry}\n")
                f.write("\n")

        # Move originals to archive
        os.makedirs(archive_dir, exist_ok=True)
        moved = 0
        for fpath in files_found:
            if os.path.dirname(os.path.abspath(fpath)) != os.path.abspath(archive_dir):
                dst = os.path.join(archive_dir, os.path.basename(fpath))
                shutil.move(fpath, dst)
                moved += 1

        return {
            "success": True,
            "weekly_file": weekly_file,
            "files_merged": len(files_found),
            "files_archived": moved,
        }

    def _parse_into_categories(self, content: str, categories: dict):
        """Parse daily log content into category buckets."""
        current_cat = "note"
        for line in content.split("\n"):
            stripped = line.strip()
            # Section headers
            if stripped.startswith("## "):
                section_name = stripped[3:].strip().lower()
                if section_name in VALID_CATEGORIES:
                    current_cat = section_name
                continue
            # Skip title lines and empty
            if stripped.startswith("# ") or not stripped:
                continue
            # Entry lines
            if stripped.startswith("- "):
                entry = stripped[2:].strip()
                if entry:
                    categories.setdefault(current_cat, []).append(entry)

    def _deduplicate_entries(self, entries: list[str]) -> list[str]:
        """Remove duplicate/near-duplicate entries. Keeps first occurrence."""
        unique = []
        seen_normalized = set()
        for entry in entries:
            # Strip timestamps for comparison
            normalized = re.sub(r'^\[\d{2}:\d{2}\]\s*', '', entry).lower().strip()
            # Skip exact duplicates
            if normalized in seen_normalized:
                continue
            # Skip if a very similar entry exists (substring match)
            is_dup = False
            for seen in seen_normalized:
                if len(normalized) > 20 and len(seen) > 20:
                    if normalized in seen or seen in normalized:
                        is_dup = True
                        break
            if not is_dup:
                seen_normalized.add(normalized)
                unique.append(entry)
        return unique
