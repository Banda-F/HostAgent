# 🚀 Деплой HostAgent на Render через GitHub

## Подробная пошаговая инструкция

Полный путь: код на компьютере → GitHub → Render → рабочий бот.

---

## ШАГ 1. Создать репозиторий на GitHub

1. Откройте https://github.com/Banda-F
2. Нажмите кнопку **«New repository»** (зелёная, справа вверху)
3. Заполните:
   - **Repository name:** `HostAgent`
   - **Description:** `🤖 AI-агент для заработка на партнёрских программах хостингов`
   - **Visibility:** Public ✅ (обязательно — Render должен видеть код)
   - ❌ **НЕ ставьте** галочку "Add a README"
   - ❌ **НЕ выбирайте** .gitignore или license
4. Нажмите **«Create repository»**

→ Вы попадёте на страницу пустого репозитория. **НЕ закрывайте её.**

---

## ШАГ 2. Запушить код на GitHub

Откройте командную строку (`cmd`) и выполните:

```cmd
cd /d "D:\ai hosting"
git branch -M main
git remote add origin https://github.com/Banda-F/HostAgent.git
git push -u origin main
```

> ⚠️ GitHub попросит вас авторизоваться. Выберите **Browser login** (войти через браузер).
> Введите логин/пароль GitHub.

✅ После успеха на странице GitHub появятся все файлы проекта.

---

## ШАГ 3. Зарегистрироваться на Render

1. Откройте https://dashboard.render.com/register
2. Нажмите **«Sign up with GitHub»**
3. Авторизуйтесь с аккаунтом **Banda-F**
4. Render получит доступ к вашим репозиториям

---

## ШАГ 4. Создать Web Service на Render

1. В панели Render нажмите **«New»** → **«Web Service»**
2. Render покажет ваши GitHub-репозитории
3. Выберите **`Banda-F/HostAgent`**
4. Настройки деплоя (внизу формы):

   | Поле | Значение |
   |------|----------|
   | **Name** | `hostagent` |
   | **Runtime** | `Python` (должен определиться автоматически) |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `gunicorn render_app:app` |
   | **Plan** | **Free** |

5. **ОЧЕНЬ ВАЖНО** — Environment Variables (переменные окружения).
   Прокрутите вниз до **«Environment Variables»** и добавьте:

   | Key | Value |
   |-----|-------|
   | `OPENAI_API_KEY` | `sk-ВАШ_OPENAI_API_КЛЮЧ` |
   | `TELEGRAM_BOT_TOKEN` | `ВАШ_ТОКЕН_ОТ_BOTFATHER` |
   | `LLM_MODEL` | `gpt-4o-mini` |
   | `PORT` | `10000` |

   **Как добавить:**
   - Нажмите **«Add Environment Variable»**
   - Введите Key и Value
   - Нажмите плюсик или Enter
   - Повторите для каждой переменной

6. Нажмите **«Create Web Service»**

---

## ШАГ 5. Ждём деплой (3–5 минут)

Render автоматически:
1. Забирает код из GitHub
2. Создаёт виртуальное окружение Python
3. Устанавливает зависимости из `requirements.txt`
4. Запускает `gunicorn render_app:app`
5. Проверяет health-check `/health`

В логах (Live Logs) вы увидите:
```
HostAgent starting on Render...
Database initialized and seeded.
Data collection completed.
Telegram bot started as background task.
```

✅ Статус сервиса должен стать **«Live»** (зелёный).

---

## ШАГ 6. Проверяем, что всё работает

### Проверка веб-дашборда:
Откройте URL вашего сервиса (Render покажет его):
```
https://hostagent.onrender.com/
```

### Проверка health-check:
```
https://hostagent.onrender.com/health
```
Должно вернуть: `{"status": "ok", "service": "HostAgent", "version": "1.0.0"}`

### Проверка бота:
Откройте Telegram → найдите вашего бота → отправьте `/start`
Должен ответить приветствием!

---

## ⚠️ Важные особенности бесплатного тарифа Render

| Ограничение | Значение |
|------------|----------|
| **Спящий режим** | Сервис засыпает через 15 мин без запросов |
| **Пробуждение** | ~30–50 секунд при первом запросе |
| **Месячный лимит** | 750 часов работы (хватает на 24/7 с запасом) |
| **Бот спит** | Telegram-бот перестанёт отвечать, пока сервис спит |

### Как бороться со сном (на бесплатном тарифе):

**Метод 1 — UptimeRobot (бесплатно):**
1. Зарегистрируйтесь на https://uptimerobot.com
2. Создайте монитор: URL = `https://hostagent.onrender.com/health`
3. Интервал: каждые 5 минут
4. Это будет "будить" сервис каждые 5 минут

**Метод 2 — Cron-job.org (бесплатно):**
1. Перейдите на https://cron-job.org
2. Создайте HTTP-задание на `https://hostagent.onrender.com/health`
3. Интервал: каждые 5 минут

> 💡 Telegram-бот будет отвечать с задержкой ~30с после пробуждения. Это нормально для free-плана.

---

## 📝 Последующие обновления кода

Когда вы меняете код на компьютере:

```cmd
cd /d "D:\ai hosting"
git add -A
git commit -m "Описание изменений"
git push
```

Render **автоматически** подхватит изменения и передеплоит сервис (2–3 минуты).

---

## 🔧 Решение проблем

### Бот не отвечает в Telegram
1. Откройте Render → ваш сервис → **Logs**
2. Посмотрите, есть ли ошибка `Failed to start Telegram bot`
3. Проверьте что `TELEGRAM_BOT_TOKEN` добавлен в Environment Variables
4. Откройте `https://hostagent.onrender.com/health` — должен вернуть JSON

### Ошибка сборки (Build failed)
1. Посмотрите лог сборки в Render → **Build Logs**
2. Обычно проблема в `requirements.txt` — какая-то библиотека не ставится
3. Решение: обновите версию библиотеки в `requirements.txt`

### Сервис спит и не просыпается
1. Проверьте UptimeRobot — работает ли мониторинг
2. Откройте URL напрямую — это разбудит сервис
3. На free-плане задержка 30–50 секунд при пробуждении — нормально

### Health-check возвращает ошибку
1. Откройте Render → Settings → убедитесь `Health Check Path` = `/health`
2. Убедитесь что `Start Command` = `gunicorn render_app:app`

### Хочу изменить переменные окружения
1. Откройте Render → ваш сервис → **Environment**
2. Измените значения
3. Нажмите **«Save Changes»**
4. Сервис автоматически передеплоится

---

## 📊 Сводка всех действий

```
1. GitHub:    Создать репозиторий Banda-F/HostAgent (Public)
2. Локально:  git push кода на GitHub
3. Render:   Зарегистрироваться (через GitHub)
4. Render:   New → Web Service → выбрать HostAgent
5. Render:   Start Command = gunicorn render_app:app
6. Render:   Добавить env vars: OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, LLM_MODEL
7. Render:   Create Web Service → ждать деплой
8. Проверить: /health → бот в Telegram → дашборд
9. UptimeRobot: мониторинг /health каждые 5 минут
10. Готово! 🎉
```
