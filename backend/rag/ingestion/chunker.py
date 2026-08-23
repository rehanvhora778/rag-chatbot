"""Chunking — cutting a page into pieces small enough to embed.

An embedding is a single vector for a whole passage, so a passage covering five
topics averages into a vague vector that matches nothing well. Chunks are
therefore kept small (~900 characters) and topic-coherent: the text is split on
blank lines first, so a heading, paragraph or bullet list is never cut in half
unless that single block is itself bigger than the chunk size.

Consecutive chunks overlap by RAG_CHUNK_OVERLAP characters, so a sentence that
straddles a boundary still appears whole in one of them.

Each page is chunked separately (see chunk_pages), which is what lets every
chunk — and therefore every answer — carry the exact page it came from.
"""
import logging
import re
import unicodedata
from typing import Any, Dict, List

from django.conf import settings

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Normalize unicode, repair line-break hyphenation, and strip corrupted/
    non-printable characters while preserving paragraph structure."""
    if not text:
        return ""

    # Canonical unicode form (also flattens ligatures like ﬁ -> fi)
    text = unicodedata.normalize("NFKC", text)

    # Normalize newlines
    text = re.sub(r"\r\n?", "\n", text)

    # Repair words split across a line break: "exam-\nple" -> "example"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Drop control/format characters (zero-width, soft hyphen, NULs, ...) but
    # keep newlines and tabs. Category starting with "C" == "other/control".
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or not unicodedata.category(ch).startswith("C")
    )

    # Collapse runs of spaces/tabs, trim each line
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))

    # Collapse 3+ blank lines into a single paragraph break
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _split_blocks(text: str) -> List[str]:
    """Split cleaned text into structural blocks (paragraphs, headings, lists).

    Blocks are separated by blank lines, so a bullet list written with single
    newlines stays together as one block and is never broken mid-list.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text)]
    return [b for b in blocks if b]


def _overlap_tail(text: str, overlap: int) -> str:
    """Return the trailing `overlap` characters of `text`, trimmed to start at a
    word boundary so the carried-over context reads cleanly."""
    if overlap <= 0 or not text:
        return ""
    if len(text) <= overlap:
        return text
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1:] if space != -1 else tail


def _split_large_block(block: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Split a single oversized block (bigger than chunk_size) on sentence
    boundaries, falling back to a hard character split for runaway sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", block)
    pieces: List[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > chunk_size:
            if current.strip():
                pieces.append(current.strip())
                current = ""
            step = max(1, chunk_size - chunk_overlap)
            for i in range(0, len(sentence), step):
                pieces.append(sentence[i:i + chunk_size].strip())
            continue

        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= chunk_size:
            current += " " + sentence
        else:
            pieces.append(current.strip())
            tail = _overlap_tail(pieces[-1], chunk_overlap)
            current = (tail + " " + sentence).strip() if tail else sentence

    if current.strip():
        pieces.append(current.strip())
    return pieces


def split_text_into_chunks(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[Dict[str, Any]]:
    """Split text into overlapping, structure-aware character chunks.

    Returns a list of {content, start_char, end_char, word_count}.
    """
    chunk_size    = chunk_size    or settings.RAG_CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

    cleaned = clean_text(text)
    if not cleaned:
        return []

    blocks = _split_blocks(cleaned)
    raw_chunks: List[str] = []
    current = ""

    for block in blocks:
        # A block larger than the chunk size is split on its own.
        if len(block) > chunk_size:
            if current.strip():
                raw_chunks.append(current.strip())
                current = ""
            raw_chunks.extend(_split_large_block(block, chunk_size, chunk_overlap))
            continue

        if not current:
            current = block
        elif len(current) + 2 + len(block) <= chunk_size:
            current += "\n\n" + block
        else:
            raw_chunks.append(current.strip())
            tail = _overlap_tail(raw_chunks[-1], chunk_overlap)
            current = (tail + "\n\n" + block) if tail else block

    if current.strip():
        raw_chunks.append(current.strip())

    # Attach character offsets (best-effort; used only for display/citations).
    chunks: List[Dict[str, Any]] = []
    search_from = 0
    for content in raw_chunks:
        if not content:
            continue
        probe = content[:40]
        start = cleaned.find(probe, search_from)
        if start == -1:
            start = cleaned.find(probe)
        if start == -1:
            start = search_from
        end = start + len(content)
        search_from = max(search_from, end - chunk_overlap)
        chunks.append({
            'content': content,
            'start_char': start,
            'end_char': end,
            'word_count': len(content.split()),
        })

    return chunks


def chunk_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Chunk every page, preserving page-number metadata and a global chunk id.

    Each returned chunk carries: chunk_index, page_number, content, start_char,
    end_char, word_count. Filename metadata is attached later in the processor.
    """
    all_chunks = []
    global_index = 0

    for page in pages:
        page_number = page['page_number']
        page_chunks = split_text_into_chunks(page['content'])

        for chunk in page_chunks:
            all_chunks.append({
                'chunk_index': global_index,
                'page_number': page_number,
                'content':     chunk['content'],
                'start_char':  chunk['start_char'],
                'end_char':    chunk['end_char'],
                'word_count':  chunk['word_count'],
            })
            global_index += 1

    logger.info("Chunked %d pages into %d chunks", len(pages), len(all_chunks))
    return all_chunks
