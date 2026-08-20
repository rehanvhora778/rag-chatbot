"""The currency the RAG layer passes around.

Retrieved passages are LangChain ``Document`` objects rather than a type
invented here. That is the whole reason for adopting langchain-core: a Document
is what its retrievers, rerankers and chains already speak, so a component
written against this project composes with one taken off the shelf, and the
reverse. Inventing a third passage type — after the repository's ``ChunkDTO``
and the API's citation dict — would buy nothing and mean writing the conversion
twice anyway.

**What this project takes from LangChain, and what it does not.**

It takes the *interfaces*: Document, Embeddings, BaseRetriever, prompt
templates. Those are small, stable, and make the pipeline composable.

It does not take the *implementations*. Most relevantly,
``RecursiveCharacterTextSplitter`` is not used, because it splits a document as
one continuous string and the page a passage came from is lost in the process.
Page numbers are not a detail here — every answer cites them, and the whole
promise of the product is that a claim can be checked against a page. The
existing chunker splits page by page and carries the number through, so it
stays.
"""
from typing import Any, Iterable, Optional

from langchain_core.documents import Document

# Metadata keys a retrieved Document carries. Named rather than typed as
# literals scattered through the code, because a typo in a metadata key is
# invisible until a citation renders as "Unknown, page None".
DOCUMENT_ID = 'document_id'
DOCUMENT_NAME = 'document_name'
PAGE_NUMBER = 'page_number'
CHUNK_ID = 'chunk_id'
CHUNK_INDEX = 'chunk_index'
SCORE = 'score'
# Set by the fusion step so a hybrid result can say which retriever found it —
# the difference between "the vector side found this" and "only the keyword
# side did" is most of what makes a hybrid retriever debuggable.
RETRIEVER = 'retriever'
RANKS = 'ranks'


def chunk_to_document(chunk: dict[str, Any]) -> Document:
    """Repository ChunkDTO -> LangChain Document."""
    return Document(
        page_content=chunk.get('content', ''),
        metadata={
            CHUNK_ID: chunk.get('chunk_id', ''),
            DOCUMENT_ID: chunk.get('document_id', ''),
            # 'Unknown' rather than '', matching document_to_chunk. The two
            # defaults have to agree: once the key exists with an empty string,
            # the fallback on the way back out never fires, and the citation
            # renders with a blank filename instead of saying it does not know.
            DOCUMENT_NAME: chunk.get('document_name') or 'Unknown',
            PAGE_NUMBER: chunk.get('page_number', 1),
            CHUNK_INDEX: chunk.get('chunk_index', 0),
            SCORE: float(chunk.get('similarity_score', 0.0)),
        },
    )


def document_to_chunk(document: Document) -> dict[str, Any]:
    """LangChain Document -> the dict shape the pipeline and citations expect.

    The API response shape predates this layer and is consumed by the React
    app, so the conversion lands on the existing keys rather than renaming
    anything.
    """
    meta = document.metadata or {}
    return {
        'chunk_id': meta.get(CHUNK_ID, ''),
        'document_id': meta.get(DOCUMENT_ID, ''),
        'document_name': meta.get(DOCUMENT_NAME, 'Unknown'),
        'page_number': meta.get(PAGE_NUMBER, 1),
        'chunk_index': meta.get(CHUNK_INDEX, 0),
        'content': document.page_content,
        'similarity_score': float(meta.get(SCORE, 0.0)),
    }


def documents_to_chunks(documents: Iterable[Document]) -> list[dict[str, Any]]:
    return [document_to_chunk(d) for d in documents]


def chunks_to_documents(chunks: Iterable[dict[str, Any]]) -> list[Document]:
    return [chunk_to_document(c) for c in chunks]


def score_of(document: Document) -> float:
    return float((document.metadata or {}).get(SCORE, 0.0))


def page_key(document: Document) -> tuple[str, int]:
    """The (document, page) pair a citation is deduplicated on."""
    meta = document.metadata or {}
    return meta.get(DOCUMENT_ID, ''), int(meta.get(PAGE_NUMBER, 0))


def identity(document: Document) -> str:
    """A stable key for one passage, for fusing result lists.

    The chunk id where there is one. Falling back to the text itself is not a
    nicety: the keyword and vector sides of a hybrid search must agree on when
    two results are the same passage, and a result missing its id would
    otherwise be fused as a distinct hit and counted twice.
    """
    meta = document.metadata or {}
    chunk_id = meta.get(CHUNK_ID)
    if chunk_id:
        return str(chunk_id)
    return f'{meta.get(DOCUMENT_ID, "")}#{meta.get(CHUNK_INDEX, "")}#{hash(document.page_content)}'


def truncate_to_budget(documents: list[Document],
                       max_chars: int,
                       minimum: int = 1) -> list[Document]:
    """Drop the lowest-ranked passages until the context fits.

    Whole passages are dropped rather than the last one being cut short: half a
    paragraph reads as a complete one to the model, and a fact truncated
    mid-sentence is exactly the kind of thing that gets cited confidently and
    wrongly.

    At least `minimum` passages are always kept — a context of nothing turns
    every question into a refusal, which is a worse failure than an oversized
    prompt.
    """
    if max_chars <= 0:
        return documents

    kept: list[Document] = []
    used = 0

    for index, document in enumerate(documents):
        length = len(document.page_content)
        if index >= minimum and used + length > max_chars:
            break
        kept.append(document)
        used += length

    return kept


def format_for_prompt(documents: list[Document],
                      multi_document: Optional[bool] = None) -> str:
    """Render passages as the labelled context block the grounding prompt expects.

    The label is what the model cites from, so it carries the page and — only
    when more than one file is in play — the filename. Adding the filename
    unconditionally would have single-document answers citing
    "(report.pdf, Page 4)" where "(Page 4)" is what a reader wants.
    """
    if multi_document is None:
        names = {
            (d.metadata or {}).get(DOCUMENT_NAME)
            for d in documents
            if (d.metadata or {}).get(DOCUMENT_NAME)
        }
        multi_document = len(names) > 1

    blocks = []
    for document in documents:
        meta = document.metadata or {}
        page = meta.get(PAGE_NUMBER)
        name = meta.get(DOCUMENT_NAME, '')

        if multi_document and name and page:
            header = f'[{name} — Page {page}]'
        elif page:
            header = f'[Page {page}]'
        else:
            header = '[Source]'

        blocks.append(f'{header}\n{document.page_content}')

    return '\n\n---\n\n'.join(blocks)
