"""ChromaDB vector store wrapper — lazy singleton client."""

import logging

import chromadb

from backend.config import get_settings
from backend.ingestion.chunker import Chunk
from backend.ingestion.embedder import LocalEmbeddingFunction

logger = logging.getLogger(__name__)

COLLECTION_NAME = "hebbot_textbooks"
UPSERT_BATCH_SIZE = 500

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        path = str(settings.chroma_abs_path)
        logger.info("Initializing ChromaDB PersistentClient at %s", path)
        _client = chromadb.PersistentClient(path=path)
    return _client


def get_collection() -> chromadb.Collection:
    """Get or create the textbook collection with local embeddings."""
    global _collection
    if _collection is None:
        client = _get_client()
        ef = LocalEmbeddingFunction()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection '%s' ready — %d documents",
            COLLECTION_NAME,
            _collection.count(),
        )
    return _collection


def upsert_chunks(chunks: list[Chunk]) -> int:
    """Upsert chunks into Chroma in batches of 500. Returns count upserted."""
    collection = get_collection()
    total = 0

    for i in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[i : i + UPSERT_BATCH_SIZE]
        collection.upsert(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[
                {
                    "book": c.book,
                    "chapter": c.chapter,
                    "section": c.section,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "word_count": c.word_count,
                    "has_definition": c.has_definition,
                }
                for c in batch
            ],
        )
        total += len(batch)
        if total % 2000 == 0 or total == len(chunks):
            logger.info("Upserted %d / %d chunks", total, len(chunks))

    return total


def query_vectors(
    query: str, n_results: int = 20, where: dict | None = None
) -> dict:
    """Query the collection by text. Returns Chroma result dict."""
    collection = get_collection()
    kwargs: dict = {"query_texts": [query], "n_results": n_results}
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def get_all_documents() -> tuple[list[str], list[str], list[dict]]:
    """Return (ids, documents, metadatas) for all chunks in collection.

    Used to rebuild the BM25 index on startup.
    """
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return [], [], []

    result = collection.get(
        include=["documents", "metadatas"],
        limit=count,
    )
    return (
        result["ids"],
        result["documents"],
        result["metadatas"],
    )
