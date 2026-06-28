"""
HostAgent — Agent: Link Manager
Управление партнёрскими ссылками: добавление, UTM-метки,
сокращение, маскировка и аналитика переходов.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, urljoin

from src.core.llm_client import LLMClient, Message, load_prompt
from src.data.database.repository import Repository

logger = logging.getLogger(__name__)

# Паттерн для распознавания URL
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\']+[^\s<>"\'.!,?;:)]'
)


class LinkManagerAgent:
    """Менеджер партнёрских ссылок."""

    def __init__(self, llm: LLMClient, repo: Repository):
        self.llm = llm
        self.repo = repo

    async def handle(self, text: str, user_id: int) -> str:
        text_lower = text.lower()

        # Маршрутизация внутри агента
        if any(kw in text_lower for kw in ["покажи", "список", "мои ссылки", "статистика"]):
            return await self._show_links(user_id)

        if any(kw in text_lower for kw in ["добавь", "создай ссылку", "новая ссылка"]):
            return await self._add_link(text, user_id)

        # По умолчанию — показываем ссылки + помощь
        return await self._show_links(user_id)

    async def _add_link(self, text: str, user_id: int) -> str:
        """Добавляет новую партнёрскую ссылку."""
        # Извлекаем URL из текста
        urls = URL_PATTERN.findall(text)
        if not urls:
            return (
                "🔗 *Добавление ссылки*\n\n"
                "Не нашёл ссылку в твоём сообщении. "
                "Пришли команду в формате:\n\n"
                "«Добавь ссылку https://beget.com/?ref=abc для Beget»\n\n"
                "Или просто пришли URL — я определю хостинг автоматически."
            )

        url = urls[0]

        # Определяем провайдера по домену
        provider = await self._detect_provider(url)
        if not provider:
            return (
                f"Не смог определить хостинг по ссылке: {url}\n"
                "Укажи название хостинга явно, например:\n"
                "«Добавь ссылку {url} — это Beget»"
            )

        # Извлекаем UTM или предлагаем добавить
        utm_source = self._extract_param(text, "source")
        utm_medium = self._extract_param(text, "medium")
        utm_campaign = self._extract_param(text, "campaign")

        # Добавляем в БД
        slug = await self.repo.add_affiliate_link(
            user_id=user_id,
            provider_id=provider.id,
            original_url=url,
            title=f"Ссылка на {provider.name}",
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
        )

        short_url = f"https://hostagent.ru/go/{slug}"

        return (
            f"✅ *Ссылка добавлена!*\n\n"
            f"🏢 Хостинг: *{provider.name}*\n"
            f"🔗 Оригинал: `{url}`\n"
            f"⚡️ Короткая: `{short_url}`\n"
            f"📊 Комиссия: {provider.commission_percent}%\n\n"
            f"Используй короткую ссылку в контенте — "
            f"я буду отслеживать клики и конверсии автоматически."
        )

    async def _detect_provider(self, url: str):
        """Определяет хостинг-провайдера по домену URL."""
        domain = urlparse(url).netloc.lower()
        # Убираем www
        domain = domain.replace("www.", "")

        providers = await self.repo.get_all_providers()
        for p in providers:
            provider_domain = urlparse(p.website).netloc.lower().replace("www.", "")
            if domain == provider_domain or domain.endswith(provider_domain):
                return p
            # Частичное совпадение по ключевой части домена
            key_part = provider_domain.split(".")[0]
            if key_part in domain:
                return p
        return None

    def _extract_param(self, text: str, param: str) -> str:
        """Извлекает UTM-параметр из текста."""
        pattern = rf"utm[_\s]?{param}[=:\s]+([^\s,]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else ""

    def add_utm_to_url(self, url: str, source: str = "telegram",
                       medium: str = "referral", campaign: str = "") -> str:
        """Добавляет UTM-метки к URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        params["utm_source"] = [source]
        params["utm_medium"] = [medium]
        if campaign:
            params["utm_campaign"] = [campaign]

        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    async def _show_links(self, user_id: int) -> str:
        """Показывает все ссылки пользователя со статистикой."""
        links = await self.repo.get_user_links(user_id)

        if not links:
            return (
                "📋 *Твои партнёрские ссылки*\n\n"
                "У тебя пока нет добавленных ссылок.\n\n"
                "Чтобы добавить, напиши:\n"
                "«Добавь ссылку https://beget.com/?ref=твойкод»\n\n"
                "Не знаешь где взять партнёрскую ссылку? "
                "Зарегистрируйся в партнёрской программе хостинга — "
                "это бесплатно!"
            )

        lines = ["📋 *Твои партнёрские ссылки*\n"]
        for l in links:
            short = f"hostagent.ru/go/{l['short_slug']}"
            lines.append(
                f"🏢 *{l['provider_name']}*\n"
                f"   🔗 {short}\n"
                f"   📊 {l['clicks']} кликов · {l['conversions']} конверсий · "
                f"{l['earnings']}₽ заработано\n"
            )
        return "\n".join(lines)
