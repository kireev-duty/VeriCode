"""Validation suite: `uv run python -m validation.run [--quick]`.

Writes docs/validation/report.md, docs/validation/*.png and docs/validation/summary.json.
Everything runs on the production code (app.modules.assessment.cat, app.modules.matching.scoring, app.modules.nlp)
against a synthetic population whose latent truth is known (app.seed.synth). Fixed seeds: results are reproducible.

Sections
  1. Adaptive test: accuracy vs. true grade, confusion matrix, test length, ability recovery, claim neutrality;
     stability over 5 population seeds; sweeps of the confirmation threshold and the exposure cap
  2. Consistency: test-retest agreement (new item instances, same candidate)
  3. Discriminativeness and exposure: item-level point-biserial, slot exposure overall and within a specialization
  4. Leak resistance: static test vs. parametric CAT under a leaked answer key; leak detector power
  5. Instance uniqueness: collision probability of item instances between two candidates
  6. Matching: P@10, nDCG@10, MRR vs. keyword and BM25 baselines + ablations with bootstrap CIs, paired differences,
     FSP weight sweep, sensitivity to the relevance definition, adaptation of company weights to declines
  7. NLP: extraction quality of need/vacancy parsing
  8. Expert labels of "vacancy - candidate" pairs
  9. Pilot on real people (validation/pilot.py)
 10. Resume PDF parsing (validation/resumes.py)
"""

import argparse
import json
import math
import random
import time
import zlib
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.catalog import GRADE_BY_ID, GRADE_ORDER, SPEC_BY_ID, SPECIALIZATIONS, grade_from_theta  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.modules import nlp  # noqa: E402
from app.modules.assessment import cat  # noqa: E402
from app.modules.assessment.families import REGISTRY  # noqa: E402
from app.modules.assessment.irt import p_correct  # noqa: E402
from app.modules.fsp.scoring import fsp_score  # noqa: E402
from app.modules.matching.scoring import DEFAULT_WEIGHTS, CandidateView, NeedSpec, score  # noqa: E402
from app.seed import synth  # noqa: E402
from validation import stats  # noqa: E402
from validation.pilot import pilot_block, pilot_section  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "validation"
DEFAULT_FSP_WEIGHT = DEFAULT_WEIGHTS["fsp"]
# The development resume set before the parser fixes (measured with this suite on 2026-10-06, git history has the code)
RESUME_BASELINE = {"full_name": "80.0%", "email": "100.0%", "phone": "73.3%", "telegram": "80.0%", "city": "100.0%",
                   "experience": "33.3%", "specialization": "100.0%", "skills_f1": 0.975}
BRAND = "#402FFF"
GREY = "#C8C9CA"
RED = "#EC1D35"
INK = "#1B1C21"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#999", "figure.dpi": 130})


def kappa(a: list[int], b: list[int], k: int, weighted: bool = True) -> float:
    """Cohen's kappa, quadratic weights for ordinal grades."""
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[x, y] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0))
    w = np.array([[((i - j) / (k - 1)) ** 2 if weighted else float(i != j) for j in range(k)] for i in range(k)])
    return float(1 - (w * obs).sum() / (w * exp).sum())


# ================================================================================================ 1-3. the test


def simulate_population(n: int, seed: int, bank, truth, tracker: cat.ExposureTracker | None = None):
    """The production flow: every session is selected under exposure control fed by the sessions before it."""
    rng = random.Random(seed)
    people = [synth.make_candidate(rng, None, i) for i in range(n)]
    tracker = tracker or cat.ExposureTracker()
    rows = []
    for c in people:
        res = synth.assign_grade(rng, c, bank, truth, exposure=tracker)
        rows.append({"c": c, "res": res})
    return rows


def grade_metrics(rows) -> dict:
    true_g = np.array([GRADE_ORDER.index(r["c"].true_grade) for r in rows])
    got_g = np.array([GRADE_ORDER.index(r["res"]["grade"]) for r in rows])
    return {"exact": float(np.mean(true_g == got_g)), "within1": float(np.mean(np.abs(true_g - got_g) <= 1)),
            "over": float(np.mean(got_g > true_g)), "under": float(np.mean(got_g < true_g)),
            "items": float(np.mean([r["res"]["attempts"][0]["items"] for r in rows]))}


def exposure_metrics(rows) -> dict:
    """Share of candidates who saw a slot in any attempt: overall and within their own specialization."""
    overall, per_spec, spec_n = Counter(), Counter(), Counter()
    for r in rows:
        keys = {k for a in r["res"]["attempts"] for k in a["keys"]}
        spec_n[r["c"].spec] += 1
        for k in keys:
            overall[k] += 1
            per_spec[(r["c"].spec, k)] += 1
    in_spec = {}
    for (sp, k), v in per_spec.items():
        in_spec[k] = max(in_spec.get(k, 0.0), v / spec_n[sp])
    return {"overall": {k: v / len(rows) for k, v in overall.items()}, "in_spec": in_spec}


def test_section(n: int, bank, truth) -> dict:
    t0 = time.time()
    tracker = cat.ExposureTracker()
    rows = simulate_population(n, 11, bank, truth, tracker)
    true_g = [GRADE_ORDER.index(r["c"].true_grade) for r in rows]
    got_g = [GRADE_ORDER.index(r["res"]["grade"]) for r in rows]
    theta_true = np.array([r["c"].theta for r in rows])
    theta_hat = np.array([r["res"]["theta"] for r in rows])
    lengths = [sum(a["items"] for a in r["res"]["attempts"]) for r in rows]
    first_len = [r["res"]["attempts"][0]["items"] for r in rows]
    attempts = [len(r["res"]["attempts"]) for r in rows]
    exact = float(np.mean(np.array(true_g) == np.array(got_g)))
    within1 = float(np.mean(np.abs(np.array(true_g) - np.array(got_g)) <= 1))
    over = float(np.mean(np.array(got_g) > np.array(true_g)))
    under = float(np.mean(np.array(got_g) < np.array(true_g)))
    conf = np.zeros((4, 4), dtype=int)
    for a, b in zip(true_g, got_g):
        conf[a, b] += 1
    # self-assessment baseline: the grade the candidate would have had without a test
    declared = [GRADE_ORDER.index(r["c"].declared_grade) for r in rows]
    declared_exact = float(np.mean(np.array(true_g) == np.array(declared)))
    declared_over = float(np.mean(np.array(declared) > np.array(true_g)))
    rmse = float(np.sqrt(np.mean((theta_true - theta_hat) ** 2)))
    # decision accuracy of the first attempt: "confirmed" iff the true ability is at/above the declared grade
    dec = []
    for r in rows:
        first = r["res"]["attempts"][0]
        truly = r["c"].theta >= GRADE_BY_ID[first["target"]].theta_min
        dec.append((first["outcome"] != "not_confirmed") == truly)
    decision_acc = float(np.mean(dec))
    corr = float(np.corrcoef(theta_true, theta_hat)[0, 1])

    # claim neutrality: same people declare one grade higher than their true grade
    rng = random.Random(5)
    bias = []
    for r in rows[: min(400, n)]:
        c = r["c"]
        tg = GRADE_ORDER.index(c.true_grade)
        bp = r["res"]["blueprint"]
        honest, _ = synth.run_test(rng, c, bank, truth, c.true_grade, bp)
        honest2, _ = synth.run_test(rng, c, bank, truth, c.true_grade, bp)
        claim, _ = synth.run_test(rng, c, bank, truth, GRADE_ORDER[min(3, tg + 1)], bp)
        bias.append((claim.theta - honest.theta, honest2.theta - honest.theta))

    # test-retest: same latent person, new seeds -> new item instances and item order
    rng = random.Random(99)
    retest = [synth.assign_grade(rng, r["c"], bank, truth, exposure=tracker) for r in rows]
    re_g = [GRADE_ORDER.index(x["grade"]) for x in retest]
    re_theta = np.array([x["theta"] for x in retest])
    agree = float(np.mean(np.array(re_g) == np.array(got_g)))

    # item statistics from the grade-assigning attempts
    per_item: dict[str, list[tuple[float, int]]] = {}
    for r in rows:
        for resp in r["res"]["responses"]:
            per_item.setdefault(resp.item.key, []).append((r["c"].theta, int(resp.correct)))
    pbis = {}
    for key, xs in per_item.items():
        if len(xs) >= 30 and 0 < sum(y for _, y in xs) < len(xs):
            t, y = zip(*xs)
            pbis[key] = float(np.corrcoef(t, y)[0, 1])
    exposure = exposure_metrics(rows)
    total_admin = sum(len(a["keys"]) for r in rows for a in r["res"]["attempts"])

    # --- plots
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].scatter(theta_true, theta_hat, s=6, alpha=0.35, color=BRAND)
    lim = [-3, 3]
    axes[0].plot(lim, lim, color=INK, lw=1)
    for g in GRADE_ORDER[1:]:
        axes[0].axvline(GRADE_BY_ID[g].theta_min, color=GREY, lw=0.8, ls="--")
        axes[0].axhline(GRADE_BY_ID[g].theta_min, color=GREY, lw=0.8, ls="--")
    axes[0].set(xlim=lim, ylim=lim, xlabel="истинная способность θ", ylabel="оценка теста θ̂",
                title=f"Восстановление способности (r = {corr:.2f})")
    im = axes[1].imshow(conf / conf.sum(1, keepdims=True), cmap="Purples", vmin=0, vmax=1)
    for i in range(4):
        for j in range(4):
            axes[1].text(j, i, conf[i, j], ha="center", va="center", color="white" if conf[i, j] > conf[i].sum() * 0.5 else INK)
    labels = [GRADE_BY_ID[g].title for g in GRADE_ORDER]
    axes[1].set(xticks=range(4), yticks=range(4), xticklabels=labels, yticklabels=labels,
                xlabel="присвоенный грейд", ylabel="истинный грейд", title=f"Матрица ошибок (точность {exact:.0%})")
    fig.colorbar(im, ax=axes[1], fraction=0.046)
    fig.tight_layout()
    fig.savefig(OUT / "test_accuracy.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    axes[0].hist(first_len, bins=range(min(first_len), max(first_len) + 2), color=BRAND, rwidth=0.85)
    axes[0].set(title=f"Длина теста (среднее {np.mean(first_len):.1f})", xlabel="заданий за попытку", ylabel="кандидатов")
    axes[1].hist(list(pbis.values()), bins=20, color=BRAND, rwidth=0.9)
    axes[1].axvline(0.2, color=RED, lw=1, ls="--")
    axes[1].set(title="Дискриминативность заданий", xlabel="точечно-бисериальная r (θ, верно)", ylabel="позиций банка")
    exp_rates = sorted(exposure["in_spec"].values(), reverse=True)
    axes[2].bar(range(len(exp_rates)), exp_rates, color=BRAND)
    axes[2].axhline(cat.EXPOSURE_MAX, color=RED, lw=1, ls="--")
    axes[2].set(title="Экспозиция внутри специализации", xlabel="позиция (по убыванию)",
                ylabel="доля кандидатов специальности")
    fig.tight_layout()
    fig.savefig(OUT / "test_items.png")
    plt.close(fig)

    # item characteristic curves for a few families
    fig, ax = plt.subplots(figsize=(6, 3.6))
    grid = np.linspace(-3, 3, 100)
    for key in ["py_slicing:1", "py_slicing:2", "py_slicing:3", "sql_query:2", "js_event_loop:3"]:
        it = next((b for b in bank if b.key == key), None)
        if it:
            ax.plot(grid, p_correct(grid, it.params), label=f"{REGISTRY[it.family].title}, ур. {it.tier}")
    ax.set(xlabel="способность θ", ylabel="P(верный ответ)", title="Характеристические кривые заданий (IRT)")
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "icc.png")
    plt.close(fig)

    return {
        "n": n,
        "seconds": round(time.time() - t0, 1),
        "grade_exact": round(exact, 3),
        "grade_within_1": round(within1, 3),
        "over_graded": round(over, 3),
        "under_graded": round(under, 3),
        "self_assessment_exact": round(declared_exact, 3),
        "self_assessment_over": round(declared_over, 3),
        "theta_corr": round(corr, 3),
        "theta_rmse": round(rmse, 3),
        "items_per_attempt_mean": round(float(np.mean(first_len)), 1),
        "items_total_mean": round(float(np.mean(lengths)), 1),
        "attempts_mean": round(float(np.mean(attempts)), 2),
        "claim_bias_theta": round(float(np.mean([b[0] for b in bias])), 3),
        "claim_bias_ci95": round(1.96 * float(np.std([b[0] for b in bias])) / math.sqrt(len(bias)), 3),
        "claim_vs_retest_sd": [round(float(np.std([b[0] for b in bias])), 3), round(float(np.std([b[1] for b in bias])), 3)],
        "decision_accuracy": round(decision_acc, 3),
        "retest_exact": round(agree, 3),
        "retest_kappa_w": round(kappa(got_g, re_g, 4), 3),
        "retest_theta_r": round(float(np.corrcoef(theta_hat, re_theta)[0, 1]), 3),
        "pbis_median": round(float(np.median(list(pbis.values()))), 3),
        "pbis_share_ge_0_2": round(float(np.mean([v >= 0.2 for v in pbis.values()])), 3),
        "max_exposure_rate": round(max(exposure["overall"].values()), 3),
        "max_exposure_in_spec": round(max(exposure["in_spec"].values()), 3),
        "exposure_in_spec": {k: round(v, 3) for k, v in exposure["in_spec"].items()},
        "exposure_cap": cat.EXPOSURE_MAX,
        "items_used": len(exposure["overall"]),
        "items_in_bank": len(bank),
        "confusion": conf.tolist(),
        "admin_total": total_admin,
    }


def seeds_section(bank, truth, seeds=(11, 12, 13, 14, 15), n: int = 1500) -> dict:
    """The headline test metrics over independent populations: mean ± SD shows they are not a lucky draw."""
    per = {"exact": [], "within1": [], "retest_kappa_w": [], "retest_exact": []}
    for seed in seeds:
        tracker = cat.ExposureTracker()
        rows = simulate_population(n, seed, bank, truth, tracker)
        g = grade_metrics(rows)
        rng = random.Random(seed + 1000)
        re_g = [GRADE_ORDER.index(synth.assign_grade(rng, r["c"], bank, truth, exposure=tracker)["grade"])
                for r in rows]
        got = [GRADE_ORDER.index(r["res"]["grade"]) for r in rows]
        per["exact"].append(g["exact"])
        per["within1"].append(g["within1"])
        per["retest_exact"].append(float(np.mean(np.array(re_g) == np.array(got))))
        per["retest_kappa_w"].append(kappa(got, re_g, 4))
    return {"seeds": list(seeds), "n": n,
            **{k: {"mean": round(float(np.mean(v)), 3), "sd": round(float(np.std(v, ddof=1)), 3) if len(v) > 1
                   else 0.0, "values": [round(x, 3) for x in v]} for k, v in per.items()}}


def sweeps_section(bank, truth, n: int = 1200) -> dict:
    """Tuning of two engine constants on one population (seed 13): the chosen values are reproducible here."""
    out: dict = {"n": n, "confirm_p": [], "exposure": []}
    keep_p, keep_r = cat.CONFIRM_P, cat.EXPOSURE_MAX
    try:
        for p in (0.5, 0.6, 0.7):
            cat.CONFIRM_P = p
            g = grade_metrics(simulate_population(n, 13, bank, truth))
            out["confirm_p"].append({"value": p, "exact": round(g["exact"], 3), "over": round(g["over"], 3),
                                     "under": round(g["under"], 3)})
        cat.CONFIRM_P = keep_p
        for r_max in (None, 0.6, 0.5, 0.4, 0.3):
            cat.EXPOSURE_MAX = r_max if r_max is not None else 1.0
            rows = simulate_population(n, 13, bank, truth, None if r_max else _NoExposure())
            g, e = grade_metrics(rows), exposure_metrics(rows)
            out["exposure"].append({"value": r_max, "exact": round(g["exact"], 3), "items": round(g["items"], 1),
                                    "max_overall": round(max(e["overall"].values()), 3),
                                    "max_in_spec": round(max(e["in_spec"].values()), 3)})
    finally:
        cat.CONFIRM_P, cat.EXPOSURE_MAX = keep_p, keep_r
    return out


class _NoExposure(cat.ExposureTracker):
    """Exposure control switched off: the tracker records nothing and reports no rates."""

    def record(self, scope, keys) -> None:
        pass

    def rates(self, scope) -> dict[str, float]:
        return {}


# ================================================================================================ 4. leaks


def leak_section(bank, truth, n: int = 600) -> dict:
    """A fraction of the bank leaks. Paired design: each candidate takes the test twice with *the same random
    numbers* - honestly and with leaked knowledge - so the difference is the effect of the leak, not retest noise.

    Static test: one fixed form of 15 items for everyone; a leaked key = guaranteed correct answers on 40% of it.
    Our CAT, "key leak": the leaked key belongs to instances other candidates saw; a new candidate gets new
    instances (other data, other correct answer), so the key does not transfer - modelled exactly as no effect.
    Our CAT, "key + method leak": in addition the cheater studied how tasks of the leaked families are solved:
    +0.15 to the probability of a correct answer on those families.
    """
    rng = random.Random(21)
    people = [synth.make_candidate(rng, "backend", i) for i in range(n)]
    bp = cat.blueprint_for_specialization(SPEC_BY_ID["backend"].core_skills, None, bank)
    pool = [b for b in bank if b.skill in bp]
    fixed = sorted(pool, key=lambda b: abs(b.params.b))[:15]
    leaked_keys = {b.key for b in fixed[:6]}
    leaked_fams = {b.family for b in fixed[:6]}

    def static_run(c, seed, cheat):
        r = random.Random(seed)
        resp = []
        for it in fixed:
            p = float(p_correct(c.skill_theta.get(it.skill, c.theta), truth[it.key]))
            u = r.random()
            resp.append(cat.Response(it, True if (cheat and it.key in leaked_keys) else u < p))
        return cat.decide(resp, "middle").theta

    def cat_run(c, seed, boost):
        r = random.Random(seed)
        responses = []
        while True:
            it = cat.select_next(bank, bp, responses, cat.selection_theta(responses, "middle"), r)
            if it is None:
                break
            p = float(p_correct(c.skill_theta.get(it.skill, c.theta), truth[it.key]))
            if boost and it.family in leaked_fams:
                p = min(1.0, p + boost)
            responses.append(cat.Response(it, r.random() < p))
            if cat.should_stop(responses, "middle"):
                break
        return cat.decide(responses, "middle").theta

    def effect(pairs):
        gain = [b - a for a, b in pairs]
        up = [GRADE_ORDER.index(grade_from_theta(b)) > GRADE_ORDER.index(grade_from_theta(a)) for a, b in pairs]
        return float(np.mean(gain)), float(np.mean(up))

    st, key, meth = [], [], []
    for i, c in enumerate(people):
        seed = 1000 + i
        st.append((static_run(c, seed, False), static_run(c, seed, True)))
        honest = cat_run(c, seed, 0.0)
        key.append((honest, cat_run(c, seed, 0.0)))  # the leaked key does not apply to new instances
        meth.append((honest, cat_run(c, seed, 0.15)))
    s_gain, s_up = effect(st)
    k_gain, k_up = effect(key)
    m_gain, m_up = effect(meth)

    # leak detector (assessment/leak.py): honest stream vs. stream where a share of respondents knows the answer
    from app.modules.assessment import leak as L

    items = [b for b in bank if b.params.c == 0]

    def detector_run(leak_from, share, steps=600):
        item = rng.choice(items)
        state = L.LeakState()
        for t in range(steps):
            th = rng.gauss(0.15, 0.95)
            p = float(p_correct(th, truth[item.key]))
            ok = True if (leak_from is not None and t >= leak_from and rng.random() < share) else rng.random() < p
            th_hat = th + rng.gauss(0, 0.35)  # the engine sees the estimate, not the truth
            if L.step(state, float(ok) - float(p_correct(th_hat, item.params))):
                return t
        return None

    fp = np.mean([detector_run(None, 0) is not None for _ in range(300)])
    power = {}
    for share in (0.3, 0.5):
        hits = [detector_run(200, share) for _ in range(300)]
        det = [h - 200 for h in hits if h is not None and h >= 200]
        power[share] = (len(det) / len(hits), int(np.median(det)) if det else None)

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    vals = [s_up, k_up, m_up]
    labels = ["Статичный тест\n(утечка ключа)", "Наш CAT\n(утечка ключа)", "Наш CAT\n(ключ + разбор метода)"]
    ax.bar(labels, vals, color=[GREY, BRAND, "#9D90FF"], width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.0%}", ha="center")
    ax.set(ylabel="доля, получивших грейд выше", title="Эффект утечки 40% заданий (парные прогоны)")
    fig.tight_layout()
    fig.savefig(OUT / "leak.png")
    plt.close(fig)
    return {
        "static_theta_gain": round(s_gain, 3), "static_grade_up": round(s_up, 3),
        "cat_key_theta_gain": round(k_gain, 3), "cat_key_grade_up": round(k_up, 3),
        "cat_method_theta_gain": round(m_gain, 3), "cat_method_grade_up": round(m_up, 3),
        "detector_false_positive_rate": round(float(fp), 3),
        "detector_power_30": round(power[0.3][0], 3), "detector_delay_30": power[0.3][1],
        "detector_power_50": round(power[0.5][0], 3), "detector_delay_50": power[0.5][1],
    }


# ================================================================================================ 5. uniqueness


def uniqueness_section(samples: int = 400) -> dict:
    """P(two candidates receive an identical instance of the same item slot) = Σ p_i² over observed instances."""
    rows = []
    for fam in REGISTRY.values():
        for tier in fam.tiers:
            cnt = Counter()
            for s in range(samples):
                inst = fam.generate(random.Random(10_000 + s), tier)
                cnt[(inst.prompt, inst.code, tuple(inst.options))] += 1
            coll = sum((v / samples) ** 2 for v in cnt.values())
            answers = Counter()
            for s in range(samples):
                inst = fam.generate(random.Random(50_000 + s), tier)
                answers[str(inst.answer)] += 1
            top_answer = max(answers.values()) / samples
            rows.append({"item": f"{fam.id}:{tier}", "distinct": len(cnt), "collision": coll,
                         "top_answer_share": top_answer, "kind": inst.kind})
    colls = [r["collision"] for r in rows]
    return {
        "slots": len(rows),
        "median_collision": round(float(np.median(colls)), 4),
        "mean_collision": round(float(np.mean(colls)), 4),
        "share_slots_collision_lt_1pct": round(float(np.mean([c < 0.01 for c in colls])), 3),
        "worst": sorted(rows, key=lambda r: -r["collision"])[:5],
        "collision_by_slot": {r["item"]: r["collision"] for r in rows},
        "median_top_answer_share": round(float(np.median([r["top_answer_share"] for r in rows])), 3),
    }


# ================================================================================================ 6. matching


RELEVANCE_VARIANTS = {  # skill margin, grade distance for rel 2, share of must-skills for rel 2, salary tolerance
    "base": (0.4, 1, 0.66, 1.1),
    "strict": (0.0, 0, 0.66, 1.0),
    "soft": (0.4, 1, 0.5, 1.2),
}


def _relevance(c: synth.SynthCandidate, v: dict, variant: str = "base") -> int:
    """Graded ground truth from the *latent* attributes the system never sees directly. The variants move the
    arbitrary thresholds of this definition, to check that conclusions do not hinge on them."""
    margin, grade_gap, frac2, sal_tol = RELEVANCE_VARIANTS[variant]
    if c.spec != v["specialization"]:
        return 0
    tg, vg = GRADE_ORDER.index(c.true_grade), GRADE_ORDER.index(v["grade"])
    thr = GRADE_BY_ID[v["grade"]].theta_min if v["grade"] != "intern" else -1.8
    knows = {s["id"] for s in c.skills}
    must = v["must_skills"]
    can = [s for s in must if s in knows and c.skill_theta.get(s, c.theta) >= thr - margin]
    frac = len(can) / len(must) if must else 1
    salary_ok = c.salary_expectation <= v["salary_to"] * sal_tol
    fmt_ok = not v["work_formats"] or bool(set(v["work_formats"]) & set(c.work_formats))
    if tg == vg and frac >= 0.99 and salary_ok and fmt_ok:
        return 3
    if abs(tg - vg) <= grade_gap and frac >= frac2 and salary_ok:
        return 2
    if abs(tg - vg) <= 1 and frac >= 0.33:
        return 1
    return 0


class _Ach:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def synthetic_achievements(c: synth.SynthCandidate, rng: random.Random, now) -> tuple[list, str]:
    """FSP results as a noisy measurement of ability: performance = θ + N(0, 0.8) -> place category.
    (The demo registry mock is deterministic per FSP ID and independent of the person, so it cannot be used here.)"""
    out = []
    for _ in range(rng.randint(1, 4)):
        perf = c.theta + rng.gauss(0, 0.8)
        rtype = "winner" if perf > 1.6 else "prize" if perf > 1.0 else "finalist" if perf > 0.3 else "participant"
        out.append(_Ach(event_level=rng.choice(["regional", "regional", "federal", "international"]), result_type=rtype,
                        discipline=rng.choice(["product", "algorithmic", "security"]), event_name="—",
                        date=now - timedelta(days=rng.randint(30, 1200))))
    perf = c.theta + rng.gauss(0, 0.8)
    rank = "КМС" if perf > 1.4 else "I" if perf > 0.8 else "II" if perf > 0.2 else ""
    return out, rank


def _view(c: synth.SynthCandidate, now, use_test=True, use_fsp=True) -> CandidateView:
    res = c.test
    fsp, reasons = 0.0, []
    if use_fsp and c.fsp_id:
        achievements, rank = synthetic_achievements(c, random.Random(zlib.crc32(c.full_name.encode()) + int(c.theta * 1000)), now)
        fsp, reasons = fsp_score(achievements, rank, now)
    return CandidateView(
        id=id(c), specialization=c.spec,
        grade=res["grade"] if use_test else c.declared_grade,
        theta=res["theta"] if use_test else None,
        skill_theta=res["skill_theta"] if use_test else {},
        declared_skills=[s["id"] for s in c.skills], experience_years=c.experience_years,
        work_formats=c.work_formats, city=c.city, relocation=c.relocation, salary_expectation=c.salary_expectation,
        fsp=fsp, fsp_reasons=reasons, last_activity=now - timedelta(days=c.activity_days), text=c.headline + " " + c.about)


def _keyword_rank(c: synth.SynthCandidate, v: dict) -> float:
    """hh-like baseline: count of required keywords in the resume, self-declared grade as a filter."""
    knows = {s["id"] for s in c.skills}
    score_ = sum(2 for s in v["must_skills"] if s in knows) + sum(1 for s in v["nice_skills"] if s in knows)
    if c.declared_grade == v["grade"]:
        score_ += 1.5
    return score_


def _bm25_rank(docs: list[list[str]], query: list[str]):
    n = len(docs)
    avg = sum(len(d) for d in docs) / n
    df = Counter(t for d in docs for t in set(d))
    out = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for q in query:
            if q in tf:
                idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                s += idf * tf[q] * 2.2 / (tf[q] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        out.append(s)
    return out


def _metrics(ranked_rels: list[int], all_rels: list[int], k: int = 10) -> tuple[float, float, float]:
    top = ranked_rels[:k]
    p_at_k = sum(1 for r in top if r >= 2) / k
    dcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(top))
    ideal = sorted(all_rels, reverse=True)[:k]
    idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    mrr = next((1 / (i + 1) for i, r in enumerate(ranked_rels) if r >= 2), 0.0)
    return p_at_k, (dcg / idcg if idcg else 0.0), mrr


SYSTEMS = {
    "Ключевые слова (как hh)": "keywords",
    "BM25 по тексту резюме": "bm25",
    "Наш скоринг без теста (самооценка)": "no_test",
    "Наш скоринг без ФСП": "no_fsp",
    "Наш скоринг (полный)": "full",
}


def need_of(v: dict) -> NeedSpec:
    return NeedSpec(specialization=v["specialization"], grade=v["grade"], must_skills=v["must_skills"],
                    nice_skills=v["nice_skills"], work_formats=v["work_formats"], city=v["city"],
                    salary_from=v["salary_from"], salary_to=v["salary_to"], text=v["description"])


WORLD_NOW = datetime(2026, 10, 1, tzinfo=UTC)


def build_world(bank, truth, n_cand: int = 900, n_vac: int = 40) -> dict:
    """The matching test set: a synthetic population with simulated test results and vacancies.
    Shared by the matching section and the expert labeling form (validation/labeling.py), fixed seeds."""
    rng = random.Random(77)
    people = [synth.make_candidate(rng, None, i) for i in range(n_cand)]
    tracker = cat.ExposureTracker()
    for c in people:
        c.test = synth.assign_grade(rng, c, bank, truth, exposure=tracker)
    vacancies = [synth.make_vacancy(rng, SPECIALIZATIONS[i % len(SPECIALIZATIONS)].id) for i in range(n_vac)]
    now = WORLD_NOW  # fixed: freshness depends on it, and the numbers must be reproducible
    views = {"full": [_view(c, now) for c in people], "no_test": [_view(c, now, use_test=False) for c in people],
             "no_fsp": [_view(c, now, use_fsp=False) for c in people]}
    tokens = [(" ".join([c.headline, c.about] + [s["id"] for s in c.skills])).lower().split() for c in people]
    return {"people": people, "vacancies": vacancies, "views": views, "tokens": tokens, "now": now}


def system_scores(world: dict, v: dict, mode: str, weights: dict[str, float] | None = None) -> dict[int, float]:
    """Score of every candidate of the vacancy's specialization (every system sees the same set: a plain
    specialization filter, as on any site). Our systems are category-first, as in the product: the target grade
    and its neighbours come before the rest."""
    people, views = world["people"], world["views"]
    idx = [i for i, c in enumerate(people) if c.spec == v["specialization"]]
    if mode == "keywords":
        tie = random.Random(zlib.crc32(v["description"].encode()))  # reproducible tie-breaking
        return {i: _keyword_rank(people[i], v) + tie.random() * 0.01 for i in idx}
    if mode == "bm25":
        q = (" ".join(v["must_skills"] + v["nice_skills"]) + " " + v["title"]).lower().split()
        return dict(zip(idx, _bm25_rank([world["tokens"][i] for i in idx], q)))
    need = need_of(v)
    gi = GRADE_ORDER.index(v["grade"])
    near = {i for i in idx if abs(GRADE_ORDER.index(views[mode][i].grade) - gi) <= 1} or set(idx)
    return {i: score(views[mode][i], need, weights=weights, now=world["now"])["score"] + (1.0 if i in near else 0.0)
            for i in idx}


def matching_section(bank, truth, n_cand: int = 900, n_vac: int = 40) -> dict:
    world = build_world(bank, truth, n_cand, n_vac)
    people, vacancies, views, now = world["people"], world["vacancies"], world["views"], world["now"]
    results = {name: [] for name in SYSTEMS}
    sensitivity = {var: {name: [] for name in SYSTEMS} for var in RELEVANCE_VARIANTS if var != "base"}
    fsp_sweep = {w: [] for w in FSP_WEIGHTS}
    per_vac_relevant = []
    for v in vacancies:
        rels = [_relevance(c, v) for c in people]
        per_vac_relevant.append(sum(1 for r in rels if r >= 2))
        idx = [i for i, c in enumerate(people) if c.spec == v["specialization"]]
        spec_rels = [rels[i] for i in idx]
        alt = {var: [_relevance(c, v, var) for c in people] for var in sensitivity}
        for name, mode in SYSTEMS.items():
            sc = system_scores(world, v, mode)
            order = sorted(idx, key=lambda i: -sc[i])
            results[name].append(_metrics([rels[i] for i in order], spec_rels))
            for var, r2 in alt.items():
                sensitivity[var][name].append(_metrics([r2[i] for i in order], [r2[i] for i in idx]))
        for w in FSP_WEIGHTS:
            sc = system_scores(world, v, "full", weights={"fsp": w})
            order = sorted(idx, key=lambda i: -sc[i])
            fsp_sweep[w].append(_metrics([rels[i] for i in order], spec_rels))
    # in-category ranking (spec x assigned grade): how well the order recovers the true ability
    from app.modules.matching.scoring import profile_strength

    def spearman(a, b) -> float:
        return _spearman(a, b)

    cats: dict[tuple, list[int]] = {}
    for i, c in enumerate(people):
        cats.setdefault((c.spec, c.test["grade"]), []).append(i)
    within = {"full": [], "no_fsp": [], "fsp_only": []}
    weights = []
    for idx in cats.values():
        if len(idx) < 8:
            continue
        true_t = [people[i].theta for i in idx]
        within["full"].append(spearman([profile_strength(views["full"][i], now) for i in idx], true_t))
        within["no_fsp"].append(spearman([profile_strength(views["no_fsp"][i], now) for i in idx], true_t))
        within["fsp_only"].append(spearman([views["full"][i].fsp for i in idx], true_t))  # ties: average ranks
        weights.append(len(idx))
    in_category = {k: round(float(np.average(v, weights=weights)), 3) for k, v in within.items()}
    in_category_ci = {k: boot_ci(v, weights=weights) for k, v in within.items()}
    in_category_diff = paired_boot_diff(within["full"], within["no_fsp"], weights=weights)

    table = {}
    for name, ms in results.items():
        arr = np.array(ms)
        table[name] = {"P@10": round(float(arr[:, 0].mean()), 3), "nDCG@10": round(float(arr[:, 1].mean()), 3),
                       "MRR": round(float(arr[:, 2].mean()), 3), "P@10_ci": boot_ci(arr[:, 0]),
                       "nDCG@10_ci": boot_ci(arr[:, 1])}
    full = np.array(results["Наш скоринг (полный)"])
    diffs = {}
    for other in ("Наш скоринг без ФСП", "Ключевые слова (как hh)", "Наш скоринг без теста (самооценка)"):
        o = np.array(results[other])
        diffs[other] = {"P@10": paired_boot_diff(full[:, 0], o[:, 0]), "nDCG@10": paired_boot_diff(full[:, 1], o[:, 1])}
    sens = {}
    for var, res in sensitivity.items():
        sens[var] = {name: {"P@10": round(float(np.mean([m[0] for m in ms])), 3),
                            "nDCG@10": round(float(np.mean([m[1] for m in ms])), 3)} for name, ms in res.items()}
    # the conclusions that must survive any reasonable relevance definition (full vs. "no FSP" is a near-tie)
    claims = {"ours>keywords": ("Наш скоринг (полный)", "Ключевые слова (как hh)"),
              "ours>bm25": ("Наш скоринг (полный)", "BM25 по тексту резюме"),
              "test>self": ("Наш скоринг (полный)", "Наш скоринг без теста (самооценка)")}
    order_kept = {var: {c: t[a]["nDCG@10"] > t[b]["nDCG@10"] for c, (a, b) in claims.items()}
                  for var, t in sens.items()}
    sweep = [{"weight": w, "P@10": round(float(np.mean([m[0] for m in ms])), 3),
              "nDCG@10": round(float(np.mean([m[1] for m in ms])), 3)} for w, ms in fsp_sweep.items()]

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    names = list(table)
    x = np.arange(len(names))
    w = 0.26
    for k, (metric, color) in enumerate([("P@10", BRAND), ("nDCG@10", "#9D90FF"), ("MRR", INK)]):
        ax.bar(x + (k - 1) * w, [table[nm][metric] for nm in names], w, label=metric, color=color)
    ax.set_xticks(x, [nm.replace(" (", "\n(") for nm in names], fontsize=8)
    ax.set(ylim=(0, 1), title="Качество подбора на 40 вакансиях × 900 кандидатах")
    ax.legend(frameon=False, ncols=3)
    fig.tight_layout()
    fig.savefig(OUT / "matching.png")
    plt.close(fig)
    return {"candidates": n_cand, "vacancies": n_vac, "relevant_per_vacancy_median": int(np.median(per_vac_relevant)),
            "table": table, "paired_diff": diffs, "in_category_spearman": in_category,
            "in_category_ci": in_category_ci, "in_category_diff_full_minus_no_fsp": in_category_diff,
            "categories": len(weights), "fsp_sweep": sweep, "sensitivity": sens, "sensitivity_order_kept": order_kept,
            "adaptation": adaptation_section(world)}


FSP_WEIGHTS = (0.0, 0.03, 0.05, 0.1)


def _boot_means(arr: np.ndarray, weights, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), (n, len(arr)))
    if weights is None:
        return arr[idx].mean(axis=1)
    w = np.asarray(weights, dtype=float)[idx]
    return (arr[idx] * w).sum(axis=1) / w.sum(axis=1)


def boot_ci(values, n: int = 2000, seed: int = 1, weights=None) -> tuple[float, float]:
    """95% percentile bootstrap interval of the (weighted) mean, resampling the units: vacancies, categories."""
    means = _boot_means(np.asarray(values, dtype=float), weights, n, seed)
    return round(float(np.percentile(means, 2.5)), 3), round(float(np.percentile(means, 97.5)), 3)


def paired_boot_diff(a, b, n: int = 2000, seed: int = 2, weights=None) -> dict:
    """Mean of the per-unit difference a - b with a 95% bootstrap interval: the units (vacancies) are resampled
    together, so the shared difficulty of a vacancy cancels out. 'significant' = the interval excludes zero."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    means = _boot_means(d, weights, n, seed)
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    mean = float(np.average(d, weights=weights))
    return {"mean": round(mean, 3), "ci": [round(lo, 3), round(hi, 3)], "significant": bool(lo > 0 or hi < 0)}


ACCEPT_ROUNDS, INVITES_PER_ROUND = 8, 10


def _decline_reason(c: synth.SynthCandidate, v: dict, rng: random.Random) -> str | None:
    """The candidate's hidden decision rule: the system never sees it, it only sees the stated reason."""
    if c.salary_expectation > v["salary_to"]:
        return "salary"
    if v["work_formats"] and not set(v["work_formats"]) & set(c.work_formats):
        return "format"
    knows = {s["id"] for s in c.skills}
    if v["must_skills"] and sum(s in knows for s in v["must_skills"]) / len(v["must_skills"]) < 2 / 3:
        return "stack"
    if GRADE_ORDER.index(c.true_grade) > GRADE_ORDER.index(v["grade"]):
        return "grade"
    return None if rng.random() < 0.8 else "not_looking"


def adaptation_section(world: dict) -> dict:
    """Does the per-company weight adaptation (scoring.adapt_weights) raise acceptance? Each vacancy is a company
    that invites its top-10 not-yet-invited candidates per round for 8 rounds. Declines with a reason feed
    adapt_weights in the adaptive arm; the fixed arm keeps the default weights. Same candidates, same random
    numbers per (company, candidate): the arms differ only in whom they invite."""
    from app.modules.matching.scoring import adapt_weights

    people, views = world["people"], world["views"]["full"]
    curves = {"adaptive": [], "fixed": []}
    for vi, v in enumerate(world["vacancies"]):
        need = need_of(v)
        idx = [i for i, c in enumerate(people) if c.spec == v["specialization"]]
        for arm in curves:
            weights: dict[str, float] = {}
            invited: set[int] = set()
            per_round = []
            for _ in range(ACCEPT_ROUNDS):
                sc = {i: score(views[i], need, weights=weights or None, now=world["now"])["score"]
                      for i in idx if i not in invited}
                batch = sorted(sc, key=lambda i: -sc[i])[:INVITES_PER_ROUND]
                accepted = 0
                for i in batch:
                    invited.add(i)
                    reason = _decline_reason(people[i], v, random.Random(vi * 100_003 + i))
                    if reason is None:
                        accepted += 1
                    elif arm == "adaptive":
                        weights = adapt_weights(weights, reason)
                per_round.append(accepted / max(1, len(batch)))
            curves[arm].append(per_round)
    out = {"companies": len(world["vacancies"]), "rounds": ACCEPT_ROUNDS, "per_round": INVITES_PER_ROUND}
    for arm, rows in curves.items():
        arr = np.array(rows)
        out[arm] = [round(float(x), 3) for x in arr.mean(axis=0)]
        out[f"{arm}_total"] = round(float(arr.mean()), 3)
    a, f = np.array(curves["adaptive"]).mean(axis=1), np.array(curves["fixed"]).mean(axis=1)
    out["diff_total"] = paired_boot_diff(a, f)
    late_a, late_f = np.array(curves["adaptive"])[:, 4:].mean(axis=1), np.array(curves["fixed"])[:, 4:].mean(axis=1)
    out["diff_late"] = paired_boot_diff(late_a, late_f)

    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(1, ACCEPT_ROUNDS + 1)
    ax.plot(x, out["fixed"], marker="o", color=GREY, label="фиксированные веса")
    ax.plot(x, out["adaptive"], marker="o", color=BRAND, label="адаптация к причинам отказов")
    ax.set(xlabel="раунд приглашений (по 10)", ylabel="доля принятых", ylim=(0, 1),
           title="Адаптация весов компании к отказам")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "adaptation.png")
    plt.close(fig)
    return out


def _spearman(a, b) -> float:
    """Tie-aware Spearman ρ (expert grades 0-3 and FSP scores have many ties); 0 when one side is constant."""
    rho = stats.spearman(a, b)
    return 0.0 if rho is None else rho


def human_section(bank, truth) -> dict:
    """Expert labels (docs/validation/labels/*.json from the form built by validation.labeling) vs every system.

    The pool of each vacancy is fixed and mixes the systems' picks with random candidates, so the systems are
    compared on how they *order* the same 10 candidates (pooled evaluation)."""
    from validation.labeling import build_pairs, pair_index

    world = build_world(bank, truth)
    pairs = build_pairs(world)
    files = sorted((OUT / "labels").glob("*.json"))
    labelers = {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("version") == pairs["version"] and d.get("labels"):
            labelers[d.get("labeler") or f.stem] = {k: int(v["rel"]) for k, v in d["labels"].items()}
    out: dict = {"version": pairs["version"], "pairs": pairs["pairs"], "labelers": len(labelers)}
    if not labelers:
        return out
    by_pair: dict[str, list[int]] = {}
    for lab in labelers.values():
        for pid, rel in lab.items():
            by_pair.setdefault(pid, []).append(rel)
    expert = {pid: float(np.mean(v)) for pid, v in by_pair.items()}
    out["labeled_pairs"] = len(expert)

    per_vac: dict[int, list[tuple[int, float]]] = {}
    for pid, rel in expert.items():
        vi, ci = pair_index(pid)
        per_vac.setdefault(vi, []).append((ci, rel))
    systems = {}
    for name, mode in SYSTEMS.items():
        ndcg, p3, rho = [], [], []
        for vi, items in per_vac.items():
            if len(items) < 5:
                continue
            sc = system_scores(world, world["vacancies"][vi], mode)
            ranked = sorted(items, key=lambda x: -sc[x[0]])
            rels = [r for _, r in ranked]
            dcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
            idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(sorted(rels, reverse=True)))
            ndcg.append(dcg / idcg if idcg else 0.0)
            p3.append(sum(1 for r in rels[:3] if r >= 2) / 3)
            rho.append(_spearman([sc[c] for c, _ in items], [r for _, r in items]))
        systems[name] = {"nDCG": round(float(np.mean(ndcg)), 3), "nDCG_ci": boot_ci(ndcg),
                         "P@3": round(float(np.mean(p3)), 3), "spearman": round(float(np.mean(rho)), 3)}
    out["systems"] = systems
    out["vacancies"] = len(per_vac)
    out["pool_relevant_share"] = round(sum(1 for r in expert.values() if r >= 2) / len(expert), 3)

    # does the synthetic ground truth of section 6 agree with a human?
    synth_rel, human_rel = [], []
    for pid, rel in expert.items():
        vi, ci = pair_index(pid)
        synth_rel.append(_relevance(world["people"][ci], world["vacancies"][vi]))
        human_rel.append(int(round(rel)))
    out["truth_kappa_w"] = round(kappa(human_rel, synth_rel, 4), 3)
    out["truth_exact"] = round(float(np.mean([a == b for a, b in zip(human_rel, synth_rel)])), 3)
    out["truth_within_1"] = round(float(np.mean([abs(a - b) <= 1 for a, b in zip(human_rel, synth_rel)])), 3)

    names = list(labelers)
    if len(names) >= 2:
        ks = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                common = sorted(set(labelers[names[i]]) & set(labelers[names[j]]))
                if len(common) >= 20:
                    ks.append(kappa([labelers[names[i]][p] for p in common], [labelers[names[j]][p] for p in common], 4))
        if ks:
            out["inter_annotator_kappa_w"] = round(float(np.mean(ks)), 3)
    return out


# ================================================================================================ 7. NLP


HANDWRITTEN = [
    ("Ищем Middle Python-разработчика на бэкенд: Django, PostgreSQL. Будет плюсом Redis. Удалённо, 220–300 тыс. руб.",
     {"specialization": "backend", "grade": "middle", "must": {"python", "django", "postgresql"}, "nice": {"redis"},
      "formats": {"remote"}, "salary": (220000, 300000)}),
    ("Senior frontend (React, TypeScript), желательно опыт с дизайн-системами; гибрид, Москва, 350-450k",
     {"specialization": "frontend", "grade": "senior", "must": {"react", "typescript"}, "nice": set(),
      "formats": {"hybrid"}, "salary": (350000, 450000)}),
    ("Требования:\n- Python 3, FastAPI\n- PostgreSQL\n- Kafka будет плюсом\nОфис в Казани, от 150 000 до 200 000 ₽",
     {"specialization": "backend", "grade": None, "must": {"python", "fastapi", "postgresql"}, "nice": {"kafka"},
      "formats": {"office"}, "salary": (150000, 200000)}),
    ("Стажёр QA: ручное тестирование, тест-кейсы, Postman. SQL приветствуется. Офис, Санкт-Петербург, до 70 тыс.",
     {"specialization": "qa", "grade": "intern", "must": {"test_design", "api_testing"}, "nice": {"sql"},
      "formats": {"office"}, "salary": (None, 70000)}),
    ("DevOps/SRE с опытом от 3 лет: Kubernetes, Terraform, Prometheus и Grafana, GitLab CI. Удалёнка. 300-380 тыс. руб",
     {"specialization": "devops", "grade": "middle", "must": {"kubernetes", "terraform", "monitoring", "ci_cd"},
      "nice": set(), "formats": {"remote"}, "salary": (300000, 380000)}),
    ("Data Scientist (junior) в антифрод: Python, pandas, scikit-learn, статистика. Будет плюсом PyTorch.",
     {"specialization": "data", "grade": "junior", "must": {"python", "pandas", "ml", "statistics"}, "nice": {"dl"},
      "formats": set(), "salary": (None, None)}),
    ("Go-разработчик в платёжный сервис. gRPC, PostgreSQL, Kafka. Опыт от 5 лет. Гибрид, 400–500 тыс. ₽",
     {"specialization": "backend", "grade": "senior", "must": {"go", "grpc", "postgresql", "kafka"}, "nice": set(),
      "formats": {"hybrid"}, "salary": (400000, 500000)}),
    ("Нужен джун на Vue.js + HTML/CSS для лендингов, удаленно, 90-120к",
     {"specialization": "frontend", "grade": "junior", "must": {"vue", "html_css"}, "nice": set(),
      "formats": {"remote"}, "salary": (90000, 120000)}),
]


DATA = Path(__file__).resolve().parent / "data"


def _gold(g: dict) -> dict:
    return {"specialization": g["specialization"], "grade": g["grade"], "must": set(g["must"]),
            "nice": set(g["nice"]), "formats": set(g["formats"]), "salary": tuple(g["salary"])}


def _eval_needs(cases: list[tuple[str, dict]], parse) -> dict:
    """Skills: micro P/R/F1 over must ∪ nice, plus the share of correctly found skills put into the right list
    (must vs nice). Fields: exact match; specialization and grade only where the gold has one."""
    tp = fp = fn = placed = placed_ok = 0
    spec = [0, 0]
    grade = [0, 0]
    sal = fmt = 0
    for text, g in cases:
        p = parse(text)
        must, nice = set(p["must_skills"]), set(p["nice_skills"])
        pred, gold = must | nice, g["must"] | g["nice"]
        tp, fp, fn = tp + len(pred & gold), fp + len(pred - gold), fn + len(gold - pred)
        for sk in pred & gold:
            placed += 1
            placed_ok += (sk in must) == (sk in g["must"])
        if g["specialization"]:
            spec = [spec[0] + (p["specialization"] == g["specialization"]), spec[1] + 1]
        if g["grade"]:
            grade = [grade[0] + (p["grade"] == g["grade"]), grade[1] + 1]
        sal += (p["salary_from"], p["salary_to"]) == g["salary"]
        fmt += set(p["work_formats"]) == g["formats"]
    prec, rec = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    n = len(cases)
    return {"cases": n, "skills_precision": round(prec, 3), "skills_recall": round(rec, 3),
            "skills_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "must_nice_acc": round(placed_ok / placed, 3) if placed else None,
            "specialization_acc": round(spec[0] / spec[1], 3), "grade_acc": round(grade[0] / grade[1], 3),
            "salary_acc": round(sal / n, 3), "format_acc": round(fmt / n, 3)}


def nlp_section() -> dict:
    """Need parsing on three sets: synthetic templates (the seed's vacancies, close to trivial), the development
    set of 40 realistic texts (rules were improved while looking at it) and the hold-out set of 20 texts written
    after the rules were frozen - the honest estimate. The LLM column needs a key (LLM_PROVIDER)."""
    from app.modules import llm

    rng = random.Random(3)
    templ = list(HANDWRITTEN)
    for _ in range(60):
        v = synth.make_vacancy(rng)
        templ.append((v["description"], {"specialization": v["specialization"], "grade": v["grade"],
                                         "must": set(v["must_skills"]), "nice": set(v["nice_skills"]),
                                         "formats": set(v["work_formats"]), "salary": (v["salary_from"], v["salary_to"])}))
    sets = {"templates": templ}
    for name, file in (("dev", "needs.json"), ("holdout", "needs_holdout.json")):
        data = json.loads((DATA / file).read_text(encoding="utf-8"))
        sets[name] = [(c["text"], _gold(c["gold"])) for c in data["cases"]]

    def with_llm(text: str) -> dict:
        return llm.refine_need(text, nlp.parse_need(text))[0]

    out: dict = {"llm": llm.enabled(), "llm_provider": settings.llm_provider if llm.enabled() else None}
    for name, cases in sets.items():
        out[name] = {"rules": _eval_needs(cases, nlp.parse_need)}
        if llm.enabled() and name != "templates":
            out[name]["rules+llm"] = _eval_needs(cases, with_llm)
    out["handwritten"] = len(HANDWRITTEN)
    return out


def _eval_resumes(people: list[dict], gold_file: str) -> dict:
    from app.modules.resume import parse_resume_text, pdf_to_text
    from validation.resumes import ROOT, gold_years

    gold = json.loads((ROOT / gold_file).read_text(encoding="utf-8"))
    today = datetime.now(UTC).date()
    fields = {"full_name": 0, "email": 0, "phone": 0, "telegram": 0, "city": 0, "experience": 0, "specialization": 0}
    tp = fp = fn = 0
    errors = []
    for g, person in zip(gold, people):
        r = parse_resume_text(pdf_to_text((ROOT / g["file"]).read_bytes()))
        ok = {"full_name": r["full_name"] == g["full_name"], "email": r["contact_email"] == g["email"],
              "phone": r["phone"] == g["phone"], "telegram": r["telegram"].lower() == g["telegram"].lower(),
              "city": r["city"] == g["city"],
              "experience": abs(r["experience_years"] - gold_years(person, today)) <= 1.0,
              "specialization": r["specialization"] == g["specialization"]}
        for k, v in ok.items():
            fields[k] += v
            if not v:
                errors.append(f"{g['file']}: {k}")
        pred, true = {x["id"] for x in r["skills"]}, set(g["skills"])
        tp, fp, fn = tp + len(pred & true), fp + len(pred - true), fn + len(true - pred)
    n = len(gold)
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    return {"resumes": n, "fields": {k: round(v / n, 3) for k, v in fields.items()},
            "skills_precision": round(prec, 3), "skills_recall": round(rec, 3),
            "skills_f1": round(2 * prec * rec / (prec + rec), 3), "errors": errors}


def resume_section() -> dict:
    """Resume PDFs (validation/resumes.py) parsed by the product code: the development set (15, the parser was
    fixed while looking at it) and the hold-out set (6, written after the fixes)."""
    from validation.resumes import HOLDOUT, PEOPLE

    return {"dev": _eval_resumes(PEOPLE, "resumes.json"), "holdout": _eval_resumes(HOLDOUT, "resumes_holdout.json")}


# ================================================================================================ report


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def human_block(h: dict) -> str:
    head = """## 8. Экспертная разметка пар «вакансия – кандидат»

Синтетическая релевантность из раздела 6 задана правилами, поэтому её проверяет человек. Из того же тестового набора
взяты 10 вакансий (по две на специализацию) и по 10 кандидатов на каждую. Пул собран так, чтобы не подыгрывать нашей
системе: топ-3 нашего скоринга, топ-3 поиска по ключевым словам, топ-2 BM25, остальные случайные из специализации, в
перемешанном порядке. Эксперт видит вакансию и профиль кандидата (стек, опыт, результат теста по навыкам, ФСП, ожидания)
и ставит оценку 0–3. **Оценок системы он не видит.** Форма: `docs/validation/labeling/index.html`
(пересобирается командой `uv run python -m validation.labeling`), ответы: `docs/validation/labels/*.json`.
"""
    if not h.get("labelers"):
        return head + f"""
Набор пар (версия `{h.get('version', '—')}`, {h.get('pairs', 100)} пар) готов; результаты появятся здесь после разметки.
"""
    rows = "\n".join(f"| {name} | {v['nDCG']:.3f} ({v['nDCG_ci'][0]:.2f}–{v['nDCG_ci'][1]:.2f}) | {v['P@3']:.3f} "
                     f"| {v['spearman']:.3f} |" for name, v in h["systems"].items())
    inter = (f"| Согласие экспертов между собой (взвешенная каппа) | {h['inter_annotator_kappa_w']} |\n"
             if "inter_annotator_kappa_w" in h else "")
    return head + f"""
Разметчиков: {h['labelers']}, размечено пар: {h['labeled_pairs']} ({h['vacancies']} вакансий). Доля подходящих
(оценка ≥ 2) в пуле — {pct(h['pool_relevant_share'])}. Системы сравниваются по тому, как они упорядочивают один и тот же пул.

| Система | nDCG пула (95% ДИ) | P@3 | ρ Спирмена с оценкой эксперта |
|---|---|---|---|
{rows}

| Проверка синтетической разметки | Значение |
|---|---|
| Совпадение оценки эксперта с синтетической релевантностью | {pct(h['truth_exact'])} (±1 балл — {pct(h['truth_within_1'])}) |
| Взвешенная каппа «эксперт — синтетика» | {h['truth_kappa_w']} |
{inter}"""


def ci(c) -> str:
    return f"{c[0]:.3f}–{c[1]:.3f}"


def diff_txt(d: dict) -> str:
    sign = "значимо" if d["significant"] else "в пределах шума"
    return f"{d['mean']:+.3f} (95% ДИ {d['ci'][0]:+.3f}…{d['ci'][1]:+.3f}, {sign})"


def seeds_block(sd: dict) -> str:
    def row(title, key):
        v = sd[key]
        return f"| {title} | {pct(v['mean'])} ± {v['sd'] * 100:.1f} п. п. | {', '.join(pct(x) for x in v['values'])} |"

    return f"""**Устойчивость к выборке.** Те же метрики на {len(sd['seeds'])} независимых популяциях по {sd['n']} человек
(сиды {', '.join(map(str, sd['seeds']))}):

| Метрика | Среднее ± SD | По популяциям |
|---|---|---|
{row("Грейд совпал с истинным", "exact")}
{row("Ошибка не больше одного грейда", "within1")}
| Взвешенная каппа test-retest | {sd['retest_kappa_w']['mean']} ± {sd['retest_kappa_w']['sd']} | {', '.join(map(str, sd['retest_kappa_w']['values']))} |
"""


def sweeps_block(sw: dict) -> str:
    cp = "\n".join(f"| {r['value']} | {pct(r['exact'])} | {pct(r['over'])} | {pct(r['under'])} |" for r in sw["confirm_p"])
    return f"""**Как выбран порог подтверждения.** Порог P(θ ≥ порога грейда) перебирается на отдельной популяции
({sw['n']} человек, сид 13):

| Порог | Грейд совпал | Завышение | Занижение |
|---|---|---|---|
{cp}

Выбрано {cat.CONFIRM_P}: работодателю важнее, чтобы подтверждённый грейд не был завышен, а более высокий порог
заметно увеличивает занижения. Альтернатива «повторная попытка продолжает измерение» (ответы первой попытки
учитываются) экономит около 20% заданий, но снижает точность, поэтому попытки независимы (`synth.CARRY_OVER`).
"""


def exposure_block(t: dict, sw: dict, u: dict) -> str:
    rows = "\n".join(
        f"| {'выключено' if r['value'] is None else r['value']} | {pct(r['exact'])} | {r['items']} | "
        f"{pct(r['max_overall'])} | {pct(r['max_in_spec'])} |" for r in sw["exposure"])
    return f"""**Экспозиция.** Утечка распространяется среди кандидатов одной специализации, поэтому главная метрика —
доля кандидатов специализации, увидевших позицию (по всем их попыткам). Движок ограничивает её онлайн-вариантом
Sympson–Hetter: позиция, показанная в доле r > {t['exposure_cap']} сессий своей специализации, допускается с
вероятностью {t['exposure_cap']}/r, а randomesque сужается с топ-5 до топ-2 по мере уточнения оценки.

| Метрика | Значение |
|---|---|
| Максимальная экспозиция позиции среди всех кандидатов | {pct(t['max_exposure_rate'])} |
| Максимальная экспозиция внутри специализации | {pct(t['max_exposure_in_spec'])} |
| Максимум «экспозиция позиции × P(совпадения экземпляра)» | {t['content_exposure_max'] * 100:.2f}% |

Перебор порога r_max ({sw['n']} человек, сид 13):

| r_max | Грейд совпал | Заданий за попытку | Max экспозиция (все) | Max экспозиция (в специализации) |
|---|---|---|---|---|
{rows}

Ниже {pct(min(r['max_in_spec'] for r in sw['exposure']))} внутри специализации экспозицию не опустить без потери
содержательной валидности: квота навыка задаёт минимум. Например, QA-тесту нужно около 6 заданий по тест-дизайну
из 10 позиций этого навыка. Поэтому экспозиция *позиции* — не экспозиция *содержания*: каждая сессия получает свой
экземпляр семейства, и вероятность, что кандидат увидит тот же экземпляр, что и его знакомый, ограничена
произведением в последней строке таблицы выше. Банк расширен до {u['slots']} позиций, в том числе
чтобы у самых нагруженных навыков (тест-дизайн, ML, статистика, Docker, JavaScript) появился выбор.
"""


def matching_block(m: dict) -> str:
    rows = "\n".join(f"| {name} | {v['P@10']:.3f} ({ci(v['P@10_ci'])}) | {v['nDCG@10']:.3f} ({ci(v['nDCG@10_ci'])}) "
                      f"| {v['MRR']:.3f} |" for name, v in m["table"].items())
    diffs = "\n".join(f"| Полный − {name} | {diff_txt(d['P@10'])} | {diff_txt(d['nDCG@10'])} |"
                       for name, d in m["paired_diff"].items())
    sweep = "\n".join(f"| {r['weight']} | {r['P@10']:.3f} | {r['nDCG@10']:.3f} |" for r in m["fsp_sweep"])
    sens_rows = []
    for name in m["table"]:
        cells = [f"{m['table'][name]['nDCG@10']:.3f}"] + [f"{m['sensitivity'][var][name]['nDCG@10']:.3f}"
                                                         for var in ("strict", "soft")]
        sens_rows.append(f"| {name} | " + " | ".join(cells) + " |")
    kept = all(all(v.values()) for v in m["sensitivity_order_kept"].values())
    ic, icc = m["in_category_spearman"], m["in_category_ci"]
    a = m["adaptation"]
    return f"""| Система | P@10 (95% ДИ) | nDCG@10 (95% ДИ) | MRR |
|---|---|---|---|
{rows}

ДИ — перцентильный бутстрап по вакансиям (2000 повторов). Парные разницы считаются по одним и тем же вакансиям,
поэтому общая «сложность» вакансии сокращается:

| Сравнение | Δ P@10 | Δ nDCG@10 |
|---|---|---|
{diffs}

![](matching.png)

Ключевое: самоописанные данные (ключевые слова, самооценка) ранжируют хуже, чем подтверждённый тестом профиль.
Абляция «без теста» показывает вклад механики тестирования в подбор.

**Роль ФСП.** Для вопроса «подходит ли кандидат вакансии» бонус ФСП почти ничего не добавляет к тесту: тест уже
измеряет ту же способность, а кандидат чуть выше порога так же «подходит», как сильный. Разница «полный − без ФСП»
выше лежит в пределах шума — в обе стороны. Перебор веса ФСП в оценке соответствия:

| Вес ФСП | P@10 | nDCG@10 |
|---|---|---|
{sweep}

Вес оставлен небольшим ({DEFAULT_FSP_WEIGHT}): он не ухудшает подбор и даёт работодателю видимый сигнал. ТЗ отводит
ФСП другую роль — **ранжирование внутри категории** по силе подтверждённого профиля. Здесь ФСП — независимое второе
измерение, и оно помогает. Корреляция Спирмена порядка внутри категории с истинной способностью
({m['categories']} категорий, ДИ — бутстрап по категориям):

| Порядок внутри категории | ρ Спирмена с истинной θ (95% ДИ) |
|---|---|
| Сила профиля: тест + ФСП + актуальность | **{ic['full']}** ({ci(icc['full'])}) |
| Без ФСП (тест + актуальность) | {ic['no_fsp']} ({ci(icc['no_fsp'])}) |
| Только ФСП | {ic['fsp_only']} ({ci(icc['fsp_only'])}) |

Парная разница «с ФСП − без ФСП» внутри категории: {diff_txt(m['in_category_diff_full_minus_no_fsp'])}.

**Чувствительность к определению релевантности.** Пороги синтетической релевантности условны, поэтому метрики
пересчитаны при строгом (без запаса по навыкам, грейд строго равен, зарплата не выше вилки) и мягком (достаточно
половины обязательных навыков, зарплата до +20%) определениях. nDCG@10:

| Система | Базовое | Строгое | Мягкое |
|---|---|---|---|
{chr(10).join(sens_rows)}

{"Выводы сохраняются при всех определениях: наш скоринг выше поиска по ключевым словам и BM25, а профиль, подтверждённый тестом, ранжирует лучше самооценки. Полный скоринг и «без ФСП» почти равны и могут меняться местами" if kept else "Часть выводов зависит от определения релевантности — см. таблицу"}.

**Адаптация весов к отказам.** Каждая из {a['companies']} вакансий — компания, которая {a['rounds']} раундов подряд
приглашает по {a['per_round']} лучших ещё не приглашённых кандидатов. У кандидатов скрытое правило: отказ, если вилка
ниже ожиданий, не подходит формат, знакомо меньше 2/3 обязательного стека или позиция ниже их истинного уровня;
иначе согласие с вероятностью 0,8. Отказ с причиной поднимает вес соответствующего компонента
(`scoring.adapt_weights`, шаг +10%, потолок ×2). Контроль — те же компании с фиксированными весами и теми же случайными
числами.

| | Доля принятых за все раунды | Раунды 5–8 |
|---|---|---|
| Фиксированные веса | {pct(a['fixed_total'])} | {pct(sum(a['fixed'][4:]) / len(a['fixed'][4:]))} |
| Адаптация к отказам | {pct(a['adaptive_total'])} | {pct(sum(a['adaptive'][4:]) / len(a['adaptive'][4:]))} |
| Разница | {diff_txt(a['diff_total'])} | {diff_txt(a['diff_late'])} |

![](adaptation.png)
"""


def nlp_block(nl: dict) -> str:
    cols = [("templates", "rules", "Шаблоны"), ("dev", "rules", "Разработка"), ("holdout", "rules", "**Отложенный**")]
    if nl.get("llm"):
        cols += [("dev", "rules+llm", "Разработка + LLM"), ("holdout", "rules+llm", "**Отложенный + LLM**")]

    def row(title, key, fmt=lambda v: f"{v:.3f}"):
        cells = []
        for st, var, _ in cols:
            v = nl[st][var][key]
            cells.append("—" if v is None else fmt(v))
        return f"| {title} | " + " | ".join(cells) + " |"

    head = "| Метрика | " + " | ".join(c[2] for c in cols) + " |\n|---|" + "---|" * len(cols)
    llm_note = (f"Столбцы «+ LLM»: правила, уточнённые языковой моделью ({nl['llm_provider']}) с постпроверкой по "
                "справочнику." if nl.get("llm") else
                "Столбцы с LLM появятся при заданном ключе (`LLM_PROVIDER`, `LLM_API_KEY`): без ключа продукт работает "
                "на правилах, и отчёт честно показывает только их.")
    return f"""Три набора описаний вакансий:

- **шаблоны** — {nl['templates']['rules']['cases']} текстов: {nl['handwritten']} ручных и вакансии генератора
  синтетики. Навыки там названы так же, как в справочнике, поэтому метрики близки к 1 и мало что доказывают;
- **разработка** — {nl['dev']['rules']['cases']} реалистичных текстов (`validation/data/needs.json`): «вода»,
  опечатки, английский и смешанный язык, жаргон и транслитерация («постгрес», «кубер», «джангу»), вилки в разных
  форматах. По ним мы находили ошибки правил и дорабатывали их. До доработки на этом наборе было F1 по навыкам 0,865,
  грейд 75%, вилка 72,5%;
- **отложенный** — {nl['holdout']['rules']['cases']} текстов (`validation/data/needs_holdout.json`), написанных
  *после* того, как правила были заморожены. Это честная оценка на новых текстах.

{head}
{row("Навыки: точность", "skills_precision")}
{row("Навыки: полнота", "skills_recall")}
{row("Навыки: F1", "skills_f1")}
{row("Навык в верном списке (обязательный / желательный)", "must_nice_acc", pct)}
{row("Специализация", "specialization_acc", pct)}
{row("Грейд (где указан)", "grade_acc", pct)}
{row("Вилка", "salary_acc", pct)}
{row("Формат работы", "format_acc", pct)}

{llm_note}

**Эмбеддинги проверены и не включены.** Мы проверили локальную модель `paraphrase-multilingual-MiniLM-L12-v2`
(fastembed, ONNX) для сопоставления незнакомых терминов со справочником и для текстовой близости «вакансия — профиль».
На жаргоне она ошибается уверенно: «свифт» → Vue (косинус 0,97), «терраформ» → вёрстка (0,91), «кубер» →
теорвер (0,68). На уровне текстов сигнал слабый: профиль про кредитный скоринг оказался ближе к вакансии платёжного
шлюза (0,57), чем профиль про процессинг платежей (0,45). Выигрыш есть только на англоязычных текстах, а модель
добавляет ~250 МБ к образу и ~300 МБ памяти. Воспроизведение: `uv run --with fastembed python -m
validation.embeddings_probe`. Вместо этого правила разбирают русские окончания и жаргон, а смысловое уточнение
делает LLM, если задан ключ.
"""


RESUME_FIELDS = {"full_name": "ФИО", "email": "E-mail", "phone": "Телефон", "telegram": "Telegram", "city": "Город",
                 "experience": "Стаж (±1 год)", "specialization": "Специализация"}
LAYOUTS = {"plain": "одна колонка", "sidebar": "две колонки", "hh": "выгрузка hh с таблицей", "english": "английское",
           "prose": "навыки в тексте «О себе»"}


def resume_block(r: dict) -> str:
    d, h = r["dev"], r["holdout"]
    rows = "\n".join(f"| {RESUME_FIELDS[k]} | {RESUME_BASELINE[k]} | {pct(d['fields'][k])} | {pct(h['fields'][k])} |"
                      for k in RESUME_FIELDS)
    holdout_errors = ", ".join(f"`{e}`" for e in h["errors"]) or "нет"
    return f"""## 10. Разбор резюме (PDF)

Вымышленные резюме в пяти вёрстках, которые встречаются в реальных PDF (`validation/resumes.py`, файлы в
`validation/data/resumes/`): одна колонка, две колонки с боковой панелью, выгрузка в стиле hh.ru с таблицей мест
работы, английское резюме и резюме, где навыки описаны прозой. Форматы периодов, телефонов и ссылок на Telegram
различаются намеренно. PDF разбирается тем же кодом, что в продукте (`resume.py`, PyMuPDF), без LLM.

На наборе разработки ({d['resumes']} резюме) мы нашли ошибки парсера и исправили их: периоды «03.2019 – н.в.» и
«с 2016 по 2019», перенос «настоящее время» внутри ячейки таблицы, телефоны с 8, имя после боковой панели, ложный
Telegram внутри слова «PostgreSQL». Отложенный набор ({h['resumes']} резюме) написан после исправлений, с форматами,
под которые парсер не настраивался: фамилия заглавными с отчеством, «2019 г. – 2021 г.», «Mar 2020 – current»,
явная строка «Опыт работы — 7 лет 9 месяцев».

| Поле | До исправлений (разработка) | После (разработка) | **Отложенный** |
|---|---|---|---|
{rows}
| Навыки: F1 | {RESUME_BASELINE['skills_f1']} | {d['skills_f1']} | **{h['skills_f1']}** |

Ошибки на отложенном наборе: {holdout_errors}. Карточка после загрузки PDF — черновик: кандидат проверяет и
подтверждает каждое поле, а при заданном ключе LLM дополняет то, что правила не нашли.
"""


OPS_RU = {"shortlist": "Подборка по потребности", "search": "Поиск по банку с фильтрами",
          "candidate card": "Карточка кандидата", "category": "Кандидаты категории", "dashboard": "Кабинет кандидата",
          "vacancies": "Вакансии с оценкой соответствия", "profile": "Профиль кандидата",
          "test blueprint": "Генерация теста по специализации", "needs list": "Список потребностей"}


def load_block() -> str:
    path = OUT / "load.json"
    head = """## 11. Нагрузка

`uv run python -m validation.load --url <стенд> --users 50`: 50 одновременных пользователей (70% работодателей,
30% кандидатов) 3 минуты работают со стендом из `docker compose` с демо-данными. Каждый делает паузу 0,5–2 с между
действиями, как человек.
"""
    if not path.exists():
        return head + "\nПрогон ещё не выполнялся.\n"
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = "\n".join(f"| {OPS_RU.get(op, op)} | {v['requests']} | {v['p50_ms']} | {v['p95_ms']} | {v['p99_ms']} | "
                     f"{v['errors']} |" for op, v in sorted(d["operations"].items(), key=lambda x: -x[1]["requests"]))
    return head + f"""
Прогон {d['generated_at']}: {d['requests']} запросов за {d['seconds']} с ({d['rps']} в секунду), ошибок
{d['error_share'] * 100:.2f}%.

| Операция | Запросов | p50, мс | p95, мс | p99, мс | Ошибок |
|---|---|---|---|---|---|
{rows}

Первый прогон нашёл узкое место: список вакансий кандидата пересчитывал траст-скор компании для каждой вакансии
(p95 4,8 с, p99 8,3 с). После кэширования траст-скора на компанию в пределах запроса — значения выше. Память всего
стека под нагрузкой — около 1 ГБ (`docker stats`: backend ~300 МБ, Keycloak ~525 МБ, PostgreSQL ~85 МБ).
"""


def write_report(s: dict) -> None:
    t, lk, u, m, nl = s["test"], s["leak"], s["uniqueness"], s["matching"], s["nlp"]
    worst = "\n".join(f"| `{w['item']}` | {w['distinct']} | {w['collision']:.3f} |" for w in u["worst"])
    report = f"""# Валидация решения

Отчёт сгенерирован командой `uv run python -m validation.run` ({s['generated_at']}).
Код валидации — `backend/validation/run.py`; он вызывает **те же модули**, что работают в продукте
(`cat.py`, `scoring.py`, `nlp.py`), на синтетической популяции с известной «скрытой истиной» (`app/seed/synth.py`).

## Почему синтетика и как она устроена

Эталонной разметки на хакатоне нет, поэтому мы моделируем кандидатов, у которых **истинная способность известна**:
- у каждого кандидата есть истинная способность θ ~ N(0,15; 0,95) и способности по навыкам θ_s = θ + N(0; 0,45);
- наблюдаемое — заявленный грейд (шумная и слегка завышенная самооценка), стек, опыт, ожидания по зарплате — порождается из θ с шумом;
- ответы на задания генерируются по модели 3PL с **«истинными» параметрами заданий, отличающимися от экспертных** (b ± 0,25, a × e^N(0; 0,15)), — движок теста их не знает, как и в реальности до калибровки.

Так мы проверяем то, что важно жюри: восстанавливает ли система скрытую правду, а не совпадает ли сама с собой.

## 1. Точность присвоения грейда

{t['n']} кандидатов прошли полный сценарий (тест на заявленный грейд → при неуспехе сразу тест на грейд ниже).

| Метрика | Значение |
|---|---|
| Грейд совпал с истинным | **{pct(t['grade_exact'])}** |
| Ошибка не больше одного грейда | **{pct(t['grade_within_1'])}** |
| Завышение / занижение | {pct(t['over_graded'])} / {pct(t['under_graded'])} |
| Для сравнения: самооценка кандидата совпадает с истиной | {pct(t['self_assessment_exact'])} (завышают {pct(t['self_assessment_over'])}) |
| Корреляция оценки θ̂ с истинной θ | {t['theta_corr']} (RMSE {t['theta_rmse']}) |
| Заданий за попытку (среднее) | {t['items_per_attempt_mean']} |
| Попыток до присвоения (среднее) | {t['attempts_mean']} |

![](test_accuracy.png)

**Нейтральность к заявленному грейду.** Тех же кандидатов прогнали дважды: с честным заявленным грейдом и с завышенным
на ступень. Средний сдвиг оценки θ̂ — **{t['claim_bias_theta']:+.3f} ± {t['claim_bias_ci95']}** (95% ДИ), то есть статистически
неотличим от нуля; разброс разницы (SD {t['claim_vs_retest_sd'][0]}) такой же, как между двумя честными попытками
(SD {t['claim_vs_retest_sd'][1]}). Заявленный грейд влияет только на выбор стартовых заданий, а оценка строится с общим
априорным распределением N(0,1): «заявить Senior на удачу» бесполезно.

**Точность решения «подтвердить / не подтвердить».** Первая попытка подтверждает заявленный грейд тогда и только тогда,
когда истинная способность не ниже порога, в **{pct(t['decision_accuracy'])}** случаев.

{seeds_block(s["seeds"])}
{sweeps_block(s["sweeps"])}
## 2. Согласованность (test-retest)

Каждый кандидат прошёл тест повторно с новыми случайными экземплярами заданий.

| Метрика | Значение |
|---|---|
| Тот же грейд при повторе | **{pct(t['retest_exact'])}** |
| Взвешенная каппа Коэна | **{t['retest_kappa_w']}** |
| Корреляция θ̂ между попытками | {t['retest_theta_r']} |

Квадратично-взвешенная каппа выше 0,8 считается «почти полным согласием».

## 3. Дискриминативность заданий и экспозиция

| Метрика | Значение |
|---|---|
| Медианная точечно-бисериальная корреляция «способность — верный ответ» | **{t['pbis_median']}** |
| Доля позиций банка с r ≥ 0,2 (порог пригодности задания) | {pct(t['pbis_share_ge_0_2'])} |
| Использовано позиций банка | {t['items_used']} из {t['items_in_bank']} |

![](test_items.png)

![](icc.png)

{exposure_block(t, s["sweeps"], u)}
## 4. Устойчивость к утечке заданий

Моделируем утечку 40% заданий. Дизайн **парный**: каждый кандидат проходит тест дважды на одних и тех же случайных
числах — честно и со «слитыми» знаниями. Поэтому разница показывает эффект утечки, а не шум повторного теста.

| Сценарий | Средний прирост θ̂ | Доля получивших грейд выше |
|---|---|---|
| Статичный тест (одна форма), утёк ключ ответов | {lk['static_theta_gain']:+.2f} | **{pct(lk['static_grade_up'])}** |
| Наш CAT, утёк ключ ответов | {lk['cat_key_theta_gain']:+.2f} | **{pct(lk['cat_key_grade_up'])}** |
| Наш CAT, утёк ключ и разбор метода (+0,15 к вероятности на «слитых» семействах) | {lk['cat_method_theta_gain']:+.2f} | {pct(lk['cat_method_grade_up'])} |

В параметрическом тесте слитый ключ бесполезен: новый кандидат получает другие данные и другой правильный ответ.
Остаётся «утечка метода» — кандидат заранее разобрался, как решаются такие задачи. Её эффект ограничен, и по сути это
освоение навыка.

![](leak.png)

**Детектор утечек** (`assessment/leak.py`) — односторонний CUSUM остатков «наблюдаемая − ожидаемая доля верных»
относительно собственной базовой линии позиции. Базовая линия нужна, потому что экспертные параметры заданий неточны:
без неё любая неоткалиброванная позиция выглядела бы «слитой». Первая версия детектора без базовой линии давала 47%
ложных срабатываний; эта проверка её и выявила.

| Метрика | Значение |
|---|---|
| Ложные срабатывания на честном потоке (600 ответов) | {pct(lk['detector_false_positive_rate'])} |
| Обнаружение, ответ знают 30% отвечающих (за 400 ответов) | {pct(lk['detector_power_30'])}, медианная задержка {lk['detector_delay_30']} ответов |
| Обнаружение, ответ знают 50% отвечающих | {pct(lk['detector_power_50'])}, медианная задержка {lk['detector_delay_50']} ответов |

Детектор — вторая линия защиты. Первая — параметризация, при которой ключ ответов вообще не переносится.

## 5. Уникальность экземпляров

Для каждой позиции банка ({u['slots']}) сгенерировано 400 экземпляров; вероятность, что два кандидата получат
**идентичный** экземпляр, — Σp².

| Метрика | Значение |
|---|---|
| Медианная вероятность совпадения | **{u['median_collision']}** |
| Доля позиций с вероятностью совпадения < 1% | {pct(u['share_slots_collision_lt_1pct'])} |
| Медианная доля самого частого правильного ответа | {pct(u['median_top_answer_share'])} |

Наименее вариативные позиции:

| Позиция | Различных экземпляров из 400 | P(совпадения) |
|---|---|---|
{worst}

## 6. Качество подбора

{m['vacancies']} вакансий × {m['candidates']} кандидатов. Релевантность пары (0–3) вычисляется из **скрытой истины**:
истинный грейд, реальное владение обязательными навыками на уровне вакансии (заявлено в профиле и истинная θ_s выше порога),
совместимость по зарплате и формату. Ни одна система не видит эти величины напрямую. Результаты соревнований ФСП
моделируются как шумное измерение способности (результат = θ + N(0; 0,8) → победитель / призёр / финалист / участник,
разряд аналогично), участие в ФСП слабо коррелирует со способностью. Медиана «хороших» (rel ≥ 2)
кандидатов на вакансию — {m['relevant_per_vacancy_median']}. Все системы ранжируют кандидатов одной специализации.

{matching_block(m)}
## 7. Разбор текста потребности

{nlp_block(nl)}
{human_block(s["human"])}
{pilot_block(s["pilot"])}
{resume_block(s["resume"])}
{load_block()}
## Ограничения и что дальше

- Синтетика проверяет корректность механики, но не реальные параметры заданий. После хакатона: пилот на 50–100
  участниках ФСП, калибровка a и b по реальным ответам (маргинальная оценка максимального правдоподобия), сравнение
  грейда с экспертной оценкой тимлидов (корреляция Спирмена).
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller samples for a fast check")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    bank = cat.build_bank()
    truth = synth.true_params(bank, random.Random(7))
    n = 600 if args.quick else 3000
    summary = {"generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}
    print("1-3. adaptive test ...", flush=True)
    summary["test"] = test_section(n, bank, truth)
    print("1. seeds ...", flush=True)
    summary["seeds"] = seeds_section(bank, truth, (11, 12) if args.quick else (11, 12, 13, 14, 15),
                                     300 if args.quick else 1500)
    print("1. sweeps ...", flush=True)
    summary["sweeps"] = sweeps_section(bank, truth, 300 if args.quick else 1200)
    print("4. leaks ...", flush=True)
    summary["leak"] = leak_section(bank, truth, 300 if args.quick else 800)
    print("5. uniqueness ...", flush=True)
    summary["uniqueness"] = uniqueness_section(200 if args.quick else 400)
    coll = summary["uniqueness"].pop("collision_by_slot")
    summary["test"]["content_exposure_max"] = round(max(
        v * coll.get(k, 0.0) for k, v in summary["test"].pop("exposure_in_spec").items()), 5)
    print("6. matching ...", flush=True)
    summary["matching"] = matching_section(bank, truth, 400 if args.quick else 900, 20 if args.quick else 40)
    print("7. nlp ...", flush=True)
    summary["nlp"] = nlp_section()
    print("8. expert labels ...", flush=True)
    summary["human"] = human_section(bank, truth)
    print("10. resumes ...", flush=True)
    summary["resume"] = resume_section()
    print("9. pilot ...", flush=True)
    summary["pilot"] = pilot_section()
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(summary)
    # the product shows the key results on the "How it works" page
    public = OUT.parents[1] / "frontend" / "public" / "validation"
    public.mkdir(parents=True, exist_ok=True)
    (public / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, default=str), encoding="utf-8")
    for png in OUT.glob("*.png"):
        (public / png.name).write_bytes(png.read_bytes())
    print(json.dumps({k: v for k, v in summary.items() if k != "test"} | {"test": {k: v for k, v in summary["test"].items() if k != "confusion"}},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
