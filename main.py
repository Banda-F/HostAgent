"""
HostAgent — Точка входа
Запускает все компоненты системы: сборщик данных, Telegram-бот и веб-дашборд.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import click
from config.config import get_config, load_config
from src.data.database.models import Database, seed_database
from src.core.llm_client import LLMClient
from src.core.orchestrator import Orchestrator
from src.data.parsers.collector import DataCollector

logger = logging.getLogger("hostagent")


def setup_logging():
    cfg = get_config()
    log_path = Path(cfg.logging.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, cfg.logging.level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )


async def init_database() -> Database:
    """Инициализирует БД и заполняет начальными данными."""
    cfg = get_config()
    db = Database(cfg.database.path)
    await db.connect()
    await seed_database(db)
    logger.info("Database initialized and seeded.")
    return db


async def run_bot(db: Database):
    """Запускает Telegram-бот."""
    from src.services.telegram_bot.bot import HostAgentBot

    llm = LLMClient()
    orchestrator = Orchestrator(db, llm)
    bot = HostAgentBot(db, orchestrator)
    await bot.run()


async def run_web(db: Database):
    """Запускает веб-дашборд."""
    import uvicorn
    from src.services.web_dashboard.app import app as web_app, get_db as _init_db

    cfg = get_config()
    logger.info(f"Web dashboard: http://{cfg.web.host}:{cfg.web.port}")
    uvicorn.run(web_app, host=cfg.web.host, port=cfg.web.port, log_level="info")


async def run_collector(db: Database):
    """Запускает сборщик данных (один раз)."""
    collector = DataCollector(db)
    await collector.collect_all()


async def run_all():
    """Запускает все компоненты параллельно."""
    db = await init_database()

    # Сначала собираем данные
    logger.info("Collecting hosting data...")
    collector = DataCollector(db)
    await collector.collect_all()

    # Запускаем бота и веб параллельно
    tasks = [
        asyncio.create_task(run_bot(db)),
        asyncio.create_task(run_web(db)),
    ]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        for t in tasks:
            t.cancel()
    finally:
        await db.close()


@click.group()
@click.option("--config", "-c", default=None, help="Путь к config.yaml")
def cli(config):
    """🤖 HostAgent — AI-агент для заработка на партнёрках хостингов."""
    if config:
        load_config(config)


@cli.command()
def bot():
    """Запустить Telegram-бот."""
    setup_logging()
    asyncio.run(_run_component("bot"))


@cli.command()
def web():
    """Запустить веб-дашборд."""
    setup_logging()
    asyncio.run(_run_component("web"))


@cli.command()
def collect():
    """Собрать данные о хостингах."""
    setup_logging()
    asyncio.run(_run_component("collector"))


@cli.command(name="all")
def run_all_cmd():
    """Запустить всё (сбор данных + бот + дашборд)."""
    setup_logging()
    asyncio.run(run_all())


async def _run_component(component: str):
    db = await init_database()
    if component == "bot":
        await run_bot(db)
    elif component == "web":
        await run_web(db)
    elif component == "collector":
        await run_collector(db)
    await db.close()


if __name__ == "__main__":
    cli()
