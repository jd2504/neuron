"""Hybrid search combining BM25 keyword search with vector similarity via RRF."""

import logging
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.retrieval import vector_store

logger = logging.getLogger(__name__)

# Module-level BM25 state — rebuilt on startup
_bm25: BM25Okapi | None = None
_bm25_ids: list[str] = []
_bm25_metadatas: list[dict] = []
_bm25_documents: list[str] = []

RRF_K = 60  # Reciprocal Rank Fusion constant


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    book: str
    chapter: int
    section: str
    page_start: int
    page_end: int
    score: float


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenization for BM25."""
    return re.findall(r"\w+", text.lower())


def build_bm25_index() -> int:
    """(Re)build the BM25 index from all documents in Chroma.

    Called at startup and after ingestion. Returns document count.
    """
    global _bm25, _bm25_ids, _bm25_metadatas, _bm25_documents

    ids, documents, metadatas = vector_store.get_all_documents()
    if not ids:
        _bm25 = None
        _bm25_ids = []
        _bm25_metadatas = []
        _bm25_documents = []
        logger.info("BM25 index: empty (no documents)")
        return 0

    tokenized = [_tokenize(doc) for doc in documents]
    _bm25 = BM25Okapi(tokenized)
    _bm25_ids = ids
    _bm25_metadatas = metadatas
    _bm25_documents = documents

    logger.info("BM25 index built: %d documents", len(ids))
    return len(ids)


def hybrid_search(
    query: str,
    top_k: int = 8,
    book_filter: str | None = None,
) -> list[RetrievedChunk]:
    """Run hybrid BM25 + vector search with RRF fusion.

    Returns up to top_k RetrievedChunk objects sorted by fused score.
    """
    # Vector search
    where = {"book": book_filter} if book_filter else None
    vec_results = vector_store.query_vectors(query, n_results=top_k * 3, where=where)

    vec_ids = vec_results["ids"][0] if vec_results["ids"] else []
    vec_docs = vec_results["documents"][0] if vec_results["documents"] else []
    vec_metas = vec_results["metadatas"][0] if vec_results["metadatas"] else []

    # BM25 search
    bm25_ranked: list[tuple[str, float, str, dict]] = []
    if _bm25 is not None and _bm25_ids:
        tokens = _tokenize(query)
        scores = _bm25.get_scores(tokens)

        # Get indices sorted by score descending
        ranked_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )

        for idx in ranked_indices[: top_k * 3]:
            if scores[idx] <= 0:
                break
            cid = _bm25_ids[idx]
            meta = _bm25_metadatas[idx]
            if book_filter and meta.get("book") != book_filter:
                continue
            bm25_ranked.append(
                (cid, scores[idx], _bm25_documents[idx], meta)
            )

    # RRF fusion
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, tuple[str, dict]] = {}

    for rank, cid in enumerate(vec_ids):
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (RRF_K + rank + 1)
        if cid not in doc_map:
            doc_map[cid] = (vec_docs[rank], vec_metas[rank])

    for rank, (cid, _score, doc, meta) in enumerate(bm25_ranked):
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (RRF_K + rank + 1)
        if cid not in doc_map:
            doc_map[cid] = (doc, meta)

    # Sort by fused score and return top_k
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    results: list[RetrievedChunk] = []
    for cid in sorted_ids[:top_k]:
        doc, meta = doc_map[cid]
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                text=doc,
                book=meta.get("book", ""),
                chapter=meta.get("chapter", 0),
                section=meta.get("section", ""),
                page_start=meta.get("page_start", 0),
                page_end=meta.get("page_end", 0),
                score=rrf_scores[cid],
            )
        )

    return results
