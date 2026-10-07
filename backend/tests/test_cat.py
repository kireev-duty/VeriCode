"""Adaptive test engine on simulated candidates with a known ability."""

import random
import statistics

from app.catalog import SPEC_BY_ID, grade_from_theta
from app.modules.assessment import cat
from app.modules.assessment.irt import ItemParams, eap, p_correct, prob_above

BANK = cat.build_bank()
BLUEPRINT = cat.blueprint_for_specialization(SPEC_BY_ID["backend"].core_skills, ["python", "postgresql"], BANK)


def simulate(theta: float, target: str, rng: random.Random) -> tuple[cat.Decision, list[cat.Response]]:
    responses: list[cat.Response] = []
    while True:
        item = cat.select_next(BANK, BLUEPRINT, responses, cat.selection_theta(responses, target), rng)
        assert item is not None
        responses.append(cat.Response(item, rng.random() < float(p_correct(theta, item.params))))
        if cat.should_stop(responses, target):
            return cat.decide(responses, target), responses


def test_eap_moves_with_answers():
    item = ItemParams(1.5, 0.0, 0.0)
    assert eap([(item, True)] * 5)[0] > 0.5 > -0.5 > eap([(item, False)] * 5)[0]
    assert eap([])[1] > eap([(item, True), (item, False)] * 4)[1], "posterior SD shrinks with data"
    assert prob_above([(item, True)] * 8, 0.0) > 0.9


def test_ability_is_recovered():
    rng = random.Random(1)
    errors = []
    for _ in range(60):
        theta = rng.gauss(0.2, 0.9)
        decision, _ = simulate(theta, grade_from_theta(theta), rng)
        errors.append(abs(decision.theta - theta))
    assert statistics.mean(errors) < 0.45


def test_length_family_cap_and_no_repeats():
    rng = random.Random(2)
    for theta in (-1.5, 0.0, 1.5):
        _, responses = simulate(theta, "middle", rng)
        assert cat.MIN_ITEMS <= len(responses) <= cat.MAX_ITEMS
        keys = [r.item.key for r in responses]
        assert len(keys) == len(set(keys))
        per_family: dict[str, int] = {}
        for r in responses:
            per_family[r.item.family] = per_family.get(r.item.family, 0) + 1
        assert max(per_family.values()) <= cat.MAX_PER_FAMILY


def test_declared_grade_does_not_inflate_the_estimate():
    """Same candidates, honest vs one grade higher claim: the mean shift of the estimate stays near zero."""
    rng_people = random.Random(3)
    shifts = []
    for i in range(80):
        theta = rng_people.gauss(0.0, 0.8)
        honest = grade_from_theta(theta)
        inflated = {"intern": "junior", "junior": "middle", "middle": "senior", "senior": "senior"}[honest]
        d1, _ = simulate(theta, honest, random.Random(1000 + i))
        d2, _ = simulate(theta, inflated, random.Random(1000 + i))
        shifts.append(d2.theta - d1.theta)
    assert abs(statistics.mean(shifts)) < 0.15


def test_strong_candidate_confirms_weak_does_not():
    rng = random.Random(4)
    strong = [simulate(1.6, "middle", rng)[0] for _ in range(10)]
    weak = [simulate(-1.2, "middle", rng)[0] for _ in range(10)]
    assert sum(d.grade == "middle" for d in strong) >= 9
    assert all(d.outcome != "upgrade_available" for d in weak)
    assert sum(d.grade is None and d.suggested_grade == "junior" for d in weak) >= 9


def test_flagged_items_leave_the_bank():
    key = BANK[0].key
    assert key not in {it.key for it in cat.build_bank({key: {"status": "flagged"}})}
    ov = cat.build_bank({key: {"a": 2.2, "b": 0.7}})
    assert next(it for it in ov if it.key == key).params.a == 2.2


def test_vacancy_blueprint_follows_vacancy_skills():
    bp = cat.blueprint_for_specialization(SPEC_BY_ID["backend"].core_skills, None, BANK,
                                          vacancy_skills={"postgresql": 0.5, "python": 0.5})
    assert abs(sum(bp.values()) - 1) < 1e-3  # weights are rounded to 4 digits
    top = sorted(bp, key=lambda s: -bp[s])[:2]
    assert set(top) <= {"python", "postgresql", "sql"}


def test_exposure_control_rotates_overused_slots():
    """A slot reported as shown in most sessions is admitted rarely; a fully overexposed pool never stalls a test."""
    rng = random.Random(5)
    first = [cat.select_next(BANK, BLUEPRINT, [], cat.start_theta("middle"), rng) for _ in range(300)]
    top = max({it.key for it in first}, key=lambda k: sum(it.key == k for it in first))
    share_free = sum(it.key == top for it in first) / len(first)
    exposure = {top: 0.95}
    controlled = [cat.select_next(BANK, BLUEPRINT, [], cat.start_theta("middle"), rng, exposure=exposure)
                  for _ in range(300)]
    share_ctl = sum(it.key == top for it in controlled) / len(controlled)
    assert share_ctl < share_free * 0.7
    everything = {it.key: 1.0 for it in BANK}
    assert cat.select_next(BANK, BLUEPRINT, [], 0.0, rng, exposure=everything, r_max=0.01) is not None


def test_exposure_tracker_is_per_specialization_with_warmup():
    tr = cat.ExposureTracker()
    for _ in range(cat.EXPOSURE_WARMUP - 1):
        tr.record("qa", ["a:1", "b:1"])
    assert tr.rates("qa") == {}
    tr.record("qa", ["a:1", "a:1"])
    assert tr.rates("qa") == {"a:1": 1.0, "b:1": (cat.EXPOSURE_WARMUP - 1) / cat.EXPOSURE_WARMUP}
    assert tr.rates("backend") == {}
