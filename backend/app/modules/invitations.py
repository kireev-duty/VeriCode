"""Invitation (employer -> candidate) and application (candidate -> vacancy) lifecycles.

Invitation statuses: sent -> viewed -> accepted | declined; sent/viewed -> expired (TTL) | withdrawn (employer).
Application statuses: sent -> viewed -> invited | rejected; sent/viewed -> withdrawn (candidate).
Contacts of a candidate open to a company after an accepted invitation or the candidate's own application.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.models import Application, CandidateProfile, Company, Invitation, Vacancy
from app.modules.events import emit_webhook, notify
from app.modules.matching.scoring import adapt_weights
from app.modules.matching.service import in_bank

DECLINE_REASONS = {
    "salary": "Не устраивает зарплата",
    "stack": "Не подходит стек или задачи",
    "format": "Не подходит формат работы или город",
    "grade": "Позиция не соответствует уровню",
    "company": "Не интересна компания или сфера",
    "not_looking": "Сейчас не ищу работу",
    "other": "Другое",
}


class FlowError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _aware(dt):
    from datetime import UTC
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def quota_left(db: Session, company_id: int) -> int:
    since = utcnow() - timedelta(days=7)
    used = db.scalar(select(func.count(Invitation.id)).where(Invitation.company_id == company_id,
                                                              Invitation.created_at >= since)) or 0
    return max(0, settings.invitation_weekly_quota - used)


def expire_stale(db: Session) -> int:
    now = utcnow()
    n = 0
    for inv in db.scalars(select(Invitation).where(Invitation.status.in_(["sent", "viewed"]))):
        if _aware(inv.expires_at) < now:
            inv.status = "expired"
            n += 1
    if n:
        db.commit()
    return n


def send_invitation(db: Session, company: Company, cand: CandidateProfile, data: dict) -> Invitation:
    if not company.name:
        raise FlowError("company_profile_required", "Заполните профиль компании: название видно кандидату", 400)
    if not in_bank(cand):
        raise FlowError("candidate_unavailable", "Кандидат недоступен для приглашений", 404)
    if not cand.open_to_offers:
        raise FlowError("not_open", "Кандидат сейчас не принимает предложения")
    if data["salary_from"] > data["salary_to"]:
        raise FlowError("bad_salary", "Нижняя граница вилки больше верхней", 400)
    active = db.scalar(select(Invitation).where(Invitation.company_id == company.id,
                                                Invitation.candidate_id == cand.id,
                                                Invitation.status.in_(["sent", "viewed"])))
    if active:
        raise FlowError("already_invited", "У кандидата уже есть активное приглашение от вашей компании")
    if quota_left(db, company.id) <= 0:
        raise FlowError("quota_exceeded", f"Лимит {settings.invitation_weekly_quota} приглашений в неделю исчерпан",
                        429)
    below = bool(cand.min_salary_for_invites and data["salary_to"] < cand.min_salary_for_invites)
    inv = Invitation(company_id=company.id, candidate_id=cand.id, need_id=data.get("need_id"),
                     vacancy_id=data.get("vacancy_id"), position_title=data["position_title"],
                     message=data["message"], salary_from=data["salary_from"], salary_to=data["salary_to"],
                     work_format=data.get("work_format") or "", contact_method=data["contact_method"],
                     challenge_task_id=data.get("challenge_task_id"), below_expectation=below,
                     match_score=data.get("match_score"), match_explanation=data.get("match_explanation") or [],
                     expires_at=utcnow() + timedelta(days=settings.invitation_ttl_days))
    db.add(inv)
    db.flush()
    notify(db, cand.user_id, "invitation", f"{company.name} приглашает: {inv.position_title}, "
                                           f"{inv.salary_from:,}–{inv.salary_to:,} ₽".replace(",", " "),
           f"/candidate/invitations/{inv.id}")
    db.commit()
    emit_webhook(company, "invitation.sent", {"invitation_id": inv.id, "candidate_code": cand.verify_code[:5]})
    return inv


def mark_viewed(db: Session, inv: Invitation) -> None:
    if inv.status == "sent":
        inv.status = "viewed"
        inv.viewed_at = utcnow()
        db.commit()


def respond(db: Session, inv: Invitation, accept: bool, reason: str | None = None, comment: str = "") -> Invitation:
    if inv.status not in ("sent", "viewed"):
        raise FlowError("not_actionable", "Приглашение уже обработано или истекло")
    if _aware(inv.expires_at) < utcnow():
        inv.status = "expired"
        db.commit()
        raise FlowError("expired", "Срок приглашения истёк")
    now = utcnow()
    inv.viewed_at = inv.viewed_at or now
    inv.responded_at = now
    company = db.get(Company, inv.company_id)
    cand = db.get(CandidateProfile, inv.candidate_id)
    if accept:
        inv.status = "accepted"
        notify(db, company.owner_id, "invitation_accepted",
               f"Кандидат {cand.verify_code[:5].upper()} принял приглашение «{inv.position_title}» — контакты открыты",
               f"/employer/candidates/{cand.id}")
        db.commit()
        emit_webhook(company, "invitation.accepted", {
            "invitation_id": inv.id, "position": inv.position_title,
            "candidate": {"full_name": cand.full_name, "email": cand.contact_email, "phone": cand.phone,
                          "telegram": cand.telegram, "grade": cand.grade, "specialization": cand.specialization}})
    else:
        if reason not in DECLINE_REASONS:
            raise FlowError("bad_reason", "Укажите причину отказа", 400)
        inv.status = "declined"
        inv.decline_reason = reason
        inv.decline_comment = comment
        company.ranking_weights = adapt_weights(company.ranking_weights or {}, reason)
        notify(db, company.owner_id, "invitation_declined",
               f"Отказ по «{inv.position_title}»: {DECLINE_REASONS[reason].lower()}", "/employer/invitations")
        db.commit()
        emit_webhook(company, "invitation.declined", {"invitation_id": inv.id, "reason": reason})
    return inv


def withdraw(db: Session, inv: Invitation) -> None:
    if inv.status not in ("sent", "viewed"):
        raise FlowError("not_actionable", "Отозвать можно только активное приглашение")
    inv.status = "withdrawn"
    db.commit()


def apply(db: Session, cand: CandidateProfile, vac: Vacancy, cover: str) -> Application:
    if vac.status != "published":
        raise FlowError("vacancy_closed", "Вакансия закрыта")
    if cand.consent_processing_at is None:
        raise FlowError("consent_required", "Дайте согласие на обработку данных в настройках", 400)
    existing = db.scalar(select(Application).where(Application.vacancy_id == vac.id,
                                                   Application.candidate_id == cand.id))
    if existing and existing.status != "withdrawn":
        raise FlowError("already_applied", "Вы уже откликнулись на эту вакансию")
    if existing:
        existing.status, existing.cover_letter = "sent", cover
        app = existing
    else:
        app = Application(vacancy_id=vac.id, candidate_id=cand.id, cover_letter=cover)
        db.add(app)
    db.flush()
    company = db.get(Company, vac.company_id)
    notify(db, company.owner_id, "application", f"Новый отклик на «{vac.title}»", f"/employer/vacancies/{vac.id}")
    db.commit()
    emit_webhook(company, "application.created", {"application_id": app.id, "vacancy_id": vac.id})
    return app


def set_application_status(db: Session, app: Application, status: str, comment: str = "") -> Application:
    allowed = {"viewed", "invited", "rejected"}
    if status not in allowed:
        raise FlowError("bad_status", "Недопустимый статус", 400)
    if app.status == "withdrawn":
        raise FlowError("withdrawn", "Кандидат отозвал отклик")
    app.status = status
    app.employer_comment = comment
    cand = db.get(CandidateProfile, app.candidate_id)
    titles = {"viewed": "Ваш отклик просмотрен", "invited": "Вас приглашают на собеседование",
              "rejected": "По отклику принято решение"}
    notify(db, cand.user_id, "application_status", f"{titles[status]}: «{app.vacancy.title}»",
           "/candidate/applications")
    db.commit()
    return app
