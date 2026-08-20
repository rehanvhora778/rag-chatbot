"""The contract both persistence backends must satisfy.

Every test here runs twice — once against MongoDB, once against PostgreSQL —
because the `backend` fixture is parametrised. That is the whole point: the
project claims `PERSISTENCE_BACKEND` can be flipped without the API changing,
and this file is where that claim is either true or caught being false.

The isolation tests matter most. "A user must never retrieve another user's
documents" is the central security property of the system, and it is currently
enforced by a filter written into each query by hand. These tests are what stop
one missing filter from becoming a cross-tenant data leak.
"""
import pytest

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════
# Documents — basic storage
# ══════════════════════════════════════════════════════════════════

class TestDocumentStorage:
    def test_create_returns_the_documented_shape(self, document_repo, user, make_document):
        doc = make_document(user, name='refund_policy.pdf')

        # The React app reads these keys directly. Both backends must produce
        # all of them or the frontend breaks on a backend switch.
        for key in ('id', 'user_id', 'original_filename', 'file_type', 'file_size',
                    'file_hash', 'status', 'page_count', 'chunk_count',
                    'summary', 'error_message', 'created_at'):
            assert key in doc, f'missing key: {key}'

        assert doc['user_id'] == user.id
        assert doc['original_filename'] == 'refund_policy.pdf'
        assert isinstance(doc['id'], str) and doc['id']

    def test_get_round_trips(self, document_repo, user, make_document):
        created = make_document(user, name='notes.pdf')
        fetched = document_repo.get(created['id'], user.id)

        assert fetched is not None
        assert fetched['id'] == created['id']
        assert fetched['original_filename'] == 'notes.pdf'

    def test_get_with_a_malformed_id_returns_none_rather_than_raising(
        self, document_repo, user
    ):
        # These ids come straight out of a URL. A client typo must be a 404,
        # not a 500 — ObjectId() and UUID() both raise on malformed input.
        for bad in ('not-an-id', '', '12345', 'x' * 100):
            assert document_repo.get(bad, user.id) is None

    def test_update_changes_only_what_was_asked(self, document_repo, user, make_document):
        doc = make_document(user, name='before.pdf')

        updated = document_repo.update(doc['id'], user.id, original_filename='after.pdf')

        assert updated['original_filename'] == 'after.pdf'
        assert updated['file_hash'] == doc['file_hash']
        assert updated['file_type'] == doc['file_type']

    def test_delete_removes_it(self, document_repo, user, make_document):
        doc = make_document(user)

        assert document_repo.delete(doc['id'], user.id) is True
        assert document_repo.get(doc['id'], user.id) is None
        assert document_repo.delete(doc['id'], user.id) is False

    def test_find_by_hash_powers_duplicate_detection(
        self, document_repo, user, make_document
    ):
        doc = make_document(user)

        assert document_repo.find_by_hash(user.id, doc['file_hash'])['id'] == doc['id']
        assert document_repo.find_by_hash(user.id, 'a' * 64) is None

    def test_listing_is_newest_first_and_paginates(
        self, document_repo, user, make_document
    ):
        for i in range(5):
            make_document(user, name=f'doc{i}.pdf')

        first = document_repo.list_for_user(user.id, page=1, page_size=2)
        assert first['total'] == 5
        assert len(first['items']) == 2

        second = document_repo.list_for_user(user.id, page=2, page_size=2)
        assert len(second['items']) == 2
        # No row may appear on two pages.
        assert not ({d['id'] for d in first['items']}
                    & {d['id'] for d in second['items']})

    def test_list_completed_filters_by_status(self, document_repo, user, make_document):
        ready = make_document(user, status='completed')
        pending = make_document(user, status='pending')

        result = document_repo.list_completed(
            user.id, [ready['id'], pending['id']]
        )

        assert [d['id'] for d in result] == [ready['id']]

    def test_count_for_user_counts_only_theirs(
        self, document_repo, user, other_user, make_document
    ):
        make_document(user)
        make_document(user)
        make_document(other_user)

        assert document_repo.count_for_user(user.id) == 2
        assert document_repo.count_for_user(other_user.id) == 1


# ══════════════════════════════════════════════════════════════════
# Documents — isolation. The security property.
# ══════════════════════════════════════════════════════════════════

class TestDocumentIsolation:
    def test_a_user_cannot_read_another_users_document(
        self, document_repo, user, other_user, make_document
    ):
        victim_doc = make_document(user, name='private_salary_review.pdf')

        # Mallory has the real id — from a log, a shared screenshot, anywhere.
        assert document_repo.get(victim_doc['id'], other_user.id) is None

    def test_a_user_cannot_update_another_users_document(
        self, document_repo, user, other_user, make_document
    ):
        victim_doc = make_document(user, name='original.pdf')

        assert document_repo.update(
            victim_doc['id'], other_user.id, original_filename='hijacked.pdf'
        ) is None
        # And the document is genuinely untouched.
        assert document_repo.get(victim_doc['id'], user.id)['original_filename'] \
            == 'original.pdf'

    def test_a_user_cannot_delete_another_users_document(
        self, document_repo, user, other_user, make_document
    ):
        victim_doc = make_document(user)

        assert document_repo.delete(victim_doc['id'], other_user.id) is False
        assert document_repo.get(victim_doc['id'], user.id) is not None

    def test_listing_never_leaks_across_users(
        self, document_repo, user, other_user, make_document
    ):
        make_document(user, name='mine.pdf')
        make_document(other_user, name='theirs.pdf')

        listing = document_repo.list_for_user(user.id)

        assert listing['total'] == 1
        assert [d['original_filename'] for d in listing['items']] == ['mine.pdf']

    def test_list_completed_drops_another_users_ids(
        self, document_repo, user, other_user, make_document
    ):
        """The path a crafted request actually takes.

        Creating a conversation posts a list of document ids. If one of them
        belongs to someone else and survives this filter, the conversation
        becomes grounded in a stranger's file and every answer quotes it.
        """
        mine = make_document(user, name='mine.pdf')
        theirs = make_document(other_user, name='theirs.pdf')

        result = document_repo.list_completed(user.id, [mine['id'], theirs['id']])

        assert [d['id'] for d in result] == [mine['id']]

    def test_find_by_hash_is_scoped_per_user(
        self, document_repo, user, other_user, make_document
    ):
        """Two people uploading the same file must both get their own copy.

        If the duplicate check were global, the second person would be told the
        file already exists — which both denies them the upload and reveals
        that someone else has that exact file.
        """
        doc = make_document(user)

        assert document_repo.find_by_hash(other_user.id, doc['file_hash']) is None


# ══════════════════════════════════════════════════════════════════
# Chunks
# ══════════════════════════════════════════════════════════════════

class TestChunkStorage:
    def test_replace_chunks_returns_ids_in_the_order_given(
        self, document_repo, user, make_document, make_chunks
    ):
        doc = make_document(user)
        chunks = make_chunks(4)

        ids = document_repo.replace_chunks(doc['id'], user.id, chunks)

        assert len(ids) == 4
        assert len(set(ids)) == 4
        # Position matters: the vector index is built from the same list, so
        # position i of the index must be chunk i.
        fetched = document_repo.get_chunks(ids, user.id)
        assert [c['chunk_index'] for c in fetched] == [0, 1, 2, 3]

    def test_replace_chunks_is_idempotent(
        self, document_repo, user, make_document, make_chunks
    ):
        """Re-processing a document must not leave the old chunks behind.

        This is the property that makes the Celery task safe to redeliver: a
        worker killed mid-document runs again and the result is the same, not
        double.
        """
        doc = make_document(user)

        first = document_repo.replace_chunks(doc['id'], user.id, make_chunks(3))
        second = document_repo.replace_chunks(doc['id'], user.id, make_chunks(3))

        assert len(second) == 3
        # The originals are gone, not merely shadowed.
        assert document_repo.get_chunks(first, user.id) == []

    def test_get_chunks_preserves_caller_order(
        self, document_repo, user, make_document, make_chunks
    ):
        """Caller order is the ranking.

        Retrieval hands over chunk ids sorted by relevance. A database IN
        clause has no defined order, so a repository that returns storage order
        silently reorders the context the model sees — best passage last.
        """
        doc = make_document(user)
        ids = document_repo.replace_chunks(doc['id'], user.id, make_chunks(4))

        shuffled = [ids[2], ids[0], ids[3]]
        result = document_repo.get_chunks(shuffled, user.id)

        assert [c['chunk_id'] for c in result] == shuffled

    def test_get_chunks_carries_the_document_name_for_citations(
        self, document_repo, user, make_document, make_chunks
    ):
        doc = make_document(user, name='refund_policy.pdf')
        ids = document_repo.replace_chunks(doc['id'], user.id, make_chunks(2))

        result = document_repo.get_chunks(ids, user.id)

        assert all(c['document_name'] == 'refund_policy.pdf' for c in result)
        assert all(c['page_number'] >= 1 for c in result)

    def test_get_chunks_skips_ids_that_do_not_exist(
        self, document_repo, user, make_document, make_chunks
    ):
        doc = make_document(user)
        ids = document_repo.replace_chunks(doc['id'], user.id, make_chunks(2))

        result = document_repo.get_chunks([*ids, 'deadbeef' * 3], user.id)

        assert len(result) == 2

    def test_deleting_a_document_removes_its_chunks(
        self, document_repo, user, make_document, make_chunks
    ):
        doc = make_document(user)
        ids = document_repo.replace_chunks(doc['id'], user.id, make_chunks(3))

        document_repo.delete(doc['id'], user.id)

        assert document_repo.get_chunks(ids, user.id) == []

    def test_a_user_cannot_read_another_users_chunks(
        self, document_repo, user, other_user, make_document, make_chunks
    ):
        """The leak that would matter most.

        Chunk ids are returned to the browser inside every citation, so they
        are the one internal identifier a user genuinely holds for content they
        may not own.
        """
        doc = make_document(user)
        ids = document_repo.replace_chunks(doc['id'], user.id, make_chunks(3))

        assert document_repo.get_chunks(ids, other_user.id) == []


# ══════════════════════════════════════════════════════════════════
# Conversations
# ══════════════════════════════════════════════════════════════════

class TestConversationStorage:
    def test_create_returns_the_documented_shape(
        self, conversation_repo, document_repo, user, make_document
    ):
        doc = make_document(user, name='policy.pdf')

        conversation = conversation_repo.create(
            user.id, 'Refund questions', [doc['id']], [doc['original_filename']],
        )

        for key in ('id', 'user_id', 'title', 'document_ids', 'document_names',
                    'status', 'message_count', 'created_at'):
            assert key in conversation, f'missing key: {key}'

        assert conversation['document_ids'] == [doc['id']]
        assert conversation['document_names'] == ['policy.pdf']
        assert conversation['message_count'] == 0

    def test_add_turn_stores_question_before_answer(
        self, conversation_repo, document_repo, user, make_document
    ):
        """Order is not cosmetic.

        History is read back sorted by created_at and fed to the model as the
        conversation so far. If an answer sorts before its question, the model
        is shown a transcript in which it replied before being asked.
        """
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Chat', [doc['id']], ['d.pdf'])

        conversation_repo.add_turn(
            conversation['id'], user.id,
            question='What is the refund window?',
            answer='Thirty days.',
            sources=[{'document_name': 'd.pdf', 'page_number': 4}],
        )

        messages = conversation_repo.list_messages(conversation['id'], user.id)

        assert [m['role'] for m in messages] == ['user', 'assistant']
        assert messages[0]['content'] == 'What is the refund window?'
        assert messages[1]['content'] == 'Thirty days.'
        assert messages[1]['sources'][0]['page_number'] == 4
        assert messages[0]['created_at'] < messages[1]['created_at']

    def test_add_turn_updates_the_sidebar_summary(
        self, conversation_repo, user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Chat', [doc['id']], ['d.pdf'])

        conversation_repo.add_turn(
            conversation['id'], user.id, 'How do refunds work?', 'Like this.', [],
        )

        updated = conversation_repo.get(conversation['id'], user.id)
        assert updated['message_count'] == 2
        assert 'refunds' in updated['last_message_preview']
        assert updated['last_message_at'] is not None

    def test_recent_history_returns_the_tail_in_order(
        self, conversation_repo, user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Chat', [doc['id']], ['d.pdf'])
        for i in range(5):
            conversation_repo.add_turn(
                conversation['id'], user.id, f'question {i}', f'answer {i}', [],
            )

        history = conversation_repo.recent_history(conversation['id'], user.id, max_turns=2)

        assert len(history) == 4                      # 2 turns == 4 messages
        assert history[0]['content'] == 'question 3'  # oldest of the tail first
        assert history[-1]['content'] == 'answer 4'

    def test_search_matches_titles_case_insensitively(
        self, conversation_repo, user, make_document
    ):
        doc = make_document(user)
        conversation_repo.create(user.id, 'Refund Policy Questions', [doc['id']], ['d.pdf'])
        conversation_repo.create(user.id, 'Shipping', [doc['id']], ['d.pdf'])

        found = conversation_repo.search(user.id, 'refund')

        assert found['total'] == 1
        assert found['items'][0]['title'] == 'Refund Policy Questions'

    def test_delete_removes_the_transcript_too(
        self, conversation_repo, user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Chat', [doc['id']], ['d.pdf'])
        conversation_repo.add_turn(conversation['id'], user.id, 'q', 'a', [])

        assert conversation_repo.delete(conversation['id'], user.id) is True
        assert conversation_repo.get(conversation['id'], user.id) is None
        assert conversation_repo.list_messages(conversation['id'], user.id) == []


class TestConversationIsolation:
    def test_a_user_cannot_read_another_users_conversation(
        self, conversation_repo, user, other_user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Private', [doc['id']], ['d.pdf'])

        assert conversation_repo.get(conversation['id'], other_user.id) is None

    def test_a_user_cannot_read_another_users_messages(
        self, conversation_repo, user, other_user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Private', [doc['id']], ['d.pdf'])
        conversation_repo.add_turn(
            conversation['id'], user.id, 'my salary?', 'redacted', [],
        )

        assert conversation_repo.list_messages(conversation['id'], other_user.id) == []

    def test_a_user_cannot_delete_another_users_conversation(
        self, conversation_repo, user, other_user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Private', [doc['id']], ['d.pdf'])

        assert conversation_repo.delete(conversation['id'], other_user.id) is False
        assert conversation_repo.get(conversation['id'], user.id) is not None

    def test_a_user_cannot_rename_another_users_conversation(
        self, conversation_repo, user, other_user, make_document
    ):
        doc = make_document(user)
        conversation = conversation_repo.create(user.id, 'Original', [doc['id']], ['d.pdf'])

        assert conversation_repo.update(
            conversation['id'], other_user.id, title='Hijacked'
        ) is None

    def test_search_never_leaks_across_users(
        self, conversation_repo, user, other_user, make_document
    ):
        mine = make_document(user)
        theirs = make_document(other_user)
        conversation_repo.create(user.id, 'Refunds mine', [mine['id']], ['d.pdf'])
        conversation_repo.create(other_user.id, 'Refunds theirs', [theirs['id']], ['d.pdf'])

        found = conversation_repo.search(user.id, 'refunds')

        assert found['total'] == 1
        assert found['items'][0]['title'] == 'Refunds mine'

    def test_a_conversation_cannot_be_grounded_in_someone_elses_document(
        self, conversation_repo, user, other_user, make_document
    ):
        """Defence in depth.

        The service validates ids before calling this, but the repository
        filters by owner again. An ownership check that exists only upstream is
        one refactor away from not existing.
        """
        theirs = make_document(other_user, name='their_secret.pdf')

        conversation = conversation_repo.create(
            user.id, 'Sneaky', [theirs['id']], ['their_secret.pdf'],
        )

        stored = conversation_repo.get(conversation['id'], user.id)
        assert stored['document_ids'] == []

    def test_regrounding_cannot_attach_someone_elses_document(
        self, conversation_repo, user, other_user, make_document
    ):
        """The other half of the same hole.

        A conversation that already exists can be re-pointed at a different set
        of documents. If that path skips the ownership filter, an attacker
        creates a legitimate conversation and then swaps in a stranger's file.
        """
        mine = make_document(user, name='mine.pdf')
        theirs = make_document(other_user, name='theirs.pdf')
        conversation = conversation_repo.create(
            user.id, 'Chat', [mine['id']], ['mine.pdf'],
        )

        conversation_repo.update(
            conversation['id'], user.id, document_ids=[theirs['id']],
        )

        stored = conversation_repo.get(conversation['id'], user.id)
        assert stored['document_ids'] == []
        assert 'theirs.pdf' not in stored['document_names']
