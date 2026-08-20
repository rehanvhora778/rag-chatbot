"""
Module 5: Text Extraction

Turns an uploaded PDF, DOCX or TXT file into a list of pages:
    [{'page_number': 1, 'content': '...', 'char_count': 123}, ...]

Every page keeps its own number so answers can cite the exact page a fact came
from. Scanned PDFs have no selectable text, so those pages are rendered to an
image and read by Groq Vision (OCR) instead.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _extract_pdf_tables(page) -> str:
    """Best-effort table extraction as GitHub-Flavored Markdown.

    Uses PyMuPDF's table finder when available; never raises — if anything goes
    wrong we simply return no tables and rely on the plain text extraction.
    """
    try:
        finder = page.find_tables()
        tables = getattr(finder, "tables", []) or []
    except Exception:
        return ""

    md_tables = []
    for table in tables:
        try:
            rows = table.extract()
        except Exception as exc:
            logger.debug("Table extraction failed on one table: %s", exc)
            continue
        # Keep only non-empty rows
        rows = [
            [("" if c is None else str(c).replace("\n", " ").strip()) for c in row]
            for row in rows if any(c not in (None, "") for c in row)
        ]
        if len(rows) < 2:
            continue
        header, *body = rows
        width = len(header)
        md = ["| " + " | ".join(header) + " |",
              "| " + " | ".join(["---"] * width) + " |"]
        for row in body:
            row = (row + [""] * width)[:width]
            md.append("| " + " | ".join(row) + " |")
        md_tables.append("\n".join(md))

    return "\n\n".join(md_tables)


def _extract_pdf_text_native(page) -> str:
    """Try multiple PyMuPDF extraction methods to get text from a page."""
    # Method 1: plain text
    text = page.get_text("text").strip()
    if text:
        return text

    # Method 2: text from blocks
    try:
        blocks = page.get_text("blocks")
        parts = [b[4].strip() for b in blocks if isinstance(b[4], str) and b[4].strip()]
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception as exc:
        logger.debug("Block text extraction failed, trying rawdict: %s", exc)

    # Method 3: raw dict (individual characters)
    try:
        raw = page.get_text("rawdict")
        chars = []
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars.append(span.get("text", ""))
                chars.append("\n")
        text = "".join(chars).strip()
        if text:
            return text
    except Exception as exc:
        logger.debug("Rawdict text extraction failed: %s", exc)

    return ""


def _render_page_png_b64(page) -> str:
    """Render a PDF page to a base64-encoded PNG (2x zoom for OCR quality).

    Kept separate from the OCR call because PyMuPDF page objects are NOT
    thread-safe: rendering must happen on the main thread, while the network
    OCR call (below) can safely fan out across a thread pool.
    """
    import base64

    import fitz

    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR quality
    pix = page.get_pixmap(matrix=mat)
    return base64.b64encode(pix.tobytes("png")).decode("utf-8")


def _ocr_image_b64(img_b64: str, page_num: int) -> str:
    """Extract text from a rendered page image using Groq Vision (Llama).

    Network-bound and thread-safe (shared httpx client), so this is what we
    parallelize across scanned pages.
    """
    try:
        from services.llm import read_image

        text = read_image(
            img_b64,
            "Extract all the text from this document page image. "
            "Return only the extracted text, preserving paragraphs. "
            "Do not add any commentary or descriptions.",
            max_tokens=2048,
        )
        logger.info("Groq Vision OCR extracted %d chars from page %d", len(text), page_num)
        return text
    except Exception as exc:
        logger.warning("Groq Vision OCR failed for page %d: %s", page_num, exc)
        return ""


def extract_text_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """Extract text page-by-page from a PDF file.
    Falls back to Groq Vision OCR for scanned/image-based pages.
    """
    import fitz  # PyMuPDF
    from django.conf import settings

    from services.chunker import clean_text

    pages = []
    scanned_pages = []
    empty_pages = 0

    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        for page_num in range(total_pages):
            page = doc[page_num]
            text = clean_text(_extract_pdf_text_native(page))

            # Table detection (find_tables) is costly per page, so it's opt-in via
            # PDF_EXTRACT_TABLES — enable it only for table-heavy documents.
            if settings.PDF_EXTRACT_TABLES:
                tables_md = _extract_pdf_tables(page)
                if tables_md:
                    text = (text + "\n\n" + tables_md).strip() if text else tables_md

            if text:
                pages.append({
                    'page_number': page_num + 1,
                    'content': text,
                    'char_count': len(text),
                })
            else:
                scanned_pages.append((page_num + 1, page))

        if scanned_pages:
            workers = max(1, settings.OCR_MAX_WORKERS)
            logger.info(
                "%d page(s) have no native text — Groq Vision OCR (%d parallel workers)",
                len(scanned_pages), workers,
            )
            from concurrent.futures import ThreadPoolExecutor

            # Render on the main thread (PyMuPDF isn't thread-safe), then OCR the
            # batch in parallel. Batching by worker count bounds peak memory.
            for start in range(0, len(scanned_pages), workers):
                batch = scanned_pages[start:start + workers]
                rendered = [(pn, _render_page_png_b64(pg)) for pn, pg in batch]
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(
                        pool.map(lambda r: (r[0], _ocr_image_b64(r[1], r[0])), rendered)
                    )
                for page_num, raw in results:
                    text = clean_text(raw)
                    if text:
                        pages.append({
                            'page_number': page_num,
                            'content': text,
                            'char_count': len(text),
                        })
                    else:
                        empty_pages += 1
                        # Add a placeholder so the page is still represented
                        pages.append({
                            'page_number': page_num,
                            'content': f"[Page {page_num}: Image-based content — text could not be extracted]",
                            'char_count': 50,
                        })

        # Sort by page number
        pages.sort(key=lambda p: p['page_number'])
        doc.close()
        logger.info(
            "PDF extracted: %d/%d page(s) with text from %s (%d empty/unreadable)",
            len(pages), total_pages, file_path, empty_pages,
        )
    except Exception as exc:
        logger.error("PDF extraction error for %s: %s", file_path, exc)
        raise

    return pages


def extract_text_from_docx(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from a DOCX file, grouping paragraphs into virtual pages."""
    from docx import Document

    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())

        page_size = 50
        pages = []
        for i in range(0, max(1, len(full_text)), page_size):
            chunk = full_text[i:i + page_size]
            content = '\n'.join(chunk)
            pages.append({
                'page_number': (i // page_size) + 1,
                'content': content,
                'char_count': len(content),
            })

        logger.info("DOCX extracted: %d virtual pages from %s", len(pages), file_path)
    except Exception as exc:
        logger.error("DOCX extraction error for %s: %s", file_path, exc)
        raise
    return pages


def extract_text_from_txt(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from a TXT file with automatic encoding detection."""
    try:
        import chardet
        raw = Path(file_path).read_bytes()
        detected = chardet.detect(raw)
        encoding = detected.get('encoding', 'utf-8') or 'utf-8'
        text = raw.decode(encoding, errors='replace')

        page_size = 2000
        pages = []
        lines = text.split('\n')
        current_page = []
        current_len = 0
        page_num = 1

        for line in lines:
            current_page.append(line)
            current_len += len(line)
            if current_len >= page_size:
                content = '\n'.join(current_page).strip()
                if content:
                    pages.append({
                        'page_number': page_num,
                        'content': content,
                        'char_count': len(content),
                    })
                    page_num += 1
                current_page = []
                current_len = 0

        if current_page:
            content = '\n'.join(current_page).strip()
            if content:
                pages.append({
                    'page_number': page_num,
                    'content': content,
                    'char_count': len(content),
                })

        logger.info("TXT extracted: %d virtual pages from %s", len(pages), file_path)
    except Exception as exc:
        logger.error("TXT extraction error for %s: %s", file_path, exc)
        raise
    return pages


def extract_text(file_path: str, file_type: str) -> List[Dict[str, Any]]:
    """Dispatch extraction based on file type."""
    extractors = {
        'pdf':  extract_text_from_pdf,
        'docx': extract_text_from_docx,
        'txt':  extract_text_from_txt,
    }
    extractor = extractors.get(file_type.lower())
    if not extractor:
        raise ValueError(f"Unsupported file type: {file_type}")
    return extractor(file_path)


def get_word_count(pages: List[Dict[str, Any]]) -> int:
    return sum(len(p['content'].split()) for p in pages)
