"""Keyword retrieval over PostgreSQL full-text search.

This is the half a dense retriever is worst at. An embedding compresses a
passage into 384 numbers that capture what it is *about*, which is exactly why
it struggles with things that mean nothing in isolation: an order number, a
clause reference like "Section 8.2", a product code, an acronym the model never
saw during training, a surname. Those are the queries where a user knows
precisely what they are looking for, so retrieving something merely
topically-adjacent is at its most annoying.

Full-text search has the mirror-image weakness — it cannot tell that "refund
window" and "return period" are the same question — which is why neither is
used alone. Fusion is in fusion.py.

Requires PostgreSQL: the ranking comes from the ``content_tsv`` column and its
GIN index, both created in documents/0002_postgres_search_indexes and kept
current by a database trigger. There is no MongoDB equivalent here, which a
system check enforces rather than letting hybrid retrieval silently degrade to
vector-only.
"""
import logging
import re
from typing import Any, Optional

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from rag.types import chunks_to_documents

logger = logging.getLogger(__name__)

# 'english' matches the configuration the trigger indexes with. They must agree:
# a query stemmed one way against a column stemmed another silently matches
# nothing, which looks exactly like a document that does not contain the word.
SEARCH_CONFIG = 'english'


class KeywordRetriever(BaseRetriever):
    """PostgreSQL full-text search over one user's chunks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: int
    document_keys: list[str] = Field(default_factory=list)
    top_k: Optional[int] = None
    filters: dict[str, Any] = Field(default_factory=dict)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None,
    ) -> list[Document]:

        if not self.document_keys:
            return []

        text = (query or '').strip()
        if not text:
            return []

        limit = self.top_k or settings.RAG_KEYWORD_TOP_K

        # Two passes, strict then broad.
        #
        # websearch_to_tsquery combines terms with AND, so it is excellent for
        # what keyword search is uniquely good at — "restocking fee",
        # "Revision 7.2", an order number — and silent for an ordinary question.
        # "How long do I have to return a domestic order?" requires every one of
        # those words in a single passage and therefore matches nothing, which
        # would leave the keyword half contributing on almost no real queries.
        #
        # So if the strict pass finds nothing, the significant terms are re-run
        # joined by OR. Precision drops, but that is what fusion is for: RRF
        # only reads the rank, and a loose keyword list that ranks the right
        # passage third still pushes it up when the dense side agrees.
        rows = self._search(text, limit, strict=True)
        if not rows:
            broadened = _or_query(text)
            if broadened:
                rows = self._search(broadened, limit, strict=False)

        if not rows:
            logger.debug('Keyword search found nothing for: %s', text[:60])
            return []

        # ts_rank is unbounded and depends on term frequency, so it is not
        # comparable with a cosine similarity. It is carried through only to
        # preserve ordering — Reciprocal Rank Fusion uses the *rank*, never the
        # score, precisely so that two incomparable scales never have to be
        # normalised against each other.
        chunks = [
            {
                'chunk_id': str(row.pk),
                'document_id': str(row.document_id),
                'document_name': row.document.original_filename,
                'page_number': row.page_number,
                'chunk_index': row.chunk_index,
                'content': row.content,
                'similarity_score': float(row.rank),
            }
            for row in rows
        ]

        logger.info('Keyword search returned %d passage(s) for: %s',
                    len(chunks), text[:60])
        return chunks_to_documents(chunks)

    def _search(self, expression: str, limit: int, strict: bool):
        """Run one full-text pass and return the ranked rows."""
        from apps.documents.models import DocumentChunk
        from rag.vectorstores.pgvector_store import PgVectorStore

        # websearch_to_tsquery, never to_tsquery: the input is whatever a user
        # typed. to_tsquery treats it as an expression language and raises a
        # syntax error on an apostrophe, an ampersand or an unbalanced quote,
        # turning "what's the refund policy?" into a 500. websearch parses human
        # input, understands quoted phrases and the word OR, and never raises.
        search = SearchQuery(expression, config=SEARCH_CONFIG,
                             search_type='websearch')

        queryset = DocumentChunk.objects.filter(
            owner_id=self.user_id, content_tsv=search,
        )

        document_filter = PgVectorStore._document_filter(self.document_keys)
        if document_filter is not None:
            queryset = queryset.filter(document_filter)

        queryset = PgVectorStore._apply_filters(queryset, self.filters)

        return list(
            queryset
            .annotate(rank=SearchRank(F('content_tsv'), search))
            .select_related('document')
            .order_by('-rank')[:limit]
        )


# Words that carry no discriminating power in a keyword query. PostgreSQL drops
# its own stopwords when building the tsvector, but they have to be removed
# before the OR is assembled or the broadened query matches every passage that
# contains "the".
_NOISE = frozenset("""
a an and are as at be by can could do does for from had has have how i in into is it
its me my of on or our that the their them there these they this to was we were what
when where which who will with would you your about please tell give show
""".split())

_TERM = re.compile(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*")


def _or_query(text: str) -> str:
    """The significant terms of a question, joined by OR.

    Numbers and identifiers are kept whatever their length — "7.2" and "4471"
    are usually the most discriminating thing in a question that contains one,
    and dropping them for being short would remove the exact case this fallback
    is most useful for.
    """
    terms = []
    for token in _TERM.findall(text):
        lowered = token.lower()
        if lowered in _NOISE:
            continue
        if len(lowered) < 3 and not any(c.isdigit() for c in lowered):
            continue
        terms.append(token)

    # A single term would already have matched in the strict pass.
    if len(terms) < 2:
        return ''

    # Capped: a long question otherwise builds a query matching most of the
    # corpus, and the tail terms contribute nothing but planner work.
    return ' OR '.join(terms[:12])
