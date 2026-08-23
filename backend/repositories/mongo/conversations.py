"""MongoDB implementation of ConversationRepository."""
import logging
import re
from datetime import timedelta
from typing import Any, Optional

from bson import ObjectId
from django.utils import timezone

from core.constants import ROLE_ASSISTANT, ROLE_USER, SESSION_ACTIVE
from core.mongo import (
    chat_sessions_col,
    chunks_col,
    documents_col,
    feedback_col,
    messages_col,
)
from core.utils import serialize_mongo_doc
from repositories.base import ConversationDTO, MessageDTO, Page
from repositories.mongo.documents import _oid

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 90


def _to_dto(session: Optional[dict]) -> Optional[ConversationDTO]:
    if session is None:
        return None
    data = serialize_mongo_doc(session)
    data['id'] = data.pop('_id', '')
    return data


def _msg_dto(message: Optional[dict]) -> Optional[MessageDTO]:
    if message is None:
        return None
    data = serialize_mongo_doc(message)
    data['id'] = data.pop('_id', '')
    return data


def _next_timestamp(conversation_id: str, now):
    """A timestamp strictly after every message already in the conversation."""
    latest = messages_col().find_one(
        {'session_id': conversation_id},
        sort=[('created_at', -1)],
        projection={'created_at': 1},
    )
    if latest and latest.get('created_at'):
        previous = latest['created_at']
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=now.tzinfo)
        if previous >= now:
            return previous + timedelta(milliseconds=2)
    return now


def make_preview(text: str) -> str:
    text = (text or '').strip()
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[:PREVIEW_LENGTH - 3] + '...'


class MongoConversationRepository:
    # ── reads ────────────────────────────────────────────────────
    def list_for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> Page:
        query = {'user_id': user_id}
        total = chat_sessions_col().count_documents(query)
        cursor = (
            chat_sessions_col().find(query)
            .sort('created_at', -1)
            .skip(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        return {'items': [_to_dto(s) for s in cursor], 'total': total}

    def get(self, conversation_id: str, user_id: int) -> Optional[ConversationDTO]:
        oid = _oid(conversation_id)
        if oid is None:
            return None
        return _to_dto(chat_sessions_col().find_one({'_id': oid, 'user_id': user_id}))

    def search(self, user_id: int, query: str, *, page: int = 1,
               page_size: int = 20) -> Page:
        # escaped: a title search for "c++" or "(draft)" must not be compiled as
        # a pattern, and a crafted query must not be able to make the server
        # evaluate a pathological regex.
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        filters = {'user_id': user_id, 'title': {'$regex': pattern}}
        total = chat_sessions_col().count_documents(filters)
        cursor = (
            chat_sessions_col().find(filters)
            .sort('updated_at', -1)
            .skip(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        return {'items': [_to_dto(s) for s in cursor], 'total': total}

    # ── writes ───────────────────────────────────────────────────
    def _owned(self, user_id: int, document_ids: list[str]) -> tuple[list[str], list[str]]:
        """Reduce a caller-supplied id list to the documents this user owns.

        The names are read from the database rather than taken from the
        caller, for two reasons: it guarantees the two lists stay positionally
        aligned (the frontend pairs them by index), and it means a display name
        shown next to a citation is always the real filename rather than
        whatever a request body claimed it was.

        The service layer validates these ids before calling. This is the same
        check repeated at the boundary that actually writes the row, because an
        ownership check that exists only upstream is one refactor away from not
        existing at all.
        """
        oids = [o for o in (_oid(d) for d in document_ids) if o is not None]
        if not oids:
            return [], []

        owned = {
            str(d['_id']): d.get('original_filename', '')
            for d in documents_col().find(
                {'_id': {'$in': oids}, 'user_id': user_id},
                {'original_filename': 1},
            )
        }
        # Caller order is preserved — it is the order the user picked.
        ordered = [d for d in document_ids if d in owned]
        return ordered, [owned[d] for d in ordered]

    def create(self, user_id: int, title: str, document_ids: list[str],
               document_names: list[str]) -> ConversationDTO:
        now = timezone.now()
        owned_ids, owned_names = self._owned(user_id, document_ids)
        session = {
            'user_id': user_id,
            'title': title,
            'document_ids': owned_ids,
            'document_names': owned_names,
            'status': SESSION_ACTIVE,
            'message_count': 0,
            'last_message_preview': '',
            'created_at': now,
            'updated_at': now,
            'last_message_at': now,
        }
        result = chat_sessions_col().insert_one(session)
        session['_id'] = result.inserted_id
        return _to_dto(session)

    def update(self, conversation_id: str, user_id: int,
               **fields: Any) -> Optional[ConversationDTO]:
        oid = _oid(conversation_id)
        if oid is None:
            return None

        # Re-grounding a conversation goes through the same ownership filter as
        # creating one — this is the endpoint a crafted request would use to
        # attach someone else's file to a chat it already controls.
        if 'document_ids' in fields:
            owned_ids, owned_names = self._owned(user_id, fields['document_ids'])
            fields['document_ids'] = owned_ids
            fields['document_names'] = owned_names

        fields['updated_at'] = timezone.now()
        return _to_dto(chat_sessions_col().find_one_and_update(
            {'_id': oid, 'user_id': user_id},
            {'$set': fields},
            return_document=True,
        ))

    def delete(self, conversation_id: str, user_id: int) -> bool:
        oid = _oid(conversation_id)
        if oid is None:
            return False
        # Ownership is checked before the messages go, so a wrong id cannot
        # delete another user's transcript.
        session = chat_sessions_col().find_one({'_id': oid, 'user_id': user_id}, {'_id': 1})
        if session is None:
            return False
        messages_col().delete_many({'session_id': conversation_id})
        return chat_sessions_col().delete_one({'_id': oid, 'user_id': user_id}).deleted_count > 0

    # ── messages ─────────────────────────────────────────────────
    def list_messages(self, conversation_id: str, user_id: int) -> list[MessageDTO]:
        if self.get(conversation_id, user_id) is None:
            return []
        cursor = messages_col().find({'session_id': conversation_id}).sort('created_at', 1)
        return [_msg_dto(m) for m in cursor]

    def add_turn(self, conversation_id: str, user_id: int, question: str,
                 answer: str, sources: list[dict[str, Any]],
                 **metrics: Any) -> tuple[MessageDTO, MessageDTO]:
        now = timezone.now()

        # The transcript is read back sorted by created_at, so the pair must be
        # strictly ordered — and not just within this turn. Two turns written
        # inside the same millisecond (the evaluation harness does exactly
        # that) would otherwise interleave, and the model would be shown a
        # history in which it answered before being asked.
        #
        # Anchoring to the newest existing message guarantees a total order per
        # conversation regardless of clock resolution or how fast turns arrive.
        base = _next_timestamp(conversation_id, now)

        user_message = {
            'session_id': conversation_id, 'user_id': user_id, 'role': ROLE_USER,
            'content': question, 'sources': [], 'created_at': base,
        }
        assistant_message = {
            'session_id': conversation_id, 'user_id': user_id, 'role': ROLE_ASSISTANT,
            'content': answer, 'sources': sources,
            'created_at': base + timedelta(milliseconds=1),
        }
        result = messages_col().insert_many([user_message, assistant_message])
        user_message['_id'], assistant_message['_id'] = result.inserted_ids

        chat_sessions_col().update_one(
            {'_id': ObjectId(conversation_id), 'user_id': user_id},
            {
                '$inc': {'message_count': 2},
                '$set': {
                    'last_message_at': now,
                    'updated_at': now,
                    'last_message_preview': make_preview(question),
                },
            },
        )
        return _msg_dto(user_message), _msg_dto(assistant_message)

    def recent_history(self, conversation_id: str, user_id: int,
                       max_turns: int) -> list[MessageDTO]:
        # Newest first, limited, then reversed: fetching in chronological order
        # would mean reading the whole transcript to find its tail.
        cursor = (
            messages_col()
            .find({'session_id': conversation_id},
                  {'role': 1, 'content': 1, 'created_at': 1, '_id': 0})
            .sort('created_at', -1)
            .limit(max_turns * 2)
        )
        history = list(cursor)
        history.reverse()
        return [{'role': m['role'], 'content': m['content']} for m in history]

    def rename_document_everywhere(self, user_id: int, document_id: str,
                                   new_name: str) -> int:
        chunks_col().update_many(
            {'document_id': document_id, 'user_id': user_id},
            {'$set': {'filename': new_name}},
        )

        updated = 0
        for session in chat_sessions_col().find(
            {'user_id': user_id, 'document_ids': document_id},
            {'document_ids': 1, 'document_names': 1},
        ):
            ids = list(session.get('document_ids') or [])
            names = list(session.get('document_names') or [])
            if document_id not in ids or len(ids) != len(names):
                continue
            names[ids.index(document_id)] = new_name
            chat_sessions_col().update_one(
                {'_id': session['_id']}, {'$set': {'document_names': names}},
            )
            updated += 1
        return updated

    # ── feedback ─────────────────────────────────────────────────
    def _owns_assistant_message(self, message_id: str, user_id: int):
        """The message, if it is this user's and is an assistant reply."""
        oid = _oid(message_id)
        if oid is None:
            return None
        # user_id is on the message row, so ownership is part of the query
        # rather than a check the caller has to remember.
        return messages_col().find_one({
            '_id': oid, 'user_id': user_id, 'role': ROLE_ASSISTANT,
        })

    def save_feedback(self, message_id: str, user_id: int, rating: int,
                      reason: str = '', comment: str = ''):
        message = self._owns_assistant_message(message_id, user_id)
        if message is None:
            return None

        now = timezone.now()
        record = {
            'message_id': message_id,
            'conversation_id': message.get('session_id', ''),
            'user_id': user_id,
            'rating': rating,
            'reason': reason,
            'comment': comment,
            'reviewed': False,
            'updated_at': now,
        }
        # Upsert on message_id, which carries a unique index: two rapid clicks
        # cannot create two verdicts, and changing a rating corrects the
        # existing row.
        feedback_col().update_one(
            {'message_id': message_id},
            {'$set': record, '$setOnInsert': {'created_at': now}},
            upsert=True,
        )
        return self.get_feedback(message_id, user_id)

    def get_feedback(self, message_id: str, user_id: int):
        record = feedback_col().find_one({'message_id': message_id, 'user_id': user_id})
        if record is None:
            return None
        data = serialize_mongo_doc(record)
        data['id'] = data.pop('_id', '')
        return data
