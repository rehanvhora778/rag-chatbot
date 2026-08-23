-- Runs once, when initdb creates an empty data directory.
--
-- CREATE EXTENSION needs superuser rights, which the application role does not
-- have. Doing it here, as the bootstrap superuser, means Django's migrations
-- can create vector columns and indexes as an ordinary user later.
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram similarity, used for fuzzy filename/title matching in the document
-- and conversation search endpoints.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent, so a full-text search for "resume" also matches "résumé".
CREATE EXTENSION IF NOT EXISTS unaccent;
