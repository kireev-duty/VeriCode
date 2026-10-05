"""Explainable candidate <-> need scoring.

score = Σ weight_k · component_k, every component in [0, 1]. The explanation is the list of contributions
(weight × value) plus explicit negative signals, so the employer sees *why* a candidate is in the shortlist.
Pure functions over plain data: the API and the offline validation (validation/) share this code.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.catalog import GRADE_BY_ID, GRADE_ORDER, SKILL_BY_ID, skill_similarity
from app.modules.nlp import text_similarity

DEFAULT_WEIGHTS = {
    "skills": 0.32,  # coverage of required / desired stack, verified skills count more
    "grade": 0.20,  # category grade vs requested grade
    "test": 0.16,  # how strongly the test result sits inside the band (ability on the needed skills)
    "fsp": 0.05,  # confirmed FSP achievements (additive bonus, no penalty without history); tuned in validation
    "salary": 0.11,  # expectation vs offered range
    "format": 0.08,  # work format and city
    "freshness": 0.05,  # recent test / regular tasks
    "text": 0.03,  # semantic closeness of the need description and the profile
}
COMPONENT_TITLES = {"skills": "Стек", "grade": "Грейд", "test": "Результат теста", "fsp": "Достижения ФСП",
                    "salary": "Зарплата", "format": "Формат и город", "freshness": "Актуальность",
                    "text": "Описание"}
# which component a candidate's decline reason points at (used to adapt per-company weights)
DECLINE_TO_COMPONENT = {"salary": "salary", "stack": "skills", "format": "format", "grade": "grade"}


@dataclass
class NeedSpec:
    specialization: str
    grade: str
    must_skills: list[str]
    nice_skills: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    city: str = ""
    salary_from: int | None = None
    salary_to: int | None = None
    text: str = ""
    require_fsp: bool = False


@dataclass
class CandidateView:
    id: int
    specialization: str | None
    grade: str | None
    theta: float | None
    skill_theta: dict[str, float]
    declared_skills: list[str]
    experience_years: float
    work_formats: list[str]
    city: str
    relocation: bool
    salary_expectation: int | None
    fsp: float  # 0..1 from fsp.scoring
    fsp_reasons: list[str]
    last_activity: datetime | None
    text: str


def _grade_fit(cand_grade: str | None, need_grade: str) -> tuple[float, str | None]:
    if cand_grade is None:
        return 0.0, "нет подтверждённого грейда"
    diff = GRADE_ORDER.index(cand_grade) - GRADE_ORDER.index(need_grade)
    if diff == 0:
        return 1.0, None
    if diff == 1:
        return 0.7, "грейд выше запрошенного"
    if diff == -1:
        return 0.45, "грейд ниже запрошенного"
    return 0.1, "грейд далёк от запрошенного"


def _skill_confidence(skill: str, c: CandidateView, need_grade: str) -> tuple[float, str]:
    """1.0 = verified by the test at the needed level, 0.6 = only declared in the profile."""
    thr = GRADE_BY_ID[need_grade].theta_min if need_grade != "intern" else -1.8
    if skill in c.skill_theta:
        st = c.skill_theta[skill]
        return (1.0 if st >= thr - 0.3 else 0.75), "verified"
    # a related tested skill (e.g. python for django) lends partial confidence
    rel = max((skill_similarity(skill, s) for s in c.skill_theta), default=0)
    if skill in c.declared_skills:
        return max(0.6, 0.6 + 0.3 * rel), "declared"
    return 0.0, "none"


def _coverage(skills: list[str], c: CandidateView, need_grade: str) -> tuple[float, list[tuple[str, float, str]]]:
    if not skills:
        return 1.0, []
    details = []
    pool = set(c.declared_skills) | set(c.skill_theta)
    for s in skills:
        best, how = 0.0, "none"
        conf, kind = _skill_confidence(s, c, need_grade)
        if conf > 0:
            best, how = conf, kind
        else:
            for other in pool:  # partial credit for a close neighbour in the skill graph
                sim = skill_similarity(s, other)
                if sim > 0:
                    oc, _ = _skill_confidence(other, c, need_grade)
                    if sim * oc * 0.8 > best:
                        best, how = sim * oc * 0.8, f"similar:{other}"
        details.append((s, best, how))
    return sum(d[1] for d in details) / len(details), details


def _salary_fit(exp: int | None, lo: int | None, hi: int | None) -> tuple[float, str]:
    if exp is None or hi is None:
        return 0.7, "unknown"
    if exp <= hi:
        return 1.0, "fits"
    if exp <= hi * 1.15:
        return 0.5, "close"
    return 0.1, "above"


def salary_status(exp: int | None, lo: int | None, hi: int | None) -> str:
    """For the employer before sending an invitation: fits / close / above / unknown (no exact number revealed)."""
    return _salary_fit(exp, lo, hi)[1]


def _format_fit(c: CandidateView, n: NeedSpec) -> float:
    if not n.work_formats:
        return 1.0
    if not c.work_formats or set(c.work_formats) & set(n.work_formats):
        fmt = 1.0
    else:
        fmt = 0.3
    if n.city and set(n.work_formats) <= {"office", "hybrid"}:
        if c.city and c.city != n.city and not c.relocation:
            fmt *= 0.5
    return fmt


def _freshness(last: datetime | None, now: datetime) -> float:
    if last is None:
        return 0.2
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    days = max(0.0, (now - last).days)
    return 0.5 ** (days / 90)


def _test_strength(c: CandidateView, n: NeedSpec) -> float:
    if c.theta is None:
        return 0.0
    needed = [s for s in n.must_skills + n.nice_skills if s in c.skill_theta]
    theta = sum(c.skill_theta[s] for s in needed) / len(needed) if needed else c.theta
    thr = GRADE_BY_ID[n.grade].theta_min if n.grade != "intern" else -1.8
    return 1 / (1 + math.exp(-2.2 * (theta - thr)))


def score(c: CandidateView, n: NeedSpec, weights: dict[str, float] | None = None,
          now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_w = sum(w.values())
    w = {k: v / total_w for k, v in w.items()}

    must_cov, must_det = _coverage(n.must_skills, c, n.grade)
    nice_cov, nice_det = _coverage(n.nice_skills, c, n.grade)
    comp = {
        "skills": 0.8 * must_cov + 0.2 * nice_cov if n.nice_skills else must_cov,
        "grade": _grade_fit(c.grade, n.grade)[0],
        "test": _test_strength(c, n),
        "fsp": c.fsp,
        "salary": _salary_fit(c.salary_expectation, n.salary_from, n.salary_to)[0],
        "format": _format_fit(c, n),
        "freshness": _freshness(c.last_activity, now),
        "text": min(1.0, text_similarity(n.text, c.text) * 2.5) if n.text and c.text else 0.0,
    }
    total = sum(w[k] * comp[k] for k in comp)

    chips = []
    verified = [s for s, v, how in must_det + nice_det if how == "verified" and v >= 1.0]
    if verified:
        chips.append({"kind": "positive", "component": "skills",
                      "text": "Подтверждено тестом: " + ", ".join(SKILL_BY_ID[s].title for s in verified[:4]),
                      "impact": round(w["skills"] * comp["skills"], 3)})
    declared = [s for s, v, how in must_det if how == "declared"]
    if declared:
        chips.append({"kind": "neutral", "component": "skills",
                      "text": "Указано в профиле: " + ", ".join(SKILL_BY_ID[s].title for s in declared[:4]),
                      "impact": 0})
    similar = [(s, how.split(":")[1]) for s, v, how in must_det if how.startswith("similar")]
    for s, other in similar[:2]:
        chips.append({"kind": "neutral", "component": "skills",
                      "text": f"{SKILL_BY_ID[s].title} нет, но есть близкий {SKILL_BY_ID[other].title}", "impact": 0})
    missing = [s for s, v, how in must_det if v == 0]
    if missing:
        chips.append({"kind": "negative", "component": "skills",
                      "text": "Нет обязательных: " + ", ".join(SKILL_BY_ID[s].title for s in missing[:4]),
                      "impact": -round(w["skills"] * len(missing) / max(1, len(n.must_skills)), 3)})
    g_val, g_note = _grade_fit(c.grade, n.grade)
    if c.grade:
        chips.append({"kind": "positive" if g_val >= 0.7 else "negative", "component": "grade",
                      "text": f"Грейд {GRADE_BY_ID[c.grade].title} подтверждён тестом"
                              + (f" ({g_note})" if g_note else ""),
                      "impact": round(w["grade"] * g_val, 3)})
    if comp["test"] >= 0.75:
        chips.append({"kind": "positive", "component": "test", "text": "Уверенный результат теста на нужных навыках",
                      "impact": round(w["test"] * comp["test"], 3)})
    if c.fsp > 0:
        chips.append({"kind": "positive", "component": "fsp", "text": "ФСП: " + "; ".join(c.fsp_reasons[:2]),
                      "impact": round(w["fsp"] * c.fsp, 3)})
    sal = salary_status(c.salary_expectation, n.salary_from, n.salary_to)
    if sal == "fits":
        chips.append({"kind": "positive", "component": "salary", "text": "Ожидания в пределах вилки",
                      "impact": round(w["salary"], 3)})
    elif sal in ("close", "above"):
        chips.append({"kind": "negative", "component": "salary",
                      "text": "Ожидания немного выше вилки" if sal == "close" else "Ожидания выше вилки",
                      "impact": -round(w["salary"] * (1 - comp["salary"]), 3)})
    if comp["format"] < 1:
        chips.append({"kind": "negative", "component": "format", "text": "Формат работы или город не совпадают",
                      "impact": -round(w["format"] * (1 - comp["format"]), 3)})
    if comp["freshness"] >= 0.8:
        chips.append({"kind": "positive", "component": "freshness", "text": "Профиль недавно подтверждён активностью",
                      "impact": round(w["freshness"] * comp["freshness"], 3)})
    return {"score": round(total, 4), "components": {k: round(v, 3) for k, v in comp.items()},
            "weights": {k: round(v, 3) for k, v in w.items()}, "chips": chips, "salary_status": sal}


def profile_strength(c: CandidateView, now: datetime | None = None) -> float:
    """Ranking inside a category without a specific need: test ability within the band, FSP, freshness."""
    now = now or datetime.now(UTC)
    if c.theta is None or c.grade is None:
        return 0.0
    idx = GRADE_ORDER.index(c.grade)
    lo = GRADE_BY_ID[c.grade].theta_min if idx > 0 else -2.0
    hi = GRADE_BY_ID[GRADE_ORDER[idx + 1]].theta_min if idx + 1 < len(GRADE_ORDER) else 2.2
    within = min(1.0, max(0.0, (c.theta - lo) / (hi - lo)))
    return round(0.6 * within + 0.25 * c.fsp + 0.15 * _freshness(c.last_activity, now), 4)


def adapt_weights(current: dict[str, float], decline_reason: str, step: float = 0.1, cap: float = 2.0
                  ) -> dict[str, float]:
    """A decline with reason X makes component X matter more for this company (multiplicative, capped)."""
    comp = DECLINE_TO_COMPONENT.get(decline_reason)
    if not comp:
        return current
    base = {**DEFAULT_WEIGHTS, **current}
    base[comp] = min(DEFAULT_WEIGHTS[comp] * cap, base[comp] * (1 + step))
    return base
