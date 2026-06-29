"""
HostAgent — Общие типы данных
Вынесены сюда, чтобы избежать циклических импортов между orchestrator и агентами.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    """Возможные намерения пользователя."""
    ANALYZE = "analyze"             # Анализ / сравнение хостингов
    RECOMMEND = "recommend"         # Подобрать хостинг
    CREATE_CONTENT = "create_content"  # Сгенерировать контент
    MANAGE_LINKS = "manage_links"   # Управление ссылками
    EARNINGS_FORECAST = "forecast"  # Прогноз дохода
    GENERAL = "general"             # Общий вопрос / болталка
    HELP = "help"                   # Справка


@dataclass
class AgentResponse:
    """Структурированный ответ агента."""
    text: str
    intent: Intent
    agent_name: str
    metadata: Optional[dict] = None


# Ключевые слова для быстрой классификации (без LLM)
INTENT_KEYWORDS = {
    Intent.ANALYZE: ["сравн", "анализ", "отлич", "разниц", "что лучше", "плюс", "минус", "рейтинг"],
    Intent.RECOMMEND: ["посовет", "подобр", "выбрать", "какой хостинг", "рекоменд", "лучший для"],
    Intent.CREATE_CONTENT: ["напиши", "создай", "сгенерируй", "пост", "статья", "обзор", "отзыв",
                            "текст", "контент", "расскажи о хостинге"],
    Intent.MANAGE_LINKS: ["ссылк", "добавь ссылку", "utm", "сократить", "маскиров"],
    Intent.EARNINGS_FORECAST: ["сколько заработ", "прогноз", "доход", "прибыль", "заработок",
                               "сколько можно"],
    Intent.HELP: ["помощь", "команды", "что умеешь", "справка", "help", "старт"],
}
