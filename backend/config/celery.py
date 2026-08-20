"""Celery application.

`celery -A config worker` finds this through the `celery_app` export in
config/__init__.py.

Tasks live next to the code they belong to (apps/documents/tasks.py and so on)
and are found by autodiscovery, so adding one never means editing this file.
"""
import logging
import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('ragchatbot')

# Every CELERY_* name in Django settings becomes a Celery setting, minus the
# prefix — one place to configure the queue rather than two.
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**_kwargs):
    """Use Django's LOGGING for the worker too.

    Celery installs its own logging config by default, which means worker output
    is formatted differently from the API's and never reaches logs/app.log —
    so an ingestion failure would be invisible in the place you look for it.
    """
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Smoke test that the worker is reachable.

    docker compose exec api python -c \
        "from config.celery import debug_task; print(debug_task.delay().id)"
    """
    logging.getLogger(__name__).info('Celery is alive: request=%r', self.request)
    return 'ok'
