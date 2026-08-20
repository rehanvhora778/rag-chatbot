"""Conversation, message and feedback models.

A message stores not just what was said but how it was produced — which model,
how long each stage took, how many chunks came back, what it cost in tokens.
That is what makes the analytics dashboard and the evaluation harness possible
without a second logging pipeline, and it is why latency and token fields live
on the row rather than only in a log line.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.documents.models import Document
from core.models import LegacyMongoIDModel, TimeStampedModel, UUIDModel


class ConversationStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    ARCHIVED = 'archived', 'Archived'


class MessageRole(models.TextChoices):
    USER = 'user', 'User'
    ASSISTANT = 'assistant', 'Assistant'
    SYSTEM = 'system', 'System'


class FeedbackRating(models.IntegerChoices):
    UNHELPFUL = -1, 'Not helpful'
    HELPFUL = 1, 'Helpful'


class FeedbackReason(models.TextChoices):
    INCORRECT = 'incorrect', 'Incorrect answer'
    IRRELEVANT = 'irrelevant', 'Irrelevant context'
    MISSING = 'missing', 'Missing information'
    HALLUCINATION = 'hallucination', 'Made something up'
    OTHER = 'other', 'Other'


class Conversation(UUIDModel, TimeStampedModel, LegacyMongoIDModel):
    """A chat grounded in a chosen set of the user's documents."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations',
    )
    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
    )

    # Which documents this conversation may retrieve from. A real many-to-many
    # rather than the array of id strings the Mongo version stored: deleting a
    # document now removes it from every conversation automatically instead of
    # leaving an id behind that retrieval silently skips.
    documents = models.ManyToManyField(
        Document,
        related_name='conversations',
        blank=True,
    )

    # Denormalised so the sidebar can render without touching the messages
    # table. Maintained by the chat service when a turn completes.
    message_count = models.IntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at'], name='conv_owner_created_idx'),
            models.Index(fields=['owner', 'status'], name='conv_owner_status_idx'),
        ]

    def __str__(self):
        return self.title

    @property
    def is_archived(self) -> bool:
        return self.status == ConversationStatus.ARCHIVED


class Message(UUIDModel, LegacyMongoIDModel):
    """One turn. Assistant rows also carry how the answer was produced."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField()

    # The citations shown under an answer: document id, name, page, score and
    # the quoted excerpt. Kept as JSON rather than its own table because it is
    # written once, read whole, and never queried across rows.
    sources = models.JSONField(default=list, blank=True)

    # --- How this answer was produced (assistant messages only) ---
    provider = models.CharField(max_length=32, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    retrieval_ms = models.IntegerField(null=True, blank=True)
    generation_ms = models.IntegerField(null=True, blank=True)
    total_ms = models.IntegerField(null=True, blank=True)
    chunks_retrieved = models.IntegerField(null=True, blank=True)
    # Set when the turn failed, so a broken answer is still part of the
    # transcript instead of a gap the user cannot ask about.
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            # The transcript read: one conversation, in order.
            models.Index(fields=['conversation', 'created_at'], name='msg_conv_created_idx'),
            models.Index(fields=['role', 'created_at'], name='msg_role_created_idx'),
        ]

    def __str__(self):
        return f'{self.role}: {self.content[:60]}'

    @property
    def is_assistant(self) -> bool:
        return self.role == MessageRole.ASSISTANT


class MessageFeedback(UUIDModel, TimeStampedModel):
    """A thumbs up or down on one assistant answer.

    One row per message: rating a message again updates the existing verdict
    rather than stacking a second one, which is what the one-to-one enforces.
    """

    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name='feedback',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback',
    )
    rating = models.IntegerField(
        choices=FeedbackRating.choices,
        validators=[MinValueValidator(-1), MaxValueValidator(1)],
    )
    # Only meaningful on a negative rating; the UI asks for it there.
    reason = models.CharField(
        max_length=32,
        choices=FeedbackReason.choices,
        blank=True,
    )
    comment = models.TextField(blank=True)
    # Cleared by an admin once a bad answer has been looked at, so the review
    # queue is a query rather than a spreadsheet someone maintains by hand.
    reviewed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['rating', '-created_at'], name='fb_rating_created_idx'),
            models.Index(fields=['reviewed', 'rating'], name='fb_reviewed_rating_idx'),
        ]

    def __str__(self):
        return f'{self.get_rating_display()} on {self.message_id}'
