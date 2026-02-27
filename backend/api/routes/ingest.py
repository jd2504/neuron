"""POST /ingest — trigger PDF ingestion pipeline."""

import asyncio
import logging

from fastapi import APIRouter, Request

from backend.api.schemas import IngestRequest, IngestResponse
from backend.ingestion.chunker import chunk_pages
from backend.ingestion.pdf_extractor import extract_pdf
from backend.retrieval.hybrid_search import build_bm25_index
from backend.retrieval.vector_store import upsert_chunks

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_ingestion(pdf_path: str) -> tuple[int, str]:
    """Synchronous ingestion pipeline — runs in a thread."""
    logger.info("Starting ingestion for: %s", pdf_path)

    # Extract
    pages = extract_pdf(pdf_path)
    if not pages:
        return 0, "unknown"

    book = pages[0].book_title

    # Chunk
    chunks = chunk_pages(pages)
    logger.info("Created %d chunks for %s", len(chunks), book)

    # Upsert to Chroma
    upserted = upsert_chunks(chunks)
    logger.info("Upserted %d chunks to Chroma", upserted)

    # Rebuild BM25
    build_bm25_index()

    return upserted, book


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, request: Request):
    """Ingest a PDF through the full pipeline.

    Runs extraction → chunking → Chroma upsert → BM25 rebuild
    in a background thread to keep the event loop responsive.
    """
    chunks_created, book = await asyncio.to_thread(_run_ingestion, req.pdf_path)
    return IngestResponse(chunks_created=chunks_created, book=book)
