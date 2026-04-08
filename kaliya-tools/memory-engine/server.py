"""FastMCP server for KALIYA Memory Engine — 5 tools for semantic memory."""

import json
import os
import sys
from datetime import datetime, timezone

from fastmcp import FastMCP

# --- Config Loading ---

CONFIG_PATH = os.environ.get(
    "MEMORY_ENGINE_CONFIG",
    os.path.expanduser("~/.claude/memory-engine/config.json"),
)

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except FileNotFoundError:
    print(f"FATAL: Config not found at {CONFIG_PATH}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"FATAL: Invalid JSON in {CONFIG_PATH}: {e}", file=sys.stderr)
    sys.exit(1)

# --- Lazy Globals ---

_db = None
_embedder = None
_indexer = None
_search_engine = None
_daily_manager = None
_recall_engine = None
_watcher = None


def _get_db():
    global _db
    if _db is None:
        from core.database import MemoryDB
        index_dir = os.path.expanduser(CONFIG.get("memory_paths", {}).get("index_dir", "~/.claude/memory-engine/index"))
        db_path = os.path.join(index_dir, "memory.db")
        _db = MemoryDB(db_path)
        _db.initialize()
        if CONFIG.get("vector_search", {}).get("use_sqlite_vec", False):
            # Dimension auto-detected from existing embeddings, or from embedder model
            embedder = _get_embedder()
            _db.initialize_vec_table(dimension=embedder.dimension)
    return _db


def _get_embedder():
    global _embedder
    if _embedder is None:
        from core.embeddings import EmbeddingModel
        emb_cfg = CONFIG.get("embedding", {})
        _embedder = EmbeddingModel(
            model_name=emb_cfg.get("model", "all-MiniLM-L6-v2"),
            model_dir=emb_cfg.get("model_path", ""),
            model_priority=emb_cfg.get("model_priority"),
            lazy_load=emb_cfg.get("lazy_load", True),
            auto_select=emb_cfg.get("auto_select", False),
        )
    return _embedder


def _get_indexer():
    global _indexer
    if _indexer is None:
        from core.indexer import MemoryIndexer
        _indexer = MemoryIndexer(_get_db(), _get_embedder(), CONFIG)
    return _indexer


def _get_search():
    global _search_engine
    if _search_engine is None:
        from core.search import SearchEngine
        _search_engine = SearchEngine(_get_db(), _get_embedder(), CONFIG)
    return _search_engine


def _get_daily():
    global _daily_manager
    if _daily_manager is None:
        from core.daily import DailyLogManager
        _daily_manager = DailyLogManager(CONFIG)
    return _daily_manager


def _get_recall():
    global _recall_engine
    if _recall_engine is None:
        from core.recall import RecallEngine
        _recall_engine = RecallEngine(_get_search(), _get_daily(), CONFIG)
    return _recall_engine


def _get_watcher():
    global _watcher
    if _watcher is None:
        if CONFIG.get("watcher", {}).get("enabled", False):
            from core.watcher import MemoryWatcher
            _watcher = MemoryWatcher(_get_indexer(), CONFIG)
            _watcher.start()
    return _watcher


def _detect_project_from_cwd() -> str:
    """Detect project identifier from CWD, matching Claude's format."""
    cwd = os.environ.get("PROJECT_DIR", os.getcwd())
    cwd = os.path.abspath(os.path.expanduser(cwd))  # Normalize
    return cwd.replace("/", "-").replace("\\", "-")


def _find_project_memory_dir() -> str:
    """Find memory directory for current project."""
    project_id = _detect_project_from_cwd()
    base = os.path.expanduser(CONFIG.get("memory_paths", {}).get("base", "~/.claude/projects"))
    memory_dir = os.path.join(base, project_id, "memory")
    if os.path.isdir(memory_dir):
        return memory_dir

    # Fallback to global memory
    global_mem = os.path.expanduser(CONFIG.get("memory_paths", {}).get("global", "~/.claude/projects/-Users-niwash/memory"))
    if os.path.isdir(global_mem):
        return global_mem
    return ""


# --- MCP Server ---

mcp = FastMCP("memory-engine")


@mcp.tool()
def memory_search(query: str, scope: str = "all", top_k: int = 8) -> str:
    """Search memory semantically. Finds relevant info even with different wording.
    scope: 'all', 'project', 'global'. Returns ranked results."""
    engine = _get_search()

    project = None
    if scope == "project":
        project = _detect_project_from_cwd()

    results = engine.search(query=query, scope=scope, top_k=top_k, project=project)

    if not results:
        return "No results found."

    output_parts = [f"Found {len(results)} results:\n"]
    for i, r in enumerate(results, 1):
        source = os.path.basename(r["source_file"])
        section = r.get("section", "")
        score = r.get("score", 0)
        evergreen = " [evergreen]" if r.get("is_evergreen") else ""
        age = r.get("age_days", 0)

        header = f"**{i}. {source}"
        if section:
            header += f" > {section}"
        header += f"** (score: {score:.3f}, age: {age}d{evergreen})"

        content = r["content"]
        if len(content) > 500:
            content = content[:500] + "..."

        output_parts.append(f"{header}\n{content}\n")

        # Show linked memories
        linked = r.get("linked", [])
        if linked:
            for lnk in linked:
                lnk_source = os.path.basename(lnk["source_file"])
                lnk_preview = lnk["content"][:150].replace("\n", " ")
                output_parts.append(f"  ↳ [{lnk['relationship']}] {lnk_source}: {lnk_preview}")

    # Mark STEP 0 as done
    try:
        open("/tmp/claude-step0-done", "w").close()
    except OSError:
        pass

    return "\n".join(output_parts)


@mcp.tool()
def memory_write(content: str, file: str = "", section: str = "") -> str:
    """Write to memory files. Default: today's daily log.
    Optionally specify file path and section header."""
    if file:
        memory_base = os.path.abspath(os.path.expanduser(
            CONFIG.get("memory_paths", {}).get("base", "~/.claude/projects")
        ))
        # Resolve relative paths against the memory base + active project memory dir
        if not os.path.isabs(file) and not file.startswith("~"):
            # Try to find the file in any project's memory/ subdir
            for proj in os.listdir(memory_base) if os.path.isdir(memory_base) else []:
                candidate = os.path.join(memory_base, proj, "memory", file)
                if os.path.isfile(candidate):
                    file = candidate
                    break
            else:
                # Default: put in first project's memory dir that has a memory/ subdir
                for proj in os.listdir(memory_base) if os.path.isdir(memory_base) else []:
                    mem_dir = os.path.join(memory_base, proj, "memory")
                    if os.path.isdir(mem_dir):
                        file = os.path.join(mem_dir, file)
                        break
        file_path = os.path.abspath(os.path.expanduser(file))
        # SECURITY: restrict writes to memory directories only
        allowed_bases = [
            memory_base,
            os.path.abspath(os.path.expanduser("~/.claude/memory-engine/")),
        ]
        real_path = os.path.realpath(file_path)
        allowed = False
        for b in allowed_bases:
            real_base = os.path.realpath(b)
            if real_path.startswith(real_base + os.sep) or real_path == real_base:
                allowed = True
                break
        if not allowed:
            return f"Error: write denied. Path must be under allowed memory directories."
        if os.path.isdir(file_path):
            return f"Error: path is a directory, not a file."
        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            return f"Error: directory {dir_path} does not exist."

        if os.path.isfile(file_path) and section:
            # Insert under section in existing file
            with open(file_path, "r", encoding="utf-8") as f:
                existing = f.read()

            section_header = f"## {section}" if not section.startswith("#") else section

            if section_header in existing:
                lines = existing.split("\n")
                insert_idx = -1
                for i, line in enumerate(lines):
                    if line.strip() == section_header:
                        insert_idx = i + 1
                        while insert_idx < len(lines):
                            if lines[insert_idx].startswith("## ") and lines[insert_idx].strip() != section_header:
                                break
                            insert_idx += 1
                        while insert_idx > i + 1 and not lines[insert_idx - 1].strip():
                            insert_idx -= 1
                        break

                if insert_idx >= 0:
                    lines.insert(insert_idx, content)
                    new_content = "\n".join(lines)
                else:
                    new_content = existing.rstrip() + f"\n\n{section_header}\n{content}\n"
            else:
                new_content = existing.rstrip() + f"\n\n{section_header}\n{content}\n"

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        elif os.path.isfile(file_path):
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"\n{content}\n")
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                if section:
                    section_header = f"## {section}" if not section.startswith("#") else section
                    f.write(f"{section_header}\n{content}\n")
                else:
                    f.write(f"{content}\n")

        # Re-index the file
        try:
            _get_indexer().index_file(file_path, project=_detect_project_from_cwd())
        except Exception as e:
            print(f"WARNING: indexing failed for {file_path}: {e}", file=sys.stderr)
            return f"File written but indexing FAILED: {e}. Content saved to disk but not searchable."

        return f"Written to {file_path}"

    # Default: write to today's daily log
    memory_dir = _find_project_memory_dir()
    if not memory_dir:
        return "Error: no memory directory found for current project."

    daily = _get_daily()
    result = daily.append(memory_dir, content, category="note")

    # Re-index
    try:
        _get_indexer().index_file(result["file_path"], project=_detect_project_from_cwd())
    except Exception as e:
        print(f"Warning: indexing failed for {result['file_path']}: {e}", file=sys.stderr)

    return f"Written to daily log: {result['file_path']} (entry #{result['entry_number']})"


@mcp.tool()
def memory_daily(content: str, category: str = "note") -> str:
    """Add timestamped entry to today's daily log.
    Categories: task, decision, learning, error, note."""
    memory_dir = _find_project_memory_dir()
    if not memory_dir:
        return "Error: no memory directory found for current project."

    daily = _get_daily()
    result = daily.append(memory_dir, content, category=category)

    if result["success"]:
        # Re-index
        try:
            _get_indexer().index_file(result["file_path"], project=_detect_project_from_cwd())
        except Exception as e:
            print(f"WARNING: indexing failed for {result['file_path']}: {e}", file=sys.stderr)
            return f"[{category.upper()}] logged but indexing FAILED: {e}. Entry saved to disk but not searchable."
        return f"[{category.upper()}] logged to {result['file_path']} (entry #{result['entry_number']})"

    return f"Error writing daily log: {result}"


@mcp.tool()
def memory_recall(frustration_mode: bool = False) -> str:
    """Get relevant memories for current context.
    Used automatically at session start. Budget-limited to 4KB.

    Set frustration_mode=True when user is frustrated (gaali/abuse detected).
    This prioritizes past mistakes and quality rules over general context."""
    recall = _get_recall()
    project_dir = os.environ.get("PROJECT_DIR", os.getcwd())
    return recall.recall(project_dir=project_dir, budget_chars=4096,
                         frustration_mode=frustration_mode)


@mcp.tool()
def memory_status() -> str:
    """Check memory system health — index stats, freshness, daily log count."""
    db = _get_db()
    stats = db.get_stats()

    memory_dir = _find_project_memory_dir()
    daily_count = 0
    if memory_dir:
        daily_dir = os.path.join(memory_dir, "daily")
        if os.path.isdir(daily_dir):
            daily_count = len([f for f in os.listdir(daily_dir) if f.endswith(".md")])

    embedder = _get_embedder()
    model_status = "available" if embedder.is_available else "not installed (BM25 only)"

    watcher = _get_watcher()
    watcher_status = "running" if (watcher and watcher.is_running) else "disabled"

    output = [
        "Memory Engine Status",
        "=" * 40,
        f"Indexed chunks:     {stats['total_chunks']}",
        f"Embeddings:         {stats['total_embeddings']}",
        f"Indexed files:      {stats['indexed_files']}",
        f"Session summaries:  {stats['total_sessions']}",
        f"Daily log files:    {daily_count}",
        f"Embedding model:    {model_status}",
        f"File watcher:       {watcher_status}",
        f"Project memory:     {memory_dir or 'not found'}",
    ]
    return "\n".join(output)


@mcp.tool()
def memory_frustration_check(user_message: str, task_context: str = "") -> str:
    """Detect frustration in user message and log it.

    Call this when processing a user message to check for frustration signals.
    If frustrated: logs the event, returns frustration_mode=True + past mistakes.
    If not frustrated: returns frustration_mode=False (no action needed).

    The response tells you whether to activate heightened-quality mode."""
    from core.recall import detect_frustration

    is_frustrated = detect_frustration(user_message)

    if not is_frustrated:
        return '{"frustrated": false, "action": "none"}'

    # Log the frustration event
    recall = _get_recall()
    project_dir = os.environ.get("PROJECT_DIR", os.getcwd())
    recall.log_frustration_event(project_dir, user_message, task_context)

    # Get boosted recall with mistakes prioritized
    boosted_recall = recall.recall(project_dir=project_dir, budget_chars=2048,
                                   frustration_mode=True)

    return (
        '{"frustrated": true, "action": "heightened_quality"}\n\n'
        "FRUSTRATION DETECTED — quality gear shift. DON'T STOP running work.\n"
        "1. Acknowledge briefly: 'Noted. Fixing.' (1 line)\n"
        "2. Running agents CONTINUE — don't halt them\n"
        "3. Silently re-read original request — check what's missing\n"
        "4. Course-correct current work — upgrade quality, zero assumptions\n"
        "5. All subsequent work = 2x verification\n\n"
        f"{boosted_recall}"
    )


@mcp.tool()
def memory_mark_important(query: str, importance: float = 5.0) -> str:
    """Mark memory chunks matching query as critical (importance 1.0-10.0).
    Critical chunks (>=5.0) are exempt from temporal decay and score higher in search."""
    if importance < 0.1 or importance > 10.0:
        return "Error: importance must be between 0.1 and 10.0"

    db = _get_db()
    chunks = db.search_chunks_by_content(query, limit=5)
    if not chunks:
        return f"No chunks found matching '{query}'"

    chunk_ids = [c["id"] for c in chunks]
    db.mark_important(chunk_ids, importance)

    results = []
    for c in chunks:
        source = os.path.basename(c["file_path"])
        preview = c["content"][:100].replace("\n", " ")
        results.append(f"  - [{c['id']}] {source}: {preview}...")

    return f"Marked {len(chunk_ids)} chunks with importance={importance}:\n" + "\n".join(results)


@mcp.tool()
def memory_link(source_query: str, target_query: str,
                relationship: str = "related") -> str:
    """Link two memories by content search. Creates a cross-reference.
    Relationships: 'related', 'depends_on', 'supersedes', 'contradicts'."""
    valid_rels = {"related", "depends_on", "supersedes", "contradicts"}
    if relationship not in valid_rels:
        return f"Error: relationship must be one of {valid_rels}"

    db = _get_db()
    source_chunks = db.search_chunks_by_content(source_query, limit=1)
    target_chunks = db.search_chunks_by_content(target_query, limit=1)

    if not source_chunks:
        return f"No source chunk found matching '{source_query}'"
    if not target_chunks:
        return f"No target chunk found matching '{target_query}'"

    source = source_chunks[0]
    target = target_chunks[0]
    db.add_cross_reference(source["id"], target["id"], relationship)

    src_preview = source["content"][:80].replace("\n", " ")
    tgt_preview = target["content"][:80].replace("\n", " ")
    return (
        f"Linked: [{source['id']}] {os.path.basename(source['file_path'])}: {src_preview}...\n"
        f"  --({relationship})--> [{target['id']}] {os.path.basename(target['file_path'])}: {tgt_preview}..."
    )


@mcp.tool()
async def memory_cleanup() -> str:
    """Remove orphan chunks from deleted files and return cleanup stats."""
    db = _get_db()
    removed = db.cleanup_orphan_chunks()
    total = db.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return f"Cleanup complete. Removed chunks from {removed} deleted files. {total} chunks remaining."


if __name__ == "__main__":
    # Start file watcher if enabled
    if CONFIG.get("watcher", {}).get("enabled", False):
        try:
            _get_watcher()
        except Exception:
            pass  # watcher is optional, don't block server startup
    mcp.run(transport="stdio")
