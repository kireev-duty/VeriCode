# 5. Описание API

Полная спецификация OpenAPI 3 генерируется автоматически:
- интерактивная документация — `/api/docs` (Swagger UI) и `/api/redoc`;
- JSON — `/api/openapi.json`.

Каждый эндпоинт описан со схемами запросов и ответов и кодами ошибок.

## Общие правила

- **Авторизация:** `Authorization: Bearer <access_token>`. Токен выдают `/api/auth/login` и `/api/auth/verify-email`.
- **Формат ошибки:**
  - обычная ошибка — `{"detail": {"code": "<машинный код>", "message": "<текст для пользователя>"}}`;
  - ошибка валидации — `422` с `{"detail": {"code": "validation_error", "message": "...", "errors": [...]}}`.
- **Коды ответов:**
  - `401` — нет или истёк токен;
  - `403` — роль не та;
  - `404` — нет объекта или нет доступа к нему;
  - `409` — конфликт состояния;
  - `429` — лимит (квота приглашений, частота тестов).

## Эндпоинты

### auth
| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/auth/register` | Регистрация (candidate / employer); письмо с подтверждением |
| POST | `/api/auth/verify-email` | Подтверждение email → токен |
| POST | `/api/auth/resend-verification` | Повторное письмо |
| POST | `/api/auth/login` | Вход (403 `email_not_verified`, если email не подтверждён) |
| POST | `/api/auth/demo-login?role=` | Вход под демо-аккаунтом: `employer`, `candidate`; `candidate_new` каждый раз создаёт нового кандидата с экспресс-тестом |
| GET | `/api/auth/me` | Текущий пользователь |

### candidate
| Метод | Путь | Назначение |
|---|---|---|
| GET/PUT | `/api/candidate/profile` | Профиль |
| POST | `/api/candidate/onboarding` | Опрос: отрасли, специализация, стек, опыт, предполагаемый грейд |
| PUT | `/api/candidate/privacy` | Видимость, «открыт к предложениям», порог зарплаты, что показывать |
| POST | `/api/candidate/consents` | Согласия на обработку и публикацию (152-ФЗ) |
| POST | `/api/candidate/resume` | PDF-резюме → распознанные поля (не сохраняются) |
| GET | `/api/candidate/profile.pdf` | Стандартизированный PDF-профиль с QR |
| DELETE | `/api/candidate/account` | Удаление аккаунта и данных |
| GET | `/api/candidate/fsp/start` | Начало привязки ФСП ID (URL авторизации) |
| POST | `/api/candidate/fsp/callback` | Обмен кода, загрузка достижений |
| POST/DELETE | `/api/candidate/fsp/refresh`, `/api/candidate/fsp` | Обновить / отвязать |
| GET | `/api/candidate/invitations` | Входящие приглашения (+ траст-скор компании) |
| POST | `/api/candidate/invitations/{id}/view\|accept\|decline\|complain` | Действия с приглашением |
| GET | `/api/candidate/vacancies` | Вакансии с оценкой соответствия профилю |
| POST | `/api/candidate/vacancies/{id}/apply` | Отклик |
| GET | `/api/candidate/applications` | Мои отклики |
| POST | `/api/candidate/applications/{id}/withdraw` | Отозвать отклик |
| GET | `/api/candidate/tasks` | Регулярные задания (новое — раз в неделю) |
| POST | `/api/candidate/tasks/{id}/submit\|skip` | Ответ или пропуск |
| GET | `/api/candidate/dashboard` | Сводка кабинета |

### assessment
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/assessment/eligibility` | Доступные грейды и ограничения по частоте |
| POST | `/api/assessment/sessions` | Начать тест (`target_grade`, опционально `vacancy_id`) |
| GET | `/api/assessment/sessions/{id}` | Текущее задание или результат с разбором |
| POST | `/api/assessment/sessions/{id}/answer` | Ответ (`item_id`, `response`, `signals`) |
| GET | `/api/assessment/history` | Попытки и история грейда |
| POST | `/api/assessment/blueprint-preview` | Публично: вакансия или текст → blueprint и примеры заданий |
| GET | `/api/assessment/bank` | Публично: банк позиций, параметры IRT, экспозиция, статус детектора |

### employer
| Метод | Путь | Назначение |
|---|---|---|
| GET/PUT | `/api/employer/company` | Профиль компании, траст-скор, квота, вебхук |
| POST | `/api/employer/needs/parse` | Текст потребности → структура |
| GET/POST/PUT/DELETE | `/api/employer/needs[/{id}]` | Потребности (сохранённые подборки) |
| POST | `/api/employer/needs/{id}/shortlist` | Подборка: категории и кандидаты с объяснением (тело — фильтры) |
| POST | `/api/employer/needs/{id}/pin\|hide` | Закрепить / скрыть кандидата |
| GET | `/api/employer/categories` | Карта категорий (число кандидатов, с ФСП) |
| POST | `/api/employer/categories/{spec}/{grade}` | Кандидаты категории по силе профиля |
| POST | `/api/employer/search` | Поиск по банку с фильтрами |
| GET | `/api/employer/candidates/{id}?need_id=` | Карточка кандидата (контакты — после принятия или отклика) |
| POST | `/api/employer/invitations/preview` | Попадает ли вилка в ожидания (без суммы), остаток квоты |
| POST | `/api/employer/invitations` | Отправить приглашение (вилка обязательна) |
| GET | `/api/employer/invitations` | Отправленные приглашения и статусы |
| POST | `/api/employer/invitations/{id}/withdraw` | Отозвать |
| GET/POST/PUT | `/api/employer/vacancies[/{id}]` | Вакансии |
| GET | `/api/employer/vacancies/{id}/applications` | Отклики с контактами, отсортированы по соответствию |
| POST | `/api/employer/applications/{id}/status` | Статус отклика |
| GET/POST | `/api/employer/tasks` | Регулярные задания |
| GET | `/api/employer/tasks/{id}/submissions` | Решения кандидатов |
| GET | `/api/employer/analytics` | Воронка, причины отказов, текущие веса ранжирования |

### common
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/catalog` | Справочники |
| GET | `/api/public/verify/{code}` | Проверка подлинности PDF-профиля по QR |
| GET | `/api/public/stats` | Открытая статистика |
| GET/POST | `/api/notifications`, `/api/notifications/read` | Уведомления |
| GET | `/api/health` | Проверка работоспособности |

## Вебхуки для ATS

POST на `webhook_url` компании. Тело — `{"event": "...", "data": {...}}`. Заголовки:
- `X-FSP-Talent-Event`;
- `X-FSP-Talent-Signature` — HMAC-SHA256 тела, ключ `webhook_secret`.

События:
- `invitation.sent`;
- `invitation.accepted` — с контактами кандидата;
- `invitation.declined` — с причиной;
- `application.created`.

Журнал доставок хранится в `webhook_deliveries`.

## Реестр ФСП (мок)

Отдельный сервис `fsp_registry`. Swagger — `/docs` внутри контейнера. Контракт описан в
[04-fsp-integration.md](04-fsp-integration.md).
