"""Project package.

Importing the Celery app here is what makes `@shared_task` work: Django loads
this package before any app, so by the time a tasks.py is imported there is an
app for its tasks to attach to.

Celery is optional — the project still runs without the broker installed, in
which case tasks fall back to running inline (see services/tasks.py).
"""

try:
    from .celery import app as celery_app

    __all__ = ('celery_app',)
except ImportError:  # celery not installed — e.g. a trimmed production image
    celery_app = None
    __all__ = ()
