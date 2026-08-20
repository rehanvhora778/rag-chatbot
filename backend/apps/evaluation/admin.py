"""Admin for RAG configurations and evaluation runs.

The run pages are read-only: a run is a measurement, and a measurement someone
can edit afterwards is not evidence of anything.
"""
import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    RAGConfiguration,
    RunStatus,
)

_RUN_COLOURS = {
    RunStatus.PENDING: ('#6b7280', '#f3f4f6'),
    RunStatus.RUNNING: ('#b45309', '#fef3c7'),
    RunStatus.COMPLETED: ('#047857', '#d1fae5'),
    RunStatus.FAILED: ('#b91c1c', '#fee2e2'),
}


@admin.register(RAGConfiguration)
class RAGConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'active_badge', 'top_k', 'fetch_k', 'hybrid_enabled',
                    'rerank_enabled', 'llm_model', 'updated_at')
    list_filter = ('is_active', 'hybrid_enabled', 'rerank_enabled', 'query_rewrite')
    search_fields = ('name', 'description', 'llm_model')
    readonly_fields = ('id', 'created_at', 'updated_at')
    actions = ('activate',)

    fieldsets = (
        (None, {'fields': ('id', 'name', 'description', 'is_active')}),
        ('Chunking', {
            'description': 'Changing these invalidates every existing chunk — '
                           'documents must be reprocessed before the numbers mean '
                           'anything.',
            'fields': ('chunk_size', 'chunk_overlap'),
        }),
        ('Retrieval', {
            'fields': ('top_k', 'fetch_k', 'use_mmr', 'mmr_lambda', 'min_similarity'),
        }),
        ('Hybrid search', {
            'fields': ('hybrid_enabled', 'keyword_top_k', 'rrf_k',
                       'rerank_enabled', 'rerank_model', 'query_rewrite'),
        }),
        ('Generation', {
            'fields': ('llm_provider', 'llm_model', 'temperature',
                       'max_output_tokens', 'max_context_chars', 'embedding_model'),
        }),
        (None, {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Active', ordering='is_active')
    def active_badge(self, obj):
        if not obj.is_active:
            return '—'
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:#047857;background:#d1fae5;">'
            'ACTIVE</span>'
        )

    @admin.action(description='Make this the active configuration')
    def activate(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one configuration.', level='ERROR')
            return
        config = queryset.first()
        # Deactivate first: the partial unique index permits only one active
        # row, so setting the new one while the old is still active would fail.
        RAGConfiguration.objects.filter(is_active=True).update(is_active=False)
        config.is_active = True
        config.save(update_fields=['is_active', 'updated_at'])
        self.message_user(request, f'"{config.name}" is now active.')


class EvaluationCaseInline(admin.TabularInline):
    model = EvaluationCase
    extra = 0
    fields = ('question', 'expected_answer', 'must_refuse', 'expected_document_names')


@admin.register(EvaluationDataset)
class EvaluationDatasetAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_cases', 'refusal_cases', 'created_at')
    search_fields = ('name', 'description')
    inlines = [EvaluationCaseInline]
    readonly_fields = ('id', 'created_at', 'updated_at')

    @admin.display(description='Cases')
    def total_cases(self, obj):
        return obj.cases.count()

    @admin.display(description='Control (must refuse)')
    def refusal_cases(self, obj):
        """How many cases check that the system declines to answer.

        A dataset with none of these cannot detect a model answering from its
        own knowledge, which is the failure this whole project exists to avoid.
        """
        return obj.cases.filter(must_refuse=True).count()


@admin.register(EvaluationCase)
class EvaluationCaseAdmin(admin.ModelAdmin):
    list_display = ('question_excerpt', 'dataset', 'must_refuse', 'created_at')
    list_filter = ('dataset', 'must_refuse')
    search_fields = ('question', 'expected_answer')
    raw_id_fields = ('dataset',)
    list_select_related = ('dataset',)

    @admin.display(description='Question')
    def question_excerpt(self, obj):
        return obj.question[:90] + ('...' if len(obj.question) > 90 else '')


class EvaluationResultInline(admin.TabularInline):
    model = EvaluationResult
    extra = 0
    max_num = 0
    can_delete = False
    fields = ('case_question', 'passed', 'refused', 'answer_excerpt', 'total_ms')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Question')
    def case_question(self, obj):
        return obj.case.question[:70]

    @admin.display(description='Answer')
    def answer_excerpt(self, obj):
        return (obj.answer or obj.error)[:90]


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status_pill', 'dataset', 'configuration',
                    'recall', 'faithful', 'correct', 'pass_rate', 'duration')
    list_filter = ('status', 'dataset', 'created_at')
    search_fields = ('label', 'dataset__name')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    raw_id_fields = ('dataset', 'configuration', 'run_by')
    list_select_related = ('dataset', 'configuration')
    inlines = [EvaluationResultInline]

    readonly_fields = ('id', 'dataset', 'configuration', 'run_by', 'label', 'status',
                       'started_at', 'finished_at', 'created_at', 'updated_at',
                       'error_message', 'metrics_table', 'settings_table')
    exclude = ('metrics', 'settings_snapshot')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Status', ordering='status')
    def status_pill(self, obj):
        fg, bg = _RUN_COLOURS.get(obj.status, ('#374151', '#e5e7eb'))
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
            fg, bg, obj.get_status_display(),
        )

    def _metric(self, obj, key):
        value = (obj.metrics or {}).get(key)
        if value is None:
            return '—'
        return f'{value:.3f}' if isinstance(value, int | float) else str(value)

    @admin.display(description='Recall')
    def recall(self, obj):
        return self._metric(obj, 'retrieval_recall')

    @admin.display(description='Faithful')
    def faithful(self, obj):
        return self._metric(obj, 'faithfulness')

    @admin.display(description='Correct')
    def correct(self, obj):
        return self._metric(obj, 'answer_correctness')

    @admin.display(description='Passed')
    def pass_rate(self, obj):
        total = obj.results.count()
        if not total:
            return '—'
        return f'{obj.results.filter(passed=True).count()}/{total}'

    @admin.display(description='Duration')
    def duration(self, obj):
        seconds = obj.duration_seconds
        return f'{seconds:.1f}s' if seconds is not None else '—'

    @admin.display(description='Metrics')
    def metrics_table(self, obj):
        metrics = obj.metrics or {}
        if not metrics:
            return 'no metrics recorded'
        rows = ''.join(
            '<tr><td style="padding:2px 14px 2px 0;">{}</td>'
            '<td style="font-weight:600;">{}</td></tr>'.format(
                key, f'{value:.4f}' if isinstance(value, float) else value
            )
            for key, value in sorted(metrics.items())
        )
        return mark_safe(f'<table>{rows}</table>')  # noqa: S308 - keys/values are ours

    @admin.display(description='Settings at run time')
    def settings_table(self, obj):
        return format_html(
            '<pre style="margin:0;white-space:pre-wrap;">{}</pre>',
            json.dumps(obj.settings_snapshot or {}, indent=2, default=str),
        )


@admin.register(EvaluationResult)
class EvaluationResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'case_question', 'passed', 'refused', 'total_ms', 'created_at')
    list_filter = ('passed', 'refused', 'run')
    search_fields = ('case__question', 'answer')
    raw_id_fields = ('run', 'case')
    list_select_related = ('run', 'case')

    def has_add_permission(self, request):
        return False

    @admin.display(description='Question')
    def case_question(self, obj):
        return obj.case.question[:80]
