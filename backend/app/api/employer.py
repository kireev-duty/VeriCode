import secrets
from collections import Counter
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api.candidate import vacancy_out
from app.api.deps import AUTH_ERRORS, DB, ERRORS_404, CurrentCompany, err
from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID
from app.models import (
    Application,
    CandidateProfile,
    GradeHistory,
    HiringNeed,
    Invitation,
    RegularTask,
    TaskSubmission,
    Vacancy,
)
from app.modules import invitations as flow
from app.modules import nlp
from app.modules.matching import service as matching
from app.modules.matching.scoring import COMPONENT_TITLES, DEFAULT_WEIGHTS, salary_status, score
from app.modules.trust import trust_for

router = APIRouter(prefix="/api/employer", tags=["employer"], responses=AUTH_ERRORS)

Format = Literal["office", "hybrid", "remote"]


class CompanyIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    city: str | None = None
    size: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_telegram: str | None = None
    inn: str | None = Field(None, max_length=12)
    webhook_url: str | None = None
    logo_color: str | None = None


class SalaryRange(BaseModel):
    salary_from: int = Field(gt=0, description="Зарплата от, ₽/мес — обязательна")
    salary_to: int = Field(gt=0, description="Зарплата до, ₽/мес — обязательна")

    @model_validator(mode="after")
    def check_range(self):
        if self.salary_from > self.salary_to:
            raise ValueError("salary_from не может быть больше salary_to")
        return self


class NeedIn(SalaryRange):
    title: str = Field(min_length=2, max_length=200)
    raw_text: str = ""
    team_description: str = ""
    specialization: str
    grade: Literal["intern", "junior", "middle", "senior"]
    must_skills: list[str] = Field(default_factory=list)
    nice_skills: list[str] = Field(default_factory=list)
    work_formats: list[Format] = Field(default_factory=list)
    city: str = ""
    require_fsp: bool = False


class ParseIn(BaseModel):
    text: str = Field(min_length=10, max_length=20000)


class FiltersIn(BaseModel):
    grades: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Навык в профиле или подтверждён тестом")
    verified_skills: list[str] = Field(default_factory=list, description="Только подтверждённые тестом")
    fsp_only: bool = False
    work_formats: list[Format] = Field(default_factory=list)
    city: str = ""
    max_salary: int | None = None
    min_experience: float | None = None
    specializations: list[str] = Field(default_factory=list)


class SearchIn(BaseModel):
    q: str = ""
    filters: FiltersIn = Field(default_factory=FiltersIn)


class PinIn(BaseModel):
    candidate_id: int
    value: bool = True


class InvitePreviewIn(SalaryRange):
    candidate_id: int


class InviteIn(SalaryRange):
    candidate_id: int
    position_title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=20, max_length=4000, description="Персональное описание предложения")
    work_format: Format | Literal[""] = ""
    contact_method: str = Field(min_length=3, max_length=300, description="Как связаться: email, Telegram, телефон")
    need_id: int | None = None
    vacancy_id: int | None = None
    challenge_task_id: int | None = None


class VacancyIn(SalaryRange):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    specialization: str
    grade: Literal["intern", "junior", "middle", "senior"]
    must_skills: list[str] = Field(default_factory=list)
    nice_skills: list[str] = Field(default_factory=list)
    work_formats: list[Format] = Field(default_factory=list)
    city: str = ""
    status: Literal["draft", "published", "closed"] = "published"


class AppStatusIn(BaseModel):
    status: Literal["viewed", "invited", "rejected"]
    comment: str = ""


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20)
    kind: Literal["approach", "quiz"] = "approach"
    specialization: str
    min_grade: Literal["intern", "junior", "middle", "senior"] = "intern"
    skills: list[str] = Field(default_factory=list)
    rubric: list[dict] = Field(default_factory=list, description='[{"point": "...", "keywords": [...], "weight": 1}]')
    quiz: dict = Field(default_factory=dict, description='{"options": [...], "correct": 0}')


def _check_spec(spec: str):
    if spec not in SPEC_BY_ID:
        raise err(400, "bad_specialization", "Неизвестная специализация")


def _clean_skills(xs: list[str]) -> list[str]:
    return [s for s in dict.fromkeys(xs) if s in SKILL_BY_ID]


# ------------------------------------------------------------------------------------------------ company


def company_out(db, c) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "industry": c.industry, "website": c.website,
            "city": c.city, "size": c.size, "contact_name": c.contact_name, "contact_email": c.contact_email,
            "contact_phone": c.contact_phone, "contact_telegram": c.contact_telegram, "inn": c.inn,
            "webhook_url": c.webhook_url, "webhook_secret": c.webhook_secret, "logo_color": c.logo_color,
            "ranking_weights": {**DEFAULT_WEIGHTS, **(c.ranking_weights or {})},
            "quota_left": flow.quota_left(db, c.id), "trust": trust_for(db, c)}


@router.get("/company", summary="Профиль компании и траст-скор")
def get_company(company: CurrentCompany, db: DB):
    return company_out(db, company)


@router.put("/company", summary="Обновить профиль компании")
def update_company(data: CompanyIn, company: CurrentCompany, db: DB):
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(company, k, v)
    if company.webhook_url and not company.webhook_secret:
        company.webhook_secret = secrets.token_hex(16)
    db.commit()
    return company_out(db, company)


# ------------------------------------------------------------------------------------------------ needs & shortlist


def need_out(n: HiringNeed) -> dict:
    return {"id": n.id, "title": n.title, "raw_text": n.raw_text, "team_description": n.team_description,
            "specialization": n.specialization, "specialization_title": SPEC_BY_ID[n.specialization].short,
            "grade": n.grade, "grade_title": GRADE_BY_ID[n.grade].title, "must_skills": n.must_skills,
            "nice_skills": n.nice_skills, "work_formats": n.work_formats, "city": n.city,
            "salary_from": n.salary_from, "salary_to": n.salary_to, "require_fsp": n.require_fsp,
            "pinned": n.pinned, "hidden": n.hidden, "created_at": n.created_at, "updated_at": n.updated_at}


def _own_need(db, company, need_id: int) -> HiringNeed:
    n = db.get(HiringNeed, need_id)
    if n is None or n.company_id != company.id:
        raise err(404, "not_found", "Потребность не найдена")
    return n


@router.post("/needs/parse", summary="Разобрать текстовое описание потребности в структуру (NLP)")
def parse_need(data: ParseIn):
    parsed = nlp.parse_need(data.text)
    parsed["skill_titles"] = {s: SKILL_BY_ID[s].title for s in parsed["must_skills"] + parsed["nice_skills"]}
    return parsed


@router.get("/needs", summary="Мои потребности (сохранённые подборки)")
def list_needs(company: CurrentCompany, db: DB):
    rows = db.scalars(select(HiringNeed).where(HiringNeed.company_id == company.id, HiringNeed.archived.is_(False))
                      .order_by(HiringNeed.updated_at.desc())).all()
    return [need_out(n) for n in rows]


@router.post("/needs", summary="Создать потребность", status_code=201)
def create_need(data: NeedIn, company: CurrentCompany, db: DB):
    _check_spec(data.specialization)
    values = data.model_dump()
    values["must_skills"] = _clean_skills(values["must_skills"])
    values["nice_skills"] = [s for s in _clean_skills(values["nice_skills"]) if s not in values["must_skills"]]
    n = HiringNeed(company_id=company.id, **values)
    db.add(n)
    db.commit()
    return need_out(n)


@router.get("/needs/{need_id}", summary="Потребность", responses=ERRORS_404)
def get_need(need_id: int, company: CurrentCompany, db: DB):
    return need_out(_own_need(db, company, need_id))


@router.put("/needs/{need_id}", summary="Изменить потребность (подборка пересчитается)", responses=ERRORS_404)
def update_need(need_id: int, data: NeedIn, company: CurrentCompany, db: DB):
    _check_spec(data.specialization)
    n = _own_need(db, company, need_id)
    values = data.model_dump()
    values["must_skills"] = _clean_skills(values["must_skills"])
    values["nice_skills"] = [s for s in _clean_skills(values["nice_skills"]) if s not in values["must_skills"]]
    for k, v in values.items():
        setattr(n, k, v)
    db.commit()
    return need_out(n)


@router.delete("/needs/{need_id}", summary="Архивировать потребность", responses=ERRORS_404)
def archive_need(need_id: int, company: CurrentCompany, db: DB):
    n = _own_need(db, company, need_id)
    n.archived = True
    db.commit()
    return {"ok": True}


@router.post("/needs/{need_id}/shortlist", summary="Подборка: рекомендованные категории и кандидаты с объяснением",
             description="Фильтры сужают ту же подборку без её потери; закреплённые кандидаты остаются сверху.",
             responses=ERRORS_404)
def need_shortlist(need_id: int, filters: FiltersIn, company: CurrentCompany, db: DB):
    n = _own_need(db, company, need_id)
    return matching.shortlist(db, company, n, filters.model_dump())


@router.post("/needs/{need_id}/pin", summary="Закрепить / открепить кандидата в подборке", responses=ERRORS_404)
def pin(need_id: int, data: PinIn, company: CurrentCompany, db: DB):
    n = _own_need(db, company, need_id)
    pinned = [x for x in (n.pinned or []) if x != data.candidate_id]
    n.pinned = pinned + [data.candidate_id] if data.value else pinned
    db.commit()
    return need_out(n)


@router.post("/needs/{need_id}/hide", summary="Скрыть / вернуть кандидата в подборке", responses=ERRORS_404)
def hide(need_id: int, data: PinIn, company: CurrentCompany, db: DB):
    n = _own_need(db, company, need_id)
    hidden = [x for x in (n.hidden or []) if x != data.candidate_id]
    n.hidden = hidden + [data.candidate_id] if data.value else hidden
    db.commit()
    return need_out(n)


@router.get("/categories", summary="Категории (специализация × грейд) с числом кандидатов")
def categories(company: CurrentCompany, db: DB):
    return matching.categories_overview(db)


@router.post("/categories/{specialization}/{grade}", summary="Кандидаты категории, ранжированные по силе профиля")
def category(specialization: str, grade: str, filters: FiltersIn, company: CurrentCompany, db: DB):
    _check_spec(specialization)
    if grade not in GRADE_BY_ID:
        raise err(400, "bad_grade", "Неизвестный грейд")
    return matching.browse_category(db, specialization, grade, filters.model_dump())


@router.post("/search", summary="Поиск по банку кандидатов с фильтрами")
def search(data: SearchIn, company: CurrentCompany, db: DB):
    return matching.search_bank(db, data.q, data.filters.model_dump())


@router.get("/candidates/{cand_id}", summary="Карточка кандидата (контакты — только после принятия или отклика)",
            responses=ERRORS_404)
def candidate_card(cand_id: int, company: CurrentCompany, db: DB, need_id: int | None = None):
    c = db.get(CandidateProfile, cand_id)
    if c is None or c.grade is None or not c.visible_to_employers or c.consent_publication_at is None:
        # an applicant stays visible to the company they applied to even if hidden from search
        if c is None or not matching.contacts_open(db, company.id, cand_id):
            raise err(404, "not_found", "Кандидат не найден или скрыл профиль")
    v = matching.candidate_view(c)
    s = score(v, matching.need_spec(_own_need(db, company, need_id))) if need_id and c.grade else None
    out = matching.card(c, v, s)
    out["experience"] = matching.experience_public(c)
    out["about"] = c.about
    out["last_task_at"] = c.last_task_at
    out["task_score"] = c.task_score
    out["test_history"] = [{"grade": h.grade, "reason": h.reason, "created_at": h.created_at}
                           for h in db.scalars(select(GradeHistory).where(GradeHistory.candidate_id == c.id)
                                               .order_by(GradeHistory.created_at.desc()))]
    opened = matching.contacts_open(db, company.id, c.id)
    out["contacts_open"] = opened
    out["contacts"] = ({"full_name": c.full_name, "email": c.contact_email, "phone": c.phone,
                        "telegram": c.telegram} if opened else None)
    invs = db.scalars(select(Invitation).where(Invitation.company_id == company.id, Invitation.candidate_id == c.id)
                      .order_by(Invitation.created_at.desc())).all()
    out["invitations"] = [{"id": i.id, "status": i.status, "position_title": i.position_title,
                           "created_at": i.created_at} for i in invs]
    return out


# ------------------------------------------------------------------------------------------------ invitations


def inv_out(i: Invitation, opened: bool) -> dict:
    c = i.candidate
    return {"id": i.id, "status": i.status, "position_title": i.position_title, "message": i.message,
            "salary_from": i.salary_from, "salary_to": i.salary_to, "work_format": i.work_format,
            "contact_method": i.contact_method, "decline_reason": i.decline_reason,
            "decline_reason_title": flow.DECLINE_REASONS.get(i.decline_reason or "", None),
            "decline_comment": i.decline_comment, "below_expectation": i.below_expectation,
            "match_score": i.match_score, "need_id": i.need_id, "vacancy_id": i.vacancy_id,
            "created_at": i.created_at, "viewed_at": i.viewed_at, "responded_at": i.responded_at,
            "expires_at": i.expires_at,
            "candidate": {"id": c.id, "code": matching.public_code(c), "headline": c.headline, "grade": c.grade,
                          "grade_title": GRADE_BY_ID[c.grade].title if c.grade else None,
                          "specialization": c.specialization,
                          "contacts": {"full_name": c.full_name, "email": c.contact_email, "phone": c.phone,
                                       "telegram": c.telegram} if opened else None}}


@router.post("/invitations/preview", summary="Перед отправкой: попадает ли вилка в ожидания (без раскрытия суммы)",
             responses=ERRORS_404)
def invite_preview(data: InvitePreviewIn, company: CurrentCompany, db: DB):
    c = db.get(CandidateProfile, data.candidate_id)
    if c is None or c.grade is None:
        raise err(404, "not_found", "Кандидат не найден")
    st = salary_status(c.salary_expectation, data.salary_from, data.salary_to)
    below = bool(c.min_salary_for_invites and data.salary_to < c.min_salary_for_invites)
    hints = {"fits": "Вилка соответствует ожиданиям кандидата",
             "close": "Ожидания кандидата немного выше верхней границы (до 15%)",
             "above": "Ожидания кандидата заметно выше вилки — вероятен отказ",
             "unknown": "Кандидат не указал ожидания"}
    return {"salary_status": "below_threshold" if below else st,
            "hint": "Вилка ниже минимального порога кандидата: приглашение будет помечено" if below else hints[st],
            "quota_left": flow.quota_left(db, company.id), "open_to_offers": c.open_to_offers}


@router.post("/invitations", summary="Отправить приглашение кандидату (вилка обязательна)", status_code=201,
             responses={404: {"description": "candidate_unavailable"},
                        409: {"description": "already_invited / not_open"},
                        429: {"description": "quota_exceeded"}})
def send_invitation(data: InviteIn, company: CurrentCompany, db: DB):
    c = db.get(CandidateProfile, data.candidate_id)
    if c is None:
        raise err(404, "candidate_unavailable", "Кандидат не найден")
    payload = data.model_dump()
    if data.need_id:
        n = _own_need(db, company, data.need_id)
        s = score(matching.candidate_view(c), matching.need_spec(n), company.ranking_weights or {})
        payload["match_score"], payload["match_explanation"] = s["score"], s["chips"]
    if data.vacancy_id:
        v = db.get(Vacancy, data.vacancy_id)
        if v is None or v.company_id != company.id:
            raise err(404, "not_found", "Вакансия не найдена")
    if data.challenge_task_id:
        t = db.get(RegularTask, data.challenge_task_id)
        if t is None or t.company_id != company.id:
            raise err(404, "not_found", "Задание не найдено")
    try:
        inv = flow.send_invitation(db, company, c, payload)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    if data.challenge_task_id:  # the challenge goes straight to the candidate's tasks
        exists = db.scalar(select(TaskSubmission).where(TaskSubmission.task_id == data.challenge_task_id,
                                                        TaskSubmission.candidate_id == c.id))
        if not exists:
            db.add(TaskSubmission(task_id=data.challenge_task_id, candidate_id=c.id, status="offered"))
            db.commit()
    return inv_out(inv, False)


@router.get("/invitations", summary="Отправленные приглашения и их статусы")
def list_invitations(company: CurrentCompany, db: DB, status: str | None = None):
    flow.expire_stale(db)
    q = select(Invitation).where(Invitation.company_id == company.id).order_by(Invitation.created_at.desc())
    if status:
        q = q.where(Invitation.status == status)
    return [inv_out(i, i.status == "accepted" or matching.contacts_open(db, company.id, i.candidate_id))
            for i in db.scalars(q)]


@router.post("/invitations/{inv_id}/withdraw", summary="Отозвать приглашение", responses=ERRORS_404)
def withdraw_invitation(inv_id: int, company: CurrentCompany, db: DB):
    i = db.get(Invitation, inv_id)
    if i is None or i.company_id != company.id:
        raise err(404, "not_found", "Приглашение не найдено")
    try:
        flow.withdraw(db, i)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    return inv_out(i, False)


# ------------------------------------------------------------------------------------------------ vacancies


def _own_vacancy(db, company, vac_id: int) -> Vacancy:
    v = db.get(Vacancy, vac_id)
    if v is None or v.company_id != company.id:
        raise err(404, "not_found", "Вакансия не найдена")
    return v


@router.get("/vacancies", summary="Мои вакансии")
def my_vacancies(company: CurrentCompany, db: DB):
    rows = db.scalars(select(Vacancy).where(Vacancy.company_id == company.id).order_by(Vacancy.created_at.desc()))
    out = []
    for v in rows:
        apps = db.scalars(select(Application).where(Application.vacancy_id == v.id)).all()
        out.append({**vacancy_out(v), "applications": len(apps),
                    "new_applications": sum(1 for a in apps if a.status == "sent")})
    return out


@router.post("/vacancies", summary="Опубликовать вакансию", status_code=201)
def create_vacancy(data: VacancyIn, company: CurrentCompany, db: DB):
    _check_spec(data.specialization)
    values = data.model_dump()
    values["must_skills"] = _clean_skills(values["must_skills"])
    values["nice_skills"] = _clean_skills(values["nice_skills"])
    v = Vacancy(company_id=company.id, **values)
    db.add(v)
    db.commit()
    return vacancy_out(v)


@router.put("/vacancies/{vac_id}", summary="Редактировать вакансию", responses=ERRORS_404)
def update_vacancy(vac_id: int, data: VacancyIn, company: CurrentCompany, db: DB):
    _check_spec(data.specialization)
    v = _own_vacancy(db, company, vac_id)
    values = data.model_dump()
    values["must_skills"] = _clean_skills(values["must_skills"])
    values["nice_skills"] = _clean_skills(values["nice_skills"])
    for k, val in values.items():
        setattr(v, k, val)
    db.commit()
    return vacancy_out(v)


@router.get("/vacancies/{vac_id}/applications", summary="Отклики на вакансию (контакты открыты)",
            responses=ERRORS_404)
def vacancy_applications(vac_id: int, company: CurrentCompany, db: DB):
    v = _own_vacancy(db, company, vac_id)
    rows = db.scalars(select(Application).where(Application.vacancy_id == v.id)
                      .order_by(Application.created_at.desc())).all()
    spec = matching.need_spec(v)
    out = []
    for a in rows:
        c = a.candidate
        view = matching.candidate_view(c)
        s = score(view, spec) if c.grade else None
        out.append({"id": a.id, "status": a.status, "cover_letter": a.cover_letter,
                    "employer_comment": a.employer_comment, "created_at": a.created_at,
                    "candidate": {**matching.card(c, view, s),
                                  "contacts": None if a.status == "withdrawn" else
                                  {"full_name": c.full_name, "email": c.contact_email, "phone": c.phone,
                                   "telegram": c.telegram}}})
    out.sort(key=lambda x: -((x["candidate"]["match"] or {}).get("score", 0)))
    return out


@router.post("/applications/{app_id}/status", summary="Сменить статус отклика", responses=ERRORS_404)
def application_status(app_id: int, data: AppStatusIn, company: CurrentCompany, db: DB):
    a = db.get(Application, app_id)
    if a is None or a.vacancy.company_id != company.id:
        raise err(404, "not_found", "Отклик не найден")
    try:
        flow.set_application_status(db, a, data.status, data.comment)
    except flow.FlowError as e:
        raise err(e.status, e.code, e.message) from None
    return {"id": a.id, "status": a.status}


# ------------------------------------------------------------------------------------------------ tasks


@router.get("/tasks", summary="Мои регулярные задания для кандидатов")
def my_tasks(company: CurrentCompany, db: DB):
    rows = db.scalars(select(RegularTask).where(RegularTask.company_id == company.id)).all()
    out = []
    for t in rows:
        subs = db.scalars(select(TaskSubmission).where(TaskSubmission.task_id == t.id)).all()
        done = [s for s in subs if s.status == "submitted"]
        out.append({"id": t.id, "title": t.title, "body": t.body, "kind": t.kind, "specialization": t.specialization,
                    "min_grade": t.min_grade, "skills": t.skills, "rubric": t.rubric, "active": t.active,
                    "offered": len(subs), "submitted": len(done),
                    "avg_score": round(sum(s.score or 0 for s in done) / len(done), 2) if done else None})
    return out


@router.post("/tasks", summary="Создать регулярное задание", status_code=201)
def create_task(data: TaskIn, company: CurrentCompany, db: DB):
    _check_spec(data.specialization)
    t = RegularTask(company_id=company.id, **data.model_dump())
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.get("/tasks/{task_id}/submissions", summary="Решения кандидатов (анонимно)", responses=ERRORS_404)
def task_submissions(task_id: int, company: CurrentCompany, db: DB):
    t = db.get(RegularTask, task_id)
    if t is None or t.company_id != company.id:
        raise err(404, "not_found", "Задание не найдено")
    subs = db.scalars(select(TaskSubmission).where(TaskSubmission.task_id == t.id,
                                                   TaskSubmission.status == "submitted")).all()
    return [{"id": s.id, "candidate_id": s.candidate_id,
             "candidate_code": matching.public_code(db.get(CandidateProfile, s.candidate_id)),
             "answer": s.answer, "score": s.score, "feedback": s.feedback, "created_at": s.created_at} for s in subs]


# ------------------------------------------------------------------------------------------------ analytics


@router.get("/analytics", summary="Воронка приглашений, причины отказов и адаптация весов ранжирования")
def analytics(company: CurrentCompany, db: DB):
    invs = db.scalars(select(Invitation).where(Invitation.company_id == company.id)).all()
    st = Counter(i.status for i in invs)
    reasons = Counter(i.decline_reason for i in invs if i.decline_reason)
    responded = [i for i in invs if i.responded_at]
    hours = [((i.responded_at - i.created_at).total_seconds() / 3600) for i in responded]
    weights = {**DEFAULT_WEIGHTS, **(company.ranking_weights or {})}
    return {
        "funnel": {"sent": len(invs), "viewed": sum(1 for i in invs if i.viewed_at), "accepted": st.get("accepted", 0),
                   "declined": st.get("declined", 0), "expired": st.get("expired", 0),
                   "withdrawn": st.get("withdrawn", 0)},
        "acceptance_rate": round(st.get("accepted", 0) / len(responded), 3) if responded else None,
        "median_response_hours": round(sorted(hours)[len(hours) // 2], 1) if hours else None,
        "decline_reasons": [{"reason": r, "title": flow.DECLINE_REASONS[r], "count": n} for r, n in reasons.most_common()],
        "weights": [{"component": k, "title": COMPONENT_TITLES[k], "default": DEFAULT_WEIGHTS[k], "current": round(v, 3)}
                    for k, v in weights.items()],
    }
