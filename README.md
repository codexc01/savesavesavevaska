# Telegram Business Deleted Messages Saver Bot

Производственная система сохранения удалённых и изменённых сообщений для бизнес-аккаунтов Telegram (Telegram Business API).

## 📌 Руководство по подключению бота

### Шаг 1. Подключение в Telegram
1. Откройте **Telegram** на телефоне или компьютере.
2. Перейдите по ссылке `tg://settings/edit` или откройте **Настройки -> Telegram для бизнеса (Автоматизация)**.
3. Выберите пункт **Чаты с клиентами / Автоматизация (Бот)**.
4. Введите имя бота: `@deletedavedo_savebot`.
5. Предоставьте права на чтение сообщений и нажмите **Сохранить**.
   *(Если не работает — отключите и подключите снова)*.

После этого бот начнет автоматически сохранять все измененные и удаленные сообщения в ваших бизнес-чатах.

---

## 🛠 Архитектура и технологии

- **Язык**: Python 3.9+
- **Фреймворк**: aiogram 3.22.0
- **База данных**: PostgreSQL (SQLAlchemy 2.x asyncpg + Alembic migrations)
- **Кэш & Идемпотентность**: Redis (aioredis)
- **Логирование**: structlog (JSON / Console output)
- **Контейнеризация**: Docker + Docker Compose

---

## 🚀 Быстрый запуск (Docker Compose)

1. Клонируйте репозиторий и создайте конфигурационный файл `.env`:
   ```bash
   cp .env.example .env
   ```

2. Заполните переменные окружения в `.env`:
   - `BOT_TOKEN`: токен вашего бота от `@BotFather`
   - `ADMIN_ID`: ваш Telegram User ID (`2106121176`)

3. Запустите комплекс в Docker:
   ```bash
   docker compose up -d --build
   ```

4. Просмотрите логи работы:
   ```bash
   docker compose logs -f bot
   ```

---

## 🧪 Запуск локальных проверок (Тесты & Линтинг)

Для проверки исходного кода и запуска 80 unit- и интеграционных тестов:

```bash
# Установка виртуального окружения
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Запуск линтера ruff и тестов pytest
PYTHONPATH=. .venv/bin/ruff check app/ tests/
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

---

## 🔒 Безопасность и Конфиденциальность

- Все админ-команды (`/admin`, `/connections`, `/stats`, `/probe_report`) строго защищены фильтром `ADMIN_ID`.
- Сторонние пользователи не видят админ-панель в меню и получают тихий игнор (silent deny) при попытке вызова команд.
