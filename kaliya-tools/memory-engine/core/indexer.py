"""Chunking + embedding pipeline for memory files and sessions."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .database import MemoryDB
from .embeddings import EmbeddingModel


class MemoryIndexer:
    def __init__(self, db: MemoryDB, embedder: EmbeddingModel, config: dict):
        self.db = db
        self.embedder = embedder
        self.config = config
        chunking = config.get("chunking", {})
        self.target_tokens = chunking.get("target_tokens", 400)
        self.overlap_tokens = chunking.get("overlap_tokens", 80)
        self.min_chunk_tokens = chunking.get("min_chunk_tokens", 50)
        self.evergreen_patterns = config.get("evergreen_patterns", [])
        indexer_cfg = config.get("indexer", {})
        self.max_summary_chars = indexer_cfg.get("max_session_summary_chars", 2000)
        self.interval_seconds = indexer_cfg.get("interval_seconds", 900)
        self.session_indexing = indexer_cfg.get("session_indexing", True)

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * 1.3)

    def _is_evergreen(self, file_path: str) -> bool:
        basename = os.path.basename(file_path)
        return basename in self.evergreen_patterns

    def _chunk_content(self, content: str, file_path: str) -> list[dict]:
        """Split content into chunks: section-aware, then paragraph-based."""
        lines = content.split("\n")
        sections = []
        current_header = ""
        current_lines = []
        current_start = 1

        for i, line in enumerate(lines, start=1):
            if line.startswith("## ") and current_lines:
                sections.append({
                    "header": current_header,
                    "text": "\n".join(current_lines),
                    "start_line": current_start,
                    "end_line": i - 1,
                })
                current_header = line.strip()
                current_lines = [line]
                current_start = i
            else:
                if line.startswith("## ") and not current_lines:
                    current_header = line.strip()
                    current_start = i
                current_lines.append(line)

        if current_lines:
            sections.append({
                "header": current_header,
                "text": "\n".join(current_lines),
                "start_line": current_start,
                "end_line": len(lines),
            })

        chunks = []
        for section in sections:
            section_chunks = self._split_section(
                section["text"], section["header"],
                section["start_line"], section["end_line"],
                file_path,
            )
            chunks.extend(section_chunks)

        return chunks

    def _split_section(self, text: str, header: str, start_line: int,
                       end_line: int, file_path: str) -> list[dict]:
        """Split a section into target-sized chunks with overlap."""
        tokens = self._estimate_tokens(text)
        if tokens <= self.target_tokens:
            if tokens < self.min_chunk_tokens:
                return []
            return [{
                "content": text,
                "section_header": header,
                "start_line": start_line,
                "end_line": end_line,
                "token_count": tokens,
            }]

        paragraphs = re.split(r"\n\n+", text)
        chunks = []
        current_text = ""
        current_start = start_line
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)
            if current_tokens + para_tokens > self.target_tokens and current_text:
                para_lines = current_text.count("\n") + 1
                chunk_end = current_start + para_lines - 1
                chunks.append({
                    "content": current_text,
                    "section_header": header,
                    "start_line": current_start,
                    "end_line": min(chunk_end, end_line),
                    "token_count": current_tokens,
                })
                # Overlap: keep last portion
                overlap_text = self._get_overlap(current_text)
                overlap_tokens = self._estimate_tokens(overlap_text)
                overlap_lines = overlap_text.count("\n")
                current_text = overlap_text + "\n\n" + para if overlap_text else para
                current_start = max(current_start, chunk_end - overlap_lines)
                current_tokens = overlap_tokens + para_tokens
            else:
                if current_text:
                    current_text += "\n\n" + para
                else:
                    current_text = para
                current_tokens += para_tokens

        if current_text and self._estimate_tokens(current_text) >= self.min_chunk_tokens:
            para_lines = current_text.count("\n") + 1
            chunks.append({
                "content": current_text,
                "section_header": header,
                "start_line": current_start,
                "end_line": end_line,
                "token_count": self._estimate_tokens(current_text),
            })

        return chunks

    def _get_overlap(self, text: str) -> str:
        """Get the trailing portion of text within overlap_tokens budget."""
        words = text.split()
        overlap_word_count = int(self.overlap_tokens / 1.3)
        if len(words) <= overlap_word_count:
            return text
        return " ".join(words[-overlap_word_count:])

    def index_file(self, file_path: str, project: str = "", is_evergreen: bool = False) -> int:
        """Index a single file. Returns number of chunks created."""
        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.isfile(file_path):
            return 0

        mtime = os.path.getmtime(file_path)

        # Check if already indexed and not modified
        meta = self.db.get_file_index_meta(file_path)
        if meta and meta["last_indexed"] >= mtime:
            return meta.get("chunk_count", 0)

        # Read file
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, IOError):
            return 0

        if not content.strip():
            return 0

        # Preserve importance + cross-references before re-indexing
        saved_metadata = self.db.save_chunk_metadata(file_path)

        # Delete old chunks + embeddings + vec entries + index_metadata for this file
        self.db.delete_chunks_by_file(file_path)

        # Determine evergreen status
        if not is_evergreen:
            is_evergreen = self._is_evergreen(file_path)

        # Chunk the content
        raw_chunks = self._chunk_content(content, file_path)
        if not raw_chunks:
            return 0

        # Prepare DB records
        chunk_records = []
        for i, c in enumerate(raw_chunks):
            chunk_records.append({
                "file_path": file_path,
                "section_header": c["section_header"],
                "content": c["content"],
                "chunk_index": i,
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "token_count": c["token_count"],
                "file_mtime": mtime,
                "is_evergreen": is_evergreen,
                "project": project,
            })

        chunk_ids = self.db.insert_chunks(chunk_records)

        # Embed and store
        embedding_count = 0
        if self.embedder.is_available:
            try:
                texts = [c["content"] for c in raw_chunks]
                vectors = self.embedder.encode_batch(texts)
                vector_bytes = [EmbeddingModel.to_bytes(v) for v in vectors]
                self.db.insert_embeddings(chunk_ids, vector_bytes, self.embedder.model_name)
                embedding_count = len(vectors)
                # Populate sqlite-vec table if available
                if self.db.vec_available:
                    for cid, vb in zip(chunk_ids, vector_bytes):
                        self.db.insert_vec_embedding(cid, vb)
            except Exception:
                pass  # embeddings fail gracefully, BM25 still works

        # Restore importance + cross-references
        if saved_metadata:
            self.db.restore_chunk_metadata(file_path, saved_metadata)

        # Update metadata
        self.db.update_file_index_meta(file_path, mtime, len(chunk_ids), embedding_count)
        return len(chunk_ids)

    def index_directory(self, dir_path: str, project: str = "") -> dict:
        """Index all .md files in a directory recursively."""
        dir_path = os.path.abspath(os.path.expanduser(dir_path))
        if not os.path.isdir(dir_path):
            return {"indexed": 0, "chunks": 0}

        total_files = 0
        total_chunks = 0
        for root, _dirs, files in os.walk(dir_path):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                is_eg = self._is_evergreen(fpath)
                count = self.index_file(fpath, project=project, is_evergreen=is_eg)
                if count > 0:
                    total_files += 1
                    total_chunks += count

        return {"indexed": total_files, "chunks": total_chunks}

    def index_all_projects(self) -> dict:
        """Scan all project memory directories and index them."""
        base = os.path.expanduser(self.config.get("memory_paths", {}).get("base", "~/.claude/projects"))
        results = {"projects": 0, "files": 0, "chunks": 0}

        if not os.path.isdir(base):
            return results

        for project_name in os.listdir(base):
            project_dir = os.path.join(base, project_name)
            if not os.path.isdir(project_dir):
                continue

            memory_dir = os.path.join(project_dir, "memory")
            if not os.path.isdir(memory_dir):
                continue

            res = self.index_directory(memory_dir, project=project_name)
            if res["indexed"] > 0:
                results["projects"] += 1
                results["files"] += res["indexed"]
                results["chunks"] += res["chunks"]

            # Also index daily subdirectory
            daily_dir = os.path.join(memory_dir, "daily")
            if os.path.isdir(daily_dir):
                daily_res = self.index_directory(daily_dir, project=project_name)
                results["files"] += daily_res["indexed"]
                results["chunks"] += daily_res["chunks"]

        return results

    def index_session_jsonl(self, jsonl_path: str, project: str = "") -> bool:
        """Parse and index a JSONL session file into session_summaries."""
        if not self.session_indexing:
            return False
        jsonl_path = os.path.abspath(os.path.expanduser(jsonl_path))
        if not os.path.isfile(jsonl_path):
            return False

        session_id = Path(jsonl_path).stem

        # Check if already indexed
        existing = self.db.conn.execute(
            "SELECT session_id FROM session_summaries WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if existing:
            return False

        try:
            with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (OSError, IOError):
            return False

        user_requests = []
        assistant_texts = []
        errors_found = []
        tools_used = {}
        files_modified = set()
        turn_count = 0
        started_at = ""

        # Error detection keywords — only match short tool_result content (not file dumps)
        _error_keywords = ("error", "traceback", "exception", "failed", "command failed")

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type", "")

            # Grab timestamp from any early entry
            if not started_at:
                ts = entry.get("timestamp", "")
                if ts:
                    started_at = ts

            if entry_type == "user":
                msg = entry.get("message", {})
                content = msg.get("content", "")

                # content can be a list of blocks or a string
                user_text_parts = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            block_type = block.get("type", "")
                            if block_type == "text":
                                txt = block.get("text", "")
                                if "<system-reminder>" not in txt:
                                    user_text_parts.append(txt)
                            elif block_type == "tool_result":
                                # Tool results live inside user messages
                                tr_content = block.get("content", "")
                                self._check_tool_result_errors(
                                    tr_content, errors_found
                                )
                        elif isinstance(block, str):
                            if "<system-reminder>" not in block:
                                user_text_parts.append(block)
                elif isinstance(content, str):
                    if "<system-reminder>" not in content:
                        user_text_parts.append(content)

                joined = " ".join(user_text_parts).strip()
                if joined:
                    user_requests.append(joined[:500])
                    turn_count += 1

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                content = msg.get("content", [])

                text_parts = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            block_type = block.get("type", "")
                            if block_type == "text":
                                text_parts.append(block.get("text", ""))
                            elif block_type == "tool_use":
                                tool_name = block.get("name", "unknown")
                                tools_used[tool_name] = tools_used.get(tool_name, 0) + 1
                                # Extract files_modified from Edit/Write/NotebookEdit
                                inp = block.get("input", {})
                                if tool_name in ("Edit", "Write", "NotebookEdit"):
                                    fp = inp.get("file_path", "") or inp.get("notebook_path", "")
                                    if fp:
                                        files_modified.add(fp)
                        elif isinstance(block, str):
                            text_parts.append(block)
                elif isinstance(content, str):
                    text_parts.append(content)

                joined = " ".join(text_parts).strip()
                if joined:
                    assistant_texts.append(joined[:500])

            # progress entries (hooks, waiting) — skip, no useful content to extract

        # Build summary
        summary_parts = []
        if user_requests:
            summary_parts.append("User requests: " + " | ".join(user_requests[:10]))
        if assistant_texts:
            summary_parts.append("Assistant actions: " + " | ".join(assistant_texts[:5]))
        summary = "\n".join(summary_parts)[:self.max_summary_chars]

        user_req_text = "\n".join(user_requests[:20])[:self.max_summary_chars]
        error_text = "\n".join(errors_found[:10])[:self.max_summary_chars]

        self.db.upsert_session({
            "session_id": session_id,
            "project": project,
            "started_at": started_at,
            "summary": summary,
            "files_modified": sorted(files_modified),
            "tools_used": tools_used,
            "turn_count": turn_count,
            "user_requests": user_req_text,
            "errors_found": error_text,
        })
        return True

    @staticmethod
    def _check_tool_result_errors(tr_content, errors_found: list):
        """Extract genuine errors from tool_result content, skipping large file dumps."""
        if isinstance(tr_content, str):
            # Skip large content (likely file reads, not errors)
            if len(tr_content) > 1000:
                return
            lower = tr_content.lower()
            if any(kw in lower for kw in ("error", "traceback", "exception", "failed", "command failed")):
                errors_found.append(tr_content[:300])
        elif isinstance(tr_content, list):
            for part in tr_content:
                if isinstance(part, dict):
                    txt = part.get("text", "")
                    if len(txt) > 1000:
                        continue
                    lower = txt.lower()
                    if any(kw in lower for kw in ("error", "traceback", "exception", "failed", "command failed")):
                        errors_found.append(txt[:300])

    def index_all_sessions(self) -> dict:
        """Find and index all JSONL session files (UUID-named, direct children of project dirs)."""
        if not self.session_indexing:
            return {"indexed": 0, "skipped": 0, "disabled": True}
        base = os.path.expanduser(self.config.get("memory_paths", {}).get("base", "~/.claude/projects"))
        results = {"indexed": 0, "skipped": 0}

        if not os.path.isdir(base):
            return results

        # UUID pattern: 8-4-4-4-12 hex chars
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$"
        )

        for project_name in os.listdir(base):
            project_dir = os.path.join(base, project_name)
            if not os.path.isdir(project_dir):
                continue

            for fname in os.listdir(project_dir):
                if not uuid_re.match(fname):
                    continue
                fpath = os.path.join(project_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                success = self.index_session_jsonl(fpath, project=project_name)
                if success:
                    results["indexed"] += 1
                else:
                    results["skipped"] += 1

        return results
