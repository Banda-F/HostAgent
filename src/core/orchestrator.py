"""
HostAgent — Оркестратор (Router)
Центральный модуль, который принимает запрос пользователя,
классифицирует его намерение и направляет к нужному AI-агенту.
"""
from __future__ import annotations

import logging

from src.core.llm_client import LLMClient, Message, load_prompt
from src.core.types import Intent, AgentResponse, INTENT_KEYWORDS
from src.data.database.models import Database
from src.data.database.repository import Repository
from src.agents.analyst.agent import AnalystAgent
from src.agents.content_creator.agent import ContentCreatorAgent
from src.agents.link_manager.agent import LinkManagerAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Центральный маршрутизатор запросов."""

    def __init__(self, db: Database, llm: LLMClient):
        self.db = db
        self.llm = llm
        self.repo = Repository(db)

        # Инициализируем агентов
        self.analyst = AnalystAgent(llm, self.repo)
        self.content_creator = ContentCreatorAgent(llm, self.repo)
        self.link_manager = LinkManagerAgent(llm, self.repo)

    def classify_intent(self, text: str) -> Intent:
        """Быстрая классификация намерения по ключевым словам."""
        text_lower = text.lower()

        # Сначала проверяем help
        if text_lower.strip() in ("/help", "/start", "помощь", "старт", "что ты умеешь"):
            return Intent.HELP

        # Подсчёт совпадений по каждой категории
        scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            scores[intent] = sum(1 for kw in keywords if kw in text_lower)

        best_intent = max(scores, key=scores.get)
        if scores[best_intent] > 0:
            return best_intent

        return Intent.GENERAL

    async def handle(self, user_id: int, text: str,
                     username: str = "") -> AgentResponse:
        """Главный метод обработки запроса пользователя."""
        # Гарантируем что пользователь есть в БД
        await self.repo.get_or_create_user(0, username)  # системный
        db_user_id = await self.repo.get_or_create_user(
            user_id, username, username
        )

        intent = self.classify_intent(text)
        logger.info(f"Intent: {intent.value} | User: {user_id} | Text: {text[:60]}")

        try:
            if intent == Intent.HELP:
                return AgentResponse(
                    text=self._help_text(),
                    intent=intent,
                    agent_name="system",
                )

            if intent == Intent.ANALYZE or intent == Intent.RECOMMEND:
                response = await self.analyst.handle(text, db_user_id, intent)
                return AgentResponse(
                    text=response, intent=intent, agent_name="analyst"
                )

            if intent == Intent.CREATE_CONTENT:
                response = await self.content_creator.handle(text, db_user_id)
                return AgentResponse(
                    text=response, intent=intent, agent_name="content_creator"
                )

            if intent == Intent.MANAGE_LINKS:
                response = await self.link_manager.handle(text, db_user_id)
                return AgentResponse(
                    text=response, intent=intent, agent_name="link_manager"
                )

            if intent == Intent.EARNINGS_FORECAST:
                response = await self.analyst.forecast_earnings(text, db_user_id)
                return AgentResponse(
                    text=response, intent=intent, agent_name="analyst"
                )

            # GENERAL — общаемся через LLM с системным промптом
            return await self._general_conversation(text, intent)

        except Exception as e:
            logger.exception(f"Error handling request: {e}")
            return AgentResponse(
                text=f"⚠️ Произошла ошибка при обработке запроса: {e}\n\n"
                     "Попробуйте переформулировать запрос или используйте /help.",
                intent=Intent.GENERAL,
                agent_name="error",
            )

    async def _general_conversation(self, text: str, intent: Intent) -> AgentResponse:
        """Общая беседа через LLM с системным промптом."""
        system_prompt = load_prompt("system")
        providers = await self.repo.get_all_providers()
        providers_context = "\n".join(
            f"- {p.name}: {p.commission_percent}% "
            f"({'повторные' if p.recurring else 'разовые'} выплаты) — {p.notes}"
            for p in providers[:8]
        )
        system_prompt += f"\n\n## Известные хостинги:\n{providers_context}"

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=text),
        ]
        response = await self.llm.chat(messages)
        return AgentResponse(
            text=response, intent=intent, agent_name="general"
        )

    def _help_text(self) -> str:
        return (
            "🤖 *HostAgent — твой AI-помощник для заработка на партнёрках хостингов*\n\n"
            "*Что я умею:*\n\n"
            "📊 *Анализ и подбор*\n"
            "• «Сравни Beget и Timeweb»\n"
            "• «Какой хостинг лучше для WordPress?»\n"
            "• «Подбери хостинг с максимальной комиссией»\n\n"
            "✍️ *Генерация контента*\n"
            "• «Напиши пост про Beget для Telegram»\n"
            "• «Создай обзор Timeweb»\n"
            "• «Напиши статью-сравнение хостингов»\n\n"
            "💰 *Прогноз дохода*\n"
            "• «Сколько я заработаю с 1000 подписчиков?»\n"
            "• «Прогноз дохода по Timeweb»\n\n"
            "🔗 *Управление ссылками*\n"
            "• «Добавь мою ссылку на Beget»\n"
            "• «Покажи мои ссылки»\n\n"
            "Просто напиши свой вопрос естественным языком! 👇"
        )
