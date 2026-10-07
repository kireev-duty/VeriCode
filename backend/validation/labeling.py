"""Expert labeling set for matching: `uv run python -m validation.labeling`.

Builds ~100 "vacancy - candidate" pairs from the same synthetic test set as the matching section of the report
(validation.run.build_world) and writes a self-contained form docs/validation/labeling/index.html. An expert rates
each pair 0-3 without seeing any system's score and downloads a JSON file; files put into docs/validation/labels/
are picked up by `validation.run` (section "Экспертная разметка").

Pooling (as in TREC evaluations), so that the set does not favour our system: for every vacancy the pool is the
top-3 of our scoring, the top-3 of the keyword baseline, the top-2 of BM25, and random candidates of the same
specialization up to POOL_SIZE; the order within a vacancy is shuffled.
"""

import hashlib
import json
import random
import zlib
from datetime import timedelta
from pathlib import Path

from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID, WORK_FORMATS, grade_from_theta
from app.modules.assessment import cat
from app.modules.fsp.scoring import DISCIPLINES, LEVELS, RESULTS
from app.seed import synth
from validation.run import OUT, build_world, synthetic_achievements, system_scores

VACANCIES_PER_SPEC = 2
POOL_SIZE = 10
POOL_PLAN = (("full", 3), ("keywords", 3), ("bm25", 2))
LABELING_DIR = OUT / "labeling"
TEMPLATE = Path(__file__).with_name("labeling_form.html")


def pick_vacancies(vacancies: list[dict]) -> list[int]:
    per_spec: dict[str, list[int]] = {}
    for i, v in enumerate(vacancies):
        per_spec.setdefault(v["specialization"], []).append(i)
    return sorted(i for ids in per_spec.values() for i in ids[:VACANCIES_PER_SPEC])


def pool_for(world: dict, vi: int, rng: random.Random) -> list[int]:
    v = world["vacancies"][vi]
    chosen: list[int] = []
    for mode, k in POOL_PLAN:
        sc = system_scores(world, v, mode)
        for i in sorted(sc, key=lambda i: -sc[i]):
            if k == 0:
                break
            if i not in chosen:
                chosen.append(i)
                k -= 1
    rest = [i for i, c in enumerate(world["people"]) if c.spec == v["specialization"] and i not in chosen]
    chosen += rng.sample(rest, POOL_SIZE - len(chosen))
    rng.shuffle(chosen)
    return chosen


def vacancy_public(v: dict) -> dict:
    return {"title": v["title"], "specialization": SPEC_BY_ID[v["specialization"]].short,
            "grade": GRADE_BY_ID[v["grade"]].title, "must": [SKILL_BY_ID[s].title for s in v["must_skills"]],
            "nice": [SKILL_BY_ID[s].title for s in v["nice_skills"]],
            "formats": [WORK_FORMATS[f] for f in v["work_formats"]], "city": v["city"],
            "salary_from": v["salary_from"], "salary_to": v["salary_to"], "description": v["description"]}


def candidate_public(c: synth.SynthCandidate, now) -> dict:
    """What a recruiter would see after contacts are opened, minus the name: profile, test result, FSP."""
    tested = c.test["skill_theta"]
    skills = [{"title": SKILL_BY_ID[s["id"]].title, "years": s["years"],
               "level": GRADE_BY_ID[grade_from_theta(tested[s["id"]])].title if s["id"] in tested else None}
              for s in c.skills if s["id"] in SKILL_BY_ID]
    listed = {s["id"] for s in c.skills}
    skills += [{"title": SKILL_BY_ID[s].title, "years": None, "level": GRADE_BY_ID[grade_from_theta(t)].title}
               for s, t in tested.items() if s not in listed and s in SKILL_BY_ID]
    fsp = []
    rank = ""
    if c.fsp_id:  # the same seed as validation.run._view: the expert sees what the scoring sees
        ach, rank = synthetic_achievements(c, random.Random(zlib.crc32(c.full_name.encode()) + int(c.theta * 1000)),
                                           now)
        fsp = [{"level": LEVELS[a.event_level][0], "result": RESULTS[a.result_type][0],
                "discipline": DISCIPLINES[a.discipline], "year": a.date.year} for a in ach]
    return {"headline": c.headline, "about": c.about, "experience_years": c.experience_years,
            "experience": [{"position": e["position"], "from": e["from"], "to": e["to"] or "н. в.",
                            "summary": e["summary"]} for e in c.experience],
            "grade": GRADE_BY_ID[c.test["grade"]].title, "skills": skills, "fsp": fsp, "fsp_rank": rank,
            "salary_expectation": c.salary_expectation, "formats": [WORK_FORMATS[f] for f in c.work_formats],
            "city": c.city, "relocation": c.relocation, "team_roles": c.team_roles,
            "last_activity": (now - timedelta(days=c.activity_days)).strftime("%d.%m.%Y")}


def build_pairs(world: dict) -> dict:
    rng = random.Random(2026)
    groups = []
    for vi in pick_vacancies(world["vacancies"]):
        v = world["vacancies"][vi]
        groups.append({"vacancy_id": f"v{vi}", "vacancy": vacancy_public(v),
                       "candidates": [{"pair_id": f"v{vi}-c{ci}", "candidate": candidate_public(world["people"][ci],
                                                                                                world["now"])}
                                      for ci in pool_for(world, vi, rng)]})
    ids = [p["pair_id"] for g in groups for p in g["candidates"]]
    version = hashlib.sha256(",".join(ids).encode()).hexdigest()[:12]
    return {"version": version, "pairs": len(ids), "groups": groups}


def pair_index(pair_id: str) -> tuple[int, int]:
    v, c = pair_id.split("-")
    return int(v[1:]), int(c[1:])


def main() -> None:
    bank = cat.build_bank()
    truth = synth.true_params(bank, random.Random(7))
    world = build_world(bank, truth)
    data = build_pairs(world)
    LABELING_DIR.mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False)
    (LABELING_DIR / "pairs.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__PAIRS_JSON__", payload.replace("</", "<\\/"))
    (LABELING_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"{data['pairs']} pairs, version {data['version']} -> {LABELING_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
