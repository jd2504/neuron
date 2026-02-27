"""Application settings loaded from environment / .env file."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

import os

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseModel):
    # LLM provider
    llm_provider: str = Field(default="gemini")
    google_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    llm_model_light: str = Field(default="gemini-2.0-flash")
    llm_model_heavy: str = Field(default="gemini-2.5-pro")

    # Paths
    chroma_path: str = Field(default="./data/chroma_db")
    pdf_dir: str = Field(default="./texts")
    session_dir: str = Field(default="./data/sessions")
    embedding_model: str = Field(default="sentence-transformers/all-mpnet-base-v2")

    # Server
    server_port: int = Field(default=8765)

    @property
    def chroma_abs_path(self) -> Path:
        return (_PROJECT_ROOT / self.chroma_path).resolve()

    @property
    def pdf_abs_path(self) -> Path:
        return (_PROJECT_ROOT / self.pdf_dir).resolve()

    @property
    def session_abs_path(self) -> Path:
        return (_PROJECT_ROOT / self.session_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    """Build settings from env vars. Cached for the process lifetime."""
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model_light=os.getenv("LLM_MODEL_LIGHT", "gemini-2.0-flash"),
        llm_model_heavy=os.getenv("LLM_MODEL_HEAVY", "gemini-2.5-pro"),
        chroma_path=os.getenv("CHROMA_PATH", "./data/chroma_db"),
        pdf_dir=os.getenv("PDF_DIR", "./texts"),
        session_dir=os.getenv("SESSION_DIR", "./data/sessions"),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"
        ),
        server_port=int(os.getenv("SERVER_PORT", "8765")),
    )
