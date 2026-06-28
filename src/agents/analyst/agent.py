"""
HostAgent — Agent: Analyst
Аналитик партнёрских программ. Анализирует, сравнивает хостинги,
даёт рекомендации и прогнозирует доход.
"""
from __future__ import annotations

import logging

from src.core.llm_client import LLMClient, Message, load_prompt
from src.core.types import Intent
from src.data.database.repository import Repository

logger = logging.getLogger(__name__)


class AnalystAgent:
    """Агент-аналитик: сравнение, рекомендации, прогнозы дохода."""

    def __init__(self, llm: LLMClient, repo: Repository):
        self.llm = llm
        self.repo = repo

    async def handle(self, text: str, user_id: int, intent: Intent) -> str:
        if intent == Intent.RECOMMEND:
            return await self.recommend(text, user_id)
        return await self.analyze(text, user_id)

    def _build_context(self) -> str:
        """Синхронно строит контекст — но данные нужны асинхронно, поэтому заглушка.
        Реальная сборка в _gather_context."""
        return ""

    async def _gather_context(self, user_id: int) -> str:
        """Собирает контекст из БД для передачи в LLM."""
        providers = await self.repo.get_all_providers()
        lines = []
        for p in providers:
            recur = "повторные выплаты" if p.recurring else "только разовая"
            lines.append(
                f"• {p.name} ({p.website}): комиссия {p.commission_percent}%, "
                f"{recur}. Мин. вывод: {p.min_payout}₽. {p.notes} "
                f"Условия: {p.conditions_url}"
            )
        return "\n".join(lines)

    async def analyze(self, text: str, user_id: int) -> str:
        """Анализ / сравнение хостингов."""
        system_prompt = load_prompt("analyst")
        context = await self._gather_context(user_id)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="system", content=f"## Текущие данные о хостингах:\n{context}"),
            Message(role="user", content=text),
        ]
        return await self.llm.chat(messages, temperature=0.4)

    async def recommend(self, text: str, user_id: int) -> str:
        """Подбор хостинга под задачу пользователя."""
        system_prompt = load_prompt("analyst")
        context = await self._gather_context(user_id)

        enhanced_prompt = (
            f"{system_prompt}\n\n"
            "## Твоя задача — ПОДОБРАТЬ лучший хостинг.\n"
            "Учти: тип проекта (блог, магазин, лендинг), бюджет, технические требования.\n"
            "Дай 1-3 конкретных рекомендации с обоснованием и расчётом потенциального дохода.\n"
        )

        messages = [
            Message(role="system", content=enhanced_prompt),
            Message(role="system", content=f"## Данные о хостингах:\n{context}"),
            Message(role="user", content=text),
        ]
        return await self.llm.chat(messages, temperature=0.5)

    async def forecast_earnings(self, text: str, user_id: int) -> str:
        """Прогноз потенциального дохода вебмастера."""
        system_prompt = load_prompt("analyst")
        context = await self._gather_context(user_id)
        user_links = await self.repo.get_user_links(user_id)

        links_info = ""
        if user_links:
            links_info = "\n## Текущие ссылки пользователя:\n" + "\n".join(
                f"- {l['provider_name']}: {l['clicks']} кликов, "
                f"{l['conversions']} конверсий, заработок {l['earnings']}₽"
                for l in user_links
            )

        forecast_prompt = (
            f"{system_prompt}\n\n"
            "## Твоя задача — РАССЧИТАТЬ ПРОГНОЗ ДОХОДА.\n"
            "Учитывай:\n"
            "• Размер аудитории и конверсию (обычно 0.5–3% для хостинга)\n"
            "• Средний чек хостинга (для РФ: shared 200-500₽/мес, VPS 500-3000₽/мес)\n"
            "• Процент комиссии и наличие повторных выплат\n"
            "• LTV клиента (обычно 6-18 месяцев)\n"
            "Дай пессимистичный, реалистичный и оптимистичный сценарии.\n"
        )

        messages = [
            Message(role="system", content=forecast_prompt),
            Message(role="system", content=f"## Данные о хостингах:\n{context}{links_info}"),
            Message(role="user", content=text),
        ]
        return await self.llm.chat(messages, temperature=0.3)
