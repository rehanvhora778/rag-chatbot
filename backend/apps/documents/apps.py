from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.documents'
    label = 'documents'
    verbose_name = 'Documents'

    def ready(self):
        """Prepare a server process for background work.

        Two things happen here, both only in a process that actually serves
        requests (management commands like migrate/shell are skipped):

          1. numpy and the urllib3/requests stack are imported on this, the
             main thread. Uploads are processed in background threads, so
             without this the first two of them can race to import a package
             and one crashes on a half-built module.
          2. The embedding model is warmed in the background, so the first
             upload or chat message doesn't wait for it to load.
        """
        import os
        import sys

        from django.conf import settings

        argv = ' '.join(sys.argv)
        if 'runserver' in argv:
            # With autoreload, ready() runs in both the watcher parent and the
            # worker child — only the child (RUN_MAIN=true) serves requests.
            if os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in argv:
                return
        elif 'manage.py' in argv:
            return  # some other management command — no server here

        # Step 1 runs whether or not the preload is enabled — the thread race it
        # prevents comes from concurrent uploads, not from the preload alone.
        from services.embeddings import (
            ensure_http_stack_loaded,
            ensure_numpy_loaded,
            preload_embedding_model_async,
        )
        ensure_numpy_loaded()
        ensure_http_stack_loaded()

        if getattr(settings, 'EMBEDDING_PRELOAD', True):
            preload_embedding_model_async()
