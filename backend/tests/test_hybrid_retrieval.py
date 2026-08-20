"""Tests for hybrid retrieval: fusion, the keyword query builder, and rewriting.

The fusion tests matter most. RRF is the piece that decides what the model
actually reads, it is four lines of arithmetic, and getting it subtly wrong
produces a pipeline that still works — just worse — which no other test would
catch.
"""
import pytest
from langchain_core.documents import Document

from rag.retrievers.fusion import deduplicate, reciprocal_rank_fusion
from rag.types import CHUNK_ID, DOCUMENT_ID, PAGE_NUMBER, RANKS, RETRIEVER, SCORE


def doc(chunk_id: str, page: int = 1, text: str = '') -> Document:
    return Document(
        page_content=text or f'passage {chunk_id}',
        metadata={CHUNK_ID: chunk_id, DOCUMENT_ID: 'd1', PAGE_NUMBER: page},
    )


def ids(documents: list[Document]) -> list[str]:
    return [d.metadata[CHUNK_ID] for d in documents]


# ══════════════════════════════════════════════════════════════════
# Reciprocal Rank Fusion
# ══════════════════════════════════════════════════════════════════

class TestReciprocalRankFusion:
    def test_a_passage_both_retrievers_rank_highly_wins(self):
        """The 'found by both' signal is most of what makes hybrid better.

        Here 'b' is second on both lists while 'a' and 'c' are first on one and
        absent from the other. Agreement should beat a single first place.
        """
        fused = reciprocal_rank_fusion({
            'vector': [doc('a'), doc('b')],
            'keyword': [doc('c'), doc('b')],
        }, k=60)

        assert ids(fused)[0] == 'b'

    def test_a_passage_only_one_retriever_found_still_survives(self):
        """The whole point of fusing rather than intersecting.

        An exact identifier appears only in the keyword list; a paraphrase only
        in the vector one. Requiring agreement would discard both.
        """
        fused = reciprocal_rank_fusion({
            'vector': [doc('a')],
            'keyword': [doc('b')],
        })

        assert set(ids(fused)) == {'a', 'b'}

    def test_rank_decides_not_score(self):
        """Cosine similarity and ts_rank are not comparable scales.

        RRF must use position only — if either retriever's score leaked into
        the fused score, an unbounded ts_rank could dominate the entire
        ordering.
        """
        strong = doc('a')
        strong.metadata[SCORE] = 0.99
        weak = doc('b')
        weak.metadata[SCORE] = 0.01

        # 'b' ranks first in both lists despite its tiny score.
        fused = reciprocal_rank_fusion({
            'vector': [weak, strong],
            'keyword': [weak, strong],
        })

        assert ids(fused)[0] == 'b'

    def test_the_fused_score_replaces_the_retriever_score(self):
        fused = reciprocal_rank_fusion({'vector': [doc('a')]}, k=60)

        # abs, not relative: the fused score is rounded to six decimal places
        # on the way out so it serialises cleanly into the citation payload,
        # and these values are small enough that a default relative tolerance
        # is tighter than that rounding.
        assert fused[0].metadata[SCORE] == pytest.approx(1 / 61, abs=1e-6)

    def test_which_retrievers_found_a_passage_is_recorded(self):
        """"Both agreed" versus "only keyword found it" is most of what makes
        a hybrid pipeline debuggable after a surprising answer."""
        fused = reciprocal_rank_fusion({
            'vector': [doc('a')],
            'keyword': [doc('a'), doc('b')],
        })

        by_id = {d.metadata[CHUNK_ID]: d for d in fused}
        assert by_id['a'].metadata[RETRIEVER] == 'keyword+vector'
        assert by_id['b'].metadata[RETRIEVER] == 'keyword'
        assert by_id['a'].metadata[RANKS] == {'vector': 1, 'keyword': 1}

    def test_a_smaller_k_sharpens_the_advantage_of_rank_one(self):
        """k flattens the gap between the top few positions. A small k makes
        first place decisive; a large one makes agreement matter more."""
        lists = {'vector': [doc('a'), doc('b')]}

        sharp = reciprocal_rank_fusion(lists, k=1)
        flat = reciprocal_rank_fusion(lists, k=1000)

        sharp_gap = sharp[0].metadata[SCORE] - sharp[1].metadata[SCORE]
        flat_gap = flat[0].metadata[SCORE] - flat[1].metadata[SCORE]
        assert sharp_gap > flat_gap

    def test_weights_shift_the_balance_between_retrievers(self):
        fused = reciprocal_rank_fusion(
            {'vector': [doc('a')], 'keyword': [doc('b')]},
            weights={'keyword': 5.0},
        )

        assert ids(fused)[0] == 'b'

    def test_an_empty_list_from_one_retriever_is_harmless(self):
        fused = reciprocal_rank_fusion({'vector': [doc('a')], 'keyword': []})

        assert ids(fused) == ['a']

    def test_no_results_at_all_fuses_to_nothing(self):
        assert reciprocal_rank_fusion({'vector': [], 'keyword': []}) == []

    def test_the_originals_are_not_mutated(self):
        """A caller comparing "what did the vector side return" against the
        fused list must not find both rewritten."""
        original = doc('a')
        original.metadata[SCORE] = 0.5

        reciprocal_rank_fusion({'vector': [original]})

        assert original.metadata[SCORE] == 0.5


class TestDeduplication:
    def test_repeated_passages_collapse_to_the_first(self):
        unique = deduplicate([doc('a'), doc('b'), doc('a')])

        assert ids(unique) == ['a', 'b']


# ══════════════════════════════════════════════════════════════════
# Keyword query building
# ══════════════════════════════════════════════════════════════════

class TestKeywordQueryBuilder:
    def test_noise_words_are_dropped(self):
        from rag.retrievers.keyword import _or_query

        built = _or_query('How long do I have to return a domestic order?')

        assert 'how' not in built.lower().split(' or ')
        assert 'return' in built
        assert 'domestic' in built

    def test_numbers_and_identifiers_are_kept_however_short(self):
        """"7.2" and "4471" are usually the most discriminating thing in a
        question that contains one — dropping them for length removes exactly
        the case this fallback exists for."""
        from rag.retrievers.keyword import _or_query

        built = _or_query('what does Revision 7.2 say about order 4471')

        assert '7.2' in built
        assert '4471' in built

    def test_a_single_significant_term_produces_nothing(self):
        """One term would already have matched the strict pass."""
        from rag.retrievers.keyword import _or_query

        assert _or_query('refunds') == ''
        assert _or_query('what is the refund') == ''

    def test_very_long_questions_are_capped(self):
        from rag.retrievers.keyword import _or_query

        built = _or_query(' '.join(f'term{i}' for i in range(40)))

        assert len(built.split(' OR ')) <= 12


# ══════════════════════════════════════════════════════════════════
# Query rewriting
# ══════════════════════════════════════════════════════════════════

class TestRewriteHeuristic:
    """The cheap check that decides whether to pay for an LLM call."""

    HISTORY = [
        {'role': 'user', 'content': 'What is the refund policy?'},
        {'role': 'assistant', 'content': 'Domestic orders: 30 days. (Page 2)'},
    ]

    def test_the_first_turn_is_never_rewritten(self):
        from rag.query.rewrite import needs_rewrite

        assert needs_rewrite('What is the refund policy?', []) is False

    @pytest.mark.parametrize('question', [
        'What about international purchases?',
        'And internationally?',
        'Why?',
        'Is that the same for gifts?',
        'What about it?',
    ])
    def test_short_or_referential_follow_ups_are_caught(self, question):
        from rag.query.rewrite import needs_rewrite

        assert needs_rewrite(question, self.HISTORY) is True

    def test_a_self_contained_question_skips_the_call(self):
        """A needless rewrite costs half a second on every turn."""
        from rag.query.rewrite import needs_rewrite

        question = ('What is the warranty period for registered products '
                    'purchased outside the United Kingdom?')

        assert needs_rewrite(question, self.HISTORY) is False


class TestRewriteCleaning:
    @pytest.mark.parametrize('raw,expected', [
        ('What are the refund terms?', 'What are the refund terms?'),
        ('"What are the refund terms?"', 'What are the refund terms?'),
        ('Rewritten question: What are the refund terms?',
         'What are the refund terms?'),
        ('What are the refund terms?\n\nI resolved "that" to refunds.',
         'What are the refund terms?'),
    ])
    def test_model_wrapping_is_stripped(self, raw, expected):
        from rag.query.rewrite import _clean

        assert _clean(raw) == expected


class TestRewritePlausibility:
    def test_an_answer_masquerading_as_a_rewrite_is_rejected(self):
        """The failure that matters.

        If the model answers instead of rewriting, that answer becomes the
        search query — retrieving passages similar to the model's own guess
        rather than to the question. That is a self-fulfilling retrieval, and
        exactly the ungrounded behaviour the system exists to prevent.
        """
        from rag.query.rewrite import _is_plausible

        original = 'What about international?'
        essay = ('International purchases have a 45 day return window measured '
                 'from delivery, and a restocking fee of 15% applies to opened '
                 'items, while unopened items are never charged one, and refunds '
                 'are issued to the original payment method within 5 to 10 days.')

        assert _is_plausible(essay, original) is False

    def test_an_empty_rewrite_is_rejected(self):
        from rag.query.rewrite import _is_plausible

        assert _is_plausible('', 'anything') is False

    def test_a_reasonable_expansion_is_accepted(self):
        from rag.query.rewrite import _is_plausible

        assert _is_plausible(
            'What are the refund terms for international purchases?',
            'What about international?',
        ) is True


class TestPreprocess:
    def test_whitespace_is_collapsed(self):
        from rag.query.rewrite import preprocess

        assert preprocess('  what   is\n the  policy? ') == 'what is the policy?'

    def test_identifiers_survive_untouched(self):
        """Lowercasing or stripping punctuation would turn "Section 8.2" into
        "section 82" — losing the very thing that made the question specific."""
        from rag.query.rewrite import preprocess

        assert preprocess('What is Section 8.2?') == 'What is Section 8.2?'


class TestRewriteDisabled:
    def test_nothing_happens_when_the_feature_is_off(self, settings):
        from rag.query.rewrite import rewrite_query

        settings.RAG_QUERY_REWRITE = False
        question, rewritten = rewrite_query('What about that?', [
            {'role': 'user', 'content': 'refunds?'},
            {'role': 'assistant', 'content': '30 days'},
        ])

        assert question == 'What about that?'
        assert rewritten is False
