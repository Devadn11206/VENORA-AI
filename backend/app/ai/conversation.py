"""Conversation session management providing thread isolation and context window bounding."""

import logging
import secrets
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional
from pydantic import BaseModel

from app.ai.schemas import ChatMessage, MessageRole

logger = logging.getLogger("venora.ai.conversation")


class ConversationContext:
    """Maintains an ordered, size-bounded conversation history for a single thread."""

    def __init__(self, conversation_id: str, max_messages: int = 20) -> None:
        self.conversation_id = conversation_id
        self.max_messages = max_messages
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.messages: Deque[ChatMessage] = deque(maxlen=max_messages)

    def add_message(self, message: ChatMessage) -> None:
        """Append message to context and update timestamp."""
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

    def get_messages(self) -> List[ChatMessage]:
        """Return shallow copy of current message history."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self.updated_at = datetime.now(timezone.utc)


class ConversationManager:
    """Manages active conversation contexts with bounded thread retention."""

    def __init__(self, max_conversations: int = 100, max_messages_per_conversation: int = 20) -> None:
        self.max_conversations = max_conversations
        self.max_messages_per_conversation = max_messages_per_conversation
        self._conversations: Dict[str, ConversationContext] = {}

    def get_or_create(self, conversation_id: Optional[str] = None) -> ConversationContext:
        """Retrieve existing context or instantiate a new one with a secure ID."""
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]

        new_id = conversation_id or f"conv_{secrets.token_hex(8)}"
        
        # Evict oldest conversation if capacity exceeded
        if len(self._conversations) >= self.max_conversations:
            oldest_id = min(self._conversations.keys(), key=lambda k: self._conversations[k].updated_at)
            del self._conversations[oldest_id]
            logger.debug(f"Evicted oldest conversation context '{oldest_id}'")

        context = ConversationContext(conversation_id=new_id, max_messages=self.max_messages_per_conversation)
        self._conversations[new_id] = context
        return context

    def get(self, conversation_id: str) -> Optional[ConversationContext]:
        """Retrieve context if present."""
        return self._conversations.get(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        """Remove conversation context."""
        return bool(self._conversations.pop(conversation_id, None))


# Singleton default manager
_default_conversation_manager = ConversationManager()


def get_conversation_manager() -> ConversationManager:
    """Retrieve global default conversation manager."""
    return _default_conversation_manager
