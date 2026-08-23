"""Admin panel, asserted against both persistence backends.

The admin API used to read MongoDB collections directly, so every endpoint here
returned 500 on a PostgreSQL deployment — and nothing caught it, because the
one admin test asserted only that a staff user got 200 and the developer
machine happened to run MongoDB. It was CI, which has PostgreSQL and no
MongoDB, that finally said so.

Every test therefore runs under the parametrised ``backend`` fixture, the same
device that makes ``PERSISTENCE_BACKEND`` trustworthy in
``test_repository_parity.py``. A backend that cannot serve the admin panel now
fails a test rather than a deployment.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db


def auth_header(user: User) -> dict:
    return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(user).access_token}'}


@pytest.fixture
def admin(db) -> User:
    return User.objects.create_user(
        username='admin-under-test',
        email='admin-under-test@example.com',
        password='not-a-real-password',  # noqa: S106
        is_staff=True,
    )


# ══════════════════════════════════════════════════════════════════
# Reachability — the regression this file exists for
# ══════════════════════════════════════════════════════════════════

class TestEveryEndpointAnswersOnBothBackends:
    """The bug was a 500, so the first thing worth asserting is "not a 500"."""

    @pytest.mark.parametrize('path', [
        '/api/admin-panel/stats/',
        '/api/admin-panel/users/',
        '/api/admin-panel/documents/',
        '/api/admin-panel/chats/',
        '/api/admin-panel/metrics/',
    ])
    def test_it_answers(self, client, admin, backend, path):
        response = client.get(path, **auth_header(admin))

        assert response.status_code == 200, (
            f'{path} returned {response.status_code} on the {backend} backend'
        )


class TestStats:
    def test_counts_reflect_what_exists(self, client, admin, user, backend,
                                        make_document):
        make_document(user, name='a.pdf', status='completed')
        make_document(user, name='b.pdf', status='failed')

        data = client.get('/api/admin-panel/stats/', **auth_header(admin)).json()['data']

        assert data['documents']['total'] == 2
        assert data['documents']['completed'] == 1
        assert data['documents']['failed'] == 1

    def test_the_shape_the_dashboard_reads_is_intact(self, client, admin, backend):
        """The React admin page indexes these keys directly.

        Asserted per key rather than by comparing a whole dict, so a failure
        names the missing one instead of printing two large structures.
        """
        data = client.get('/api/admin-panel/stats/', **auth_header(admin)).json()['data']

        for key in ('users', 'documents', 'chat', 'dau_trend', 'query_trend'):
            assert key in data, f'stats payload lost "{key}"'

        for key in ('total', 'active', 'new_7d', 'admins'):
            assert key in data['users']
        for key in ('total', 'completed', 'failed', 'pending', 'new_7d'):
            assert key in data['documents']
        for key in ('total_sessions', 'total_messages', 'queries_7d', 'queries_30d'):
            assert key in data['chat']

    def test_the_trends_cover_seven_days_even_when_nothing_happened(
        self, client, admin, backend
    ):
        """A quiet day is a zero, not a gap.

        A trend that omitted empty days would compress the x-axis and make a
        week with two active days look like a week of continuous use.
        """
        data = client.get('/api/admin-panel/stats/', **auth_header(admin)).json()['data']

        assert len(data['dau_trend']) == 7
        assert len(data['query_trend']) == 7
        assert all(point['users'] == 0 for point in data['dau_trend'])


# ══════════════════════════════════════════════════════════════════
# Listing
# ══════════════════════════════════════════════════════════════════

class TestUserList:
    def test_per_user_counts_are_attributed_to_the_right_user(
        self, client, admin, user, other_user, backend, make_document
    ):
        """The batched count query is easy to get subtly wrong.

        Grouping by the wrong column, or zipping results back by position
        rather than by id, gives every row plausible-looking numbers that
        belong to somebody else.
        """
        make_document(user, name='one.pdf')
        make_document(user, name='two.pdf')
        make_document(other_user, name='three.pdf')

        rows = client.get('/api/admin-panel/users/', **auth_header(admin)).json()['data']
        by_id = {row['id']: row for row in rows}

        assert by_id[user.id]['documents'] == 2
        assert by_id[other_user.id]['documents'] == 1
        assert by_id[admin.id]['documents'] == 0

    def test_search_filters(self, client, admin, user, backend):
        rows = client.get('/api/admin-panel/users/?search=admin-under-test',
                          **auth_header(admin)).json()['data']

        assert [r['id'] for r in rows] == [admin.id]


class TestDocumentList:
    def test_documents_carry_their_owner_and_a_readable_size(
        self, client, admin, user, backend, make_document
    ):
        make_document(user, name='policy.pdf')

        rows = client.get('/api/admin-panel/documents/',
                          **auth_header(admin)).json()['data']

        assert len(rows) == 1
        assert rows[0]['original_filename'] == 'policy.pdf'
        assert rows[0]['username'] == user.username
        # Display-only, added by the view; the admin table renders it directly.
        assert rows[0]['file_size_display']

    def test_status_filter(self, client, admin, user, backend, make_document):
        make_document(user, name='ok.pdf', status='completed')
        make_document(user, name='bad.pdf', status='failed')

        rows = client.get('/api/admin-panel/documents/?status=failed',
                          **auth_header(admin)).json()['data']

        assert [r['original_filename'] for r in rows] == ['bad.pdf']

    def test_search_filter(self, client, admin, user, backend, make_document):
        make_document(user, name='warranty.pdf')
        make_document(user, name='invoice.pdf')

        rows = client.get('/api/admin-panel/documents/?search=warrant',
                          **auth_header(admin)).json()['data']

        assert [r['original_filename'] for r in rows] == ['warranty.pdf']


# ══════════════════════════════════════════════════════════════════
# Deletion
# ══════════════════════════════════════════════════════════════════

class TestDeletion:
    def test_deleting_a_document_removes_it(self, client, admin, user, backend,
                                            make_document, document_repo):
        document = make_document(user, name='gone.pdf')

        response = client.delete(f"/api/admin-panel/documents/{document['id']}/",
                                 **auth_header(admin))

        assert response.status_code == 200
        assert document_repo.get(document['id'], user.id) is None

    def test_an_unknown_document_is_a_404_not_a_500(self, client, admin, backend):
        """Including an id that is not even the right shape.

        The Mongo path raises InvalidId on a non-ObjectId string and the
        Postgres path raises on a non-UUID; both have to answer 404 rather than
        letting the exception become a server error.
        """
        response = client.delete('/api/admin-panel/documents/not-a-real-id/',
                                 **auth_header(admin))

        assert response.status_code == 404

    def test_deleting_a_user_takes_their_documents_with_them(
        self, client, admin, user, backend, make_document, document_repo
    ):
        """Otherwise the rows outlive the account and the admin totals drift."""
        document = make_document(user, name='orphan.pdf')

        response = client.delete(f'/api/admin-panel/users/{user.id}/',
                                 **auth_header(admin))

        assert response.status_code == 200
        assert not User.objects.filter(id=user.id).exists()
        assert document_repo.get(document['id'], user.id) is None


# ══════════════════════════════════════════════════════════════════
# Authorisation
# ══════════════════════════════════════════════════════════════════

class TestAuthorisation:
    """Unchanged by the migration, and re-asserted because it would be a quiet
    thing to break while moving every view's body."""

    @pytest.mark.parametrize('path', [
        '/api/admin-panel/stats/',
        '/api/admin-panel/users/',
        '/api/admin-panel/documents/',
        '/api/admin-panel/chats/',
    ])
    def test_a_normal_user_is_refused(self, client, user, backend, path):
        assert client.get(path, **auth_header(user)).status_code == 403

    @pytest.mark.parametrize('path', [
        '/api/admin-panel/stats/',
        '/api/admin-panel/users/',
    ])
    def test_an_anonymous_request_is_refused(self, client, backend, path):
        assert client.get(path).status_code == 401
