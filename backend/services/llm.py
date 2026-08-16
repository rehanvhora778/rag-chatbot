"""
Module 9: LLM Integration — Groq API.

Two jobs:
  * generate_rag_response()      answers a question from retrieved document text
  * read_image()                 OCRs a scanned PDF page rendered as an image
"""
import re
import time
import logging
from typing import List, Dict
from django.conf import settings

logger = logging.getLogger(__name__)

_groq_client = None


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        api_key = settings.GROQ_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in .env")
        _groq_client = Groq(api_key=api_key)
        logger.info("Groq client initialized (model: %s)", settings.GROQ_MODEL)
    return _groq_client


def _call_with_retry(messages, max_retries: int = 3) -> str:
    """Call Groq with exponential backoff on rate-limit errors.

    `messages` is a standard chat-completions message list, e.g.
    [{"role": "system", ...}, {"role": "user", ...}]. Temperature and output
    length are project-wide settings, so every answer behaves the same way.
    """
    import groq as groq_lib

    client = get_groq_client()
    delay = 5

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                max_tokens=settings.GROQ_MAX_OUTPUT_TOKENS,
                temperature=settings.GROQ_TEMPERATURE,
            )
            return response.choices[0].message.content
        except groq_lib.RateLimitError as exc:
            if attempt < max_retries:
                logger.warning("Groq rate limit (attempt %d/%d). Retrying in %ds...", attempt, max_retries, delay)
                time.sleep(delay)
                delay *= 2
            else:
                logger.error("Groq rate limit: all retries exhausted.")
                raise
        except Exception as exc:
            logger.error("Groq LLM error: %s", exc)
            raise


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    """Remove a reasoning model's thinking, keeping only its answer.

    Vision-capable models are often reasoning models that narrate their thought
    process in <think> blocks. That deliberation must never reach a document — it
    would be embedded and quoted back as if it were the file's own content.
    """
    text = _THINK_BLOCK.sub("", text).strip()
    if "<think>" in text.lower():
        # Thinking that never closed: the answer was cut off, so there is none.
        head = text.lower().split("<think>", 1)[0].strip()
        return head
    return text


def read_image(image_b64: str, prompt: str, mime_type: str = 'image/png',
               max_tokens: int = 600) -> str:
    """Send one image to the vision model and return its plain-text reading.

    Used to OCR scanned PDF pages that have no selectable text. Reasoning is
    switched off where the model supports it, and stripped defensively where it
    does not, so a model's thinking is never stored as document content.
    """
    import groq as groq_lib

    # Images are the most rate-limited calls in the app; ride out a 429 rather
    # than losing the page or frame entirely.
    client = get_groq_client().with_options(max_retries=5)
    messages = [{
        'role': 'user',
        'content': [
            {'type': 'image_url',
             'image_url': {'url': f"data:{mime_type};base64,{image_b64}"}},
            {'type': 'text', 'text': prompt},
        ],
    }]

    try:
        response = client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            reasoning_effort='none',
        )
    except groq_lib.BadRequestError as exc:
        # Not every vision model accepts reasoning_effort; retry plainly.
        if 'reasoning' not in str(exc).lower():
            raise
        response = client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=messages,
            max_tokens=max_tokens,
        )

    return _strip_reasoning(response.choices[0].message.content or '')


# The exact sentence shown to the user when the answer is not in the documents.
# Used both as an instruction to the model and as the server-side fallback, so
# the experience is identical whether the model or the pipeline produces it.
REFUSAL_MESSAGE = (
    "I could not find an answer to your question in the uploaded document(s). "
    "Please upload a document containing this information or ask a question "
    "related to the uploaded files."
)

RAG_SYSTEM_PROMPT = """You are a document expert. Everything you know comes ONLY from the CONTEXT passages below, which were retrieved from the user's uploaded documents. Each passage is labelled with the page it came from, like [Page 12] or [report.pdf — Page 12].

=== 1. DECIDE FIRST ===
Read every passage before writing anything, then pick one of three paths:
- The passages answer the question -> write the full answer.
- They answer only part of it -> answer that part, then add one final line: "The documents do not cover the rest of this question." Never guess to fill the gap.
- They do not answer it at all (empty, off-topic, or only a passing mention) -> reply with EXACTLY this sentence and nothing else, no heading, no greeting:
"{refusal}"

=== 2. GROUNDING RULES ===
- Use ONLY facts found in the CONTEXT. Never add outside knowledge — recognising a term is not permission to explain it from memory.
- Combine passages. The answer is often spread across several of them; merge those pieces into one complete response instead of answering from the first passage alone.
- When asked for "all", "every", "list", or "steps", extract EVERY matching item from EVERY passage — never stop at the first two.
- Prefer the exact wording of the document for definitions, names, numbers, and formulas. Do not round numbers or rename things.

=== 3. CITE THE PAGE (required) ===
- End every sentence or bullet that states a fact from the documents with its page in round brackets: (Page 12).
- A fact drawn from several pages cites them all: (Pages 3, 7).
- When the context contains more than one file name, put the file first: (report.pdf, Page 12).
- Cite the page shown in that passage's label — never invent or guess a page number.
- Apart from these page citations, never mention passages, chunks, retrieval, or similarity. Do not open with "According to the context" or "The document says" — just answer as the expert.

=== 4. SHAPE OF THE ANSWER ===
Match the format to the question:
- Simple factual question -> 1-3 direct sentences. Do not force headings onto a short answer.
- "List / name / what are the ..." -> a bullet list, one item per line, every item from the documents.
- "How to / steps / process" -> a numbered list in order.
- "Compare / difference / X vs Y" -> a Markdown table with one row per point of comparison.
- "Explain / describe / why" -> a short direct answer first, then the supporting detail underneath.
Only use a "## Details" heading when the answer is long enough to need sections. Bold the key terms, and never return a wall of text.

=== 5. FORMATTING ===
GitHub-Flavored Markdown. Fenced code blocks with a language tag (```python). Markdown tables for tabular data. `> ` blockquotes for a **Note:** or **Tip:** worth pulling out.

=== 6. TONE ===
Confident, precise, professional. No filler ("Okay", "Sure", "I think"). Short questions get short answers; complex ones get thorough ones."""

# Inject the canonical refusal sentence (kept as a token above so the long
# message lives in exactly one place).
RAG_SYSTEM_PROMPT = RAG_SYSTEM_PROMPT.replace("{refusal}", REFUSAL_MESSAGE)

RAG_USER_TEMPLATE = """CONTEXT (each passage is labelled with the page it came from — cite those pages):
{context}

CONVERSATION SO FAR:
{history}

QUESTION:
{question}"""

SUMMARY_PROMPT = """Analyze the following document content and generate a comprehensive summary.

Include:
1. Main topics and themes
2. Key points and findings
3. Important details or data
4. Overall purpose of the document

DOCUMENT CONTENT:
{content}

SUMMARY:"""


def generate_rag_response(
    question: str,
    context_chunks: List[Dict],
    conversation_history: List[Dict] = None,
) -> str:
    # Page numbers (and file names) travel with each reference so the model can
    # cite them inline, e.g. (Page 12) — see the HARD RULES in the system prompt.
    doc_names = {c.get('document_name') for c in context_chunks if c.get('document_name')}
    multi_doc = len(doc_names) > 1
    context_parts = []
    for chunk in context_chunks:
        page = chunk.get('page_number')
        name = chunk.get('document_name', '')
        if multi_doc and name and page:
            header = f"[{name} — Page {page}]"
        elif page:
            header = f"[Page {page}]"
        else:
            header = "[Source]"
        context_parts.append(f"{header}\n{chunk['content']}")
    context_text = "\n\n---\n\n".join(context_parts)

    history_parts = []
    if conversation_history:
        for msg in conversation_history:
            role = 'User' if msg['role'] == 'user' else 'Assistant'
            history_parts.append(f"{role}: {msg['content']}")
    history_text = "\n".join(history_parts) if history_parts else "No previous conversation."

    user_message = RAG_USER_TEMPLATE.format(
        context=context_text,
        history=history_text,
        question=question,
    )
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        return _call_with_retry(messages)
    except Exception as exc:
        logger.error("LLM RAG generation error: %s", exc)
        raise


def generate_document_summary(pages_content: List[Dict]) -> str:
    sample_pages = pages_content[:5]
    combined = "\n\n---PAGE BREAK---\n\n".join(
        f"Page {p['page_number']}:\n{p['content']}" for p in sample_pages
    )
    if len(combined) > 15000:
        combined = combined[:15000] + "\n... [truncated]"

    prompt = SUMMARY_PROMPT.format(content=combined)

    try:
        return _call_with_retry([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.error("LLM summarization error: %s", exc)
        raise
