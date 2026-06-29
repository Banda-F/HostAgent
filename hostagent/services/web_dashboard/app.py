"""
HostAgent — Веб-дашборд
FastAPI-приложение для визуальной аналитики партнёрского заработка.
Показывает статистику ссылок, кликов, контента и прогнозы.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.config import get_config
from hostagent.data.database.models import Database, seed_database
from hostagent.data.database.repository import Repository

logger = logging.getLogger(__name__)

# Пути
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# FastAPI
app = FastAPI(title="HostAgent Dashboard", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Глобальные зависимости
_db: Optional[Database] = None
_repo: Optional[Repository] = None


async def get_db() -> Database:
    global _db
    if _db is None:
        cfg = get_config()
        _db = Database(cfg.database.path)
        await _db.connect()
        await seed_database(_db)
    return _db


async def get_repo() -> Repository:
    global _repo
    if _repo is None:
        db = await get_db()
        _repo = Repository(db)
    return _repo


# ===== Монтаж статики =====
STATIC_DIR.mkdir(parents=True, exist_ok=True)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ===== Главная страница =====

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, repo: Repository = Depends(get_repo)):
    """Главная страница дашборда — обзорная статистика."""
    # Берём данные первого пользователя (для демо) или переданного
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


# ===== API =====

@app.get("/api/providers")
async def api_providers(repo: Repository = Depends(get_repo)):
    """Список всех хостинг-провайдеров с условиями."""
    providers = await repo.get_all_providers()
    return [
        {
            "name": p.name,
            "website": p.website,
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
    """Статистика пользователя."""
    stats = await repo.get_dashboard_stats(user_id)
    return stats


@app.get("/api/links/{user_id}")
async def api_links(user_id: int, repo: Repository = Depends(get_repo)):
    """Список ссылок пользователя."""
    links = await repo.get_user_links(user_id)
    return links


@app.get("/api/content/{user_id}")
async def api_content(user_id: int, repo: Repository = Depends(get_repo)):
    """Список контента пользователя."""
    content = await repo.get_user_content(user_id)
    return content


@app.post("/api/link/redirect/{slug}")
async def api_redirect(slug: str, repo: Repository = Depends(get_repo)):
    """Редирект по короткой ссылке + логирование клика."""
    link = await repo.get_link_by_slug(slug)
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")

    # Логируем клик
    await repo.record_click(link["id"])

    # Перенаправляем на оригинальный URL
    return RedirectResponse(url=link["original_url"], status_code=307)


@app.get("/api/comparison")
async def api_comparison(repo: Repository = Depends(get_repo)):
    """Данные для сравнительной таблицы хостингов."""
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


# ===== Запуск =====

async def start_web():
    """Запускает веб-дашборд."""
    import uvicorn
    cfg = get_config()
    await get_db()  # Инициализируем БД
    logger.info(f"Starting web dashboard on {cfg.web.host}:{cfg.web.port}")
    uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_web())
