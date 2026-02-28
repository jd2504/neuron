"""POST /chat — main conversation endpoint with SSE streaming."""

import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.agent.llm_client import Message, ModelTier
from backend.agent.system_prompts import get_system_prompt
from backend.api.schemas import ChatRequest, ChatResponse, ChunkSource, SessionStats
from backend.retrieval.hybrid_search import RetrievedChunk, hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter()

# Mode → model tier mapping
_MODE_TIER: dict[str, ModelTier] = {
    "explain": "light",
    "quiz": "light",
    "deep_dive": "heavy",
    "misconception": "heavy",
}


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into the context block for the system prompt."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] ({chunk.book}, Ch.{chunk.chapter}, pp.{chunk.page_start}-{chunk.page_end})\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


def _chunks_to_sources(chunks: list[RetrievedChunk]) -> list[ChunkSource]:
    return [
        ChunkSource(
            chunk_id=c.chunk_id,
            book=c.book,
            chapter=c.chapter,
            section=c.section,
            page_start=c.page_start,
            page_end=c.page_end,
            score=c.score,
        )
        for c in chunks
    ]


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """Stream a chat response via SSE.

    SSE events:
      - event: token, data: <incremental text>
      - event: done,  data: <full ChatResponse JSON>
    """
    session_mgr = request.app.state.session_manager
    llm = request.app.state.llm_client

    # Get or create session
    session = None
    if req.session_id:
        session = await session_mgr.get(req.session_id)
    if session is None:
        session = await session_mgr.create(mode=req.mode)

    session.mode = req.mode

    # Hybrid search for relevant chunks
    try:
        chunks = hybrid_search(
            query=req.message,
            top_k=8,
            book_filter=req.book_filter,
        )
    except Exception:
        logger.exception("Hybrid search failed, proceeding without context")
        chunks = []

    # Build system prompt with retrieved context
    context_text = _build_context(chunks)
    system_prompt = get_system_prompt(
        mode=req.mode,
        book_filter=req.book_filter,
        retrieved_context=context_text,
    )

    # Add user message to history
    user_msg = Message(role="user", content=req.message)
    session_mgr.add_message(session, user_msg)

    # Determine model tier
    tier = _MODE_TIER.get(req.mode, "light")

    sources = _chunks_to_sources(chunks)
    stats = SessionStats(
        message_count=len(session.history),
        topics_covered=session.topics_covered,
        quiz_score=session.quiz_score,
    )

    async def event_generator():
        full_response = []
        try:
            async for token in llm.generate(
                messages=session.history,
                system_prompt=system_prompt,
                model_tier=tier,
            ):
                full_response.append(token)
                yield {"event": "token", "data": token}

            # Save assistant response to session
            assistant_text = "".join(full_response)
            assistant_msg = Message(role="assistant", content=assistant_text)
            session_mgr.add_message(session, assistant_msg)
            await session_mgr.save(session)

            # Send final done event with full response
            done_payload = ChatResponse(
                session_id=session.session_id,
                response=assistant_text,
                sources=sources,
                mode=req.mode,
                session_stats=stats,
            )
            yield {"event": "done", "data": done_payload.model_dump_json()}

        except Exception as e:
            logger.exception("Error during chat streaming")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())
