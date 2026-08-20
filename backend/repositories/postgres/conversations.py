"""PostgreSQL implementation of ConversationRepository."""
import logging
from datetime import timedelta
from typing import Any, Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.chat.models import Conversation, ConversationStatus, Message, MessageRole
from apps.documents.models import Document
from repositories.base import ConversationDTO, MessageDTO, Page
from repositories.mongo.conversations import PREVIEW_LENGTH, make_preview
from repositories.postgres.documents import _uuid

logger = logging.getLogger(__name__)

_WRITABLE = {'title', 'status', 'message_count', 'last_message_at',
             'last_message_preview'}


def _to_dto(conversation: Optional[Conversation]) -> Optional[ConversationDTO]:
    """The shape /api/chat/sessions/ has always returned.

    ``document_ids`` and ``document_names`` were denormalised arrays in MongoDB
    and are a many-to-many here, so they are read back out of the relation. The
    two lists stay positionally aligned because the frontend pairs them by index.
    """
    if conversation is None:
        return None
    documents = list(conversation.documents.all())
    return {
        'id': str(conversation.pk),
        'user_id': conversation.owner_id,
        'title': conversation.title,
        'document_ids': [str(d.pk) for d in documents],
        'document_names': [d.original_filename for d in documents],
        'status': conversation.status,
        'message_count': conversation.message_count,
        'last_message_preview': conversation.last_message_preview,
        'created_at': conversation.created_at,
        'updated_at': conversation.updated_at,
        'last_message_at': conversation.last_message_at,
    }


def _msg_dto(message: Message, conversation_id: str, user_id: int) -> MessageDTO:
    return {
        'id': str(message.pk),
        'session_id': conversation_id,
        'user_id': user_id,
        'role': message.role,
        'content': message.content,
        'sources': message.sources or [],
        'created_at': message.created_at,
    }


class PostgresConversationRepository:
    # ── reads ────────────────────────────────────────────────────
    def _base(self, user_id: int):
        # prefetch: _to_dto touches conversation.documents for every row, which
        # without this is one extra query per conversation in the list.
        return (Conversation.objects
                .filter(owner_id=user_id)
                .prefetch_related('documents'))

    def list_for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> Page:
        qs = self._base(user_id).order_by('-created_at')
        total = qs.count()
        start = max(page - 1, 0) * page_size
        return {
            'items': [_to_dto(c) for c in qs[start:start + page_size]],
            'total': total,
        }

    def get(self, conversation_id: str, user_id: int) -> Optional[ConversationDTO]:
        pk = _uuid(conversation_id)
        if pk is None:
            return None
        return _to_dto(self._base(user_id).filter(pk=pk).first())

    def search(self, user_id: int, query: str, *, page: int = 1,
               page_size: int = 20) -> Page:
        # icontains, not the full-text index: titles are short and users expect
        # substring behaviour here ("ref" finding "Refunds"), which stemmed
        # full-text search does not give.
        qs = self._base(user_id).filter(title__icontains=query).order_by('-updated_at')
        total = qs.count()
        start = max(page - 1, 0) * page_size
        return {
            'items': [_to_dto(c) for c in qs[start:start + page_size]],
            'total': total,
        }

    # ── writes ───────────────────────────────────────────────────
    def create(self, user_id: int, title: str, document_ids: list[str],
               document_names: list[str]) -> ConversationDTO:
        now = timezone.now()
        with transaction.atomic():
            conversation = Conversation.objects.create(
                owner_id=user_id,
                title=title,
                status=ConversationStatus.ACTIVE,
                last_message_at=now,
            )
            pks = [p for p in (_uuid(d) for d in document_ids) if p is not None]
            if pks:
                # Re-filtered by owner even though the caller validated them:
                # this is the last place before the row is written, and an
                # ownership check that only exists upstream is one refactor away
                # from not existing.
                owned = Document.objects.filter(pk__in=pks, owner_id=user_id)
                conversation.documents.set(owned)
        return _to_dto(conversation)

    def update(self, conversation_id: str, user_id: int,
               **fields: Any) -> Optional[ConversationDTO]:
        pk = _uuid(conversation_id)
        if pk is None:
            return None

        conversation = Conversation.objects.filter(pk=pk, owner_id=user_id).first()
        if conversation is None:
            return None

        document_ids = fields.pop('document_ids', None)
        fields.pop('document_names', None)  # derived from the relation

        with transaction.atomic():
            data = {k: v for k, v in fields.items() if k in _WRITABLE}
            if data:
                for key, value in data.items():
                    setattr(conversation, key, value)
                conversation.save(update_fields=[*data.keys(), 'updated_at'])

            if document_ids is not None:
                pks = [p for p in (_uuid(d) for d in document_ids) if p is not None]
                owned = Document.objects.filter(pk__in=pks, owner_id=user_id)
                conversation.documents.set(owned)

        return self.get(conversation_id, user_id)

    def delete(self, conversation_id: str, user_id: int) -> bool:
        pk = _uuid(conversation_id)
        if pk is None:
            return False
        # Messages cascade with the conversation.
        deleted, _ = Conversation.objects.filter(pk=pk, owner_id=user_id).delete()
        return deleted > 0

    # ── messages ─────────────────────────────────────────────────
    def list_messages(self, conversation_id: str, user_id: int) -> list[MessageDTO]:
        pk = _uuid(conversation_id)
        if pk is None:
            return []
        if not Conversation.objects.filter(pk=pk, owner_id=user_id).exists():
            return []
        messages = Message.objects.filter(conversation_id=pk).order_by('created_at')
        return [_msg_dto(m, conversation_id, user_id) for m in messages]

    def add_turn(self, conversation_id: str, user_id: int, question: str,
                 answer: str, sources: list[dict[str, Any]],
                 **metrics: Any) -> tuple[MessageDTO, MessageDTO]:
        pk = _uuid(conversation_id)
        now = timezone.now()

        with transaction.atomic():
            # Same total-ordering requirement as the MongoDB implementation:
            # anchor to the newest existing message so turns written in the same
            # millisecond cannot interleave.
            latest = (Message.objects.filter(conversation_id=pk)
                      .order_by('-created_at')
                      .values_list('created_at', flat=True)
                      .first())
            base = now if latest is None or latest < now else latest + timedelta(milliseconds=2)

            user_message = Message.objects.create(
                conversation_id=pk, role=MessageRole.USER, content=question,
            )
            Message.objects.filter(pk=user_message.pk).update(created_at=base)
            user_message.created_at = base
            assistant_message = Message.objects.create(
                conversation_id=pk,
                role=MessageRole.ASSISTANT,
                content=answer,
                sources=sources,
                provider=metrics.get('provider', ''),
                model_name=metrics.get('model_name', ''),
                prompt_tokens=metrics.get('prompt_tokens'),
                completion_tokens=metrics.get('completion_tokens'),
                total_tokens=metrics.get('total_tokens'),
                retrieval_ms=metrics.get('retrieval_ms'),
                generation_ms=metrics.get('generation_ms'),
                total_ms=metrics.get('total_ms'),
                chunks_retrieved=metrics.get('chunks_retrieved'),
                error=metrics.get('error', ''),
            )
            # auto_now_add gave both rows the same instant. Nudging the answer
            # forward keeps "order by created_at" showing the question first,
            # exactly as the MongoDB implementation does.
            Message.objects.filter(pk=assistant_message.pk).update(
                created_at=base + timedelta(milliseconds=1)
            )
            assistant_message.refresh_from_db(fields=['created_at'])

            # F() so two concurrent turns both count, rather than one reading a
            # stale value and overwriting the other's increment.
            Conversation.objects.filter(pk=pk, owner_id=user_id).update(
                message_count=F('message_count') + 2,
                last_message_at=now,
                updated_at=now,
                last_message_preview=make_preview(question)[:PREVIEW_LENGTH],
            )

        return (_msg_dto(user_message, conversation_id, user_id),
                _msg_dto(assistant_message, conversation_id, user_id))

    def recent_history(self, conversation_id: str, user_id: int,
                       max_turns: int) -> list[MessageDTO]:
        pk = _uuid(conversation_id)
        if pk is None:
            return []
        recent = list(
            Message.objects
            .filter(conversation_id=pk)
            .order_by('-created_at')
            .values('role', 'content')[:max_turns * 2]
        )
        recent.reverse()
        return [{'role': m['role'], 'content': m['content']} for m in recent]

    def rename_document_everywhere(self, user_id: int, document_id: str,
                                   new_name: str) -> int:
        """A no-op by design.

        MongoDB stored the document's name in three places — the document, a
        copy on every chunk, and a copy on every conversation — so a rename had
        to be written to all three or citations would keep quoting the old name.
        Here the name exists once and every reader reaches it through a foreign
        key, so a rename is already visible everywhere the moment it is saved.

        The method stays because it is part of the contract both backends
        implement; it returns 0 because nothing needed updating.
        """
        return 0
