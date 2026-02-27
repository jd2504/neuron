"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.agent.llm_client import get_llm_client
from backend.agent.session import SessionManager
from backend.api.routes import chat, ingest, session
from backend.api.schemas import HealthResponse
from backend.config import get_settings
from backend.retrieval.hybrid_search import build_bm25_index
from backend.retrieval.vector_store import get_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    logger.info("Starting Hebbot with provider=%s", settings.llm_provider)

    # Initialize shared state
    app.state.settings = settings
    app.state.llm_client = get_llm_client(settings.llm_provider)
    app.state.session_manager = SessionManager(settings.session_abs_path)

    # Build BM25 index from existing Chroma data (if any)
    count = build_bm25_index()
    logger.info("BM25 index: %d documents at startup", count)

    yield

    logger.info("Shutting down Hebbot")


app = FastAPI(title="Hebbot", version="0.1.0", lifespan=lifespan)

# Register routers
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(session.router)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check with index stats."""
    try:
        collection = get_collection()
        count = collection.count()

        # Count distinct books
        if count > 0:
            result = collection.get(include=["metadatas"], limit=count)
            books = {m.get("book") for m in result["metadatas"] if m}
            books_indexed = len(books)
        else:
            books_indexed = 0

        return HealthResponse(
            status="ok",
            books_indexed=books_indexed,
            chunks_indexed=count,
        )
    except Exception as e:
        logger.exception("Health check error")
        return HealthResponse(status=f"error: {e}")
