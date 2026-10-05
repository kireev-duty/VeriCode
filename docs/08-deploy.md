# 8. Сборка, развёртывание и локальный запуск

## Вариант 1. Docker Compose (рекомендуется)

Требования: Docker 24+ с Compose v2, 3 ГБ свободной памяти, свободный порт 8080. ОС любая: Linux, macOS или Windows
с Docker Desktop.

```bash
git clone <repo> fsp-talent
cd fsp-talent
docker compose up -d --build
```

При первом запуске:
1. PostgreSQL создаёт базу.
2. Backend применяет миграции Alembic (`alembic upgrade head`).
3. Backend загружает демо-данные (`SEED_DEMO=true`). Это идемпотентно: повторный запуск ничего не дублирует.
4. Keycloak импортирует realm `fsp` из `deploy/keycloak/realm-fsp.json`.

Готовность проверяется так:

```bash
docker compose ps
curl http://localhost:8080/api/health   # {"ok": true, ...}
```

Адреса: приложение — http://localhost:8080, Swagger — `/api/docs`, ФСП ID — `/auth`, почта — `/mail`.

### Полезные команды

```bash
docker compose logs -f backend                    # логи API
docker compose down                               # остановить
docker compose down -v                            # остановить и удалить данные (демо пересоздастся)
docker compose exec backend python -m app.seed.run --reset   # пересоздать демо-данные
```

### Переменные окружения

Задаются в `.env` рядом с `docker-compose.yml`.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `PUBLIC_URL` | `http://localhost:8080` | Публичный адрес: ссылки в письмах, QR, OIDC redirect, Keycloak hostname |
| `HTTP_PORT` | `8080` | Внешний порт nginx |
| `JWT_SECRET` | dev-значение | Секрет подписи токенов — **сменить в проде** |
| `POSTGRES_PASSWORD` | `fsp` | Пароль БД |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Пароль админки Keycloak |
| `SEED_DEMO` | `true` | Загрузить демо-данные при старте |
| `EXPOSE_EMAIL_LINKS` | `true` | Возвращать ссылку подтверждения в ответе API (только для демо) |
| `FSP_OIDC_ENABLED` | `true` | `false` — встроенная заглушка ФСП ID вместо Keycloak |
| `LLM_PROVIDER` | `none` | Зарезервировано для перефразирования условий |

## Вариант 2. Развёртывание на сервере с HTTPS

1. VPS с 2 vCPU и 4 ГБ RAM, Docker, домен с A-записью на сервер.
2. В `.env` задайте: `PUBLIC_URL=https://talent.example.ru`, `HTTP_PORT=8080`, `JWT_SECRET=<случайные 64 символа>`,
   `EXPOSE_EMAIL_LINKS=false` (если настроен настоящий SMTP) или `true` (для демо-стенда).
3. Поставьте перед стеком Caddy для автоматического TLS (`deploy/Caddyfile`):

   ```
   talent.example.ru {
     reverse_proxy localhost:8080
   }
   ```

   ```bash
   docker compose up -d --build
   caddy run --config deploy/Caddyfile   # или caddy как systemd-сервис
   ```

4. Nginx внутри стека передаёт `X-Forwarded-Proto`, Keycloak работает за прокси (`KC_PROXY_HEADERS=xforwarded`).
   Ссылки авторизации ФСП ID строятся от `PUBLIC_URL`.

## Вариант 3. Локальная разработка без Docker

Backend (нужен [uv](https://docs.astral.sh/uv/)). По умолчанию используется SQLite, ФСП ID работает в режиме
заглушки, мок реестра вызывается в процессе:

```bash
cd backend
uv sync
uv run python -m app.seed.run --reset          # демо-данные в dev.db
SMTP_HOST= uv run uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm ci
npm run dev                                     # http://localhost:5173, /api проксируется на :8000
```

## Проверки

```bash
cd backend
uv run pytest -q                       # e2e-сценарий API: регистрация → тест → подборка → приглашение → контакты
uv run ruff check app validation       # линтер
uv run python -m validation.run        # валидация: docs/validation/report.md (~4 мин; --quick — 30 с)
cd ../frontend && npm run build        # проверка типов и сборка
```
