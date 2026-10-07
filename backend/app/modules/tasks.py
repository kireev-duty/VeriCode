"""Regular short tasks: once a week a candidate gets a task from an employer of a matching category.

"approach" tasks are graded by a transparent rubric (key points with synonyms); with an LLM configured a point also
counts when the answer covers it in other words and the model cites a quote that is really in the answer.
"quiz" tasks are auto-checked.
The score feeds the profile freshness index shown to employers ("подтверждён активностью N дней назад").
"""

import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import GRADE_ORDER
from app.core.db import utcnow
from app.models import CandidateProfile, RegularTask, TaskSubmission
from app.modules import llm

OFFER_EVERY_DAYS = 7
SCORE_EMA = 0.5


def _aware(dt):
    from datetime import UTC
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def offer_if_due(db: Session, cand: CandidateProfile) -> TaskSubmission | None:
    if not cand.specialization or not cand.grade:
        return None
    last = db.scalar(select(TaskSubmission).where(TaskSubmission.candidate_id == cand.id)
                     .order_by(TaskSubmission.created_at.desc()))
    if last and (last.status == "offered" or _aware(last.created_at) > utcnow() - timedelta(days=OFFER_EVERY_DAYS)):
        return None
    done = set(db.scalars(select(TaskSubmission.task_id).where(TaskSubmission.candidate_id == cand.id)))
    level = GRADE_ORDER.index(cand.grade)
    tasks = [t for t in db.scalars(select(RegularTask).where(RegularTask.active.is_(True),
                                                             RegularTask.specialization == cand.specialization))
             if t.id not in done and GRADE_ORDER.index(t.min_grade) <= level]
    if not tasks:
        return None
    # prefer tasks that match the candidate's declared stack
    stack = {s["id"] for s in cand.skills or [] if isinstance(s, dict)}
    tasks.sort(key=lambda t: (-len(stack & set(t.skills)), t.id))
    sub = TaskSubmission(task_id=tasks[0].id, candidate_id=cand.id, status="offered")
    db.add(sub)
    db.commit()
    return sub


def grade_answer(task: RegularTask, answer: str) -> tuple[float, list[dict]]:
    if task.kind == "quiz":
        try:
            ok = int(answer) == int(task.quiz.get("correct", -1))
        except ValueError:
            ok = False
        return (1.0 if ok else 0.0), [{"point": "Верный вариант", "hit": ok}]
    text = answer.lower().replace("ё", "е")
    semantic = llm.grade_approach(f"{task.title}\n{task.body}", [p["point"] for p in task.rubric], answer)
    feedback, total, got = [], 0.0, 0.0
    for i, p in enumerate(task.rubric):
        w = float(p.get("weight", 1))
        hit = any(re.search(rf"\b{re.escape(k.lower())}", text) for k in p.get("keywords", []))
        by_llm = bool(semantic and semantic[i] and not hit)
        total += w
        got += w if hit or by_llm else 0
        feedback.append({"point": p["point"], "hit": hit or by_llm, "by": "llm" if by_llm else "rules"})
    score = got / total if total else 0.0
    if len(text.strip()) < 80:  # a one-liner is not an approach
        score *= 0.5
    return round(score, 2), feedback


def submit(db: Session, cand: CandidateProfile, sub: TaskSubmission, answer: str) -> TaskSubmission:
    score, feedback = grade_answer(sub.task, answer)
    sub.answer, sub.score, sub.feedback, sub.status = answer, score, feedback, "submitted"
    cand.last_task_at = utcnow()
    cand.task_score = round(SCORE_EMA * score + (1 - SCORE_EMA) * (cand.task_score or score), 3)
    db.commit()
    return sub
