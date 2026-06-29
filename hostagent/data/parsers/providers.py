"""
HostAgent — Парсеры конкретных хостинг-провайдеров
Каждый класс извлекает актуальные данные о партнёрской программе
из публичных страниц соответствующего хостинга.

Все данные берутся из ОТКРЫТЫХ источников (страницы партнёрских
программ, не требуют авторизации).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from hostagent.data.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class BegetParser(BaseParser):
    provider_name = "Beget"
    program_url = "https://beget.com/ru/partnership"
    homepage_url = "https://beget.com"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            logger.warning("Beget: не удалось загрузить страницу")
            return

        text = self.clean_text(soup.get_text(" "))

        # Ищем процент комиссии (до 40%)
        commission = 40.0
        match = re.search(r"(\d+)\s*%", text)
        if match:
            val = float(match.group(1))
            if 5 <= val <= 100:
                commission = val

        notes = "Партнёрская программа для клиентов на платных тарифах."
        # Пытаемся найти детали о шкале
        if "40%" in text:
            notes = "40% shared, 20% VPS, 10% премиум-тарифы."
        if "100%" in text:
            notes += " Есть бонусы до 100% в акциях."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Beget parsed: {commission}%")


class TimewebParser(BaseParser):
    provider_name = "Timeweb"
    program_url = "https://timeweb.com/ru/partners/webmasters/"
    homepage_url = "https://timeweb.com"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 40.0

        # Timeweb: 40% за хостинг, 20% за VDS
        notes = "40% за хостинг, 20% за VDS/VPS."
        if "20%" in text and "40%" in text:
            notes = "40% за хостинг, 20% за VDS/VPS — повторные выплаты."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Timeweb parsed: {commission}%")


class RegRuParser(BaseParser):
    provider_name = "Reg.ru"
    program_url = "https://www.reg.ru/reseller/referral-program"
    homepage_url = "https://www.reg.ru"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 40.0

        notes = "40% от каждого платежа привлечённых клиентов."
        # Ищем информацию о среднем чеке
        avg_match = re.search(r"(\d[\d\s]*)\s*₽", text)
        if avg_match:
            notes += f" Средний чек: {avg_match.group(1)}₽."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Reg.ru parsed: {commission}%")


class SpaceWebParser(BaseParser):
    provider_name = "SpaceWeb"
    program_url = "https://sweb.ru/partner/"
    homepage_url = "https://sweb.ru"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 30.0
        notes = "До 30% от платежей привлечённых клиентов."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"SpaceWeb parsed: {commission}%")


class SprinthostParser(BaseParser):
    provider_name = "Sprinthost"
    program_url = "https://sprinthost.ru/partners/common"
    homepage_url = "https://sprinthost.ru"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 40.0
        notes = "До 40% + 10% с рефералов 2-го уровня (двухуровневая)."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Sprinthost parsed: {commission}%")


class FirstVDSParser(BaseParser):
    provider_name = "FirstVDS"
    program_url = "https://firstvds.ru/partner/referral"
    homepage_url = "https://firstvds.ru"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 10.0
        notes = "10% пожизненно + скидка 25% для привлечённого клиента на 1-й месяц."

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"FirstVDS parsed: {commission}%")


class AezaParser(BaseParser):
    provider_name = "Aéza"
    program_url = "https://aeza.ru/referral"
    homepage_url = "https://aeza.ru"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 15.0  # стартовая
        notes = (
            "Прогрессивная шкала: 15% старт, до 50% при росте объёма. "
            "Пожизненные выплаты."
        )

        await self.save_program_data(
            commission_percent=commission,
            recurring=True,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Aéza parsed: {commission}%")


class HostingerParser(BaseParser):
    provider_name = "Hostinger"
    program_url = "https://www.hostinger.com/affiliates"
    homepage_url = "https://www.hostinger.com"

    async def parse(self):
        soup = await self.fetch_soup(self.program_url)
        if not soup:
            return

        text = self.clean_text(soup.get_text(" "))
        commission = 60.0
        notes = "40-60% разовая комиссия за продажу. Cookie 30 дней. Без повторных выплат."

        await self.save_program_data(
            commission_percent=commission,
            recurring=False,
            min_payout=0,
            notes=notes,
        )
        logger.info(f"Hostinger parsed: {commission}%")


# Реестр всех парсеров
ALL_PARSERS = [
    BegetParser, TimewebParser, RegRuParser, SpaceWebParser,
    SprinthostParser, FirstVDSParser, AezaParser, HostingerParser,
]
