"""Resume parsing test set: `uv run python -m validation.resumes` (re)builds validation/data/resumes/*.pdf.

15 fictional resumes in five layouts (plus 6 hold-out ones written after the parser fixes) that real PDFs use: a plain single column, a two-column template with a
sidebar, an hh.ru-like export with a table of jobs, an English CV and a "creative" one with prose instead of
lists. Contacts, period formats ("Январь 2020 — настоящее время", "03.2019 – 05.2021", "Sep 2021 – Present",
"с 2016 по 2019") and the way skills are mentioned vary on purpose. The gold fields are stored next to the PDFs
(resumes.json); validation.run (section "Разбор резюме") parses the PDFs with the product code and compares.
All people are fictional.
"""

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Frame, PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.doctemplate import BaseDocTemplate

ROOT = Path(__file__).resolve().parent / "data" / "resumes"
FONTS = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь",
             "Декабрь"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# period: (start_year, start_month, end_year | None (present), end_month)
PEOPLE = [
    {"layout": "plain", "name": "Анна Кравцова", "email": "anna.kravtsova@mail.example", "phone": "+7 (912) 345-67-80",
     "telegram": "@kravtsova_dev", "city": "Екатеринбург", "spec": "backend", "period_fmt": "ru_month",
     "jobs": [("Python-разработчик", "ООО «ЛогистикТех»", (2021, 3, None, 0)),
              ("Младший разработчик", "Студия «Пиксель»", (2019, 7, 2021, 2))],
     "skills_text": "Python, Django, PostgreSQL, Redis, Docker, Git", "skills": ["python", "django", "postgresql",
                                                                             "redis", "docker", "git"]},
    {"layout": "sidebar", "name": "Дмитрий Орлов", "email": "d.orlov@example.org", "phone": "8 999 123 45 67",
     "telegram": "t.me/orlov_front", "city": "Москва", "spec": "frontend", "period_fmt": "mm_yyyy",
     "jobs": [("Frontend-разработчик", "Банк «Северный»", (2020, 2, None, 0)),
              ("Верстальщик", "Агентство «Лендинг Про»", (2018, 9, 2020, 1))],
     "skills_text": "JavaScript, TypeScript, React, Redux, HTML/CSS, Webpack", "skills": [
         "javascript", "typescript", "react", "redux", "html_css", "webpack"]},
    {"layout": "hh", "name": "Мария Белова", "email": "maria.belova@example.com", "phone": "+7 921 555 12 34",
     "telegram": "", "city": "Санкт-Петербург", "spec": "qa", "period_fmt": "ru_month",
     "jobs": [("QA-инженер", "ООО «ФинСофт»", (2022, 1, None, 0)),
              ("Тестировщик", "ИП Сидоров", (2020, 5, 2021, 12))],
     "skills_text": "Тест-дизайн, тест-кейсы, Postman, SQL, Jira, pytest", "skills": [
         "test_design", "api_testing", "sql", "autotests"]},
    {"layout": "english", "name": "Ivan Sokolov", "email": "ivan.sokolov@example.net", "phone": "+7-903-777-1122",
     "telegram": "@isokolov", "city": "Казань", "spec": "devops", "period_fmt": "en",
     "jobs": [("DevOps Engineer", "CloudCore LLC", (2021, 9, None, 0)),
              ("System Administrator", "Kazan IT Park", (2017, 6, 2021, 8))],
     "skills_text": "Linux, Docker, Kubernetes, Terraform, GitLab CI, Prometheus, Grafana, Bash", "skills": [
         "linux", "docker", "kubernetes", "terraform", "ci_cd", "monitoring", "bash"]},
    {"layout": "prose", "name": "Елена Смирнова", "email": "smirnova.e@example.ru", "phone": "+79161234567",
     "telegram": "Telegram: esmirnova_ds", "city": "Новосибирск", "spec": "data", "period_fmt": "years",
     "jobs": [("Data Scientist", "Ритейл-сеть «Корзина»", (2020, 1, None, 0)),
              ("Аналитик данных", "НИИ прикладной математики", (2016, 1, 2019, 12))],
     "skills_text": "Строю модели оттока на градиентном бустинге (CatBoost), пишу на Python и pandas, много SQL, "
                    "проверяю гипотезы A/B-тестами", "skills": ["ml", "python", "pandas", "sql", "statistics"]},
    {"layout": "plain", "name": "Сергей Ким", "email": "kim.sergey@example.com", "phone": "+7 (981) 000-11-22",
     "telegram": "@sergeykim", "city": "Краснодар", "spec": "backend", "period_fmt": "mm_yyyy",
     "jobs": [("Go-разработчик", "Маркетплейс «Ярмарка»", (2022, 4, None, 0)),
              ("Backend-разработчик", "Стартап «Доставка 24»", (2019, 10, 2022, 3))],
     "skills_text": "Go, gRPC, PostgreSQL, Kafka, Kubernetes, микросервисы", "skills": [
         "go", "grpc", "postgresql", "kafka", "kubernetes", "microservices"]},
    {"layout": "sidebar", "name": "Ольга Миронова", "email": "o.mironova@example.org", "phone": "+7 917 222 33 44",
     "telegram": "@olga_qa", "city": "Самара", "spec": "qa", "period_fmt": "since",
     "jobs": [("Инженер по автоматизации тестирования", "Телеком «Волна»", (2019, 1, None, 0)),
              ("Тестировщик", "Интернет-магазин «Техно»", (2016, 1, 2018, 12))],
     "skills_text": "Python, pytest, Selenium, Playwright, API-тестирование, Jenkins, нагрузочное тестирование (Locust)",
     "skills": ["python", "autotests", "api_testing", "ci_cd", "load_testing"]},
    {"layout": "hh", "name": "Артём Волков", "email": "artem.volkov@example.com", "phone": "8 (903) 444-55-66",
     "telegram": "", "city": "Москва", "spec": "backend", "period_fmt": "ru_month",
     "jobs": [("Ведущий Java-разработчик", "Банк «Столица»", (2018, 3, None, 0)),
              ("Java-разработчик", "Интегратор «СофтЛайн Плюс»", (2014, 9, 2018, 2))],
     "skills_text": "Java, Spring Boot, PostgreSQL, Kafka, микросервисная архитектура, Kubernetes", "skills": [
         "java", "spring", "postgresql", "kafka", "microservices", "kubernetes"]},
    {"layout": "english", "name": "Alexey Petrov", "email": "a.petrov@example.io", "phone": "+7 999 888 77 66",
     "telegram": "t.me/apetrov_ml", "city": "Москва", "spec": "data", "period_fmt": "en",
     "jobs": [("Machine Learning Engineer", "VisionLab", (2021, 2, None, 0)),
              ("Junior Data Scientist", "RetailAI", (2019, 6, 2021, 1))],
     "skills_text": "Python, PyTorch, computer vision (YOLO, OpenCV), Docker, SQL", "skills": [
         "python", "ml", "dl", "cv", "docker", "sql"]},
    {"layout": "prose", "name": "Наталья Зайцева", "email": "zaytseva.dev@example.ru", "phone": "+7 (950) 765-43-21",
     "telegram": "@nzaytseva", "city": "Воронеж", "spec": "frontend", "period_fmt": "years",
     "jobs": [("Frontend-разработчик", "Студия «Вектор»", (2021, 1, None, 0))],
     "skills_text": "Делаю интерфейсы на Vue и Nuxt, пишу на TypeScript, аккуратно верстаю по макетам Figma, "
                    "настраивала сборку на Vite", "skills": ["vue", "typescript", "html_css", "webpack"]},
    {"layout": "plain", "name": "Павел Никитин", "email": "pnikitin@example.com", "phone": "8-912-777-88-99",
     "telegram": "", "city": "Пермь", "spec": "devops", "period_fmt": "mm_yyyy",
     "jobs": [("SRE-инженер", "Онлайн-кинотеатр «Кадр»", (2020, 11, None, 0)),
              ("Системный администратор Linux", "Хостинг «Облако-М»", (2015, 4, 2020, 10))],
     "skills_text": "Linux, Ansible, Docker, Kubernetes, Prometheus, Grafana, ELK, Yandex Cloud", "skills": [
         "linux", "terraform", "docker", "kubernetes", "monitoring", "cloud"]},
    {"layout": "sidebar", "name": "Виктория Лебедева", "email": "v.lebedeva@example.net", "phone": "+7 960 101 20 30",
     "telegram": "@vika_ds", "city": "Томск", "spec": "data", "period_fmt": "ru_month",
     "jobs": [("Стажёр-аналитик", "Университетская лаборатория данных", (2024, 9, None, 0))],
     "skills_text": "Python, pandas, статистика, SQL, основы машинного обучения (scikit-learn)", "skills": [
         "python", "pandas", "statistics", "sql", "ml"]},
    {"layout": "hh", "name": "Роман Егоров", "email": "roman.egorov@example.com", "phone": "+7 (912) 909-08-07",
     "telegram": "@regorov", "city": "Уфа", "spec": "backend", "period_fmt": "since",
     "jobs": [("PHP-разработчик", "Агрегатор «Тур-Поиск»", (2020, 1, None, 0)),
              ("Веб-программист", "Студия «Сайт за неделю»", (2017, 1, 2019, 12))],
     "skills_text": "PHP, Laravel, MySQL, REST API, Docker, Redis", "skills": [
         "php", "laravel", "mysql", "rest", "docker", "redis"]},
    {"layout": "english", "name": "Kirill Fedorov", "email": "kfedorov@example.dev", "phone": "+7 921 321 54 76",
     "telegram": "@kfedorov_qa", "city": "Санкт-Петербург", "spec": "qa", "period_fmt": "en",
     "jobs": [("QA Automation Engineer", "FinTech Hub", (2022, 3, None, 0)),
              ("Manual QA Engineer", "GameDev Studio", (2020, 8, 2022, 2))],
     "skills_text": "Java, JUnit, Selenide, RestAssured, Postman, SQL, Jenkins, test design", "skills": [
         "java", "autotests", "api_testing", "sql", "ci_cd", "test_design"]},
    {"layout": "prose", "name": "Тимур Ахметов", "email": "akhmetov.t@example.ru", "phone": "8 917 000 12 12",
     "telegram": "Telegram: timur_ops", "city": "Казань", "spec": "devops", "period_fmt": "mm_yyyy",
     "jobs": [("DevOps-инженер", "Финтех «Перевод»", (2019, 5, None, 0)),
              ("Инженер технической поддержки", "Провайдер «Сеть+»", (2017, 3, 2019, 4))],
     "skills_text": "Поддерживаю кластеры Kubernetes, пишу пайплайны в GitHub Actions, автоматизирую "
                    "инфраструктуру Terraform, слежу за метриками в Prometheus", "skills": [
         "kubernetes", "ci_cd", "terraform", "monitoring"]},
]

# Hold-out: written after the parser fixes made on PEOPLE, with formats the parser was not tuned for
# ("period_texts" overrides the generated period strings; "display_name" is how the name is typeset).
HOLDOUT = [
    {"layout": "plain", "name": "Иванова Светлана Петровна", "display_name": "ИВАНОВА Светлана Петровна",
     "email": "s.ivanova@example.ru", "phone": "+7 912 3456789", "telegram": "", "city": "Пермь", "spec": "backend",
     "period_fmt": "ru_month", "period_texts": ["с марта 2021 г. по н.в.", "2019 г. – 2021 г."],
     "jobs": [("Backend-разработчик", "ООО «ПромСофт»", (2021, 3, None, 0)),
              ("Программист 1С", "Завод «Уралмаш-Сервис»", (2019, 1, 2021, 2))],
     "skills_text": "Python, FastAPI, PostgreSQL, Docker, RabbitMQ", "skills": [
         "python", "fastapi", "postgresql", "docker", "rabbitmq"]},
    {"layout": "sidebar", "name": "Nikolay Belov", "email": "n.belov@example.com", "phone": "+7 (985) 765-00-11",
     "telegram": "TG: @nikolay_be", "city": "Москва", "spec": "backend", "period_fmt": "en",
     "period_texts": ["Mar 2020 – current", "Aug 2016 – Feb 2020"],
     "jobs": [("Senior Backend Engineer", "Payments Cloud", (2020, 3, None, 0)),
              ("Software Engineer", "Telecom Systems", (2016, 8, 2020, 2))],
     "skills_text": "Java, Kotlin, Spring, Kafka, PostgreSQL, Kubernetes, system design", "skills": [
         "java", "kotlin", "spring", "kafka", "postgresql", "kubernetes", "system_design"]},
    {"layout": "hh", "name": "Григорий Осипов", "email": "osipov.g@example.org", "phone": "+7 903 100 20 30",
     "telegram": "@gosipov", "city": "Нижний Новгород", "spec": "devops", "period_fmt": "ru_month",
     "summary_line": "Опыт работы — 7 лет 9 месяцев",
     "jobs": [("DevOps-инженер", "Интернет-провайдер «Волга-Нет»", (2020, 7, None, 0)),
              ("Системный администратор", "Колледж информатики", (2019, 1, 2020, 6))],
     "skills_text": "Linux, Bash, Docker, Kubernetes, Ansible, Zabbix, GitLab CI", "skills": [
         "linux", "bash", "docker", "kubernetes", "terraform", "monitoring", "ci_cd"]},
    {"layout": "prose", "name": "Ксения Романова", "email": "romanova.k@example.com", "phone": "8(926)1112233",
     "telegram": "@kromanova", "city": "Москва", "spec": "frontend", "period_fmt": "years",
     "period_texts": ["2022 — сейчас", "2020 — 2022"],
     "jobs": [("Frontend-разработчик", "EdTech «Учи.Код»", (2022, 1, None, 0)),
              ("Junior frontend", "Агентство «Пиксели»", (2020, 1, 2021, 12))],
     "skills_text": "Пишу на React и Next.js с TypeScript, стилизую через Tailwind, покрываю компоненты тестами в "
                    "Jest", "skills": ["react", "typescript"]},
    {"layout": "plain", "name": "Олег Тарасов", "email": "tarasov.oleg@example.net", "phone": "+7 921 222 33 44",
     "telegram": "t.me/otarasov", "city": "Санкт-Петербург", "spec": "data", "period_fmt": "ru_month",
     "period_texts": ["Июль 2023 – по настоящее время", "Февраль 2021 – Июнь 2023"],
     "jobs": [("Data Engineer", "Сервис доставки «Быстро»", (2023, 7, None, 0)),
              ("Аналитик данных", "Сеть аптек «Здоровье»", (2021, 2, 2023, 6))],
     "skills_text": "Python, SQL, Airflow, Spark, ClickHouse, pandas", "skills": [
         "python", "sql", "clickhouse", "pandas"]},
    {"layout": "english", "name": "Daria Kuznetsova", "email": "d.kuznetsova@example.io", "phone": "+7 999 000 11 22",
     "telegram": "@dkuz_qa", "city": "Казань", "spec": "qa", "period_fmt": "en",
     "period_texts": ["Jan 2021 - Now", "Jun 2019 - Dec 2020"],
     "jobs": [("QA Automation Engineer", "Marketplace Tech", (2021, 1, None, 0)),
              ("QA Engineer", "Mobile Games", (2019, 6, 2020, 12))],
     "skills_text": "Cypress, TypeScript, Postman, REST API testing, GitHub Actions, test cases", "skills": [
         "autotests", "typescript", "api_testing", "rest", "ci_cd", "test_design"]},
]


def _fmt_period(fmt: str, p: tuple) -> str:
    y1, m1, y2, m2 = p
    if fmt == "ru_month":
        end = "настоящее время" if y2 is None else f"{MONTHS_RU[m2 - 1]} {y2}"
        return f"{MONTHS_RU[m1 - 1]} {y1} — {end}"
    if fmt == "mm_yyyy":
        end = "н.в." if y2 is None else f"{m2:02d}.{y2}"
        return f"{m1:02d}.{y1} – {end}"
    if fmt == "en":
        end = "Present" if y2 is None else f"{MONTHS_EN[m2 - 1]} {y2}"
        return f"{MONTHS_EN[m1 - 1]} {y1} – {end}"
    if fmt == "since":
        return f"с {y1} по настоящее время" if y2 is None else f"с {y1} по {y2}"
    return f"{y1}–{'по сей день' if y2 is None else y2}"


def gold_years(person: dict, today: date) -> float:
    """Union of job periods in years, the same rule the parser should apply."""
    spans = []
    for _, _, (y1, m1, y2, m2) in person["jobs"]:
        start = date(y1, m1, 1)
        end = today if y2 is None else date(y2, m2, 28)
        spans.append((start, end))
    spans.sort()
    total, (cs, ce) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += (ce - cs).days
            cs, ce = s, e
    total += (ce - cs).days
    return round(total / 365.25, 1)


def _styles():
    for name, file in (("PT", "PTSans-Regular.ttf"), ("PT-Bold", "PTSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
    base = ParagraphStyle("b", fontName="PT", fontSize=10, leading=13)
    return {"body": base, "h1": ParagraphStyle("h1", parent=base, fontName="PT-Bold", fontSize=18, leading=22),
            "h2": ParagraphStyle("h2", parent=base, fontName="PT-Bold", fontSize=12, leading=16, spaceBefore=8),
            "small": ParagraphStyle("s", parent=base, fontSize=9, leading=11, textColor=colors.HexColor("#555555"))}


def _contacts(p: dict, english: bool) -> list[str]:
    out = [f"{'Phone' if english else 'Телефон'}: {p['phone']}", f"E-mail: {p['email']}"]
    if p["telegram"]:
        out.append(p["telegram"] if p["telegram"].startswith(("t.me", "Telegram")) else f"Telegram {p['telegram']}")
    out.append(f"{'City' if english else 'Город'}: {p['city']}")
    return out


def build_one(p: dict, path: Path) -> None:
    st = _styles()
    en = p["layout"] == "english"
    texts = p.get("period_texts") or [_fmt_period(p["period_fmt"], per) for _, _, per in p["jobs"]]
    jobs = [(title, org, text) for (title, org, _), text in zip(p["jobs"], texts)]
    head = [Paragraph(p.get("display_name", p["name"]), st["h1"]), Paragraph(jobs[0][0], st["body"]), Spacer(1, 6)]
    exp_title = "Work experience" if en else "Опыт работы"
    skills_title = "Skills" if en else "Ключевые навыки"
    if p["layout"] == "sidebar":
        doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm)
        w, h = A4
        side = Frame(12 * mm, 15 * mm, 60 * mm, h - 30 * mm, id="side")
        main = Frame(78 * mm, 15 * mm, w - 90 * mm, h - 30 * mm, id="main")
        doc.addPageTemplates([PageTemplate(id="two", frames=[side, main])])
        story = [Paragraph("Контакты", st["h2"])] + [Paragraph(c, st["small"]) for c in _contacts(p, en)]
        story += [Paragraph(skills_title, st["h2"]), Paragraph(p["skills_text"], st["small"])]
        story += [Spacer(1, 400)]  # push the rest into the main frame
        story += head + [Paragraph(exp_title, st["h2"])]
        for title, org, per in jobs:
            story += [Paragraph(f"<b>{title}</b>", st["body"]), Paragraph(f"{org}, {per}", st["small"])]
        doc.build(story)
        return
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    story = list(head)
    if p["layout"] == "hh":
        story = [Paragraph(f"Резюме обновлено {date(2026, 9, 30):%d.%m.%Y}", st["small"])] + story
    story += [Paragraph(c, st["body"]) for c in _contacts(p, en)]
    if p["layout"] == "prose":
        story += [Paragraph("О себе", st["h2"]), Paragraph(p["skills_text"] + ".", st["body"])]
    story += [Paragraph(exp_title, st["h2"])]
    if p.get("summary_line"):
        story.append(Paragraph(p["summary_line"], st["body"]))
    if p["layout"] == "hh":
        rows = [[Paragraph(per, st["small"]), Paragraph(f"<b>{org}</b><br/>{title}", st["body"])]
                for title, org, per in jobs]
        t = Table(rows, colWidths=[45 * mm, 120 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc"))]))
        story.append(t)
    else:
        for title, org, per in jobs:
            story += [Paragraph(f"<b>{title}</b> — {org}", st["body"]), Paragraph(per, st["small"]), Spacer(1, 4)]
    if p["layout"] != "prose":
        story += [Paragraph(skills_title, st["h2"]), Paragraph(p["skills_text"], st["body"])]
    doc.build(story)


def build() -> list[dict]:
    return _build(PEOPLE, "resume", "resumes.json") + _build(HOLDOUT, "holdout", "resumes_holdout.json")


def _build(people: list[dict], prefix: str, gold_file: str) -> list[dict]:
    ROOT.mkdir(parents=True, exist_ok=True)
    gold = []
    for i, p in enumerate(people, start=1):
        path = ROOT / f"{prefix}_{i:02d}_{p['layout']}.pdf"
        build_one(p, path)
        tg = p["telegram"].split("/")[-1].split(":")[-1].strip().lstrip("@")  # "TG: @x", "t.me/x" -> "x"
        gold.append({"file": path.name, "layout": p["layout"], "full_name": p["name"], "email": p["email"],
                     "phone": "+7" + "".join(ch for ch in p["phone"] if ch.isdigit())[-10:],
                     "telegram": f"@{tg}" if tg else "", "city": p["city"], "specialization": p["spec"],
                     "skills": p["skills"], "jobs": [[t, o, list(per)] for t, o, per in p["jobs"]]})
    (ROOT / gold_file).write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    return gold


if __name__ == "__main__":
    print(len(build()), "resumes in", ROOT)
