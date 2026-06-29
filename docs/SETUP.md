# HostAgent — Руководство по установке и запуску

## Требования

- **Python 3.11+** (рекомендуется 3.12)
- **pip** (входит в состав Python)
- **Telegram Bot Token** (получить у [@BotFather](https://t.me/BotFather))
- **OpenAI API ключ** или локальный LLM (Ollama)

## Установка (5 минут)

### 1. Клонируйте и перейдите в папку

```bash
cd "D:\ai hosting"
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте конфигурацию

```bash
copy config\config.example.yaml config\config.yaml
```

Отредактируйте `config/config.yaml`:
```yaml
llm:
  provider: openai
  openai:
    api_key: "sk-ВАШ-КЛЮЧ"         # ← Обязательно
    model: "gpt-4o-mini"            # или gpt-4o для лучшего качества

telegram:
  bot_token: "ВАШ-ТОКЕН-БОТА"       # ← Обязательно (от @BotFather)
```

### 5. Запустите

```bash
# Собрать данные о хостингах (один раз)
python main.py collect

# Запустить Telegram-бот
python main.py bot

# Запустить веб-дашборд
python main.py web

# Или всё вместе
python main.py all
```

## Использование OpenAI-совместимых API

HostAgent работает с любым OpenAI-совместимым API. Вот популярные варианты:

### OpenAI (по умолчанию)
```yaml
llm:
  provider: openai
  openai:
    api_key: "sk-..."
    model: "gpt-4o-mini"
    base_url: "https://api.openai.com/v1"
```

### OpenRouter (доступ к множеству моделей)
```yaml
llm:
  provider: openai
  openai:
    api_key: "sk-or-..."
    model: "openai/gpt-4o-mini"
    base_url: "https://openrouter.ai/api/v1"
```

### Локальный Ollama (бесплатно!)
```yaml
llm:
  provider: ollama
  ollama:
    model: "llama3.1"
```

### Яндекс GPT (через прокси)
```yaml
llm:
  provider: openai
  openai:
    api_key: "your-key"
    model: "yandexgpt-lite"
    base_url: "https://your-proxy-url/v1"
```

## Как использовать Telegram-бота

После запуска (`python main.py bot`) найдите бота в Telegram и отправьте `/start`.

### Основные команды:

| Команда | Описание |
|---------|----------|
| `/start` | Запустить бота и пройти онбординг |
| `/help` | Список всех возможностей |
| `/top` | Топ-5 хостингов по размеру комиссии |
| `/analyze Запрос` | Сравнить хостинги (например: `/analyze Beget и Timeweb`) |
| `/content Запрос` | Сгенерировать контент (например: `/content пост про Beget`) |
| `/addlink URL` | Добавить партнёрскую ссылку |
| `/links` | Показать все ваши ссылки |
| `/stats` | Ваша статистика |
| `/forecast Запрос` | Прогноз дохода |

### Примеры диалогов:

**Анализ:**
```
Вы: Сравни Beget и Timeweb для WordPress-блога
Бот: [Подробное сравнение с таблицей и рекомендацией]
```

**Контент:**
```
Вы: Напиши пост про Sprinthost для Telegram канала про веб-разработку
Бот: [Готовый пост с партнёрской ссылкой, который можно сразу скопировать]
```

**Прогноз:**
```
Вы: Сколько я заработаю, если у меня 3000 подписчиков в Telegram
Бот: [Расчёт дохода по трём сценариям: пессимистичный, реалистичный, оптимистичный]
```

## Веб-дашборд

После запуска (`python main.py web`) откройте:
```
http://127.0.0.1:8080
```

Дашборд показывает:
- Общую статистику (клики, конверсии, заработок)
- Таблицу сравнения партнёрских программ
- Ваши партнёрские ссылки и их эффективность
- Сгенерированный контент

## Автоматический сбор данных

Сборщик парсит страницы партнёрских программ каждые 24 часа.
Чтобы включить автосборку, добавьте в свой планировщик (cron/Task Scheduler):

**Windows (Task Scheduler):**
```cmd
cd /d "D:\ai hosting" && venv\Scripts\python.exe main.py collect
```

**Linux (cron):**
```cron
0 */6 * * * cd /path/to/hostagent && venv/bin/python main.py collect
```

## Структура проекта

```
D:\ai hosting\
├── main.py                     # Точка входа (CLI)
├── requirements.txt            # Зависимости Python
├── config/
│   ├── config.py               # Загрузчик конфигурации
│   └── config.example.yaml     # Шаблон конфигурации
├── hostagent/                  # Основной пакет проекта
│   ├── core/
│   │   ├── llm_client.py       # Клиент для LLM (OpenAI/Ollama)
│   │   ├── orchestrator.py     # Маршрутизатор запросов
│   │   └── types.py            # Общие типы (Intent, AgentResponse)
│   ├── agents/
│   │   ├── analyst/agent.py    # Агент-аналитик
│   │   ├── content_creator/agent.py  # Генератор контента
│   │   └── link_manager/agent.py     # Менеджер ссылок
│   ├── data/
│   │   ├── database/
│   │   │   ├── models.py       # SQLite схема + seed
│   │   │   └── repository.py   # Слой доступа к данным
│   │   └── parsers/
│   │       ├── base.py         # Базовый парсер
│   │       ├── providers.py    # Парсеры 8 хостингов
│   │       ├── reviews.py      # Парсер отзывов
│   │       └── collector.py    # Оркестратор сбора
│   ├── services/
│   │   ├── telegram_bot/bot.py # Telegram-бот
│   │   └── web_dashboard/
│   │       ├── app.py          # FastAPI приложение
│   │       └── templates/dashboard.html
│   └── utils/
├── render_app.py               # Точка входа для Render (веб + бот)
├── render.yaml                 # Конфигурация Render
├── Procfile                    # Procfile для Render/Heroku
├── runtime.txt                 # Версия Python
└── prompts/
    ├── system.txt              # Системный промпт
    ├── analyst.txt             # Промпт аналитика
    ├── content_creator.txt     # Промпт генератора контента
    └── link_optimizer.txt      # Промпт менеджера ссылок
```

## Решение проблем

### Ошибка: "Config file not found"
Убедитесь, что `config/config.yaml` существует. Скопируйте из `config.example.yaml`.

### Ошибка: "OpenAI API key not set"
Заполните `api_key` в `config/config.yaml` или используйте локальный Ollama.

### Ошибка: "Telegram bot token not set"
Получите токен у [@BotFather](https://t.me/BotFather) и укажите в конфиге.

### Бот отвечает ошибкой "request timed out"
Проверьте подключение к интернету и API-ключ. Увеличьте таймаут в конфиге.

### Хочу использовать бесплатно (без OpenAI)
Установите [Ollama](https://ollama.com), скачайте модель (`ollama pull llama3.1`)
и измените `config.yaml`:
```yaml
llm:
  provider: ollama
  ollama:
    model: "llama3.1"
```
