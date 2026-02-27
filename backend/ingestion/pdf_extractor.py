"""Extract text from textbook PDFs with structural metadata."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # pymupdf

logger = logging.getLogger(__name__)

# Map filename substrings to canonical book names
FILENAME_TO_BOOK: dict[str, str] = {
    "cognitive-neuroscience": "gazzaniga",
    "Purves": "purves",
    "Neuroscience_by_Dale_Purves": "purves",
    "KANDEL": "kandel",
    "Principles of Neural Science": "kandel",
}

HEADING_FONT_SIZE_THRESHOLD = 14.0


@dataclass
class PageExtract:
    text: str
    page_num: int
    book_title: str
    chapter: int
    section: str
    is_figure_heavy: bool


def _identify_book(filename: str) -> str:
    """Map a PDF filename to a canonical book name."""
    for substr, book in FILENAME_TO_BOOK.items():
        if substr in filename:
            return book
    return Path(filename).stem.lower()


def _detect_chapter(headings: list[str], current_chapter: int) -> int:
    """Try to detect chapter number from heading text."""
    import re

    for heading in headings:
        m = re.match(r"(?:chapter|ch\.?)\s*(\d+)", heading, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return current_chapter


def extract_pdf(pdf_path: str | Path) -> list[PageExtract]:
    """Extract text and metadata from a PDF file.

    Returns one PageExtract per page. Logs progress every 100 pages.
    """
    pdf_path = Path(pdf_path)
    book = _identify_book(pdf_path.name)
    logger.info("Starting extraction: %s (book=%s)", pdf_path.name, book)

    doc = fitz.open(str(pdf_path))
    pages: list[PageExtract] = []
    current_chapter = 0
    current_section = ""

    for i, page in enumerate(doc):
        # Extract text blocks with font info
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        page_text_parts: list[str] = []
        headings: list[str] = []
        text_char_count = 0
        image_block_count = 0

        for block in blocks:
            if block["type"] == 1:  # image block
                image_block_count += 1
                continue
            for line in block.get("lines", []):
                line_text = ""
                max_font_size = 0.0
                for span in line["spans"]:
                    line_text += span["text"]
                    text_char_count += len(span["text"])
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                line_text = line_text.strip()
                if not line_text:
                    continue
                if max_font_size > HEADING_FONT_SIZE_THRESHOLD:
                    headings.append(line_text)
                page_text_parts.append(line_text)

        # Update structural tracking
        current_chapter = _detect_chapter(headings, current_chapter)
        if headings:
            current_section = headings[-1]

        # Heuristic: page is figure-heavy if images dominate
        is_figure_heavy = (
            image_block_count > 2 and text_char_count < 200
        )

        full_text = "\n".join(page_text_parts)
        pages.append(
            PageExtract(
                text=full_text,
                page_num=i + 1,
                book_title=book,
                chapter=current_chapter,
                section=current_section,
                is_figure_heavy=is_figure_heavy,
            )
        )

        if (i + 1) % 100 == 0:
            logger.info(
                "  %s: extracted %d / %d pages", book, i + 1, len(doc)
            )

    doc.close()
    logger.info(
        "Finished %s: %d pages, %d figure-heavy pages skipped text",
        book,
        len(pages),
        sum(1 for p in pages if p.is_figure_heavy),
    )
    return pages
