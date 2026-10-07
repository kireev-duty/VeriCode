"""Assessment use-cases: eligibility (grade-change policy), sessions, answering, finishing, leak detection."""

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog import GRADE_BY_ID, GRADES, SPEC_BY_ID, grade_index
from app.core.config import settings
from app.core.db import utcnow
from app.models import (
    AssessmentItem,
    AssessmentSession,
    CandidateProfile,
    GradeHistory,
    ItemFamilyStat,
    Vacancy,
)
from app.modules.assessment import cat, leak
from app.modules.assessment.families import REGISTRY, check
from app.modules.assessment.irt import p_correct

TIME_GRACE_S = 15
UPGRADE_WINDOW_DAYS = 7


class AssessmentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------------------------------------ bank


def ensure_item_stats(db: Session) -> None:
    """Creates calibration rows for new item slots. Several workers may start at once: a lost race is fine."""
    existing = set(db.scalars(select(ItemFamilyStat.item_key)))
    for fam in REGISTRY.values():
        for tier, t in fam.tiers.items():
            key = fam.item_key(tier)
            if key not in existing:
                db.add(ItemFamilyStat(item_key=key, a=t.a, b=t.b))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def load_bank(db: Session) -> list[cat.BankItem]:
    overrides = {s.item_key: {"a": s.a, "b": s.b, "status": s.status} for s in db.scalars(select(ItemFamilyStat))}
    return cat.build_bank(overrides)


def exposure_rates(db: Session, specialization: str) -> dict[str, float]:
    """Share of test sessions of the specialization that showed each slot (a key appears at most once per session).
    Empty during warm-up: the control needs enough sessions to tell an overused slot from noise."""
    sessions = db.scalar(select(func.count()).select_from(AssessmentSession)
                         .where(AssessmentSession.specialization == specialization)) or 0
    if sessions < cat.EXPOSURE_WARMUP:
        return {}
    rows = db.execute(select(AssessmentItem.item_key, func.count())
                      .join(AssessmentSession, AssessmentSession.id == AssessmentItem.session_id)
                      .where(AssessmentSession.specialization == specialization)
                      .group_by(AssessmentItem.item_key))
    return {key: n / sessions for key, n in rows}


def _as_aware(dt):
    if dt is not None and dt.tzinfo is None:
        from datetime import UTC
        return dt.replace(tzinfo=UTC)
    return dt


# ------------------------------------------------------------------------------------------------ policy


def eligibility(db: Session, cand: CandidateProfile) -> dict:
    """Which grades the candidate may be tested on right now, and why not otherwise.

    Policy:
      * the first category: any grade; after a failed attempt a lower grade is available immediately;
      * repeating the same grade after a failed attempt: not earlier than SAME_GRADE_RETRY days;
      * changing a confirmed grade (up or down): not more often than once per GRADE_CHANGE_COOLDOWN days;
      * exception: after a confident result ("upgrade_available") the next grade is open for 7 days.
    """
    now = utcnow()
    sessions = list(db.scalars(select(AssessmentSession).where(
        AssessmentSession.candidate_id == cand.id).order_by(AssessmentSession.created_at.desc())))
    active = next((s for s in sessions if s.status == "active"), None)
    finished = [s for s in sessions if s.status == "finished"]
    last = finished[0] if finished else None

    changed_at = _as_aware(cand.grade_changed_at or cand.grade_confirmed_at)
    cooldown_until = changed_at + timedelta(days=settings.grade_change_cooldown_days) if changed_at else None

    grades = []
    for g in GRADES:
        allowed, reason, available_from = True, "", None
        failed_same = next((s for s in finished if s.target_grade == g.id and s.outcome == "not_confirmed"), None)
        retry_until = (_as_aware(failed_same.finished_at) + timedelta(days=settings.same_grade_retry_days)
                       if failed_same else None)
        if cand.grade is None:
            if retry_until and retry_until > now:
                allowed, reason, available_from = False, "Повторная попытка на этот грейд позже", retry_until
        elif g.id == cand.grade:
            last_same = next((s for s in finished if s.target_grade == g.id), None)
            refresh_until = (_as_aware(last_same.finished_at) + timedelta(days=settings.same_grade_retry_days)
                             if last_same else None)
            if refresh_until and refresh_until > now:
                allowed, reason, available_from = False, "Грейд подтверждён недавно", refresh_until
        else:
            in_window = (last is not None and last.outcome == "upgrade_available"
                         and last.result_grade == cand.grade
                         and grade_index(g.id) == grade_index(cand.grade) + 1
                         and _as_aware(last.finished_at) + timedelta(days=UPGRADE_WINDOW_DAYS) > now)
            if not in_window and cooldown_until and cooldown_until > now:
                allowed, reason, available_from = False, "Смена грейда не чаще раза в 90 дней", cooldown_until
            elif retry_until and retry_until > now:
                allowed, reason, available_from = False, "Повторная попытка на этот грейд позже", retry_until
        grades.append({"grade": g.id, "title": g.title, "allowed": allowed, "reason": reason,
                       "available_from": available_from.isoformat() if available_from else None})

    suggested = None
    if last and last.outcome == "not_confirmed" and cand.grade is None:
        idx = grade_index(last.target_grade)
        suggested = GRADES[idx - 1].id if idx > 0 else None
    elif last and last.outcome == "upgrade_available":
        idx = grade_index(last.target_grade)
        suggested = GRADES[idx + 1].id if idx + 1 < len(GRADES) else None
    return {"grades": grades, "active_session_id": active.id if active else None, "suggested_grade": suggested,
            "current_grade": cand.grade, "cooldown_until": cooldown_until.isoformat() if cooldown_until else None}


# ------------------------------------------------------------------------------------------------ sessions


def _responses(session: AssessmentSession, bank_by_key: dict[str, cat.BankItem]) -> list[cat.Response]:
    out = []
    for it in session.items:
        if it.is_correct is None:
            continue
        bank_item = bank_by_key.get(it.item_key) or cat.BankItem(
            it.item_key, it.item_key.split(":")[0], int(it.item_key.split(":")[1]), it.skill,
            cat.ItemParams(it.a, it.b, 0.0), it.time_limit_s)
        # parameters are frozen at the moment the item was shown
        out.append(cat.Response(cat.BankItem(bank_item.key, bank_item.family, bank_item.tier, bank_item.skill,
                                             cat.ItemParams(it.a, it.b, bank_item.params.c), bank_item.time_s),
                                bool(it.is_correct)))
    return out


def _add_item(db: Session, session: AssessmentSession, bank: list[cat.BankItem]) -> AssessmentItem | None:
    bank_by_key = {b.key: b for b in bank}
    responses = _responses(session, bank_by_key)
    rng = random.Random(session.seed * 1000 + len(session.items))
    nxt = cat.select_next(bank, session.blueprint, responses, cat.selection_theta(responses, session.target_grade),
                          rng, exclude_keys={i.item_key for i in session.items},
                          exposure=exposure_rates(db, session.specialization))
    if nxt is None:
        return None
    item_seed = random.Random(session.seed + 7919 * (len(session.items) + 1)).randrange(1 << 30)
    inst = REGISTRY[nxt.family].generate(random.Random(item_seed), nxt.tier)
    item = AssessmentItem(session_id=session.id, position=len(session.items) + 1, item_key=nxt.key, skill=nxt.skill,
                          seed=item_seed, a=nxt.params.a, b=nxt.params.b, payload=inst.payload(),
                          answer={**inst.answer_key(), "kind": inst.kind}, time_limit_s=nxt.time_s)
    session.items.append(item)
    stat = db.get(ItemFamilyStat, nxt.key)
    if stat:
        stat.exposures += 1
    return item


def vacancy_blueprint(db: Session, vacancy_id: int) -> tuple[dict[str, float], Vacancy]:
    vac = db.get(Vacancy, vacancy_id)
    if not vac:
        raise AssessmentError("not_found", "Вакансия не найдена")
    raw: dict[str, float] = {}
    for s in vac.must_skills:
        raw[s] = raw.get(s, 0) + 1.0
    for s in vac.nice_skills:
        raw[s] = raw.get(s, 0) + 0.4
    return raw, vac


def build_blueprint(db: Session, specialization: str, stack: list[str] | None,
                    vacancy_id: int | None = None) -> dict[str, float]:
    bank = load_bank(db)
    spec = SPEC_BY_ID[specialization]
    vac_skills = None
    if vacancy_id:
        raw, _ = vacancy_blueprint(db, vacancy_id)
        total = sum(raw.values()) or 1
        vac_skills = {k: v / total for k, v in raw.items()}
    return cat.blueprint_for_specialization(spec.core_skills, stack, bank, vac_skills)


def start_session(db: Session, cand: CandidateProfile, target_grade: str, vacancy_id: int | None = None
                  ) -> AssessmentSession:
    if not cand.onboarding_done or not cand.specialization:
        raise AssessmentError("onboarding_required", "Сначала пройдите опрос по специализации")
    if target_grade not in GRADE_BY_ID:
        raise AssessmentError("bad_grade", "Неизвестный грейд")
    elig = eligibility(db, cand)
    if elig["active_session_id"]:
        return db.get(AssessmentSession, elig["active_session_id"])
    rule = next(g for g in elig["grades"] if g["grade"] == target_grade)
    if not rule["allowed"]:
        raise AssessmentError("cooldown", f"{rule['reason']} (доступно с {rule['available_from'][:10]})")
    stack = [s["id"] for s in cand.skills if isinstance(s, dict)] if cand.skills else None
    session = AssessmentSession(candidate_id=cand.id, specialization=cand.specialization, target_grade=target_grade,
                                blueprint=build_blueprint(db, cand.specialization, stack, vacancy_id),
                                vacancy_id=vacancy_id, seed=random.SystemRandom().randrange(1 << 30),
                                prior_mean=0.0, theta=cat.start_theta(target_grade),
                                flags={"express": True} if cand.user.is_demo else {})
    db.add(session)
    db.flush()
    _add_item(db, session, load_bank(db))
    db.commit()
    db.refresh(session)
    return session


def current_item(session: AssessmentSession) -> AssessmentItem | None:
    pending = [i for i in session.items if i.is_correct is None]
    return pending[-1] if pending else None


def answer(db: Session, session: AssessmentSession, item_id: int, response, signals: dict | None) -> dict:
    if session.status != "active":
        raise AssessmentError("finished", "Тест уже завершён")
    item = current_item(session)
    if item is None or item.id != item_id:
        raise AssessmentError("stale_item", "Ответ на это задание уже принят или задание не текущее")
    now = utcnow()
    elapsed = (now - _as_aware(item.shown_at)).total_seconds()
    timed_out = elapsed > item.time_limit_s + TIME_GRACE_S
    item.response = {"value": response}
    item.answered_at = now
    item.is_correct = (not timed_out) and check(item.answer["kind"], item.answer, response)
    item.signals = {**(signals or {}), "elapsed_s": round(elapsed, 1), "timed_out": timed_out}

    bank = load_bank(db)
    responses = _responses(session, {b.key: b for b in bank})
    theta, se = cat.current_estimate(responses)
    session.theta, session.se = round(theta, 3), round(se, 3)
    nxt = None
    if not cat.should_stop(responses, session.target_grade, express=bool((session.flags or {}).get("express"))):
        nxt = _add_item(db, session, bank)
    if nxt is None:
        finish(db, session, responses)
    db.commit()
    return {"correct_hidden": True, "finished": session.status == "finished"}


def finish(db: Session, session: AssessmentSession, responses: list[cat.Response]) -> None:
    d = cat.decide(responses, session.target_grade)
    now = utcnow()
    session.status = "finished"
    session.finished_at = now
    session.theta, session.se = d.theta, d.se
    session.p_target = d.p_target
    session.outcome = d.outcome
    session.result_grade = d.grade
    session.skill_theta = d.skill_theta
    items = session.items
    session.flags = {
        **(session.flags or {}),
        "timeouts": sum(1 for i in items if (i.signals or {}).get("timed_out")),
        "paste_events": sum(int((i.signals or {}).get("paste", 0)) for i in items),
        "blur_events": sum(int((i.signals or {}).get("blur", 0)) for i in items),
        "items": len(items),
        "measured_grade": d.measured_grade,
        "p_up": d.p_up,
        "suggested_grade": d.suggested_grade,
    }

    cand = db.get(CandidateProfile, session.candidate_id)
    previous = cand.grade
    if d.grade is not None:
        if previous and previous != d.grade:
            cand.grade_changed_at = now
        cand.grade = d.grade
        cand.theta, cand.theta_se = d.theta, d.se
        cand.skill_theta = {**(cand.skill_theta or {}), **d.skill_theta}
        cand.grade_confirmed_at = now
        cand.claimed_grade = None
        reason = {"confirmed": "Грейд подтверждён тестом",
                  "upgrade_available": "Грейд подтверждён с запасом: доступен тест на грейд выше"}[d.outcome]
    else:
        if previous is None:  # nothing confirmed yet: keep the claim and the measured ability for the tail
            cand.claimed_grade = session.target_grade
            cand.theta, cand.theta_se = d.theta, d.se
        reason = "Заявленный грейд не подтверждён" + (f", текущий грейд {previous} сохранён" if previous else "")
    db.add(GradeHistory(candidate_id=cand.id, specialization=session.specialization, grade=cand.grade,
                        previous_grade=previous, session_id=session.id, reason=reason))
    update_leak_detector(db, session, d.theta)


def update_leak_detector(db: Session, session: AssessmentSession, theta: float) -> None:
    """A slot whose answers become correct more often than the respondents' ability predicts (relative to the slot's
    own baseline) is flagged and leaves rotation: a sign that it, or the trick to solve it, has leaked."""
    bank = {b.key: b for b in load_bank(db)}
    for it in session.items:
        if it.is_correct is None:
            continue
        stat = db.get(ItemFamilyStat, it.item_key)
        if not stat:
            continue
        c = bank[it.item_key].params.c if it.item_key in bank else 0.0
        expected = float(p_correct(theta, cat.ItemParams(it.a, it.b, c)))
        state = leak.LeakState(n=stat.responses, baseline=stat.residual_baseline or 0.0, cusum=stat.residual_cusum)
        flagged = leak.step(state, float(bool(it.is_correct)) - expected)
        stat.responses = state.n
        stat.correct += int(bool(it.is_correct))
        stat.residual_baseline, stat.residual_cusum = state.baseline, state.cusum
        if flagged and stat.status == "active":
            stat.status = "flagged"
            stat.flagged_at = utcnow()
