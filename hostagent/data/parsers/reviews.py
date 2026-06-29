"""
HostAgent — Парсер отзывов о хостингах
Собирает публичные отзывы и рейтинги из агрегатора ru.hostings.info.
Данные используются аналитиком для более точных рекомендаций.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from hostagent.data.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class ReviewsParser(BaseParser):
    """Парсер отзывов из публичного агрегатора hostings.info."""

    provider_name = "Reviews"
    # Публичная страница рейтинга хостингов РФ
    program_url = "https://ru.hostings.info/hostings/country/russia"
    homepage_url = "https://ru.hostings.info"

    async def parse(self):
        """Собирает рейтинги хостингов из публичного списка."""
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            logger.warning("Reviews: не удалось загрузить страницу рейтингов")
            return

        count_saved = 0

        # Находим карточки хостингов с рейтингом
        # Структура hostings.info: таблица или карточки с названиями и оценками
        hosting_items = soup.select(".hosting-card, .hosting-row, tr, [data-hosting]")
        for item in hosting_items:
            try:
                name = self._extract_hosting_name(item)
                rating = self._extract_rating(item)
                if name and rating:
                    await self._save_review(name, rating, item.get_text(" ", strip=True)[:500])
                    count_saved += 1
            except Exception as e:
                logger.debug(f"Skip item: {e}")
                continue

        # Также пытаемся извлечь общие рейтинги из текста страницы
        text = self.clean_text(soup.get_text(" "))
        await self._extract_ratings_from_text(text)

        logger.info(f"Reviews: обработано {count_saved} элементов")

    def _extract_hosting_name(self, element) -> str | None:
        """Извлекает название хостинга из элемента."""
        # Ищем в ссылках или заголовках
        link = element.select_one("a[href*='/hostings/'], .hosting-name, .name, h3, h4")
        if link:
            name = self.clean_text(link.get_text())
            # Очищаем от лишнего
            name = re.sub(r'\s*\([^)]*\)', '', name).strip()
            return name if name and len(name) < 50 else None
        return None

    def _extract_rating(self, element) -> float | None:
        """Извлекает числовой рейтинг (1-5 или 0-10)."""
        # Ищем элементы с рейтингом
        rating_el = element.select_one(".rating, .score, .stars, [data-rating]")
        if rating_el:
            return self.extract_percent(rating_el.get("data-rating", ""))

        # Пытаемся найти число в тексте
        text = element.get_text(" ", strip=True)
        # Ищем паттерн "4.5" или "9.2/10"
        match = re.search(r'(\d+\.?\d*)\s*(?:/\s*10|из\s*10|из\s*5)?', text)
        if match:
            val = float(match.group(1))
            if 0 < val <= 10:
                return val
        return None

    async def _save_review(self, provider_name: str, rating: float, text: str):
        """Сохраняет отзыв в БД, привязывая к провайдеру."""
        # Находим провайдера по имени (нечёткое совпадение)
        provider = await self.db.fetchone(
            "SELECT id, name FROM hosting_providers WHERE is_active=1"
        )
        # Точное или частичное совпадение
        all_providers = await self.db.fetchall(
            "SELECT id, name FROM hosting_providers WHERE is_active=1"
        )
        provider_id = None
        prov_name_lower = provider_name.lower()
        for p in all_providers:
            p_name_lower = p["name"].lower()
            if (prov_name_lower in p_name_lower or
                p_name_lower in prov_name_lower):
                provider_id = p["id"]
                break

        if not provider_id:
            return  # Хостинг не из нашего списка

        # Проверяем, нет ли уже такой записи
        existing = await self.db.fetchone(
            """SELECT id FROM reviews_scraped
               WHERE provider_id=? AND source='hostings.info'
               AND review_date=?""",
            (provider_id, datetime.utcnow().strftime("%Y-%m-%d")),
        )
        if existing:
            return  # Уже сохранено сегодня

        await self.db.execute(
            """INSERT INTO reviews_scraped
               (provider_id, source, rating, review_text, review_date, url)
               VALUES (?, 'hostings.info', ?, ?, ?, ?)""",
            (provider_id, rating, text[:500],
             datetime.utcnow().strftime("%Y-%m-%d"), self.program_url),
        )

    async def _extract_ratings_from_text(self, text: str):
        """Достаёт рейтинги, если не удалось распарсить DOM."""
        # Ищем паттерны вида "Beget 4.5" или "Timeweb — 9.2/10"
        known_hosts = ["Beget", "Timeweb", "Reg.ru", "SpaceWeb", "Sprinthost",
                       "FirstVDS", "Aéza", "Aeza", "Hostinger"]
        for host in known_hosts:
            # Ищем рейтинг рядом с названием
            pattern = rf'{re.escape(host)}[\s\-:]*(\d+\.?\d*)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rating = float(match.group(1))
                if 0 < rating <= 10:
                    await self._save_review(host, rating, f"Рейтинг: {rating}")
                    logger.debug(f"Found rating for {host}: {rating}")
