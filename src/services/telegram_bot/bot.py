"""
HostAgent — Telegram-бот
Основной интерфейс взаимодействия с пользователем.
Полнофункциональный бот с командами, кнопками и AI-диалогом.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config.config import get_config
from src.core.llm_client import LLMClient
from src.core.orchestrator import Orchestrator
from src.data.database.models import Database, seed_database
from src.data.database.repository import Repository

logger = logging.getLogger(__name__)


class HostAgentBot:
    """Telegram-бот HostAgent."""

    # Эмодзи для интерфейса
    E_SPARKLE = "🤖"
    E_CHART = "📊"
    E_PEN = "✍️"
    E_LINK = "🔗"
    E_MONEY = "💰"
    E_HELP = "❓"

    def __init__(self, db: Database, orchestrator: Orchestrator):
        self.db = db
        self.orchestrator = orchestrator
        self.repo = Repository(db)
        self.app: Optional[Application] = None

    # ===== Команды =====

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start — приветствие и онбординг."""
        user = update.effective_user
        await self.repo.get_or_create_user(
            user.id, user.username, user.first_name
        )

        text = (
            f"{self.E_SPARKLE} *Привет, {user.first_name}!*\n\n"
            "Я *HostAgent* — твой AI-помощник для заработка на партнёрках "
            "российских хостингов.\n\n"
            "Я умею:\n"
            f"{self.E_CHART} Анализировать и сравнивать хостинги\n"
            f"{self.E_PEN} Создавать продающий контент с твоими ссылками\n"
            f"{self.E_LINK} Управлять партнёрскими ссылками\n"
            f"{self.E_MONEY} Считать потенциальный доход\n\n"
            "*С чего начать?*\n"
            "Просто напиши свой вопрос или выбери кнопку ниже 👇"
        )

        keyboard = self._main_keyboard()
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help — справка."""
        response = await self.orchestrator.handle(
            user_id=update.effective_user.id,
            text="помощь",
            username=update.effective_user.username or "",
        )
        await update.message.reply_text(
            response.text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=self._main_keyboard(),
        )

    async def cmd_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /analyze — быстрый запуск анализа."""
        if not context.args:
            await update.message.reply_text(
                f"{self.E_CHART} *Анализ хостингов*\n\n"
                "Напиши, что сравнить. Например:\n"
                "`/analyze Beget и Timeweb`\n"
                "`/analyze лучший хостинг для WordPress`\n"
                "`/analyze хостинг с максимальной комиссией`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        query = " ".join(context.args)
        await self._process_with_typing(update, query)

    async def cmd_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /content — генерация контента."""
        if not context.args:
            await update.message.reply_text(
                f"{self.E_PEN} *Генерация контента*\n\n"
                "Примеры:\n"
                "`/content пост про Beget для Telegram`\n"
                "`/content обзор Timeweb`\n"
                "`/content сравнение Beget и Reg.ru`\n"
                "`/content статья про выбор хостинга для новичков`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        query = "напиши " + " ".join(context.args)
        await self._process_with_typing(update, query)

    async def cmd_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /links — показать мои ссылки."""
        response = await self.orchestrator.handle(
            user_id=update.effective_user.id,
            text="покажи мои ссылки",
            username=update.effective_user.username or "",
        )
        await update.message.reply_text(
            response.text, parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_addlink(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /addlink — добавить ссылку."""
        if not context.args:
            await update.message.reply_text(
                f"{self.E_LINK} *Добавление ссылки*\n\n"
                "Формат:\n"
                "`/addlink https://beget.com/?ref=твойкод`\n"
                "`/addlink https://timeweb.com/?ref=abc utm_source=telegram`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        query = "добавь ссылку " + " ".join(context.args)
        await self._process_with_typing(update, query)

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats — статистика пользователя."""
        user_id = await self.repo.get_or_create_user(
            update.effective_user.id,
            update.effective_user.username or "",
            update.effective_user.first_name,
        )
        stats = await self.repo.get_dashboard_stats(user_id)

        text = (
            f"{self.E_CHART} *Твоя статистика*\n\n"
            f"🔗 Ссылок: *{stats['links_count']}*\n"
            f"👆 Кликов: *{stats['total_clicks']}*\n"
            f"✅ Конверсий: *{stats['total_conversions']}*\n"
            f"💰 Заработано: *{stats['total_earnings']}₽*\n"
            f"📝 Контента создано: *{stats['content_count']}*"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_forecast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /forecast — прогноз дохода."""
        if not context.args:
            await update.message.reply_text(
                f"{self.E_MONEY} *Прогноз дохода*\n\n"
                "Примеры:\n"
                "`/forecast у меня 1000 подписчиков в Telegram`\n"
                "`/forecast блог 5000 посетителей в месяц`\n"
                "`/forecast веб-студия 10 клиентов в месяц`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        query = "сколько я заработаю, если " + " ".join(context.args)
        await self._process_with_typing(update, query)

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /top — топ хостингов по комиссии."""
        providers = await self.repo.get_top_providers_by_commission(limit=5)
        lines = [f"{self.E_CHART} *Топ-5 хостингов по комиссии*\n"]
        for i, p in enumerate(providers, 1):
            recur = "🔄 повторные" if p.recurring else "1️⃣ разовая"
            lines.append(
                f"*{i}. {p.name}* — {p.commission_percent}% ({recur})\n"
                f"   {p.notes}\n"
            )
        lines.append("\nНапиши боту, чтобы узнать подробнее о любом из них.")
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        )

    # ===== Обработка текстовых сообщений =====

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает произвольное сообщение через AI-оркестратор."""
        await self._process_with_typing(update, update.message.text)

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий inline-кнопок."""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "btn_analyze":
            await query.edit_message_text(
                f"{self.E_CHART} Напиши, что нужно сравнить или подобрать.\n"
                "Например: *«Сравни Beget и Timeweb»* или "
                "*«Какой хостинг лучше для интернет-магазина?»*",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif data == "btn_content":
            await query.edit_message_text(
                f"{self.E_PEN} Что создать? Например:\n"
                "• *«Напиши пост про Beget для Telegram»*\n"
                "• *«Создай обзор Timeweb»*",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif data == "btn_links":
            response = await self.orchestrator.handle(
                user_id=update.effective_user.id,
                text="покажи мои ссылки",
            )
            await query.edit_message_text(
                response.text, parse_mode=ParseMode.MARKDOWN,
            )
        elif data == "btn_forecast":
            await query.edit_message_text(
                f"{self.E_MONEY} Опиши свою аудиторию:\n"
                "• *«У меня 2000 подписчиков в Telegram»*\n"
                "• *«Блог с 5000 посещений в месяц»*",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif data == "btn_top":
            providers = await self.repo.get_top_providers_by_commission(limit=5)
            lines = [f"{self.E_CHART} *Топ-5 по комиссии*\n"]
            for i, p in enumerate(providers, 1):
                recur = "🔄" if p.recurring else "1️⃣"
                lines.append(f"*{i}. {p.name}* — {p.commission_percent}% {recur}")
            await query.edit_message_text(
                "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
            )

    async def _process_with_typing(self, update: Update, text: str):
        """Обрабатывает запрос с индикатором «печатает»."""
        chat_id = update.effective_chat.id

        # Показываем статус «печатает»
        typing_task = asyncio.create_task(self._typing_loop(chat_id, update))

        try:
            response = await self.orchestrator.handle(
                user_id=update.effective_user.id,
                text=text,
                username=update.effective_user.username or "",
            )
            # Отправляем ответ (с разбивкой длинных сообщений)
            await self._send_long_message(update, response.text)
        finally:
            typing_task.cancel()

    async def _typing_loop(self, chat_id: int, update: Update):
        """Периодически отправляет статус «печатает»."""
        try:
            while True:
                # Используем контекст-бот, если доступен
                bot = update.get_bot() if hasattr(update, "get_bot") else None
                if bot:
                    await bot.send_chat_action(
                        chat_id=chat_id, action="typing"
                    )
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _send_long_message(self, update: Update, text: str):
        """Отправляет длинное сообщение, разбивая на части (лимит TG ~4096)."""
        MAX_LEN = 4000
        if len(text) <= MAX_LEN:
            await update.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=self._main_keyboard(),
            )
            return

        # Разбиваем по абзацам, стараясь не разорвать предложение
        parts = []
        current = ""
        for paragraph in text.split("\n\n"):
            if len(current) + len(paragraph) + 2 > MAX_LEN:
                if current:
                    parts.append(current)
                current = paragraph
            else:
                current = current + "\n\n" + paragraph if current else paragraph
        if current:
            parts.append(current)

        for i, part in enumerate(parts):
            keyboard = self._main_keyboard() if i == len(parts) - 1 else None
            try:
                await update.message.reply_text(
                    part, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard,
                )
            except Exception:
                # Если Markdown некорректен — отправляем как простой текст
                await update.message.reply_text(
                    part, reply_markup=keyboard,
                )

    def _main_keyboard(self) -> ReplyKeyboardMarkup:
        """Главная клавиатура бота."""
        keyboard = [
            [f"{self.E_CHART} Анализ хостингов", f"{self.E_PEN} Создать контент"],
            [f"{self.E_LINK} Мои ссылки", f"{self.E_MONEY} Прогноз дохода"],
            [f"{self.E_HELP} Помощь"],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # ===== Запуск =====

    def setup(self):
        """Регистрирует все обработчики."""
        self.app = Application.builder().token(
            get_config().telegram.bot_token
        ).build()

        # Команды
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("analyze", self.cmd_analyze))
        self.app.add_handler(CommandHandler("content", self.cmd_content))
        self.app.add_handler(CommandHandler("links", self.cmd_links))
        self.app.add_handler(CommandHandler("addlink", self.cmd_addlink))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("forecast", self.cmd_forecast))
        self.app.add_handler(CommandHandler("top", self.cmd_top))

        # Кнопки
        self.app.add_handler(CallbackQueryHandler(self.handle_button))

        # Текстовые сообщения
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

    async def _set_bot_commands(self):
        """Устанавливает список команд в меню бота."""
        await asyncio.sleep(2)
        if not self.app:
            return
        from telegram import BotCommand
        commands = [
            BotCommand("start", "Запустить бота"),
            BotCommand("help", "Помощь и команды"),
            BotCommand("analyze", "Анализ хостингов"),
            BotCommand("content", "Создать контент"),
            BotCommand("addlink", "Добавить партнёрскую ссылку"),
            BotCommand("links", "Мои ссылки"),
            BotCommand("stats", "Моя статистика"),
            BotCommand("forecast", "Прогноз дохода"),
            BotCommand("top", "Топ хостингов по комиссии"),
        ]
        try:
            await self.app.bot.set_my_commands(commands)
        except Exception as e:
            logger.warning(f"Could not set bot commands: {e}")

    async def run(self):
        """Запускает бота (polling)."""
        self.setup()
        logger.info("Starting Telegram bot (polling)...")
        await self.app.initialize()
        await self.app.start()
        asyncio.ensure_future(self._set_bot_commands())
        await self.app.updater.start_polling()
        # Держим процесс активным
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()


async def main():
    """Точка входа для запуска Telegram-бота."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = get_config()
    if not cfg.telegram.bot_token or "your-" in cfg.telegram.bot_token:
        print("[ERROR] Telegram bot token не настроен!")
        print("Заполните config/config.yaml → telegram.bot_token")
        return

    # Подключаем БД
    db = Database(cfg.database.path)
    await db.connect()
    await seed_database(db)

    # Создаём оркестратор
    llm = LLMClient()
    orchestrator = Orchestrator(db, llm)

    # Запускаем бота
    bot = HostAgentBot(db, orchestrator)
    await bot.run()

    await llm.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
