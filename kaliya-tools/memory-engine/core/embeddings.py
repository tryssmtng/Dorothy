"""Local embedding model wrapper using sentence-transformers with lazy loading."""

import os

import numpy as np

_SENTENCE_TRANSFORMERS_AVAILABLE = True
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

MODEL_REGISTRY = {
    "all-MiniLM-L6-v2": {"dimension": 384, "type": "sentence-transformers"},
    "all-mpnet-base-v2": {"dimension": 768, "type": "sentence-transformers"},
    "paraphrase-MiniLM-L6-v2": {"dimension": 384, "type": "sentence-transformers"},
    "multi-qa-MiniLM-L6-cos-v1": {"dimension": 384, "type": "sentence-transformers"},
}


class EmbeddingModel:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", model_dir: str = "",
                 model_priority: list[str] = None, lazy_load: bool = True,
                 auto_select: bool = False):
        self.model_dir = os.path.expanduser(model_dir) if model_dir else os.path.expanduser(
            "~/.claude/memory-engine/models/"
        )
        self.lazy_load = lazy_load
        self.auto_select = auto_select
        if self.auto_select and model_priority:
            self.model_name = self._select_best_model(model_priority)
        elif model_priority:
            self.model_name = self._select_best_model(model_priority)
        else:
            self.model_name = model_name
        spec = MODEL_REGISTRY.get(self.model_name, {})
        self.dimension = spec.get("dimension", 384)
        self._model = None
        # Eager load if lazy_load is disabled
        if not self.lazy_load and _SENTENCE_TRANSFORMERS_AVAILABLE:
            self._load_model()

    def _select_best_model(self, priority: list[str]) -> str:
        """Try models in priority order, return first available."""
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            return priority[0] if priority else "all-MiniLM-L6-v2"
        for model_name in priority:
            if model_name not in MODEL_REGISTRY:
                continue
            # Check if model is cached locally
            cache_path = os.path.join(self.model_dir, model_name.replace("/", "_"))
            if os.path.isdir(cache_path):
                return model_name
        # Fallback: return first in priority list (will be downloaded on first use)
        return priority[0] if priority else "all-MiniLM-L6-v2"

    def _load_model(self):
        if self._model is not None:
            return
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        os.makedirs(self.model_dir, exist_ok=True)
        self._model = SentenceTransformer(self.model_name, cache_folder=self.model_dir)

    @property
    def is_available(self) -> bool:
        return _SENTENCE_TRANSFORMERS_AVAILABLE

    @property
    def is_model_cached(self) -> bool:
        """Check if model is cached locally (no download needed)."""
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            return False
        cache_path = os.path.join(self.model_dir, self.model_name.replace("/", "_"))
        return os.path.isdir(cache_path)

    def encode(self, text: str) -> np.ndarray:
        self._load_model()
        vec = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vec.astype(np.float32)

    def encode_batch(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        self._load_model()
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=64)
        return [v.astype(np.float32) for v in vecs]

    def cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def cosine_similarity_batch(self, query_vec: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        if len(vectors) == 0:
            return np.array([], dtype=np.float32)
        if isinstance(vectors, list):
            vectors = np.array(vectors, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return np.zeros(len(vectors), dtype=np.float32)
        q = query_vec / query_norm
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normalized = vectors / norms
        similarities = normalized @ q
        return similarities.astype(np.float32)

    @staticmethod
    def to_bytes(vec: np.ndarray) -> bytes:
        arr = vec.astype(np.float32)
        return arr.tobytes()

    @staticmethod
    def from_bytes(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32).copy()
