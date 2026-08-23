"""Django Admin for analytics events."""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event_type', 'user', 'summary')
    list_filter = ('event_type', 'created_at')
    search_fields = ('user__username', 'user__email', 'event_type')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('user',)
    list_select_related = ('user',)
    list_per_page = 100

    readonly_fields = ('user', 'event_type', 'metadata', 'created_at', 'pretty_metadata')
    exclude = ('metadata',)

    # Events are a record of what happened. Editing one would make the
    # dashboard lie, and there is no reason to create one by hand.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Detail')
    def summary(self, obj):
        meta = obj.metadata or {}
        interesting = ('filename', 'document_id', 'session_id', 'method',
                       'chunks_retrieved', 'question_length')
        parts = [f'{k}={meta[k]}' for k in interesting if k in meta]
        return ', '.join(parts) or '—'

    @admin.display(description='Metadata')
    def pretty_metadata(self, obj):
        return format_html(
            '<pre style="margin:0;white-space:pre-wrap;">{}</pre>',
            json.dumps(obj.metadata or {}, indent=2, default=str),
        )
