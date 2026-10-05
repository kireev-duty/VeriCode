"""Reference data: specializations, grades, skills and the skill-similarity graph.

The catalog lives in code (not in the DB): it is versioned with the scoring logic that depends on it
and is exposed read-only through /api/catalog.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------------------------
# Grades. theta_min is the lower bound on the ability scale (IRT, N(0,1) population) for the grade.
# ---------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Grade:
    id: str
    title: str
    order: int
    theta_min: float
    description: str


GRADES: list[Grade] = [
    Grade("intern", "Intern", 0, -99.0, "Стажёр: опыт до года, учебные и пет-проекты"),
    Grade("junior", "Junior", 1, -0.9, "Решает типовые задачи под присмотром, опыт 1–2 года"),
    Grade("middle", "Middle", 2, 0.1, "Самостоятельно ведёт задачи и модули, опыт 2–5 лет"),
    Grade("senior", "Senior", 3, 1.1, "Проектирует системы, отвечает за качество и менторит, опыт 5+ лет"),
]
GRADE_BY_ID = {g.id: g for g in GRADES}
GRADE_ORDER = [g.id for g in GRADES]


def grade_index(grade_id: str) -> int:
    return GRADE_BY_ID[grade_id].order


def grade_center(grade_id: str) -> float:
    """Middle of the grade's theta band: used as the prior mean when a candidate declares this grade."""
    i = grade_index(grade_id)
    lo = GRADES[i].theta_min if i > 0 else -2.0
    hi = GRADES[i + 1].theta_min if i + 1 < len(GRADES) else 2.2
    return round((lo + hi) / 2, 2)


def grade_from_theta(theta: float) -> str:
    current = GRADES[0].id
    for g in GRADES:
        if theta >= g.theta_min:
            current = g.id
    return current


# ---------------------------------------------------------------------------------------------------------------
# Skills. related = {skill_id: similarity 0..1}; the graph is symmetrised in SKILL_SIM below.
# ---------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    id: str
    title: str
    group: str
    synonyms: tuple[str, ...] = ()
    related: dict[str, float] = field(default_factory=dict)


_S = Skill
SKILLS: list[Skill] = [
    # languages
    _S("python", "Python", "language", ("python3", "питон", "пайтон", "py")),
    _S("java", "Java", "language", (), {"kotlin": 0.6, "csharp": 0.5}),
    _S("kotlin", "Kotlin", "language", (), {"java": 0.6}),
    _S("go", "Go", "language", ("golang",)),
    _S("csharp", "C#", "language", ("c#", ".net", "dotnet", "asp.net"), {"java": 0.5}),
    _S("cpp", "C++", "language", ("c++", "cpp"), {"algorithms": 0.3}),
    _S("javascript", "JavaScript", "language", ("js", "ecmascript", "es6"), {"typescript": 0.8}),
    _S("typescript", "TypeScript", "language", ("ts",), {"javascript": 0.8}),
    _S("php", "PHP", "language", (), {"laravel": 0.5}),
    _S("sql", "SQL", "data", ("t-sql", "pl/sql", "plpgsql")),
    _S("bash", "Bash", "ops", ("shell", "sh", "zsh", "командная строка")),
    # backend
    _S("django", "Django", "backend", ("drf", "django rest framework"), {"fastapi": 0.6, "flask": 0.7, "python": 0.4}),
    _S("fastapi", "FastAPI", "backend", (), {"django": 0.6, "flask": 0.7, "python": 0.4}),
    _S("flask", "Flask", "backend", (), {"fastapi": 0.7, "django": 0.7, "python": 0.4}),
    _S("spring", "Spring", "backend", ("spring boot", "springboot"), {"java": 0.4}),
    _S("nodejs", "Node.js", "backend", ("node", "node.js", "express", "nestjs", "nest.js"), {"javascript": 0.4}),
    _S("laravel", "Laravel", "backend", (), {"php": 0.5}),
    _S("rest", "REST API", "backend", ("restful", "rest api", "openapi", "swagger"), {"http": 0.6, "grpc": 0.4}),
    _S("grpc", "gRPC", "backend", ("protobuf",), {"rest": 0.4}),
    _S("http", "HTTP", "backend", ("https", "tcp/ip", "сети"), {"rest": 0.6}),
    _S("asyncio", "Асинхронность", "backend", ("async", "asyncio", "async/await", "event loop")),
    _S("microservices", "Микросервисы", "backend", ("microservices", "микросервисная архитектура"),
       {"kafka": 0.3, "docker": 0.3}),
    _S("system_design", "Проектирование систем", "backend", ("system design", "архитектура", "highload"),
       {"microservices": 0.5}),
    # data storage
    _S("postgresql", "PostgreSQL", "data", ("postgres", "postgre", "psql"), {"mysql": 0.7, "sql": 0.5}),
    _S("mysql", "MySQL", "data", ("mariadb",), {"postgresql": 0.7, "sql": 0.5}),
    _S("mongodb", "MongoDB", "data", ("mongo",)),
    _S("redis", "Redis", "data", (), {"rabbitmq": 0.2}),
    _S("kafka", "Kafka", "data", ("apache kafka",), {"rabbitmq": 0.6}),
    _S("rabbitmq", "RabbitMQ", "data", ("rabbit", "amqp"), {"kafka": 0.6}),
    _S("clickhouse", "ClickHouse", "data", (), {"sql": 0.4}),
    # frontend
    _S("html_css", "HTML/CSS", "frontend", ("html", "css", "html5", "css3", "вёрстка", "верстка", "sass", "scss")),
    _S("react", "React", "frontend", ("react.js", "reactjs", "next.js", "nextjs"), {"vue": 0.5, "angular": 0.4}),
    _S("vue", "Vue", "frontend", ("vue.js", "vuejs", "nuxt"), {"react": 0.5, "angular": 0.4}),
    _S("angular", "Angular", "frontend", (), {"react": 0.4, "vue": 0.4, "typescript": 0.3}),
    _S("redux", "Redux", "frontend", ("mobx", "zustand", "state management"), {"react": 0.5}),
    _S("webpack", "Сборщики", "frontend", ("webpack", "vite", "rollup", "babel")),
    _S("browser", "Браузер и Web API", "frontend", ("dom", "web api", "браузер")),
    _S("frontend_perf", "Производительность фронтенда", "frontend", ("web vitals", "lighthouse")),
    # data / ml
    _S("pandas", "Pandas", "ml", ("numpy",), {"python": 0.4, "statistics": 0.3}),
    _S("statistics", "Статистика", "ml", ("теорвер", "a/b тесты", "ab-тесты", "a/b testing", "probability"),
       {"ml": 0.5}),
    _S("ml", "Машинное обучение", "ml", ("machine learning", "scikit-learn", "sklearn", "catboost", "xgboost",
                                           "lightgbm"), {"statistics": 0.5, "dl": 0.6}),
    _S("dl", "Глубокое обучение", "ml", ("deep learning", "pytorch", "tensorflow", "keras", "нейросети"),
       {"ml": 0.6, "nlp": 0.5, "cv": 0.5}),
    _S("nlp", "NLP", "ml", ("llm", "transformers", "bert"), {"dl": 0.5}),
    _S("cv", "Компьютерное зрение", "ml", ("computer vision", "opencv", "yolo"), {"dl": 0.5}),
    # qa
    _S("test_design", "Тест-дизайн", "qa", ("тест-кейсы", "чек-листы", "test cases", "ручное тестирование"),
       {"autotests": 0.4}),
    _S("autotests", "Автотесты", "qa", ("pytest", "selenium", "playwright", "cypress", "junit", "автоматизация"),
       {"test_design": 0.4}),
    _S("api_testing", "Тестирование API", "qa", ("postman", "api testing"), {"rest": 0.5, "autotests": 0.4}),
    _S("load_testing", "Нагрузочное тестирование", "qa", ("jmeter", "locust", "k6")),
    # devops
    _S("linux", "Linux", "ops", ("unix", "ubuntu", "debian", "centos"), {"bash": 0.6}),
    _S("docker", "Docker", "ops", ("docker-compose", "docker compose", "контейнеры"), {"kubernetes": 0.5}),
    _S("kubernetes", "Kubernetes", "ops", ("k8s", "helm", "openshift"), {"docker": 0.5}),
    _S("ci_cd", "CI/CD", "ops", ("gitlab ci", "github actions", "jenkins", "teamcity", "argocd")),
    _S("terraform", "Terraform", "ops", ("ansible", "iac", "infrastructure as code")),
    _S("monitoring", "Мониторинг", "ops", ("prometheus", "grafana", "zabbix", "elk", "observability")),
    _S("cloud", "Облака", "ops", ("aws", "yandex cloud", "gcp", "azure", "selectel")),
    # cross-cutting
    _S("git", "Git", "general", ("github", "gitlab")),
    _S("algorithms", "Алгоритмы и структуры данных", "general",
       ("алгоритмы", "структуры данных", "leetcode", "спортивное программирование", "олимпиадное программирование"),
       {"cpp": 0.3}),
    _S("oop", "ООП и паттерны", "general", ("ооп", "solid", "паттерны", "design patterns")),
    _S("security", "Информационная безопасность", "general",
       ("кибербезопасность", "infosec", "owasp", "pentest", "ctf")),
]

SKILL_BY_ID = {s.id: s for s in SKILLS}


def _build_similarity() -> dict[str, dict[str, float]]:
    sim: dict[str, dict[str, float]] = {s.id: {} for s in SKILLS}
    for s in SKILLS:
        for other, w in s.related.items():
            sim[s.id][other] = max(sim[s.id].get(other, 0), w)
            sim[other][s.id] = max(sim[other].get(s.id, 0), w)
    return sim


SKILL_SIM = _build_similarity()


def skill_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return SKILL_SIM.get(a, {}).get(b, 0.0)


# ---------------------------------------------------------------------------------------------------------------
# Specializations. core_skills drive the test blueprint and the default matching profile.
# ---------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Specialization:
    id: str
    title: str
    short: str
    description: str
    core_skills: dict[str, float]  # skill -> weight in the default test blueprint
    stack_options: tuple[str, ...]  # skills offered in the onboarding survey


SPECIALIZATIONS: list[Specialization] = [
    Specialization(
        "backend", "Backend-разработка", "Backend", "Серверная логика, API, базы данных",
        {"python": 0.3, "sql": 0.2, "http": 0.15, "algorithms": 0.15, "system_design": 0.1, "asyncio": 0.1},
        ("python", "java", "go", "csharp", "nodejs", "php", "django", "fastapi", "flask", "spring", "postgresql",
         "mysql", "mongodb", "redis", "kafka", "rabbitmq", "docker", "rest", "grpc", "microservices"),
    ),
    Specialization(
        "frontend", "Frontend-разработка", "Frontend", "Веб-интерфейсы и клиентская логика",
        {"javascript": 0.35, "typescript": 0.15, "html_css": 0.15, "react": 0.15, "browser": 0.1, "http": 0.1},
        ("javascript", "typescript", "react", "vue", "angular", "redux", "html_css", "webpack", "browser",
         "frontend_perf", "rest"),
    ),
    Specialization(
        "data", "Data Science / ML", "Data/ML", "Анализ данных, модели машинного обучения",
        {"statistics": 0.3, "ml": 0.3, "python": 0.15, "sql": 0.15, "pandas": 0.1},
        ("python", "pandas", "sql", "statistics", "ml", "dl", "nlp", "cv", "clickhouse"),
    ),
    Specialization(
        "qa", "Тестирование (QA)", "QA", "Ручное и автоматизированное тестирование",
        {"test_design": 0.35, "api_testing": 0.2, "autotests": 0.2, "sql": 0.15, "http": 0.1},
        ("test_design", "autotests", "api_testing", "load_testing", "python", "java", "javascript", "sql"),
    ),
    Specialization(
        "devops", "DevOps / SRE", "DevOps", "Инфраструктура, CI/CD, надёжность",
        {"linux": 0.3, "docker": 0.2, "kubernetes": 0.15, "ci_cd": 0.15, "bash": 0.1, "http": 0.1},
        ("linux", "bash", "docker", "kubernetes", "ci_cd", "terraform", "monitoring", "cloud", "python", "go"),
    ),
]
SPEC_BY_ID = {s.id: s for s in SPECIALIZATIONS}

INDUSTRIES = [
    "Финтех и банки", "E-commerce и ритейл", "GovTech", "Телеком", "Игры", "EdTech", "Медтех",
    "Промышленность и энергетика", "Логистика", "Медиа и развлечения", "Кибербезопасность", "Аутсорс и интеграция",
]

WORK_FORMATS = {"office": "Офис", "hybrid": "Гибрид", "remote": "Удалённо"}

TEAM_ROLES = ["Разработчик", "Тимлид", "Архитектор", "Аналитик", "Капитан команды", "Ментор", "Дизайнер"]

SOFT_SKILLS = [
    "Командная работа", "Коммуникация", "Лидерство", "Самоорганизация", "Наставничество", "Критическое мышление",
    "Публичные выступления", "Работа в условиях дедлайнов",
]


def catalog_payload() -> dict:
    return {
        "grades": [g.__dict__ for g in GRADES],
        "specializations": [
            {"id": s.id, "title": s.title, "short": s.short, "description": s.description,
             "core_skills": list(s.core_skills), "stack_options": list(s.stack_options)}
            for s in SPECIALIZATIONS
        ],
        "skills": [{"id": s.id, "title": s.title, "group": s.group} for s in SKILLS],
        "industries": INDUSTRIES,
        "work_formats": WORK_FORMATS,
        "team_roles": TEAM_ROLES,
        "soft_skills": SOFT_SKILLS,
    }
