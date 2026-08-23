"""Django Admin for documents and chunks."""
from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Document, DocumentChunk, DocumentCollection, DocumentStatus

# Colours for the status pill. Kept here rather than on the model because it is
# presentation, and nothing outside the admin needs it.
_STATUS_COLOURS = {
    DocumentStatus.PENDING: ('#6b7280', '#f3f4f6'),
    DocumentStatus.PROCESSING: ('#b45309', '#fef3c7'),
    DocumentStatus.COMPLETED: ('#047857', '#d1fae5'),
    DocumentStatus.FAILED: ('#b91c1c', '#fee2e2'),
}


def status_badge(status: str, label: str) -> str:
    fg, bg = _STATUS_COLOURS.get(status, ('#374151', '#e5e7eb'))
    return format_html(
        '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
        'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
        fg, bg, label,
    )


class DocumentChunkInline(admin.TabularInline):
    """A read-only peek at the first few chunks of a document.

    ``extra = 0`` and no add permission: chunks are produced by the ingestion
    pipeline, and one typed by hand would have no embedding, so it would be
    invisible to vector search while still appearing in keyword results.
    """

    model = DocumentChunk
    extra = 0
    max_num = 0
    can_delete = False
    fields = ('chunk_index', 'page_number', 'word_count', 'has_embedding', 'preview')
    readonly_fields = fields
    ordering = ('chunk_index',)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(boolean=True, description='Vector')
    def has_embedding(self, obj):
        return obj.embedding is not None

    @admin.display(description='Text')
    def preview(self, obj):
        return obj.preview


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'original_filename', 'owner', 'status_pill', 'file_type',
        'size_display', 'page_count', 'chunk_count', 'processing_time', 'created_at',
    )
    list_filter = ('status', 'file_type', 'created_at')
    search_fields = ('original_filename', 'owner__username', 'owner__email', 'file_hash')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('owner',)
    # A text box rather than a dropdown that would load every account.
    raw_id_fields = ('owner', 'collection')
    inlines = [DocumentChunkInline]
    list_per_page = 50

    readonly_fields = (
        'id', 'legacy_mongo_id', 'file_hash', 'file_path', 'stored_filename',
        'file_size', 'page_count', 'word_count', 'chunk_count', 'vector_count',
        'processing_started_at', 'processing_completed_at', 'processing_duration_ms',
        'task_id', 'created_at', 'updated_at', 'chunk_link',
    )
    fieldsets = (
        ('File', {
            'fields': ('id', 'owner', 'collection', 'original_filename',
                       'file_type', 'file_size', 'stored_filename', 'file_path',
                       'file_hash'),
        }),
        ('Processing', {
            'fields': ('status', 'error_message', 'task_id',
                       'processing_started_at', 'processing_completed_at',
                       'processing_duration_ms'),
        }),
        ('Results', {
            'fields': ('page_count', 'word_count', 'chunk_count', 'vector_count',
                       'chunk_link', 'summary'),
        }),
        ('Migration', {
            'classes': ('collapse',),
            'fields': ('legacy_mongo_id', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Status', ordering='status')
    def status_pill(self, obj):
        return status_badge(obj.status, obj.get_status_display())

    @admin.display(description='Size', ordering='file_size')
    def size_display(self, obj):
        size = float(obj.file_size or 0)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'

    @admin.display(description='Took', ordering='processing_duration_ms')
    def processing_time(self, obj):
        if obj.processing_duration_ms is None:
            return '—'
        return f'{obj.processing_duration_ms / 1000:.1f}s'

    @admin.display(description='Chunks')
    def chunk_link(self, obj):
        url = reverse('admin:documents_documentchunk_changelist')
        return mark_safe(  # noqa: S308 - both values are ours, not user input
            f'<a href="{url}?document__id__exact={obj.pk}">'
            f'View {obj.chunk_count} chunk(s)</a>'
        )


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document_name', 'chunk_index', 'page_number', 'word_count',
                    'has_embedding', 'preview')
    list_filter = ('page_number', 'created_at')
    search_fields = ('content', 'document__original_filename')
    ordering = ('document', 'chunk_index')
    raw_id_fields = ('document', 'owner')
    list_select_related = ('document',)
    list_per_page = 50

    # The embedding is 384 floats and content_tsv is a machine-readable blob.
    # Rendering either into a form field produces an unusable page, so both are
    # summarised instead of shown.
    exclude = ('embedding', 'content_tsv')
    readonly_fields = ('id', 'created_at', 'embedding_summary', 'metadata')

    def has_add_permission(self, request):
        return False

    @admin.display(description='Document', ordering='document__original_filename')
    def document_name(self, obj):
        return obj.document.original_filename

    @admin.display(boolean=True, description='Vector')
    def has_embedding(self, obj):
        return obj.embedding is not None

    @admin.display(description='Text')
    def preview(self, obj):
        return obj.preview

    @admin.display(description='Embedding')
    def embedding_summary(self, obj):
        if obj.embedding is None:
            return 'not embedded'
        values = list(obj.embedding)
        head = ', '.join(f'{v:.4f}' for v in values[:6])
        return f'{len(values)} dimensions — [{head}, ...]'


@admin.register(DocumentCollection)
class DocumentCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'document_total', 'created_at')
    search_fields = ('name', 'owner__username', 'owner__email')
    raw_id_fields = ('owner',)
    list_select_related = ('owner',)
    ordering = ('owner', 'name')

    def get_queryset(self, request):
        # Annotated so the count column is one query rather than one per row.
        return super().get_queryset(request).annotate(_documents=Count('documents'))

    @admin.display(description='Documents', ordering='_documents')
    def document_total(self, obj):
        return obj._documents
