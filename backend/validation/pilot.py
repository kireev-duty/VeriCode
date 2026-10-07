"""Pilot on real people: `uv run python -m validation.pilot --fetch http://localhost:8080 --token $PILOT_EXPORT_TOKEN`.

Downloads the anonymised export (GET /api/assessment/pilot/export) into docs/validation/pilot/, and computes the
"Пилот" section of the report (validation.run calls pilot_section()):

* agreement of the test estimate θ̂ with external anchors from the post-test survey: commercial experience,
  self-assessed grade, the grade given by a team lead (Spearman ρ; weighted kappa for the lead's grade);
* calibration of the item bank on real answers: observed vs. expected (3PL at θ̂) share of correct answers;
* time per item and the share of timeouts;
* complaints about specific instances ("the correct answer is wrong", "unclear").

With a handful of people this is a sanity check, not a calibration: the report says so and shows the n.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

from app.catalog import GRADE_ORDER
from app.modules.assessment import cat
from app.modules.assessment.irt import ItemParams, p_correct
from validation import stats

PILOT_DIR = Path(__file__).resolve().parents[2] / "docs" / "validation" / "pilot"
MIN_ITEM_RESPONSES = 3


def _spearman(a, b) -> float | None:
    if len(a) < 4:
        return None
    rho = stats.spearman(a, b)
    return None if rho is None else round(rho, 3)


def load_sessions() -> list[dict]:
    """All exported sessions, de-duplicated by session id (several exports may overlap)."""
    seen: dict[tuple, dict] = {}
    for f in sorted(PILOT_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for s in data.get("sessions", []):
            seen[(f.stem.split("-")[0], s["session"])] = s
    return list(seen.values())


def pilot_section() -> dict:
    sessions = [s for s in load_sessions() if s.get("items")]
    out: dict = {"sessions": len(sessions), "candidates": len({s["candidate"] for s in sessions})}
    if not sessions:
        return out
    # one row per person: the last session with a survey, otherwise the last session
    per_person: dict[str, dict] = {}
    for s in sorted(sessions, key=lambda x: x.get("finished_at") or ""):
        if s.get("survey") or s["candidate"] not in per_person or not per_person[s["candidate"]].get("survey"):
            per_person[s["candidate"]] = s
    people = list(per_person.values())
    surveyed = [p for p in people if p.get("survey")]
    out["surveyed"] = len(surveyed)

    def anchor(key: str, conv):
        pairs = [(p["theta"], conv(p["survey"][key])) for p in surveyed if p["survey"].get(key) not in (None, "")]
        return len(pairs), _spearman([a for a, _ in pairs], [b for _, b in pairs])

    out["rho_experience"] = anchor("experience_years", float)
    out["rho_self_grade"] = anchor("self_grade", GRADE_ORDER.index)
    out["rho_lead_grade"] = anchor("lead_grade", GRADE_ORDER.index)
    lead = [(GRADE_ORDER.index(p["grade"] or "intern"), GRADE_ORDER.index(p["survey"]["lead_grade"]))
            for p in surveyed if p["survey"].get("lead_grade") and p.get("grade")]
    if lead:
        out["lead_exact"] = round(float(np.mean([a == b for a, b in lead])), 3)
        out["lead_within_1"] = round(float(np.mean([abs(a - b) <= 1 for a, b in lead])), 3)
        out["lead_n"] = len(lead)

    # item calibration: observed vs. expected share of correct answers at the respondent's estimate
    floors = {b.key: b.params.c for b in cat.build_bank()}
    per_item: dict[str, list[tuple[int, float]]] = {}
    seconds, timeouts, complaints = [], 0, []
    for s in sessions:
        for it in s["items"]:
            p = float(p_correct(s["theta"], ItemParams(it["a"], it["b"], floors.get(it["item_key"], 0.0))))
            per_item.setdefault(it["item_key"], []).append((int(it["correct"]), p))
            if it.get("seconds") is not None:
                seconds.append(it["seconds"] / max(1, it["time_limit_s"]))
                timeouts += it["seconds"] > it["time_limit_s"]
            if it.get("report"):
                complaints.append({"item": it["item_key"], "reason": it["report"]["reason"],
                                   "text": it["report"].get("text", "")})
    resid = [o - e for rows in per_item.values() for o, e in rows]
    out["responses"] = len(resid)
    out["mean_residual"] = round(float(np.mean(resid)), 3)  # > 0: items easier than the priors say
    worst = []
    for key, rows in per_item.items():
        if len(rows) >= MIN_ITEM_RESPONSES:
            obs, exp = np.mean([o for o, _ in rows]), np.mean([e for _, e in rows])
            worst.append({"item": key, "n": len(rows), "observed": round(float(obs), 2), "expected": round(float(exp), 2)})
    out["items_ge_min"] = len(worst)
    out["worst_items"] = sorted(worst, key=lambda r: -abs(r["observed"] - r["expected"]))[:5]
    if seconds:
        out["time_share_median"] = round(float(np.median(seconds)), 2)
        out["timeouts_share"] = round(timeouts / len(seconds), 3)
    out["complaints"] = complaints
    return out


def pilot_block(p: dict) -> str:
    head = """## 9. Пилот на людях

Синтетика проверяет механику, но не реальные параметры заданий. Поэтому тест проходят живые люди, после теста
заполняют необязательную анкету (стаж, должность, самооценка, грейд по оценке тимлида) и могут пожаловаться на
конкретное задание. Выгрузка обезличена (кандидат заменён псевдонимом): `GET /api/assessment/pilot/export` по токену
`PILOT_EXPORT_TOKEN`, затем `uv run python -m validation.pilot --fetch <адрес стенда> --token <токен>`.
"""
    if not p.get("sessions"):
        return head + "\nДанных пилота пока нет; раздел заполнится после выгрузки.\n"

    def rho(v):
        n, r = v
        return f"{r} (n = {n})" if r is not None else f"недостаточно данных (n = {n})"

    lead = (f"| Грейд по тесту совпал с оценкой тимлида | {p['lead_exact'] * 100:.0f}% (±1 грейд — "
            f"{p['lead_within_1'] * 100:.0f}%, n = {p['lead_n']}) |\n" if "lead_n" in p else "")
    worst = "\n".join(f"| `{w['item']}` | {w['n']} | {w['observed']} | {w['expected']} |" for w in p["worst_items"])
    complaints = "\n".join(f"- `{c['item']}`: {c['reason']}" + (f" — «{c['text']}»" if c["text"] else "")
                           for c in p["complaints"]) or "- жалоб нет"
    timing = (f"| Медиана времени на задание (доля лимита) | {p['time_share_median']} |\n"
              f"| Доля ответов после лимита | {p['timeouts_share'] * 100:.1f}% |\n" if "time_share_median" in p else "")
    return head + f"""
Сессий: {p['sessions']}, людей: {p['candidates']}, заполнили анкету: {p['surveyed']}. При такой выборке это проверка
здравого смысла, а не калибровка: интервалы широкие, поэтому n указано у каждой цифры.

| Согласие оценки теста θ̂ с внешними ориентирами | ρ Спирмена |
|---|---|
| Коммерческий стаж | {rho(p['rho_experience'])} |
| Самооценка грейда | {rho(p['rho_self_grade'])} |
| Грейд по оценке тимлида | {rho(p['rho_lead_grade'])} |

| Метрика | Значение |
|---|---|
{lead}| Ответов | {p['responses']} |
| Средний остаток «наблюдаемая − ожидаемая доля верных» | {p['mean_residual']:+.3f} |
{timing}
Позиции с наибольшим расхождением (не меньше {MIN_ITEM_RESPONSES} ответов):

| Позиция | Ответов | Доля верных | Ожидалось по 3PL |
|---|---|---|---|
{worst}

Жалобы на задания:

{complaints}
"""


def fetch(base_url: str, token: str) -> Path:
    r = httpx.get(base_url.rstrip("/") + "/api/assessment/pilot/export", headers={"X-Pilot-Token": token},
                  timeout=60)
    r.raise_for_status()
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    out = PILOT_DIR / f"pilot-{datetime.now(UTC):%Y%m%d-%H%M}.json"
    out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", metavar="URL", help="base URL of the stand, e.g. http://localhost:8080")
    ap.add_argument("--token", default="", help="PILOT_EXPORT_TOKEN of the stand")
    args = ap.parse_args()
    if args.fetch:
        print("saved", fetch(args.fetch, args.token))
    print(json.dumps(pilot_section(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
