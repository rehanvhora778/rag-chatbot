"""The grounding prompt.

This is the most valuable text in the project. It is what makes the assistant
refuse a question the documents do not answer instead of answering it from the
model's own memory, and it is what produces the page citations the whole product
is built around. It has been tuned against real answers and is carried over
verbatim rather than rewritten — a "cleaner" prompt that refuses less often is a
regression, however much better it reads.

Expressed as a LangChain ``ChatPromptTemplate`` so it composes with the rest of
the pipeline and so the variables it needs are declared rather than implied by
whichever ``.format()`` call happens to build it.

The refusal sentence lives in exactly one place and is injected into the
template. The pipeline emits the same string as a server-side fallback when
retrieval returns nothing, and the evaluation harness detects a refusal by
matching it — three consumers that must agree byte for byte, which they do by
construction rather than by everyone remembering to update three files.
"""
from langchain_core.prompts import ChatPromptTemplate

# The exact sentence shown when the answer is not in the documents.
REFUSAL_MESSAGE = (
    'I could not find an answer to your question in the uploaded document(s). '
    'Please upload a document containing this information or ask a question '
    'related to the uploaded files.'
)

SYSTEM_PROMPT = """You are a document expert. Everything you know comes ONLY from the CONTEXT passages below, which were retrieved from the user's uploaded documents. Each passage is labelled with the page it came from, like [Page 12] or [report.pdf — Page 12].

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

USER_TEMPLATE = """CONTEXT (each passage is labelled with the page it came from — cite those pages):
{context}

CONVERSATION SO FAR:
{history}

QUESTION:
{question}"""


def build_rag_prompt(nonce: str = '') -> ChatPromptTemplate:
    """The chat prompt used for every grounded answer.

    ``partial`` binds the refusal sentence once, so callers supply only the
    three things that change per question and cannot accidentally pass a
    different refusal.

    When a `nonce` is given, the data-versus-instructions clause is appended,
    naming the exact delimiters the context is wrapped in. It is added rather
    than always present because the rule has to refer to a real, unforgeable
    boundary to mean anything — a clause about "the context" in the abstract is
    advice, while one naming a token the document could not have predicted is
    a rule.
    """
    system = SYSTEM_PROMPT.replace('{refusal}', REFUSAL_MESSAGE)

    if nonce:
        from rag.security.injection import boundary_instruction

        system = system + '\n' + boundary_instruction(nonce)

    return ChatPromptTemplate.from_messages([
        ('system', '{system}'),
        ('human', USER_TEMPLATE),
    ]).partial(system=system)


SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ('human', """Analyze the following document content and generate a comprehensive summary.

Include:
1. Main topics and themes
2. Key points and findings
3. Important details or data
4. Overall purpose of the document

DOCUMENT CONTENT:
{content}

SUMMARY:"""),
])


def format_history(history: list[dict]) -> str:
    """Render prior turns for the CONVERSATION SO FAR block."""
    if not history:
        return 'No previous conversation.'

    lines = []
    for message in history:
        speaker = 'User' if message.get('role') == 'user' else 'Assistant'
        lines.append(f'{speaker}: {message.get("content", "")}')
    return '\n'.join(lines)
