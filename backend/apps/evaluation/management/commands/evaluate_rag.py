"""Score the RAG pipeline against an evaluation dataset.

    python manage.py evaluate_rag --dataset "Refund policy" --user 8
    python manage.py evaluate_rag --dataset "Refund policy" --user 8 --judge
    python manage.py evaluate_rag --compare

Deterministic metrics by default. ``--judge`` adds LLM-graded faithfulness and
correctness at the cost of one extra API call per case and a number that will
not reproduce exactly.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.evaluation.models import EvaluationDataset, EvaluationRun, RAGConfiguration
from apps.evaluation.runner import EvaluationError, run_evaluation

# Printed in this order, with a one-line explanation, because a wall of
# unexplained decimals is not a report anyone can act on.
METRIC_ORDER = [
    ('retrieval_recall', 'Retrieval recall', 'share of expected pages that were found'),
    ('retrieval_precision', 'Retrieval precision', 'share of retrieved pages that were wanted'),
    ('mrr', 'Mean reciprocal rank', 'how high the first correct page ranked'),
    ('context_relevance', 'Context relevance', 'share of passages related to the question'),
    ('faithfulness', 'Faithfulness (judged)', 'claims supported by the context'),
    ('faithfulness_lexical', 'Faithfulness (lexical)', 'answer wording found in the context'),
    ('citation_validity', 'Citation validity', 'cited pages that were actually retrieved'),
    ('answer_correctness', 'Answer correctness (judged)', 'agreement with the reference answer'),
    ('answer_correctness_lexical', 'Answer correctness (lexical)', 'token overlap with reference'),
    ('refusal_accuracy_control', 'Refusal accuracy', 'out-of-scope questions correctly declined'),
    ('answer_rate_answerable', 'Answer rate', 'answerable questions actually answered'),
]

# Latency, of completed cases only, so the parts always sum to the whole.
LATENCY_ORDER = [
    ('latency_ms_mean', 'Latency mean'),
    ('latency_ms_p50', 'Latency p50'),
    ('latency_ms_p95', 'Latency p95'),
    ('retrieval_ms_mean', '  of which retrieval'),
    ('generation_ms_mean', '  of which generation'),
    ('retrieval_ms_mean_all', 'Retrieval mean (all cases)'),
]


class Command(BaseCommand):
    help = 'Run an evaluation dataset against the RAG pipeline and report the scores.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', help='Dataset name. Omit to use the only one.')
        parser.add_argument('--user', type=int,
                            help='User id whose documents to search. Defaults to the '
                                 'first user who owns the required documents.')
        parser.add_argument('--label', default='',
                            help='Short name for this run, e.g. "baseline-dense-only".')
        parser.add_argument('--judge', action='store_true',
                            help='Add LLM-graded faithfulness and correctness.')
        parser.add_argument('--limit', type=int,
                            help='Only run the first N cases (for a quick check).')
        parser.add_argument('--config', help='RAGConfiguration name to record against.')
        parser.add_argument('--compare', action='store_true',
                            help='Print the last runs side by side and exit.')
        parser.add_argument('--quiet', action='store_true',
                            help='Only print the summary table.')

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if opts['compare']:
            self._compare()
            return

        dataset = self._dataset(opts.get('dataset'))
        user_id = self._user_id(opts.get('user'), dataset)
        configuration = self._configuration(opts.get('config'))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nEvaluating "{dataset.name}" as user {user_id}'
        ))
        if opts['judge']:
            self.stdout.write(self.style.WARNING(
                '  --judge: one extra LLM call per case; scores will not reproduce exactly.'
            ))

        quiet = opts['quiet']

        def progress(index, total, case):
            if quiet:
                return
            self.stdout.write(f'  [{index}/{total}] {case.question[:70]}')

        try:
            run = run_evaluation(
                dataset, user_id,
                label=opts['label'], judge=opts['judge'],
                configuration=configuration, limit=opts.get('limit'),
                progress=progress,
            )
        except EvaluationError as exc:
            raise CommandError(str(exc)) from exc

        self._report(run)

    # ------------------------------------------------------------------
    def _dataset(self, name):
        if name:
            dataset = EvaluationDataset.objects.filter(name=name).first()
            if dataset is None:
                names = list(EvaluationDataset.objects.values_list('name', flat=True))
                available = ', '.join(names) if names else (
                    'none yet — load one with: manage.py load_eval_dataset'
                )
                raise CommandError(f'No dataset named "{name}". Available: {available}')
            return dataset

        datasets = list(EvaluationDataset.objects.all())
        if not datasets:
            raise CommandError(
                'No evaluation datasets exist. Load one with:\n'
                '  python manage.py load_eval_dataset'
            )
        if len(datasets) > 1:
            names = ', '.join(d.name for d in datasets)
            raise CommandError(f'Several datasets exist; pass --dataset. One of: {names}')
        return datasets[0]

    def _user_id(self, user_id, dataset):
        if user_id:
            if not User.objects.filter(pk=user_id).exists():
                raise CommandError(f'No user with id {user_id}.')
            return user_id

        # Pick the first user who can actually satisfy the dataset, so the
        # common case needs no flag at all.
        from apps.evaluation.runner import resolve_corpus

        for candidate in User.objects.filter(is_active=True).order_by('pk'):
            try:
                resolve_corpus(dataset, candidate.pk)
            except EvaluationError:
                continue
            self.stdout.write(f'  (using user {candidate.pk}: {candidate.email or candidate.username})')
            return candidate.pk

        raise CommandError(
            'No user has the documents this dataset needs. Upload them, or pass '
            '--user to see exactly what is missing.'
        )

    def _configuration(self, name):
        if not name:
            return None
        configuration = RAGConfiguration.objects.filter(name=name).first()
        if configuration is None:
            raise CommandError(f'No RAG configuration named "{name}".')
        return configuration

    # ------------------------------------------------------------------
    def _report(self, run: EvaluationRun):
        m = run.metrics or {}

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 62))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'  {run.label or run.dataset.name}'
        ))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 62))

        passed = m.get('cases_passed', 0)
        total = m.get('cases_total', 0)
        errored = m.get('cases_errored', 0)
        style = self.style.SUCCESS if passed == total else self.style.WARNING
        self.stdout.write(style(
            f'\n  {passed}/{total} cases passed'
            + (f'   ({errored} errored)' if errored else '')
        ))
        self.stdout.write(
            f'  {m.get("cases_answerable", 0)} answerable, '
            f'{m.get("cases_control", 0)} control (must refuse)\n'
        )

        self._generation_caveat(m)
        self._corpus_caveat(m)

        self.stdout.write('  QUALITY')
        for key, title, explanation in METRIC_ORDER:
            if key not in m:
                continue
            self.stdout.write(
                f'    {title:<30} {self._bar(m[key])} {m[key]:.3f}   {explanation}'
            )

        self.stdout.write('\n  LATENCY')
        for key, title in LATENCY_ORDER:
            if key in m:
                self.stdout.write(f'    {title:<30} {m[key]:>8.0f} ms')

        snapshot = run.settings_snapshot or {}
        self.stdout.write('\n  CONFIGURATION')
        for key in ('vector_backend', 'llm_model', 'embedding_model', 'chunk_size',
                    'top_k', 'fetch_k', 'use_mmr', 'min_similarity',
                    'hybrid_enabled', 'rerank_enabled'):
            if key in snapshot:
                self.stdout.write(f'    {key:<30} {snapshot[key]}')

        self.stdout.write(
            f'\n  Run id {run.pk}\n'
            f'  Failing cases: /django-admin/evaluation/evaluationresult/'
            f'?run__id__exact={run.pk}&passed__exact=0\n'
        )

    def _generation_caveat(self, m: dict):
        """Say when the provider, not the pipeline, is why cases failed."""
        errored = m.get('cases_errored') or 0
        if not errored:
            return

        total = m.get('cases_total', 0)
        lines = [
            f'  NOTE: {errored} of {total} case(s) failed to generate an answer, '
            'usually a provider',
            '        rate limit. Their RETRIEVAL scores are still included — that '
            'half ran fine.',
            '        The answer-side scores below are averaged only over cases '
            'that answered,',
            '        so they come from a smaller sample than the retrieval ones.',
            '',
        ]
        self.stdout.write(self.style.WARNING('\n'.join(lines)))

    def _corpus_caveat(self, m: dict):
        """Say when recall is not worth reading.

        Recall counts how many of the expected pages came back. If the corpus
        holds barely more chunks than the retriever returns, almost all of it
        comes back every time and recall approaches 1.0 no matter how good
        retrieval is. A headline number that cannot go down is not a
        measurement, and an evaluation that prints it without saying so is
        inviting the reader to draw a conclusion it does not support.
        """
        coverage = m.get('retrieval_coverage')
        chunks = m.get('corpus_chunks')
        if not coverage or coverage < 0.25:
            return

        returned = int(round(coverage * chunks))
        lines = [
            f'  NOTE: this corpus holds only {chunks} chunk(s), and retrieval returns '
            f'up to {returned}',
            f'        of them — {coverage:.0%} of everything available. At this size '
            'recall is close to',
            '        guaranteed and should not be read as evidence that retrieval is '
            'good.',
            '        Precision and context relevance are the informative numbers here.',
            '        Add more documents for a recall figure that can actually move.',
            '',
        ]
        self.stdout.write(self.style.WARNING('\n'.join(lines)))

    @staticmethod
    def _bar(value: float, width: int = 20) -> str:
        filled = int(round(max(0.0, min(1.0, value)) * width))
        return '[' + '#' * filled + '.' * (width - filled) + ']'

    # ------------------------------------------------------------------
    def _compare(self):
        runs = list(EvaluationRun.objects.order_by('-created_at')[:5])
        if not runs:
            raise CommandError('No evaluation runs recorded yet.')

        runs.reverse()
        headers = [(r.label or str(r.pk)[:8])[:14] for r in runs]

        self.stdout.write(self.style.MIGRATE_HEADING('\nRun comparison (oldest first)\n'))
        self.stdout.write('  ' + ' ' * 30 + ''.join(f'{h:>16}' for h in headers))

        for key, title, _explanation in METRIC_ORDER:
            if not any(key in (r.metrics or {}) for r in runs):
                continue
            cells = []
            for r in runs:
                value = (r.metrics or {}).get(key)
                cells.append(f'{value:>16.3f}' if value is not None else f'{"—":>16}')
            self.stdout.write(f'  {title:<30}' + ''.join(cells))

        cells = []
        for r in runs:
            value = (r.metrics or {}).get('latency_ms_p95')
            cells.append(f'{value:>13.0f} ms' if value is not None else f'{"—":>16}')
        self.stdout.write(f'  {"Latency p95":<30}' + ''.join(cells))
        self.stdout.write('')
