"""Computerized adaptive testing over the bank of (family, tier) items.

Pure logic without DB access: the API service and the Monte-Carlo validation (validation/) run the same code.

Design choices (see docs/testing.md):
* The declared grade only chooses the *starting point* of item selection. Ability is estimated with the
  population prior N(0, 1) for everyone, so claiming a higher grade cannot inflate the result.
* Content balancing: every next item comes from the skill that lags most behind the blueprint share.
* Exposure control: "randomesque" - a random pick among the top-K most informative items, and at most
  MAX_PER_FAMILY tiers of one family per session.
* Stopping: posterior SD below SE_STOP, or the grade decision is already unambiguous, or MAX_ITEMS.
"""

import random
from dataclasses import dataclass, field
from functools import cache

from app.catalog import GRADE_BY_ID, GRADES, SKILL_SIM, grade_center, grade_from_theta, grade_index
from app.modules.assessment.families import REGISTRY
from app.modules.assessment.families.base import guess_floor
from app.modules.assessment.irt import ItemParams, eap, fisher_info, prob_above

MIN_ITEMS = 10
MAX_ITEMS = 18
SE_STOP = 0.33
RANDOMESQUE_K = 3
MAX_PER_FAMILY = 2
CARRY_MIN_NEW = 5  # a follow-up attempt adds at least this many new items
CONFIRM_P = 0.6  # posterior probability required to confirm a grade (tuned in validation)
SKILL_PRIOR_SD = 0.6


@dataclass(frozen=True)
class BankItem:
    key: str
    family: str
    tier: int
    skill: str
    params: ItemParams
    time_s: int


@dataclass
class Response:
    item: BankItem
    correct: bool


@dataclass
class Decision:
    theta: float
    se: float
    p_target: float
    p_up: float
    outcome: str  # confirmed | upgrade_available | not_confirmed
    grade: str | None  # grade assigned by this session (None if the target was not confirmed)
    measured_grade: str  # grade band of the point estimate, for information
    suggested_grade: str | None  # next test to offer
    skill_theta: dict[str, float] = field(default_factory=dict)


@cache
def _guess_floor(family_id: str, tier: int) -> float:
    sample = REGISTRY[family_id].generate(random.Random(0), tier)
    return guess_floor(sample.kind, len(sample.options))


def build_bank(overrides: dict[str, dict] | None = None) -> list[BankItem]:
    """overrides: item_key -> {"a", "b", "status"} from calibration / leak detector state."""
    overrides = overrides or {}
    bank = []
    for fam in REGISTRY.values():
        for tier, t in fam.tiers.items():
            key = fam.item_key(tier)
            ov = overrides.get(key, {})
            if ov.get("status") in ("retired", "flagged"):  # flagged by the leak detector: out until reviewed
                continue
            c = _guess_floor(fam.id, tier)
            bank.append(BankItem(key, fam.id, tier, fam.skill,
                                 ItemParams(ov.get("a", t.a), ov.get("b", t.b), c), t.time_s))
    return bank


def skills_in_bank(bank: list[BankItem]) -> set[str]:
    return {it.skill for it in bank}


def normalize_blueprint(raw: dict[str, float], bank: list[BankItem]) -> dict[str, float]:
    """Maps requested skills onto skills that have items (via the similarity graph) and normalizes weights."""
    available = skills_in_bank(bank)
    out: dict[str, float] = {}
    for skill, w in raw.items():
        if w <= 0:
            continue
        if skill in available:
            out[skill] = out.get(skill, 0) + w
            continue
        related = sorted(((s, v) for s, v in SKILL_SIM.get(skill, {}).items() if s in available and v >= 0.4),
                         key=lambda x: -x[1])
        if related:
            s, v = related[0]
            out[s] = out.get(s, 0) + w * v
    total = sum(out.values())
    return {k: round(v / total, 4) for k, v in out.items()} if total else {}


def current_estimate(responses: list[Response]) -> tuple[float, float]:
    return eap([(r.item.params, r.correct) for r in responses])


def select_next(bank: list[BankItem], blueprint: dict[str, float], responses: list[Response], theta: float,
                rng: random.Random, exclude_keys: set[str] | None = None) -> BankItem | None:
    used_keys = {r.item.key for r in responses} | (exclude_keys or set())
    fam_count: dict[str, int] = {}
    skill_count: dict[str, int] = {}
    for r in responses:
        fam_count[r.item.family] = fam_count.get(r.item.family, 0) + 1
        skill_count[r.item.skill] = skill_count.get(r.item.skill, 0) + 1

    def eligible(it: BankItem) -> bool:
        return it.key not in used_keys and fam_count.get(it.family, 0) < MAX_PER_FAMILY

    n = len(responses) + 1
    skills = sorted(blueprint, key=lambda s: (-(blueprint[s] * n - skill_count.get(s, 0)), rng.random()))
    for skill in skills + [None]:
        pool = [it for it in bank if eligible(it) and (skill is None or it.skill == skill)]
        if skill is None:
            pool = [it for it in pool if it.skill in blueprint] or pool
        if pool:
            pool.sort(key=lambda it: -fisher_info(theta, it.params))
            return rng.choice(pool[:RANDOMESQUE_K])
    return None


def start_theta(target_grade: str) -> float:
    return grade_center(target_grade)


def selection_theta(responses: list[Response], target_grade: str) -> float:
    """Point used to pick the next item: starts at the declared grade, then follows the estimate."""
    if not responses:
        return start_theta(target_grade)
    theta, _ = current_estimate(responses)
    w = min(1.0, len(responses) / 4)
    return w * theta + (1 - w) * start_theta(target_grade)


def _thresholds(target_grade: str) -> tuple[float, float | None]:
    idx = grade_index(target_grade)
    thr = GRADE_BY_ID[target_grade].theta_min
    up = GRADES[idx + 1].theta_min if idx + 1 < len(GRADES) else None
    return thr, up


def should_stop(responses: list[Response], target_grade: str, new_count: int | None = None) -> bool:
    """new_count: items added in a follow-up attempt that continues a previous measurement (carry-over).
    Such an attempt adds at least CARRY_MIN_NEW items targeted at the new grade and at most MAX_ITEMS."""
    n = len(responses)
    k = n if new_count is None else new_count
    if k >= MAX_ITEMS:
        return True
    if n < MIN_ITEMS or (new_count is not None and new_count < CARRY_MIN_NEW):
        return False
    pairs = [(r.item.params, r.correct) for r in responses]
    _, se = eap(pairs)
    if se <= SE_STOP:
        return True
    thr, up = _thresholds(target_grade)
    p_t = prob_above(pairs, thr)
    p_u = prob_above(pairs, up) if up is not None else 0.0
    return p_t <= 0.03 or (p_t >= 0.97 and p_u <= 0.1)


def decide(responses: list[Response], target_grade: str) -> Decision:
    pairs = [(r.item.params, r.correct) for r in responses]
    theta, se = eap(pairs)
    thr, up = _thresholds(target_grade)
    p_t = prob_above(pairs, thr)
    p_u = prob_above(pairs, up) if up is not None else 0.0
    idx = grade_index(target_grade)
    if p_t >= CONFIRM_P:
        outcome = "upgrade_available" if p_u >= CONFIRM_P else "confirmed"
        grade = target_grade
        suggested = GRADES[idx + 1].id if outcome == "upgrade_available" else None
    else:
        outcome, grade = "not_confirmed", None
        suggested = GRADES[idx - 1].id if idx > 0 else None

    by_skill: dict[str, list] = {}
    for r in responses:
        by_skill.setdefault(r.item.skill, []).append((r.item.params, r.correct))
    skill_theta = {s: round(eap(p, prior_mean=theta, prior_sd=SKILL_PRIOR_SD)[0], 2) for s, p in by_skill.items()}
    return Decision(round(theta, 3), round(se, 3), round(p_t, 3), round(p_u, 3), outcome, grade,
                    grade_from_theta(theta), suggested, skill_theta)


def blueprint_for_specialization(spec_core: dict[str, float], stack: list[str] | None, bank: list[BankItem],
                                 vacancy_skills: dict[str, float] | None = None) -> dict[str, float]:
    """Default blueprint = specialization core skills (70%) + candidate's declared stack (30%).
    For a vacancy-driven test the vacancy skills take 70% and the specialization core 30%."""
    raw: dict[str, float] = {}
    if vacancy_skills:
        for s, w in vacancy_skills.items():
            raw[s] = raw.get(s, 0) + 0.7 * w
        for s, w in spec_core.items():
            raw[s] = raw.get(s, 0) + 0.3 * w
    else:
        for s, w in spec_core.items():
            raw[s] = raw.get(s, 0) + 0.7 * w
        if stack:
            for s in stack:
                raw[s] = raw.get(s, 0) + 0.3 / len(stack)
    return normalize_blueprint(raw, bank)
