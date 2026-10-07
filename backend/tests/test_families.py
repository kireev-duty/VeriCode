"""Item families: deterministic by seed, well-formed, gradeable by their own key, and actually varied."""

import math
import random

import pytest

from app.modules.assessment.families import REGISTRY
from app.modules.assessment.families.base import check

SLOTS = [(fam.id, tier) for fam in REGISTRY.values() for tier in fam.tiers]


@pytest.mark.parametrize(("family_id", "tier"), SLOTS, ids=[f"{f}:{t}" for f, t in SLOTS])
def test_slot_is_deterministic_wellformed_and_varied(family_id, tier):
    fam = REGISTRY[family_id]
    a = fam.generate(random.Random(123), tier)
    b = fam.generate(random.Random(123), tier)
    assert a.payload() == b.payload() and a.answer_key() == b.answer_key()

    seen = set()
    for seed in range(40):
        inst = fam.generate(random.Random(seed), tier)
        assert inst.prompt.strip()
        key = inst.answer_key()
        if inst.kind == "single":
            assert len(inst.options) >= 2
            assert len(set(inst.options)) == len(inst.options), "duplicate options"
            assert 0 <= inst.answer < len(inst.options)
            wrong = (inst.answer + 1) % len(inst.options)
            assert not check(inst.kind, key, wrong)
        elif inst.kind == "number":
            assert math.isfinite(float(inst.answer))
            assert not check(inst.kind, key, float(inst.answer) + inst.tolerance + 1000)
        else:
            assert str(inst.answer).strip()
            assert not check(inst.kind, key, str(inst.answer) + " x")
        assert check(inst.kind, key, inst.answer), "the key must accept its own answer"
        seen.add((inst.prompt, inst.code, tuple(inst.options)))
    # a leaked instance must not cover the slot: dozens of surface variants for every slot
    assert len(seen) >= 10, f"{family_id}:{tier} produced only {len(seen)} distinct instances out of 40"


def test_answer_does_not_leak_into_payload():
    for fam in REGISTRY.values():
        for tier in fam.tiers:
            payload = fam.generate(random.Random(7), tier).payload()
            assert "answer" not in payload and "explanation" not in payload


@pytest.mark.parametrize(("family_id", "tier"), SLOTS, ids=[f"{f}:{t}" for f, t in SLOTS])
def test_two_candidates_rarely_share_an_instance(family_id, tier):
    """P(two candidates get the same instance) = sum of squared instance frequencies; target < 1% for every slot.
    400 draws: the plug-in estimate is >= 1/400, so the bound is checked with a margin for sampling noise."""
    counts: dict[tuple, int] = {}
    for seed in range(400):
        inst = REGISTRY[family_id].generate(random.Random(10_000 + seed), tier)
        key = (inst.prompt, inst.code, tuple(inst.options))
        counts[key] = counts.get(key, 0) + 1
    collision = sum((c / 400) ** 2 for c in counts.values())
    assert collision < 0.012, f"{family_id}:{tier}: P(collision) = {collision:.3f}"
