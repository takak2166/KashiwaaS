"""Bot domain model (aggregates, ports)."""

from src.bot.domain.conversation import ThreadConversation
from src.bot.domain.mention import BotMention, is_duplicate_assistant_reply
from src.bot.domain.repository import ThreadConversationRepository

__all__ = [
    "BotMention",
    "ThreadConversation",
    "ThreadConversationRepository",
    "is_duplicate_assistant_reply",
]
