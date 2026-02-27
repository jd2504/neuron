"""Session management with JSON file persistence."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from backend.agent.llm_client import Message

logger = logging.getLogger(__name__)

MAX_HISTORY = 50


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    history: list[Message] = Field(default_factory=list)
    mode: str = "explain"
    topics_covered: list[str] = Field(default_factory=list)
    weak_areas: dict[str, int] = Field(default_factory=dict)
    quiz_score: dict[str, int] = Field(
        default_factory=lambda: {"correct": 0, "total": 0}
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_active: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SessionManager:
    """Manages session lifecycle with in-memory cache + JSON persistence."""

    def __init__(self, session_dir: Path):
        self._dir = session_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    async def get(self, session_id: str) -> Session | None:
        """Load a session from cache or disk."""
        if session_id in self._cache:
            return self._cache[session_id]

        path = self._path(session_id)
        if not path.exists():
            return None

        data = await asyncio.to_thread(path.read_text)
        session = Session.model_validate_json(data)
        self._cache[session_id] = session
        return session

    async def create(self, mode: str = "explain") -> Session:
        """Create a new session."""
        session = Session(mode=mode)
        self._cache[session.session_id] = session
        await self._save(session)
        return session

    async def save(self, session: Session) -> None:
        """Save session to cache and disk."""
        session.last_active = datetime.now(timezone.utc).isoformat()
        self._cache[session.session_id] = session
        await self._save(session)

    async def _save(self, session: Session) -> None:
        path = self._path(session.session_id)
        data = session.model_dump_json(indent=2)
        await asyncio.to_thread(path.write_text, data)

    async def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        self._cache.pop(session_id, None)
        path = self._path(session_id)
        if path.exists():
            await asyncio.to_thread(path.unlink)
            return True
        return False

    def add_message(self, session: Session, message: Message) -> None:
        """Append a message to session history, capping at MAX_HISTORY."""
        session.history.append(message)
        if len(session.history) > MAX_HISTORY:
            session.history = session.history[-MAX_HISTORY:]
