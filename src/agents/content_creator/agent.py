"""
HostAgent — Agent: Content Creator
Генерирует готовый контент с партнёрскими ссылками: посты, статьи,
обзоры, сравнения, рекламные креативы.
"""
from __future__ import annotations

import json
import logging
import re

from src.core.llm_client import LLMClient, Message, load_prompt
from src.data.database.repository import Repository

logger = logging.getLogger(__name__)


# Определяем тип контента по запросу
CONTENT_TYPES = {
    "telegram_post": ["пост", "телеграм", "telegram", "тг", "канал"],
    "article": ["статья", "статью", "материал", "лонгрид"],
    "review": ["обзор", "отзыв", "ревью"],
    "comparison": ["сравнен", "сравн", "что лучше", "или"],
    "ad": ["реклам", "креатив", "промо", "pr"],
    "seo": ["seo", "сео", "для сайта", "описание"],
}


class ContentCreatorAgent:
    """Генератор контента с партнёрскими ссылками."""

    def __init__(self, llm: LLMClient, repo: Repository):
        self.llm = llm
        self.repo = repo

    async def handle(self, text: str, user_id: int) -> str:
        # Определяем тип контента
        content_type = self._detect_content_type(text)

        # Находим упомянутые хостинги
        providers = await self.repo.get_all_providers()
        mentioned = self._find_mentioned_providers(text, providers)

        # Получаем ссылки пользователя для этих хостингов
        user_links = await self.repo.get_user_links(user_id)
        link_map = {l["provider_name"]: l for l in user_links}

        # Генерируем контент
        content = await self._generate_content(
            text, content_type, mentioned, providers, link_map
        )

        # Сохраняем в БД
        await self.repo.save_content(
            user_id=user_id,
            content_type=content_type,
            title=self._extract_title(content),
            body=content,
            platforms=[content_type],
            linked_link_ids=[link_map[m.name]["id"] for m in mentioned
                             if m.name in link_map],
        )

        return content

    def _detect_content_type(self, text: str) -> str:
        text_lower = text.lower()
        for ctype, keywords in CONTENT_TYPES.items():
            if any(kw in text_lower for kw in keywords):
                return ctype
        return "telegram_post"  # по умолчанию

    def _find_mentioned_providers(self, text: str, providers) -> list:
        text_lower = text.lower()
        found = []
        for p in providers:
            # Проверяем разные варианты написания
            variants = [p.name.lower(), p.name.lower().replace("ё", "е")]
            if any(v in text_lower for v in variants):
                found.append(p)
        return found

    async def _generate_content(self, request: str, content_type: str,
                                 mentioned: list, all_providers: list,
                                 link_map: dict) -> str:
        """Генерирует контент через LLM с учётом типа и контекста."""
        system_prompt = load_prompt("content_creator")

        # Строим контекст по хостингам
        providers_context = "\n".join(
            f"- {p.name}: {p.commission_percent}% комиссия, "
            f"{p.website}. {p.description}"
            for p in (mentioned or all_providers[:5])
        )

        # Инструкция по ссылкам
        links_instruction = ""
        for p in mentioned:
            if p.name in link_map:
                link = link_map[p.name]
                short_url = f"https://hostagent.ru/go/{link['short_slug']}"
                links_instruction += (
                    f"\n• Для {p.name} используй ссылку: {short_url}"
                )
            else:
                links_instruction += (
                    f"\n• Для {p.name} ссылка ещё не добавлена — "
                    f"используй заглушку [ССЫЛКА_{p.name.upper()}] "
                    f"и предложи пользователю добавить её командой /addlink"
                )

        type_guidelines = {
            "telegram_post": (
                "Формат: пост для Telegram (до 4096 символов). "
                "Эмодзи уместны. Чёткая структура: цепляющий заголовок → "
                "польза → призыв к действию. Вставь ссылку естественно."
            ),
            "article": (
                "Формат: полноценная статья (1500-3000 символов). "
                "Заголовок H1, подзаголовки H2, списки. "
                "SEO-оптимизированная, без переспама."
            ),
            "review": (
                "Формат: честный обзор. Плюсы, минусы, личный опыт. "
                "Балanced подход вызывает больше доверия → выше конверсия."
            ),
            "comparison": (
                "Формат: сравнительная таблица/текст. "
                "Объективное сравнение по ключевым параметрам. "
                "Вывод с рекомендацией."
            ),
            "ad": (
                "Формат: рекламный креатив. Цепляющий, короткий. "
                "Оффер → выгода → призыв. Не слишком агрессивно."
            ),
            "seo": (
                "Формат: SEO-описание для страницы. "
                "Ключевые слова вплетены естественно. "
                "Мета-описание в конце."
            ),
        }

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="system", content=(
                f"## Тип контента: {content_type}\n"
                f"{type_guidelines.get(content_type, '')}\n\n"
                f"## Хостинги для упоминания:\n{providers_context}\n\n"
                f"## Партнёрские ссылки:{links_instruction or ' (не указаны)'}"
            )),
            Message(role="user", content=request),
        ]

        return await self.llm.chat(messages, temperature=0.8)

    def _extract_title(self, content: str) -> str:
        """Извлекает заголовок из сгенерированного контента."""
        lines = content.strip().split("\n")
        for line in lines[:3]:
            clean = line.strip().lstrip("#").strip()
            clean = re.sub(r"[*_`]", "", clean)
            if clean and len(clean) < 200:
                return clean
        return lines[0][:100] if lines else "Без заголовка"
