"""Abstract base models shared by every app.

These are abstract, so they create no tables of their own and do not need
``core`` to be an installed app.
"""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """``created_at`` / ``updated_at`` on everything that has a lifecycle."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """A UUID primary key, for anything whose id appears in a URL or an API body.

    Sequential integer ids leak two things through any endpoint that exposes
    them: how many rows exist, and what the neighbouring ids are. For a system
    whose central security property is that one user can never reach another
    user's documents, "guess the next id" should not even be a shape an attack
    can take — ownership checks are then the second line of defence rather than
    the only one.

    uuid4 rather than a time-ordered scheme: random keys do scatter B-tree
    inserts, but that cost only becomes visible at a scale far beyond a
    per-user document store, and uuid7 is not in the standard library for the
    Python version this project targets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class LegacyMongoIDModel(models.Model):
    """Remembers the MongoDB ``_id`` a row was migrated from.

    Two jobs, both temporary:

    * ``migrate_from_mongo`` is re-runnable because it can ask whether a given
      Mongo document has already been copied.
    * FAISS index files on disk are named after the Mongo document id
      (``indexes/<user_id>/<mongo_id>.index``). A migrated document has to keep
      resolving to the same filename or every existing index is orphaned —
      see ``Document.vector_index_key``.

    Dropped once the migration is verified and FAISS is retired.
    """

    legacy_mongo_id = models.CharField(
        max_length=24,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text='The MongoDB ObjectId this row was migrated from, if any.',
    )

    class Meta:
        abstract = True
