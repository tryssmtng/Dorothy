"""SQLite database for memory chunks, embeddings, FTS5 search, and session summaries."""

import hashlib
import sqlite3
import json
import os
import sys
import threading
from datetime import datetime, timezone


class MemoryDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        # Note: WAL mode allows concurrent reads. _lock is for write serialization only.
        # Read operations are safe without lock due to MVCC in WAL mode.
        self._lock = threading.Lock()

    def initialize(self):
        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                section_header TEXT DEFAULT '',
                content TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                start_line INTEGER DEFAULT 0,
                end_line INTEGER DEFAULT 0,
                token_count INTEGER DEFAULT 0,
                file_mtime REAL DEFAULT 0,
                is_evergreen INTEGER DEFAULT 0,
                project TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_evergreen ON chunks(is_evergreen)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                vector BLOB NOT NULL,
                model_name TEXT DEFAULT 'all-MiniLM-L6-v2',
                created_at TEXT
            )
        """)

        # FTS5 for BM25 keyword search
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    section_header,
                    file_path,
                    project,
                    content='chunks',
                    content_rowid='id',
                    tokenize='porter unicode61'
                )
            """)
        except sqlite3.OperationalError as e:
            # FTS5 not available — fall back to basic table
            print(f"FTS5 creation skipped: {e}", file=sys.stderr)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                project TEXT DEFAULT '',
                started_at TEXT,
                summary TEXT DEFAULT '',
                files_modified TEXT DEFAULT '[]',
                tools_used TEXT DEFAULT '{}',
                turn_count INTEGER DEFAULT 0,
                user_requests TEXT DEFAULT '',
                errors_found TEXT DEFAULT '',
                created_at TEXT
            )
        """)

        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                    summary,
                    user_requests,
                    errors_found,
                    project,
                    content='session_summaries',
                    content_rowid='id',
                    tokenize='porter unicode61'
                )
            """)
        except sqlite3.OperationalError as e:
            print(f"FTS5 creation skipped: {e}", file=sys.stderr)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS index_metadata (
                file_path TEXT PRIMARY KEY,
                last_indexed REAL DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                embedding_count INTEGER DEFAULT 0
            )
        """)

        # FTS triggers for auto-sync
        for trigger_sql in [
            """CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, content, section_header, file_path, project)
                VALUES (new.id, new.content, new.section_header, new.file_path, new.project);
            END""",
            """CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, section_header, file_path, project)
                VALUES ('delete', old.id, old.content, old.section_header, old.file_path, old.project);
            END""",
            """CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, section_header, file_path, project)
                VALUES ('delete', old.id, old.content, old.section_header, old.file_path, old.project);
                INSERT INTO chunks_fts(rowid, content, section_header, file_path, project)
                VALUES (new.id, new.content, new.section_header, new.file_path, new.project);
            END""",
            """CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON session_summaries BEGIN
                INSERT INTO sessions_fts(rowid, summary, user_requests, errors_found, project)
                VALUES (new.id, new.summary, new.user_requests, new.errors_found, new.project);
            END""",
            """CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON session_summaries BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, summary, user_requests, errors_found, project)
                VALUES ('delete', old.id, old.summary, old.user_requests, old.errors_found, old.project);
            END""",
            """CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON session_summaries BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, summary, user_requests, errors_found, project)
                VALUES ('delete', old.id, old.summary, old.user_requests, old.errors_found, old.project);
                INSERT INTO sessions_fts(rowid, summary, user_requests, errors_found, project)
                VALUES (new.id, new.summary, new.user_requests, new.errors_found, new.project);
            END""",
        ]:
            try:
                cur.execute(trigger_sql)
            except sqlite3.OperationalError:
                pass  # trigger exists or FTS not available

        # Migration: add importance column
        try:
            cur.execute("ALTER TABLE chunks ADD COLUMN importance REAL DEFAULT 1.0")
        except sqlite3.OperationalError:
            pass  # column already exists

        # Cross-references table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cross_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
                target_chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
                relationship TEXT DEFAULT 'related',
                created_at TEXT,
                UNIQUE(source_chunk_id, target_chunk_id, relationship)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_xref_source ON cross_references(source_chunk_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_xref_target ON cross_references(target_chunk_id)")

        self.conn.commit()

        # Initialize sqlite-vec if available (toggled externally)
        self._vec_available = False

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Escape FTS5 special characters by quoting each term."""
        import re
        words = re.findall(r'\w+', query)
        if not words:
            return '""'
        return " ".join(f'"{w}"' for w in words)

    # --- Chunk Operations ---

    def insert_chunks(self, chunks: list[dict]) -> list[int]:
        now = datetime.now(timezone.utc).isoformat()
        ids = []
        with self._lock:
            cur = self.conn.cursor()
            for c in chunks:
                cur.execute("""
                    INSERT INTO chunks (file_path, section_header, content, chunk_index,
                        start_line, end_line, token_count, file_mtime, is_evergreen, project,
                        created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["file_path"], c.get("section_header", ""), c["content"],
                    c.get("chunk_index", 0), c.get("start_line", 0), c.get("end_line", 0),
                    c.get("token_count", 0), c.get("file_mtime", 0),
                    1 if c.get("is_evergreen") else 0, c.get("project", ""),
                    now, now,
                ))
                ids.append(cur.lastrowid)
            self.conn.commit()
        return ids

    def delete_chunks_by_file(self, file_path: str):
        with self._lock:
            # Delete cross-references (CASCADE handles this, but explicit for clarity)
            self.conn.execute("""
                DELETE FROM cross_references WHERE source_chunk_id IN (SELECT id FROM chunks WHERE file_path = ?)
                   OR target_chunk_id IN (SELECT id FROM chunks WHERE file_path = ?)
            """, (file_path, file_path))
            self.conn.execute("DELETE FROM embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE file_path = ?)", (file_path,))
            # Delete vec_chunks entries if table exists
            if self.vec_available:
                self.conn.execute("DELETE FROM vec_chunks WHERE chunk_id IN (SELECT id FROM chunks WHERE file_path = ?)", (file_path,))
            self.conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            self.conn.execute("DELETE FROM index_metadata WHERE file_path = ?", (file_path,))
            self.conn.commit()

    def save_chunk_metadata(self, file_path: str) -> dict:
        """Save importance + cross-refs before reindex. Returns metadata keyed by content hash."""
        metadata = {}
        chunks = self.conn.execute(
            "SELECT id, content, importance FROM chunks WHERE file_path = ?", (file_path,)
        ).fetchall()
        for c in chunks:
            content_hash = hashlib.md5(c["content"].encode()).hexdigest()
            entry = {}
            # Save importance if non-default
            if c["importance"] and c["importance"] != 1.0:
                entry["importance"] = c["importance"]
            # Save cross-refs
            refs = self.conn.execute("""
                SELECT c2.content, xr.relationship,
                       CASE WHEN xr.source_chunk_id = ? THEN 'outgoing' ELSE 'incoming' END as direction
                FROM cross_references xr
                JOIN chunks c2 ON (
                    CASE WHEN xr.source_chunk_id = ? THEN xr.target_chunk_id ELSE xr.source_chunk_id END = c2.id
                )
                WHERE xr.source_chunk_id = ? OR xr.target_chunk_id = ?
            """, (c["id"], c["id"], c["id"], c["id"])).fetchall()
            if refs:
                entry["cross_refs"] = [
                    {"content_hash": hashlib.md5(r["content"].encode()).hexdigest(),
                     "relationship": r["relationship"], "direction": r["direction"]}
                    for r in refs
                ]
            if entry:
                metadata[content_hash] = entry
        return metadata

    def restore_chunk_metadata(self, file_path: str, metadata: dict):
        """Restore importance + cross-refs after reindex by matching content hashes."""
        if not metadata:
            return
        chunks = self.conn.execute(
            "SELECT id, content FROM chunks WHERE file_path = ?", (file_path,)
        ).fetchall()
        hash_to_new_id = {}
        for c in chunks:
            content_hash = hashlib.md5(c["content"].encode()).hexdigest()
            hash_to_new_id[content_hash] = c["id"]

        with self._lock:
            for old_hash, entry in metadata.items():
                new_id = hash_to_new_id.get(old_hash)
                if not new_id:
                    continue
                # Restore importance
                if "importance" in entry:
                    self.conn.execute(
                        "UPDATE chunks SET importance = ? WHERE id = ?",
                        (entry["importance"], new_id)
                    )
                # Restore cross-refs
                for ref in entry.get("cross_refs", []):
                    target_id = hash_to_new_id.get(ref["content_hash"])
                    if not target_id:
                        # Target chunk might be in a different file — search by content hash
                        all_chunks = self.conn.execute("SELECT id, content FROM chunks").fetchall()
                        for ac in all_chunks:
                            if hashlib.md5(ac["content"].encode()).hexdigest() == ref["content_hash"]:
                                target_id = ac["id"]
                                break
                    if target_id:
                        if ref["direction"] == "outgoing":
                            src, tgt = new_id, target_id
                        else:
                            src, tgt = target_id, new_id
                        try:
                            self.conn.execute(
                                "INSERT OR IGNORE INTO cross_references (source_chunk_id, target_chunk_id, relationship, created_at) VALUES (?, ?, ?, ?)",
                                (src, tgt, ref["relationship"], datetime.now(timezone.utc).isoformat())
                            )
                        except Exception as e:
                            print(f"metadata restoration failed: {e}", file=sys.stderr)
            self.conn.commit()

    def get_all_chunks(self, project: str = None) -> list[dict]:
        if project:
            rows = self.conn.execute("SELECT * FROM chunks WHERE project = ?", (project,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM chunks").fetchall()
        return [dict(r) for r in rows]

    def mark_important(self, chunk_ids: list[int], importance: float):
        """Set importance score for chunks. >= 5.0 = exempt from temporal decay."""
        with self._lock:
            placeholders = ','.join('?' * len(chunk_ids))
            self.conn.execute(
                f"UPDATE chunks SET importance = ? WHERE id IN ({placeholders})",
                [importance] + chunk_ids
            )
            self.conn.commit()

    def search_chunks_by_content(self, query: str, limit: int = 5) -> list[dict]:
        """Simple content search for finding chunks to mark."""
        # Escape LIKE wildcards in user input
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(
            "SELECT id, file_path, section_header, content, importance FROM chunks WHERE content LIKE ? ESCAPE '\\' LIMIT ?",
            (f"%{escaped}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def add_cross_reference(self, source_id: int, target_id: int, relationship: str = "related"):
        """Create a cross-reference link between two chunks."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.conn.execute("""
                INSERT OR IGNORE INTO cross_references
                (source_chunk_id, target_chunk_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (source_id, target_id, relationship, now))
            self.conn.commit()

    def get_linked_chunks(self, chunk_id: int) -> list[dict]:
        """Get all chunks linked to a given chunk (bidirectional)."""
        rows = self.conn.execute("""
            SELECT DISTINCT c.id, c.file_path, c.section_header, c.content, xr.relationship
            FROM cross_references xr
            JOIN chunks c ON (
                (xr.target_chunk_id = c.id AND xr.source_chunk_id = ?) OR
                (xr.source_chunk_id = c.id AND xr.target_chunk_id = ?)
            )
        """, (chunk_id, chunk_id)).fetchall()
        return [dict(r) for r in rows]

    # --- Embedding Operations ---

    def insert_embeddings(self, chunk_ids: list[int], vectors: list[bytes], model_name: str = "all-MiniLM-L6-v2"):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self.conn.cursor()
            for cid, vec in zip(chunk_ids, vectors):
                cur.execute("""
                    INSERT OR REPLACE INTO embeddings (chunk_id, vector, model_name, created_at)
                    VALUES (?, ?, ?, ?)
                """, (cid, vec, model_name, now))
            self.conn.commit()

    def get_all_embeddings(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT e.chunk_id, e.vector, c.file_path, c.section_header, c.content,
                   c.file_mtime, c.is_evergreen, c.project, c.start_line, c.end_line,
                   c.importance
            FROM embeddings e JOIN chunks c ON e.chunk_id = c.id
        """).fetchall()
        return [dict(r) for r in rows]

    def get_embedding_model_name(self) -> str | None:
        """Get the model name used for existing embeddings."""
        row = self.conn.execute(
            "SELECT model_name FROM embeddings LIMIT 1"
        ).fetchone()
        return row["model_name"] if row else None

    def needs_reembedding(self, new_model: str) -> bool:
        """Check if stored embeddings use a different model."""
        current = self.get_embedding_model_name()
        return current is not None and current != new_model

    # --- BM25 Search ---

    def bm25_search(self, query: str, limit: int = 24, project: str = None) -> list[dict]:
        try:
            safe_query = self._sanitize_fts5_query(query)
            if project:
                rows = self.conn.execute("""
                    SELECT c.id, c.file_path, c.section_header, c.content,
                           c.file_mtime, c.is_evergreen, c.project, c.start_line, c.end_line,
                           c.importance, chunks_fts.rank AS bm25_rank
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.id
                    WHERE chunks_fts MATCH ? AND c.project = ?
                    ORDER BY chunks_fts.rank
                    LIMIT ?
                """, (safe_query, project, limit)).fetchall()
            else:
                rows = self.conn.execute("""
                    SELECT c.id, c.file_path, c.section_header, c.content,
                           c.file_mtime, c.is_evergreen, c.project, c.start_line, c.end_line,
                           c.importance, chunks_fts.rank AS bm25_rank
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY chunks_fts.rank
                    LIMIT ?
                """, (safe_query, limit)).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def search_sessions(self, query: str, limit: int = 5) -> list[dict]:
        try:
            safe_query = self._sanitize_fts5_query(query)
            rows = self.conn.execute("""
                SELECT s.*, sessions_fts.rank AS bm25_rank
                FROM sessions_fts
                JOIN session_summaries s ON sessions_fts.rowid = s.id
                WHERE sessions_fts MATCH ?
                ORDER BY sessions_fts.rank
                LIMIT ?
            """, (safe_query, limit)).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    # --- Session Operations ---

    def upsert_session(self, session_data: dict):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.conn.execute("""
                INSERT INTO session_summaries
                    (session_id, project, started_at, summary, files_modified, tools_used,
                     turn_count, user_requests, errors_found, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary=excluded.summary, files_modified=excluded.files_modified,
                    tools_used=excluded.tools_used, turn_count=excluded.turn_count,
                    user_requests=excluded.user_requests, errors_found=excluded.errors_found
            """, (
                session_data["session_id"], session_data.get("project", ""),
                session_data.get("started_at", ""), session_data.get("summary", ""),
                json.dumps(session_data.get("files_modified", [])),
                json.dumps(session_data.get("tools_used", {})),
                session_data.get("turn_count", 0),
                session_data.get("user_requests", ""),
                session_data.get("errors_found", ""),
                now,
            ))
            self.conn.commit()

    # --- Index Metadata ---

    def get_file_index_meta(self, file_path: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM index_metadata WHERE file_path = ?", (file_path,)).fetchone()
        return dict(row) if row else None

    def update_file_index_meta(self, file_path: str, mtime: float, chunk_count: int, embedding_count: int):
        with self._lock:
            self.conn.execute("""
                INSERT INTO index_metadata (file_path, last_indexed, chunk_count, embedding_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    last_indexed=excluded.last_indexed, chunk_count=excluded.chunk_count,
                    embedding_count=excluded.embedding_count
            """, (file_path, mtime, chunk_count, embedding_count))
            self.conn.commit()

    # --- Stats ---

    def get_stats(self) -> dict:
        chunk_count = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        embedding_count = self.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        session_count = self.conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
        file_count = self.conn.execute("SELECT COUNT(DISTINCT file_path) FROM chunks").fetchone()[0]
        return {
            "total_chunks": chunk_count,
            "total_embeddings": embedding_count,
            "total_sessions": session_count,
            "indexed_files": file_count,
        }

    def close(self):
        self.conn.close()

    # --- sqlite-vec Native Vector Search ---

    def cleanup_orphan_chunks(self) -> int:
        """Remove chunks whose source files no longer exist on disk."""
        cursor = self.conn.execute("SELECT DISTINCT file_path FROM chunks")
        paths = [row[0] for row in cursor.fetchall()]
        removed = 0
        for path in paths:
            if not os.path.exists(path):
                self.delete_chunks_by_file(path)
                removed += 1
        return removed

    def initialize_vec_table(self, dimension: int | None = None):
        """Create sqlite-vec virtual table if extension available.

        dimension: Embedding vector dimension. If None, auto-detects from:
          1. Existing embeddings in the DB (len(blob) / 4)
          2. Falls back to 384 (all-MiniLM-L6-v2 default)
        """
        if dimension is None:
            dimension = self._detect_embedding_dimension()
        try:
            self.conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(self.conn)
            # Check existing dimension — drop and recreate if different
            try:
                existing = self.conn.execute("SELECT embedding FROM vec_chunks LIMIT 1").fetchone()
                if existing and len(existing[0]) != dimension * 4:  # float32 = 4 bytes
                    self.conn.execute("DROP TABLE vec_chunks")
            except Exception:
                pass  # Table doesn't exist yet
            self.conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
                USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{dimension}])
            """)
            self._vec_available = True
        except Exception:
            self._vec_available = False

    def _detect_embedding_dimension(self) -> int:
        """Auto-detect embedding dimension from existing embeddings or fall back to 384."""
        try:
            row = self.conn.execute("SELECT vector FROM embeddings LIMIT 1").fetchone()
            if row and row[0]:
                return len(row[0]) // 4  # float32 = 4 bytes per dimension
        except Exception:
            pass
        return 384

    @property
    def vec_available(self) -> bool:
        """Check if sqlite-vec is available."""
        return getattr(self, '_vec_available', False)

    def vec_search(self, query_vec_bytes: bytes, limit: int) -> list[dict]:
        """Native vector search using sqlite-vec."""
        if not self.vec_available:
            return []
        rows = self.conn.execute("""
            SELECT v.chunk_id, v.distance, c.id, c.file_path, c.section_header,
                   c.content, c.file_mtime, c.is_evergreen, c.project,
                   c.start_line, c.end_line, c.importance
            FROM vec_chunks v
            JOIN chunks c ON v.chunk_id = c.id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
        """, (query_vec_bytes, limit)).fetchall()
        return [dict(r) for r in rows]

    def insert_vec_embedding(self, chunk_id: int, vec_bytes: bytes):
        """Insert embedding into sqlite-vec virtual table."""
        if not self.vec_available:
            return
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, vec_bytes)
            )
            self.conn.commit()

    def populate_vec_from_existing(self) -> int:
        """Backfill vec_chunks from existing embeddings table. Returns count populated."""
        if not self.vec_available:
            return 0
        # Get all embeddings not yet in vec_chunks
        rows = self.conn.execute("""
            SELECT e.chunk_id, e.vector FROM embeddings e
            WHERE e.chunk_id NOT IN (SELECT chunk_id FROM vec_chunks)
        """).fetchall()
        if not rows:
            return 0
        with self._lock:
            for row in rows:
                self.conn.execute(
                    "INSERT OR REPLACE INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                    (row["chunk_id"], row["vector"])
                )
            self.conn.commit()
        return len(rows)

    def get_vec_dimension(self) -> int | None:
        """Get the dimension of the current vec_chunks table, or None if not available."""
        if not self.vec_available:
            return None
        try:
            row = self.conn.execute("SELECT embedding FROM vec_chunks LIMIT 1").fetchone()
            if row and row["embedding"]:
                # float32 = 4 bytes per dimension
                return len(row["embedding"]) // 4
            # Table exists but empty — check table SQL for dimension
            spec = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='vec_chunks'"
            ).fetchone()
            if spec and spec["sql"]:
                import re
                match = re.search(r'float\[(\d+)\]', spec["sql"])
                if match:
                    return int(match.group(1))
        except Exception:
            pass
        return None

    def delete_vec_by_file(self, file_path: str):
        """Delete vec embeddings for chunks belonging to a file."""
        if not self.vec_available:
            return
        with self._lock:
            self.conn.execute("""
                DELETE FROM vec_chunks WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE file_path = ?
                )
            """, (file_path,))
            self.conn.commit()

    # --- Auto Scoring & Cross-References ---

    def auto_score_importance(self) -> dict:
        """Auto-score chunk importance based on file type and content keywords."""
        SCORES = {
            "credentials-secrets": 8.0,
            "accounts-credentials": 8.0,
            "mistakes-learnings": 6.0,
            "MEMORY.md": 5.0,
            "CLAUDE.md": 5.0,
            "workflow-patterns": 4.0,
            "malik-preferences": 4.0,
            "device-environment": 3.0,
            "heartbeat": 2.0,
        }
        KEYWORD_BOOST = {
            "password": 2.0, "api_key": 2.0, "token": 2.0, "secret": 2.0,
            "credential": 2.0, "ssh": 1.5, "CRITICAL": 1.5, "NEVER": 1.0,
            "BLOCKED": 1.0, "BANNED": 1.0, "root cause": 1.5,
        }

        stats = {"updated": 0, "skipped": 0}
        with self._lock:
            chunks = self.conn.execute(
                "SELECT id, file_path, content, importance FROM chunks"
            ).fetchall()

            for chunk in chunks:
                basename = os.path.basename(chunk["file_path"])
                name_no_ext = os.path.splitext(basename)[0]

                # Start with file-based score
                score = 1.0
                for pattern, s in SCORES.items():
                    if pattern in basename or pattern in name_no_ext:
                        score = max(score, s)
                        break

                # Keyword boost
                content_lower = chunk["content"].lower()
                for keyword, boost in KEYWORD_BOOST.items():
                    if keyword.lower() in content_lower:
                        score = min(score + boost, 10.0)  # Cap at 10.0

                # Only update if different from current
                if abs(score - (chunk["importance"] or 1.0)) > 0.01:
                    self.conn.execute(
                        "UPDATE chunks SET importance = ? WHERE id = ?",
                        (score, chunk["id"])
                    )
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1

            self.conn.commit()
        return stats

    def auto_generate_cross_references(self) -> dict:
        """Auto-generate cross-references between related chunks using keyword overlap."""
        stats = {"created": 0, "existing": 0}

        # Get all chunks with their content
        chunks = self.conn.execute(
            "SELECT id, file_path, content, section_header FROM chunks"
        ).fetchall()

        # Extract keywords per chunk (simple tokenization)
        def extract_keywords(text):
            stopwords = {
                'that', 'this', 'with', 'from', 'have', 'will', 'been',
                'they', 'their', 'when', 'what', 'which', 'about', 'into',
                'than', 'only', 'also', 'more', 'some', 'other', 'were', 'then',
            }
            words = set()
            for word in text.lower().split():
                word = word.strip(".,;:!?()[]{}\"'`")
                if len(word) > 3 and word not in stopwords:
                    words.add(word)
            return words

        # Entity patterns to link
        ENTITIES = [
            'ssh', 'careone', 'frida', 'xposed', 'shopify', 'playwright',
            'memory-engine', 'hook', 'claude.md', 'deploy', 'server', 'adb',
            'android', 'bsv',
        ]

        chunk_keywords = []
        for c in chunks:
            kw = extract_keywords(c["content"])
            entities = {e for e in ENTITIES if e in c["content"].lower()}
            chunk_keywords.append({
                "id": c["id"], "file_path": c["file_path"],
                "keywords": kw, "entities": entities,
            })

        with self._lock:
            for i, c1 in enumerate(chunk_keywords):
                for c2 in chunk_keywords[i + 1:]:
                    # Skip same file
                    if c1["file_path"] == c2["file_path"]:
                        continue

                    # Check entity overlap
                    shared_entities = c1["entities"] & c2["entities"]
                    if not shared_entities:
                        continue

                    # Check keyword overlap (Jaccard)
                    intersection = c1["keywords"] & c2["keywords"]
                    union = c1["keywords"] | c2["keywords"]
                    if not union:
                        continue
                    jaccard = len(intersection) / len(union)

                    if jaccard > 0.15 or len(shared_entities) >= 2:
                        # Check if already exists
                        existing = self.conn.execute(
                            "SELECT 1 FROM cross_references WHERE source_chunk_id=? AND target_chunk_id=?",
                            (c1["id"], c2["id"])
                        ).fetchone()
                        if not existing:
                            now = datetime.now(timezone.utc).isoformat()
                            self.conn.execute("""
                                INSERT OR IGNORE INTO cross_references
                                (source_chunk_id, target_chunk_id, relationship, created_at)
                                VALUES (?, ?, ?, ?)
                            """, (c1["id"], c2["id"], "related", now))
                            stats["created"] += 1
                        else:
                            stats["existing"] += 1

            self.conn.commit()
        return stats
