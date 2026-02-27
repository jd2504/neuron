# Claude Code Instructions — Hebbot

## Project Purpose
RAG-backed neuroscience study assistant with Emacs UI and FastAPI backend.

## Stack
- Python 3.14, FastAPI, uvicorn
- Chroma (vector DB), sentence-transformers (embeddings), pymupdf (PDF parsing)
- rank_bm25 (keyword search)
- google-genai SDK (default LLM provider); anthropic SDK (optional alternative)
- Emacs Lisp (UI layer, Phase 2)

## Venv
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Key Conventions
- All backend code lives in `backend/`
- Textbook PDFs live in `texts/` — never commit them
- Chroma DB and sessions are ephemeral — gitignored under `data/`
- Use async FastAPI routes throughout
- Stream LLM responses using SSE (Server-Sent Events)
- Session state is stored server-side as JSON, keyed by session_id (UUID)
- System prompts are centralized in `agent/system_prompts.py` — never inline them
- Shared state (`llm_client`, `session_manager`, `settings`) on `app.state`
- BM25 index rebuilt in-memory on startup from Chroma data

## Environment Variables (use .env)
LLM_PROVIDER=gemini
GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
LLM_MODEL_LIGHT=gemini-2.0-flash
LLM_MODEL_HEAVY=gemini-2.5-pro
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
CHROMA_PATH=./data/chroma_db
PDF_DIR=./texts
SERVER_PORT=8765

## Running
```bash
source .venv/bin/activate
uvicorn backend.main:app --port 8765 --reload
```

## Testing
Run pytest from project root. Tests mock the LLM provider and Chroma.
