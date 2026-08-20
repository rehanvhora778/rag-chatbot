"""Shared test fixtures.

The important one is ``document_repo`` / ``conversation_repo``: they are
parametrised over both persistence backends, so a test written once runs twice
and the assertions become a specification that MongoDB and PostgreSQL must both
satisfy. A backend that cannot pass them is not a drop-in replacement, and the
suite says so before a deployment finds out.
"""
import os
import uuid

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection

from repositories.factory import reset_repositories

# A separate database from the developer's real one. Mongo has no equivalent of
# pytest-django's test-database handling, so this is done by hand — without it
# the suite would insert into, and then drop, the collections holding the
# documents someone is actually working with.
TEST_MONGO_DB = 'ragchatbot_pytest'


# ══════════════════════════════════════════════════════════════════
# Availability
# ══════════════════════════════════════════════════════════════════

def _mongo_available() -> bool:
    try:
        from pymongo import MongoClient

        client = MongoClient(settings.MONGODB_HOST, serverSelectionTimeoutMS=1500)
        client.admin.command('ping')
        client.close()
        return True
    except Exception:
        return False


def _postgres_available() -> bool:
    return connection.vendor == 'postgresql'


# ══════════════════════════════════════════════════════════════════
# Users
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username='alice', email='alice@example.com', password='alice-password-1',
    )


@pytest.fixture
def other_user(db) -> User:
    """A second account. Every isolation test needs someone to be isolated from."""
    return User.objects.create_user(
        username='mallory', email='mallory@example.com', password='mallory-password-1',
    )


# ══════════════════════════════════════════════════════════════════
# Repositories, parametrised over both backends
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def mongo_test_db(settings):
    """Point the Mongo client at a scratch database and drop it afterwards."""
    from core import mongo

    settings.MONGODB_DB = TEST_MONGO_DB
    mongo.close_connection()          # force a reconnect against the new name

    yield

    client = mongo.get_mongo_client()
    client.drop_database(TEST_MONGO_DB)
    mongo.close_connection()


@pytest.fixture(params=['mongo', 'postgres'])
def backend(request, settings, db):
    """Configure one persistence backend and yield its name.

    Skips rather than fails when a backend is not reachable: a laptop with no
    MongoDB running should still be able to run the PostgreSQL half of the
    suite, and CI runs both.
    """
    name = request.param

    if name == 'mongo':
        if not _mongo_available():
            pytest.skip('MongoDB is not reachable')
        request.getfixturevalue('mongo_test_db')
    elif name == 'postgres':
        if not _postgres_available():
            pytest.skip(
                'PostgreSQL is required for this backend. '
                'Set DATABASE_URL to run it (CI always does).'
            )

    settings.PERSISTENCE_BACKEND = name
    reset_repositories()
    yield name
    reset_repositories()


@pytest.fixture
def document_repo(backend):
    from repositories.factory import get_document_repository

    return get_document_repository()


@pytest.fixture
def conversation_repo(backend):
    from repositories.factory import get_conversation_repository

    return get_conversation_repository()


# ══════════════════════════════════════════════════════════════════
# Builders
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def make_document(document_repo):
    """Create a document through the repository under test."""

    def _make(user, *, name='report.pdf', status='completed', **overrides):
        fields = {
            'original_filename': name,
            'filename': f'{uuid.uuid4().hex}.pdf',
            # Never opened — these tests exercise storage, not the filesystem.
            'file_path': f'/nonexistent/{uuid.uuid4().hex}.pdf',  # noqa: S108
            'file_type': 'pdf',
            'file_size': 2048,
            # Unique per call so the (owner, file_hash) constraint does not fire
            # on tests that simply need two documents.
            'file_hash': uuid.uuid4().hex + uuid.uuid4().hex,
            'status': status,
            **overrides,
        }
        return document_repo.create(user.id, **fields)

    return _make


@pytest.fixture
def make_chunks():
    """Chunk payloads in the shape replace_chunks expects, without embeddings.

    Vectors are left out on purpose: these tests are about storage and
    isolation, and loading a real embedding model would make them slow and
    dependent on a Hugging Face download.
    """

    def _make(count=3, *, page_start=1):
        return [
            {
                'content': f'Passage number {i} about refunds and warranties.',
                'chunk_index': i,
                'page_number': page_start + i,
                'start_char': i * 100,
                'end_char': (i + 1) * 100,
                'word_count': 7,
                'embedding': None,
            }
            for i in range(count)
        ]

    return _make


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """Fail loudly if a unit test tries to reach the internet.

    A test that quietly calls Groq is slow, costs money, and passes or fails
    depending on someone else's uptime. Tests that genuinely need the network
    opt in with @pytest.mark.integration.
    """
    if 'integration' in request.keywords:
        return

    import socket

    def _blocked(*args, **kwargs):
        raise RuntimeError(
            'This test attempted a network connection. Mock the provider, or '
            'mark the test with @pytest.mark.integration.'
        )

    # MongoDB and PostgreSQL are reached over sockets too, so only outbound
    # name resolution to non-local hosts is blocked.
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):
        if host not in ('localhost', '127.0.0.1', '::1', None, ''):
            _blocked()
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, 'getaddrinfo', guarded)


@pytest.fixture(scope='session', autouse=True)
def _announce_backends():
    """Print which backends the run will actually exercise."""
    yield
    if os.environ.get('PYTEST_XDIST_WORKER'):
        return
