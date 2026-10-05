import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import DB, ERRORS_401, CurrentUser, err
from app.core.config import settings
from app.core.db import utcnow
from app.core.email import send_email
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.models import CandidateProfile, Company, EmailToken, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["candidate", "employer"]
    company_name: str | None = Field(default=None, max_length=200)


class RegisterOut(BaseModel):
    user_id: int
    email: str
    email_sent: bool
    dev_verify_link: str | None = Field(None, description="Только в dev-режиме: ссылка подтверждения для демо")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyIn(BaseModel):
    token: str


class ResendIn(BaseModel):
    email: EmailStr


def user_payload(u: User) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "email_verified": u.email_verified,
            "is_demo": u.is_demo,
            "company_name": u.company.name if u.company else None,
            "onboarding_done": u.candidate.onboarding_done if u.candidate else None}


def _issue_verification(db, user: User) -> tuple[bool, str]:
    token, token_hash = new_opaque_token()
    db.add(EmailToken(user_id=user.id, token_hash=token_hash,
                      expires_at=utcnow() + timedelta(hours=settings.email_token_hours)))
    db.commit()
    link = f"{settings.public_url}/verify-email?token={token}"
    sent = send_email(user.email, "Подтвердите email — ФСП Талант",
                      f"Здравствуйте!\n\nДля завершения регистрации перейдите по ссылке:\n{link}\n\n"
                      f"Ссылка действует {settings.email_token_hours} ч.")
    return sent, link


def create_user(db, email: str, password: str, role: str, company_name: str | None = None,
                verified: bool = False, demo: bool = False, password_hash: str | None = None) -> User:
    user = User(email=email.lower(), password_hash=password_hash or hash_password(password), role=role,
                email_verified=verified, is_demo=demo)
    db.add(user)
    db.flush()
    if role == "candidate":
        db.add(CandidateProfile(user_id=user.id, contact_email=user.email, verify_code=secrets.token_hex(8)))
    else:
        db.add(Company(owner_id=user.id, name=company_name or "", contact_email=user.email))
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED,
             summary="Регистрация по email (кандидат или работодатель)",
             responses={409: {"description": "Email уже зарегистрирован (code: email_taken)"}})
def register(data: RegisterIn, db: DB):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise err(status.HTTP_409_CONFLICT, "email_taken", "Этот email уже зарегистрирован")
    user = create_user(db, data.email, data.password, data.role, data.company_name)
    sent, link = _issue_verification(db, user)
    return RegisterOut(user_id=user.id, email=user.email, email_sent=sent,
                       dev_verify_link=link if settings.expose_email_links else None)


@router.post("/verify-email", response_model=TokenOut, summary="Подтверждение email по токену из письма",
             responses={400: {"description": "Токен недействителен или истёк (code: invalid_token)"}})
def verify_email(data: VerifyIn, db: DB):
    row = db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(data.token)))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at.replace(tzinfo=now.tzinfo) < now:
        raise err(status.HTTP_400_BAD_REQUEST, "invalid_token", "Ссылка недействительна или устарела")
    row.used_at = now
    user = db.get(User, row.user_id)
    user.email_verified = True
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user_payload(user))


@router.post("/resend-verification", summary="Повторно отправить письмо подтверждения")
def resend(data: ResendIn, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user and not user.email_verified:
        sent, link = _issue_verification(db, user)
        return {"ok": True, "dev_verify_link": link if settings.expose_email_links else None}
    return {"ok": True, "dev_verify_link": None}  # same answer for unknown emails: no account enumeration


@router.post("/login", response_model=TokenOut, summary="Вход по email и паролю",
             responses={**ERRORS_401, 403: {"description": "Email не подтверждён (code: email_not_verified)"}})
def login(data: LoginIn, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise err(status.HTTP_401_UNAUTHORIZED, "bad_credentials", "Неверный email или пароль")
    if not user.email_verified:
        raise err(status.HTTP_403_FORBIDDEN, "email_not_verified", "Подтвердите email: письмо отправлено при регистрации")
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user_payload(user))


@router.post("/demo-login", response_model=TokenOut, summary="Вход под демо-аккаунтом (для проверки жюри)",
             responses={404: {"description": "Демо-данные не загружены (code: not_found)"}})
def demo_login(role: Literal["candidate", "employer", "candidate_new"], db: DB):
    email = {"candidate": "demo.candidate@fsp-talent.ru", "employer": "demo.employer@fsp-talent.ru",
             "candidate_new": "demo.new@fsp-talent.ru"}[role]
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise err(status.HTTP_404_NOT_FOUND, "not_found", "Демо-данные не загружены: выполните seed")
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user_payload(user))


@router.get("/me", summary="Текущий пользователь", responses=ERRORS_401)
def me(user: CurrentUser):
    return user_payload(user)
