"""Document, chunk and collection models.

This is where the vectors live once ``VECTOR_BACKEND=pgvector``: a chunk row
carries its own embedding and its own full-text index, so a hybrid search is
two indexes on one table rather than a FAISS file, a Mongo query and a join
between them.
"""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MinValueValidator
from django.db import models
from pgvector.django import HnswIndex, VectorField

from core.models import LegacyMongoIDModel, TimeStampedModel, UUIDModel

# The vector column's width is fixed in the database schema, so it cannot be a
# setting that is read at runtime — changing it is a migration, not a config
# change. It is declared here and cross-checked against EMBEDDING_DIMENSION by
# a system check (see apps.py), so a mismatch is reported at startup instead of
# as an opaque insert error on the first upload after swapping models.
EMBEDDING_DIM = 384


class DocumentStatus(models.TextChoices):
    """Lifecycle of an uploaded file.

    The stored values are the same four strings the MongoDB implementation
    used, because the React app compares against them directly. `PENDING` is
    what the UI presents as "Queued".
    """

    PENDING = 'pending', 'Queued'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class DocumentCollection(UUIDModel, TimeStampedModel):
    """An optional folder a user can group documents into."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='collections',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'name'], name='uniq_collection_name_per_owner'
            ),
        ]

    def __str__(self):
        return self.name


class Document(UUIDModel, TimeStampedModel, LegacyMongoIDModel):
    """One uploaded file and everything known about processing it."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    collection = models.ForeignKey(
        DocumentCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )

    # --- The file ---
    original_filename = models.CharField(max_length=255)
    # The randomised name it is stored under. Never derived from the uploaded
    # name, so a filename like "../../settings.py" cannot escape the media root.
    stored_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=1024)
    file_type = models.CharField(max_length=16)
    file_size = models.BigIntegerField(validators=[MinValueValidator(0)])
    # SHA-256. Uniqueness per owner is what makes "you already uploaded this"
    # a database guarantee rather than a check that two concurrent uploads can
    # both pass before either inserts.
    file_hash = models.CharField(max_length=64, db_index=True)

    # --- Processing ---
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING,
    )
    error_message = models.TextField(blank=True)
    # The Celery task currently owning this document, so a stuck document can
    # be traced to a specific task and revoked.
    task_id = models.CharField(max_length=64, blank=True, db_index=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    processing_duration_ms = models.IntegerField(null=True, blank=True)

    # --- Results ---
    page_count = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)
    chunk_count = models.IntegerField(default=0)
    vector_count = models.IntegerField(default=0)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'file_hash'], name='uniq_document_hash_per_owner'
            ),
        ]
        indexes = [
            # The documents list: this user's files, newest first.
            models.Index(fields=['owner', '-created_at'], name='doc_owner_created_idx'),
            # The status poll the upload screen runs, and the stale-document sweep.
            models.Index(fields=['owner', 'status'], name='doc_owner_status_idx'),
            models.Index(fields=['status', 'created_at'], name='doc_status_created_idx'),
        ]

    def __str__(self):
        return f'{self.original_filename} ({self.get_status_display()})'

    @property
    def vector_index_key(self) -> str:
        """Filename stem for this document's FAISS index.

        Migrated documents keep using their old MongoDB id, because that is the
        name the index file on disk already has. Anything created after the
        migration uses its UUID. Only the FAISS backend needs this; pgvector
        stores vectors on the chunk rows and never touches the filesystem.
        """
        return self.legacy_mongo_id or str(self.pk)

    @property
    def is_ready(self) -> bool:
        return self.status == DocumentStatus.COMPLETED


class DocumentChunk(UUIDModel):
    """A passage of a document, with its embedding and its full-text index."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='chunks',
    )
    # Denormalised from document.owner on purpose.
    #
    # Every retrieval query filters by owner. Reaching the owner through a join
    # to documents would mean the planner has to combine the join with an
    # approximate-nearest-neighbour scan, and an HNSW index cannot be used to
    # satisfy a predicate it does not contain — the filter would be applied
    # after the vector scan had already picked its candidates, which is how a
    # user with few documents on a busy instance ends up retrieving nothing.
    # Holding owner_id on the chunk keeps the filter and the vector index on the
    # same table. It is written once at ingestion and never updated.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chunks',
    )

    content = models.TextField()
    chunk_index = models.IntegerField()
    page_number = models.IntegerField(default=1)
    start_char = models.IntegerField(default=0)
    end_char = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)

    # --- Retrieval ---
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True, blank=True)
    # Populated at ingestion from `content`. Kept as a stored column rather than
    # computed per query because to_tsvector over every chunk on every search is
    # exactly the work the index exists to avoid.
    content_tsv = SearchVectorField(null=True, editable=False)

    # Room for per-chunk provenance (section heading, table id, OCR flag)
    # without a migration each time something new is worth recording.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document_id', 'chunk_index']
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'chunk_index'], name='uniq_chunk_index_per_document'
            ),
        ]
        indexes = [
            models.Index(fields=['owner'], name='chunk_owner_idx'),
            models.Index(fields=['document', 'chunk_index'], name='chunk_doc_order_idx'),
            # The vector and full-text indexes are PostgreSQL-only and are
            # created in a separate, vendor-guarded migration so that
            # `migrate` still succeeds on the SQLite default.
        ]

    def __str__(self):
        return f'{self.document_id} #{self.chunk_index} (p{self.page_number})'

    @property
    def preview(self) -> str:
        return self.content[:120] + ('...' if len(self.content) > 120 else '')


# Index definitions kept beside the model they belong to, but attached by the
# vendor-guarded migration rather than by Meta.indexes.
#
# HNSW over cosine distance, because the embeddings are L2-normalised — cosine
# and inner product rank identically, and cosine is what the rest of the
# pipeline reports. m/ef_construction are pgvector's defaults: good recall
# without making ingestion of a large document noticeably slower.
CHUNK_EMBEDDING_INDEX = HnswIndex(
    name='chunk_embedding_hnsw_idx',
    fields=['embedding'],
    m=16,
    ef_construction=64,
    opclasses=['vector_cosine_ops'],
)

CHUNK_FTS_INDEX = GinIndex(fields=['content_tsv'], name='chunk_content_tsv_gin_idx')
