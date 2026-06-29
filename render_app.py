"""
HostAgent — Render-точка входа
Единый FastAPI-процесс: веб-дашборд + Telegram-бот (background polling).
Render запускает через: gunicorn render_app:app

Health-check: GET /health
Dashboard:    GET /
API:          /api/*
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Корень проекта в Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Логирование в stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("hostagent")

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.config import get_config
from hostagent.data.database.models import Database, seed_database
from hostagent.data.database.repository import Repository

# ============================================================
# FastAPI app
# ============================================================
app = FastAPI(title="HostAgent", version="1.0.0")

TEMPLATES_DIR = project_root / "src" / "services" / "web_dashboard" / "templates"
STATIC_DIR = project_root / "src" / "services" / "web_dashboard" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Глобальные ссылки
_db: Optional[Database] = None
_repo: Optional[Repository] = None
_bot_task = None


def get_db() -> Database:
    return _db


def get_repo() -> Repository:
    return _repo


# ============================================================
# Startup / Shutdown
# ============================================================
@app.on_event("startup")
async def on_startup():
    global _db, _repo, _bot_task

    logger.info("=" * 50)
    logger.info("HostAgent starting on Render...")
    logger.info("=" * 50)

    # 1. БД
    cfg = get_config()
    _db = Database(cfg.database.path)
    await _db.connect()
    await seed_database(_db)
    _repo = Repository(_db)
    logger.info("Database initialized and seeded.")

    # 2. Сбор данных о хостингах
    try:
        from hostagent.data.parsers.collector import DataCollector
        collector = DataCollector(_db)
        await collector.collect_all()
        logger.info("Data collection completed.")
    except Exception as e:
        logger.error(f"Data collection failed (non-critical): {e}")

    # 3. Telegram-бот в фоне
    try:
        from hostagent.core.llm_client import LLMClient
        from hostagent.core.orchestrator import Orchestrator
        from hostagent.services.telegram_bot.bot import HostAgentBot

        llm = LLMClient()
        orchestrator = Orchestrator(_db, llm)
        bot_instance = HostAgentBot(_db, orchestrator)
        bot_instance.setup()

        _bot_task = asyncio.create_task(_run_bot_forever(bot_instance))
        logger.info("Telegram bot started as background task.")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        # Не падаем — веб-дашборд всё равно работает


async def _run_bot_forever(bot_instance):
    """Запускает polling бота в фоне, перезапускает при ошибках."""
    while True:
        try:
            await bot_instance.app.initialize()
            await bot_instance.app.start()
            await bot_instance.app.updater.start_polling(drop_pending_updates=True)
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Bot task cancelled.")
            break
        except Exception as e:
            logger.error(f"Bot polling error: {e}. Restarting in 10s...")
            await asyncio.sleep(10)


@app.on_event("shutdown")
async def on_shutdown():
    if _bot_task:
        _bot_task.cancel()
    if _db:
        await _db.close()
    logger.info("HostAgent stopped.")


# ============================================================
# Health-check
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "HostAgent", "version": "1.0.0"}


# ============================================================
# Dashboard
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, repo: Repository = Depends(get_repo)):
    user_id = request.query_params.get("user_id", 1)
    stats = await repo.get_dashboard_stats(int(user_id))
    providers = await repo.get_all_providers()
    links = await repo.get_user_links(int(user_id))
    content = await repo.get_user_content(int(user_id))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "providers": providers,
        "links": links[:20],
        "content": content[:10],
        "user_id": user_id,
    })


# ============================================================
# API endpoints
# ============================================================
@app.get("/api/providers")
async def api_providers(repo: Repository = Depends(get_repo)):
    providers = await repo.get_all_providers()
    return [
        {
            "name": p.name, "website": p.website,
            "commission": p.commission_percent,
            "recurring": p.recurring,
            "min_payout": p.min_payout,
            "notes": p.notes,
            "conditions_url": p.conditions_url,
        }
        for p in providers
    ]


@app.get("/api/stats/{user_id}")
async def api_stats(user_id: int, repo: Repository = Depends(get_repo)):
    return await repo.get_dashboard_stats(user_id)


@app.get("/api/links/{user_id}")
async def api_links(user_id: int, repo: Repository = Depends(get_repo)):
    return await repo.get_user_links(user_id)


@app.get("/api/content/{user_id}")
async def api_content(user_id: int, repo: Repository = Depends(get_repo)):
    return await repo.get_user_content(user_id)


@app.post("/api/link/redirect/{slug}")
async def api_redirect(slug: str, repo: Repository = Depends(get_repo)):
    link = await repo.get_link_by_slug(slug)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await repo.record_click(link["id"])
    return RedirectResponse(url=link["original_url"], status_code=307)


@app.get("/api/comparison")
async def api_comparison(repo: Repository = Depends(get_repo)):
    providers = await repo.get_all_providers()
    return [
        {
            "name": p.name,
            "commission": p.commission_percent,
            "recurring": "Да" if p.recurring else "Нет",
            "min_payout": p.min_payout,
            "url": p.conditions_url,
        }
        for p in providers
    ]


# ============================================================
# Локальный запуск
# ============================================================
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
