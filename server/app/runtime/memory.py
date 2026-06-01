"""FAISS-backed semantic memory per agent_id (shared across all conversations)."""
from __future__ import annotations

import json
import os

import numpy as np

_MEMORY_DIR = os.environ.get("MEMORY_DIR", "./data/memory")
_DIM = 384  # all-MiniLM-L6-v2 output dimension
_model = None


def _embed(texts: list[str]) -> "np.ndarray":
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model.encode(texts, convert_to_numpy=True).astype("float32")


def _safe(s: str) -> str:
    return s.replace("/", "_").replace(":", "_")


class SemanticMemory:
    def __init__(self, agent_id: str):
        import faiss

        base = os.path.join(_MEMORY_DIR, _safe(agent_id))
        self._index_path = base + ".faiss"
        self._texts_path = base + ".json"

        if os.path.exists(self._index_path):
            self._index = faiss.read_index(self._index_path)
            with open(self._texts_path) as f:
                self._texts: list[str] = json.load(f)
        else:
            self._index = faiss.IndexFlatL2(_DIM)
            self._texts = []

    def add(self, text: str) -> None:
        if not text.strip():
            return
        vec = _embed([text])
        self._index.add(vec)
        self._texts.append(text)
        self._save()

    def search(self, query: str, k: int = 4) -> list[str]:
        if self._index.ntotal == 0:
            return []
        vec = _embed([query])
        k = min(k, self._index.ntotal)
        _, indices = self._index.search(vec, k)
        return [self._texts[i] for i in indices[0] if 0 <= i < len(self._texts)]

    def _save(self) -> None:
        import faiss
        os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
        faiss.write_index(self._index, self._index_path)
        with open(self._texts_path, "w") as f:
            json.dump(self._texts, f)


def get_memory(agent_id: str) -> SemanticMemory:
    return SemanticMemory(agent_id)
