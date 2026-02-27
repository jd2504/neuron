# Hebbot: Cognitive Neuroscience Study Assistant
## Architecture Document for Claude Code

---

## Project Overview

A RAG-powered conversational study assistant for graduate-level cognitive neuroscience,
with an Emacs-native UI backed by a local Python API server. The system ingests neuroscience
textbook PDFs, indexes them into a local vector store, and exposes a conversational interface
through Emacs buffers powered by an LLM API (Gemini by default, with Claude as a drop-in alternative).

### Source Textbooks

The system is built around three graduate-level neuroscience textbooks stored in `texts/`:

1. **Gazzaniga et al.** — *Cognitive Neuroscience: The Biology of the Mind*
2. **Purves et al.** — *Neuroscience*
3. **Kandel et al.** — *Principles of Neural Science* (5th ed.)

These provide complementary coverage: Gazzaniga focuses on cognitive systems,
Purves on foundational neurobiology, and Kandel on cellular/molecular mechanisms
through systems neuroscience. Cross-textbook synthesis is a core feature.

---

## Repository Structure

```
hebbot/
│
├── CLAUDE.md                          # Claude Code project instructions (see below)
│
├── backend/                           # Python FastAPI server
│   ├── main.py                        # FastAPI app entrypoint
│   ├── config.py                      # Settings (paths, model names, ports)
│   ├── requirements.txt
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py           # pymupdf-based PDF text extraction
│   │   ├── chunker.py                 # Semantic chunking with metadata tagging
│   │   └── embedder.py                # Local embedding model (sentence-transformers)
│   │
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── vector_store.py            # Chroma DB wrapper (init, upsert, query)
│   │   ├── hybrid_search.py           # BM25 + vector search fusion
│   │   └── reranker.py                # Cross-encoder reranking of retrieved chunks
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── llm_client.py             # Provider-agnostic LLM interface (ABC)
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── gemini.py             # Google Gemini via google-genai SDK (default)
│   │   │   └── claude.py             # Anthropic Claude via anthropic SDK (opt-in)
│   │   ├── system_prompts.py          # Mode-specific system prompts
│   │   ├── session.py                 # Session state: history, weak areas, topic tracking
│   │   └── modes/
│   │       ├── explain.py             # Socratic explanation mode
│   │       ├── quiz.py                # Question generation and grading
│   │       ├── deep_dive.py           # Mechanism-level cross-textbook synthesis
│   │       └── misconception.py       # User belief critique mode
│   │
│   └── api/
│       ├── __init__.py
│       ├── routes/
│       │   ├── chat.py                # POST /chat — main conversation endpoint
│       │   ├── quiz.py                # POST /quiz/generate, POST /quiz/grade
│       │   ├── ingest.py              # POST /ingest — trigger PDF ingestion
│       │   └── session.py             # GET/DELETE /session — session management
│       └── schemas.py                 # Pydantic request/response models
│
├── emacs/                             # Elisp package
│   ├── hebbot.el                      # Main package entry point
│   ├── hebbot-api.el                  # HTTP client (request.el wrapper)
│   ├── hebbot-ui.el                   # Buffer management, rendering, keybinds
│   ├── hebbot-quiz.el                 # Quiz mode UI and scoring display
│   ├── hebbot-org.el                  # Org-mode integration (capture, org-drill export)
│   └── hebbot-transient.el            # Transient menu (Magit-style command palette)
│
├── texts/                             # Textbook PDFs (gitignored)
│   ├── cognitive-neuroscience-the-biology-of-the-mind_compress.pdf
│   ├── Neuroscience_by_Dale_Purves_et_al_eds_(...).pdf
│   └── Principles of Neural Science, Fifth - KANDEL.pdf
│
├── data/
│   ├── chroma_db/                     # Auto-created vector store (gitignored)
│   └── sessions/                      # Persisted session JSON files (gitignored)
│
├── scripts/
│   ├── ingest_all.sh                  # One-shot: ingest all PDFs in texts/
│   └── start_server.sh                # Start FastAPI with uvicorn
│
└── tests/
    ├── test_ingestion.py
    ├── test_retrieval.py
    └── test_agent.py
```

---

## CLAUDE.md (place in project root)

```markdown
# Claude Code Instructions — Hebbot

## Project Purpose
RAG-backed neuroscience study assistant with Emacs UI and FastAPI backend.

## Stack
- Python 3.11+, FastAPI, uvicorn
- Chroma (vector DB), sentence-transformers (embeddings), pymupdf (PDF parsing)
- rank_bm25 (keyword search), sentence-transformers cross-encoder (reranking)
- google-genai SDK (default LLM provider); anthropic SDK (optional alternative)
- Emacs Lisp (UI layer)

## Key Conventions
- All backend code lives in `backend/`
- All Elisp lives in `emacs/`
- Textbook PDFs live in `texts/` — never commit them
- Chroma DB and sessions are ephemeral — gitignored
- Use async FastAPI routes throughout
- Stream LLM responses using SSE (Server-Sent Events)
- Session state is stored server-side as JSON, keyed by session_id (UUID)
- System prompts are centralized in `agent/system_prompts.py` — never inline them

## Environment Variables (use .env)
LLM_PROVIDER=gemini                              # "gemini" (default) or "claude"
GOOGLE_API_KEY=                                  # required when LLM_PROVIDER=gemini
ANTHROPIC_API_KEY=                               # required when LLM_PROVIDER=claude
LLM_MODEL_LIGHT=gemini-2.0-flash                # quiz, simple explanations
LLM_MODEL_HEAVY=gemini-2.5-pro                  # deep dives, cross-textbook synthesis
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
CHROMA_PATH=./data/chroma_db
PDF_DIR=./texts
SERVER_PORT=8765

## Running Locally
```bash
cd backend && pip install -r requirements.txt
uvicorn main:app --port 8765 --reload
```

## Testing
Run pytest from project root. Tests mock the LLM provider and Chroma.
```
---

## Backend: Key Module Specs

### `ingestion/pdf_extractor.py`
```
Purpose: Extract text from PDFs preserving structure
Input: Path to PDF file
Output: List of dicts {text, page_num, section_heading, book_title, chapter}
Library: pymupdf (fitz)
Notes:
  - Detect section headings via font size heuristics
  - Flag pages that are majority images (figure-heavy pages)
  - Store figure captions separately for retrieval
  - Kandel (266MB) is figure-heavy — expect many flagged pages
  - Log extraction progress per-book (these are large files)
```

### `ingestion/chunker.py`
```
Purpose: Split extracted text into retrieval-ready chunks
Strategy: Sliding window, 600 tokens, 100 token overlap
Metadata per chunk: {book, chapter, section, page_range, chunk_id}
Notes:
  - Never split mid-sentence
  - Keep definition blocks together (detect via "is defined as", "refers to" patterns)
  - Tag chunks containing key neuroscience term lists for boosted retrieval
  - Expected output: ~30,000–50,000 chunks across all three textbooks
```

### `retrieval/hybrid_search.py`
```
Purpose: Fuse BM25 keyword search with vector similarity search
Algorithm: Reciprocal Rank Fusion (RRF)
Inputs: query string, top_k (default 8)
Output: Ranked list of chunks with scores
Notes:
  - BM25 is especially important for exact neuroscience terminology
    (e.g. "NMDA receptor", "V4 area", "place cells", "Brodmann area")
  - Vector search handles conceptual/paraphrase queries
  - Optional book_filter parameter to scope search to one textbook
```

### `agent/llm_client.py`
```
Purpose: Provider-agnostic LLM interface
Design: Abstract base class (ABC) with two concrete implementations

class LLMClient(ABC):
    async def generate(self, messages, system_prompt, stream=True) -> AsyncIterator[str]
    async def generate_json(self, messages, system_prompt, schema) -> dict
    def select_model(self, mode) -> str   # light vs heavy based on mode

Features common to both providers:
  - Streaming via async iterators (converted to SSE at the API layer)
  - Automatic model selection based on mode:
      light model → quiz, simple explain
      heavy model → deep dives, misconception checks
  - Token usage tracking per session

Provider instantiation (in config.py):
  LLM_PROVIDER env var selects the implementation at startup.
  Factory function: get_llm_client() -> LLMClient
```

### `agent/providers/gemini.py` (default)
```
Purpose: Google Gemini implementation via google-genai SDK
Models:
  - Light: gemini-2.0-flash  (fast, low cost)
  - Heavy: gemini-2.5-pro    (high capability, cross-textbook synthesis)
Auth: GOOGLE_API_KEY env var (GCP API key with Gemini access)
Notes:
  - Uses google.genai.Client for both streaming and structured output
  - generate_json uses response_mime_type="application/json" for quiz grading
  - Streaming via client.models.generate_content_stream()
```

### `agent/providers/claude.py` (opt-in)
```
Purpose: Anthropic Claude implementation via anthropic SDK
Models:
  - Light: claude-haiku-4-5-20251001
  - Heavy: claude-sonnet-4-6
Auth: ANTHROPIC_API_KEY env var
Notes:
  - Uses anthropic.AsyncAnthropic for streaming
  - Prompt caching for system prompts (saves ~70% on repeated calls)
  - To switch: set LLM_PROVIDER=claude and ANTHROPIC_API_KEY in .env
```

### `agent/session.py`
```
Purpose: Track learning state across turns
Session object:
  {
    session_id: UUID,
    history: [...messages],
    mode: "explain" | "quiz" | "deep_dive" | "misconception",
    topics_covered: [...],
    weak_areas: {topic: miss_count},
    quiz_score: {correct: int, total: int},
    created_at: timestamp,
    last_active: timestamp
  }
Persistence: JSON file at data/sessions/{session_id}.json
```

### `api/schemas.py`
```python
# Core request/response shapes

class ChatRequest(BaseModel):
    session_id: str | None   # null = new session
    message: str
    mode: Literal["explain", "quiz", "deep_dive", "misconception"] = "explain"
    topic_filter: str | None  # optionally scope retrieval to a topic
    book_filter: str | None   # optionally scope retrieval to a specific textbook

class ChatResponse(BaseModel):
    session_id: str
    response: str             # streamed as SSE, final assembled here for non-stream
    sources: list[ChunkSource]
    mode: str
    session_stats: SessionStats

class QuizQuestion(BaseModel):
    question: str
    question_type: Literal["mcq", "free_recall", "fill_blank"]
    options: list[str] | None   # for MCQ
    correct_answer: str
    explanation: str
    source_chunk_id: str
```

---

## API Routes

```
POST /ingest
  Body: {pdf_path: str} or trigger full re-index
  Response: {chunks_created: int, books_indexed: list[str]}

POST /chat
  Body: ChatRequest
  Response: Server-Sent Events stream → ChatResponse on completion

POST /quiz/generate
  Body: {topic: str, n_questions: int, question_types: list[str], session_id: str}
  Response: list[QuizQuestion]

POST /quiz/grade
  Body: {question_id: str, user_answer: str, session_id: str}
  Response: {correct: bool, score: float, feedback: str, explanation: str}

GET /session/{session_id}
  Response: full Session object

DELETE /session/{session_id}
  Response: {deleted: true}

GET /health
  Response: {status: "ok", books_indexed: int, chunks_indexed: int}
```

---

## Emacs Layer: Key Module Specs

### `hebbot.el` (entry point)
```elisp
;; Responsibilities:
;; - Define hebbot-mode (derived from special-mode)
;; - Set server URL (default: http://localhost:8765)
;; - Load all submodules
;; - Provide autoloads for interactive commands:
;;   M-x hebbot               → open main chat buffer
;;   M-x hebbot-quiz          → start quiz session
;;   M-x hebbot-ingest        → trigger PDF ingestion
;;   M-x hebbot-menu          → open transient menu
```

### `hebbot-ui.el`
```elisp
;; Responsibilities:
;; - Manage *Hebbot* chat buffer
;; - Render streaming responses token-by-token into buffer
;; - Display source citations in a separate *Hebbot-Sources* buffer
;; - Keybindings within hebbot-mode:
;;   RET       → send input
;;   C-c C-m   → change mode (explain/quiz/deep_dive/misconception)
;;   C-c C-s   → show session stats
;;   C-c C-o   → export conversation to org-mode
;;   q         → bury buffer
```

### `hebbot-api.el`
```elisp
;; Responsibilities:
;; - HTTP calls using request.el
;; - SSE streaming parser (process filter on url-retrieve)
;; - Store session-id in buffer-local variable
;; - Handle errors gracefully with user-facing messages
```

### `hebbot-quiz.el`
```elisp
;; Responsibilities:
;; - Render quiz questions in dedicated *Hebbot-Quiz* buffer
;; - MCQ: present options with (a)(b)(c)(d), accept single keypress answer
;; - Free recall: open minibuffer for text input
;; - Display score overlay after each answer
;; - Accumulate session score, show summary at end
```

### `hebbot-org.el`
```elisp
;; Responsibilities:
;; - Capture key insights to org-mode file (configurable path)
;; - Export Q&A pairs as org-drill flashcards:
;;   * Question
;;     :PROPERTIES:
;;     :DRILL_CARD_TYPE: twosided
;;     :END:
;;     Answer text here
;; - Hook into org-capture-templates
```

### `hebbot-transient.el`
```elisp
;; Magit-style command menu triggered by M-x hebbot-menu
;; Layout:
;;
;;  Hebbot ─────────────────────────────
;;  Modes                  Actions
;;  e  Explain             i  Ingest PDFs
;;  q  Quiz                s  Session stats
;;  d  Deep Dive           r  Reset session
;;  m  Misconception       x  Export to Org
;;  ────────────────────────────────────
;;  b  Filter by book      ?  Help
;;  t  Set topic filter
```

---

## System Prompts (agent/system_prompts.py)

```python
BOOK_NAMES = {
    "gazzaniga": "Cognitive Neuroscience: The Biology of the Mind (Gazzaniga et al.)",
    "purves": "Neuroscience (Purves et al.)",
    "kandel": "Principles of Neural Science (Kandel et al.)",
}

BASE_CONTEXT = """
You are Hebbot, an expert tutor in cognitive neuroscience at the graduate level.
You have access to retrieved passages from the following textbooks: {book_list}.
Always ground your responses in the provided source material.
Cite the book and chapter when making specific claims.
If the retrieved context does not contain enough information, say so clearly
rather than speculating beyond what the sources support.
"""

EXPLAIN_MODE = BASE_CONTEXT + """
Mode: Explanation
Use Socratic questioning to deepen understanding. After explaining a concept,
ask one follow-up question to probe the student's comprehension.
Connect concepts to related mechanisms and brain regions where relevant.
"""

QUIZ_MODE = BASE_CONTEXT + """
Mode: Quiz
Generate {question_type} questions based on the retrieved content.
For MCQs: provide 4 options, exactly one correct, with plausible distractors.
For free recall: ask for mechanism-level explanation, not just definitions.
After grading, explain why the answer is correct and highlight common misconceptions.
"""

DEEP_DIVE_MODE = BASE_CONTEXT + """
Mode: Deep Dive
Provide a mechanistic, graduate-level explanation. Cover:
1. Cellular/molecular mechanisms where relevant
2. Systems-level context
3. Key experimental evidence from the literature
4. Open questions or areas of debate
Synthesize across textbooks when sources offer complementary perspectives.
"""

MISCONCEPTION_MODE = BASE_CONTEXT + """
Mode: Misconception Check
The student will state their understanding of a concept.
Identify what is correct, what is imprecise, and what is wrong.
Be direct but constructive. Suggest the correct framing.
"""
```

---

## Ingestion Pipeline (one-time setup)

```bash
# 1. Ensure textbook PDFs are in texts/
# 2. Run ingestion
./scripts/ingest_all.sh

# What this does:
# - Iterates all PDFs in texts/
# - Extracts text + metadata via pymupdf
# - Chunks with overlap, tags metadata
# - Embeds with local sentence-transformers model (no API cost)
# - Upserts into Chroma collection "hebbot_textbooks"
# - Logs per-book progress: chunks created, pages skipped (image-heavy)
# - Full ingestion of all three textbooks: expect ~15–30 minutes on first run
```

---

## Development Phases

**Phase 1 — Backend MVP**
- [ ] PDF ingestion pipeline (extractor → chunker → embedder → Chroma)
- [ ] Hybrid search (BM25 + vector + RRF)
- [ ] Basic `/chat` endpoint with Gemini integration (provider-agnostic LLM layer)
- [ ] Session management
- [ ] `/health` endpoint

**Phase 2 — Emacs UI**
- [ ] `hebbot.el` package skeleton
- [ ] Chat buffer with streaming display
- [ ] HTTP client layer
- [ ] Basic keybindings

**Phase 3 — Learning Features**
- [ ] Quiz generation and grading endpoints
- [ ] Emacs quiz UI
- [ ] Weak area tracking in session
- [ ] Org-mode export and org-drill integration

**Phase 4 — Polish**
- [ ] Transient menu
- [ ] Reranker (cross-encoder)
- [ ] Prompt caching for cost reduction
- [ ] Spaced repetition queue based on session history
- [ ] Figure/caption handling in ingestion

---

## Dependencies

### Python (backend/requirements.txt)
```
fastapi
uvicorn[standard]
google-genai          # Gemini SDK (default LLM provider)
anthropic             # Claude SDK (optional, for LLM_PROVIDER=claude)
pymupdf
sentence-transformers
chromadb
rank-bm25
python-dotenv
pydantic
sse-starlette        # Server-Sent Events for streaming
```

### Emacs packages (declare in package header)
```
request             ; HTTP client
markdown-mode       ; render LLM responses
transient           ; command menu (ships with modern Emacs)
org                 ; org-mode (ships with Emacs)
```

---

## Notes for Claude Code

- Start with Phase 1. Get the backend working and testable via curl before touching Elisp.
- The Elisp layer is deliberately thin — it's a display and input layer only. All logic lives in Python.
- Use `pytest` with `httpx.AsyncClient` for API route testing.
- Mock the LLM client in tests — never make live API calls in the test suite.
  Tests should mock at the `LLMClient` ABC level, not provider-specific classes.
- `LLM_PROVIDER` env var selects gemini or claude. `LLM_MODEL_LIGHT` / `LLM_MODEL_HEAVY` control
  model selection per mode. Defaults are Gemini models; override for Claude when switching.
- Chroma runs embedded (no separate server needed) — `chromadb.PersistentClient(path=CHROMA_PATH)`.
- The `texts/` directory is at the project root, not inside `data/`.
- The embedding model `all-mpnet-base-v2` (768 dim) is preferred over `all-MiniLM-L6-v2` (384 dim)
  for better handling of specialized neuroscience vocabulary.
- The `google-genai` package is the current Google Gen AI SDK (not the older `google-generativeai`).
- To switch to Claude: set `LLM_PROVIDER=claude`, `ANTHROPIC_API_KEY=sk-...`,
  `LLM_MODEL_LIGHT=claude-haiku-4-5-20251001`, `LLM_MODEL_HEAVY=claude-sonnet-4-6` in `.env`.
