# 8. Сборка, развёртывание и локальный запуск

## Вариант 1. Docker Compose (рекомендуется)

Требования: Docker 24+ с Compose v2, 3 ГБ свободной памяти, свободный порт 8080. ОС любая: Linux, macOS или Windows
с Docker Desktop. GPU не нужен: локальных моделей нет, языковая модель необязательна и вызывается по API. Стек
с запасом укладывается в ориентир стенда жюри (8 CPU, 32–64 ГБ RAM).

Для проверки: на странице входа кнопка «Новый кандидат» создаёт свежий аккаунт на каждый клик, тест в нём
идёт в экспресс-режиме (3–5 минут). «Демо-работодатель» открывает кабинет с готовыми потребностями и подборками.

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
| `HTTP_BIND` | `0.0.0.0` | Адрес публикации порта; `127.0.0.1` за Caddy, чтобы не было входа в обход HTTPS |
| `JWT_SECRET` | dev-значение | Секрет подписи токенов — **сменить в проде** |
| `POSTGRES_PASSWORD` | `fsp` | Пароль БД |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Пароль админки Keycloak |
| `SEED_DEMO` | `true` | Загрузить демо-данные при старте |
| `EXPOSE_EMAIL_LINKS` | `true` | Возвращать ссылку подтверждения в ответе API (только для демо) |
| `FSP_OIDC_ENABLED` | `true` | `false` — встроенная заглушка ФСП ID вместо Keycloak |
| `LLM_PROVIDER` | `none` | Языковая модель поверх правил NLP: `none`, `gigachat`, `yandex`, `local` или цепочка через запятую (`gigachat,local`: при сбое первой отвечает следующая, при сбое всех — правила) |
| `LLM_API_KEY` | — | GigaChat: ключ авторизации (Base64) из личного кабинета; YandexGPT: API-ключ сервисного аккаунта |
| `LLM_MODEL` | — | По умолчанию `GigaChat` или `yandexgpt-lite/latest` |
| `LLM_SCOPE` | `GIGACHAT_API_PERS` | GigaChat: `GIGACHAT_API_PERS`, `GIGACHAT_API_B2B` или `GIGACHAT_API_CORP` |
| `LLM_FOLDER_ID` | — | YandexGPT: идентификатор каталога Yandex Cloud |
| `LLM_VERIFY_SSL`, `LLM_CA_BUNDLE` | `true`, `certs/russian_trusted_ca.pem` | GigaChat использует сертификат НУЦ Минцифры: корневой и промежуточный сертификаты лежат в `backend/certs/` и встроены в образ |
| `LLM_TIMEOUT` | `30` | Таймаут ответа облачной модели, с; соединение повторяется до 3 раз |
| `LOCAL_LLM_URL` | `http://ollama:11434/v1` | Локальная открытая модель: OpenAI-совместимый API (Ollama, vLLM, llama.cpp server) |
| `LOCAL_LLM_MODEL` | `qwen3:4b-instruct` | Qwen3-4B-Instruct-2507 (Apache-2.0), ~2.5 ГБ; Ollama скачивает её при первом старте |

Локальная модель запускается профилем: `docker compose --profile local-llm up -d` (+~3 ГБ RAM, без видеокарты ответ 10–40 с).
Данные кандидатов при этом не покидают сервер.

Без ключа все сценарии работают на правилах. Проверить ключ: `cd backend && uv run python -m app.modules.llm "текст вакансии"`
— команда покажет провайдера, разбор правилами и уточнённый разбор.

## Вариант 2. Развёртывание на сервере с HTTPS

1. VPS с 2 vCPU, 4 ГБ RAM и 30 ГБ диска (Ubuntu 24.04). Домен: A-запись `talent` → IP сервера, TTL 300;
   проверка — `nslookup talent.example.ru`. Без покупки домена подойдёт DuckDNS или `<ip>.sslip.io`.
2. Подготовьте сервер:

   ```bash
   curl -fsSL https://get.docker.com | sh
   apt install -y caddy git
   ufw allow 22,80,443/tcp && ufw enable
   git clone <repo> fsp-talent && cd fsp-talent
   ```

3. В `.env` задайте: `PUBLIC_URL=https://talent.example.ru`, `HTTP_BIND=127.0.0.1` (стенд доступен только через
   Caddy), `JWT_SECRET=<openssl rand -hex 32>`, `POSTGRES_PASSWORD` и `KEYCLOAK_ADMIN_PASSWORD` — случайные,
   `EXPOSE_EMAIL_LINKS=false` (если настроен настоящий SMTP) или `true` (для демо-стенда).
4. Поставьте перед стеком Caddy для автоматического TLS: замените домен в `deploy/Caddyfile`, затем

   ```bash
   docker compose up -d --build
   cp deploy/Caddyfile /etc/caddy/Caddyfile && systemctl reload caddy   # сертификат Let's Encrypt выпустится сам
   curl https://talent.example.ru/api/health
   ```

5. Nginx внутри стека передаёт `X-Forwarded-Proto`, Keycloak работает за прокси (`KC_PROXY_HEADERS=xforwarded`).
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
uv run pytest -q                       # 341 тест: сквозной сценарий API, права доступа, политики, уникальность
                                       # каждой позиции банка, CAT и экспозиция, скоринг, LLM-слой, пилот, резюме
uv run ruff check app validation tests # линтер
uv run python -m validation.run        # валидация: docs/validation/report.md (~15 мин; --quick — ~5 мин)
uv run python -m validation.labeling   # форма разметки пар людьми: docs/validation/labeling/index.html
uv run python -m validation.resumes    # пересобрать набор PDF-резюме для раздела 10
cd ../frontend && npm run build        # проверка типов и сборка
```

Против запущенного стенда (`docker compose up -d --build`):

```bash
cd e2e && npm ci && npx playwright install chromium
npx playwright test                    # сквозной сценарий ТЗ 3.3 + скриншоты всех страниц на 1440 и 375 px
                                       # (e2e/screens/), проверка отсутствия горизонтальной прокрутки
cd ../backend
uv run python -m validation.load --users 50 --seconds 180   # нагрузка: p50/p95/p99 → docs/validation/load.json
```

Результаты последнего нагрузочного прогона (50 одновременных пользователей, 3 минуты, ноутбук): 37 запросов в
секунду без ошибок; p95 всех операций ≤ 380 мс (подборка — 218 мс, поиск — 143 мс, карточка кандидата — 102 мс).
Память стека под нагрузкой — около 1 ГБ: backend ~300 МБ, Keycloak ~525 МБ, PostgreSQL ~85 МБ.

### Пилот на людях

1. Задайте токен выгрузки: `PILOT_EXPORT_TOKEN=<случайная строка>` в `.env` рядом с `docker-compose.yml`, затем
   `docker compose up -d`.
2. Участники регистрируются, проходят тест и заполняют анкету «Помогите проверить тест» на странице результата.
3. `cd backend && uv run python -m validation.pilot --fetch http://<стенд> --token <токен>` сохраняет обезличенную
   выгрузку в `docs/validation/pilot/`; `uv run python -m validation.run` добавит раздел «Пилот» в отчёт.
