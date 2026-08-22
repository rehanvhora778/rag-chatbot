"""Server-Sent Events for streaming answers.

SSE rather than WebSockets, deliberately. The data flows one way — the server
sends tokens, the client sends nothing until the next question — and SSE is
plain HTTP: it works through the existing JWT authentication, the existing
CORS configuration and a WSGI deployment, none of which is true of WebSockets.
Adding Channels, an ASGI server and a Redis channel layer to push text in one
direction would be a lot of moving parts for no capability.

**Ordering matters more than it looks.** Citations are sent *before* the first
token, not after the answer. The UI can then render Sources immediately and
fill the answer in above them, instead of the layout jumping when the sources
arrive at the end — and a user who only wanted to know which page something
came from has it straight away.

**The turn is persisted by the generator, not the view.** A streamed response
has already returned headers by the time the first token is produced, so there
is no later point at which the view can save anything. If the generator did not
do it, a streamed conversation would vanish on refresh.
"""
import json
import logging
from typing import Any, Iterator

from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)

# Sent every so often so intermediaries that time out an idle connection keep
# it open. A comment line is valid SSE and is ignored by every client.
KEEPALIVE = ': keep-alive\n\n'


def sse(event: str, data: dict[str, Any]) -> str:
    """One SSE frame.

    ``json.dumps`` handles the part that bites people writing this by hand: a
    payload containing a newline would otherwise terminate the frame early and
    the client would see a truncated event. Encoding to JSON means the data
    line never contains a raw newline.
    """
    return f'event: {event}\ndata: {json.dumps(data, default=str)}\n\n'


def stream_response(generator: Iterator[str]) -> StreamingHttpResponse:
    """Wrap an SSE generator in a response configured not to be buffered.

    Every header here exists because something in the path between Django and
    the browser will otherwise hold the whole response until it completes,
    turning a stream into a slow ordinary reply:

    * ``Cache-Control: no-cache`` — the browser must not replay a stream.
    * ``X-Accel-Buffering: no`` — nginx buffers proxied responses by default,
      which is exactly what must not happen here.
    * ``Connection: keep-alive`` — the connection stays open between events.
    """
    response = StreamingHttpResponse(
        generator, content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    return response


def chat_event_stream(user_id: int, conversation_id: str, question: str,
                      document_ids: list[str]) -> Iterator[str]:
    """Answer a question, yielding SSE frames, and persist the turn at the end.

    Errors are yielded as an ``error`` event rather than raised. Once streaming
    has begun the status code is already sent, so raising would drop the
    connection and leave the browser unable to distinguish a failure from a
    network problem.
    """
    from rag.chains import rag_chain
    from repositories.factory import get_conversation_repository
    from services.rag_pipeline import resolve_index_keys

    repository = get_conversation_repository()
    answer_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    try:
        history = _recent_history(repository, conversation_id, user_id)
        keys = resolve_index_keys(user_id, document_ids)

        for event in rag_chain.stream(
            user_id=user_id,
            question=question,
            document_keys=keys,
            history=history,
        ):
            kind = event.get('type')

            if kind == 'sources':
                citations = event.get('citations', [])
                yield sse('sources', {
                    'citations': citations,
                    'retrieval_ms': event.get('retrieval_ms'),
                })

            elif kind == 'token':
                answer_parts.append(event['text'])
                yield sse('token', {'text': event['text']})

            elif kind == 'security':
                # Surfaced so the UI can warn that a document contains what
                # looks like an embedded instruction. Never blocks the answer.
                yield sse('security', {'findings': event.get('findings', [])})

            elif kind == 'error':
                yield sse('error', {'message': event.get('message', 'Generation failed.')})
                return

            elif kind == 'done':
                metrics = event

    except Exception as exc:
        logger.error('Streaming failed for conversation %s: %s',
                     conversation_id, exc, exc_info=True)
        yield sse('error', {'message': 'Failed to generate a response. Please try again.'})
        return

    answer = ''.join(answer_parts)

    # Persisted here because the view cannot: the response headers went out
    # before the first token existed.
    message_id = ''
    try:
        _user_message, assistant_message = repository.add_turn(
            conversation_id, user_id,
            question=question,
            answer=answer,
            sources=citations,
            provider=metrics.get('provider', ''),
            model_name=metrics.get('model', ''),
            retrieval_ms=metrics.get('retrieval_ms'),
            generation_ms=metrics.get('generation_ms'),
            total_ms=(metrics.get('retrieval_ms') or 0) + (metrics.get('generation_ms') or 0),
            chunks_retrieved=len(citations),
        )
        message_id = assistant_message.get('id', '')
    except Exception as exc:
        # The user has already read the answer; losing the transcript is bad
        # but not worth replacing a delivered answer with an error.
        logger.error('Could not persist the streamed turn for %s: %s',
                     conversation_id, exc, exc_info=True)

    _record_query_event(user_id, conversation_id, question, len(citations))

    # The message id arrives last because it does not exist until the turn is
    # saved — and the client needs it to attach feedback to this answer.
    yield sse('done', {
        'message_id': message_id,
        'refused': metrics.get('refused', False),
        'retrieval_ms': metrics.get('retrieval_ms'),
        'generation_ms': metrics.get('generation_ms'),
        'model': metrics.get('model', ''),
    })


def _recent_history(repository, conversation_id: str, user_id: int) -> list[dict]:
    from django.conf import settings

    from services.rag_pipeline import _trim_history

    return _trim_history(
        repository.recent_history(
            conversation_id, user_id, settings.CONVERSATION_MEMORY_TURNS,
        )
    )


def _record_query_event(user_id: int, conversation_id: str, question: str,
                        citation_count: int) -> None:
    from core.analytics import record_event
    from core.constants import EVENT_QUERY

    record_event(user_id, EVENT_QUERY, {
        'session_id': conversation_id,
        'question_length': len(question),
        'chunks_retrieved': citation_count,
        'streamed': True,
    })
