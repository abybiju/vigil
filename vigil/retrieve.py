"""Local, deterministic retrieval over the FAQ/policy corpus.

Default backend is TF-IDF (scikit-learn) + in-process cosine — zero model download,
deterministic, ideal for the small corpus. An optional fastembed backend is available
behind the same `Retriever` interface (`uv sync --extra semantic`, VIGIL_EMBEDDER=fastembed).

The corpus text is persisted in `faq_chunks` so retrieval is reproducible from the DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from . import config, db


@dataclass
class RetrievedChunk:
    content: str
    source_title: str | None
    source_url: str | None
    chunk_index: int
    score: float


@runtime_checkable
class Retriever(Protocol):
    def fit(self, chunks: list[dict]) -> "Retriever": ...
    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]: ...


def _top_k(chunks: list[dict], sims: np.ndarray, k: int) -> list[RetrievedChunk]:
    order = np.argsort(-sims)[:k]
    return [
        RetrievedChunk(
            content=chunks[i]["content"],
            source_title=chunks[i].get("source_title"),
            source_url=chunks[i].get("source_url"),
            chunk_index=int(chunks[i].get("chunk_index", i)),
            score=float(sims[i]),
        )
        for i in order
    ]


class TfidfRetriever:
    """L2-normalised TF-IDF vectors; cosine == dot product."""

    def __init__(self) -> None:
        self._chunks: list[dict] = []
        self._vectorizer = None
        self._matrix = None

    def fit(self, chunks: list[dict]) -> "TfidfRetriever":
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._chunks = list(chunks)
        texts = [c["content"] for c in self._chunks]
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform(texts) if texts else None
        return self

    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]:
        if self._matrix is None or not self._chunks:
            return []
        q = self._vectorizer.transform([query])
        sims = (self._matrix @ q.T).toarray().ravel()
        return _top_k(self._chunks, sims, k)


class FastEmbedRetriever:
    """Optional semantic backend (ONNX bge-small). Requires the `semantic` extra."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model = None
        self._chunks: list[dict] = []
        self._emb: np.ndarray | None = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as e:  # pragma: no cover - exercised only when extra missing
                raise RuntimeError(
                    "fastembed is not installed. Run `uv sync --extra semantic` or set VIGIL_EMBEDDER=tfidf."
                ) from e
            self._model = TextEmbedding(self._model_name)
        return self._model

    @staticmethod
    def _normalize(m: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.clip(norms, 1e-12, None)

    def fit(self, chunks: list[dict]) -> "FastEmbedRetriever":
        model = self._ensure_model()
        self._chunks = list(chunks)
        texts = [c["content"] for c in self._chunks]
        self._emb = self._normalize(np.array(list(model.embed(texts)))) if texts else None
        return self

    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]:
        if self._emb is None or not self._chunks:
            return []
        model = self._ensure_model()
        qv = self._normalize(np.array([next(iter(model.embed([query])))]))[0]
        sims = self._emb @ qv
        return _top_k(self._chunks, sims, k)


def _make_retriever() -> Retriever:
    return FastEmbedRetriever() if config.EMBEDDER == "fastembed" else TfidfRetriever()


def _chunk_text(text: str) -> list[str]:
    """Fallback splitter for corpus files that ship raw `content` instead of `chunks`."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def build_corpus(conn, files: list[str | Path]) -> int:
    """Read corpus JSON files, flatten to chunks, persist into faq_chunks. Returns count."""
    rows: list[dict] = []
    for f in files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        title = data.get("source_title")
        url = data.get("source_url")
        chunks = data.get("chunks") or _chunk_text(data.get("content", ""))
        for i, content in enumerate(chunks):
            rows.append(
                {"source_title": title, "source_url": url, "chunk_index": i, "content": content}
            )

    # Precompute + store vectors only for the semantic backend (TF-IDF refits cheaply on load).
    vectors: list[list[float] | None] = [None] * len(rows)
    if config.EMBEDDER == "fastembed" and rows:
        fe = FastEmbedRetriever()
        fe.fit(rows)
        if fe._emb is not None:
            vectors = [v.tolist() for v in fe._emb]

    for r, vec in zip(rows, vectors):
        db.insert(
            conn,
            "faq_chunks",
            {
                "id": db.new_id(),
                "source_title": r["source_title"],
                "source_url": r["source_url"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "vector": json.dumps(vec) if vec is not None else None,
            },
            commit=False,
        )
    conn.commit()
    return len(rows)


def load_retriever(conn) -> Retriever:
    """Build a fitted retriever from the persisted corpus."""
    rows = db.query(
        conn,
        "SELECT source_title, source_url, chunk_index, content FROM faq_chunks "
        "ORDER BY source_title, chunk_index",
    )
    chunks = [dict(r) for r in rows]
    return _make_retriever().fit(chunks)
