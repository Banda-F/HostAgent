"""
HostAgent — Сборщик данных (Collector)
Оркеструет работу всех парсеров: запускает их последовательно,
собирает данные о партнёрских программах и отзывы.
Может запускаться по расписанию через APScheduler.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from hostagent.data.database.models import Database, seed_database
from hostagent.data.parsers.base import BaseParser
from hostagent.data.parsers.providers import ALL_PARSERS
from hostagent.data.parsers.reviews import ReviewsParser

logger = logging.getLogger(__name__)


class DataCollector:
    """Центральный сборщик данных о хостингах."""

    def __init__(self, db: Database):
        self.db = db
        self.parsers: list[BaseParser] = []

    def init_parsers(self):
        """Создаёт экземпляры всех парсеров."""
        self.parsers = [ParserClass(self.db) for ParserClass in ALL_PARSERS]

    async def collect_all(self):
        """Полный цикл сбора данных со всех источников."""
        logger.info("=" * 60)
        logger.info("Starting full data collection")
        logger.info("=" * 60)

        # Сначала заполняем БД начальными данными
        await seed_database(self.db)

        # Инициализируем парсеры
        self.init_parsers()

        results = {"success": [], "failed": []}

        # Запускаем парсеры последовательно (вежливо к сайтам)
        for parser in self.parsers:
            try:
                logger.info(f"--- Parsing {parser.provider_name} ---")
                await parser.parse()
                results["success"].append(parser.provider_name)
            except Exception as e:
                logger.error(f"Failed to parse {parser.provider_name}: {e}")
                results["failed"].append(parser.provider_name)
            finally:
                await parser.close()

        # Собираем отзывы из публичного агрегатора
        try:
            logger.info("--- Collecting reviews ---")
            reviews_parser = ReviewsParser(self.db)
            await reviews_parser.parse()
            await reviews_parser.close()
        except Exception as e:
            logger.error(f"Reviews collection failed: {e}")

        logger.info("=" * 60)
        logger.info(
            f"Collection done. Success: {len(results['success'])}, "
            f"Failed: {len(results['failed'])}"
        )
        if results["failed"]:
            logger.warning(f"Failed providers: {results['failed']}")
        logger.info("=" * 60)

        return results

    async def collect_single(self, provider_name: str) -> bool:
        """Собирает данные только по одному провайдеру."""
        self.init_parsers()
        for parser in self.parsers:
            if parser.provider_name.lower() == provider_name.lower():
                try:
                    await parser.parse()
                    await parser.close()
                    return True
                except Exception as e:
                    logger.error(f"Parse {provider_name} failed: {e}")
                    return False
                finally:
                    await parser.close()
        return False


async def run_collection():
    """Точка входа для запуска сбора данных."""
    db = Database(get_db_path())
    await db.connect()

    collector = DataCollector(db)
    await collector.collect_all()
    await db.close()


def get_db_path() -> str:
    from config.config import get_config
    return get_config().database.path


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_collection())
