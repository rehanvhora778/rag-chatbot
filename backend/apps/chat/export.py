"""
Professional document-style PDF export.

Turns a chat session's question/answer pairs into a clean, GitHub/Notion-style
technical document — NOT a chat transcript. No usernames, timestamps, sources,
page references, or any RAG/retrieval metadata ever appear in the output. The
reader cannot tell the answer came from a RAG system.

Note: this is a separate, plain-text export path. The download button in the
chat header produces the dark, styled PDF instead (see exportPDF in ChatPage).

Pipeline:  Markdown  ->  HTML (python-markdown)  ->  styled PDF.
Rendering: WeasyPrint when available (best fidelity), otherwise xhtml2pdf — a
pure-Python engine with zero native dependencies that always works on Windows.
"""
import io
import logging
import re
from html import escape as _escape
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Markdown → HTML
# ════════════════════════════════════════════════════════════════════
def _markdown_to_html(md_text: str) -> str:
    import markdown

    text = md_text or ''

    # Render task-list checkboxes as glyph-safe boxes (no Unicode glyphs needed,
    # so they render correctly with the built-in PDF fonts).
    text = re.sub(r'(?im)^(\s*[-*+]\s+)\[x\]\s+', r'\1<span class="tick done">x</span> ', text)
    text = re.sub(r'(?m)^(\s*[-*+]\s+)\[ \]\s+',  r'\1<span class="tick"></span> ', text)

    extensions = [
        'markdown.extensions.tables',
        'markdown.extensions.fenced_code',
        'markdown.extensions.sane_lists',
        'markdown.extensions.attr_list',
        'markdown.extensions.def_list',
        'markdown.extensions.nl2br',
    ]
    extension_configs: Dict[str, Any] = {}

    # Syntax highlighting via Pygments (inline styles so it survives both engines).
    try:
        import pygments  # noqa: F401
        extensions.append('markdown.extensions.codehilite')
        extension_configs['markdown.extensions.codehilite'] = {
            'noclasses': True,
            'guess_lang': False,
            'pygments_style': 'friendly',
        }
    except Exception as exc:
        # Pygments missing — code blocks still render as monospace.
        logger.debug("Pygments unavailable, code blocks will not be highlighted: %s", exc)

    return markdown.markdown(
        text,
        extensions=extensions,
        extension_configs=extension_configs,
        output_format='html5',
    )


# ════════════════════════════════════════════════════════════════════
# Stylesheet — professional, GitHub/Notion-style document
# ════════════════════════════════════════════════════════════════════
BASE_CSS = """
* { box-sizing: border-box; }
body {
  font-family: Helvetica, "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt; line-height: 1.62; color: #1f2937;
}

h1.doc-title {
  font-size: 23pt; font-weight: bold; color: #0f172a;
  margin: 0 0 20px 0; padding-bottom: 9px;
  border-bottom: 1.5pt solid #6366f1;
  string-set: doctitle content();
}

/* Question highlight box */
.qa-question {
  background-color: #eef2ff;
  border: 0.5pt solid #c7d2fe; border-left: 3pt solid #6366f1;
  border-radius: 8px; padding: 12px 16px; margin: 4px 0 16px 0;
  page-break-inside: avoid;
}
.qa-label {
  font-size: 8pt; font-weight: bold; text-transform: uppercase;
  letter-spacing: 1.4px; color: #4f46e5; margin-bottom: 5px;
}
.qa-text { font-size: 12.5pt; font-weight: bold; color: #1e1b4b; line-height: 1.4; }

.qa-answer-label {
  font-size: 9pt; font-weight: bold; text-transform: uppercase; letter-spacing: 1.4px;
  color: #64748b; margin: 6px 0 8px 0;
}
.qa-divider { border: 0; border-top: 0.5pt solid #e5e7eb; margin: 28px 0; }

/* Answer body typography */
.qa-answer h1, .qa-answer h2, .qa-answer h3, .qa-answer h4 {
  color: #0f172a; font-weight: bold; margin: 17px 0 7px 0;
  -pdf-keep-with-next: true;
}
.qa-answer h1 { font-size: 16pt; }
.qa-answer h2 { font-size: 13.5pt; padding-bottom: 3px; border-bottom: 0.5pt solid #eceef1; }
.qa-answer h3 { font-size: 11.5pt; }
.qa-answer h4 { font-size: 10.5pt; }
.qa-answer p  { margin: 8px 0; }
.qa-answer ul, .qa-answer ol { margin: 8px 0; padding-left: 22px; }
.qa-answer li { margin: 4px 0; }
.qa-answer strong { font-weight: bold; color: #0f172a; }
.qa-answer em { font-style: italic; }
.qa-answer a { color: #4f46e5; text-decoration: underline; }
.qa-answer hr { border: 0; border-top: 0.5pt solid #e5e7eb; margin: 16px 0; }

blockquote {
  border-left: 3pt solid #6366f1; background-color: #f8fafc;
  margin: 12px 0; padding: 9px 15px; color: #475569;
}
blockquote p { margin: 3px 0; }

/* Inline code */
code {
  font-family: "Courier New", Courier, monospace; font-size: 0.88em;
  background-color: #eef1f4; color: #9d174d; padding: 1px 5px; border-radius: 4px;
}
/* Code blocks */
.codehilite, pre {
  background-color: #f6f8fa; border: 0.5pt solid #e1e4e8; border-radius: 6px;
  padding: 11px 13px; margin: 13px 0;
  font-family: "Courier New", Courier, monospace; font-size: 8.6pt; line-height: 1.5;
  color: #24292e; white-space: pre-wrap; word-wrap: break-word;
  page-break-inside: avoid;
}
.codehilite pre { margin: 0; padding: 0; border: 0; background: transparent; }
pre code, .codehilite code { background: transparent; color: inherit; padding: 0; font-size: 8.6pt; }

/* Tables */
table {
  width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 9.5pt;
  page-break-inside: avoid;
}
th {
  background-color: #1f2937; color: #ffffff; font-weight: bold; text-align: center;
  padding: 7px 9px; border: 0.5pt solid #cbd5e1;
}
td {
  padding: 6px 9px; border: 0.5pt solid #e5e7eb; text-align: left;
  vertical-align: top; color: #1f2937;
}
tbody tr:nth-child(even) td { background-color: #f9fafb; }

/* Task-list checkboxes */
.tick {
  display: inline-block; width: 9pt; height: 9pt; margin-right: 5px;
  border: 0.7pt solid #9ca3af; border-radius: 2px;
  text-align: center; line-height: 9pt; font-size: 7pt; color: transparent;
}
.tick.done { background-color: #10b981; border-color: #10b981; color: #ffffff; }
"""

# WeasyPrint: running header (document title) + page-number footer via margin boxes.
WEASY_PAGE_CSS = """
@page {
  size: A4 portrait;
  margin: 2.3cm 1.9cm 2cm 1.9cm;
  @top-center   { content: string(doctitle); color: #9ca3af; font-size: 8.5pt; }
  @bottom-center{ content: counter(page);    color: #9ca3af; font-size: 9pt; }
}
"""

# xhtml2pdf: static header/footer frames; page number via <pdf:pagenumber>.
PISA_PAGE_CSS = """
@page {
  size: a4 portrait;
  margin: 2.3cm 1.9cm 2cm 1.9cm;
  @frame header_frame { -pdf-frame-content: pdfHeader; top: 1cm;   left: 1.9cm; width: 17.2cm; height: 1cm; }
  @frame footer_frame { -pdf-frame-content: pdfFooter; bottom: 1cm; left: 1.9cm; width: 17.2cm; height: 1cm; }
}
#pdfHeader { text-align: center; color: #9ca3af; font-size: 8.5pt; }
#pdfFooter { text-align: center; color: #9ca3af; font-size: 9pt; }
"""

_WEASY_TEMPLATE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head>'
    '<body>{body}</body></html>'
)
_PISA_TEMPLATE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head>'
    '<body>{header}{footer}{body}</body></html>'
)


# ════════════════════════════════════════════════════════════════════
# Document assembly
# ════════════════════════════════════════════════════════════════════
def _build_body_html(doc_title: str, items: List[Tuple[str, str]]) -> str:
    parts = [f'<h1 class="doc-title">{_escape(doc_title)}</h1>']
    multi = len(items) > 1
    for i, (question, answer_md) in enumerate(items, 1):
        label = f"Question {i}" if multi else "Question"
        answer_html = _markdown_to_html(answer_md)
        parts.append(
            '<div class="qa-question">'
            f'<div class="qa-label">{label}</div>'
            f'<div class="qa-text">{_escape(question or "—")}</div>'
            '</div>'
        )
        parts.append('<div class="qa-answer-label">Answer</div>')
        parts.append(f'<div class="qa-answer">{answer_html}</div>')
        if multi and i < len(items):
            parts.append('<hr class="qa-divider"/>')
    return '\n'.join(parts)


def _render_weasyprint(body_html: str):
    try:
        from weasyprint import HTML
    except Exception as exc:  # native libs missing (common on Windows)
        logger.info("WeasyPrint unavailable (%s); using xhtml2pdf.", exc.__class__.__name__)
        return None
    try:
        html_doc = _WEASY_TEMPLATE.format(css=BASE_CSS + WEASY_PAGE_CSS, body=body_html)
        return HTML(string=html_doc).write_pdf()
    except Exception as exc:
        logger.warning("WeasyPrint render failed (%s); falling back to xhtml2pdf.", exc)
        return None


def _render_xhtml2pdf(doc_title: str, body_html: str) -> bytes:
    from xhtml2pdf import pisa

    header = f'<div id="pdfHeader">{_escape(doc_title)}</div>'
    footer = '<div id="pdfFooter">Page <pdf:pagenumber></div>'
    html_doc = _PISA_TEMPLATE.format(
        css=BASE_CSS + PISA_PAGE_CSS, header=header, footer=footer, body=body_html,
    )
    out = io.BytesIO()
    result = pisa.CreatePDF(src=html_doc, dest=out, encoding='utf-8')
    if result.err:
        logger.error("xhtml2pdf reported %d error(s) during PDF generation.", result.err)
    return out.getvalue()


def render_answer_pdf(doc_title: str, items: List[Tuple[str, str]]) -> bytes:
    """Render Q/A pairs into a professional document PDF (engine auto-selected)."""
    body = _build_body_html(doc_title, items)
    pdf = _render_weasyprint(body)
    if pdf:
        return pdf
    return _render_xhtml2pdf(doc_title, body)


# ════════════════════════════════════════════════════════════════════
# Pairing / titles / filenames
# ════════════════════════════════════════════════════════════════════
def _pair_messages(messages: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Collapse an alternating message stream into (question, answer) pairs."""
    items: List[Tuple[str, str]] = []
    pending_q = None
    for m in messages or []:
        role = m.get('role')
        content = (m.get('content') or '').strip()
        if role == 'user':
            pending_q = content
        elif role == 'assistant':
            items.append((pending_q if pending_q is not None else '', content))
            pending_q = None
    return items


def _clean_title(text: str) -> str:
    t = re.sub(r'\s+', ' ', (text or '').strip())
    return t[:120] if t else 'Document'


def _document_title(session_title: str, items: List[Tuple[str, str]]) -> str:
    # Single question → use the question itself; multiple → use the chat's title.
    if len(items) == 1 and items[0][0].strip():
        return _clean_title(items[0][0])
    return _clean_title(session_title)


def build_export_filename(session_title: str, messages: List[Dict[str, Any]]) -> str:
    """Generate a descriptive filename like 'What_is_FAISS.pdf'."""
    items = _pair_messages(messages)
    title = _document_title(session_title, items)
    slug = re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_')
    slug = re.sub(r'_+', '_', slug)[:60].strip('_') or 'Document'
    return f"{slug}.pdf"


# ════════════════════════════════════════════════════════════════════
# Public entry point (signature kept for backward compatibility — the
# username / document_names / timestamp arguments are intentionally ignored).
# ════════════════════════════════════════════════════════════════════
def export_chat_to_pdf(
    session_title: str,
    messages: List[Dict[str, Any]],
    username: str = None,
    document_names: List[str] = None,
    exported_at=None,
) -> bytes:
    items = _pair_messages(messages)
    if not items:
        items = [(_clean_title(session_title), "_No answer is available yet._")]
    doc_title = _document_title(session_title, items)
    return render_answer_pdf(doc_title, items)
