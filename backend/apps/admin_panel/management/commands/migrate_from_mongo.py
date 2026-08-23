"""Copy the MongoDB (and SQLite) data into PostgreSQL.

    python manage.py migrate_from_mongo --dry-run
    python manage.py migrate_from_mongo --users-from-sqlite db.sqlite3
    python manage.py migrate_from_mongo

Design notes worth knowing before running it:

**It is re-runnable.** Documents, conversations and messages record the
MongoDB ``_id`` they came from (``legacy_mongo_id``), so a second run skips what
it already copied. Chunks are guarded instead by their ``(document, chunk_index)``
uniqueness, which costs nothing extra on a table that may hold millions of rows.
A migration that can only be run once is a migration you cannot rehearse.

**Vectors are copied where they exist, never recomputed here.** Chunks written
after vector persistence was added carry their embedding in MongoDB as a float32
blob, and those 384 floats are decoded straight into the ``vector(384)`` column —
bit-identical, not merely equivalent, and far faster than re-embedding.

Chunks written *before* that change have text but no vector. They still migrate,
and their content is fully searchable by keyword, but they are invisible to
vector search until ``manage.py reprocess_documents`` re-embeds them. The command
reports how many fall into this category rather than leaving it to be discovered
as an unexplained drop in answer quality.

**Users come from SQLite, not MongoDB.** Django's auth tables were never in
MongoDB, and every Mongo record references a user by the integer primary key
those tables issued. Users therefore have to land in PostgreSQL *with the same
ids*, or nothing else can be attached to them — which is why this reads the
SQLite file directly and preserves primary keys and password hashes.

**created_at is preserved; updated_at is not.** ``updated_at`` is an
``auto_now`` field, so the ORM overwrites it on every write. Ordering and
analytics depend on ``created_at``, which is preserved exactly.
"""
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.chat.models import Conversation, ConversationStatus, Message, MessageRole
from apps.documents.models import Document, DocumentChunk, DocumentStatus

STEPS = ('users', 'documents', 'chunks', 'conversations', 'messages', 'analytics')


def aware(value):
    """Attach UTC to a naive datetime.

    PyMongo returns naive datetimes because BSON has no timezone: the offset is
    simply not part of what MongoDB stored. With ``USE_TZ = True`` Django warns
    about every one of them and the value goes into a ``timestamptz`` column
    interpreted against whatever the session timezone happens to be — correct
    here only by the coincidence that both are UTC, and silently wrong on any
    host configured otherwise.

    The application has always written UTC (``django.utils.timezone.now()``),
    so stamping UTC on the way in is a statement of what the value already
    meant, not a conversion.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # SQLite hands back ISO strings rather than datetimes.
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class Command(BaseCommand):
    help = 'Copy documents, chunks, conversations, messages and analytics from MongoDB into PostgreSQL.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be copied and write nothing.',
        )
        parser.add_argument(
            '--only', default=','.join(STEPS),
            help=f'Comma-separated subset of: {", ".join(STEPS)}',
        )
        parser.add_argument(
            '--users-from-sqlite', default='',
            help='Path to the old db.sqlite3, to copy auth users across first. '
                 'Required on a fresh PostgreSQL database.',
        )
        parser.add_argument(
            '--batch-size', type=int, default=500,
            help='Rows per bulk insert (default 500).',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        self.dry_run = opts['dry_run']
        self.batch_size = opts['batch_size']
        self.stats = defaultdict(int)

        # A dry run writes nothing, so each step would otherwise find the
        # previous step's rows missing and report that everything has to be
        # skipped — which says nothing about whether the real run would work.
        # These hold what each step *would* have created, so the later steps
        # can be reported against it.
        self._would_create_users: set = set()
        self._would_create_documents: dict = {}
        self._would_create_conversations: set = set()

        steps = [s.strip() for s in opts['only'].split(',') if s.strip()]
        unknown = set(steps) - set(STEPS)
        if unknown:
            raise CommandError(f'Unknown step(s): {", ".join(sorted(unknown))}')

        if connection.vendor != 'postgresql':
            raise CommandError(
                f'The target database is {connection.vendor}, not PostgreSQL. '
                'Set DATABASE_URL before running this.'
            )

        self._banner()

        if 'users' in steps and opts['users_from_sqlite']:
            self._migrate_users(Path(opts['users_from_sqlite']))
        elif 'users' in steps:
            self.stdout.write(self.style.WARNING(
                'Skipping users: pass --users-from-sqlite <path> to copy them. '
                'Documents whose owner is missing will be skipped.'
            ))

        # Each step is its own transaction: a failure in messages should not
        # roll back documents that migrated cleanly an hour earlier.
        if 'documents' in steps:
            self._run_step('documents', self._migrate_documents)
        if 'chunks' in steps:
            self._run_step('chunks', self._migrate_chunks)
        if 'conversations' in steps:
            self._run_step('conversations', self._migrate_conversations)
        if 'messages' in steps:
            self._run_step('messages', self._migrate_messages)
        if 'analytics' in steps:
            self._run_step('analytics', self._migrate_analytics)

        self._summary()

    # ------------------------------------------------------------------
    def _banner(self):
        mode = 'DRY RUN — nothing will be written' if self.dry_run else 'LIVE'
        self.stdout.write(self.style.MIGRATE_HEADING(f'\nMongoDB -> PostgreSQL  [{mode}]'))
        self.stdout.write(f'  source: {settings.MONGODB_HOST} / {settings.MONGODB_DB}')
        self.stdout.write(f'  target: {connection.settings_dict.get("NAME")}\n')

    def _run_step(self, name, fn):
        self.stdout.write(self.style.MIGRATE_LABEL(f'\n{name}'))
        if self.dry_run:
            fn()
            return
        with transaction.atomic():
            fn()

    def _note(self, message):
        self.stdout.write(f'  {message}')

    def _warn(self, message):
        self.stdout.write(self.style.WARNING(f'  {message}'))

    # ------------------------------------------------------------------
    def _migrate_users(self, sqlite_path: Path):
        """Copy auth users out of the old SQLite file, primary keys intact."""
        self.stdout.write(self.style.MIGRATE_LABEL('\nusers'))

        if not sqlite_path.exists():
            raise CommandError(f'No SQLite database at {sqlite_path}')

        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                'SELECT id, password, last_login, is_superuser, username, '
                'first_name, last_name, email, is_staff, is_active, date_joined '
                'FROM auth_user'
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise CommandError(f'Could not read auth_user from {sqlite_path}: {exc}') from exc
        finally:
            conn.close()

        existing = set(User.objects.values_list('pk', flat=True))
        to_create = [r for r in rows if r['id'] not in existing]

        self._note(f'{len(rows)} user(s) in SQLite, {len(to_create)} not yet in PostgreSQL')
        if self.dry_run:
            self._would_create_users = {r['id'] for r in to_create}
            self.stats['users'] += len(to_create)
            return
        if not to_create:
            return

        with transaction.atomic():
            User.objects.bulk_create([
                User(
                    pk=r['id'],
                    # The hash is copied verbatim. Re-hashing is impossible
                    # anyway (the plaintext is gone), and copying it means
                    # everyone's existing password keeps working.
                    password=r['password'],
                    last_login=aware(r['last_login']),
                    is_superuser=bool(r['is_superuser']),
                    username=r['username'],
                    first_name=r['first_name'] or '',
                    last_name=r['last_name'] or '',
                    email=r['email'] or '',
                    is_staff=bool(r['is_staff']),
                    is_active=bool(r['is_active']),
                    date_joined=aware(r['date_joined']) or timezone.now(),
                )
                for r in to_create
            ], batch_size=self.batch_size)

            # bulk_create does not fire post_save, so the profile signal never
            # ran for these rows. Create the profiles explicitly rather than
            # leaving accounts that raise on the first profile access.
            from apps.authentication.models import UserProfile

            UserProfile.objects.bulk_create(
                [UserProfile(user_id=r['id'], email_verified=bool(r['is_active']))
                 for r in to_create],
                ignore_conflicts=True,
            )

            # PostgreSQL's id sequence still starts at 1 after explicit-pk
            # inserts, so the next signup would collide with user 1. Push it
            # past the highest id we just inserted.
            self._resync_sequence(User)

        self.stats['users'] += len(to_create)
        self._note(f'copied {len(to_create)} user(s) and their profiles')

    @staticmethod
    def _resync_sequence(model):
        table = model._meta.db_table
        pk = model._meta.pk.column
        with connection.cursor() as cur:
            # noqa justification: `table` and `pk` come from Django's model
            # metadata, never from input. Identifiers cannot be bound as query
            # parameters, so interpolation is the only way to name a table.
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "  # noqa: S608
                f"COALESCE((SELECT MAX({pk}) FROM {table}), 1), true)"
            )

    # ------------------------------------------------------------------
    def _migrate_documents(self):
        from core.mongo import documents_col

        known_users = (set(User.objects.values_list('pk', flat=True))
                       | self._would_create_users)
        already = set(
            Document.objects.exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', flat=True)
        )

        source = list(documents_col().find())
        self._note(f'{len(source)} document(s) in MongoDB, {len(already)} already migrated')

        pending, skipped_owner, skipped_dupe = [], 0, 0
        # The (owner, file_hash) unique constraint is new — MongoDB only had an
        # application-level check, so the source may well contain pairs that
        # violate it. Detect them here instead of letting the insert fail.
        seen_hashes = set(Document.objects.values_list('owner_id', 'file_hash'))

        for doc in source:
            mongo_id = str(doc['_id'])
            if mongo_id in already:
                continue

            owner_id = doc.get('user_id')
            if owner_id not in known_users:
                skipped_owner += 1
                continue

            file_hash = doc.get('file_hash') or ''
            if (owner_id, file_hash) in seen_hashes:
                skipped_dupe += 1
                continue
            seen_hashes.add((owner_id, file_hash))

            status = doc.get('status', DocumentStatus.PENDING)
            if status not in DocumentStatus.values:
                status = DocumentStatus.PENDING

            pending.append(Document(
                owner_id=owner_id,
                legacy_mongo_id=mongo_id,
                original_filename=doc.get('original_filename', 'untitled'),
                stored_filename=doc.get('filename', ''),
                file_path=doc.get('file_path', ''),
                file_type=doc.get('file_type', ''),
                file_size=doc.get('file_size') or 0,
                file_hash=file_hash,
                status=status,
                error_message=doc.get('error_message') or '',
                page_count=doc.get('page_count') or 0,
                word_count=doc.get('word_count') or 0,
                chunk_count=doc.get('chunk_count') or 0,
                vector_count=doc.get('vector_count') or 0,
                summary=doc.get('summary') or '',
            ))

        if skipped_owner:
            self._warn(f'skipped {skipped_owner} document(s) whose owner does not exist here')
        if skipped_dupe:
            self._warn(f'skipped {skipped_dupe} document(s) that duplicate an '
                       f'existing (owner, file_hash) pair')

        if self.dry_run:
            # The MongoDB id stands in for the primary key the real run would
            # assign. It has to be distinct per document: a shared placeholder
            # makes the (document, chunk_index) dedup below treat chunk 0 of
            # every document as the same row, and the dry run then under-reports
            # the chunk count by however many documents there are.
            self._would_create_documents = {
                d.legacy_mongo_id: (d.legacy_mongo_id, d.owner_id) for d in pending
            }

        self._insert(pending, source, 'documents')

    # ------------------------------------------------------------------
    def _migrate_chunks(self):
        import numpy as np

        from core.mongo import chunks_col

        # legacy Mongo document id -> (new uuid, owner_id)
        doc_map = {
            legacy: (pk, owner_id)
            for legacy, pk, owner_id in Document.objects
            .exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', 'pk', 'owner_id')
        }
        doc_map.update(self._would_create_documents)
        if not doc_map:
            self._warn('no migrated documents — run the documents step first')
            return

        # Chunks carry no legacy id column of their own — a unique index over
        # millions of rows to support a one-off migration is not worth its
        # write cost. The (document, chunk_index) uniqueness constraint already
        # makes re-running safe, so `seen` below is the idempotency guard, and
        # the Mongo id is kept in `metadata` purely for traceability.
        dim = settings.EMBEDDING_DIMENSION
        source = list(chunks_col().find())
        self._note(f'{len(source)} chunk(s) in MongoDB')

        pending, no_vector, orphaned, duplicated = [], 0, 0, 0
        # (document_pk, chunk_index) must be unique. A document that was
        # reprocessed in the past can have left duplicates behind.
        seen = set(DocumentChunk.objects.values_list('document_id', 'chunk_index'))

        for chunk in source:
            mongo_id = str(chunk['_id'])
            target = doc_map.get(str(chunk.get('document_id', '')))
            if target is None:
                orphaned += 1
                continue
            doc_pk, owner_id = target

            index = chunk.get('chunk_index', 0)
            if (doc_pk, index) in seen:
                duplicated += 1
                continue
            seen.add((doc_pk, index))

            embedding = None
            raw = chunk.get('embedding')
            if raw:
                vector = np.frombuffer(bytes(raw), dtype=np.float32)
                if vector.size == dim:
                    embedding = vector.tolist()
                else:
                    # A vector of the wrong width is not comparable with the
                    # others; storing it would poison every search it appears in.
                    no_vector += 1
            else:
                no_vector += 1

            pending.append(DocumentChunk(
                document_id=doc_pk,
                owner_id=owner_id,
                content=chunk.get('content', ''),
                chunk_index=index,
                page_number=chunk.get('page_number', 1),
                start_char=chunk.get('start_char', 0),
                end_char=chunk.get('end_char', 0),
                word_count=chunk.get('word_count', 0),
                embedding=embedding,
                metadata={'legacy_mongo_id': mongo_id},
            ))

        if orphaned:
            self._warn(f'skipped {orphaned} chunk(s) whose document was not migrated')
        if duplicated:
            self._warn(f'skipped {duplicated} chunk(s) that repeat a '
                       f'(document, chunk_index) already present')
        if no_vector:
            pct = 100 * no_vector / max(len(source), 1)
            self._warn(
                f'{no_vector} of {len(source)} chunk(s) ({pct:.0f}%) have no usable '
                f'stored vector. They migrate with their text intact but are '
                f'invisible to vector search until re-embedded:'
            )
            self._warn('    manage.py reprocess_documents')

        self._insert(pending, source, 'chunks', preserve_created=False)

    # ------------------------------------------------------------------
    def _migrate_conversations(self):
        from core.mongo import chat_sessions_col

        known_users = (set(User.objects.values_list('pk', flat=True))
                       | self._would_create_users)
        already = set(
            Conversation.objects.exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', flat=True)
        )
        doc_map = dict(
            Document.objects.exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', 'pk')
        )
        doc_map.update({k: v[0] for k, v in self._would_create_documents.items()})

        source = list(chat_sessions_col().find())
        self._note(f'{len(source)} conversation(s) in MongoDB, {len(already)} already migrated')

        pending, links, skipped = [], {}, 0
        for session in source:
            mongo_id = str(session['_id'])
            if mongo_id in already:
                continue
            owner_id = session.get('user_id')
            if owner_id not in known_users:
                skipped += 1
                continue

            status = session.get('status', ConversationStatus.ACTIVE)
            if status not in ConversationStatus.values:
                status = ConversationStatus.ACTIVE

            conversation = Conversation(
                owner_id=owner_id,
                legacy_mongo_id=mongo_id,
                title=(session.get('title') or 'Untitled')[:200],
                status=status,
                message_count=session.get('message_count') or 0,
                last_message_at=aware(session.get('last_message_at')),
                last_message_preview=(session.get('last_message_preview') or '')[:200],
            )
            pending.append(conversation)
            links[mongo_id] = [
                doc_map[d] for d in (session.get('document_ids') or []) if d in doc_map
            ]

        if skipped:
            self._warn(f'skipped {skipped} conversation(s) with an unknown owner')

        if self.dry_run:
            self._would_create_conversations = {c.legacy_mongo_id for c in pending}

        created = self._insert(pending, source, 'conversations')
        if not created or self.dry_run:
            return

        # Attach the document many-to-many now that the rows have primary keys.
        through = Conversation.documents.through
        rows = [
            through(conversation_id=c.pk, document_id=doc_pk)
            for c in created
            for doc_pk in links.get(c.legacy_mongo_id, [])
        ]
        if rows:
            through.objects.bulk_create(rows, ignore_conflicts=True, batch_size=self.batch_size)
            self._note(f'linked {len(rows)} conversation-document pair(s)')

    # ------------------------------------------------------------------
    def _migrate_messages(self):
        from core.mongo import messages_col

        conv_map = dict(
            Conversation.objects.exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', 'pk')
        )
        conv_map.update({legacy: None for legacy in self._would_create_conversations})
        if not conv_map:
            self._warn('no migrated conversations — run the conversations step first')
            return

        already = set(
            Message.objects.exclude(legacy_mongo_id=None)
            .values_list('legacy_mongo_id', flat=True)
        )
        source = list(messages_col().find())
        self._note(f'{len(source)} message(s) in MongoDB, {len(already)} already migrated')

        pending, orphaned = [], 0
        for msg in source:
            mongo_id = str(msg['_id'])
            if mongo_id in already:
                continue
            session_key = str(msg.get('session_id', ''))
            if session_key not in conv_map:
                orphaned += 1
                continue
            conversation_id = conv_map[session_key]

            role = msg.get('role', MessageRole.USER)
            if role not in MessageRole.values:
                role = MessageRole.USER

            pending.append(Message(
                conversation_id=conversation_id,
                legacy_mongo_id=mongo_id,
                role=role,
                content=msg.get('content', ''),
                sources=msg.get('sources') or [],
                chunks_retrieved=len(msg.get('sources') or []) or None,
            ))

        if orphaned:
            self._warn(f'skipped {orphaned} message(s) whose conversation was not migrated')

        self._insert(pending, source, 'messages', created_key='created_at')

    # ------------------------------------------------------------------
    def _migrate_analytics(self):
        from core.mongo import analytics_col

        known_users = set(User.objects.values_list('pk', flat=True))
        # Sorted because the resume-by-count below only makes sense against a
        # stable order; an unsorted find() may return rows differently on each
        # call, which would re-copy some events and skip others.
        source = list(analytics_col().find().sort('created_at', 1))

        # Analytics rows have no legacy id column of their own, so re-running
        # is guarded by count instead: if the target already holds at least as
        # many events as the source, there is nothing new to copy.
        existing = AnalyticsEvent.objects.count()
        self._note(f'{len(source)} event(s) in MongoDB, {existing} already in PostgreSQL')
        if existing >= len(source):
            self._note('nothing to do')
            return

        pending = [
            AnalyticsEvent(
                user_id=event.get('user_id') if event.get('user_id') in known_users else None,
                event_type=event.get('event_type', 'unknown')[:40],
                metadata=event.get('metadata') or {},
            )
            for event in source[existing:]
        ]
        self._insert(pending, source[existing:], 'analytics', created_key='created_at')

    # ------------------------------------------------------------------
    def _insert(self, pending, source, label, preserve_created=True, created_key='created_at'):
        """Bulk-create `pending`, then restore each row's original created_at."""
        if not pending:
            self._note('nothing new to copy')
            return []

        if self.dry_run:
            self._note(f'would copy {len(pending)} {label}')
            self.stats[label] += len(pending)
            return []

        model = type(pending[0])
        created = model.objects.bulk_create(pending, batch_size=self.batch_size)

        if preserve_created:
            # auto_now_add stamped every row with "now" during bulk_create.
            # bulk_update passes add=False to pre_save, so the original value is
            # kept this time — which is why the timestamps survive at all.
            by_legacy = {}
            for item in source:
                by_legacy[str(item['_id'])] = aware(item.get(created_key))

            restorable = []
            for index, obj in enumerate(created):
                original = None
                legacy = getattr(obj, 'legacy_mongo_id', None)
                if legacy:
                    original = by_legacy.get(legacy)
                elif index < len(source):
                    original = aware(source[index].get(created_key))
                if original:
                    obj.created_at = original
                    restorable.append(obj)

            if restorable:
                model.objects.bulk_update(restorable, ['created_at'],
                                          batch_size=self.batch_size)

        self.stats[label] += len(created)
        self._note(self.style.SUCCESS(f'copied {len(created)} {label}'))
        return created

    # ------------------------------------------------------------------
    def _summary(self):
        self.stdout.write(self.style.MIGRATE_HEADING('\nSummary'))
        if not self.stats:
            self.stdout.write('  nothing was copied')
        for label in ('users', *STEPS[1:]):
            if self.stats.get(label):
                verb = 'would copy' if self.dry_run else 'copied'
                self.stdout.write(f'  {verb} {self.stats[label]:>6} {label}')

        if self.dry_run:
            self.stdout.write(self.style.WARNING(
                '\nDry run — nothing was written. Re-run without --dry-run to apply.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '\nDone. Next:\n'
                '  1. PERSISTENCE_BACKEND=postgres VECTOR_BACKEND=pgvector\n'
                '  2. manage.py check\n'
                '  3. Re-run the evaluation to confirm retrieval parity before '
                'retiring MongoDB.'
            ))
