"""
Module 12: Conversation Memory
Retrieves and formats the last N turns of a chat session for context injection.
"""
import logging
from typing import Dict, List

from django.conf import settings

from core.constants import ROLE_USER
from core.mongo import messages_col

logger = logging.getLogger(__name__)


def get_conversation_history(session_id: str, max_turns: int = None) -> List[Dict]:
    """
    Fetch the last `max_turns` user+assistant message pairs from a session.
    Returns list of {role, content} dicts in chronological order.
    """
    max_turns = max_turns or settings.CONVERSATION_MEMORY_TURNS
    limit = max_turns * 2  # each turn = 1 user + 1 assistant message

    messages = list(
        messages_col()
        .find({'session_id': session_id}, {'role': 1, 'content': 1, 'created_at': 1, '_id': 0})
        .sort('created_at', -1)
        .limit(limit)
    )

    # Reverse so chronological order (oldest first)
    messages.reverse()
    return [{'role': m['role'], 'content': m['content']} for m in messages]


def format_history_for_prompt(history: List[Dict]) -> str:
    """Convert history list to a formatted string for prompt injection."""
    if not history:
        return "No previous conversation."
    lines = []
    for msg in history:
        role = 'User' if msg['role'] == ROLE_USER else 'Assistant'
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def summarize_history_if_long(history: List[Dict], max_chars: int = 3000) -> List[Dict]:
    """
    If conversation history exceeds max_chars, keep only the most recent turns
    to avoid blowing the context window.
    """
    total = sum(len(m['content']) for m in history)
    if total <= max_chars:
        return history

    # Drop oldest messages until within budget
    while history and sum(len(m['content']) for m in history) > max_chars:
        history = history[2:]  # drop oldest user+assistant pair

    return history
