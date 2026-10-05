"""Validation suite: `uv run python -m validation.run [--quick]`.

Writes docs/validation/report.md, docs/validation/*.png and docs/validation/summary.json.
Everything runs on the production code (app.modules.assessment.cat, app.modules.matching.scoring, app.modules.nlp)
against a synthetic population whose latent truth is known (app.seed.synth). Fixed seeds: results are reproducible.

Sections
  1. Adaptive test: accuracy vs. true grade, confusion matrix, test length, ability recovery, claim neutrality
  2. Consistency: test-retest agreement (new item instances, same candidate)
  3. Discriminativeness: item-level point-biserial and test information
  4. Leak resistance: static test vs. parametric CAT under a leaked answer key; leak detector power
  5. Instance uniqueness: collision probability of item instances between two candidates
  6. Matching: P@10, nDCG@10, MRR vs. keyword and BM25 baselines + ablations, on graded relevance from latent truth
  7. NLP: extraction quality of need/vacancy parsing
"""

import argparse
import json
import math
import random
import statistics
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
from app.modules import nlp  # noqa: E402
from app.modules.assessment import cat  # noqa: E402
from app.modules.assessment.families import REGISTRY  # noqa: E402
from app.modules.assessment.irt import p_correct  # noqa: E402
from app.modules.fsp.scoring import fsp_score  # noqa: E402
from app.modules.matching.scoring import CandidateView, NeedSpec, score  # noqa: E402
from app.seed import synth  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "validation"
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


def simulate_population(n: int, seed: int, bank, truth):
    rng = random.Random(seed)
    people = [synth.make_candidate(rng, None, i) for i in range(n)]
    rows = []
    for c in people:
        res = synth.assign_grade(rng, c, bank, truth)
        rows.append({"c": c, "res": res})
    return rows


def test_section(n: int, bank, truth) -> dict:
    t0 = time.time()
    rows = simulate_population(n, 11, bank, truth)
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
    retest = [synth.assign_grade(rng, r["c"], bank, truth) for r in rows]
    re_g = [GRADE_ORDER.index(x["grade"]) for x in retest]
    re_theta = np.array([x["theta"] for x in retest])
    agree = float(np.mean(np.array(re_g) == np.array(got_g)))

    # item statistics from the first attempts
    per_item: dict[str, list[tuple[float, int]]] = {}
    for r in rows:
        for resp in r["res"]["responses"]:
            per_item.setdefault(resp.item.key, []).append((r["c"].theta, int(resp.correct)))
    pbis = {}
    for key, xs in per_item.items():
        if len(xs) >= 30 and 0 < sum(y for _, y in xs) < len(xs):
            t, y = zip(*xs)
            pbis[key] = float(np.corrcoef(t, y)[0, 1])
    exposure = Counter()
    for r in rows:
        for resp in r["res"]["responses"]:
            exposure[resp.item.key] += 1
    total_admin = sum(exposure.values())

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
    exp_rates = sorted((v / n for v in exposure.values()), reverse=True)
    axes[2].bar(range(len(exp_rates)), exp_rates, color=BRAND)
    axes[2].set(title="Экспозиция позиций банка", xlabel="позиция (по убыванию)", ylabel="доля кандидатов")
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
        "max_exposure_rate": round(max(exposure.values()) / n, 3),
        "items_used": len(exposure),
        "items_in_bank": len(bank),
        "confusion": conf.tolist(),
        "admin_total": total_admin,
    }


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
        "median_top_answer_share": round(float(np.median([r["top_answer_share"] for r in rows])), 3),
    }


# ================================================================================================ 6. matching


def _relevance(c: synth.SynthCandidate, v: dict) -> int:
    """Graded ground truth from the *latent* attributes the system never sees directly."""
    if c.spec != v["specialization"]:
        return 0
    tg, vg = GRADE_ORDER.index(c.true_grade), GRADE_ORDER.index(v["grade"])
    thr = GRADE_BY_ID[v["grade"]].theta_min if v["grade"] != "intern" else -1.8
    knows = {s["id"] for s in c.skills}
    must = v["must_skills"]
    can = [s for s in must if s in knows and c.skill_theta.get(s, c.theta) >= thr - 0.4]
    frac = len(can) / len(must) if must else 1
    salary_ok = c.salary_expectation <= v["salary_to"] * 1.1
    fmt_ok = not v["work_formats"] or bool(set(v["work_formats"]) & set(c.work_formats))
    if tg == vg and frac >= 0.99 and salary_ok and fmt_ok:
        return 3
    if abs(tg - vg) <= 1 and frac >= 0.66 and salary_ok:
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
        fsp, reasons = fsp_score(achievements, rank, c.spec, now)
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
    return score_ + random.random() * 0.01


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


def matching_section(bank, truth, n_cand: int = 900, n_vac: int = 40) -> dict:
    rng = random.Random(77)
    people = [synth.make_candidate(rng, None, i) for i in range(n_cand)]
    for c in people:
        c.test = synth.assign_grade(rng, c, bank, truth)
    vacancies = []
    for i in range(n_vac):
        v = synth.make_vacancy(rng, SPECIALIZATIONS[i % len(SPECIALIZATIONS)].id)
        vacancies.append(v)
    now = datetime.now(UTC)
    views = {"full": [_view(c, now) for c in people], "no_test": [_view(c, now, use_test=False) for c in people],
             "no_fsp": [_view(c, now, use_fsp=False) for c in people]}
    tokens = [(" ".join([c.headline, c.about] + [s["id"] for s in c.skills])).lower().split() for c in people]
    systems = {
        "Ключевые слова (как hh)": None,
        "BM25 по тексту резюме": None,
        "Наш скоринг без теста (самооценка)": "no_test",
        "Наш скоринг без ФСП": "no_fsp",
        "Наш скоринг (полный)": "full",
    }
    results = {name: [] for name in systems}
    per_vac_relevant = []
    for v in vacancies:
        rels = [_relevance(c, v) for c in people]
        per_vac_relevant.append(sum(1 for r in rels if r >= 2))
        need = NeedSpec(specialization=v["specialization"], grade=v["grade"], must_skills=v["must_skills"],
                        nice_skills=v["nice_skills"], work_formats=v["work_formats"], city=v["city"],
                        salary_from=v["salary_from"], salary_to=v["salary_to"], text=v["description"])
        # every system sees the same candidate set: the vacancy's specialization (a plain filter on any site)
        idx = [i for i, c in enumerate(people) if c.spec == v["specialization"]]
        spec_rels = [rels[i] for i in idx]
        for name, mode in systems.items():
            if mode is None and name.startswith("Ключевые"):
                order = sorted(idx, key=lambda i: -_keyword_rank(people[i], v))
            elif mode is None:
                q = (" ".join(v["must_skills"] + v["nice_skills"]) + " " + v["title"]).lower().split()
                sc = _bm25_rank([tokens[i] for i in idx], q)
                order = [idx[j] for j in sorted(range(len(idx)), key=lambda j: -sc[j])]
            else:
                # category-first: the target grade and its neighbours, ranked by score (as in the product)
                gi = GRADE_ORDER.index(v["grade"])
                cands = [i for i in idx if abs(GRADE_ORDER.index(views[mode][i].grade) - gi) <= 1] or idx
                rest = [i for i in idx if i not in set(cands)]
                order = sorted(cands, key=lambda i: -score(views[mode][i], need, now=now)["score"]) + rest
            results[name].append(_metrics([rels[i] for i in order], spec_rels))
    # in-category ranking (spec x assigned grade): how well the order recovers the true ability
    from app.modules.matching.scoring import profile_strength

    def spearman(a, b):
        ra = np.argsort(np.argsort(a))
        rb = np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])

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
        within["fsp_only"].append(spearman([views["full"][i].fsp + 1e-6 * random.random() for i in idx], true_t))
        weights.append(len(idx))
    in_category = {k: round(float(np.average(v, weights=weights)), 3) for k, v in within.items()}

    table = {}
    for name, ms in results.items():
        arr = np.array(ms)
        table[name] = {"P@10": round(float(arr[:, 0].mean()), 3), "nDCG@10": round(float(arr[:, 1].mean()), 3),
                       "MRR": round(float(arr[:, 2].mean()), 3)}

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
            "table": table, "in_category_spearman": in_category, "categories": len(weights)}


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


def nlp_section() -> dict:
    rng = random.Random(3)
    cases = list(HANDWRITTEN)
    for _ in range(60):
        v = synth.make_vacancy(rng)
        cases.append((v["description"], {"specialization": v["specialization"], "grade": v["grade"],
                                         "must": set(v["must_skills"]), "nice": set(v["nice_skills"]),
                                         "formats": set(v["work_formats"]), "salary": (v["salary_from"], v["salary_to"])}))
    tp = fp = fn = 0
    spec_ok = grade_ok = sal_ok = fmt_ok = 0
    grade_n = 0
    hand = {"spec": 0, "skills_f1": []}
    for i, (text, gold) in enumerate(cases):
        p = nlp.parse_need(text)
        pred = set(p["must_skills"]) | set(p["nice_skills"])
        goldset = gold["must"] | gold["nice"]
        tp += len(pred & goldset)
        fp += len(pred - goldset)
        fn += len(goldset - pred)
        spec_ok += p["specialization"] == gold["specialization"]
        if gold["grade"]:
            grade_n += 1
            grade_ok += p["grade"] == gold["grade"]
        sal_ok += (p["salary_from"], p["salary_to"]) == gold["salary"]
        fmt_ok += set(p["work_formats"]) == gold["formats"]
        if i < len(HANDWRITTEN):
            hand["spec"] += p["specialization"] == gold["specialization"]
            t = len(pred & goldset)
            hand["skills_f1"].append(2 * t / (len(pred) + len(goldset)) if pred or goldset else 1)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    n = len(cases)
    return {"cases": n, "handwritten": len(HANDWRITTEN), "skills_precision": round(prec, 3),
            "skills_recall": round(rec, 3), "skills_f1": round(2 * prec * rec / (prec + rec), 3),
            "specialization_acc": round(spec_ok / n, 3), "grade_acc": round(grade_ok / grade_n, 3),
            "salary_acc": round(sal_ok / n, 3), "format_acc": round(fmt_ok / n, 3),
            "handwritten_skills_f1": round(statistics.mean(hand["skills_f1"]), 3),
            "handwritten_spec_acc": round(hand["spec"] / len(HANDWRITTEN), 3)}


# ================================================================================================ report


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_report(s: dict) -> None:
    t, lk, u, m, nl = s["test"], s["leak"], s["uniqueness"], s["matching"], s["nlp"]
    rows = "\n".join(f"| {name} | {v['P@10']:.3f} | {v['nDCG@10']:.3f} | {v['MRR']:.3f} |" for name, v in m["table"].items())
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

**Как выбирались параметры.** Порог подтверждения P(θ ≥ порог) перебирался на той же симуляции: 0,7 даёт 73% точного
совпадения при 21% занижений, 0,6 — ~78% при 16%, 0,5 — ~79%, но завышений становится больше. Выбрано 0,6: работодателю
важнее, чтобы подтверждённый грейд не был завышен. Проверена и альтернатива «повторная попытка продолжает измерение»
(ответы первой попытки учитываются): на 22% меньше заданий, но точность на 5 п. п. ниже, поэтому попытки независимы.

## 2. Согласованность (test-retest)

Каждый кандидат прошёл тест повторно с новыми случайными экземплярами заданий.

| Метрика | Значение |
|---|---|
| Тот же грейд при повторе | **{pct(t['retest_exact'])}** |
| Взвешенная каппа Коэна | **{t['retest_kappa_w']}** |
| Корреляция θ̂ между попытками | {t['retest_theta_r']} |

Квадратично-взвешенная каппа выше 0,8 считается «почти полным согласием».

## 3. Дискриминативность заданий

| Метрика | Значение |
|---|---|
| Медианная точечно-бисериальная корреляция «способность — верный ответ» | **{t['pbis_median']}** |
| Доля позиций банка с r ≥ 0,2 (порог пригодности задания) | {pct(t['pbis_share_ge_0_2'])} |
| Использовано позиций банка | {t['items_used']} из {t['items_in_bank']} |
| Максимальная экспозиция позиции | {pct(t['max_exposure_rate'])} кандидатов |

![](test_items.png)

![](icc.png)

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

Наименее вариативные позиции (кандидаты на расширение шаблонов):

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

| Система | P@10 | nDCG@10 | MRR |
|---|---|---|---|
{rows}

![](matching.png)

Ключевое: самоописанные данные (ключевые слова, самооценка) ранжируют хуже, чем подтверждённый тестом профиль.
Абляция «без теста» показывает вклад механики тестирования в подбор.

**Роль ФСП.** Для вопроса «подходит ли кандидат вакансии» бонус ФСП почти ничего не добавляет к тесту: тест уже
измеряет ту же способность, а кандидат чуть выше порога так же «подходит», как сильный. Поэтому вес ФСП в соответствии
вакансии подобран небольшим (0,05; перебор весов 0 / 0,03 / 0,05 / 0,1 — в коде валидации). ТЗ отводит ФСП другую
роль — **ранжирование внутри категории** по силе подтверждённого профиля. Здесь ФСП — независимое второе измерение,
и оно помогает: корреляция Спирмена порядка внутри категории с истинной способностью ({m['categories']} категорий):

| Порядок внутри категории | ρ Спирмена с истинной θ |
|---|---|
| Сила профиля: тест + ФСП + актуальность | **{m['in_category_spearman']['full']}** |
| Без ФСП (тест + актуальность) | {m['in_category_spearman']['no_fsp']} |
| Только ФСП | {m['in_category_spearman']['fsp_only']} |

## 7. Разбор текста потребности

{nl['cases']} описаний ({nl['handwritten']} написаны вручную в разных стилях, остальные — шаблонные вакансии с эталоном).

| Метрика | Значение |
|---|---|
| Навыки: точность / полнота / F1 | {nl['skills_precision']} / {nl['skills_recall']} / **{nl['skills_f1']}** |
| F1 по навыкам на ручных текстах | {nl['handwritten_skills_f1']} |
| Специализация | {pct(nl['specialization_acc'])} |
| Грейд (где указан) | {pct(nl['grade_acc'])} |
| Вилка | {pct(nl['salary_acc'])} |
| Формат работы | {pct(nl['format_acc'])} |

## Ограничения и что дальше

- Синтетика проверяет корректность механики, но не реальные параметры заданий. После хакатона: пилот на 50–100
  участниках ФСП, калибровка a и b по реальным ответам (маргинальная оценка максимального правдоподобия), сравнение
  грейда с экспертной оценкой тимлидов (корреляция Спирмена).
- Пилот на людях и экспертная разметка ~100 пар «вакансия — кандидат» дополняют этот отчёт (раздел будет добавлен
  по результатам).
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
    print("4. leaks ...", flush=True)
    summary["leak"] = leak_section(bank, truth, 300 if args.quick else 800)
    print("5. uniqueness ...", flush=True)
    summary["uniqueness"] = uniqueness_section(200 if args.quick else 400)
    print("6. matching ...", flush=True)
    summary["matching"] = matching_section(bank, truth, 400 if args.quick else 900, 20 if args.quick else 40)
    print("7. nlp ...", flush=True)
    summary["nlp"] = nlp_section()
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
