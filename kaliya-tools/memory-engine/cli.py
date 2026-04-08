#!/usr/bin/env python3
"""CLI interface for KALIYA Memory Engine — used by hooks and manual invocation."""

import argparse
import json
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_config() -> dict:
    config_path = os.environ.get(
        "MEMORY_ENGINE_CONFIG",
        os.path.expanduser("~/.claude/memory-engine/config.json"),
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)


def _get_db(config: dict):
    from core.database import MemoryDB
    index_dir = os.path.expanduser(config.get("memory_paths", {}).get("index_dir", "~/.claude/memory-engine/index"))
    db_path = os.path.join(index_dir, "memory.db")
    db = MemoryDB(db_path)
    db.initialize()
    # Initialize sqlite-vec if enabled in config
    if config.get("vector_search", {}).get("use_sqlite_vec", False):
        dim = config.get("embedding", {}).get("dimension", None)
        db.initialize_vec_table(dimension=dim)
    return db


def _get_embedder(config: dict):
    from core.embeddings import EmbeddingModel
    emb_cfg = config.get("embedding", {})
    return EmbeddingModel(
        model_name=emb_cfg.get("model", "all-MiniLM-L6-v2"),
        model_dir=emb_cfg.get("model_path", ""),
        model_priority=emb_cfg.get("model_priority"),
        lazy_load=emb_cfg.get("lazy_load", True),
        auto_select=emb_cfg.get("auto_select", False),
    )


def cmd_recall(args, config: dict):
    """Generate recall context and print to stdout."""
    db = _get_db(config)
    embedder = _get_embedder(config)

    from core.search import SearchEngine
    from core.daily import DailyLogManager
    from core.recall import RecallEngine

    search = SearchEngine(db, embedder, config)
    daily = DailyLogManager(config)
    recall = RecallEngine(search, daily, config)

    output = recall.recall(
        project_dir=args.project,
        budget_chars=args.budget,
    )
    print(output)
    db.close()


def cmd_flush(args, config: dict):
    """Flush session state to daily log."""
    db = _get_db(config)
    embedder = _get_embedder(config)

    from core.search import SearchEngine
    from core.daily import DailyLogManager
    from core.recall import RecallEngine

    search = SearchEngine(db, embedder, config)
    daily = DailyLogManager(config)
    recall = RecallEngine(search, daily, config)

    state = {}
    if args.state_file:
        try:
            with open(args.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading state file: {e}", file=sys.stderr)
            state = {}

    result = recall.flush(
        project_dir=args.project or "",
        session_id=args.session_id or "unknown",
        state=state,
    )
    print(json.dumps(result, indent=2))
    db.close()


def cmd_index(args, config: dict):
    """Run indexing — full or single file."""
    db = _get_db(config)
    embedder = _get_embedder(config)

    from core.indexer import MemoryIndexer
    indexer = MemoryIndexer(db, embedder, config)

    if args.file:
        file_path = os.path.abspath(args.file)
        # Detect project from file path
        project = None
        base = os.path.expanduser(config.get("memory_paths", {}).get("base", "~/.claude/projects"))
        if file_path.startswith(os.path.abspath(base)):
            rel = os.path.relpath(file_path, os.path.abspath(base))
            project = rel.split(os.sep)[0] if os.sep in rel else None
        count = indexer.index_file(file_path, project=project)
        print(json.dumps({"file": file_path, "chunks": count, "project": project}))
    elif args.all_projects:
        result = indexer.index_all_projects()
        print(json.dumps(result, indent=2))

        if config.get("indexer", {}).get("session_indexing", False):
            session_result = indexer.index_all_sessions()
            print(json.dumps({"sessions": session_result}, indent=2))
    else:
        # Default: index all projects
        result = indexer.index_all_projects()
        print(json.dumps(result, indent=2))

    db.close()


def cmd_status(args, config: dict):
    """Print system status as JSON."""
    db = _get_db(config)
    stats = db.get_stats()

    # Add daily log count
    global_mem = os.path.expanduser(config.get("memory_paths", {}).get("global", "~/.claude/projects/-Users-niwash/memory"))
    daily_dir = os.path.join(global_mem, "daily")
    daily_count = 0
    if os.path.isdir(daily_dir):
        daily_count = len([f for f in os.listdir(daily_dir) if f.endswith(".md")])

    stats["daily_log_files"] = daily_count

    embedder = _get_embedder(config)
    stats["embedding_model_available"] = embedder.is_available
    stats["config_path"] = os.environ.get(
        "MEMORY_ENGINE_CONFIG",
        os.path.expanduser("~/.claude/memory-engine/config.json"),
    )

    print(json.dumps(stats, indent=2))
    db.close()


def cmd_compress(args, config: dict):
    """Compress weekly daily logs into summaries."""
    from core.daily import DailyLogManager
    daily = DailyLogManager(config)

    if args.project:
        base = os.path.expanduser(config.get("memory_paths", {}).get("base", "~/.claude/projects"))
        project_hash = args.project.replace("/", "-").replace("\\", "-")
        memory_dir = os.path.join(base, project_hash, "memory")
    else:
        memory_dir = os.path.expanduser(
            config.get("memory_paths", {}).get("global", "~/.claude/projects/-Users-niwash/memory"))

    if not os.path.isdir(memory_dir):
        print(json.dumps({"success": False, "error": f"Memory dir not found: {memory_dir}"}))
        return

    result = daily.compress_week(memory_dir, week_start_date=args.week or "")
    print(json.dumps(result, indent=2))


def cmd_score(args, config: dict):
    """Auto-score chunk importance based on file type and content keywords."""
    db = _get_db(config)
    stats = db.auto_score_importance()
    print(f"Importance scoring: {stats['updated']} updated, {stats['skipped']} unchanged")

    # Show distribution
    dist = db.conn.execute(
        "SELECT CAST(importance AS INT) as imp, COUNT(*) FROM chunks GROUP BY imp ORDER BY imp DESC"
    ).fetchall()
    for row in dist:
        print(f"  importance {row[0]}: {row[1]} chunks")
    db.close()


def cmd_crossref(args, config: dict):
    """Auto-generate cross-references between related chunks."""
    db = _get_db(config)
    stats = db.auto_generate_cross_references()
    print(f"Cross-references: {stats['created']} created, {stats['existing']} already existed")
    total = db.conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
    print(f"Total cross-references: {total}")
    db.close()


def cmd_reembed(args, config: dict):
    """Re-embed all chunks with current model."""
    db = _get_db(config)
    embedder = _get_embedder(config)

    current_model = db.get_embedding_model_name()
    new_model = embedder.model_name

    chunks = db.get_all_chunks()
    if not chunks:
        print(json.dumps({"success": False, "error": "No chunks to re-embed"}))
        db.close()
        return

    # Validate dimension matches config and vec table
    new_dim = len(embedder.encode("test"))
    config_dim = config.get("embedding", {}).get("dimension", 384)
    if new_dim != config_dim:
        print(f"WARNING: New model dimension ({new_dim}) differs from config ({config_dim})")
        print(f"Updating config dimension and recreating vec table...")
        db.initialize_vec_table(new_dim)

    print(f"Re-embedding {len(chunks)} chunks: {current_model or 'none'} -> {new_model}")

    texts = [c["content"] for c in chunks]
    ids = [c["id"] for c in chunks]

    from core.embeddings import EmbeddingModel
    vectors = embedder.encode_batch(texts)
    vector_bytes = [EmbeddingModel.to_bytes(v) for v in vectors]

    db.insert_embeddings(ids, vector_bytes, new_model)

    # Recreate vec table if dimension changed
    old_spec = db.conn.execute("SELECT sql FROM sqlite_master WHERE name='vec_chunks'").fetchone()
    if old_spec:
        new_dim = embedder.dimension
        if f"float[{new_dim}]" not in (old_spec["sql"] or ""):
            db.conn.execute("DROP TABLE IF EXISTS vec_chunks")
            db.conn.commit()
            db.initialize_vec_table(new_dim)
            # Repopulate vec table
            if db.vec_available:
                for chunk_id, vec_blob in zip(ids, vector_bytes):
                    db.insert_vec_embedding(chunk_id, vec_blob)

    print(json.dumps({
        "success": True,
        "chunks_reembedded": len(ids),
        "old_model": current_model,
        "new_model": new_model,
    }, indent=2))
    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="KALIYA Memory Engine CLI",
        prog="memory-engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # recall
    recall_parser = subparsers.add_parser("recall", help="Generate recall context for session start")
    recall_parser.add_argument("--project", type=str, default=None, help="Project directory path")
    recall_parser.add_argument("--budget", type=int, default=4096, help="Character budget for output")

    # flush
    flush_parser = subparsers.add_parser("flush", help="Flush session state to daily log")
    flush_parser.add_argument("--project", type=str, default=None, help="Project directory path")
    flush_parser.add_argument("--session-id", type=str, default=None, help="Session ID")
    flush_parser.add_argument("--state-file", type=str, default=None, help="Path to JSON state file")

    # index
    index_parser = subparsers.add_parser("index", help="Run memory indexing")
    index_parser.add_argument("--all-projects", action="store_true", help="Index all project memory dirs")
    index_parser.add_argument("--file", type=str, default=None, help="Index a single file")

    # status
    subparsers.add_parser("status", help="Print system status")

    # compress
    compress_parser = subparsers.add_parser("compress", help="Compress weekly daily logs into summaries")
    compress_parser.add_argument("--project", type=str, default=None, help="Project directory path")
    compress_parser.add_argument("--week", type=str, default=None, help="Week start date (YYYY-MM-DD, Monday)")

    # reembed
    subparsers.add_parser("reembed", help="Re-embed all chunks with current model")

    # score
    subparsers.add_parser("score", help="Auto-score chunk importance by file type and keywords")

    # crossref
    subparsers.add_parser("crossref", help="Auto-generate cross-references between related chunks")

    args = parser.parse_args()
    config = _load_config()

    if args.command == "recall":
        cmd_recall(args, config)
    elif args.command == "flush":
        cmd_flush(args, config)
    elif args.command == "index":
        cmd_index(args, config)
    elif args.command == "status":
        cmd_status(args, config)
    elif args.command == "compress":
        cmd_compress(args, config)
    elif args.command == "reembed":
        cmd_reembed(args, config)
    elif args.command == "score":
        cmd_score(args, config)
    elif args.command == "crossref":
        cmd_crossref(args, config)


if __name__ == "__main__":
    main()
