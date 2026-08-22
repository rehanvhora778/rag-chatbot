"""Request correlation and structured logging.

The problem this solves is specific. A user reports that a question returned
nothing useful. The answer involved a web request, a retrieval, an LLM call and
possibly a Celery task, each logging separately, and there is nothing in the log
that ties them together — so reconstructing what happened means grepping by
timestamp and hoping the instance was quiet.

A request id fixes that. It is generated once per request, attached to every log
record emitted while handling it, returned to the client in a response header,
and passed to any task the request queues. One id, one grep, the whole story.

It is stored in a ``ContextVar`` rather than on the request object, because the
code that needs to log is several layers below the view and threading a request
through the repository and the retriever to reach a log line would be worse than
the problem. ContextVars are per-thread and per-async-task, so a gunicorn worker
handling four requests on four threads keeps four separate values.
"""
import logging
import time
import uuid
from contextvars import ContextVar

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Empty rather than None so a log record never renders "request_id=None" for
# work that legitimately has no request — a management command, a beat job.
_request_id: ContextVar[str] = ContextVar('request_id', default='')
_user_id: ContextVar[str] = ContextVar('user_id', default='')

REQUEST_ID_HEADER = 'X-Request-ID'
# Accepted from the client so a request id assigned by a load balancer or an
# upstream service is preserved rather than replaced, which is what makes the
# id useful across more than one service.
INCOMING_HEADER = 'HTTP_X_REQUEST_ID'
MAX_INCOMING_LENGTH = 64


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value or '')


def get_user_id() -> str:
    return _user_id.get()


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class RequestContextFilter(logging.Filter):
    """Adds request_id and user_id to every log record.

    A filter rather than a formatter, because the fields have to exist on the
    record before any formatter runs — including the ones on handlers this
    module does not control.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or '-'
        record.user_id = _user_id.get() or '-'
        return True


class RequestContextMiddleware(MiddlewareMixin):
    """Assigns a request id, logs the outcome, and returns the id to the client.

    Slow requests are logged at WARNING with their duration. That is the line
    someone actually goes looking for when the app "feels slow", and without it
    the only evidence is a gap between two unrelated log entries.
    """

    # A RAG answer legitimately takes seconds; this is set well above that so
    # the warning means "unusual", not "normal for this endpoint".
    SLOW_REQUEST_MS = 5000

    def process_request(self, request):
        incoming = (request.META.get(INCOMING_HEADER) or '').strip()
        # Validated before use: this value reaches log files, and an unbounded
        # or newline-bearing string from a client could forge log entries.
        if incoming and len(incoming) <= MAX_INCOMING_LENGTH and incoming.isprintable():
            request_id = incoming
        else:
            request_id = new_request_id()

        _request_id.set(request_id)
        _user_id.set('')
        request.request_id = request_id
        request._started_at = time.perf_counter()

    def process_response(self, request, response):
        request_id = getattr(request, 'request_id', '') or _request_id.get()
        if request_id:
            response[REQUEST_ID_HEADER] = request_id

        started = getattr(request, '_started_at', None)
        if started is not None:
            duration_ms = (time.perf_counter() - started) * 1000

            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False):
                _user_id.set(str(user.pk))

            if duration_ms >= self.SLOW_REQUEST_MS:
                logger.warning(
                    'Slow request: %s %s -> %s in %.0fms',
                    request.method, request.path, response.status_code, duration_ms,
                )
            elif response.status_code >= 500:
                logger.error(
                    '%s %s -> %s in %.0fms',
                    request.method, request.path, response.status_code, duration_ms,
                )

        # Cleared so a pooled thread does not carry this request's id into the
        # next one, which would attribute one user's log lines to another.
        _request_id.set('')
        _user_id.set('')
        return response

    def process_exception(self, request, exception):
        logger.error(
            'Unhandled exception in %s %s: %s',
            request.method, request.path, exception, exc_info=True,
        )
        return None


def with_request_id(task_kwargs: dict) -> dict:
    """Attach the current request id to a task's kwargs.

    A document queued by an upload should be traceable back to the request that
    queued it. Passed explicitly because a Celery task runs in a different
    process, where the ContextVar is empty.
    """
    request_id = get_request_id()
    if request_id:
        return {**task_kwargs, 'request_id': request_id}
    return task_kwargs


class timed:
    """Context manager that logs how long a block took.

    Used around the stages of a RAG answer, so the log says which stage was slow
    rather than only that the answer was. Never suppresses an exception — a
    timing helper that swallowed errors would be a very effective way to hide
    them.

        with timed('retrieval', question=q):
            ...
    """

    def __init__(self, label: str, log=None, **context):
        self.label = label
        self.log = log or logger
        self.context = context
        self.elapsed_ms = 0.0

    def __enter__(self):
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.elapsed_ms = (time.perf_counter() - self._started) * 1000
        detail = ' '.join(f'{k}={v}' for k, v in self.context.items())
        if exc_type is None:
            self.log.info('%s took %.0fms %s', self.label, self.elapsed_ms, detail)
        else:
            self.log.error('%s failed after %.0fms %s: %s',
                           self.label, self.elapsed_ms, detail, exc)
        return False
