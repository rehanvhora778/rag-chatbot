"""Tests for the evaluation metrics.

Every number the project quotes about itself is computed here, so a bug in this
module does not produce a wrong answer — it produces a wrong *belief* about how
good the answers are, which is worse, because it is the thing that decides
whether a change ships.

These are pure functions: no database, no network, no model.
"""
import pytest

from apps.evaluation import metrics


def chunk(page: int, content: str, document: str = 'policy.pdf') -> dict:
    return {'document_name': document, 'page_number': page, 'content': content}


# ══════════════════════════════════════════════════════════════════
# Tokenisation
# ══════════════════════════════════════════════════════════════════

class TestTokenisation:
    def test_stopwords_are_removed(self):
        assert metrics.content_tokens('the refund is in the policy') == {'refund', 'policy'}

    def test_case_and_punctuation_are_normalised(self):
        assert metrics.content_tokens('Refund, REFUNDS; refund.') == {'refund'}

    def test_singular_and_plural_are_the_same_token(self):
        """Without this, a question about "refunds" matches nothing in a
        passage about a "refund", and every overlap metric under-reports."""
        assert metrics.content_tokens('refunds') == metrics.content_tokens('refund')
        assert metrics.content_tokens('policies') == metrics.content_tokens('policy')

    def test_common_verb_endings_are_stripped(self):
        assert metrics.content_tokens('shipping') == metrics.content_tokens('ship')
        assert metrics.content_tokens('returned') == metrics.content_tokens('return')

    @pytest.mark.parametrize('word', ['business', 'class', 'address', 'status', 'analysis'])
    def test_words_ending_in_double_s_are_left_alone(self, word):
        """The guard that stops "business" becoming "busines"."""
        assert metrics.stem(word) == word

    def test_short_words_are_never_shortened(self):
        for word in ('is', 'as', 'gas', 'has'):
            assert metrics.stem(word) == word

    def test_hyphenated_words_stay_whole(self):
        assert 'thirty-day' in metrics.content_tokens('a thirty-day window')

    def test_possessives_reduce_to_the_bare_word(self):
        """So "Northwind's policy" and "Northwind policy" agree."""
        assert metrics.content_tokens("Northwind's") == metrics.content_tokens('Northwind')

    @pytest.mark.parametrize('inflected,base', [
        ('shipping', 'ship'),
        ('stopped', 'stop'),
        ('returned', 'return'),
        ('processed', 'process'),
    ])
    def test_doubled_consonants_are_collapsed(self, inflected, base):
        assert metrics.stem(inflected) == metrics.stem(base)

    @pytest.mark.parametrize('word', ['falling', 'passed'])
    def test_genuinely_doubled_letters_survive(self, word):
        """l, s and z are doubled in the base word, so undoubling them would
        turn "falling" into "fal"."""
        assert metrics.stem(word) in ('fall', 'pass')


class TestTokenF1:
    def test_identical_text_scores_one(self):
        assert metrics.token_f1('refunds within 30 days', 'refunds within 30 days') == 1.0

    def test_unrelated_text_scores_zero(self):
        assert metrics.token_f1('shipping costs money', 'warranty covers defects') == 0.0

    def test_partial_overlap_scores_between(self):
        score = metrics.token_f1(
            'Refunds are issued within 30 days.',
            'Domestic orders may be returned within 30 days of delivery.',
        )
        assert 0.0 < score < 1.0

    def test_padding_an_answer_lowers_precision(self):
        """Correct plus a page of waffle should score below correct alone.

        Otherwise the metric rewards verbosity, and a pipeline tuned against it
        learns to pad.
        """
        reference = 'The refund window is 30 days.'
        tight = metrics.token_f1('The refund window is 30 days.', reference)
        padded = metrics.token_f1(
            'The refund window is 30 days. Northwind also operates shipping, '
            'warranty, loyalty, privacy and support policies described elsewhere.',
            reference,
        )
        assert padded < tight

    def test_two_empty_strings_agree(self):
        assert metrics.token_f1('', '') == 1.0

    def test_one_empty_string_does_not(self):
        assert metrics.token_f1('', 'something') == 0.0
        assert metrics.token_f1('something', '') == 0.0


# ══════════════════════════════════════════════════════════════════
# Refusal
# ══════════════════════════════════════════════════════════════════

class TestRefusalDetection:
    def test_the_canonical_refusal_is_recognised(self):
        from services.llm import REFUSAL_MESSAGE

        assert metrics.is_refusal(REFUSAL_MESSAGE) is True

    def test_trailing_whitespace_does_not_break_it(self):
        from services.llm import REFUSAL_MESSAGE

        assert metrics.is_refusal(REFUSAL_MESSAGE + '\n\n  ') is True

    def test_a_real_answer_is_not_a_refusal(self):
        assert metrics.is_refusal('The refund window is 30 days (Page 2).') is False

    def test_an_empty_answer_is_not_counted_as_a_refusal(self):
        """An empty reply is a failure, not a principled decline.

        Scoring it as a refusal would let a pipeline that returns nothing at all
        post a perfect refusal accuracy.
        """
        assert metrics.is_refusal('') is False


# ══════════════════════════════════════════════════════════════════
# Retrieval
# ══════════════════════════════════════════════════════════════════

class TestRetrievalMetrics:
    def test_recall_counts_expected_pages_that_were_found(self):
        retrieved = [chunk(2, 'refunds'), chunk(5, 'damage')]

        assert metrics.retrieval_recall(retrieved, [], [2]) == 1.0
        assert metrics.retrieval_recall(retrieved, [], [2, 5]) == 1.0
        assert metrics.retrieval_recall(retrieved, [], [2, 7]) == 0.5
        assert metrics.retrieval_recall(retrieved, [], [7]) == 0.0

    def test_recall_is_none_without_ground_truth(self):
        """A case declaring no expected pages must not score as perfect.

        None keeps it out of the average; 1.0 would let a dataset with no ground
        truth report flawless retrieval.
        """
        assert metrics.retrieval_recall([chunk(2, 'x')], [], []) is None

    def test_precision_falls_as_extra_pages_are_retrieved(self):
        one_wanted = [chunk(2, 'refunds')]
        six_returned = [chunk(p, 'text') for p in range(1, 7)]

        assert metrics.retrieval_precision(one_wanted, [], [2]) == 1.0
        assert metrics.retrieval_precision(six_returned, [], [2]) == pytest.approx(1 / 6)

    def test_precision_is_zero_when_nothing_was_retrieved(self):
        assert metrics.retrieval_precision([], [], [2]) == 0.0

    def test_document_name_is_honoured_when_given(self):
        retrieved = [chunk(2, 'refunds', document='other.pdf')]

        # Right page, wrong document — not a hit.
        assert metrics.retrieval_recall(retrieved, ['policy.pdf'], [2]) == 0.0
        assert metrics.retrieval_recall(retrieved, ['other.pdf'], [2]) == 1.0

    def test_document_name_is_ignored_when_omitted(self):
        """Single-document datasets should not have to name the file every time."""
        retrieved = [chunk(2, 'refunds', document='anything.pdf')]

        assert metrics.retrieval_recall(retrieved, [], [2]) == 1.0

    def test_reciprocal_rank_rewards_ranking_the_right_page_first(self):
        first = [chunk(2, 'a'), chunk(9, 'b'), chunk(9, 'c')]
        third = [chunk(9, 'a'), chunk(9, 'b'), chunk(2, 'c')]

        assert metrics.reciprocal_rank(first, [], [2]) == 1.0
        assert metrics.reciprocal_rank(third, [], [2]) == pytest.approx(1 / 3)
        assert metrics.reciprocal_rank([chunk(9, 'a')], [], [2]) == 0.0


class TestContextRelevance:
    def test_all_related_passages_score_one(self):
        retrieved = [chunk(2, 'Refund requests are processed quickly.'),
                     chunk(3, 'Refund amounts exclude delivery.')]

        assert metrics.context_relevance(retrieved, 'How do refunds work?') == 1.0

    def test_noise_lowers_the_score(self):
        retrieved = [chunk(2, 'Refunds take 30 days.'),
                     chunk(7, 'Bicycles are stored in the yard.')]

        assert metrics.context_relevance(retrieved, 'How do refunds work?') == 0.5

    def test_empty_retrieval_scores_zero(self):
        assert metrics.context_relevance([], 'anything?') == 0.0


# ══════════════════════════════════════════════════════════════════
# Grounding and citations
# ══════════════════════════════════════════════════════════════════

class TestFaithfulness:
    def test_an_answer_taken_from_the_context_scores_high(self):
        context = [chunk(2, 'Domestic orders may be returned within 30 days.')]

        score = metrics.faithfulness_lexical('Orders may be returned within 30 days.', context)

        assert score == 1.0

    def test_invented_content_lowers_the_score(self):
        context = [chunk(2, 'Domestic orders may be returned within 30 days.')]

        score = metrics.faithfulness_lexical(
            'Orders may be returned within 30 days and refunded in cryptocurrency '
            'at any branch in Reykjavik.',
            context,
        )

        assert score < 0.7

    def test_a_refusal_is_perfectly_faithful(self):
        """Declining to answer invents nothing.

        Scoring a refusal as unfaithful would penalise exactly the behaviour the
        grounding prompt exists to produce, and reward a pipeline that guesses.
        """
        from services.llm import REFUSAL_MESSAGE

        assert metrics.faithfulness_lexical(REFUSAL_MESSAGE, []) == 1.0


class TestCitations:
    @pytest.mark.parametrize('answer,expected', [
        ('The window is 30 days (Page 2).', {2}),
        ('Both apply (Pages 3, 7).', {3, 7}),
        ('See the handbook (policy.pdf, Page 12).', {12}),
        ('Several (policy.pdf, Pages 4, 9).', {4, 9}),
        ('Two claims (Page 2). And another (Page 5).', {2, 5}),
        ('No citation here at all.', set()),
    ])
    def test_page_citations_are_extracted(self, answer, expected):
        assert metrics.extract_cited_pages(answer) == expected

    def test_citing_a_retrieved_page_is_valid(self):
        retrieved = [chunk(2, 'refunds'), chunk(3, 'shipping')]

        assert metrics.citation_validity('Refunds take 30 days (Page 2).', retrieved) == 1.0

    def test_a_hallucinated_page_number_is_caught(self):
        """The worst failure this system has.

        An invented page number makes an answer look *more* checkable than an
        uncited one while being impossible to check, so it has to be detected
        rather than rewarded.
        """
        retrieved = [chunk(2, 'refunds')]

        assert metrics.citation_validity('Refunds take 30 days (Page 47).', retrieved) == 0.0

    def test_partially_hallucinated_citations_score_between(self):
        retrieved = [chunk(2, 'refunds')]

        score = metrics.citation_validity('It depends (Pages 2, 47).', retrieved)

        assert score == 0.5

    def test_an_uncited_answer_returns_none(self):
        """None, not 1.0: an answer citing nothing has no citation accuracy to
        report, and scoring it perfect would reward dropping citations."""
        assert metrics.citation_validity('Refunds take 30 days.', [chunk(2, 'x')]) is None


# ══════════════════════════════════════════════════════════════════
# Aggregation
# ══════════════════════════════════════════════════════════════════

class TestAggregation:
    def test_none_values_are_excluded_not_counted_as_zero(self):
        assert metrics.mean([1.0, None, 0.0]) == 0.5
        assert metrics.mean([None, None]) is None
        assert metrics.mean([]) is None

    def test_percentiles(self):
        values = [10.0, 20.0, 30.0, 40.0, 100.0]

        assert metrics.percentile(values, 0.5) == 30.0
        assert metrics.percentile(values, 0.95) == 100.0
        assert metrics.percentile([], 0.5) is None
