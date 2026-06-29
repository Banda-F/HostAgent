"""
HostAgent — Настройки конфигурации
Загружает config.yaml и предоставляет доступ ко всем настройкам.
"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class LLMConfig:
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class TelegramConfig:
    bot_token: str = ""
    webhook_url: str = ""
    webhook_port: int = 8443
    admin_ids: list[int] = field(default_factory=list)


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    secret_key: str = "change-this-secret"
    username: str = "admin"
    password: str = "changeme123"


@dataclass
class DatabaseConfig:
    path: str = "data/hostagent.db"


@dataclass
class ScraperConfig:
    update_interval_hours: int = 24
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    request_delay: float = 2.0
    request_timeout: int = 30


@dataclass
class LinkShortenerConfig:
    method: str = "internal"
    bitly_access_token: str = ""


@dataclass
class NotificationsConfig:
    notify_program_changes: bool = True
    weekly_report: bool = True
    report_hour_utc: int = 9


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/hostagent.log"
    max_size_mb: int = 10
    backup_count: int = 5


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    web: WebConfig = field(default_factory=WebConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    link_shortener: LinkShortenerConfig = field(default_factory=LinkShortenerConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """Рекурсивное слияние словарей."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_llm_config(data: dict) -> LLMConfig:
    provider = data.get("provider", "openai")
    provider_data = data.get(provider, {})
    return LLMConfig(
        provider=provider,
        api_key=provider_data.get("api_key", ""),
        model=provider_data.get("model", "gpt-4o-mini"),
        base_url=provider_data.get("base_url", "https://api.openai.com/v1"),
        temperature=provider_data.get("temperature", 0.7),
        max_tokens=provider_data.get("max_tokens", 4096),
    )


def _build_web_config(data: dict) -> WebConfig:
    """Собирает WebConfig, поддерживая как плоский формат, так и
    вложенную секцию auth (для совместимости с config.example.yaml)."""
    # Делаем копию, чтобы не мутировать исходный словарь
    data = dict(data)

    # Если auth вложен — извлекаем username/password оттуда
    auth = data.pop("auth", None)
    if isinstance(auth, dict):
        data.setdefault("username", auth.get("username", "admin"))
        data.setdefault("password", auth.get("password", "changeme123"))

    # Убираем неизвестные ключи, чтобы dataclass не упал
    valid_fields = {f for f in WebConfig.__dataclass_fields__}
    clean = {k: v for k, v in data.items() if k in valid_fields}
    return WebConfig(**clean)


def _build_link_shortener_config(data: dict) -> LinkShortenerConfig:
    """Собирает LinkShortenerConfig, поддерживая вложенную секцию bitly."""
    data = dict(data)

    bitly = data.pop("bitly", None)
    if isinstance(bitly, dict):
        data.setdefault("bitly_access_token", bitly.get("access_token", ""))

    valid_fields = {f for f in LinkShortenerConfig.__dataclass_fields__}
    clean = {k: v for k, v in data.items() if k in valid_fields}
    return LinkShortenerConfig(**clean)


def _apply_env_overrides(cfg: AppConfig) -> AppConfig:
    """Перекрывает значения из YAML переменными окружения.
    Это нужно для облачных платформ (Render, Heroku), где секреты
    передаются через env vars, а не через файлы."""
    # LLM
    if os.environ.get("OPENAI_API_KEY"):
        cfg.llm.api_key = os.environ["OPENAI_API_KEY"]
    if os.environ.get("OPENROUTER_API_KEY"):
        # Поддержка ключа OpenRouter (приоритет над OPENAI_API_KEY)
        cfg.llm.api_key = os.environ["OPENROUTER_API_KEY"]
        cfg.llm.base_url = "https://openrouter.ai/api/v1"
    # Модель: поддерживаем оба имени переменной
    model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    if model:
        cfg.llm.model = model
    if os.environ.get("OPENAI_BASE_URL"):
        cfg.llm.base_url = os.environ["OPENAI_BASE_URL"]
    if os.environ.get("LLM_PROVIDER"):
        cfg.llm.provider = os.environ["LLM_PROVIDER"]

    # Telegram
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg.telegram.bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

    # Web — Render передаёт PORT
    if os.environ.get("PORT"):
        cfg.web.port = int(os.environ["PORT"])
    if os.environ.get("WEB_HOST"):
        cfg.web.host = os.environ["WEB_HOST"]

    # Database — на облаке используем путь из env или /tmp
    if os.environ.get("DATABASE_PATH"):
        cfg.database.path = os.environ["DATABASE_PATH"]

    return cfg


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Загружает конфигурацию из YAML-файла, затем перекрывает env vars."""
    if config_path is None:
        config_path = os.environ.get(
            "HOSTAGENT_CONFIG",
            str(Path(__file__).parent / "config.yaml"),
        )

    path = Path(config_path)
    if not path.exists():
        # Файл не найден — используем дефолтную конфигурацию + env vars
        print(f"[WARN] Config file not found: {path}. Using defaults + env vars.")
        return _apply_env_overrides(AppConfig())

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    cfg = AppConfig(
        llm=_build_llm_config(data.get("llm", {})),
        telegram=TelegramConfig(**data.get("telegram", {})),
        web=_build_web_config(data.get("web", {})),
        database=DatabaseConfig(**data.get("database", {})),
        scraper=ScraperConfig(**data.get("scraper", {})),
        link_shortener=_build_link_shortener_config(data.get("link_shortener", {})),
        notifications=NotificationsConfig(**data.get("notifications", {})),
        logging=LoggingConfig(**data.get("logging", {})),
    )
    return _apply_env_overrides(cfg)


# Глобальный экземпляр конфигурации (lazy-loaded)
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Возвращает глобальную конфигурацию (singleton)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
