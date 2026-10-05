from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB, ERRORS_401, ERRORS_404, CurrentUser, err
from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID, catalog_payload
from app.models import CandidateProfile, Company, Invitation, Notification, Vacancy
from app.modules.fsp.scoring import DISCIPLINES, LEVELS, RESULTS

router = APIRouter(prefix="/api", tags=["common"])


@router.get("/catalog", summary="Справочники: специализации, грейды, навыки, отрасли, форматы работы")
def catalog():
    return catalog_payload() | {"fsp": {"disciplines": DISCIPLINES, "levels": {k: v[0] for k, v in LEVELS.items()},
                                        "results": {k: v[0] for k, v in RESULTS.items()}}}


@router.get("/public/verify/{code}", summary="Публичная проверка PDF-профиля по QR-коду", responses=ERRORS_404)
def verify(code: str, db: DB):
    c = db.scalar(select(CandidateProfile).where(CandidateProfile.verify_code == code))
    if c is None:
        raise err(404, "not_found", "Профиль не найден")
    return {
        "code": f"К-{c.verify_code[:5].upper()}",
        "full_name": c.full_name if c.consent_publication_at else "",
        "specialization": SPEC_BY_ID[c.specialization].title if c.specialization else None,
        "grade": GRADE_BY_ID[c.grade].title if c.grade else None,
        "grade_confirmed_at": c.grade_confirmed_at,
        "verified_skills": [SKILL_BY_ID[s].title for s in (c.skill_theta or {}) if s in SKILL_BY_ID],
        "fsp_linked": bool(c.fsp_id),
        "achievements": [{"event_name": a.event_name, "year": a.date.year,
                          "result": RESULTS.get(a.result_type, (a.result_type,))[0],
                          "level": LEVELS.get(a.event_level, (a.event_level,))[0]} for a in c.achievements],
    }


@router.get("/public/stats", summary="Открытая статистика платформы")
def stats(db: DB):
    searchable = select(func.count(CandidateProfile.id)).where(CandidateProfile.grade.is_not(None))
    return {
        "candidates": db.scalar(searchable) or 0,
        "with_fsp": db.scalar(searchable.where(CandidateProfile.fsp_id.is_not(None))) or 0,
        "companies": db.scalar(select(func.count(Company.id)).where(Company.name != "")) or 0,
        "vacancies": db.scalar(select(func.count(Vacancy.id)).where(Vacancy.status == "published")) or 0,
        "invitations": db.scalar(select(func.count(Invitation.id))) or 0,
        "accepted": db.scalar(select(func.count(Invitation.id)).where(Invitation.status == "accepted")) or 0,
    }


@router.get("/notifications", summary="Уведомления текущего пользователя", responses=ERRORS_401)
def notifications(user: CurrentUser, db: DB, limit: int = 30):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                                 Notification.read.is_(False))) or 0
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "link": n.link,
                                         "read": n.read, "created_at": n.created_at} for n in rows]}


@router.post("/notifications/read", summary="Отметить все уведомления прочитанными", responses=ERRORS_401)
def read_all(user: CurrentUser, db: DB):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}
