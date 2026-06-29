"""
HostAgent — Базовый класс парсера
Общий функционал для всех парсеров хостингов:
вежливые HTTP-запросы, задержки, обработка ошибок, кэширование.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config.config import get_config
from hostagent.data.database.models import Database
from hostagent.data.database.repository import Repository

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Базовый класс для парсеров данных о хостингах."""

    # Имя провайдера (переопределяется в подклассах)
    provider_name: str = ""
    # URL страницы партнёрской программы
    program_url: str = ""
    # URL главной страницы
    homepage_url: str = ""

    def __init__(self, db: Database):
        self.db = db
        self.repo = Repository(db)
        cfg = get_config()
        self.user_agent = cfg.scraper.user_agent
        self.request_delay = cfg.scraper.request_delay
        self.timeout = cfg.scraper.request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, url: str) -> Optional[str]:
        """Вежливый HTTP GET с задержкой."""
        await asyncio.sleep(self.request_delay)
        client = await self.get_client()
        try:
            logger.info(f"[{self.provider_name}] Fetching: {url}")
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[{self.provider_name}] HTTP {e.response.status_code} for {url}"
            )
        except Exception as e:
            logger.error(f"[{self.provider_name}] Fetch failed {url}: {e}")
        return None

    async def fetch_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Возвращает BeautifulSoup-объект страницы."""
        html = await self.fetch(url)
        if html is None:
            return None
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def extract_percent(text: str) -> Optional[float]:
        """Извлекает процент из текста (например, '40%' -> 40.0)."""
        if not text:
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(text))
        if match:
            return float(match.group(1).replace(",", "."))
        return None

    @staticmethod
    def extract_money(text: str) -> Optional[float]:
        """Извлекает денежную сумму (₽, €, $)."""
        if not text:
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*[₽€$руб]", str(text), re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", "."))
        match = re.search(r"(\d+(?:[.,]\d+)?)", str(text))
        return float(match.group(1).replace(",", ".")) if match else None

    @staticmethod
    def clean_text(text: str) -> str:
        """Очищает текст от лишних пробелов и переносов."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    async def save_program_data(self, commission_percent: float,
                                 recurring: bool, min_payout: float,
                                 notes: str):
        """Сохраняет/обновляет данные о партнёрской программе в БД."""
        now = datetime.utcnow().isoformat()

        # Находим провайдера
        provider = await self.db.fetchone(
            "SELECT id FROM hosting_providers WHERE name=?", (self.provider_name,)
        )
        if not provider:
            logger.warning(f"[{self.provider_name}] Provider not found in DB")
            return

        provider_id = provider["id"]

        # Проверяем, есть ли уже запись
        existing = await self.db.fetchone(
            "SELECT * FROM affiliate_programs WHERE provider_id=?", (provider_id,)
        )

        if existing:
            # Логируем изменения
            old_comm = existing["commission_percent"]
            if old_comm != commission_percent:
                await self.db.execute(
                    """INSERT INTO program_changes_log
                       (program_id, field_changed, old_value, new_value)
                       VALUES (?, 'commission_percent', ?, ?)""",
                    (existing["id"], str(old_comm), str(commission_percent)),
                )
                logger.info(
                    f"[{self.provider_name}] Commission changed: "
                    f"{old_comm}% -> {commission_percent}%"
                )

            await self.db.execute(
                """UPDATE affiliate_programs SET
                   commission_percent=?, recurring=?, min_payout=?,
                   notes=?, last_updated=?
                   WHERE provider_id=?""",
                (commission_percent, int(recurring), min_payout,
                 notes, now, provider_id),
            )
        else:
            await self.db.execute(
                """INSERT INTO affiliate_programs
                   (provider_id, program_name, commission_percent, recurring,
                    min_payout, conditions_url, notes, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (provider_id, self.provider_name, commission_percent,
                 int(recurring), min_payout, self.program_url,
                 notes, now),
            )

    @abstractmethod
    async def parse(self):
        """Основной метод парсинга. Реализуется в подклассах."""
        ...

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
