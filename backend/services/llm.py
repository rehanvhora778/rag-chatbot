"""
LLM Integration — uses Groq API (Llama 3.3 70B).
"""
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
    [{"role": "system", ...}, {"role": "user", ...}].
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


# The exact sentence shown to the user when the answer is not in the documents.
# Used both as an instruction to the model and as the server-side fallback, so
# the experience is identical whether the model or the pipeline produces it.
REFUSAL_MESSAGE = (
    "I could not find an answer to your question in the uploaded document(s). "
    "Please upload a document containing this information or ask a question "
    "related to the uploaded files."
)

RAG_SYSTEM_PROMPT = """You are an intelligent RAG assistant. Your entire knowledge comes ONLY from the retrieved document context provided below. Your highest priority is to answer the user's EXACT question completely — directly and FIRST — using that context.

=== DECISION PROCEDURE (critical — follow before writing anything) ===
  STEP 1 — Identify exactly what the user is asking.
  STEP 2 — Read ALL retrieved context chunks carefully. Decide: do they contain the information needed to answer THIS question? Merge information from multiple chunks whenever possible.
  STEP 3 — If NO (the context is empty, is about a different topic, or only mentions the subject in passing without really answering), reply with EXACTLY this sentence and nothing else — no heading, no greeting, no extra text:
  "{refusal}"
  STEP 4 — If the context covers the question only PARTIALLY: answer everything the context supports, then end with exactly this sentence: "The retrieved document context does not contain a complete answer." Never guess to fill the gaps.
  STEP 5 — If YES, write a complete answer using ONLY the facts in the CONTEXT.

Example of correct refusal:
  CONTEXT is about Python programming. QUESTION asks "What is ChatGPT?".
  -> Correct response (verbatim, nothing else): {refusal}

=== HARD RULES ===
- Use ONLY information present in the CONTEXT. Never invent facts, names, numbers, or APIs. NEVER use outside knowledge or training data — recognizing a term is NOT permission to answer it.
- Search ALL retrieved chunks before concluding information is unavailable, and merge findings from multiple chunks into one complete answer.
- If the user asks for "all", "every", "complete", or a "list": extract EVERY matching item from ALL chunks — never stop after finding only one or two.
- Cite page numbers when they are shown in the context, inline like (Page 12); when more than one document appears in the context, include the file name too, like (report.pdf, Page 12).
- Answer the request directly. NEVER begin with phrases like "According to the provided context...", "The document mentions...", or "Based on the retrieved information...". Apart from page citations, never mention chunks, retrieval, sources, or similarity — present everything as your own expert answer.

=== RESPONSE FORMAT (every answer — refusals excepted, they are the exact sentence alone) ===
## Answer
<The direct, complete answer to the user's request comes FIRST, before any explanation:>
- "List ..." → the complete list, as bullets.
- "Name ..." → all names.
- "Steps / how to ..." → all steps, as a numbered list.
- "Compare / difference / X vs Y" → a Markdown comparison table, never paragraphs.
- "Advantages / disadvantages" → all of them.
- Simple factual question → a short, direct answer — do not force extra structure.

## Additional Details (optional)
<Explanation, notes, examples, or observations — ONLY if they are supported by the document. Omit this section entirely when there is nothing document-backed to add.>

=== FORMATTING ===
Clean, professional GitHub-Flavored Markdown that is easy to scan:
- **Bold** important terms. Prefer bullet or numbered lists over dense paragraphs. NEVER return one large wall of text.
- Use Markdown tables whenever information is comparative or tabular (comparisons, pros/cons, features, specifications).
- For code, ALWAYS use fenced code blocks WITH a language tag (```python, ```javascript, ```sql, ...).
- Use `> ` blockquotes for callouts, starting them with **Tip:**, **Note:**, or **Warning:** when useful.

=== TONE ===
Confident, concise, and professional. Never use filler such as "Okay", "Sure", "Yeah", "I think", or "Maybe". Adapt the length to the question: short for simple questions, thorough for complex topics."""

# Inject the canonical refusal sentence (kept as a token above so the long
# message lives in exactly one place).
RAG_SYSTEM_PROMPT = RAG_SYSTEM_PROMPT.replace("{refusal}", REFUSAL_MESSAGE)

RAG_USER_TEMPLATE = """RETRIEVED CONTEXT (cite its page numbers inline; never mention the retrieval mechanism itself):
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
