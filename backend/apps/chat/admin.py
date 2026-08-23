"""Django Admin for conversations, messages and feedback.

The feedback screens are the interesting ones: a bad-answer queue that an admin
can actually work through is what turns thumbs-down clicks into a list of
retrieval problems to fix.
"""
from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Conversation,
    ConversationStatus,
    FeedbackRating,
    Message,
    MessageFeedback,
    MessageRole,
)

_ROLE_COLOURS = {
    MessageRole.USER: ('#1d4ed8', '#dbeafe'),
    MessageRole.ASSISTANT: ('#5b21b6', '#ede9fe'),
    MessageRole.SYSTEM: ('#374151', '#e5e7eb'),
}


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    max_num = 0
    can_delete = False
    fields = ('created_at', 'role', 'excerpt', 'source_count', 'total_ms')
    readonly_fields = fields
    ordering = ('created_at',)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Message')
    def excerpt(self, obj):
        return obj.content[:160] + ('...' if len(obj.content) > 160 else '')

    @admin.display(description='Sources')
    def source_count(self, obj):
        return len(obj.sources or [])


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'status_pill', 'message_count',
                    'document_total', 'last_message_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'owner__username', 'owner__email', 'last_message_preview')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('owner',)
    # M2M to documents: a horizontal filter beats a multi-select listing every
    # document in the system.
    filter_horizontal = ('documents',)
    list_select_related = ('owner',)
    inlines = [MessageInline]
    readonly_fields = ('id', 'legacy_mongo_id', 'message_count', 'last_message_at',
                       'last_message_preview', 'created_at', 'updated_at')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_documents=Count('documents'))

    @admin.display(description='Status', ordering='status')
    def status_pill(self, obj):
        fg, bg = (('#047857', '#d1fae5') if obj.status == ConversationStatus.ACTIVE
                  else ('#6b7280', '#f3f4f6'))
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
            fg, bg, obj.get_status_display(),
        )

    @admin.display(description='Docs', ordering='_documents')
    def document_total(self, obj):
        return obj._documents


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'role_pill', 'conversation_title', 'excerpt',
                    'source_count', 'model_name', 'total_ms', 'total_tokens')
    list_filter = ('role', 'provider', 'created_at')
    search_fields = ('content', 'conversation__title', 'conversation__owner__email')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('conversation',)
    list_select_related = ('conversation', 'conversation__owner')
    list_per_page = 50

    readonly_fields = (
        'id', 'legacy_mongo_id', 'conversation', 'role', 'content', 'sources',
        'provider', 'model_name', 'prompt_tokens', 'completion_tokens',
        'total_tokens', 'retrieval_ms', 'generation_ms', 'total_ms',
        'chunks_retrieved', 'error', 'created_at', 'feedback_link',
    )
    fieldsets = (
        (None, {'fields': ('id', 'conversation', 'role', 'content', 'created_at')}),
        ('Citations', {'fields': ('sources',)}),
        ('Generation', {
            'fields': ('provider', 'model_name', 'prompt_tokens', 'completion_tokens',
                       'total_tokens', 'chunks_retrieved', 'error'),
        }),
        ('Latency', {'fields': ('retrieval_ms', 'generation_ms', 'total_ms')}),
        ('Feedback', {'fields': ('feedback_link',)}),
        ('Migration', {'classes': ('collapse',), 'fields': ('legacy_mongo_id',)}),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description='Role', ordering='role')
    def role_pill(self, obj):
        fg, bg = _ROLE_COLOURS.get(obj.role, ('#374151', '#e5e7eb'))
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
            fg, bg, obj.get_role_display(),
        )

    @admin.display(description='Conversation', ordering='conversation__title')
    def conversation_title(self, obj):
        return obj.conversation.title

    @admin.display(description='Message')
    def excerpt(self, obj):
        return obj.content[:100] + ('...' if len(obj.content) > 100 else '')

    @admin.display(description='Sources')
    def source_count(self, obj):
        return len(obj.sources or [])

    @admin.display(description='Feedback')
    def feedback_link(self, obj):
        feedback = getattr(obj, 'feedback', None)
        if feedback is None:
            return 'none'
        url = reverse('admin:chat_messagefeedback_change', args=[feedback.pk])
        return mark_safe(  # noqa: S308 - values are ours, not user input
            f'<a href="{url}">{feedback.get_rating_display()}'
            f'{" — " + feedback.get_reason_display() if feedback.reason else ""}</a>'
        )


@admin.register(MessageFeedback)
class MessageFeedbackAdmin(admin.ModelAdmin):
    """The bad-answer review queue.

    Defaults to unreviewed negatives, because that is the only view anyone
    opens this page to look at.
    """

    list_display = ('created_at', 'rating_pill', 'reason', 'user',
                    'question_excerpt', 'answer_excerpt', 'reviewed')
    list_filter = ('rating', 'reason', 'reviewed', 'created_at')
    search_fields = ('comment', 'message__content', 'user__email', 'user__username')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('message', 'user')
    list_select_related = ('message', 'message__conversation', 'user')
    list_editable = ('reviewed',)
    actions = ('mark_reviewed', 'mark_unreviewed')

    readonly_fields = ('id', 'message', 'user', 'rating', 'reason', 'comment',
                       'created_at', 'updated_at', 'question_excerpt',
                       'answer_excerpt', 'retrieved_sources')

    @admin.display(description='Rating', ordering='rating')
    def rating_pill(self, obj):
        helpful = obj.rating == FeedbackRating.HELPFUL
        fg, bg = ('#047857', '#d1fae5') if helpful else ('#b91c1c', '#fee2e2')
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
            fg, bg, obj.get_rating_display(),
        )

    @admin.display(description='Question')
    def question_excerpt(self, obj):
        """The user turn immediately before the rated answer.

        A thumbs-down is unreadable without it — "this answer was wrong" means
        nothing until you know what was asked.
        """
        previous = (
            Message.objects
            .filter(
                conversation_id=obj.message.conversation_id,
                role=MessageRole.USER,
                created_at__lt=obj.message.created_at,
            )
            .order_by('-created_at')
            .values_list('content', flat=True)
            .first()
        )
        if not previous:
            return '—'
        return previous[:140] + ('...' if len(previous) > 140 else '')

    @admin.display(description='Answer')
    def answer_excerpt(self, obj):
        content = obj.message.content
        return content[:140] + ('...' if len(content) > 140 else '')

    @admin.display(description='Retrieved sources')
    def retrieved_sources(self, obj):
        sources = obj.message.sources or []
        if not sources:
            return 'nothing was retrieved for this answer'
        rows = ''.join(
            '<li>{} — page {} (score {})</li>'.format(
                s.get('document_name', '?'),
                s.get('page_number', '?'),
                s.get('similarity_score', '?'),
            )
            for s in sources
        )
        return mark_safe(f'<ul style="margin:0;padding-left:18px;">{rows}</ul>')  # noqa: S308

    @admin.action(description='Mark selected as reviewed')
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(reviewed=True)
        self.message_user(request, f'{updated} marked reviewed.')

    @admin.action(description='Mark selected as not reviewed')
    def mark_unreviewed(self, request, queryset):
        updated = queryset.update(reviewed=False)
        self.message_user(request, f'{updated} reopened.')
