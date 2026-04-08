"""Auto-recall engine for session-start context injection."""

import os
import re
from datetime import datetime, timezone

from .search import SearchEngine
from .daily import DailyLogManager

# Frustration markers — gaali/abuse words that signal quality failure
FRUSTRATION_MARKERS = re.compile(
    r'\b(bsdk|madarchod|gandu|chutiya|behenchod|mc|bc|sala|bakchod|gadh[ae]'
    r'|nalayak|bewakoof|harami|kamine|tatti|ghatiya|bakwas|faltu|bekar'
    r'|worst|pathetic|useless|garbage|trash|horrible|terrible|wtf|fuck)\b',
    re.IGNORECASE
)


def detect_frustration(text: str) -> bool:
    """Detect if user message contains frustration signals."""
    if not text:
        return False
    return bool(FRUSTRATION_MARKERS.search(text))


class RecallEngine:
    def __init__(self, search_engine: SearchEngine, daily_manager: DailyLogManager, config: dict):
        self.search = search_engine
        self.daily = daily_manager
        self.config = config
        self.default_budget = config.get("search", {}).get("max_result_chars", 4096)

    def _detect_project(self, project_dir: str) -> str:
        """Convert a project directory path to Claude's project identifier."""
        if not project_dir:
            return ""
        project_dir = os.path.abspath(os.path.expanduser(project_dir))
        return project_dir.replace("/", "-").replace("\\", "-")

    def _find_project_memory_dir(self, project_dir: str) -> str:
        """Find the memory directory for a project."""
        if not project_dir:
            return ""
        project_id = self._detect_project(project_dir)
        base = os.path.expanduser(self.config.get("memory_paths", {}).get("base", "~/.claude/projects"))
        memory_dir = os.path.join(base, project_id, "memory")
        if os.path.isdir(memory_dir):
            return memory_dir
        return ""

    def recall(self, project_dir: str = None, budget_chars: int = 0,
               frustration_mode: bool = False) -> str:
        """Generate recall context for session injection.

        When frustration_mode=True, prioritizes past mistakes and learnings
        over general context — because Malik is frustrated, meaning quality
        was bad, and past learnings need to be front-and-center.
        """
        if budget_chars <= 0:
            budget_chars = self.default_budget

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        parts = []
        used = 0

        parts.append(f"[MEMORY RECALL — {today}]")
        used += len(parts[-1]) + 2

        if frustration_mode:
            # FRUSTRATION MODE: learnings FIRST, bigger budget
            parts.append("\n## ALERT: Past Mistakes & Learnings (PRIORITY)")
            used += 50

            learnings_budget = int(budget_chars * 0.6)
            learnings = self._get_learnings(learnings_budget)
            if learnings:
                parts.append(learnings)
                used += len(learnings)

            # Then daily logs (smaller budget)
            memory_dir = self._find_project_memory_dir(project_dir)
            remaining = budget_chars - used
            if memory_dir and remaining > 200:
                daily_content = self._get_daily_content(memory_dir, int(remaining * 0.5))
                if daily_content:
                    parts.append("\n## Recent Activity")
                    parts.append(daily_content)
                    used += len(daily_content) + 20

            # Then quality rules search
            remaining = budget_chars - used
            if remaining > 200:
                quality_results = self.search.search(
                    query="quality verification protocol mistake avoid",
                    scope="all", top_k=3
                )
                if quality_results:
                    parts.append("\n## Quality Rules (Review Before Acting)")
                    for r in quality_results[:2]:
                        snippet = r["content"].strip()
                        if len(snippet) <= remaining:
                            parts.append(f"- {snippet[:300]}")
                            remaining -= len(snippet[:300]) + 4
        else:
            # NORMAL MODE: daily logs first
            memory_dir = self._find_project_memory_dir(project_dir)
            if memory_dir:
                daily_budget = int(budget_chars * 0.4)
                daily_content = self._get_daily_content(memory_dir, daily_budget)
                if daily_content:
                    parts.append("\n## Recent Activity")
                    parts.append(daily_content)
                    used += len(daily_content) + 20

            # Project-relevant context via search
            remaining = budget_chars - used
            if remaining > 200:
                context_budget = int(remaining * 0.6)
                project_id = self._detect_project(project_dir) if project_dir else None
                context_content = self._get_context(project_id, context_budget)
                if context_content:
                    parts.append("\n## Relevant Context")
                    parts.append(context_content)
                    used += len(context_content) + 22

            # Recent learnings
            remaining = budget_chars - used
            if remaining > 200:
                learnings = self._get_learnings(remaining)
                if learnings:
                    parts.append("\n## Recent Learnings")
                    parts.append(learnings)

        return "\n".join(parts)

    def log_frustration_event(self, project_dir: str, user_message: str,
                              task_context: str = "") -> dict:
        """Log a frustration event to daily log when gaali detected.

        Called by MCP server when frustration markers found in user message.
        Saves: what Malik said, what was being worked on, timestamp.
        """
        memory_dir = self._find_project_memory_dir(project_dir)
        if not memory_dir:
            global_mem = os.path.expanduser(
                self.config.get("memory_paths", {}).get("global", "~/.claude/projects/-Users-niwash/memory")
            )
            if os.path.isdir(global_mem):
                memory_dir = global_mem
            else:
                return {"success": False, "error": "No memory directory"}

        # Sanitize — store the signal, not the exact words
        content = f"FRUSTRATION DETECTED — Quality failure. "
        if task_context:
            content += f"Task: {task_context}. "
        content += "Action: Re-read original request, check quality.md rules, fix with 2x quality."

        return self.daily.append(memory_dir, content, category="error")

    def _get_daily_content(self, memory_dir: str, budget: int) -> str:
        """Get recent daily log content within budget."""
        logs = self.daily.get_recent_logs(memory_dir)
        if not logs:
            return ""

        content_parts = []
        remaining = budget

        for log in logs:
            log_content = log["content"].strip()
            if not log_content:
                continue

            # Trim to fit budget
            if len(log_content) > remaining:
                log_content = log_content[:remaining] + "..."

            content_parts.append(f"### {log['date']}")
            content_parts.append(log_content)
            remaining -= len(log_content) + len(log["date"]) + 10

            if remaining <= 50:
                break

        return "\n".join(content_parts)

    def _get_context(self, project_id: str, budget: int) -> str:
        """Search memory for project-relevant context."""
        # Build a generic context query
        queries = ["recent tasks and decisions", "current project state"]
        results_all = []
        seen = set()

        for q in queries:
            results = self.search.search(
                query=q,
                scope="project" if project_id else "all",
                top_k=4,
                project=project_id,
            )
            for r in results:
                key = (r.get("source_file", ""), r.get("start_line", 0))
                if key not in seen:
                    seen.add(key)
                    results_all.append(r)

        if not results_all:
            return ""

        content_parts = []
        remaining = budget

        for r in results_all:
            snippet = r["content"].strip()
            source = os.path.basename(r["source_file"])
            section = r.get("section", "")

            header = f"*{source}"
            if section:
                header += f" > {section}"
            header += "*"

            entry = f"{header}\n{snippet}"
            if len(entry) > remaining:
                break

            content_parts.append(entry)
            remaining -= len(entry) + 2

            if remaining <= 50:
                break

        return "\n\n".join(content_parts)

    def _get_learnings(self, budget: int) -> str:
        """Get recent entries from mistakes-learnings files."""
        results = self.search.search(
            query="mistake learning error fix gotcha",
            scope="all",
            top_k=3,
        )

        # Filter for learning-related files
        learning_results = [
            r for r in results
            if any(kw in r["source_file"].lower() for kw in ["mistake", "learning", "error"])
        ]
        if not learning_results:
            learning_results = results[:2]

        if not learning_results:
            return ""

        content_parts = []
        remaining = budget

        for r in learning_results:
            snippet = r["content"].strip()
            if len(snippet) > remaining:
                snippet = snippet[:remaining] + "..."

            content_parts.append(f"- {snippet}")
            remaining -= len(snippet) + 4

            if remaining <= 50:
                break

        return "\n".join(content_parts)

    def flush(self, project_dir: str, session_id: str, state: dict) -> dict:
        """Flush machine state to daily log (called by pre-compact hook)."""
        memory_dir = self._find_project_memory_dir(project_dir)
        if not memory_dir:
            # Use global memory as fallback
            global_mem = os.path.expanduser(
                self.config.get("memory_paths", {}).get("global", "~/.claude/projects/-Users-niwash/memory")
            )
            if os.path.isdir(global_mem):
                memory_dir = global_mem
            else:
                return {"success": False, "file_path": "", "error": "No memory directory found"}

        # Match keys from pre-compact-save.sh state.json format
        task = state.get("task", state.get("last_session_snapshot", "unknown"))
        files = state.get("files_modified", state.get("recently_modified_files", []))
        branch = state.get("branch", state.get("git_branch", "unknown"))
        cwd = state.get("cwd", "unknown")

        files_str = ", ".join(files[:10]) if files else "none"
        content = f"Session {session_id} compact — CWD: {cwd}, Files: {files_str}, Branch: {branch}"

        result = self.daily.append(memory_dir, content, category="task")
        return result
