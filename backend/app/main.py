import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import assessment, auth, candidate, common, employer
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.modules.assessment.service import ensure_item_stats

logging.basicConfig(level=logging.INFO)

DESCRIPTION = """
**ФСП Талант** — платформа подбора ИТ-специалистов с обратной механикой: кандидаты получают категорию
(специализация × грейд) по итогам опроса и адаптивного теста, работодатель находит категорию и сам выходит
на кандидата с предложением и зарплатной вилкой.

Ошибки возвращаются в едином формате: `{"detail": {"code": "...", "message": "..."}}`;
ошибки валидации — `422` с `{"detail": {"code": "validation_error", "message": "...", "errors": [...]}}`.

Авторизация: `Authorization: Bearer <access_token>` из `/api/auth/login` или `/api/auth/verify-email`.
"""

TAGS = [
    {"name": "auth", "description": "Регистрация с подтверждением email, вход"},
    {"name": "candidate", "description": "Кабинет кандидата: профиль, опрос, приватность, ФСП ID, приглашения, отклики"},
    {"name": "assessment", "description": "Адаптивное тестирование на грейд (IRT/CAT, параметрические задания)"},
    {"name": "employer", "description": "Кабинет работодателя: потребности, подборки, поиск, приглашения, вакансии"},
    {"name": "common", "description": "Справочники, уведомления, публичная проверка профиля"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_item_stats(db)
    yield


app = FastAPI(title="ФСП Талант API", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS,
              lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url="/api/redoc")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    first = errors[0]["msg"] if errors else "Некорректные данные"
    return JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "message": first,
                                                             "errors": errors}})


for r in (auth.router, candidate.router, assessment.router, employer.router, common.router):
    app.include_router(r)


@app.get("/api/health", tags=["common"], summary="Проверка работоспособности")
def health():
    return {"ok": True, "env": settings.environment}
