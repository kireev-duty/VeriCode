# 7. Используемые библиотеки и компоненты

Весь стек — открытое ПО под лицензиями MIT, Apache-2.0, BSD, PostgreSQL License, OFL. Версии зафиксированы:
- backend — `backend/uv.lock`;
- frontend — `frontend/package-lock.json`;
- образы — `docker-compose.yml` и Dockerfile.

## Инфраструктура

| Компонент | Версия | Лицензия | Назначение |
|---|---|---|---|
| PostgreSQL | 16 (alpine) | PostgreSQL | Основная СУБД |
| Keycloak | 26.1 | Apache-2.0 | ФСП ID: OIDC-провайдер, realm `fsp` |
| nginx | 1.27 (alpine) | BSD-2 | Раздача SPA, обратный прокси `/api`, `/auth`, `/mail` |
| Mailpit | 1.21 | MIT | SMTP и веб-ящик для писем подтверждения на стенде |
| Python | 3.12 | PSF | Backend |
| Node.js | 20 (сборка) | MIT | Сборка frontend |

## Backend (Python)

| Библиотека | Версия | Лицензия | Назначение |
|---|---|---|---|
| fastapi | 0.142.2 | MIT | HTTP API, OpenAPI |
| uvicorn[standard] | 0.54.0 | BSD-3 | ASGI-сервер |
| sqlalchemy | 2.1.3 | MIT | ORM |
| alembic | 1.20.0 | MIT | Миграции |
| psycopg[binary] | 3.3.6 | LGPL-3 | Драйвер PostgreSQL |
| pydantic | 2.13.5 | MIT | Схемы и валидация |
| pydantic-settings | 2.15.0 | MIT | Конфигурация из env |
| pyjwt | 2.15.1 | MIT | JWT-токены |
| argon2-cffi | 25.1.0 | MIT | Хеширование паролей (argon2id) |
| email-validator | 2.3.0 | Unlicense | Валидация email |
| python-multipart | 0.0.32 | Apache-2.0 | Загрузка файлов |
| httpx | 0.28.1 | BSD-3 | OIDC, реестр ФСП, вебхуки |
| numpy | 2.5.3 | BSD-3 | IRT: EAP, информация Фишера |
| pymupdf | 1.28.2 | AGPL-3 / коммерческая | Извлечение текста из PDF-резюме\* |
| reportlab | 5.0.1 | BSD | Генерация PDF-профиля |
| qrcode | 8.2 | BSD | QR-код проверки профиля |
| matplotlib (dev) | 3.11.2 | PSF-based | Графики отчёта валидации |
| pytest (dev) | 9.1.1 | MIT | Тесты |
| ruff (dev) | 0.16 | MIT | Линтер |

\* PyMuPDF распространяется под AGPL. Для коммерческой эксплуатации замена — `pypdf` (BSD): модуль `resume.py`
использует только извлечение текста, это одна функция `pdf_to_text`.

## Frontend

| Библиотека | Версия | Лицензия | Назначение |
|---|---|---|---|
| react, react-dom | 19.3.0 | MIT | UI |
| react-router | 8.4.0 | MIT | Маршрутизация |
| @tanstack/react-query | 5.104.1 | MIT | Запросы и кэш |
| tailwindcss, @tailwindcss/vite | 4.3.3 | MIT | Стили |
| lucide-react | 1.52.0 | ISC | Иконки |
| recharts | 3.10.1 | MIT | Графики аналитики |
| prism-react-renderer | 2.4.1 | MIT | Подсветка кода в заданиях |
| clsx | 2.1.1 | MIT | Утилита классов |
| @fontsource-variable/golos-text | 5.3.0 | OFL-1.1 | Шрифт интерфейса |
| @fontsource-variable/jetbrains-mono | 5.3.0 | OFL-1.1 | Моноширинный шрифт (брендбук ФСП) |
| typescript | 6.0.3 | Apache-2.0 | Типизация |
| vite | 8.3.2 | MIT | Сборка |

## Шрифты в PDF

PT Sans (OFL-1.1, ParaType) и JetBrains Mono (OFL-1.1) лежат в `backend/app/assets/fonts` вместе с текстами лицензий.

## Внешние сервисы

Не используются. Решение работает полностью офлайн: NLP и оценка заданий детерминированны и не требуют LLM.
LLM-провайдер (GigaChat, YandexGPT, Claude) зарезервирован в конфигурации (`LLM_PROVIDER`) только для
необязательного перефразирования условий.
