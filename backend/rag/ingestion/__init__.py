"""Ingestion — turning an uploaded file into searchable, embedded chunks.

    file -> extract text (per page) -> chunk -> embed -> store

It lives in ``rag/`` rather than in the documents app because it is the write
side of retrieval: chunk size, overlap and the embedding model are the same
decisions on both sides, and a change to one that is not matched in the other
silently degrades every answer. Keeping them in one package is what makes that
hard to get wrong.

Nothing here knows about HTTP, and the only Django it touches is settings and
the repository it writes through.
"""
