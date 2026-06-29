"""
HostAgent — Модели базы данных
SQLite-схема для хранения данных о хостингах, партнёрских программах,
пользователях, ссылках и сгенерированном контенте.
"""
from __future__ import annotations

import sqlite3
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config.config import get_config


SCHEMA = """
-- Провайдеры хостинга
CREATE TABLE IF NOT EXISTS hosting_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    website TEXT NOT NULL,
    description TEXT,
    logo_url TEXT,
    country TEXT DEFAULT 'RU',
    is_active INTEGER DEFAULT 1,
    last_updated TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Партнёрские программы
CREATE TABLE IF NOT EXISTS affiliate_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,
    program_name TEXT NOT NULL,
    commission_percent REAL NOT NULL DEFAULT 0,
    commission_type TEXT DEFAULT 'percent',  -- percent, fixed, tiered
    recurring INTEGER DEFAULT 1,  -- 1=повторные выплаты, 0=разовые
    min_payout REAL DEFAULT 0,
    payout_frequency TEXT,        -- monthly, weekly, on_request
    cookie_lifetime_days INTEGER,
    signup_bonus REAL DEFAULT 0,
    second_tier_percent REAL DEFAULT 0,
    conditions_url TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    last_updated TEXT,
    FOREIGN KEY (provider_id) REFERENCES hosting_providers(id),
    UNIQUE(provider_id, program_name)
);

-- Тарифные планы хостинга
CREATE TABLE IF NOT EXISTS hosting_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,
    plan_type TEXT NOT NULL,      -- shared, vps, dedicated, cloud, wordpress
    plan_name TEXT NOT NULL,
    price_monthly REAL,
    price_yearly REAL,
    currency TEXT DEFAULT 'RUB',
    specs TEXT,                    -- JSON: cpu, ram, disk, bandwidth
    features TEXT,                 -- JSON array
    url TEXT,
    is_active INTEGER DEFAULT 1,
    last_updated TEXT,
    FOREIGN KEY (provider_id) REFERENCES hosting_providers(id)
);

-- Отзывы о хостингах (собираются из публичных источников)
CREATE TABLE IF NOT EXISTS reviews_scraped (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,
    source TEXT,                   -- hostings.info, otzovik, etc.
    rating REAL,                   -- 1-5
    review_text TEXT,
    author TEXT,
    review_date TEXT,
    url TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES hosting_providers(id)
);

-- Пользователи агента (вебмастера)
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    display_name TEXT,
    niche TEXT,                    -- ниша: блогер, фрилансер, веб-студия
    audience_size INTEGER DEFAULT 0,
    primary_channel TEXT,          -- telegram, youtube, blog, etc.
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_active TEXT
);

-- Партнёрские ссылки пользователя
CREATE TABLE IF NOT EXISTS affiliate_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    original_url TEXT NOT NULL,    -- полная партнёрская ссылка
    short_slug TEXT UNIQUE,        -- короткий код для внутренних ссылок
    title TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    earnings REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(id),
    FOREIGN KEY (provider_id) REFERENCES hosting_providers(id)
);

-- Сгенерированный контент
CREATE TABLE IF NOT EXISTS content_pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content_type TEXT,             -- post, article, review, comparison, ad
    title TEXT,
    body TEXT NOT NULL,
    platforms TEXT,                -- JSON array: telegram, vk, dzen
    linked_link_ids TEXT,          -- JSON array of affiliate_links.id
    status TEXT DEFAULT 'draft',   -- draft, approved, published
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(id)
);

-- Лог кликов по партнёрским ссылкам
CREATE TABLE IF NOT EXISTS click_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    clicked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ip_hash TEXT,                  -- хэш IP для аналитики без хранения
    referrer TEXT,
    user_agent TEXT,
    country TEXT,
    FOREIGN KEY (link_id) REFERENCES affiliate_links(id)
);

-- Журнал изменений условий партнёрских программ
CREATE TABLE IF NOT EXISTS program_changes_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL,
    field_changed TEXT,
    old_value TEXT,
    new_value TEXT,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (program_id) REFERENCES affiliate_programs(id)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_links_user ON affiliate_links(user_id);
CREATE INDEX IF NOT EXISTS idx_links_provider ON affiliate_links(provider_id);
CREATE INDEX IF NOT EXISTS idx_clicks_link ON click_events(link_id);
CREATE INDEX IF NOT EXISTS idx_clicks_time ON click_events(clicked_at);
CREATE INDEX IF NOT EXISTS idx_content_user ON content_pieces(user_id);
"""


class Database:
    """Асинхронная обёртка над SQLite."""

    _instance: Optional["Database"] = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    @classmethod
    async def get_instance(cls) -> "Database":
        if cls._instance is None:
            cfg = get_config()
            cls._instance = Database(cfg.database.path)
            await cls._instance.connect()
        return cls._instance

    async def connect(self):
        """Создаёт соединение и инициализирует схему."""
        # Создаём директорию для БД
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    # ---- Универсальные helpers ----

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Выполняет INSERT/UPDATE/DELETE, возвращает lastrowid."""
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor.lastrowid

    async def executemany(self, sql: str, params_list: list[tuple]):
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchall()


# -----------------------------
# Семя данных (seed data)
# -----------------------------
SEED_PROVIDERS = [
    ("Beget", "https://beget.com", "Хостинг, VPS, домены. Своя панель управления.", "https://beget.com/favicon.ico"),
    ("Timeweb", "https://timeweb.com", "Крупнейший хостинг в РФ. Shared, VDS, облачный.", None),
    ("Reg.ru", "https://www.reg.ru", "Хостинг, домены, серверы. Один из лидеров рынка.", None),
    ("SpaceWeb", "https://sweb.ru", "Хостинг с 2002 года. Тестовый период.", None),
    ("Sprinthost", "https://sprinthost.ru", "Надёжный shared-хостинг, 2-уровневая партнёрка.", None),
    ("FirstVDS", "https://firstvds.ru", "VDS/VPS-провайдер от создателей Timeweb.", None),
    ("Aéza", "https://aeza.ru", "Облачные серверы, почасовая оплата, 9+ стран.", None),
    ("Hostinger", "https://www.hostinger.com", "Международный хостинг, до 60% комиссии.", None),
]

SEED_PROGRAMS = [
    # (provider_name, program_name, commission%, recurring, min_payout, conditions_url, notes)
    ("Beget", "Стандартная", 40.0, 1, 0, "https://beget.com/ru/partnership", "40% shared, 20% VPS, 10% премиум. Нужен платный тариф."),
    ("Timeweb", "Вебмастер", 40.0, 1, 0, "https://timeweb.com/ru/partners/webmasters/", "40% за хостинг, 20% за VDS/VPS."),
    ("Reg.ru", "Реферальная", 40.0, 1, 0, "https://www.reg.ru/reseller/referral-program", "40% от каждого платежа."),
    ("SpaceWeb", "Партнёрская", 30.0, 1, 0, "https://sweb.ru/partner/", "До 30% от платежей клиентов."),
    ("Sprinthost", "Реферальная", 40.0, 1, 0, "https://sprinthost.ru/partners/common", "До 40% + 10% с рефералов 2-го уровня."),
    ("FirstVDS", "Реферальная", 10.0, 1, 0, "https://firstvds.ru/partner/referral", "10% пожизненно + скидка 25% клиенту."),
    ("Aéza", "Реферальная", 15.0, 1, 0, "https://aeza.ru/referral", "15-50% прогрессивная шкала."),
    ("Hostinger", "Affiliate", 40.0, 0, 0, "https://www.hostinger.com/affiliates", "40-60% разовая, cookie 30 дней."),
]


async def seed_database(db: Database):
    """Заполняет БД начальными данными о хостингах (только если пусто)."""
    # Проверяем, есть ли уже данные
    row = await db.fetchone("SELECT COUNT(*) as c FROM hosting_providers")
    if row and row["c"] > 0:
        return  # Данные уже есть

    now = datetime.utcnow().isoformat()

    for name, website, desc, logo in SEED_PROVIDERS:
        await db.execute(
            """INSERT OR IGNORE INTO hosting_providers
               (name, website, description, logo_url, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (name, website, desc, logo, now),
        )

    for prov_name, prog_name, comm, recur, min_p, url, notes in SEED_PROGRAMS:
        prov = await db.fetchone("SELECT id FROM hosting_providers WHERE name=?", (prov_name,))
        if prov:
            await db.execute(
                """INSERT OR IGNORE INTO affiliate_programs
                   (provider_id, program_name, commission_percent, recurring,
                    min_payout, conditions_url, notes, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (prov["id"], prog_name, comm, recur, min_p, url, notes, now),
            )

    print(f"[SEED] Загружено {len(SEED_PROVIDERS)} провайдеров и {len(SEED_PROGRAMS)} программ.")
