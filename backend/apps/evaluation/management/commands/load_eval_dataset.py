"""Load an evaluation dataset from JSON.

    python manage.py load_eval_dataset
    python manage.py load_eval_dataset --file evaluation/datasets/refund_policy.json
    python manage.py load_eval_dataset --export "Refund policy" --out questions.json

Datasets are JSON files rather than fixtures so they can be reviewed in a pull
request, edited by someone who does not know Django, and carried to another
install. Loading is idempotent: a case is matched by its question text, so
re-running updates the expected answers rather than duplicating the dataset.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.evaluation.models import EvaluationCase, EvaluationDataset

DEFAULT_DIR = Path(settings.BASE_DIR) / 'evaluation' / 'datasets'


class Command(BaseCommand):
    help = 'Load (or export) an evaluation dataset as JSON.'

    def add_arguments(self, parser):
        parser.add_argument('--file', help='Path to a dataset JSON file.')
        parser.add_argument('--all', action='store_true',
                            help=f'Load every .json in {DEFAULT_DIR}')
        parser.add_argument('--export', help='Dataset name to export instead of loading.')
        parser.add_argument('--out', help='Where to write the export.')

    def handle(self, *args, **opts):
        if opts.get('export'):
            self._export(opts['export'], opts.get('out'))
            return

        if opts.get('file'):
            paths = [Path(opts['file'])]
        else:
            if not DEFAULT_DIR.exists():
                raise CommandError(f'No dataset directory at {DEFAULT_DIR}')
            paths = sorted(DEFAULT_DIR.glob('*.json'))
            if not paths:
                raise CommandError(f'No .json datasets found in {DEFAULT_DIR}')
            if not opts.get('all') and len(paths) > 1:
                names = ', '.join(p.name for p in paths)
                raise CommandError(
                    f'Several datasets found ({names}). Pass --file or --all.'
                )

        for path in paths:
            self._load(path)

    # ------------------------------------------------------------------
    def _load(self, path: Path):
        if not path.exists():
            raise CommandError(f'No such file: {path}')

        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'{path.name} is not valid JSON: {exc}') from exc

        name = payload.get('name')
        if not name:
            raise CommandError(f'{path.name} has no "name".')

        cases = payload.get('cases') or []
        if not cases:
            raise CommandError(f'{path.name} has no cases.')

        with transaction.atomic():
            dataset, created = EvaluationDataset.objects.update_or_create(
                name=name,
                defaults={
                    'description': payload.get('description', ''),
                    'required_document_names': payload.get('required_documents', []),
                },
            )

            added = updated = 0
            for entry in cases:
                question = (entry.get('question') or '').strip()
                if not question:
                    continue
                # Matched on the question, so editing an expected answer and
                # reloading corrects the case instead of adding a second copy
                # of the same question with different ground truth.
                _case, was_created = EvaluationCase.objects.update_or_create(
                    dataset=dataset,
                    question=question,
                    defaults={
                        'expected_answer': entry.get('expected_answer', ''),
                        'expected_document_names': entry.get('expected_documents', []),
                        'expected_pages': entry.get('expected_pages', []),
                        'must_refuse': bool(entry.get('must_refuse', False)),
                        'tags': entry.get('tags', []),
                    },
                )
                added += was_created
                updated += not was_created

        controls = dataset.cases.filter(must_refuse=True).count()
        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} dataset "{name}": {added} new case(s), {updated} updated, '
            f'{dataset.cases.count()} total ({controls} control).'
        ))

        if not controls:
            # Without control cases a dataset cannot tell a grounded pipeline
            # from a model answering everything out of its own memory.
            self.stdout.write(self.style.WARNING(
                '  No control cases (must_refuse). This dataset cannot detect '
                'the assistant answering from its own knowledge.'
            ))

    # ------------------------------------------------------------------
    def _export(self, name: str, out: str | None):
        dataset = EvaluationDataset.objects.filter(name=name).first()
        if dataset is None:
            raise CommandError(f'No dataset named "{name}".')

        payload = {
            'name': dataset.name,
            'description': dataset.description,
            'required_documents': dataset.required_document_names,
            'cases': [
                {
                    'question': c.question,
                    'expected_answer': c.expected_answer,
                    'expected_documents': c.expected_document_names,
                    'expected_pages': c.expected_pages,
                    'must_refuse': c.must_refuse,
                    'tags': c.tags,
                }
                for c in dataset.cases.all()
            ],
        }

        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if out:
            Path(out).write_text(text, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'Wrote {out}'))
        else:
            self.stdout.write(text)
