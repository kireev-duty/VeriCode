"""Explainable matching score: monotone in what matters, no penalty without FSP, bounded weight adaptation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.modules.matching.scoring import (
    DEFAULT_WEIGHTS,
    CandidateView,
    NeedSpec,
    adapt_weights,
    profile_strength,
    salary_status,
    score,
)

NOW = datetime(2026, 10, 5, tzinfo=UTC)
NEED = NeedSpec(specialization="backend", grade="middle", must_skills=["python", "django", "postgresql"],
                nice_skills=["redis"], work_formats=["remote"], salary_from=220_000, salary_to=300_000,
                text="Python backend Django PostgreSQL")
BASE = CandidateView(
    id=1, specialization="backend", grade="middle", theta=0.6, skill_theta={"python": 0.7, "sql": 0.5},
    declared_skills=["python", "django", "postgresql"], experience_years=3, work_formats=["remote"], city="Казань",
    relocation=False, salary_expectation=250_000, fsp=0.0, fsp_reasons=[], last_activity=NOW - timedelta(days=5),
    text="Python backend developer, Django, PostgreSQL")


def s(c: CandidateView, n: NeedSpec = NEED, **kw) -> float:
    return score(c, n, now=NOW, **kw)["score"]


def test_more_required_skills_score_higher():
    fewer = replace(BASE, declared_skills=["python"])
    assert s(BASE) > s(fewer)
    # django / postgresql get partial credit through close skills (python, sql) and say so
    chips = score(fewer, NEED, now=NOW)["chips"]
    assert any("но есть близкий" in ch["text"] for ch in chips)
    unrelated = replace(BASE, declared_skills=["go"], skill_theta={"go": 0.7})
    chips = score(unrelated, NEED, now=NOW)["chips"]
    assert any(ch["kind"] == "negative" and "Нет обязательных" in ch["text"] for ch in chips)


def test_skill_verified_by_test_beats_declared():
    declared_only = replace(BASE, skill_theta={})
    assert s(BASE) > s(declared_only)


def test_grade_fit_and_test_strength():
    assert s(BASE) > s(replace(BASE, grade="junior", theta=-0.4, skill_theta={"python": -0.4}))
    assert s(replace(BASE, theta=1.0, skill_theta={"python": 1.1, "sql": 0.9})) > s(BASE)


def test_salary_above_range_lowers_score_without_revealing_the_number():
    above = replace(BASE, salary_expectation=420_000)
    assert s(BASE) > s(above)
    assert salary_status(250_000, 220_000, 300_000) == "fits"
    assert salary_status(330_000, 220_000, 300_000) == "close"
    assert salary_status(420_000, 220_000, 300_000) == "above"
    assert all("420" not in ch["text"] for ch in score(above, NEED, now=NOW)["chips"])


def test_no_fsp_history_is_neutral():
    res = score(BASE, NEED, now=NOW)
    assert res["components"]["fsp"] == 0
    assert not any(ch["component"] == "fsp" for ch in res["chips"]), "no negative 'no FSP' signal"
    with_fsp = replace(BASE, fsp=0.8, fsp_reasons=["Призёр, всероссийский уровень"])
    assert s(with_fsp) > s(BASE)
    assert s(with_fsp) - s(BASE) <= DEFAULT_WEIGHTS["fsp"] + 1e-9, "FSP is a bounded bonus, not a gate"


def test_format_mismatch_is_explained():
    office_only = replace(BASE, work_formats=["office"])
    res = score(office_only, NEED, now=NOW)
    assert res["components"]["format"] < 1
    assert any(ch["component"] == "format" and ch["kind"] == "negative" for ch in res["chips"])


def test_weights_are_normalized_and_explained():
    res = score(BASE, NEED, now=NOW)
    assert abs(sum(res["weights"].values()) - 1) < 0.01
    assert 0 <= res["score"] <= 1
    assert all(0 <= v <= 1 for v in res["components"].values())


def test_decline_reason_adapts_weight_with_a_cap():
    w = {}
    for _ in range(50):
        w = adapt_weights(w, "salary")
    assert w["salary"] == DEFAULT_WEIGHTS["salary"] * 2
    assert adapt_weights({}, "other") == {}
    # the adapted weights change the ranking in the expected direction
    cheap, pricey = replace(BASE, salary_expectation=240_000), replace(BASE, salary_expectation=330_000)
    gap_default = s(cheap) - s(pricey)
    gap_adapted = s(cheap, weights=w) - s(pricey, weights=w)
    assert gap_adapted > gap_default > 0


def test_in_category_strength_prefers_stronger_and_fsp():
    assert profile_strength(replace(BASE, theta=0.9), NOW) > profile_strength(BASE, NOW)
    assert profile_strength(replace(BASE, fsp=0.7), NOW) > profile_strength(BASE, NOW)
    assert profile_strength(replace(BASE, grade=None), NOW) == 0


# ------------------------------------------------------------------------------------------------ FSP signal

def _ach(result: str, level: str = "regional", discipline: str = "product", years_ago: float = 0.0):
    from types import SimpleNamespace
    return SimpleNamespace(result_type=result, event_level=level, discipline=discipline, event_name="Кубок",
                           date=NOW - timedelta(days=365.25 * years_ago))


def test_fsp_better_result_scores_higher():
    from app.modules.fsp.scoring import fsp_score
    vals = [fsp_score([_ach(r)], "", NOW)[0] for r in ("participant", "finalist", "prize", "winner")]
    assert vals == sorted(vals) and len(set(vals)) == 4


def test_fsp_no_hierarchy_of_events_or_disciplines():
    from app.modules.fsp.scoring import fsp_score
    regional = fsp_score([_ach("winner", "regional", "drones")], "", NOW)[0]
    federal = fsp_score([_ach("winner", "federal", "algorithmic")], "", NOW)[0]
    assert regional == federal


def test_fsp_participations_are_capped_below_one_prize():
    from app.modules.fsp.scoring import fsp_score
    many_visits = fsp_score([_ach("participant") for _ in range(20)], "", NOW)[0]
    one_prize = fsp_score([_ach("prize")], "", NOW)[0]
    assert many_visits < one_prize


def test_fsp_recent_result_counts_more():
    from app.modules.fsp.scoring import fsp_score
    assert fsp_score([_ach("winner", years_ago=0)], "", NOW)[0] > fsp_score([_ach("winner", years_ago=3)], "", NOW)[0]


def test_unconfirmed_grade_ranks_at_half_strength_and_is_explained():
    unconf = replace(BASE, grade=None, claimed_grade="middle")
    assert 0 < profile_strength(unconf, NOW) < profile_strength(BASE, NOW)
    chips = score(unconf, NEED, now=NOW)["chips"]
    assert any("не подтверждён" in ch["text"] for ch in chips)
    assert s(unconf) < s(BASE)
