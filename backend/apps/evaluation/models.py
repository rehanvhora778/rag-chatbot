"""RAG configuration and the evaluation harness's storage.

Configuration lives in the same app as evaluation on purpose. A retrieval
setting has no meaning on its own — ``top_k=6`` is neither good nor bad — it
only means something as "the configuration that scored 0.91 recall on this
dataset". Every run is therefore stamped with the configuration it ran against,
and comparing two configurations is a query rather than an exercise in
remembering what the settings were three weeks ago.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class RunStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class RAGConfiguration(UUIDModel, TimeStampedModel):
    """A named, complete set of the knobs that change retrieval or generation.

    Exactly one row may be active. When none is, the pipeline falls back to the
    values in Django settings, which is what keeps the project runnable with no
    database row at all.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)

    # --- Chunking (changing these invalidates existing chunks) ---
    chunk_size = models.IntegerField(default=900)
    chunk_overlap = models.IntegerField(default=200)

    # --- Retrieval ---
    top_k = models.IntegerField(default=6)
    fetch_k = models.IntegerField(default=24)
    use_mmr = models.BooleanField(default=True)
    mmr_lambda = models.FloatField(default=0.7)
    min_similarity = models.FloatField(default=0.2)

    # --- Hybrid ---
    hybrid_enabled = models.BooleanField(default=False)
    keyword_top_k = models.IntegerField(default=24)
    rrf_k = models.IntegerField(default=60)
    rerank_enabled = models.BooleanField(default=False)
    rerank_model = models.CharField(max_length=200, blank=True)
    query_rewrite = models.BooleanField(default=False)

    # --- Generation ---
    llm_provider = models.CharField(max_length=32, default='groq')
    llm_model = models.CharField(max_length=120, blank=True)
    temperature = models.FloatField(default=0.2)
    max_output_tokens = models.IntegerField(default=2048)
    max_context_chars = models.IntegerField(default=12000)
    embedding_model = models.CharField(max_length=120, default='all-MiniLM-L6-v2')

    class Meta:
        ordering = ['-is_active', 'name']
        constraints = [
            # Partial unique index: any number of inactive rows, at most one
            # active. Enforced by the database rather than by a save() hook,
            # so two admins activating different configurations at the same
            # moment cannot both succeed.
            models.UniqueConstraint(
                fields=['is_active'],
                condition=models.Q(is_active=True),
                name='uniq_single_active_rag_configuration',
            ),
        ]

    def __str__(self):
        return f'{self.name}{" (active)" if self.is_active else ""}'

    def clean(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValidationError(
                {'chunk_overlap': 'Overlap must be smaller than the chunk size, '
                                  'or chunking never advances through the text.'}
            )
        if self.fetch_k < self.top_k:
            raise ValidationError(
                {'fetch_k': 'The candidate pool cannot be smaller than the number '
                            'of chunks selected from it.'}
            )
        if not 0.0 <= self.mmr_lambda <= 1.0:
            raise ValidationError({'mmr_lambda': 'Must be between 0 and 1.'})


class EvaluationDataset(UUIDModel, TimeStampedModel):
    """A named set of questions to score the pipeline against."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    # Which documents must be uploaded for this dataset to be answerable.
    # Names rather than foreign keys: a dataset is meant to survive being
    # exported to JSON and loaded into a different install.
    required_document_names = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def case_count(self) -> int:
        return self.cases.count()


class EvaluationCase(UUIDModel, TimeStampedModel):
    """One question, and what a correct response to it looks like."""

    dataset = models.ForeignKey(
        EvaluationDataset,
        on_delete=models.CASCADE,
        related_name='cases',
    )
    question = models.TextField()
    expected_answer = models.TextField(blank=True)

    # Retrieval ground truth: which sources SHOULD come back. This is what
    # makes recall and precision measurable rather than a matter of opinion.
    expected_document_names = models.JSONField(default=list, blank=True)
    expected_pages = models.JSONField(default=list, blank=True)

    # A control case. The pipeline is only trustworthy if it refuses questions
    # the documents do not answer, so a dataset without these measures nothing
    # about grounding — an assistant that answers everything from memory would
    # score perfectly on answerable questions alone.
    must_refuse = models.BooleanField(default=False)

    tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.question[:80]


class EvaluationRun(UUIDModel, TimeStampedModel):
    """One execution of a dataset against one configuration."""

    dataset = models.ForeignKey(
        EvaluationDataset,
        on_delete=models.CASCADE,
        related_name='runs',
    )
    configuration = models.ForeignKey(
        RAGConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='runs',
    )
    # Whose documents the run retrieved against — results are meaningless
    # without knowing which corpus was searched.
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluation_runs',
    )

    label = models.CharField(
        max_length=120,
        blank=True,
        help_text='Short name for this run, e.g. "baseline-dense-only".',
    )
    status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # A frozen copy of the settings actually in force, not a pointer to them.
    # A configuration row can be edited afterwards; a run's numbers have to keep
    # meaning what they meant when they were produced.
    settings_snapshot = models.JSONField(default=dict, blank=True)

    # Aggregates: retrieval_recall, retrieval_precision, context_relevance,
    # faithfulness, answer_correctness, refusal_accuracy, latency percentiles.
    metrics = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['dataset', '-created_at'], name='evalrun_ds_created_idx'),
            models.Index(fields=['status', '-created_at'], name='evalrun_status_idx'),
        ]

    def __str__(self):
        return f'{self.label or self.dataset.name} @ {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def duration_seconds(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class EvaluationResult(UUIDModel):
    """What happened for one case in one run."""

    run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name='results',
    )
    case = models.ForeignKey(
        EvaluationCase,
        on_delete=models.CASCADE,
        related_name='results',
    )

    answer = models.TextField(blank=True)
    refused = models.BooleanField(default=False)
    # What retrieval actually returned: document name, page, score, per chunk.
    retrieved = models.JSONField(default=list, blank=True)
    # Per-case metric values, same keys as the run's aggregate.
    scores = models.JSONField(default=dict, blank=True)

    retrieval_ms = models.IntegerField(null=True, blank=True)
    generation_ms = models.IntegerField(null=True, blank=True)
    total_ms = models.IntegerField(null=True, blank=True)

    passed = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'case'], name='uniq_result_per_case_per_run'
            ),
        ]
        indexes = [
            models.Index(fields=['run', 'passed'], name='evalres_run_passed_idx'),
        ]

    def __str__(self):
        return f'{"PASS" if self.passed else "FAIL"}: {self.case_id}'
