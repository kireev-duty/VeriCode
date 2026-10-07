from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AUTH_ERRORS, DB, ERRORS_404, CurrentCandidate, err
from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID
from app.core.db import utcnow
from app.models import (
    Application,
    AssessmentSession,
    CandidateProfile,
    Company,
    FspAchievement,
    Invitation,
    TaskSubmission,
    User,
    Vacancy,
)
from app.modules import invitations as flow
from app.modules import pdf_profile, resume, tasks
from app.modules.fsp import client as fsp
from app.modules.matching.scoring import score
from app.modules.matching.service import candidate_view, experience_public, need_spec

router = APIRouter(prefix="/api/candidate", tags=["candidate"], responses=AUTH_ERRORS)


# ------------------------------------------------------------------------------------------------ schemas


class SkillIn(BaseModel):
    id: str
    years: float | None = None


class ExperienceIn(BaseModel):
    company: str = ""
    position: str = ""
    start: str = Field("", alias="from")
    to: str = ""
    summary: str = ""

    model_config = {"populate_by_name": True}


class ProfileIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    telegram: str | None = None
    contact_email: str | None = None
    birth_year: int | None = None
    headline: str | None = None
    about: str | None = None
    city: str | None = None
    work_formats: list[Literal["office", "hybrid", "remote"]] | None = None
    relocation: bool | None = None
    salary_expectation: int | None = Field(None, ge=0)
    experience_years: float | None = Field(None, ge=0, le=60)
    skills: list[SkillIn] | None = None
    team_roles: list[str] | None = None
    soft_skills: list[str] | None = None
    experience: list[ExperienceIn] | None = None
    education: list[dict] | None = None


class OnboardingIn(BaseModel):
    industries: list[str] = Field(default_factory=list, description="Отрасли, в которых есть опыт")
    specialization: str
    stack: list[SkillIn] = Field(default_factory=list)
    experience_years: float = Field(0, ge=0, le=60)
    declared_grade: Literal["intern", "junior", "middle", "senior"]
    team_roles: list[str] = Field(default_factory=list)
    work_formats: list[Literal["office", "hybrid", "remote"]] = Field(default_factory=list)
    answers: dict = Field(default_factory=dict, description="Ответы на вопросы опроса (самооценка, задачи)")


class PrivacyIn(BaseModel):
    visible_to_employers: bool | None = None
    open_to_offers: bool | None = None
    min_salary_for_invites: int | None = Field(None, ge=0)
    privacy: dict | None = Field(None, description="show_city, show_fsp, show_companies")


class ConsentIn(BaseModel):
    processing: bool
    publication: bool


class DeclineIn(BaseModel):
    reason: Literal["salary", "stack", "format", "grade", "company", "not_looking", "other"]
    comment: str = ""


class ComplaintIn(BaseModel):
    reason: Literal["fake", "spam", "salary_mismatch", "rude", "other"]
    comment: str = ""


class ApplyIn(BaseModel):
    cover_letter: str = ""


class FspCallbackIn(BaseModel):
    code: str
    state: str


class TaskAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)


# ------------------------------------------------------------------------------------------------ profile


def profile_out(c: CandidateProfile) -> dict:
    return {
        "id": c.id, "code": f"К-{c.verify_code[:5].upper()}", "verify_code": c.verify_code,
        "full_name": c.full_name, "phone": c.phone, "telegram": c.telegram, "contact_email": c.contact_email,
        "birth_year": c.birth_year, "headline": c.headline, "about": c.about, "city": c.city,
        "work_formats": c.work_formats, "relocation": c.relocation, "salary_expectation": c.salary_expectation,
        "experience_years": c.experience_years, "skills": c.skills, "team_roles": c.team_roles,
        "soft_skills": c.soft_skills, "experience": c.experience, "education": c.education,
        "industries": c.industries, "specialization": c.specialization,
        "specialization_title": SPEC_BY_ID[c.specialization].title if c.specialization else None,
        "declared_grade": c.declared_grade, "onboarding_done": c.onboarding_done,
        "grade": c.grade, "grade_title": GRADE_BY_ID[c.grade].title if c.grade else None,
        "theta": c.theta, "theta_se": c.theta_se, "skill_theta": c.skill_theta,
        "grade_confirmed_at": c.grade_confirmed_at, "grade_changed_at": c.grade_changed_at,
        "last_task_at": c.last_task_at, "task_score": c.task_score,
        "fsp_id": c.fsp_id, "fsp_linked_at": c.fsp_linked_at, "fsp_profile": c.fsp_profile,
        "achievements": [{"id": a.id, "event_name": a.event_name, "event_level": a.event_level,
                          "discipline": a.discipline, "date": a.date, "place": a.place, "participants": a.participants,
                          "team_name": a.team_name, "team_role": a.team_role, "result_type": a.result_type,
                          "certificate_url": a.certificate_url} for a in c.achievements],
        "consent_processing_at": c.consent_processing_at, "consent_publication_at": c.consent_publication_at,
        "visible_to_employers": c.visible_to_employers, "open_to_offers": c.open_to_offers,
        "min_salary_for_invites": c.min_salary_for_invites,
        "privacy": {"show_city": True, "show_fsp": True, "show_companies": False, **(c.privacy or {})},
        "searchable": bool(c.grade and c.visible_to_employers and c.consent_publication_at),
    }


@router.get("/profile", summary="Мой профиль")
def get_profile(cand: CurrentCandidate):
    return profile_out(cand)


@router.put("/profile", summary="Обновить профиль (частично)")
def update_profile(data: ProfileIn, cand: CurrentCandidate, db: DB):
    values = data.model_dump(exclude_unset=True, by_alias=True)
    if "skills" in values:
        values["skills"] = [s for s in values["skills"] if s["id"] in SKILL_BY_ID]
    for k, v in values.items():
        setattr(cand, k, v)
    db.commit()
    return profile_out(cand)


@router.post("/onboarding", summary="Опрос по отрасли и специализации, выбор предполагаемого грейда",
             responses={400: {"description": "Неизвестная специализация (code: bad_specialization)"}})
def onboarding(data: OnboardingIn, cand: CurrentCandidate, db: DB):
    if data.specialization not in SPEC_BY_ID:
        raise err(400, "bad_specialization", "Неизвестная специализация")
    if cand.grade and cand.specialization and cand.specialization != data.specialization:
        raise err(409, "specialization_locked",
                  "Специализация закреплена результатом теста; смена — через поддержку или после 90 дней")
    cand.industries = data.industries
    cand.specialization = data.specialization
    stack = {s["id"]: s for s in (cand.skills or []) if isinstance(s, dict)}
    for s in data.stack:
        if s.id in SKILL_BY_ID:
            stack[s.id] = {"id": s.id, "years": s.years}
    cand.skills = list(stack.values())
    cand.experience_years = data.experience_years
    cand.declared_grade = data.declared_grade
    cand.team_roles = data.team_roles or cand.team_roles
    cand.work_formats = data.work_formats or cand.work_formats
    cand.survey = data.answers
    cand.onboarding_done = True
    db.commit()
    return profile_out(cand)


@router.put("/privacy", summary="Приватность: видимость для работодателей, порог зарплаты, что показывать")
def update_privacy(data: PrivacyIn, cand: CurrentCandidate, db: DB):
    values = data.model_dump(exclude_unset=True)
    if "privacy" in values:
        cand.privacy = {**(cand.privacy or {}), **values.pop("privacy")}
    for k, v in values.items():
        setattr(cand, k, v)
    db.commit()
    return profile_out(cand)


@router.post("/consents", summary="Согласия по 152-ФЗ: обработка и публикация профиля")
def consents(data: ConsentIn, cand: CurrentCandidate, db: DB):
    now = utcnow()
    cand.consent_processing_at = now if data.processing else None
    cand.consent_publication_at = now if (data.publication and data.processing) else None
    if not data.processing:
        cand.visible_to_employers = False
    db.commit()
    return profile_out(cand)


@router.post("/resume", summary="Загрузить PDF-резюме и получить распознанные поля (не сохраняются)",
             responses={400: {"description": "Не PDF или файл пустой (code: bad_file)"}})
async def upload_resume(cand: CurrentCandidate, file: UploadFile = File(...)):
    data = await file.read()
    if not data or len(data) > 10 * 1024 * 1024 or not data.startswith(b"%PDF"):
        raise err(400, "bad_file", "Загрузите PDF до 10 МБ")
    try:
        parsed = resume.parse_resume_pdf(data)
    except Exception:  # noqa: BLE001 - malformed PDFs come in many shapes
        raise err(400, "bad_file", "Не удалось прочитать PDF") from None
    parsed["skills"] = [{**s, "title": SKILL_BY_ID[s["id"]].title} for s in parsed["skills"]]
    return parsed


@router.get("/profile.pdf", summary="Стандартизированный PDF-профиль с QR-кодом проверки",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def profile_pdf(cand: CurrentCandidate):
    pdf = pdf_profile.render(cand)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="profile-{cand.verify_code[:5]}.pdf"'})


@router.delete("/account", summary="Удалить аккаунт и все персональные данные (152-ФЗ)")
def delete_account(cand: CurrentCandidate, db: DB):
    user = db.get(User, cand.user_id)
    db.delete(user)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------------------------------------ FSP


@router.get("/fsp/start", summary="Начать привязку ФСП ID (OIDC, Keycloak-совместимо)")
def fsp_start(cand: CurrentCandidate):
    return fsp.authorize_url(cand.id)


def _store_fsp(db, cand: CandidateProfile, fsp_id: str) -> None:
    other = db.scalar(select(CandidateProfile).where(CandidateProfile.fsp_id == fsp_id,
                                                     CandidateProfile.id != cand.id))
    if other:
        raise err(409, "fsp_taken", "Этот ФСП ID уже привязан к другому профилю")
    try:
        participant, results = fsp.fetch_registry(fsp_id)
    except fsp.FspError as e:
        raise err(404, e.code, e.message) from None
    cand.fsp_id = fsp_id
    cand.fsp_linked_at = utcnow()
    cand.fsp_profile = {"rank": participant.get("rank", ""), "rating": participant.get("rating", 0),
                        "region": participant.get("region", ""), "disciplines": participant.get("disciplines", [])}
    cand.achievements.clear()
    db.flush()
    for r in results:
        ev = r["event"]
        cand.achievements.append(FspAchievement(
            external_id=r["id"], event_name=ev["name"], event_level=ev["level"], discipline=ev["discipline"],
            date=datetime.fromisoformat(ev["date"]), place=r.get("place"), participants=r.get("participants_count"),
            team_name=(r.get("team") or {}).get("name", ""), team_role=(r.get("team") or {}).get("role", ""),
            result_type=r["result_type"], certificate_url=r.get("certificate_url", "")))
    if any((r.get("team") or {}).get("role") == "Капитан" for r in results):
        if "Капитан команды" not in (cand.team_roles or []):
            cand.team_roles = [*(cand.team_roles or []), "Капитан команды"]
    db.commit()


@router.post("/fsp/callback", summary="Завершить привязку ФСП ID: обмен кода и загрузка достижений из реестра",
             responses={400: {"description": "invalid_state / invalid_code / oidc_failed"},
                        404: {"description": "fsp_not_found"}, 409: {"description": "fsp_taken"}})
def fsp_callback(data: FspCallbackIn, cand: CurrentCandidate, db: DB):
    try:
        fsp.check_state(data.state, cand.id)
        fsp_id = fsp.exchange_code(data.code)
    except fsp.FspError as e:
        raise err(400, e.code, e.message) from None
    _store_fsp(db, cand, fsp_id)
    return profile_out(cand)


@router.post("/fsp/refresh", summary="Обновить достижения из реестра ФСП",
             responses={400: {"description": "ФСП ID не привязан (code: not_linked)"}})
def fsp_refresh(cand: CurrentCandidate, db: DB):
    if not cand.fsp_id:
        raise err(400, "not_linked", "ФСП ID не привязан")
    _store_fsp(db, cand, cand.fsp_id)
    return profile_out(cand)


@router.delete("/fsp", summary="Отвязать ФСП ID")
def fsp_unlink(cand: CurrentCandidate, db: DB):
    cand.fsp_id = None
    cand.fsp_linked_at = None
    cand.fsp_profile = {}
    cand.achievements.clear()
    db.commit()
    return profile_out(cand)


# ------------------------------------------------------------------------------------------------ invitations


def invitation_out(inv: Invitation, company: Company) -> dict:
    return {
        "id": inv.id, "status": inv.status, "position_title": inv.position_title, "message": inv.message,
        "salary_from": inv.salary_from, "salary_to": inv.salary_to, "work_format": inv.work_format,
        "contact_method": inv.contact_method if inv.status == "accepted" else None,
        "contact_method_hint": "Откроется после принятия" if inv.status != "accepted" else None,
        "below_expectation": inv.below_expectation, "decline_reason": inv.decline_reason,
        "company": {"id": company.id, "name": company.name, "industry": company.industry, "city": company.city,
                    "website": company.website, "description": company.description, "size": company.size,
                    "domain_verified": company.domain_verified, "logo_color": company.logo_color},
        "need_id": inv.need_id, "vacancy_id": inv.vacancy_id, "challenge_task_id": inv.challenge_task_id,
        "match_explanation": inv.match_explanation,
        "created_at": inv.created_at, "viewed_at": inv.viewed_at, "responded_at": inv.responded_at,
        "expires_at": inv.expires_at,
    }


def _own_invitation(db, cand, inv_id: int) -> Invitation:
    inv = db.get(Invitation, inv_id)
    if inv is None or inv.candidate_id != cand.id:
        raise err(404, "not_found", "Приглашение не найдено")
    return inv


@router.get("/invitations", summary="Входящие приглашения от работодателей")
def my_invitations(cand: CurrentCandidate, db: DB):
    flow.expire_stale(db)
    rows = db.scalars(select(Invitation).where(Invitation.candidate_id == cand.id)
                      .order_by(Invitation.created_at.desc())).all()
    from app.modules.trust import trust_for
    trust: dict[int, dict] = {}  # one trust computation per company, not per invitation
    out = []
    for inv in rows:
        if inv.company_id not in trust:
            trust[inv.company_id] = trust_for(db, inv.company)
        item = invitation_out(inv, inv.company)
        item["company"]["trust"] = trust[inv.company_id]
        out.append(item)
    return out


@router.post("/invitations/{inv_id}/view", summary="Отметить приглашение просмотренным", responses=ERRORS_404)
def view_invitation(inv_id: int, cand: CurrentCandidate, db: DB):
    inv = _own_invitation(db, cand, inv_id)
    flow.mark_viewed(db, inv)
    return invitation_out(inv, inv.company)


@router.post("/invitations/{inv_id}/accept", summary="Принять приглашение: работодателю откроются контакты",
             responses={**ERRORS_404, 409: {"description": "not_actionable / expired"}})
def accept_invitation(inv_id: int, cand: CurrentCandidate, db: DB):
    inv = _own_invitation(db, cand, inv_id)
    try:
        flow.respond(db, inv, True)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    return invitation_out(inv, inv.company)


@router.post("/invitations/{inv_id}/decline", summary="Отклонить приглашение с причиной",
             responses={**ERRORS_404, 409: {"description": "not_actionable / expired"}})
def decline_invitation(inv_id: int, data: DeclineIn, cand: CurrentCandidate, db: DB):
    inv = _own_invitation(db, cand, inv_id)
    try:
        flow.respond(db, inv, False, data.reason, data.comment)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    return invitation_out(inv, inv.company)


@router.post("/invitations/{inv_id}/complain", summary="Пожаловаться на работодателя (фиктивное предложение и т. п.)",
             responses=ERRORS_404)
def complain(inv_id: int, data: ComplaintIn, cand: CurrentCandidate, db: DB):
    from app.models import Complaint
    inv = _own_invitation(db, cand, inv_id)
    db.add(Complaint(company_id=inv.company_id, candidate_id=cand.id, invitation_id=inv.id, reason=data.reason,
                     comment=data.comment))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------------------------------------ vacancies


@router.get("/vacancies", summary="Опубликованные вакансии с оценкой соответствия моему профилю")
def vacancies(cand: CurrentCandidate, db: DB, specialization: str | None = None, only_matching: bool = False):
    q = (select(Vacancy).where(Vacancy.status == "published").options(selectinload(Vacancy.company))
         .order_by(Vacancy.created_at.desc()))
    if specialization:
        q = q.where(Vacancy.specialization == specialization)
    rows = db.scalars(q).all()
    applied = {a.vacancy_id: a.status for a in db.scalars(select(Application).where(
        Application.candidate_id == cand.id))}
    view = candidate_view(cand)
    out = []
    from app.modules.trust import trust_for
    # the trust score runs several queries (invitations, complaints, market salaries): once per company, not per
    # vacancy - this endpoint was the slowest one under the load test (validation/load.py)
    trust: dict[int, dict] = {}
    for v in rows:
        s = score(view, need_spec(v)) if cand.grade else None
        if only_matching and (s is None or v.specialization != cand.specialization):
            continue
        if v.company_id not in trust:
            trust[v.company_id] = trust_for(db, v.company)
        out.append({**vacancy_out(v), "match": s, "application_status": applied.get(v.id),
                    "company_trust": trust[v.company_id]})
    if only_matching:
        out.sort(key=lambda x: -(x["match"] or {}).get("score", 0))
    return out


def vacancy_out(v: Vacancy) -> dict:
    return {"id": v.id, "title": v.title, "description": v.description, "specialization": v.specialization,
            "specialization_title": SPEC_BY_ID[v.specialization].short, "grade": v.grade,
            "grade_title": GRADE_BY_ID[v.grade].title, "must_skills": v.must_skills, "nice_skills": v.nice_skills,
            "work_formats": v.work_formats, "city": v.city, "salary_from": v.salary_from, "salary_to": v.salary_to,
            "status": v.status, "created_at": v.created_at,
            "company": {"id": v.company.id, "name": v.company.name, "industry": v.company.industry,
                        "logo_color": v.company.logo_color, "domain_verified": v.company.domain_verified}}


@router.post("/vacancies/{vac_id}/apply", summary="Откликнуться на вакансию (контакты откроются работодателю)",
             responses={**ERRORS_404, 409: {"description": "already_applied / vacancy_closed"}})
def apply_vacancy(vac_id: int, data: ApplyIn, cand: CurrentCandidate, db: DB):
    vac = db.get(Vacancy, vac_id)
    if vac is None:
        raise err(404, "not_found", "Вакансия не найдена")
    try:
        app = flow.apply(db, cand, vac, data.cover_letter)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    return {"id": app.id, "status": app.status}


@router.get("/applications", summary="Мои отклики и их статусы")
def my_applications(cand: CurrentCandidate, db: DB):
    rows = db.scalars(select(Application).where(Application.candidate_id == cand.id)
                      .order_by(Application.created_at.desc())).all()
    return [{"id": a.id, "status": a.status, "cover_letter": a.cover_letter, "employer_comment": a.employer_comment,
             "created_at": a.created_at, "updated_at": a.updated_at, "vacancy": vacancy_out(a.vacancy)} for a in rows]


@router.post("/applications/{app_id}/withdraw", summary="Отозвать отклик", responses=ERRORS_404)
def withdraw_application(app_id: int, cand: CurrentCandidate, db: DB):
    a = db.get(Application, app_id)
    if a is None or a.candidate_id != cand.id:
        raise err(404, "not_found", "Отклик не найден")
    a.status = "withdrawn"
    db.commit()
    return {"id": a.id, "status": a.status}


# ------------------------------------------------------------------------------------------------ tasks


def task_out(sub: TaskSubmission) -> dict:
    t = sub.task
    return {"id": sub.id, "status": sub.status, "score": sub.score, "feedback": sub.feedback, "answer": sub.answer,
            "created_at": sub.created_at,
            "task": {"id": t.id, "title": t.title, "body": t.body, "kind": t.kind,
                     "options": (t.quiz or {}).get("options", []), "skills": t.skills,
                     "company": t.company.name if t.company else "ФСП Талант"}}


@router.get("/tasks", summary="Регулярные задания: текущее и история (новое выдаётся раз в неделю)")
def my_tasks(cand: CurrentCandidate, db: DB):
    tasks.offer_if_due(db, cand)
    rows = db.scalars(select(TaskSubmission).where(TaskSubmission.candidate_id == cand.id)
                      .order_by(TaskSubmission.created_at.desc())).all()
    return [task_out(s) for s in rows]


@router.post("/tasks/{sub_id}/submit", summary="Отправить решение или подход к решению", responses=ERRORS_404)
def submit_task(sub_id: int, data: TaskAnswerIn, cand: CurrentCandidate, db: DB):
    sub = db.get(TaskSubmission, sub_id)
    if sub is None or sub.candidate_id != cand.id:
        raise err(404, "not_found", "Задание не найдено")
    if sub.status != "offered":
        raise err(409, "already_submitted", "Задание уже выполнено или пропущено")
    return task_out(tasks.submit(db, cand, sub, data.answer))


@router.post("/tasks/{sub_id}/skip", summary="Пропустить задание", responses=ERRORS_404)
def skip_task(sub_id: int, cand: CurrentCandidate, db: DB):
    sub = db.get(TaskSubmission, sub_id)
    if sub is None or sub.candidate_id != cand.id:
        raise err(404, "not_found", "Задание не найдено")
    sub.status = "skipped"
    db.commit()
    return task_out(sub)


@router.get("/dashboard", summary="Сводка кабинета кандидата")
def dashboard(cand: CurrentCandidate, db: DB):
    flow.expire_stale(db)
    invs = db.scalars(select(Invitation).where(Invitation.candidate_id == cand.id)).all()
    apps = db.scalars(select(Application).where(Application.candidate_id == cand.id)).all()
    active = db.scalar(select(AssessmentSession).where(AssessmentSession.candidate_id == cand.id,
                                                       AssessmentSession.status == "active"))
    offered = tasks.offer_if_due(db, cand)
    pending_task = offered or db.scalar(select(TaskSubmission).where(TaskSubmission.candidate_id == cand.id,
                                                                     TaskSubmission.status == "offered"))
    steps = [
        {"key": "consent", "title": "Согласие на обработку данных", "done": cand.consent_processing_at is not None},
        {"key": "onboarding", "title": "Опрос по специализации", "done": cand.onboarding_done},
        {"key": "test", "title": "Тест на грейд", "done": cand.grade is not None},
        {"key": "profile", "title": "Профиль и резюме", "done": bool(cand.headline and cand.skills)},
        {"key": "fsp", "title": "Привязка ФСП ID (по желанию)", "done": cand.fsp_id is not None, "optional": True},
        {"key": "publish", "title": "Профиль виден работодателям",
         "done": bool(cand.grade and cand.visible_to_employers and cand.consent_publication_at)},
    ]
    return {
        "profile": profile_out(cand), "steps": steps, "active_session_id": active.id if active else None,
        "invitations": {"new": sum(1 for i in invs if i.status == "sent"),
                        "active": sum(1 for i in invs if i.status in ("sent", "viewed")),
                        "accepted": sum(1 for i in invs if i.status == "accepted"), "total": len(invs)},
        "applications": {"total": len(apps), "active": sum(1 for a in apps if a.status in ("sent", "viewed"))},
        "pending_task": task_out(pending_task) if pending_task else None,
        "experience_public": experience_public(cand),
    }
