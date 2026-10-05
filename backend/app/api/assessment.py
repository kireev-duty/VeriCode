import random

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AUTH_ERRORS, DB, ERRORS_404, ERRORS_409, CurrentCandidate, err
from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID
from app.models import AssessmentSession, GradeHistory, ItemFamilyStat
from app.modules import nlp
from app.modules.assessment import cat, service
from app.modules.assessment.families import REGISTRY

router = APIRouter(prefix="/api/assessment", tags=["assessment"])


class StartIn(BaseModel):
    target_grade: str = Field(description="intern | junior | middle | senior")
    vacancy_id: int | None = Field(None, description="Собрать тест по навыкам вакансии")


class AnswerIn(BaseModel):
    item_id: int
    response: str | int | float | None
    signals: dict = Field(default_factory=dict, description="paste, blur — сигналы целостности, не штрафы")


class BlueprintIn(BaseModel):
    specialization: str | None = None
    vacancy_id: int | None = None
    text: str | None = Field(None, description="Текст вакансии, если её нет в системе")
    samples: int = Field(4, ge=0, le=8)


def _item_out(item) -> dict | None:
    if item is None:
        return None
    fam = REGISTRY.get(item.item_key.split(":")[0])
    return {"id": item.id, "position": item.position, "skill": item.skill,
            "skill_title": SKILL_BY_ID[item.skill].title if item.skill in SKILL_BY_ID else item.skill,
            "family_title": fam.title if fam else "", "format": fam.fmt if fam else "",
            "time_limit_s": item.time_limit_s, "shown_at": item.shown_at.isoformat(), **item.payload}


def _session_out(s: AssessmentSession, with_review: bool = False) -> dict:
    out = {
        "id": s.id, "status": s.status, "specialization": s.specialization,
        "specialization_title": SPEC_BY_ID[s.specialization].title,
        "target_grade": s.target_grade, "target_grade_title": GRADE_BY_ID[s.target_grade].title,
        "blueprint": [{"skill": k, "title": SKILL_BY_ID[k].title if k in SKILL_BY_ID else k, "weight": v}
                      for k, v in sorted(s.blueprint.items(), key=lambda x: -x[1])],
        "answered": sum(1 for i in s.items if i.is_correct is not None),
        "min_items": cat.MIN_ITEMS, "max_items": cat.MAX_ITEMS,
        "current_item": _item_out(service.current_item(s)) if s.status == "active" else None,
        "created_at": s.created_at.isoformat(),
    }
    if s.status == "finished":
        out["result"] = {
            "outcome": s.outcome, "grade": s.result_grade, "theta": s.theta, "se": s.se, "p_target": s.p_target,
            "ci90": [round(s.theta - 1.645 * s.se, 2), round(s.theta + 1.645 * s.se, 2)],
            "measured_grade": (s.flags or {}).get("measured_grade"),
            "suggested_grade": (s.flags or {}).get("suggested_grade"),
            "skill_theta": [{"skill": k, "title": SKILL_BY_ID[k].title if k in SKILL_BY_ID else k, "theta": v}
                            for k, v in sorted(s.skill_theta.items(), key=lambda x: -x[1])],
            "flags": s.flags, "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            "correct": sum(1 for i in s.items if i.is_correct),
        }
        if with_review:
            out["review"] = [{**_item_out(i), "response": (i.response or {}).get("value"), "is_correct": i.is_correct,
                              "answer": i.answer.get("answer"), "explanation": i.answer.get("explanation", "")}
                             for i in s.items]
    return out


def _own_session(db, cand, session_id: int) -> AssessmentSession:
    s = db.get(AssessmentSession, session_id)
    if s is None or s.candidate_id != cand.id:
        raise err(status.HTTP_404_NOT_FOUND, "not_found", "Сессия не найдена")
    return s


@router.get("/eligibility", summary="Доступные грейды для теста и ограничения по частоте", responses=AUTH_ERRORS)
def get_eligibility(cand: CurrentCandidate, db: DB):
    return service.eligibility(db, cand)


@router.post("/sessions", summary="Начать тест на грейд (или вернуть активный)",
             responses={**AUTH_ERRORS, **ERRORS_409,
                        400: {"description": "onboarding_required / bad_grade"},
                        429: {"description": "Ограничение частоты (code: cooldown)"}})
def start(data: StartIn, cand: CurrentCandidate, db: DB):
    try:
        s = service.start_session(db, cand, data.target_grade, data.vacancy_id)
    except service.AssessmentError as e:
        code = {"cooldown": 429, "not_found": 404}.get(e.code, 400)
        raise err(code, e.code, e.message) from None
    return _session_out(s)


@router.get("/sessions/{session_id}", summary="Состояние сессии и текущее задание",
            responses={**AUTH_ERRORS, **ERRORS_404})
def get_session(session_id: int, cand: CurrentCandidate, db: DB):
    s = _own_session(db, cand, session_id)
    return _session_out(s, with_review=s.status == "finished")


@router.post("/sessions/{session_id}/answer", summary="Ответ на текущее задание",
             responses={**AUTH_ERRORS, **ERRORS_404,
                        409: {"description": "Задание не текущее или тест завершён (code: stale_item / finished)"}})
def post_answer(session_id: int, data: AnswerIn, cand: CurrentCandidate, db: DB):
    s = _own_session(db, cand, session_id)
    try:
        service.answer(db, s, data.item_id, data.response, data.signals)
    except service.AssessmentError as e:
        raise err(status.HTTP_409_CONFLICT, e.code, e.message) from None
    db.refresh(s)
    return _session_out(s, with_review=s.status == "finished")


@router.get("/history", summary="История тестов и изменений грейда", responses=AUTH_ERRORS)
def history(cand: CurrentCandidate, db: DB):
    sessions = db.scalars(select(AssessmentSession).where(AssessmentSession.candidate_id == cand.id)
                          .order_by(AssessmentSession.created_at.desc())).all()
    grades = db.scalars(select(GradeHistory).where(GradeHistory.candidate_id == cand.id)
                        .order_by(GradeHistory.created_at.desc())).all()
    return {
        "sessions": [_session_out(s) for s in sessions],
        "grade_history": [{"grade": g.grade, "previous_grade": g.previous_grade, "reason": g.reason,
                           "session_id": g.session_id, "created_at": g.created_at.isoformat()} for g in grades],
        "survey": {"industries": cand.industries, "specialization": cand.specialization,
                   "declared_grade": cand.declared_grade, "answers": cand.survey},
    }


@router.post("/blueprint-preview", summary="Как система формирует тест по вакансии: blueprint и примеры заданий",
             description="Публичный эндпоинт для демонстрации механики: навыки вакансии → веса blueprint → "
                         "сгенерированные экземпляры заданий (без ответов). Каждый вызов даёт новые экземпляры.")
def blueprint_preview(data: BlueprintIn, db: DB):
    bank = service.load_bank(db)
    vac_skills, title, spec = None, None, data.specialization
    if data.vacancy_id:
        try:
            raw, vac = service.vacancy_blueprint(db, data.vacancy_id)
        except service.AssessmentError as e:
            raise err(404, e.code, e.message) from None
        spec, title = vac.specialization, vac.title
        total = sum(raw.values()) or 1
        vac_skills = {k: v / total for k, v in raw.items()}
    elif data.text:
        must, nice = nlp.split_must_nice(data.text)
        spec = spec or nlp.detect_specialization(data.text, must + nice) or "backend"
        raw = {s: 1.0 for s in must} | {s: 0.4 for s in nice if s not in must}
        total = sum(raw.values()) or 1
        vac_skills = {k: v / total for k, v in raw.items()} if raw else None
    spec = spec or "backend"
    if spec not in SPEC_BY_ID:
        raise err(400, "bad_specialization", "Неизвестная специализация")
    bp = cat.blueprint_for_specialization(SPEC_BY_ID[spec].core_skills, None, bank, vac_skills)
    rng = random.Random()
    samples = []
    for skill in list(bp)[: data.samples]:
        pool = [b for b in bank if b.skill == skill]
        if pool:
            b = rng.choice(pool)
            inst = REGISTRY[b.family].generate(random.Random(rng.randrange(1 << 30)), b.tier)
            samples.append({"skill": skill, "skill_title": SKILL_BY_ID[skill].title, "family": REGISTRY[b.family].title,
                            "tier": b.tier, "difficulty_b": b.params.b, **inst.payload()})
    return {"vacancy_title": title, "specialization": spec, "detected_skills": list(vac_skills or {}),
            "blueprint": [{"skill": k, "title": SKILL_BY_ID[k].title, "weight": v,
                           "families": len({x.family for x in bank if x.skill == k})} for k, v in bp.items()],
            "samples": samples}


@router.get("/bank", summary="Банк семейств заданий: параметры IRT, экспозиция, статус детектора утечек")
def bank_overview(db: DB):
    stats = {s.item_key: s for s in db.scalars(select(ItemFamilyStat))}
    out = []
    for fam in REGISTRY.values():
        for tier, t in fam.tiers.items():
            key = fam.item_key(tier)
            st = stats.get(key)
            out.append({"key": key, "family": fam.title, "skill": fam.skill, "format": fam.fmt, "tier": tier,
                        "a": st.a if st else t.a, "b": st.b if st else t.b,
                        "exposures": st.exposures if st else 0, "responses": st.responses if st else 0,
                        "p_correct": round(st.correct / st.responses, 3) if st and st.responses else None,
                        "leak_cusum": round(st.residual_cusum, 2) if st else 0,
                        "status": st.status if st else "active"})
    return {"families": len(REGISTRY), "items": out}
