"""PostgreSQL-only physical indexes for hybrid retrieval.

Three things are created here rather than through ``Meta.indexes``:

* an HNSW index over the embedding column (vector search)
* a GIN index over the tsvector column (keyword search)
* a trigger that keeps the tsvector column in step with ``content``

They are not in ``Meta.indexes`` because ``migrate`` still has to succeed on the
SQLite default — ``USING hnsw`` and ``USING gin`` are syntax SQLite rejects
outright. Declaring them in Meta would make Django emit AddIndex operations
that run unconditionally; doing it here means the whole migration is a no-op on
any non-PostgreSQL connection, and the model state Django compares against
during ``makemigrations --check`` is untouched, so this does not show up as a
permanently pending change.

The tsvector is maintained by a database trigger rather than in the ingestion
code on purpose. Three different paths write chunks — the ingestion task, the
Mongo migration command, and bulk operations from the shell — and a column that
each of them has to remember to populate is a column that will be wrong. A
trigger cannot be forgotten.
"""
from django.db import migrations

CHUNK_TABLE = 'documents_documentchunk'
DOCUMENT_TABLE = 'documents_document'

FORWARD_SQL = f"""
-- --------------------------------------------------------------------
-- Keyword half of hybrid retrieval
-- --------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ragchat_chunk_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunk_tsv_trigger ON {CHUNK_TABLE};

CREATE TRIGGER chunk_tsv_trigger
    BEFORE INSERT OR UPDATE OF content ON {CHUNK_TABLE}
    FOR EACH ROW EXECUTE FUNCTION ragchat_chunk_tsv_update();

-- Backfill anything already present (a no-op on a fresh database, and what
-- makes this migration correct when it runs after migrate_from_mongo).
UPDATE {CHUNK_TABLE}
   SET content_tsv = to_tsvector('english', COALESCE(content, ''))
 WHERE content_tsv IS NULL;

CREATE INDEX IF NOT EXISTS chunk_content_tsv_gin_idx
    ON {CHUNK_TABLE} USING gin (content_tsv);

-- --------------------------------------------------------------------
-- Vector half of hybrid retrieval
-- --------------------------------------------------------------------
-- Cosine distance: the embeddings are L2-normalised, so cosine and inner
-- product produce the same ranking, and cosine is the score the rest of the
-- pipeline reports. m=16 / ef_construction=64 are pgvector's defaults — good
-- recall without making ingestion of a large document noticeably slower.
CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw_idx
    ON {CHUNK_TABLE} USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- --------------------------------------------------------------------
-- Fuzzy filename matching for the documents list search box
-- --------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS doc_filename_trgm_idx
    ON {DOCUMENT_TABLE} USING gin (original_filename gin_trgm_ops);
"""

REVERSE_SQL = f"""
DROP INDEX IF EXISTS doc_filename_trgm_idx;
DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;
DROP INDEX IF EXISTS chunk_content_tsv_gin_idx;
DROP TRIGGER IF EXISTS chunk_tsv_trigger ON {CHUNK_TABLE};
DROP FUNCTION IF EXISTS ragchat_chunk_tsv_update();
"""


def _run_if_postgres(sql):
    """Execute `sql` only on a PostgreSQL connection."""

    def _inner(apps, schema_editor):
        if schema_editor.connection.vendor != 'postgresql':
            return
        schema_editor.execute(sql)

    return _inner


class Migration(migrations.Migration):
    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            _run_if_postgres(FORWARD_SQL),
            reverse_code=_run_if_postgres(REVERSE_SQL),
        ),
    ]
