"""Tests for the rag/ package: types, providers, prompts and vector stores.

The claim this file exists to defend is that ``VECTOR_BACKEND`` can be changed
without changing what gets retrieved. Everything else here protects a smaller
invariant that is easy to break by accident and expensive to notice.
"""
import numpy as np
import pytest
from langchain_core.documents import Document

from rag import types
from rag.vectorstores.base import SearchHit, mmr_select


def make_document(page: int, text: str, score: float = 0.5,
                  name: str = 'policy.pdf', chunk_id: str = '') -> Document:
    return Document(
        page_content=text,
        metadata={
            types.CHUNK_ID: chunk_id or f'chunk-{page}',
            types.DOCUMENT_ID: 'doc-1',
            types.DOCUMENT_NAME: name,
            types.PAGE_NUMBER: page,
            types.CHUNK_INDEX: page - 1,
            types.SCORE: score,
        },
    )


# ══════════════════════════════════════════════════════════════════
# Type boundary
# ══════════════════════════════════════════════════════════════════

class TestTypeConversion:
    def test_chunk_to_document_and_back_is_lossless(self):
        """The conversion happens on every request in both directions.

        Anything dropped here is dropped from a citation — a page number lost
        in translation renders as "page None" under an otherwise good answer.
        """
        chunk = {
            'chunk_id': 'c1', 'document_id': 'd1', 'document_name': 'policy.pdf',
            'page_number': 4, 'chunk_index': 3, 'content': 'Refunds take 30 days.',
            'similarity_score': 0.87,
        }

        restored = types.document_to_chunk(types.chunk_to_document(chunk))

        assert restored == chunk

    def test_missing_fields_get_usable_defaults(self):
        """A chunk from an older row must not produce a crash or a blank citation."""
        restored = types.document_to_chunk(types.chunk_to_document({'content': 'text'}))

        assert restored['content'] == 'text'
        assert restored['page_number'] == 1
        assert restored['document_name'] == 'Unknown'
        assert restored['similarity_score'] == 0.0

    def test_identity_distinguishes_passages(self):
        a = make_document(1, 'first', chunk_id='c1')
        b = make_document(2, 'second', chunk_id='c2')

        assert types.identity(a) != types.identity(b)
        assert types.identity(a) == types.identity(make_document(1, 'first', chunk_id='c1'))

    def test_identity_falls_back_when_a_chunk_id_is_missing(self):
        """Hybrid fusion has to recognise the same passage from two retrievers.

        A result with no id must still get a stable key, or it is counted twice
        and its fused rank is wrong.
        """
        bare = Document(page_content='text', metadata={types.DOCUMENT_ID: 'd1'})

        assert types.identity(bare) == types.identity(
            Document(page_content='text', metadata={types.DOCUMENT_ID: 'd1'})
        )


class TestContextBudget:
    def test_passages_that_fit_are_all_kept(self):
        documents = [make_document(i, 'x' * 100) for i in range(1, 5)]

        assert len(types.truncate_to_budget(documents, 1000)) == 4

    def test_lowest_ranked_passages_are_dropped_first(self):
        documents = [make_document(i, 'x' * 100) for i in range(1, 6)]

        kept = types.truncate_to_budget(documents, 250)

        assert [d.metadata[types.PAGE_NUMBER] for d in kept] == [1, 2]

    def test_at_least_one_passage_always_survives(self):
        """A context of nothing turns every question into a refusal.

        That is a worse failure than an oversized prompt, so the budget yields.
        """
        documents = [make_document(1, 'x' * 10_000)]

        assert len(types.truncate_to_budget(documents, 100)) == 1

    def test_a_passage_is_never_cut_in_half(self):
        documents = [make_document(1, 'x' * 100), make_document(2, 'y' * 100)]

        kept = types.truncate_to_budget(documents, 150)

        assert all(len(d.page_content) == 100 for d in kept)


class TestPromptFormatting:
    def test_a_single_document_cites_pages_without_the_filename(self):
        rendered = types.format_for_prompt([make_document(4, 'Refunds take 30 days.')])

        assert '[Page 4]' in rendered
        assert 'policy.pdf' not in rendered

    def test_several_documents_get_the_filename_too(self):
        """Otherwise "(Page 4)" is ambiguous across files."""
        rendered = types.format_for_prompt([
            make_document(4, 'a', name='policy.pdf'),
            make_document(4, 'b', name='handbook.pdf'),
        ])

        assert '[policy.pdf — Page 4]' in rendered
        assert '[handbook.pdf — Page 4]' in rendered


# ══════════════════════════════════════════════════════════════════
# The refusal sentence — three consumers that must agree
# ══════════════════════════════════════════════════════════════════

class TestRefusalConsistency:
    def test_the_prompt_embeds_the_same_sentence_the_pipeline_emits(self):
        """The prompt tells the model to say it, the pipeline says it when
        retrieval is empty, and the evaluation harness detects a refusal by
        matching it. Three places, one string, or the harness silently reports
        every refusal as an answer."""
        from rag.prompts.grounding import REFUSAL_MESSAGE, build_rag_prompt

        rendered = build_rag_prompt().format_messages(
            context='none', history='none', question='q',
        )
        system = rendered[0].content

        assert REFUSAL_MESSAGE in system
        assert '{refusal}' not in system

    def test_the_legacy_import_path_is_the_same_object(self):
        from rag.prompts.grounding import REFUSAL_MESSAGE as canonical
        from services.llm import REFUSAL_MESSAGE as legacy

        assert legacy == canonical

    def test_the_metrics_recognise_it(self):
        from apps.evaluation import metrics
        from rag.prompts.grounding import REFUSAL_MESSAGE

        assert metrics.is_refusal(REFUSAL_MESSAGE) is True


# ══════════════════════════════════════════════════════════════════
# MMR
# ══════════════════════════════════════════════════════════════════

class TestMMR:
    def test_near_duplicates_are_not_all_selected(self):
        """Overlapping chunks mean the two best matches are often the same
        sentence twice. Without diversity the model gets one fact repeated
        rather than several."""
        same = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        different = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        hits = [
            SearchHit('a', 0.90, same),
            SearchHit('b', 0.89, same),        # near-duplicate of a
            SearchHit('c', 0.60, different),
        ]

        chosen = [h.chunk_id for h in mmr_select(hits, k=2, lambda_mult=0.5)]

        assert chosen[0] == 'a'
        assert chosen[1] == 'c'

    def test_lambda_one_is_pure_relevance(self):
        same = np.array([1.0, 0.0], dtype=np.float32)
        hits = [SearchHit('a', 0.9, same), SearchHit('b', 0.8, same),
                SearchHit('c', 0.7, same)]

        chosen = [h.chunk_id for h in mmr_select(hits, k=2, lambda_mult=1.0)]

        assert chosen == ['a', 'b']

    def test_hits_without_vectors_fall_back_to_relevance_order(self):
        hits = [SearchHit('a', 0.9), SearchHit('b', 0.8)]

        assert [h.chunk_id for h in mmr_select(hits, k=2, lambda_mult=0.5)] == ['a', 'b']


# ══════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════

class TestRegistry:
    def test_the_configured_vector_store_is_returned(self, settings):
        from rag.registry import get_vector_store, reset_providers

        settings.VECTOR_BACKEND = 'faiss'
        reset_providers()
        assert get_vector_store().name == 'faiss'

        settings.VECTOR_BACKEND = 'pgvector'
        reset_providers()
        assert get_vector_store().name == 'pgvector'
        reset_providers()

    def test_an_unknown_store_falls_back_rather_than_crashing(self, settings):
        """A typo must not take the process down, but it must be loud."""
        from rag.registry import get_vector_store, reset_providers

        settings.VECTOR_BACKEND = 'chroma'
        reset_providers()
        assert get_vector_store().name == 'faiss'
        reset_providers()

    def test_an_unknown_llm_provider_names_what_is_available(self, settings):
        """Unlike the vector store, this raises: silently answering with a
        different model than configured is not a recoverable state."""
        from rag.registry import UnknownProvider, get_llm, reset_providers

        settings.LLM_PROVIDER = 'anthropic'
        reset_providers()
        with pytest.raises(UnknownProvider, match='groq'):
            get_llm()
        reset_providers()

    def test_providers_are_cached(self, settings):
        from rag.registry import get_llm, reset_providers

        settings.LLM_PROVIDER = 'groq'
        reset_providers()
        assert get_llm() is get_llm()
        reset_providers()


# ══════════════════════════════════════════════════════════════════
# Provider conformance
# ══════════════════════════════════════════════════════════════════

class TestProviderConformance:
    def test_groq_satisfies_the_llm_protocol(self):
        from rag.llm.base import LLMProvider
        from rag.llm.groq_provider import GroqProvider

        assert isinstance(GroqProvider(api_key='not-used'), LLMProvider)

    def test_both_stores_satisfy_the_vector_store_protocol(self):
        from rag.vectorstores.base import VectorStore
        from rag.vectorstores.faiss_store import FAISSVectorStore
        from rag.vectorstores.pgvector_store import PgVectorStore

        assert isinstance(FAISSVectorStore(), VectorStore)
        assert isinstance(PgVectorStore(), VectorStore)

    def test_only_pgvector_claims_filter_support(self):
        """Asked rather than assumed, so a filter is never silently dropped."""
        from rag.vectorstores.faiss_store import FAISSVectorStore
        from rag.vectorstores.pgvector_store import PgVectorStore

        assert FAISSVectorStore().supports_filters() is False
        assert PgVectorStore().supports_filters() is True

    def test_usage_distinguishes_zero_from_unreported(self):
        """A provider that reports nothing must not look like one that used no
        tokens — the difference matters when the number is summed into a cost."""
        from rag.llm.base import Usage

        assert Usage.from_provider(None).total_tokens is None
        assert Usage.from_provider({'total_tokens': 0}).total_tokens == 0

    def test_a_length_finish_reason_is_reported_as_truncated(self):
        """A truncated answer usually loses its closing citations, which reads
        as a grounding failure when it is a token-budget one."""
        from rag.llm.base import LLMResponse

        assert LLMResponse('x', 'm', 'p', finish_reason='length').truncated is True
        assert LLMResponse('x', 'm', 'p', finish_reason='stop').truncated is False


class TestReasoningStripping:
    @pytest.mark.parametrize('raw,expected', [
        ('<think>plan</think>The answer.', 'The answer.'),
        ('<THINK>plan</THINK>The answer.', 'The answer.'),
        ('No reasoning here.', 'No reasoning here.'),
        ('<think>never closed', ''),
    ])
    def test_model_deliberation_never_reaches_the_answer(self, raw, expected):
        """A reasoning model's thinking must not be stored as document content
        or shown as an answer — it would be embedded and later quoted back as
        if it were the file's own text."""
        from rag.llm.groq_provider import strip_reasoning

        assert strip_reasoning(raw) == expected
