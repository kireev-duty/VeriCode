"""How FSP achievements turn into an employer-facing signal.

Our proposed registry data model (docs/fsp-integration.md): participant (fsp_id, sport rank, rating, region) and
results (event, level, discipline, date, place / participants, team, role in the team, certificate link).
The signal is *additive*: a candidate without FSP history is not penalised, only lacks a bonus.
It only moves a candidate inside a category; the grade itself comes from the test alone.

Per the organisers' Q&A: no hierarchy of events or disciplines (a regional hackathon counts as much as a national
championship), what matters is how many events and the result in each. Plain participations are capped, so a
profile cannot be pumped up with online qualifier attendance.
"""

import math
from datetime import UTC, datetime

DISCIPLINES = {
    "product": "Продуктовое программирование",
    "algorithmic": "Алгоритмическое программирование",
    "security": "Программирование систем информационной безопасности",
    "drones": "Программирование беспилотных авиационных систем",
    "robotics": "Программирование робототехники",
}
LEVELS = {"regional": ("Региональный",), "federal": ("Всероссийский",),  # labels only, not weighted
          "international": ("Международный",)}
RESULTS = {"winner": ("Победитель", 1.0), "prize": ("Призёр", 0.75), "finalist": ("Финалист", 0.45),
           "participant": ("Участник", 0.2)}
RANKS = {"": 0.0, "III": 0.1, "II": 0.2, "I": 0.35, "КМС": 0.6, "МС": 0.8, "МСМК": 1.0}

DISCIPLINE_SKILLS = {
    "product": ["system_design", "rest", "git"],
    "algorithmic": ["algorithms", "cpp", "python"],
    "security": ["security", "linux", "http"],
    "drones": ["cpp", "python", "cv"],
    "robotics": ["cpp", "python"],
}
HALF_LIFE_YEARS = 2.0
SCALE = 0.7  # winner this year -> score ~0.5
PARTICIPATION_CAP = 0.3  # max contribution of all plain participations to the total (< one prize place)


def _age_years(date: datetime, now: datetime) -> float:
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return max(0.0, (now - date).days / 365.25)


def achievement_weight(a, now: datetime | None = None) -> float:
    """Result x recency. Level and discipline deliberately do not matter."""
    now = now or datetime.now(UTC)
    result = RESULTS.get(a.result_type, ("", 0.2))[1]
    decay = 0.5 ** (_age_years(a.date, now) / HALF_LIFE_YEARS)
    return result * decay


def fsp_score(achievements, rank: str, now: datetime | None = None) -> tuple[float, list[str]]:
    """0..1 saturating score and short human-readable reasons."""
    if not achievements and not rank:
        return 0.0, []
    weights = sorted(((achievement_weight(a, now), a) for a in achievements), key=lambda x: -x[0])
    placed = sum(w for w, a in weights if a.result_type != "participant") * SCALE
    participated = min(PARTICIPATION_CAP, sum(w for w, a in weights if a.result_type == "participant") * SCALE)
    total = placed + participated + RANKS.get(rank, 0.0)
    score = 1 - math.exp(-total)
    reasons = []
    if rank:
        reasons.append(f"разряд {rank}")
    if achievements:
        n_placed = sum(1 for a in achievements if a.result_type in ("winner", "prize"))
        reasons.append(f"{len(achievements)} соревн., из них призовых: {n_placed}")
    for _, a in weights[:2]:
        res = RESULTS.get(a.result_type, ("Участник",))[0].lower()
        reasons.append(f"{res}: {a.event_name} ({a.date.year})")
    return round(score, 3), reasons


def skills_from_achievements(achievements) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in achievements:
        for s in DISCIPLINE_SKILLS.get(a.discipline, []):
            out[s] = out.get(s, 0) + 1
    return out
