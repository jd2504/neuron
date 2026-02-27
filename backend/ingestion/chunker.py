"""Split extracted pages into retrieval-ready chunks with metadata."""

import re
import logging
from dataclasses import dataclass

from backend.ingestion.pdf_extractor import PageExtract

logger = logging.getLogger(__name__)

# Approximate tokens = words * 1.3.  Target ~600 tokens → ~460 words.
TARGET_WORDS = 460
OVERLAP_WORDS = 77

# Sentence boundary regex — split on . ! ? followed by whitespace/end
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Definition patterns to keep together
_DEFINITION_PATTERNS = re.compile(
    r"(?:is defined as|refers to|is the process of|is a type of|are called|known as)",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    book: str
    chapter: int
    section: str
    page_start: int
    page_end: int
    word_count: int
    has_definition: bool


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving sentence boundaries."""
    sentences = _SENTENCE_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


def _word_count(text: str) -> int:
    return len(text.split())


def chunk_pages(pages: list[PageExtract]) -> list[Chunk]:
    """Chunk a list of page extracts using a sliding sentence window.

    Groups pages by (book, chapter), then applies a sliding window of
    ~460 words with ~77 word overlap. Never splits mid-sentence.
    """
    # Group pages by book+chapter for contiguous chunking
    groups: dict[tuple[str, int], list[PageExtract]] = {}
    for page in pages:
        if page.is_figure_heavy and _word_count(page.text) < 30:
            continue  # Skip near-empty figure pages
        key = (page.book_title, page.chapter)
        groups.setdefault(key, []).append(page)

    all_chunks: list[Chunk] = []

    for (book, chapter), group_pages in sorted(groups.items()):
        # Combine all sentences for this chapter
        sentences: list[tuple[str, int]] = []  # (sentence, page_num)
        for page in group_pages:
            for sent in _split_sentences(page.text):
                sentences.append((sent, page.page_num))

        if not sentences:
            continue

        seq = 0
        i = 0
        while i < len(sentences):
            # Build a chunk of ~TARGET_WORDS
            chunk_sentences: list[str] = []
            chunk_pages: list[int] = []
            words = 0

            j = i
            while j < len(sentences) and words < TARGET_WORDS:
                sent, pnum = sentences[j]
                chunk_sentences.append(sent)
                chunk_pages.append(pnum)
                words += _word_count(sent)
                j += 1

            chunk_text = " ".join(chunk_sentences)

            # Determine section from last page in range
            section = ""
            for page in group_pages:
                if page.page_num in chunk_pages and page.section:
                    section = page.section

            chunk_id = f"{book}_{chapter:03d}_{seq:05d}"
            has_def = bool(_DEFINITION_PATTERNS.search(chunk_text))

            all_chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    book=book,
                    chapter=chapter,
                    section=section,
                    page_start=min(chunk_pages),
                    page_end=max(chunk_pages),
                    word_count=_word_count(chunk_text),
                    has_definition=has_def,
                )
            )
            seq += 1

            # Slide window: move forward by (target - overlap) words
            advance_words = 0
            advance_idx = i
            while advance_idx < j and advance_words < (TARGET_WORDS - OVERLAP_WORDS):
                advance_words += _word_count(sentences[advance_idx][0])
                advance_idx += 1
            i = advance_idx

            # Safety: always advance at least one sentence
            if i == (j - len(chunk_sentences)):
                i = j

    logger.info(
        "Chunking complete: %d chunks from %d pages",
        len(all_chunks),
        len(pages),
    )
    return all_chunks
