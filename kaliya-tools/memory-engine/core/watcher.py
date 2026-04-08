"""Real-time file watcher using watchfiles (fsevents on macOS)."""

import os
import sys
import threading
import logging
from watchfiles import watch, Change

logger = logging.getLogger("memory-engine.watcher")


class MemoryWatcher:
    """Watches memory directories for .md changes and auto-reindexes."""

    def __init__(self, indexer, config: dict):
        self.indexer = indexer
        self.config = config
        self._thread = None
        self._stop_event = threading.Event()
        self._watch_paths = self._resolve_watch_paths()

    def _resolve_watch_paths(self) -> list[str]:
        """Get all project memory dirs to watch."""
        base = os.path.expanduser(
            self.config.get("memory_paths", {}).get("base", "~/.claude/projects")
        )
        paths = []
        if os.path.isdir(base):
            for name in os.listdir(base):
                mem_dir = os.path.join(base, name, "memory")
                if os.path.isdir(mem_dir):
                    paths.append(mem_dir)
        return paths

    def _derive_project(self, file_path: str) -> str:
        """Extract project ID from file path."""
        base = os.path.expanduser(
            self.config.get("memory_paths", {}).get("base", "~/.claude/projects")
        )
        try:
            rel = os.path.relpath(file_path, base)
            parts = rel.split(os.sep)
            return parts[0] if len(parts) > 1 else ""
        except ValueError:
            return ""

    def _watch_loop(self):
        """Main watch loop — runs in daemon thread."""
        if not self._watch_paths:
            logger.info("No memory directories to watch")
            return

        logger.info(f"Watching {len(self._watch_paths)} memory directories")
        try:
            for changes in watch(
                *self._watch_paths,
                stop_event=self._stop_event,
                watch_filter=lambda change, path: path.endswith(".md"),
                rust_timeout=5000,
            ):
                for change_type, path in changes:
                    project = self._derive_project(path)
                    if change_type in (Change.added, Change.modified):
                        try:
                            self.indexer.index_file(path, project=project)
                            logger.info(f"Re-indexed: {path}")
                        except Exception as e:
                            logger.warning(f"Index failed for {path}: {e}")
                    elif change_type == Change.deleted:
                        try:
                            self.indexer.db.delete_chunks_by_file(str(path))
                            logger.info(f"Deleted chunks for removed file: {path}")
                        except Exception as e:
                            logger.warning(f"Delete failed for {path}: {e}")
        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"Watcher stopped unexpectedly: {e}")

    def start(self):
        """Start watching in background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="memory-watcher"
        )
        self._thread.start()
        logger.info("File watcher started")

    def stop(self):
        """Signal watcher to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if watcher thread is alive."""
        return self._thread is not None and self._thread.is_alive()
