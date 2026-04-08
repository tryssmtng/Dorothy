"""Hybrid BM25 + Vector search with RRF, temporal decay, and MMR re-ranking."""

import math
from datetime import datetime, timezone

import numpy as np

from .database import MemoryDB
from .embeddings import EmbeddingModel


class SearchEngine:
    def __init__(self, db: MemoryDB, embedder: EmbeddingModel, config: dict):
        self.db = db
        self.embedder = embedder
        self._vector_cache: dict[int, np.ndarray] = {}
        search_cfg = config.get("search", {})
        self.default_top_k = search_cfg.get("default_top_k", 8)
        self.candidate_multiplier = search_cfg.get("candidate_multiplier", 3)
        self.rrf_k = search_cfg.get("rrf_k", 60)
        self.mmr_lambda = search_cfg.get("mmr_lambda", 0.7)
        self.decay_half_life = search_cfg.get("decay_half_life_days", 30)
        self.decay_lambda = math.log(2) / self.decay_half_life if self.decay_half_life > 0 else 0
        expansion_cfg = config.get("query_expansion", {})
        self.expansion_enabled = expansion_cfg.get("enabled", False)
        self.expansion_map = expansion_cfg.get("static_map", {})
        self.cross_refs_enabled = config.get("cross_references", {}).get("enabled", False)
        self.max_linked = config.get("cross_references", {}).get("max_linked_per_result", 2)
        importance_cfg = config.get("importance", {})
        self.importance_enabled = importance_cfg.get("enabled", True)
        self.critical_threshold = importance_cfg.get("critical_threshold", 5.0)
        self.decay_exempt_importance = importance_cfg.get("decay_exempt_above", 5.0)
        self.max_result_chars = search_cfg.get("max_result_chars", 4096)

    def _expand_query(self, query: str) -> str:
        """Expand query with static synonyms for better BM25 matching."""
        if not self.expansion_enabled:
            return query

        terms = query.lower().split()
        expanded = list(terms)

        for term in terms:
            synonyms = self.expansion_map.get(term, [])
            expanded.extend(synonyms)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for t in expanded:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        return " ".join(unique)

    def search(self, query: str, scope: str = "all", top_k: int = 0,
               project: str = None) -> list[dict]:
        """Hybrid search: BM25 + vector + RRF + decay + MMR."""
        if top_k <= 0:
            top_k = self.default_top_k

        self._vector_cache.clear()
        candidate_count = top_k * self.candidate_multiplier
        proj_filter = project if scope == "project" and project else None

        # Step 1: BM25 search (with query expansion)
        expanded_query = self._expand_query(query)
        bm25_results = self._bm25_search(expanded_query, candidate_count, proj_filter)

        # Step 2: Vector search
        vector_results = self._vector_search(query, candidate_count, proj_filter)

        # Step 3: RRF merge
        merged = self._rrf_merge(bm25_results, vector_results)

        # Step 4: Temporal decay
        decayed = self._apply_decay(merged)

        # Step 5: MMR re-ranking
        final = self._mmr_rerank(decayed, top_k)

        return final

    def _bm25_search(self, query: str, limit: int, project: str = None) -> list[dict]:
        """Run FTS5 BM25 search and return ranked results."""
        rows = self.db.bm25_search(query, limit=limit, project=project)
        results = []
        for rank, row in enumerate(rows):
            results.append({
                "id": row["id"],
                "content": row["content"],
                "source_file": row["file_path"],
                "section": row["section_header"],
                "is_evergreen": row["is_evergreen"],
                "project": row["project"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "file_mtime": row["file_mtime"],
                "importance": row.get("importance", 1.0),
                "bm25_rank": rank + 1,
            })
        return results

    def _vector_search(self, query: str, limit: int, project: str = None) -> list[dict]:
        """Embed query, compare against all stored embeddings."""
        if not self.embedder.is_available:
            return []

        # Use sqlite-vec if available (faster for large datasets)
        if self.db.vec_available:
            try:
                query_vec = self.embedder.encode(query)
                query_bytes = EmbeddingModel.to_bytes(query_vec)
                vec_results = self.db.vec_search(query_bytes, limit)
                results = []
                for rank, row in enumerate(vec_results):
                    chunk_id = row["chunk_id"]
                    results.append({
                        "id": row["id"],
                        "content": row["content"],
                        "source_file": row["file_path"],
                        "section": row["section_header"],
                        "is_evergreen": row["is_evergreen"],
                        "project": row["project"],
                        "start_line": row["start_line"],
                        "end_line": row["end_line"],
                        "file_mtime": row["file_mtime"],
                        "importance": row.get("importance", 1.0),
                        "vector_rank": rank + 1,
                        "vector_score": 1.0 - row.get("distance", 0),
                    })
                # Populate _vector_cache so MMR doesn't re-encode all chunks
                for r in results:
                    emb_row = self.db.conn.execute(
                        "SELECT vector FROM embeddings WHERE chunk_id = ?", (r["id"],)
                    ).fetchone()
                    if emb_row:
                        self._vector_cache[r["id"]] = EmbeddingModel.from_bytes(emb_row["vector"])
                return results
            except Exception:
                pass  # Fall through to numpy scan

        try:
            query_vec = self.embedder.encode(query)
        except Exception:
            return []

        all_embs = self.db.get_all_embeddings()
        if not all_embs:
            return []

        # Filter by project if needed
        if project:
            all_embs = [e for e in all_embs if e["project"] == project]
            if not all_embs:
                return []

        vectors = np.array([EmbeddingModel.from_bytes(e["vector"]) for e in all_embs], dtype=np.float32)
        similarities = self.embedder.cosine_similarity_batch(query_vec, vectors)

        # Get top indices
        top_count = min(limit, len(similarities))
        top_indices = np.argsort(similarities)[::-1][:top_count]

        results = []
        for rank, idx in enumerate(top_indices):
            emb = all_embs[idx]
            chunk_id = emb["chunk_id"]
            self._vector_cache[chunk_id] = vectors[idx]
            results.append({
                "id": chunk_id,
                "content": emb["content"],
                "source_file": emb["file_path"],
                "section": emb["section_header"],
                "is_evergreen": emb["is_evergreen"],
                "project": emb["project"],
                "start_line": emb["start_line"],
                "end_line": emb["end_line"],
                "file_mtime": emb["file_mtime"],
                "importance": emb.get("importance", 1.0),
                "vector_rank": rank + 1,
                "vector_score": float(similarities[idx]),
            })
        return results

    def _rrf_merge(self, bm25_results: list[dict], vector_results: list[dict]) -> list[dict]:
        """Reciprocal Rank Fusion: merge BM25 and vector results."""
        scores = {}  # id -> {data, score}

        for r in bm25_results:
            rid = r["id"]
            rrf_score = 1.0 / (self.rrf_k + r["bm25_rank"])
            scores[rid] = {
                "data": r,
                "score": rrf_score,
            }

        for r in vector_results:
            rid = r["id"]
            rrf_score = 1.0 / (self.rrf_k + r["vector_rank"])
            if rid in scores:
                scores[rid]["score"] += rrf_score
            else:
                scores[rid] = {
                    "data": r,
                    "score": rrf_score,
                }

        # Sort by score descending
        sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        results = []
        for item in sorted_items:
            d = item["data"]
            d["score"] = item["score"]
            results.append(d)
        return results

    def _apply_decay(self, results: list[dict]) -> list[dict]:
        """Apply temporal decay to non-evergreen results."""
        if self.decay_lambda == 0:
            return results

        now_ts = datetime.now(timezone.utc).timestamp()

        for r in results:
            mtime = r.get("file_mtime", 0)
            if mtime <= 0:
                r["age_days"] = 0
                continue

            age_seconds = max(0, now_ts - mtime)
            age_days = age_seconds / 86400.0
            r["age_days"] = round(age_days, 1)

            if not r.get("is_evergreen") and r.get("importance", 1.0) < self.decay_exempt_importance:
                decay_factor = math.exp(-self.decay_lambda * age_days)
                r["score"] = r["score"] * decay_factor

            # Apply dampened importance multiplier (only when importance scoring is enabled)
            if self.importance_enabled:
                imp = r.get("importance", 1.0)
                if imp >= self.critical_threshold:
                    # Critical items get stronger boost
                    r["score"] = r["score"] * (1.0 + math.log(imp) * 1.5)
                elif imp > 1.0:
                    r["score"] = r["score"] * (1.0 + math.log(imp))
                else:
                    r["score"] = r["score"] * imp

        # Re-sort after decay
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _mmr_rerank(self, candidates: list[dict], top_k: int) -> list[dict]:
        """Maximal Marginal Relevance: balance relevance + diversity."""
        if len(candidates) <= top_k:
            return self._format_results(candidates)

        if not self.embedder.is_available:
            return self._format_results(candidates[:top_k])

        # Build vectors from cache; only encode uncached chunks
        vectors = []
        uncached_indices = []
        for i, c in enumerate(candidates):
            cached = self._vector_cache.get(c["id"])
            if cached is not None:
                vectors.append(cached)
            else:
                vectors.append(None)
                uncached_indices.append(i)

        if uncached_indices:
            try:
                texts = [candidates[i]["content"] for i in uncached_indices]
                new_vecs = self.embedder.encode_batch(texts)
                for j, idx in enumerate(uncached_indices):
                    vectors[idx] = new_vecs[j]
            except Exception:
                return self._format_results(candidates[:top_k])

        if any(v is None for v in vectors):
            return self._format_results(candidates[:top_k])

        selected = []
        selected_vecs = []
        remaining = list(range(len(candidates)))

        for _ in range(top_k):
            if not remaining:
                break

            best_idx = -1
            best_mmr = -float("inf")

            for idx in remaining:
                relevance = candidates[idx]["score"]

                max_sim = 0.0
                if selected_vecs:
                    for sv in selected_vecs:
                        sim = self.embedder.cosine_similarity(vectors[idx], sv)
                        if sim > max_sim:
                            max_sim = sim

                mmr = self.mmr_lambda * relevance - (1.0 - self.mmr_lambda) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx

            if best_idx >= 0:
                selected.append(candidates[best_idx])
                selected_vecs.append(vectors[best_idx])
                remaining.remove(best_idx)

        return self._format_results(selected)

    def _format_results(self, results: list[dict]) -> list[dict]:
        """Format results into clean output dicts."""
        formatted = []
        for r in results:
            content = r["content"]
            if len(content) > self.max_result_chars:
                content = content[:self.max_result_chars]
            entry = {
                "id": r.get("id", 0),
                "content": content,
                "source_file": r["source_file"],
                "section": r.get("section", ""),
                "score": round(r.get("score", 0), 4),
                "importance": r.get("importance", 1.0),
                "age_days": r.get("age_days", 0),
                "is_evergreen": bool(r.get("is_evergreen")),
                "project": r.get("project", ""),
                "start_line": r.get("start_line", 0),
                "end_line": r.get("end_line", 0),
            }
            # Add cross-referenced linked chunks
            if self.cross_refs_enabled and entry["id"]:
                linked = self.db.get_linked_chunks(entry["id"])
                if linked:
                    entry["linked"] = [
                        {
                            "content": l["content"][:200],
                            "source_file": l["file_path"],
                            "relationship": l["relationship"],
                        }
                        for l in linked[:self.max_linked]
                    ]
            formatted.append(entry)
        return formatted

    def search_sessions(self, query: str, limit: int = 5) -> list[dict]:
        """Search session summaries via FTS."""
        rows = self.db.search_sessions(query, limit=limit)
        results = []
        for row in rows:
            results.append({
                "session_id": row["session_id"],
                "project": row["project"],
                "summary": row["summary"],
                "user_requests": row["user_requests"],
                "errors_found": row["errors_found"],
                "turn_count": row["turn_count"],
            })
        return results
