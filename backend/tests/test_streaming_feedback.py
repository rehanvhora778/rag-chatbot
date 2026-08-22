"""Tests for SSE streaming and answer feedback.

The framing tests are the ones that would otherwise fail in a browser rather
than in CI: an SSE frame containing a raw newline terminates early, and the
client sees a truncated event with no error anywhere to explain it.
"""
import json
import uuid

import pytest

from apps.chat.streaming import sse

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════
# SSE framing
# ══════════════════════════════════════════════════════════════════

class TestSSEFraming:
    def test_a_frame_has_an_event_a_data_line_and_a_blank_line(self):
        frame = sse('token', {'text': 'hello'})

        assert frame == 'event: token\ndata: {"text": "hello"}\n\n'

    def test_a_newline_in_the_payload_cannot_terminate_the_frame(self):
        """The bug this encoding exists to prevent.

        A raw newline in a data line ends the frame, so the client would see a
        truncated event and the rest of the answer would arrive as garbage —
        with nothing logged anywhere, because nothing went wrong on the server.
        """
        frame = sse('token', {'text': 'line one\nline two\n\nparagraph'})

        # Exactly one blank line, at the very end.
        assert frame.count('\n\n') == 1
        assert frame.endswith('\n\n')
        assert len(frame.strip().split('\n')) == 2

    def test_the_payload_round_trips(self):
        payload = {'text': 'a "quoted" — ünicode\nstring', 'n': 3}

        frame = sse('token', payload)
        decoded = json.loads(frame.split('data: ', 1)[1].strip())

        assert decoded == payload

    def test_non_serialisable_values_do_not_raise(self):
        """A datetime in a payload must not take the stream down mid-answer."""
        from django.utils import timezone

        frame = sse('done', {'at': timezone.now()})

        assert frame.startswith('event: done')


class TestStreamResponseHeaders:
    def test_the_response_is_configured_not_to_be_buffered(self):
        """Every one of these exists because something between Django and the
        browser will otherwise hold the whole response until it completes,
        turning a stream into a slow ordinary reply."""
        from apps.chat.streaming import stream_response

        response = stream_response(iter(['event: ping\ndata: {}\n\n']))

        assert response['Content-Type'] == 'text/event-stream'
        assert response['Cache-Control'] == 'no-cache'
        assert response['X-Accel-Buffering'] == 'no'


# ══════════════════════════════════════════════════════════════════
# Feedback — run against both persistence backends
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def answered_conversation(conversation_repo, document_repo, user):
    """A conversation with one question and one answer in it."""
    document = document_repo.create(
        user.id,
        original_filename='policy.pdf', filename='stored.pdf',
        file_path='/nonexistent/stored.pdf',  # noqa: S108
        file_type='pdf', file_size=1024,
        file_hash=uuid.uuid4().hex * 2, status='completed',
    )
    conversation = conversation_repo.create(
        user.id, 'Refunds', [document['id']], ['policy.pdf'],
    )
    _question, answer = conversation_repo.add_turn(
        conversation['id'], user.id,
        question='What is the refund window?',
        answer='Thirty days. (Page 2)',
        sources=[{'document_name': 'policy.pdf', 'page_number': 2}],
    )
    return conversation, answer


class TestFeedback:
    def test_a_rating_is_stored_and_read_back(self, conversation_repo, user,
                                              answered_conversation):
        _conversation, answer = answered_conversation

        saved = conversation_repo.save_feedback(
            answer['id'], user.id, rating=-1, reason='missing', comment='no detail',
        )

        assert saved is not None
        assert saved['rating'] == -1
        assert saved['reason'] == 'missing'
        assert conversation_repo.get_feedback(answer['id'], user.id)['comment'] == 'no detail'

    def test_rating_again_replaces_rather_than_stacks(self, conversation_repo, user,
                                                      answered_conversation):
        """Changing your mind corrects the record.

        Without this the negative-feedback queue fills with verdicts the user
        has already withdrawn, and the counts an admin reads are wrong.
        """
        _conversation, answer = answered_conversation

        conversation_repo.save_feedback(answer['id'], user.id, rating=-1, reason='incorrect')
        conversation_repo.save_feedback(answer['id'], user.id, rating=1)

        current = conversation_repo.get_feedback(answer['id'], user.id)
        assert current['rating'] == 1

    def test_another_user_cannot_rate_the_answer(self, conversation_repo, user,
                                                 other_user, answered_conversation):
        _conversation, answer = answered_conversation

        assert conversation_repo.save_feedback(answer['id'], other_user.id, rating=1) is None

    def test_another_user_cannot_read_the_verdict(self, conversation_repo, user,
                                                  other_user, answered_conversation):
        _conversation, answer = answered_conversation
        conversation_repo.save_feedback(answer['id'], user.id, rating=-1)

        assert conversation_repo.get_feedback(answer['id'], other_user.id) is None

    def test_a_question_cannot_be_rated(self, conversation_repo, user,
                                        answered_conversation):
        """Only assistant answers have anything to rate.

        Allowing it would put the user's own words into the queue of answers to
        investigate.
        """
        conversation, _answer = answered_conversation
        messages = conversation_repo.list_messages(conversation['id'], user.id)
        question = next(m for m in messages if m['role'] == 'user')

        assert conversation_repo.save_feedback(question['id'], user.id, rating=-1) is None

    def test_a_malformed_id_returns_none_rather_than_raising(self, conversation_repo,
                                                             user):
        assert conversation_repo.save_feedback('not-an-id', user.id, rating=1) is None
        assert conversation_repo.get_feedback('not-an-id', user.id) is None

    def test_no_verdict_reads_back_as_none(self, conversation_repo, user,
                                           answered_conversation):
        _conversation, answer = answered_conversation

        assert conversation_repo.get_feedback(answer['id'], user.id) is None


class TestFeedbackValidation:
    """Rules enforced by the service rather than the repository."""

    def test_an_invalid_rating_is_rejected(self, backend, user):
        from services.chat_service import ChatError, submit_feedback

        with pytest.raises(ChatError, match='Rating must be'):
            submit_feedback(user.id, 'any-id', rating=5)

    def test_an_unknown_reason_is_rejected(self, backend, user):
        from services.chat_service import ChatError, submit_feedback

        with pytest.raises(ChatError, match='Unknown reason'):
            submit_feedback(user.id, 'any-id', rating=-1, reason='because')

    def test_a_reason_on_a_positive_rating_is_dropped(self, conversation_repo, user,
                                                      answered_conversation):
        """Every reason describes a way the answer was wrong, so one attached
        to a thumbs-up is noise in the queue of things to fix."""
        from services.chat_service import submit_feedback

        _conversation, answer = answered_conversation

        record = submit_feedback(user.id, answer['id'], rating=1, reason='incorrect')

        assert record['reason'] == ''
