"""Demo data: `python -m app.seed.run [--reset] [--candidates 500]`.

Creates demo accounts for the jury (password: demo12345):
  demo.candidate@fsp-talent.ru  - Middle Python backend, FSP linked, invitations and a regular task
  demo.employer@fsp-talent.ru   - company with needs, vacancies, tasks and an invitation history
  demo.new@fsp-talent.ru        - a fresh candidate to walk through onboarding and the test
All companies and people are fictional.
"""

import argparse
import random
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import select

from app.api.auth import create_user
from app.catalog import GRADE_ORDER, SPEC_BY_ID
from app.core.db import Base, SessionLocal, engine, utcnow
from app.core.security import hash_password
from app.models import (
    Application,
    AssessmentSession,
    CandidateProfile,
    Company,
    FspAchievement,
    GradeHistory,
    HiringNeed,
    Invitation,
    ItemFamilyStat,
    RegularTask,
    TaskSubmission,
    User,
    Vacancy,
)
from app.modules.assessment.service import ensure_item_stats, load_bank
from app.modules.fsp import registry_app
from app.modules.invitations import DECLINE_REASONS
from app.seed import synth

PASSWORD = "demo12345"

COMPANIES = [
    ("Кодовая Гавань", "Финтех и банки", "kodgavan.ru", "Москва", "200–500",
     "Разрабатываем платёжную инфраструктуру для банков и маркетплейсов. Сильная инженерная культура, код-ревью, "
     "своя платформа наблюдаемости."),
    ("Северный Бит", "Телеком", "sevbit.ru", "Санкт-Петербург", "500–1000",
     "Биллинг и OSS/BSS-системы для операторов связи."),
    ("ТехноСфера Лаб", "Промышленность и энергетика", "tsphere-lab.ru", "Екатеринбург", "50–200",
     "Промышленный IoT и предиктивная аналитика оборудования."),
    ("Облачная Мельница", "Аутсорс и интеграция", "cloudmill.ru", "Казань", "50–200",
     "Облачная миграция и DevOps-аутсорс."),
    ("Учим Вместе", "EdTech", "uchim-vmeste.ru", "Москва", "200–500", "Онлайн-школа программирования."),
    ("Медиана", "Медтех", "mediana-med.ru", "Новосибирск", "50–200", "ML-системы поддержки врачебных решений."),
    ("Корзина Онлайн", "E-commerce и ритейл", "korzina-online.ru", "Москва", "1000+",
     "Маркетплейс товаров для дома, 20 млн пользователей."),
    ("Логос Логистик", "Логистика", "logos-log.ru", "Нижний Новгород", "200–500", "Оптимизация доставки."),
    ("Пиксельная Лига", "Игры", "pixel-liga.ru", "Санкт-Петербург", "50–200", "Мобильные и браузерные игры."),
    ("ГосЦифра Регион", "GovTech", "goscifra-region.ru", "Казань", "200–500", "Региональные госуслуги."),
    ("Щит и Ключ", "Кибербезопасность", "shield-key.ru", "Москва", "50–200", "SOC и пентест."),
    ("Медиапоток", "Медиа и развлечения", "mediapotok.ru", "Москва", "200–500", "Стриминговая платформа."),
    ("Финтех Плюс", "Финтех и банки", "fintechplus.ru", "Москва", "500–1000", "Кредитный скоринг и антифрод."),
    ("Иннокод", "Аутсорс и интеграция", "innocode.ru", "Иннополис", "50–200", "Заказная разработка."),
    ("Тихая Гавань", "Финтех и банки", "", "Москва", "1–50", ""),  # sparse profile: low trust score on purpose
]

TASKS = [
    ("backend", "junior", "Ограничение частоты запросов",
     "Публичный API начали «долбить» ботами: до 2000 запросов в секунду с одного IP. Как бы вы ограничили частоту "
     "запросов, не задев честных пользователей? Опишите подход, где хранить счётчики и что вернуть клиенту.",
     [("Алгоритм ограничения (token/leaky bucket, скользящее окно)", ["bucket", "окн", "sliding", "window"]),
      ("Общее хранилище счётчиков для нескольких инстансов", ["redis", "memcached", "общ"]),
      ("Код ответа 429 и заголовок Retry-After", ["429", "retry-after"]),
      ("Ключ ограничения не только IP (токен, пользователь)", ["токен", "пользовател", "api key", "ключ"])],
     ["redis", "http"]),
    ("backend", "middle", "Медленный отчёт",
     "Эндпоинт отчёта за год отвечает 40 секунд и иногда падает по таймауту. Как будете искать причину и что "
     "предложите, чтобы пользователь всё-таки получал отчёт?",
     [("Профилирование и анализ плана запроса", ["explain", "профил", "план"]),
      ("Индексы / оптимизация запроса", ["индекс", "index"]),
      ("Асинхронная генерация через очередь/фоновую задачу", ["очеред", "фонов", "celery", "async", "асинхрон"]),
      ("Кэширование или предагрегация", ["кэш", "cache", "агрегац", "материализ"])],
     ["postgresql", "system_design"]),
    ("frontend", "junior", "Список из 10 000 элементов",
     "Страница со списком из 10 000 карточек тормозит при прокрутке. Что сделаете?",
     [("Виртуализация списка", ["виртуал", "virtual", "windowing"]),
      ("Пагинация или подгрузка по мере прокрутки", ["пагинац", "infinite", "подгруз"]),
      ("Мемоизация и лишние ререндеры", ["memo", "мемо", "ререндер", "re-render"]),
      ("Профилирование (DevTools, Profiler)", ["profiler", "devtools", "профил"])], ["react", "frontend_perf"]),
    ("data", "junior", "Метрика для антифрода",
     "Модель антифрода показывает accuracy 99,2%. Руководитель доволен. Что вы проверите, прежде чем согласиться?",
     [("Дисбаланс классов", ["дисбаланс", "imbalance", "доля"]),
      ("Precision/recall/F1 или PR-AUC", ["precision", "recall", "f1", "pr-auc"]),
      ("Стоимость ошибок разных типов", ["стоимост", "ошибк", "cost"]),
      ("Утечка данных / проверка на отложенной выборке", ["утечк", "leak", "отложен", "holdout"])],
     ["ml", "statistics"]),
    ("qa", "junior", "Форма регистрации",
     "Составьте план тестирования формы регистрации: email, пароль, подтверждение пароля, чекбокс согласия.",
     [("Граничные значения и классы эквивалентности", ["гранич", "эквивалент"]),
      ("Негативные сценарии и валидация", ["негатив", "невалид", "ошибк"]),
      ("Безопасность (SQL-инъекции, XSS, хранение пароля)", ["инъекц", "xss", "безопас"]),
      ("Повторная регистрация и подтверждение email", ["повтор", "подтвержд", "дубл"])], ["test_design"]),
    ("devops", "middle", "Падение после релиза",
     "После выкладки новой версии сервис начал отвечать 502 у части пользователей. Ваши действия по шагам?",
     [("Откат или переключение трафика", ["откат", "rollback", "canary", "blue"]),
      ("Метрики и логи для локализации", ["лог", "метрик", "grafana", "prometheus"]),
      ("Проверка readiness/liveness и конфигурации", ["readiness", "liveness", "проб", "конфиг"]),
      ("Постмортем и защита от повторения", ["постмортем", "postmortem", "разбор"])],
     ["kubernetes", "monitoring"]),
]


@lru_cache
def _hash() -> str:
    return hash_password(PASSWORD)


def valid_inn(rng: random.Random) -> str:
    d = [rng.randint(0, 9) for _ in range(9)]
    coefs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    return "".join(map(str, d)) + str(sum(c * x for c, x in zip(coefs, d)) % 11 % 10)


def _fsp(db, cand: CandidateProfile, fsp_id: str) -> None:
    p = registry_app.participant(fsp_id)
    if p is None:
        return
    cand.fsp_id = fsp_id
    cand.fsp_linked_at = utcnow() - timedelta(days=30)
    cand.fsp_profile = {"rank": p.rank, "rating": p.rating, "region": p.region, "disciplines": p.disciplines}
    for r in registry_app.results(fsp_id):
        cand.achievements.append(FspAchievement(
            external_id=r.id, event_name=r.event.name, event_level=r.event.level, discipline=r.event.discipline,
            date=datetime(r.event.date.year, r.event.date.month, r.event.date.day), place=r.place,
            participants=r.participants_count, team_name=r.team.name if r.team else "",
            team_role=r.team.role if r.team else "", result_type=r.result_type, certificate_url=r.certificate_url))


def make_candidate_user(db, rng, s: synth.SynthCandidate, email: str, bank, truth, stats: dict) -> CandidateProfile:
    user = create_user(db, email, PASSWORD, "candidate", verified=True, demo=True, password_hash=_hash())
    c = user.candidate
    now = utcnow()
    c.full_name, c.headline, c.about, c.city = s.full_name, s.headline, s.about, s.city
    c.contact_email = email
    c.phone = f"+79{rng.randint(100000000, 999999999)}"
    c.telegram = "@" + email.split("@")[0].replace(".", "_")
    c.work_formats, c.relocation, c.salary_expectation = s.work_formats, s.relocation, s.salary_expectation
    c.experience_years, c.skills, c.experience = s.experience_years, s.skills, s.experience
    c.team_roles, c.soft_skills = s.team_roles, s.soft_skills
    c.industries = rng.sample(["Финтех и банки", "E-commerce и ритейл", "Телеком", "GovTech", "EdTech"], 2)
    c.specialization, c.declared_grade, c.onboarding_done = s.spec, s.declared_grade, True
    c.survey = {"self_rating": {k["id"]: rng.randint(2, 5) for k in s.skills[:4]}}
    c.consent_processing_at = c.consent_publication_at = now - timedelta(days=s.activity_days + 2)
    c.privacy = {"show_city": True, "show_fsp": True, "show_companies": rng.random() < 0.3}
    if rng.random() < 0.3:
        c.min_salary_for_invites = int(s.salary_expectation * 0.85 / 5000) * 5000

    res = synth.assign_grade(rng, s, bank, truth)
    s.test = res
    when = now - timedelta(days=s.activity_days)
    for i, att in enumerate(res["attempts"]):
        ts = when - timedelta(minutes=40 * (len(res["attempts"]) - i))
        sess = AssessmentSession(candidate_id=c.id, specialization=s.spec, target_grade=att["target"],
                                 blueprint=res["blueprint"], seed=rng.randrange(1 << 30), status="finished",
                                 theta=att["theta"], se=att["se"], result_grade=att["target"]
                                 if att["outcome"] != "not_confirmed" else None, outcome=att["outcome"],
                                 p_target=att["p_target"], skill_theta=att["skill_theta"],
                                 flags={"items": att["items"], "timeouts": 0, "paste_events": 0, "blur_events": 0},
                                 finished_at=ts, created_at=ts - timedelta(minutes=25))
        db.add(sess)
        db.flush()
        db.add(GradeHistory(candidate_id=c.id, specialization=s.spec,
                            grade=att["target"] if att["outcome"] != "not_confirmed" else None,
                            previous_grade=None, session_id=sess.id, created_at=ts,
                            reason="Грейд подтверждён тестом" if att["outcome"] != "not_confirmed"
                            else "Заявленный грейд не подтверждён"))
    for r in res["responses"]:
        st = stats.setdefault(r.item.key, [0, 0])
        st[0] += 1
        st[1] += int(r.correct)
    c.grade, c.theta, c.theta_se, c.skill_theta = res["grade"], res["theta"], res["se"], res["skill_theta"]
    c.grade_confirmed_at = when
    if rng.random() < 0.5:
        c.last_task_at = now - timedelta(days=int(s.activity_days * rng.random()))
        c.task_score = round(rng.uniform(0.4, 1.0), 2)
    if s.fsp_id:
        _fsp(db, c, s.fsp_id)
    return c


def seed(n_candidates: int = 500, reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    rng = random.Random(2026)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "demo.employer@fsp-talent.ru")):
            print("Demo data already present (use --reset to recreate)")
            return
        ensure_item_stats(db)
        bank = load_bank(db)
        truth = synth.true_params(bank, random.Random(7))
        stats: dict[str, list[int]] = {}
        now = utcnow()

        # ---------------------------------------------------------------- companies
        companies: list[Company] = []
        for i, (name, industry, site, city, size, descr) in enumerate(COMPANIES):
            email = "demo.employer@fsp-talent.ru" if i == 0 else f"hr{i}@{site or 'mail.ru'}"
            u = create_user(db, email, PASSWORD, "employer", name, verified=True, demo=True, password_hash=_hash())
            co = u.company
            co.industry, co.website, co.city, co.size, co.description = industry, site, city, size, descr
            co.contact_name = rng.choice(["Ольга", "Мария", "Андрей", "Евгения"]) + " (HR)"
            co.contact_email = f"hr@{site}" if site else email
            co.contact_telegram = f"@{site.split('.')[0]}_hr" if site else ""
            co.inn = valid_inn(rng) if site else "1234567890"
            co.logo_color = rng.choice(["#402FFF", "#1B1C21", "#EC1D35", "#0F9D58", "#F4B400", "#7B61FF"])
            co.created_at = now - timedelta(days=rng.randint(10, 200))
            companies.append(co)
        db.commit()
        demo_co = companies[0]

        # ---------------------------------------------------------------- vacancies
        vacancies: list[Vacancy] = []
        for i in range(40):
            co = companies[i % (len(companies) - 1)]
            v = synth.make_vacancy(rng)
            vac = Vacancy(company_id=co.id, **v, created_at=now - timedelta(days=rng.randint(0, 40)))
            db.add(vac)
            vacancies.append(vac)
        # an anomalous "too good to be true" offer from the sparse company
        lure = synth.make_vacancy(rng, "backend", "junior")
        lure.update(title="Junior Python-разработчик, удалённо", salary_from=450000, salary_to=600000,
                    description="Срочно! Без опыта, удалённо, 450–600 тыс. ₽. Пишите в Telegram.")
        db.add(Vacancy(company_id=companies[-1].id, **lure))
        db.commit()

        # ---------------------------------------------------------------- tasks
        task_rows = []
        for spec, grade, title, body, rubric, skills in TASKS:
            t = RegularTask(company_id=demo_co.id if spec in ("backend", "frontend") else rng.choice(companies[1:5]).id,
                            title=title, body=body, kind="approach", specialization=spec, min_grade=grade,
                            skills=skills, rubric=[{"point": p, "keywords": k, "weight": 1} for p, k in rubric])
            db.add(t)
            task_rows.append(t)
        db.commit()

        # ---------------------------------------------------------------- candidates
        synth_pool: list[tuple[CandidateProfile, synth.SynthCandidate]] = []
        demo = synth.make_candidate(rng, "backend", 0)
        demo.theta, demo.declared_grade = 0.65, "middle"
        demo.skill_theta = {k: 0.65 + rng.gauss(0, 0.3) for k in demo.skill_theta}
        demo.skills = [{"id": "python", "years": 4}, {"id": "fastapi", "years": 2}, {"id": "django", "years": 3},
                       {"id": "postgresql", "years": 4}, {"id": "redis", "years": 2}, {"id": "docker", "years": 3},
                       {"id": "kafka", "years": 1}, {"id": "git", "years": 5}]
        demo.full_name, demo.city, demo.fsp_id = "Алексей Смирнов", "Москва", "FSP-100231"
        demo.headline, demo.salary_expectation, demo.experience_years = "Python backend-разработчик", 260000, 4.5
        demo.work_formats, demo.activity_days = ["remote", "hybrid"], 3
        dc = make_candidate_user(db, rng, demo, "demo.candidate@fsp-talent.ru", bank, truth, stats)
        dc.team_roles = ["Разработчик", "Капитан команды"]
        dc.min_salary_for_invites = None
        synth_pool.append((dc, demo))
        for i in range(1, n_candidates):
            s = synth.make_candidate(rng, None, i)
            c = make_candidate_user(db, rng, s, f"cand{i:04d}@example.ru", bank, truth, stats)
            synth_pool.append((c, s))
            if i % 100 == 0:
                db.commit()
                print(f"  candidates: {i}")
        db.commit()
        for key, (n, k) in stats.items():
            st = db.get(ItemFamilyStat, key)
            if st:
                st.exposures += n
                st.responses += n
                st.correct += k
        create_user(db, "demo.new@fsp-talent.ru", PASSWORD, "candidate", verified=True, demo=True)
        db.commit()

        # ---------------------------------------------------------------- needs for the demo employer
        needs = [
            HiringNeed(company_id=demo_co.id, title="Middle Python backend в команду платежей",
                       raw_text="Ищем Middle Python-разработчика в команду платёжного шлюза: FastAPI или Django, "
                                "PostgreSQL, асинхронность. Будет плюсом Kafka и Redis. Удалённо или гибрид, "
                                "220–300 тыс. ₽.",
                       team_description="8 человек, платёжный шлюз, 3000 RPS в пике", specialization="backend",
                       grade="middle", must_skills=["python", "postgresql", "asyncio"],
                       nice_skills=["kafka", "redis", "fastapi"], work_formats=["remote", "hybrid"],
                       salary_from=220000, salary_to=300000),
            HiringNeed(company_id=demo_co.id, title="Senior Frontend для личного кабинета",
                       raw_text="Senior Frontend: React, TypeScript, дизайн-система, производительность.",
                       specialization="frontend", grade="senior", must_skills=["react", "typescript"],
                       nice_skills=["frontend_perf", "redux"], work_formats=["hybrid", "remote"],
                       salary_from=320000, salary_to=420000),
            HiringNeed(company_id=demo_co.id, title="Junior QA в команду платежей",
                       raw_text="Junior QA: тест-дизайн, API, SQL.", specialization="qa", grade="junior",
                       must_skills=["test_design", "api_testing"], nice_skills=["sql"], work_formats=["office", "hybrid"],
                       city="Москва", salary_from=90000, salary_to=130000),
        ]
        db.add_all(needs)
        db.commit()

        # ---------------------------------------------------------------- invitation history (all companies)
        searchable = [c for c, _ in synth_pool if c.id != dc.id]
        for co in companies[:-1]:
            for _ in range(rng.randint(3, 9)):
                c = rng.choice(searchable)
                created = now - timedelta(days=rng.randint(1, 35), hours=rng.randint(0, 23))
                lo = int(synth.market_salary(c.specialization, c.grade) * rng.uniform(0.75, 1.0) / 10000) * 10000
                hi = lo + rng.choice([30000, 50000, 80000])
                status = rng.choices(["accepted", "declined", "viewed", "sent", "expired"], weights=[4, 3, 2, 2, 1])[0]
                reason = None
                if status == "declined":
                    reason = "salary" if (c.salary_expectation or 0) > hi else rng.choice(list(DECLINE_REASONS))
                inv = Invitation(company_id=co.id, candidate_id=c.id, position_title=c.headline.split(",")[0],
                                 message="Здравствуйте! Посмотрели ваш профиль и результаты теста — хотим "
                                         "предложить позицию в нашей команде.", salary_from=lo, salary_to=hi,
                                 contact_method=co.contact_telegram or co.contact_email, status=status,
                                 decline_reason=reason, created_at=created,
                                 viewed_at=created + timedelta(hours=5) if status != "sent" else None,
                                 responded_at=created + timedelta(hours=rng.randint(6, 60))
                                 if status in ("accepted", "declined") else None,
                                 expires_at=created + timedelta(days=14))
                db.add(inv)
        # demo candidate: a fresh invitation to accept and an accepted one from the demo employer
        other = companies[6]
        db.add(Invitation(company_id=other.id, candidate_id=dc.id, position_title="Python-разработчик в команду поиска",
                          message="Алексей, добрый день! Мы строим новый поиск по каталогу из 20 млн товаров и ищем "
                                  "backend-разработчика на FastAPI. Ваш результат теста и опыт на хакатонах ФСП нам "
                                  "очень подходят.", salary_from=250000, salary_to=320000, work_format="remote",
                          contact_method="@korzina_hr", status="sent", expires_at=now + timedelta(days=12)))
        db.add(Invitation(company_id=companies[11].id, candidate_id=dc.id, position_title="Backend-разработчик",
                          message="Здравствуйте! Предлагаем позицию backend-разработчика стриминговой платформы.",
                          salary_from=180000, salary_to=210000, contact_method="@mediapotok_hr", status="sent",
                          below_expectation=True, expires_at=now + timedelta(days=9)))
        db.add(Invitation(company_id=demo_co.id, candidate_id=dc.id, need_id=needs[0].id,
                          position_title="Middle Python backend", message="Алексей, приглашаем в команду платежей!",
                          salary_from=240000, salary_to=300000, contact_method="@kodgavan_hr", status="accepted",
                          viewed_at=now - timedelta(days=2), responded_at=now - timedelta(days=2),
                          created_at=now - timedelta(days=3), expires_at=now + timedelta(days=11)))
        db.add(TaskSubmission(task_id=task_rows[1].id, candidate_id=dc.id, status="offered"))

        # ---------------------------------------------------------------- applications
        for v in vacancies[:25]:
            pool = [c for c in searchable if c.specialization == v.specialization]
            for c in rng.sample(pool, min(len(pool), rng.randint(0, 4))):
                db.add(Application(vacancy_id=v.id, candidate_id=c.id,
                                   cover_letter="Здравствуйте! Интересна ваша вакансия, готов обсудить.",
                                   status=rng.choice(["sent", "sent", "viewed", "invited", "rejected"]),
                                   created_at=now - timedelta(days=rng.randint(0, 20))))
        db.commit()
        n = db.query(CandidateProfile).count()
        by_grade = {g: db.query(CandidateProfile).filter(CandidateProfile.grade == g).count() for g in GRADE_ORDER}
        by_spec = {s: db.query(CandidateProfile).filter(CandidateProfile.specialization == s).count() for s in SPEC_BY_ID}
        print(f"Seed done: {n} candidates, by grade {by_grade}, by specialization {by_spec}, "
              f"{len(companies)} companies, {len(vacancies) + 1} vacancies")
        print(f"Demo password for all demo accounts: {PASSWORD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--candidates", type=int, default=500)
    args = ap.parse_args()
    seed(args.candidates, args.reset)
