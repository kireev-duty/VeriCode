"""How FSP achievements turn into an employer-facing signal.

Our proposed registry data model (docs/fsp-integration.md): participant (fsp_id, sport rank, rating, region) and
results (event, level, discipline, date, place / participants, team, role in the team, certificate link).
The signal is *additive*: a candidate without FSP history is not penalised, only lacks a bonus.
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
LEVELS = {"regional": ("Региональный", 1.0), "federal": ("Всероссийский", 2.0),
          "international": ("Международный", 3.0)}
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
RELEVANCE = {  # discipline -> specialization -> relevance
    "product": {"backend": 0.9, "frontend": 0.9, "data": 0.8, "qa": 0.8, "devops": 0.8},
    "algorithmic": {"backend": 0.8, "frontend": 0.5, "data": 0.8, "qa": 0.4, "devops": 0.4},
    "security": {"backend": 0.7, "frontend": 0.4, "data": 0.3, "qa": 0.6, "devops": 0.9},
    "drones": {"backend": 0.5, "frontend": 0.2, "data": 0.6, "qa": 0.3, "devops": 0.3},
    "robotics": {"backend": 0.5, "frontend": 0.2, "data": 0.5, "qa": 0.3, "devops": 0.3},
}
HALF_LIFE_YEARS = 2.0


def _age_years(date: datetime, now: datetime) -> float:
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return max(0.0, (now - date).days / 365.25)


def achievement_weight(a, specialization: str | None, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    level = LEVELS.get(a.event_level, ("", 1.0))[1]
    result = RESULTS.get(a.result_type, ("", 0.2))[1]
    decay = 0.5 ** (_age_years(a.date, now) / HALF_LIFE_YEARS)
    rel = RELEVANCE.get(a.discipline, {}).get(specialization or "", 0.6)
    return level * result * decay * rel


def fsp_score(achievements, rank: str, specialization: str | None, now: datetime | None = None
              ) -> tuple[float, list[str]]:
    """0..1 saturating score and short human-readable reasons."""
    if not achievements and not rank:
        return 0.0, []
    weights = sorted(((achievement_weight(a, specialization, now), a) for a in achievements),
                     key=lambda x: -x[0])
    total = sum(w for w, _ in weights) * 0.45 + RANKS.get(rank, 0.0)
    score = 1 - math.exp(-total)
    reasons = []
    if rank:
        reasons.append(f"разряд {rank}")
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
