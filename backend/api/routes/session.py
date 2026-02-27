"""Session management routes."""

from fastapi import APIRouter, HTTPException, Request

from backend.api.schemas import SessionStats

router = APIRouter()


@router.get("/session/{session_id}")
async def get_session(session_id: str, request: Request):
    """Retrieve full session data."""
    session_mgr = request.app.state.session_manager
    session = await session_mgr.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "mode": session.mode,
        "message_count": len(session.history),
        "history": [
            {"role": m.role, "content": m.content} for m in session.history
        ],
        "topics_covered": session.topics_covered,
        "quiz_score": session.quiz_score,
        "created_at": session.created_at,
        "last_active": session.last_active,
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a session."""
    session_mgr = request.app.state.session_manager
    deleted = await session_mgr.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}
