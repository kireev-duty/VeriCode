"""Synthetic population with a known latent truth.

Every candidate has a true ability theta (and per-skill abilities); everything observable - declared grade,
stack, experience, salary expectations, *test answers* - is drawn from it with noise. Grades in the demo DB are
therefore assigned by actually running the adaptive test on simulated answers, and the offline validation
(validation/) can compare system output with the hidden truth.
"""

import math
import random
from dataclasses import dataclass, field

from app.catalog import GRADE_ORDER, SPEC_BY_ID, SPECIALIZATIONS, grade_from_theta
from app.modules.assessment import cat
from app.modules.assessment.irt import ItemParams, p_correct

MALE = ["Александр", "Дмитрий", "Максим", "Иван", "Артём", "Никита", "Михаил", "Егор", "Андрей", "Илья", "Кирилл",
        "Роман", "Сергей", "Тимур", "Павел", "Глеб", "Денис", "Ярослав", "Арсений", "Владимир"]
FEMALE = ["Анна", "Мария", "Елизавета", "Дарья", "Полина", "Алиса", "Виктория", "Екатерина", "Софья", "Ксения",
          "Валерия", "Анастасия", "Алина", "Ольга", "Вероника", "Юлия", "Ирина", "Арина", "Диана", "Ева"]
SURNAMES = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков",
            "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов",
            "Степанов", "Николаев", "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв",
            "Борисов", "Яковлев", "Григорьев", "Романов", "Воробьёв", "Сергеев", "Кузьмин", "Фролов", "Белов"]
CITIES = ["Москва"] * 6 + ["Санкт-Петербург"] * 3 + ["Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород",
                                                      "Самара", "Краснодар", "Томск", "Иннополис", "Пермь", "Воронеж"]
EMPLOYERS = ["ООО «Цифровые решения»", "ИТ-интегратор «Вектор»", "Банк «Северный»", "Маркетплейс «Корзина»",
             "Студия «Пиксель»", "Телеком «Сигнал»", "Логистика «Маршрут»", "Госсервис «Портал»", "Стартап «Облако»",
             "Агентство «Код»", "EdTech «Учи»", "Медтех «Пульс»"]
HEADLINES = {
    "backend": ["Python-разработчик", "Backend-разработчик (Python/Go)", "Java backend-инженер",
                "Разработчик микросервисов", "Backend developer"],
    "frontend": ["Frontend-разработчик (React)", "Frontend developer", "Vue.js разработчик",
                 "Разработчик интерфейсов", "React/TypeScript инженер"],
    "data": ["Data Scientist", "ML-инженер", "Аналитик данных", "NLP-инженер", "Computer Vision инженер"],
    "qa": ["QA-инженер", "Инженер по автоматизации тестирования", "Тестировщик ПО", "QA Automation (Python)"],
    "devops": ["DevOps-инженер", "SRE-инженер", "Инженер инфраструктуры", "Platform engineer"],
}
ABOUT = {
    "backend": "Проектирую и пишу сервисы и API, работаю с базами данных и очередями. Покрываю код тестами, "
               "участвую в код-ревью и разборе инцидентов.",
    "frontend": "Делаю быстрые и доступные интерфейсы, работаю с дизайн-системами и состоянием приложения, "
                "оптимизирую производительность и собираю фронтенд в CI.",
    "data": "Строю модели машинного обучения от разведочного анализа до продакшена, считаю A/B-тесты, "
            "работаю с SQL и большими выборками.",
    "qa": "Проектирую тест-кейсы и чек-листы, автоматизирую регресс, тестирую API и интеграции, "
          "выстраиваю процессы качества в команде.",
    "devops": "Поддерживаю инфраструктуру в Kubernetes, настраиваю CI/CD и мониторинг, автоматизирую рутину "
              "и отвечаю за надёжность сервисов.",
}
BASE_SALARY = {"intern": 65_000, "junior": 120_000, "middle": 230_000, "senior": 360_000}
SPEC_SALARY = {"backend": 1.0, "frontend": 0.95, "data": 1.05, "qa": 0.85, "devops": 1.05}
SOFT = ["Командная работа", "Коммуникация", "Лидерство", "Самоорганизация", "Наставничество", "Критическое мышление",
        "Публичные выступления", "Работа в условиях дедлайнов"]


def market_salary(spec: str, grade: str) -> int:
    return int(BASE_SALARY[grade] * SPEC_SALARY[spec])


@dataclass
class SynthCandidate:
    spec: str
    theta: float  # true ability
    skill_theta: dict[str, float]  # true per-skill ability
    declared_grade: str
    skills: list[dict]
    experience_years: float
    city: str
    work_formats: list[str]
    relocation: bool
    salary_expectation: int
    full_name: str
    female: bool
    headline: str
    about: str
    experience: list[dict]
    team_roles: list[str]
    soft_skills: list[str]
    fsp_id: str | None
    activity_days: int  # days since the last activity
    test: dict = field(default_factory=dict)  # result of the simulated test

    @property
    def true_grade(self) -> str:
        return grade_from_theta(self.theta)


def make_candidate(rng: random.Random, spec: str | None = None, idx: int = 0) -> SynthCandidate:
    spec = spec or rng.choices([s.id for s in SPECIALIZATIONS], weights=[32, 24, 16, 14, 14])[0]
    sp = SPEC_BY_ID[spec]
    theta = rng.gauss(0.15, 0.95)
    # per-skill ability: shared ability + skill-specific deviation
    pool = list(dict.fromkeys(list(sp.core_skills) + list(sp.stack_options)))
    skill_theta = {s: theta + rng.gauss(0, 0.45) for s in pool}
    years = max(0.0, round(2.6 + 2.3 * theta + rng.gauss(0, 1.2), 1))
    # self-assessment is noisy and slightly optimistic
    declared = grade_from_theta(theta + rng.gauss(0.15, 0.55))
    # the stack people list grows with experience; stronger skills are listed more often
    n_skills = max(3, min(len(sp.stack_options), int(3 + years * 0.8 + rng.random() * 3)))
    weights = [math.exp(skill_theta.get(s, theta) - theta) * (2.0 if s in sp.core_skills else 1.0)
               for s in sp.stack_options]
    chosen: list[str] = []
    while len(chosen) < n_skills:
        s = rng.choices(sp.stack_options, weights=weights)[0]
        if s not in chosen:
            chosen.append(s)
    for core in sp.core_skills:  # most people of a specialization list its main language / tool
        if core in sp.stack_options and core not in chosen and rng.random() < 0.7:
            chosen.append(core)
    skills = [{"id": s, "years": round(max(0.5, min(years, years * rng.uniform(0.4, 1.0))), 1)} for s in chosen]
    for extra in ("git", "docker", "sql"):
        if extra not in chosen and rng.random() < 0.45:
            skills.append({"id": extra, "years": round(max(0.5, years * rng.uniform(0.3, 0.9)), 1)})
    true_g = grade_from_theta(theta)
    salary = int(market_salary(spec, true_g) * math.exp(rng.gauss(0.05, 0.16)) / 5000) * 5000
    female = rng.random() < 0.3
    first = rng.choice(FEMALE if female else MALE)
    last = rng.choice(SURNAMES) + ("а" if female else "")
    city = rng.choice(CITIES)
    formats = rng.choice([["remote"], ["remote", "hybrid"], ["hybrid"], ["office", "hybrid"], ["office"],
                          ["remote", "hybrid", "office"]])
    exp_entries, left = [], years
    end_year = 2026
    while left >= 0.8 and len(exp_entries) < 3:
        dur = min(left, round(rng.uniform(1, 3.5), 1))
        start = end_year - max(1, round(dur))
        exp_entries.append({"company": rng.choice(EMPLOYERS), "position": rng.choice(HEADLINES[spec]),
                            "from": str(start), "to": "" if not exp_entries else str(end_year),
                            "summary": rng.choice([
                                "Разработка новых модулей, код-ревью, менторинг стажёров.",
                                "Поддержка и развитие продукта, оптимизация производительности.",
                                "Запуск сервиса с нуля, проектирование архитектуры и CI.",
                                "Работа в продуктовой команде из 6 человек, участие в планировании."])})
        left -= dur
        end_year = start
    roles = ["Разработчик"]
    if theta > 0.8 and rng.random() < 0.5:
        roles.append(rng.choice(["Тимлид", "Ментор", "Архитектор"]))
    fsp_id = f"FSP-{100001 + idx * 7:06d}" if rng.random() < 0.4 else None
    if fsp_id and fsp_id.endswith("0"):
        fsp_id = fsp_id[:-1] + "1"
    return SynthCandidate(
        spec=spec, theta=theta, skill_theta=skill_theta, declared_grade=declared, skills=skills,
        experience_years=years, city=city, work_formats=formats, relocation=rng.random() < 0.25,
        salary_expectation=salary, full_name=f"{first} {last}", female=female,
        headline=rng.choice(HEADLINES[spec]),
        about=ABOUT[spec], experience=exp_entries, team_roles=roles, soft_skills=rng.sample(SOFT, rng.randint(2, 4)),
        fsp_id=fsp_id, activity_days=int(rng.expovariate(1 / 60)),
    )


def true_params(bank: list[cat.BankItem], rng: random.Random, noise_b: float = 0.25, noise_a: float = 0.15
                ) -> dict[str, ItemParams]:
    """The real item parameters differ from the expert priors: the engine never sees these."""
    return {it.key: ItemParams(max(0.4, it.params.a * math.exp(rng.gauss(0, noise_a))),
                               it.params.b + rng.gauss(0, noise_b), it.params.c) for it in bank}


def run_test(rng: random.Random, c: SynthCandidate, bank: list[cat.BankItem], truth: dict[str, ItemParams],
             target: str, blueprint: dict[str, float], leaked: set[str] | None = None) -> tuple[cat.Decision, list]:
    """Simulates one adaptive test session. leaked: item keys whose answers the candidate knows in advance."""
    responses: list[cat.Response] = []
    while True:
        it = cat.select_next(bank, blueprint, responses, cat.selection_theta(responses, target), rng)
        if it is None:
            break
        if leaked and it.key in leaked:
            ok = True
        else:
            th = c.skill_theta.get(it.skill, c.theta)
            ok = rng.random() < float(p_correct(th, truth[it.key]))
        responses.append(cat.Response(it, ok))
        if cat.should_stop(responses, target):
            break
    return cat.decide(responses, target), responses


def assign_grade(rng: random.Random, c: SynthCandidate, bank, truth) -> dict:
    """Candidate flow per policy: test on the declared grade, if not confirmed - immediately one grade lower,
    until a grade is confirmed (intern always is)."""
    bp = cat.blueprint_for_specialization(SPEC_BY_ID[c.spec].core_skills, [s["id"] for s in c.skills], bank)
    target = c.declared_grade
    attempts = []
    while True:
        d, resp = run_test(rng, c, bank, truth, target, bp)
        attempts.append({"target": target, "outcome": d.outcome, "theta": d.theta, "se": d.se, "items": len(resp),
                         "p_target": d.p_target, "skill_theta": d.skill_theta})
        if d.grade is not None:
            return {"grade": d.grade, "theta": d.theta, "se": d.se, "skill_theta": d.skill_theta,
                    "attempts": attempts, "blueprint": bp, "responses": resp}
        target = GRADE_ORDER[GRADE_ORDER.index(target) - 1]


# ------------------------------------------------------------------------------------------------ vacancies

VACANCY_TEMPLATES = {
    "backend": [
        ("Python-разработчик", ["python", "django", "postgresql"], ["redis", "docker"]),
        ("Backend-разработчик (FastAPI)", ["python", "fastapi", "postgresql", "asyncio"], ["kafka", "kubernetes"]),
        ("Go-разработчик", ["go", "postgresql", "grpc"], ["kafka", "kubernetes"]),
        ("Java-разработчик", ["java", "spring", "postgresql"], ["kafka", "microservices"]),
        ("Backend-разработчик платёжного шлюза", ["python", "sql", "rest"], ["rabbitmq", "system_design"]),
    ],
    "frontend": [
        ("Frontend-разработчик (React)", ["javascript", "typescript", "react"], ["redux", "webpack"]),
        ("Vue-разработчик", ["javascript", "vue", "html_css"], ["typescript"]),
        ("Frontend-разработчик дизайн-системы", ["typescript", "react", "html_css"], ["frontend_perf", "browser"]),
    ],
    "data": [
        ("Data Scientist", ["python", "ml", "statistics", "sql"], ["pandas", "dl"]),
        ("ML-инженер (NLP)", ["python", "dl", "nlp"], ["ml", "docker"]),
        ("Аналитик данных", ["sql", "statistics", "pandas"], ["python", "clickhouse"]),
    ],
    "qa": [
        ("QA-инженер", ["test_design", "api_testing", "sql"], ["autotests"]),
        ("Инженер по автоматизации тестирования", ["autotests", "python", "api_testing"], ["load_testing", "ci_cd"]),
    ],
    "devops": [
        ("DevOps-инженер", ["linux", "docker", "kubernetes", "ci_cd"], ["terraform", "monitoring"]),
        ("SRE-инженер", ["linux", "kubernetes", "monitoring"], ["go", "python"]),
    ],
}
TEAMS = ["Команда платёжных сервисов", "Продуктовая команда личного кабинета", "Команда поиска и рекомендаций",
         "Команда внутренней платформы", "Команда мобильного банка", "Команда аналитики"]


def vacancy_text(rng: random.Random, title: str, grade: str, must: list[str], nice: list[str], fmt: list[str],
                 city: str, lo: int, hi: int) -> str:
    from app.catalog import SKILL_BY_ID, WORK_FORMATS
    m = ", ".join(SKILL_BY_ID[s].title for s in must)
    n = ", ".join(SKILL_BY_ID[s].title for s in nice)
    years = {"intern": "без опыта", "junior": "от 1 года", "middle": "от 2–3 лет", "senior": "от 5 лет"}[grade]
    return (f"{rng.choice(TEAMS)} ищет: {title} ({grade.capitalize()}).\n"
            f"Требования: опыт {years}; {m}.\n" + (f"Будет плюсом: {n}.\n" if n else "")
            + f"Формат: {', '.join(WORK_FORMATS[f].lower() for f in fmt)}" + (f", {city}" if city else "")
            + f". Зарплата {lo:,}–{hi:,} ₽.".replace(",", " "))


def make_vacancy(rng: random.Random, spec: str | None = None, grade: str | None = None) -> dict:
    spec = spec or rng.choice(list(VACANCY_TEMPLATES))
    title, must, nice = rng.choice(VACANCY_TEMPLATES[spec])
    grade = grade or rng.choices(GRADE_ORDER, weights=[1, 3, 5, 3])[0]
    base = market_salary(spec, grade)
    lo = int(base * rng.uniform(0.8, 0.95) / 10000) * 10000
    hi = int(base * rng.uniform(1.05, 1.3) / 10000) * 10000
    fmt = rng.choice([["remote"], ["hybrid"], ["office", "hybrid"], ["remote", "hybrid"]])
    city = "" if fmt == ["remote"] else rng.choice(["Москва", "Москва", "Санкт-Петербург", "Казань", "Новосибирск"])
    return {"title": f"{title}", "specialization": spec, "grade": grade, "must_skills": list(must),
            "nice_skills": list(nice), "work_formats": fmt, "city": city, "salary_from": lo, "salary_to": hi,
            "description": vacancy_text(rng, title, grade, must, nice, fmt, city, lo, hi)}
