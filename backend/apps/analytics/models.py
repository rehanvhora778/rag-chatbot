"""Analytics events.

Append-only and high volume, so this is the one table that keeps a plain
integer primary key: the ids are never exposed in an API, and a monotonic key
keeps inserts at the end of the index instead of scattered through it.
"""
from django.conf import settings
from django.db import models


class EventType(models.TextChoices):
    """The stored values match the strings the MongoDB implementation used, so
    events copied by ``migrate_from_mongo`` need no translation and the
    existing dashboard queries keep working."""

    DOCUMENT_UPLOAD = 'document_upload', 'Document uploaded'
    CHAT_QUERY = 'chat_query', 'Chat query'
    SUMMARY_GENERATED = 'summary_generated', 'Summary generated'
    PDF_EXPORT = 'pdf_export', 'PDF export'
    USER_LOGIN = 'user_login', 'User login'
    DOCUMENT_FAILED = 'document_failed', 'Document processing failed'
    FEEDBACK_GIVEN = 'feedback_given', 'Feedback given'


class AnalyticsEvent(models.Model):
    # SET_NULL rather than CASCADE: deleting an account must remove that
    # person's documents and conversations, but the fact that N uploads
    # happened last Tuesday is not personal data once it is detached, and
    # cascading would silently rewrite history every time an account is closed.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_events',
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='evt_user_created_idx'),
            models.Index(fields=['event_type', '-created_at'], name='evt_type_created_idx'),
        ]

    def __str__(self):
        return f'{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M}'
