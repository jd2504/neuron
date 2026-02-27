"""Pydantic request/response models for the API."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None  # null = new session
    message: str
    mode: Literal["explain", "quiz", "deep_dive", "misconception"] = "explain"
    topic_filter: str | None = None
    book_filter: str | None = None


class ChunkSource(BaseModel):
    chunk_id: str
    book: str
    chapter: int
    section: str
    page_start: int
    page_end: int
    score: float


class SessionStats(BaseModel):
    message_count: int
    topics_covered: list[str]
    quiz_score: dict[str, int]


class ChatResponse(BaseModel):
    session_id: str
    response: str
    sources: list[ChunkSource]
    mode: str
    session_stats: SessionStats


class IngestRequest(BaseModel):
    pdf_path: str


class IngestResponse(BaseModel):
    chunks_created: int
    book: str


class HealthResponse(BaseModel):
    status: str = "ok"
    books_indexed: int = 0
    chunks_indexed: int = 0
