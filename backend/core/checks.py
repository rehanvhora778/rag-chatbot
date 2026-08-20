"""Startup checks for configurations that are valid Python but broken systems.

Each of these describes a mistake whose natural symptom appears far away from
its cause — an insert error on the first upload, a retrieval that silently
returns nothing, a worker that never picks anything up. ``manage.py check``
runs them, so does ``runserver``, and CI runs them with ``--fail-level``.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register

# Tag so the whole group can be run alone: manage.py check --tag ragchat
RAGCHAT = 'ragchat'


@register(RAGCHAT)
def check_embedding_dimension(app_configs, **kwargs):
    """EMBEDDING_DIMENSION must match the width of the vector column.

    The column is ``vector(384)`` in the schema. Pointing EMBEDDING_MODEL_NAME
    at a model with a different output width is a one-line settings change that
    produces no error at all until the first chunk is written, and then only an
    opaque "expected 384 dimensions, not 768" from the driver.
    """
    from apps.documents.models import EMBEDDING_DIM

    configured = getattr(settings, 'EMBEDDING_DIMENSION', EMBEDDING_DIM)
    if configured != EMBEDDING_DIM:
        return [
            Error(
                f'EMBEDDING_DIMENSION is {configured} but the chunk embedding '
                f'column is vector({EMBEDDING_DIM}).',
                hint=(
                    'Changing the embedding model changes the vector width, which '
                    'is part of the database schema. Update EMBEDDING_DIM in '
                    'apps/documents/models.py, generate a migration, and re-embed '
                    'every existing chunk — old vectors are not comparable with '
                    'new ones even where the widths happen to agree.'
                ),
                id='ragchat.E001',
            )
        ]
    return []


@register(RAGCHAT)
def check_persistence_backend(app_configs, **kwargs):
    """PERSISTENCE_BACKEND=postgres needs an actual PostgreSQL connection."""
    from django.db import connection

    backend = getattr(settings, 'PERSISTENCE_BACKEND', 'mongo')
    problems = []

    if backend not in ('mongo', 'postgres'):
        problems.append(
            Error(
                f"PERSISTENCE_BACKEND is '{backend}'; expected 'mongo' or 'postgres'.",
                id='ragchat.E002',
            )
        )
        return problems

    if backend == 'postgres' and connection.vendor != 'postgresql':
        problems.append(
            Error(
                f"PERSISTENCE_BACKEND is 'postgres' but the default database is "
                f"{connection.vendor}.",
                hint='Set DATABASE_URL to a PostgreSQL connection string.',
                id='ragchat.E003',
            )
        )
    return problems


@register(RAGCHAT)
def check_vector_backend(app_configs, **kwargs):
    from django.db import connection

    backend = getattr(settings, 'VECTOR_BACKEND', 'faiss')
    problems = []

    if backend not in ('faiss', 'pgvector'):
        problems.append(
            Error(
                f"VECTOR_BACKEND is '{backend}'; expected 'faiss' or 'pgvector'.",
                id='ragchat.E004',
            )
        )
        return problems

    if backend == 'pgvector':
        if connection.vendor != 'postgresql':
            problems.append(
                Error(
                    f"VECTOR_BACKEND is 'pgvector' but the default database is "
                    f'{connection.vendor}.',
                    hint='Set DATABASE_URL to a PostgreSQL connection string.',
                    id='ragchat.E005',
                )
            )
        elif settings.PERSISTENCE_BACKEND != 'postgres':
            # The vectors would be in PostgreSQL while the chunks they belong to
            # are in MongoDB, so a vector search could not resolve its own hits.
            problems.append(
                Error(
                    "VECTOR_BACKEND='pgvector' requires PERSISTENCE_BACKEND='postgres'.",
                    hint='pgvector stores each vector on its chunk row, so the '
                         'chunks have to be in PostgreSQL too.',
                    id='ragchat.E006',
                )
            )
    return problems


@register(RAGCHAT)
def check_hybrid_retrieval(app_configs, **kwargs):
    """Hybrid search needs the PostgreSQL full-text index to exist."""
    if not getattr(settings, 'RAG_HYBRID_ENABLED', False):
        return []
    if settings.VECTOR_BACKEND != 'pgvector':
        return [
            Error(
                "RAG_HYBRID_ENABLED is on but VECTOR_BACKEND is not 'pgvector'.",
                hint='The keyword half of hybrid retrieval is a PostgreSQL '
                     'full-text index on the chunk table. With the FAISS backend '
                     'there is nothing to search, and retrieval would quietly '
                     'degrade to vector-only.',
                id='ragchat.E007',
            )
        ]
    return []


# HS256 signs with the raw key. RFC 7518 section 3.2 requires a key at least as
# long as the hash output — 32 bytes for SHA-256 — because a shorter one can be
# attacked directly rather than through the algorithm.
MIN_SECRET_KEY_BYTES = 32


@register(RAGCHAT)
def check_secret_key_strength(app_configs, **kwargs):
    """A short SECRET_KEY means forgeable sessions and forgeable JWTs.

    SIMPLE_JWT signs every access and refresh token with SECRET_KEY using
    HS256. A key materially shorter than the hash is brute-forceable offline
    from a single captured token, and whoever recovers it can mint a token for
    any account — including a staff one. PyJWT emits a warning about this, but
    a warning in a library's output during a request is not somewhere anyone
    looks.
    """
    key = getattr(settings, 'SECRET_KEY', '') or ''
    length = len(key.encode('utf-8'))

    if length >= MIN_SECRET_KEY_BYTES:
        return []

    hint = (
        'Generate one with: '
        'python -c "import secrets; print(secrets.token_urlsafe(64))" '
        'then set SECRET_KEY in backend/.env. Changing it invalidates existing '
        'sessions and JWTs, so everyone signs in again — which is the point.'
    )

    if settings.DEBUG:
        return [Warning(
            f'SECRET_KEY is only {length} bytes; JWTs are signed with it using '
            f'HS256, which needs at least {MIN_SECRET_KEY_BYTES}.',
            hint=hint, id='ragchat.W003',
        )]

    return [Error(
        f'SECRET_KEY is only {length} bytes. Every session cookie and JWT is '
        f'signed with it, and a key this short can be recovered from a single '
        f'captured token.',
        hint=hint, id='ragchat.E008',
    )]


@register(RAGCHAT, deploy=True)
def check_production_secrets(app_configs, **kwargs):
    """Things that are merely untidy in development and dangerous in production."""
    problems = []

    if settings.DEBUG:
        return problems

    if getattr(settings, 'DEFAULT_ADMIN_PASSWORD', ''):
        problems.append(
            Warning(
                'DEFAULT_ADMIN_PASSWORD is set in the environment of a running '
                'production process.',
                hint='It is only needed by `manage.py create_admin` at deploy '
                     'time. Leaving it in the running service means the admin '
                     'password is readable from anything that can dump the '
                     'environment.',
                id='ragchat.W001',
            )
        )

    if not getattr(settings, 'GROQ_API_KEY', ''):
        problems.append(
            Warning(
                'No LLM API key is configured; every chat request will fail.',
                hint='Set GROQ_API_KEY.',
                id='ragchat.W002',
            )
        )

    return problems
