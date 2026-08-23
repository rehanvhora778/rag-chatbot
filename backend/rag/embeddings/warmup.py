"""Import-race guards and model preloading for a server process.

Both functions here exist because of the same class of bug: a package whose
``__init__`` imports its own submodules is not safe to import from two threads
at once, and this project starts background threads (the embedding preload,
document processing) that all pull in the same heavy dependencies. Importing
them once on the main thread, before any worker exists, makes the race
impossible.

Called from ``apps/documents/apps.py`` at startup.
"""
import logging
import threading

logger = logging.getLogger(__name__)


def ensure_numpy_loaded():
    """Import numpy on the calling thread, before any worker thread can.

    numpy's package initialisation is not thread-safe the *first* time it runs:
    its __init__ imports its own submodules, so a second thread importing numpy
    at that moment sees a half-built module and dies with

        cannot import name 'matrix_power' from partially initialized module
        'numpy.linalg' (most likely due to a circular import)

    Every heavy dependency here pulls numpy in (onnxruntime, transformers,
    faiss, PyMuPDF, torch), and both the preload below and document processing
    run in background threads — so two of them racing to be first is a real
    possibility. Importing numpy once up front, on the main thread, makes that
    impossible: by the time any thread starts, sys.modules['numpy'] is complete
    and every later import is just a dict lookup.
    """
    import numpy  # noqa: F401


def ensure_http_stack_loaded():
    """Import urllib3/requests on the calling thread, before any worker thread can.

    Exactly the same hazard as ensure_numpy_loaded(), one layer down. urllib3's
    package initialisation imports its own submodules, so a second thread
    importing it mid-flight sees a half-built module and dies with

        cannot import name 'HTTPConnectionPool' from partially initialized
        module 'urllib3.connectionpool' (most likely due to a circular import)

    Three things race for this stack the moment a server process starts: the
    embedding preload thread (huggingface_hub -> requests -> urllib3), the
    Google sign-in import in apps.authentication.views (google-auth ->
    requests -> urllib3), and the Groq client. Whichever loses the race takes
    its feature down for the whole process lifetime — Google sign-in came back
    503 "google-auth is not installed" when it was in fact installed and fine.

    Importing it once here, on the main thread, makes the race impossible.
    """
    import requests  # noqa: F401
    import urllib3  # noqa: F401


def preload_embedding_model_async():
    """Warm the embedding model in a daemon thread so the first upload or chat
    message doesn't pay the model-load cost."""
    # Must happen here, on the caller's thread — not inside _load(). See above.
    ensure_numpy_loaded()
    ensure_http_stack_loaded()

    def _load():
        try:
            from rag.embeddings.onnx_backend import get_embedding_model

            get_embedding_model()
        except Exception as exc:
            logger.warning("Embedding model preload failed: %s", exc)

    threading.Thread(target=_load, name='embedding-preload', daemon=True).start()
