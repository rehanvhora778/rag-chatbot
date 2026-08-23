"""Metrics for scoring a RAG pipeline.

Two kinds live here, and the difference matters more than any individual
number.

**Deterministic metrics** are computed from the retrieved set and the answer
text alone. They are free, instant, reproducible, and they cannot drift: a
baseline captured today is comparable with a run six months from now. Retrieval
recall, precision, MRR, refusal accuracy and citation validity are all of this
kind, and they are the ones this project's headline numbers are built on.

**Judged metrics** ask a language model whether an answer is faithful to its
context or correct against a reference. They correlate better with what a human
would say, and they cost an API call per case, vary between runs, and change
whenever the judge model is retired. They are opt-in for that reason.

Where a judge is unavailable, faithfulness and correctness fall back to lexical
proxies. A proxy is reported under its own name — ``faithfulness_lexical``
rather than ``faithfulness`` — because quietly substituting a weaker measure
for a stronger one under the same label is how an evaluation starts lying.
"""
import re
from typing import Any, Iterable, Optional

# Words carrying no topical content. Overlap metrics computed without removing
# them mostly measure how much English two strings have in common: an answer
# and a passage that share nothing but "the of and to a" would otherwise score
# as substantially grounded.
STOPWORDS = frozenset("""
a an and are as at be been but by for from had has have he her his i if in into is it
its of on or she that the their them then there these they this to was were what when
which who will with would you your our us we do does did not no nor so such than too
very can could should may might must shall about above after again against all also
any because before being below between both during each few further here how more most
other own same some only just over under once
""".split())

_WORD = re.compile(r"[a-z0-9]+(?:[.'-][a-z0-9]+)*")

# Page citations as the system prompt asks for them:
#   (Page 12)  (Pages 3, 7)  (report.pdf, Page 12)  (report.pdf, Pages 4, 9)
_CITATION = re.compile(r'\(([^()]*?)\bpages?\s+([\d,\s]+)\)', re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════
# Text helpers
# ══════════════════════════════════════════════════════════════════

def tokenize(text: str) -> list[str]:
    return _WORD.findall((text or '').lower())


def stem(word: str) -> str:
    """Strip the common English inflections, conservatively.

    Every overlap metric here compares sets of words, and without this a
    question asking about "refunds" shares nothing with a passage about a
    "refund" — the passage is then scored as irrelevant, the answer built from
    it as unfaithful, and a correct answer as incorrect. Measured on the sample
    corpus, that single mismatch was depressing context relevance by roughly a
    third.

    Deliberately not a real stemmer. Porter would need a dependency and would
    conflate words this project cares about keeping apart; the rules below cover
    plurals and the two most common verb endings and stop there. The guards
    (never shorten below four characters, never strip from a double 's') exist
    to avoid turning "business" into "busines" or "class" into "clas".
    """
    # Possessives first: "northwind's" and "northwind" are the same word, and
    # stripping only the trailing s would leave a stray apostrophe behind.
    if word.endswith("'s"):
        word = word[:-2]
    elif word.endswith("s'"):
        word = word[:-2]

    if len(word) <= 3:
        return word

    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    for suffix in ('sses', 'shes', 'ches', 'xes', 'zes'):
        if word.endswith(suffix):
            return word[:-2]
    if word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    if word.endswith('ing') and len(word) > 5:
        return _undouble(word[:-3])
    if word.endswith('ed') and len(word) > 4 and not word.endswith('eed'):
        return _undouble(word[:-2])

    return word


def _undouble(word: str) -> str:
    """Collapse the consonant doubled before -ing or -ed.

    English doubles a final consonant before those endings, so "shipping"
    reduces to "shipp" and would still not match "ship" — which is the exact
    pair this corpus contains. l, s and z are excluded because they are
    genuinely doubled in the base word ("fall", "pass", "buzz").
    """
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in 'lsz':
        return word[:-1]
    return word


def content_tokens(text: str) -> set[str]:
    """Stemmed, lower-cased tokens with stopwords removed."""
    return {
        stem(t) for t in tokenize(text)
        if t not in STOPWORDS and len(t) > 1
    }


def token_f1(prediction: str, reference: str) -> float:
    """Harmonic mean of token precision and recall against a reference answer.

    A blunt instrument, and deliberately so: it rewards an answer that uses the
    document's own vocabulary, which is exactly the behaviour the grounding
    prompt asks for. It cannot recognise a correct paraphrase, which is why it
    is reported as ``answer_correctness_lexical`` and why the judge exists.
    """
    predicted = content_tokens(prediction)
    expected = content_tokens(reference)

    if not predicted or not expected:
        # Two empty strings agree completely; one empty and one not do not.
        return 1.0 if not predicted and not expected else 0.0

    overlap = len(predicted & expected)
    if not overlap:
        return 0.0

    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


# ══════════════════════════════════════════════════════════════════
# Refusal
# ══════════════════════════════════════════════════════════════════

def is_refusal(answer: str) -> bool:
    """Did the assistant decline to answer?

    Matched against the canonical refusal sentence, which the pipeline emits
    verbatim both as a server-side fallback and via the prompt. A prefix
    comparison rather than equality because the model occasionally adds
    trailing whitespace or a newline, and an evaluation that scores those as
    "answered anyway" would report a grounding failure that did not happen.
    """
    from rag.prompts.grounding import REFUSAL_MESSAGE

    normalised = ' '.join((answer or '').split()).lower()
    canonical = ' '.join(REFUSAL_MESSAGE.split()).lower()
    if not normalised:
        return False
    return normalised.startswith(canonical[:80])


# ══════════════════════════════════════════════════════════════════
# Retrieval
# ══════════════════════════════════════════════════════════════════

def _retrieved_pages(chunks: Iterable[dict[str, Any]]) -> set[tuple[str, int]]:
    return {(c.get('document_name', ''), int(c.get('page_number', 0))) for c in chunks}


def _expected_pages(document_names: list[str], pages: list[int]) -> set[tuple[str, int]]:
    """Ground truth as (document, page) pairs.

    When only pages are given, the document is left blank and matching ignores
    it — useful for a single-document dataset, where naming the file in every
    case is noise.
    """
    if not pages:
        return set()
    if not document_names:
        return {('', int(p)) for p in pages}
    return {(name, int(p)) for name in document_names for p in pages}


def _matches(expected: tuple[str, int], retrieved: set[tuple[str, int]]) -> bool:
    name, page = expected
    if name:
        return (name, page) in retrieved
    return any(p == page for _, p in retrieved)


def retrieval_recall(chunks: list[dict[str, Any]], document_names: list[str],
                     pages: list[int]) -> Optional[float]:
    """Fraction of the pages that should have been found that were found.

    The single most important retrieval number: a passage that never reaches
    the model cannot be cited, and no amount of prompt engineering recovers it.
    Returns None when the case declares no ground truth, so cases without it are
    excluded from the average rather than silently counted as perfect.
    """
    expected = _expected_pages(document_names, pages)
    if not expected:
        return None

    retrieved = _retrieved_pages(chunks)
    hits = sum(1 for e in expected if _matches(e, retrieved))
    return hits / len(expected)


def retrieval_precision(chunks: list[dict[str, Any]], document_names: list[str],
                        pages: list[int]) -> Optional[float]:
    """Fraction of what was retrieved that should have been.

    Low precision is not automatically bad — extra context can help — but it
    costs tokens and dilutes attention, and a pipeline retrieving six pages to
    find one is a pipeline whose top_k is wrong.
    """
    expected = _expected_pages(document_names, pages)
    if not expected:
        return None

    retrieved = _retrieved_pages(chunks)
    if not retrieved:
        return 0.0

    if document_names:
        hits = sum(1 for pair in retrieved if pair in expected)
    else:
        wanted = {page for _, page in expected}
        hits = sum(1 for _, page in retrieved if page in wanted)

    return hits / len(retrieved)


def reciprocal_rank(chunks: list[dict[str, Any]], document_names: list[str],
                    pages: list[int]) -> Optional[float]:
    """1/rank of the first correct passage, 0 if none.

    Recall says whether the right passage arrived; this says whether it arrived
    *first*. The distinction matters because context is ordered and a model
    weights the top of it more heavily.
    """
    expected = _expected_pages(document_names, pages)
    if not expected:
        return None

    for position, chunk in enumerate(chunks, start=1):
        pair = (chunk.get('document_name', ''), int(chunk.get('page_number', 0)))
        if any(_matches(e, {pair}) for e in expected):
            return 1.0 / position
    return 0.0


# ══════════════════════════════════════════════════════════════════
# Grounding
# ══════════════════════════════════════════════════════════════════

def context_relevance(chunks: list[dict[str, Any]], question: str) -> float:
    """How much of the retrieved context has anything to do with the question.

    Measured as the share of retrieved passages sharing at least one content
    word with it. Crude, but it catches the failure that matters: a retriever
    returning six passages of which one is on-topic looks fine on recall and
    still hands the model five passages of noise to be misled by.
    """
    if not chunks:
        return 0.0

    asked = content_tokens(question)
    if not asked:
        return 0.0

    relevant = sum(1 for c in chunks if asked & content_tokens(c.get('content', '')))
    return relevant / len(chunks)


def faithfulness_lexical(answer: str, chunks: list[dict[str, Any]]) -> float:
    """Share of the answer's content words that appear in the retrieved context.

    A proxy for "did the model make this up". It is generous — a model can
    assemble a false claim entirely out of words present in the context — so it
    detects invention, not misstatement, and a low score is much more
    informative than a high one.

    A refusal scores 1.0: declining to answer is perfectly faithful, and
    scoring it as unfaithful would reward a pipeline that guesses.
    """
    if is_refusal(answer):
        return 1.0

    claimed = content_tokens(answer)
    if not claimed:
        return 0.0

    supported = set()
    for chunk in chunks:
        supported |= content_tokens(chunk.get('content', ''))

    if not supported:
        return 0.0
    return len(claimed & supported) / len(claimed)


def extract_cited_pages(answer: str) -> set[int]:
    """Every page number the answer claims to be citing."""
    pages: set[int] = set()
    for _prefix, numbers in _CITATION.findall(answer or ''):
        for part in numbers.split(','):
            part = part.strip()
            if part.isdigit():
                pages.add(int(part))
    return pages


def citation_validity(answer: str, chunks: list[dict[str, Any]]) -> Optional[float]:
    """Fraction of cited pages that were actually retrieved.

    This is the metric most specific to this project, and the one that catches
    the worst failure mode it has. The system's whole promise is that every
    fact carries the page it came from. A model that invents "(Page 47)" for a
    real fact produces an answer that looks *more* trustworthy than an
    uncited one and is impossible to check — which is worse than no citation.

    Returns None when the answer cites nothing, so uncited answers do not
    quietly score as perfectly cited.
    """
    cited = extract_cited_pages(answer)
    if not cited:
        return None

    available = {int(c.get('page_number', 0)) for c in chunks}
    return len(cited & available) / len(cited)


# ══════════════════════════════════════════════════════════════════
# Aggregation
# ══════════════════════════════════════════════════════════════════

def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    """Average, ignoring cases that did not produce a value.

    None means "this case had nothing to measure", which is different from
    zero. Treating the two the same would let a dataset without ground truth
    report a confident 0.0 for recall.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def percentile(values: list[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. p is a fraction, e.g. 0.95."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(p * len(ordered) + 0.5) - 1))
    return ordered[index]
