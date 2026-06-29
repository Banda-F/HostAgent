"""
HostAgent — Репозиторий: удобный доступ к данным БД
Высокоуровневые методы для работы с хостингами, программами, ссылками, контентом.
"""
from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from hostagent.data.database.models import Database


@dataclass
class HostingInfo:
    """Краткая информация о хостинге и его партнёрской программе."""
    id: int
    name: str
    website: str
    description: str
    commission_percent: float
    recurring: bool
    min_payout: float
    conditions_url: str
    notes: str


class Repository:
    """Слой доступа к данным."""

    def __init__(self, db: Database):
        self.db = db

    # ---- Хостинги и партнёрские программы ----

    async def get_all_providers(self) -> list[HostingInfo]:
        rows = await self.db.fetchall(
            """
            SELECT p.id, p.name, p.website, p.description,
                   ap.commission_percent, ap.recurring, ap.min_payout,
                   ap.conditions_url, ap.notes
            FROM hosting_providers p
            LEFT JOIN affiliate_programs ap ON ap.provider_id = p.id
            WHERE p.is_active = 1 AND ap.is_active = 1
            ORDER BY ap.commission_percent DESC
            """
        )
        return [
            HostingInfo(
                id=r["id"], name=r["name"], website=r["website"],
                description=r["description"] or "",
                commission_percent=r["commission_percent"] or 0,
                recurring=bool(r["recurring"]),
                min_payout=r["min_payout"] or 0,
                conditions_url=r["conditions_url"] or "",
                notes=r["notes"] or "",
            )
            for r in rows
        ]

    async def get_provider(self, provider_id: int) -> Optional[HostingInfo]:
        r = await self.db.fetchone(
            """
            SELECT p.id, p.name, p.website, p.description,
                   ap.commission_percent, ap.recurring, ap.min_payout,
                   ap.conditions_url, ap.notes
            FROM hosting_providers p
            LEFT JOIN affiliate_programs ap ON ap.provider_id = p.id
            WHERE p.id = ?
            """, (provider_id,)
        )
        if not r:
            return None
        return HostingInfo(
            id=r["id"], name=r["name"], website=r["website"],
            description=r["description"] or "",
            commission_percent=r["commission_percent"] or 0,
            recurring=bool(r["recurring"]),
            min_payout=r["min_payout"] or 0,
            conditions_url=r["conditions_url"] or "",
            notes=r["notes"] or "",
        )

    async def get_top_providers_by_commission(self, limit: int = 5) -> list[HostingInfo]:
        """Топ хостингов по размеру комиссии."""
        all_providers = await self.get_all_providers()
        return sorted(all_providers, key=lambda x: x.commission_percent, reverse=True)[:limit]

    # ---- Пользователи ----

    async def get_or_create_user(self, telegram_id: int, username: str = "",
                                 display_name: str = "") -> int:
        row = await self.db.fetchone(
            "SELECT id FROM user_profiles WHERE telegram_id=?", (telegram_id,)
        )
        if row:
            await self.db.execute(
                "UPDATE user_profiles SET last_active=?, username=? WHERE id=?",
                (datetime.utcnow().isoformat(), username, row["id"]),
            )
            return row["id"]
        user_id = await self.db.execute(
            """INSERT INTO user_profiles (telegram_id, username, display_name, last_active)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, display_name, datetime.utcnow().isoformat()),
        )
        return user_id

    async def update_user_profile(self, user_id: int, niche: str = None,
                                  audience_size: int = None,
                                  primary_channel: str = None):
        fields, params = [], []
        for col, val in [("niche", niche), ("audience_size", audience_size),
                         ("primary_channel", primary_channel)]:
            if val is not None:
                fields.append(f"{col}=?")
                params.append(val)
        if fields:
            params.append(user_id)
            await self.db.execute(
                f"UPDATE user_profiles SET {', '.join(fields)} WHERE id=?",
                tuple(params),
            )

    # ---- Партнёрские ссылки ----

    async def add_affiliate_link(self, user_id: int, provider_id: int,
                                  original_url: str, title: str = "",
                                  utm_source: str = "", utm_medium: str = "",
                                  utm_campaign: str = "") -> str:
        """Создаёт партнёрскую ссылку, возвращает короткий slug."""
        slug = self._generate_slug()
        await self.db.execute(
            """INSERT INTO affiliate_links
               (user_id, provider_id, original_url, short_slug, title,
                utm_source, utm_medium, utm_campaign)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, provider_id, original_url, slug, title,
             utm_source, utm_medium, utm_campaign),
        )
        return slug

    def _generate_slug(self, length: int = 7) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    async def get_link_by_slug(self, slug: str) -> Optional[dict]:
        r = await self.db.fetchone(
            """SELECT l.*, p.name as provider_name
               FROM affiliate_links l
               JOIN hosting_providers p ON p.id = l.provider_id
               WHERE l.short_slug=? AND l.is_active=1""",
            (slug,)
        )
        return dict(r) if r else None

    async def get_user_links(self, user_id: int) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT l.*, p.name as provider_name
               FROM affiliate_links l
               JOIN hosting_providers p ON p.id = l.provider_id
               WHERE l.user_id=? AND l.is_active=1
               ORDER BY l.created_at DESC""",
            (user_id,)
        )
        return [dict(r) for r in rows]

    async def record_click(self, link_id: int, referrer: str = "",
                           user_agent: str = "", ip_hash: str = ""):
        await self.db.execute(
            "UPDATE affiliate_links SET clicks = clicks + 1 WHERE id=?",
            (link_id,)
        )
        await self.db.execute(
            """INSERT INTO click_events (link_id, referrer, user_agent, ip_hash)
               VALUES (?, ?, ?, ?)""",
            (link_id, referrer, user_agent, ip_hash),
        )

    async def get_click_stats(self, link_id: int, days: int = 30) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        row = await self.db.fetchone(
            """SELECT COUNT(*) as total,
                      DATE(clicked_at) as day,
                      COUNT(*) as clicks
               FROM click_events
               WHERE link_id=? AND clicked_at >= ?
               GROUP BY DATE(clicked_at)""",
            (link_id, since)
        )
        total_row = await self.db.fetchone(
            """SELECT SUM(clicks) as clicks, SUM(conversions) as conv, SUM(earnings) as earn
               FROM affiliate_links WHERE id=?""",
            (link_id,)
        )
        return {
            "total_clicks": total_row["clicks"] if total_row and total_row["clicks"] else 0,
            "total_conversions": total_row["conv"] if total_row and total_row["conv"] else 0,
            "total_earnings": total_row["earn"] if total_row and total_row["earn"] else 0,
        }

    # ---- Контент ----

    async def save_content(self, user_id: int, content_type: str, title: str,
                           body: str, platforms: list[str],
                           linked_link_ids: list[int]) -> int:
        return await self.db.execute(
            """INSERT INTO content_pieces
               (user_id, content_type, title, body, platforms, linked_link_ids, status)
               VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
            (user_id, content_type, title, body,
             json.dumps(platforms), json.dumps(linked_link_ids)),
        )

    async def get_user_content(self, user_id: int, limit: int = 20) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT * FROM content_pieces WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit)
        )
        return [dict(r) for r in rows]

    # ---- Аналитика для дашборда ----

    async def get_dashboard_stats(self, user_id: int) -> dict:
        links = await self.db.fetchone(
            """SELECT COUNT(*) as count,
                      COALESCE(SUM(clicks),0) as clicks,
                      COALESCE(SUM(conversions),0) as conversions,
                      COALESCE(SUM(earnings),0) as earnings
               FROM affiliate_links WHERE user_id=?""",
            (user_id,)
        )
        content = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM content_pieces WHERE user_id=?",
            (user_id,)
        )
        return {
            "links_count": links["count"] if links else 0,
            "total_clicks": links["clicks"] if links else 0,
            "total_conversions": links["conversions"] if links else 0,
            "total_earnings": links["earnings"] if links else 0,
            "content_count": content["count"] if content else 0,
        }
