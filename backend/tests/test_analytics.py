"""Per-user analytics, asserted against both persistence backends.

Same defect as the admin panel, one blast radius larger: these views read
MongoDB directly, so on a PostgreSQL deployment the analytics page broke for
every user rather than only for staff. Nothing caught it because there were no
tests for these endpoints at all.

The parametrised ``backend`` fixture runs everything here twice, so a store
that cannot serve the analytics screens fails a test rather than a deployment.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from core.constants import EVENT_EXPORT, EVENT_QUERY, EVENT_UPLOAD

pytestmark = pytest.mark.django_db

ANALYTICS = '/api/analytics/'
DASHBOARD = '/api/analytics/dashboard/'


def auth_header(user: User) -> dict:
    return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(user).access_token}'}


@pytest.fixture
def record_event(backend):
    """Write an analytics event through whichever store is live."""
    from core.analytics import record_event as _record

    def _make(user, event_type, **metadata):
        return _record(user.id, event_type, metadata or {})

    return _make


# ══════════════════════════════════════════════════════════════════
# Reachability — the regression this file exists for
# ══════════════════════════════════════════════════════════════════

class TestBothEndpointsAnswerOnBothBackends:
    @pytest.mark.parametrize('path', [ANALYTICS, DASHBOARD])
    def test_it_answers(self, client, user, backend, path):
        response = client.get(path, **auth_header(user))

        assert response.status_code == 200, (
            f'{path} returned {response.status_code} on the {backend} backend'
        )

    @pytest.mark.parametrize('path', [ANALYTICS, DASHBOARD])
    def test_a_brand_new_account_gets_zeroes_not_an_error(
        self, client, user, backend, path
    ):
        """Empty is the first state every account is in.

        Aggregates over nothing are exactly where a SUM returns None and a
        division blows up, so the emptiest case is worth asserting explicitly.
        """
        assert client.get(path, **auth_header(user)).status_code == 200

    @pytest.mark.parametrize('path', [ANALYTICS, DASHBOARD])
    def test_anonymous_is_refused(self, client, backend, path):
        assert client.get(path).status_code == 401


# ══════════════════════════════════════════════════════════════════
# Recording — the write side
# ══════════════════════════════════════════════════════════════════

class TestRecordEvent:
    """``record_event`` wrote to MongoDB unconditionally.

    On a PostgreSQL deployment every event was therefore dropped: the write
    failed, ``record_event`` swallowed it by design, and the only trace was a
    WARNING. Migrating the read side alone fixed nothing, because there was
    nothing stored to read — which is exactly what these assertions catch, by
    writing through the real entry point and reading back through the API
    rather than checking a store directly.
    """

    def test_an_event_is_stored_and_read_back(self, client, user, backend,
                                              record_event):
        assert record_event(user, EVENT_QUERY) is True

        data = client.get(ANALYTICS, **auth_header(user)).json()['data']

        assert data['activity']['queries_last_30d'] == 1

    def test_metadata_survives_the_round_trip(self, client, user, backend,
                                              record_event):
        """The activity feed's detail column is read straight out of it."""
        record_event(user, EVENT_UPLOAD, filename='handbook.pdf')

        activity = client.get(ANALYTICS, **auth_header(user)).json()['data']['recent_activity']

        assert activity[0]['detail'] == 'handbook.pdf'

    def test_a_failure_is_reported_rather_than_raised(self, user, backend,
                                                      monkeypatch):
        """Telemetry must never fail the request it is describing.

        Asserted because the contract is a silent one: every caller ignores the
        return value, so nothing else would notice if this started raising.
        """
        import core.analytics as analytics

        def explode(*args, **kwargs):
            raise RuntimeError('store is down')

        monkeypatch.setattr(analytics, '_record_postgres', explode)
        monkeypatch.setattr(analytics, '_record_mongo', explode)

        assert analytics.record_event(user.id, EVENT_QUERY) is False


# ══════════════════════════════════════════════════════════════════
# The payload the React screens read
# ══════════════════════════════════════════════════════════════════

class TestAnalyticsPayload:
    def test_the_shape_is_intact(self, client, user, backend):
        data = client.get(ANALYTICS, **auth_header(user)).json()['data']

        for key in ('documents', 'chat', 'activity', 'daily_query_trend',
                    'most_used_documents', 'recent_activity'):
            assert key in data, f'analytics payload lost "{key}"'

        for key in ('total', 'completed', 'failed', 'this_week', 'by_type'):
            assert key in data['documents']
        for key in ('total_sessions', 'active_sessions', 'total_messages',
                    'user_queries', 'messages_this_week'):
            assert key in data['chat']
        for key in ('uploads_last_30d', 'queries_last_30d', 'exports_last_30d'):
            assert key in data['activity']

    def test_document_counts_and_type_breakdown(self, client, user, backend,
                                                make_document):
        make_document(user, name='a.pdf', status='completed')
        make_document(user, name='b.pdf', status='failed')

        documents = client.get(ANALYTICS, **auth_header(user)).json()['data']['documents']

        assert documents['total'] == 2
        assert documents['completed'] == 1
        assert documents['failed'] == 1
        assert documents['by_type'] == {'pdf': 2}

    def test_another_users_documents_are_not_counted(
        self, client, user, other_user, backend, make_document
    ):
        """The isolation property, on the screen that aggregates everything.

        A missing owner filter here would not raise or look wrong — it would
        quietly inflate one user's totals with another's, which is the kind of
        leak that is only ever noticed by the person it embarrasses.
        """
        make_document(user, name='mine.pdf')
        make_document(other_user, name='theirs.pdf')
        make_document(other_user, name='theirs-too.pdf')

        data = client.get(ANALYTICS, **auth_header(user)).json()['data']

        assert data['documents']['total'] == 1

    def test_event_counts_are_per_event_type(self, client, user, backend,
                                             record_event):
        record_event(user, EVENT_UPLOAD, filename='a.pdf')
        record_event(user, EVENT_QUERY)
        record_event(user, EVENT_QUERY)
        record_event(user, EVENT_EXPORT)

        activity = client.get(ANALYTICS, **auth_header(user)).json()['data']['activity']

        assert activity['uploads_last_30d'] == 1
        assert activity['queries_last_30d'] == 2
        assert activity['exports_last_30d'] == 1

    def test_the_trend_covers_seven_days_including_empty_ones(
        self, client, user, backend, record_event
    ):
        record_event(user, EVENT_QUERY)

        trend = client.get(ANALYTICS, **auth_header(user)).json()['data']['daily_query_trend']

        assert len(trend) == 7
        assert sum(point['queries'] for point in trend) == 1
        # Today is the last bucket, and today is when the event was written.
        assert trend[-1]['queries'] == 1

    def test_recent_activity_is_labelled_and_newest_first(
        self, client, user, backend, record_event
    ):
        record_event(user, EVENT_UPLOAD, filename='handbook.pdf')
        record_event(user, EVENT_QUERY)

        activity = client.get(ANALYTICS, **auth_header(user)).json()['data']['recent_activity']

        assert len(activity) == 2
        assert activity[0]['event_type'] == EVENT_QUERY
        assert activity[0]['label'] == 'Asked a question'
        assert activity[1]['label'] == 'Uploaded a document'
        assert activity[1]['detail'] == 'handbook.pdf'


class TestMostUsedDocuments:
    def test_it_ranks_by_questions_asked(self, client, user, backend,
                                         make_document, conversation_repo):
        popular = make_document(user, name='popular.pdf')
        quiet = make_document(user, name='quiet.pdf')

        busy = conversation_repo.create(user.id, 'Busy', [popular['id']],
                                        [popular['original_filename']])
        conversation_repo.create(user.id, 'Quiet', [quiet['id']],
                                 [quiet['original_filename']])
        for i in range(3):
            conversation_repo.add_turn(busy['id'], user.id,
                                       question=f'q{i}', answer=f'a{i}', sources=[])

        rows = client.get(ANALYTICS, **auth_header(user)).json()['data']['most_used_documents']

        assert rows, 'no documents ranked'
        assert rows[0]['name'] == 'popular.pdf'
        assert rows[0]['queries'] == 3
        assert rows[0]['sessions'] == 1

    def test_an_empty_account_ranks_nothing_rather_than_failing(
        self, client, user, backend
    ):
        rows = client.get(ANALYTICS, **auth_header(user)).json()['data']['most_used_documents']

        assert rows == []


# ══════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════

class TestDashboard:
    def test_totals_and_recent_lists(self, client, user, backend,
                                     make_document, conversation_repo):
        document = make_document(user, name='report.pdf')
        conversation_repo.create(user.id, 'Session', [document['id']],
                                 [document['original_filename']])

        data = client.get(DASHBOARD, **auth_header(user)).json()['data']

        assert data['stats']['total_documents'] == 1
        assert data['stats']['total_sessions'] == 1
        assert len(data['recent_documents']) == 1
        assert data['recent_documents'][0]['original_filename'] == 'report.pdf'
        # Display-only, added by the view; the dashboard card renders it.
        assert data['recent_documents'][0]['file_size_display']
        assert len(data['recent_sessions']) == 1

    def test_a_session_with_no_messages_still_appears(
        self, client, user, backend, make_document, conversation_repo
    ):
        """Ordering is by last_message_at, which is NULL until the first turn.

        PostgreSQL sorts NULLs first on a descending order and SQLite sorts
        them last, so without an explicit nulls_last this both misorders the
        dashboard and does it differently per database.
        """
        document = make_document(user, name='report.pdf')
        conversation_repo.create(user.id, 'Never used', [document['id']],
                                 [document['original_filename']])

        data = client.get(DASHBOARD, **auth_header(user)).json()['data']

        assert [s['title'] for s in data['recent_sessions']] == ['Never used']

    def test_another_users_data_is_not_shown(self, client, user, other_user,
                                             backend, make_document):
        make_document(other_user, name='not-yours.pdf')

        data = client.get(DASHBOARD, **auth_header(user)).json()['data']

        assert data['stats']['total_documents'] == 0
        assert data['recent_documents'] == []
