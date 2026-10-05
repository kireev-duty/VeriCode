from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import CandidateProfile, Company, User

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def err(status_code: int, code: str, message: str) -> HTTPException:
    """Uniform error body: {"detail": {"code": "...", "message": "..."}}."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def current_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None:
        raise err(status.HTTP_401_UNAUTHORIZED, "not_authenticated", "Требуется вход")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise err(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Сессия истекла, войдите снова") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise err(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Пользователь не найден")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_candidate(user: CurrentUser, db: DB) -> CandidateProfile:
    if user.role != "candidate" or user.candidate is None:
        raise err(status.HTTP_403_FORBIDDEN, "forbidden", "Доступно только кандидатам")
    return user.candidate


def current_company(user: CurrentUser, db: DB) -> Company:
    if user.role != "employer" or user.company is None:
        raise err(status.HTTP_403_FORBIDDEN, "forbidden", "Доступно только работодателям")
    return user.company


CurrentCandidate = Annotated[CandidateProfile, Depends(current_candidate)]
CurrentCompany = Annotated[Company, Depends(current_company)]

ERRORS_401 = {401: {"description": "Не авторизован (code: not_authenticated / invalid_token)"}}
ERRORS_403 = {403: {"description": "Недостаточно прав для роли (code: forbidden)"}}
ERRORS_404 = {404: {"description": "Объект не найден (code: not_found)"}}
ERRORS_409 = {409: {"description": "Конфликт состояния (code зависит от операции)"}}
AUTH_ERRORS = {**ERRORS_401, **ERRORS_403}
