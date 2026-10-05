"""Mock of the FSP participant registry - our *proposal* of its API and data model.

Runs as a separate service (docker compose: fsp_registry) from the same image:
    uvicorn app.modules.fsp.registry_app:app --port 8090
Data is generated deterministically from the FSP ID, so the same ID always returns the same history.
Conventions for the demo: IDs look like FSP-123456; an ID ending with 0 belongs to a participant without
competition results; IDs starting with FSP-9 are unknown to the registry (404).
"""

import hashlib
import random
from datetime import date

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

REGISTRY_TOKEN = "fsp-registry-demo-token"

EVENTS = [
    ("product", "federal", "Чемпионат России по спортивному программированию (продуктовое программирование)"),
    ("product", "federal", "Всероссийский хакатон ФСП «Цифровой прорыв»"),
    ("product", "regional", "Региональный хакатон ФСП «{region} Код»"),
    ("product", "international", "Международный хакатон «BRICS Digital»"),
    ("algorithmic", "federal", "Кубок России по спортивному программированию (алгоритмическое)"),
    ("algorithmic", "regional", "Первенство {region} по алгоритмическому программированию"),
    ("algorithmic", "international", "Международная олимпиада по спортивному программированию"),
    ("security", "federal", "Чемпионат России: программирование систем информационной безопасности (CTF)"),
    ("security", "regional", "Региональные соревнования по ИБ «{region} CTF»"),
    ("drones", "federal", "Всероссийские соревнования по программированию БАС"),
    ("robotics", "regional", "Региональные соревнования по программированию робототехники"),
]
REGIONS = ["Москвы", "Санкт-Петербурга", "Татарстана", "Новосибирской области", "Свердловской области",
           "Нижегородской области", "Краснодарского края"]
REGION_SHORT = ["Москва", "Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний", "Краснодар"]
ROLES = ["Капитан", "Разработчик", "Backend-разработчик", "Frontend-разработчик", "Аналитик", "Дизайнер", "ML-инженер"]
RANKS = ["", "", "III", "II", "I", "КМС", "МС"]
FIRST = ["Алексей", "Мария", "Иван", "Анна", "Дмитрий", "Екатерина", "Никита", "Софья", "Артём", "Полина"]
LAST = ["Смирнов", "Иванова", "Кузнецов", "Попова", "Соколов", "Лебедева", "Козлов", "Новикова", "Морозов", "Волкова"]


class Participant(BaseModel):
    fsp_id: str
    full_name: str
    birth_year: int
    region: str
    rank: str  # спортивный разряд: "", III, II, I, КМС, МС
    rating: int  # рейтинг участника в системе ФСП
    disciplines: list[str]


class Event(BaseModel):
    id: str
    name: str
    level: str  # regional | federal | international
    discipline: str  # product | algorithmic | security | drones | robotics
    date: date
    city: str


class Team(BaseModel):
    name: str
    role: str
    size: int


class Result(BaseModel):
    id: str
    event: Event
    place: int | None
    participants_count: int
    result_type: str  # winner | prize | finalist | participant
    team: Team | None
    certificate_url: str


def _rng(fsp_id: str) -> random.Random:
    return random.Random(int(hashlib.sha256(fsp_id.encode()).hexdigest()[:12], 16))


def participant(fsp_id: str) -> Participant | None:
    if not fsp_id.startswith("FSP-") or fsp_id.startswith("FSP-9"):
        return None
    rng = _rng(fsp_id)
    region = rng.randrange(len(REGIONS))
    has_results = not fsp_id.endswith("0")
    rank = rng.choice(RANKS) if has_results else ""
    return Participant(fsp_id=fsp_id, full_name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                       birth_year=rng.randint(1994, 2007), region=REGIONS[region], rank=rank,
                       rating=rng.randint(800, 2400) if has_results else 0,
                       disciplines=sorted({e[0] for e in rng.sample(EVENTS, 3)}) if has_results else [])


def results(fsp_id: str) -> list[Result]:
    p = participant(fsp_id)
    if p is None or fsp_id.endswith("0"):
        return []
    rng = _rng(fsp_id + ":results")
    region = REGIONS.index(p.region)
    out = []
    for i in range(rng.randint(1, 5)):
        disc, level, name = rng.choice(EVENTS)
        n = {"regional": rng.randint(20, 80), "federal": rng.randint(60, 300),
             "international": rng.randint(80, 400)}[level]
        place = rng.choice([1, 2, 3, rng.randint(4, 12), rng.randint(10, n)])
        rtype = "winner" if place == 1 else "prize" if place <= 3 else "finalist" if place <= 12 else "participant"
        team = disc in ("product", "security", "drones", "robotics")
        d = date(rng.randint(2022, 2026), rng.randint(1, 12), rng.randint(1, 28))
        out.append(Result(
            id=f"{fsp_id}-R{i + 1}",
            event=Event(id="EV-" + hashlib.sha256(f"{name}{d.year}".encode()).hexdigest()[:6],
                        name=name.format(region=REGION_SHORT[region]),
                        level=level, discipline=disc, date=d, city=REGION_SHORT[region] if level == "regional" else
                        rng.choice(["Москва", "Казань", "Иннополис", "Санкт-Петербург"])),
            place=place, participants_count=n, result_type=rtype,
            team=Team(name=rng.choice(["Null Pointer", "Bit by Bit", "404 Found", "Stack Overflow", "Kernel Panic"]),
                      role=rng.choice(ROLES), size=rng.randint(3, 5)) if team else None,
            certificate_url=f"https://fsp-russia.com/certificates/{fsp_id}-R{i + 1}.pdf",
        ))
    return sorted(out, key=lambda r: r.event.date, reverse=True)


app = FastAPI(title="ФСП: реестр участников (мок)", version="0.1.0",
              description="Предлагаемый контракт реестра ФСП для интеграции с платформой подбора. "
                          "Авторизация сервис-сервис: Bearer-токен (в проде — client credentials Keycloak).")


def _auth(authorization: str | None):
    if authorization != f"Bearer {REGISTRY_TOKEN}":
        raise HTTPException(401, "invalid service token")


@app.get("/api/v1/participants/{fsp_id}", response_model=Participant, summary="Карточка участника")
def get_participant(fsp_id: str, authorization: str | None = Header(None)):
    _auth(authorization)
    p = participant(fsp_id)
    if p is None:
        raise HTTPException(404, "participant not found")
    return p


@app.get("/api/v1/participants/{fsp_id}/results", response_model=list[Result], summary="Результаты участника")
def get_results(fsp_id: str, authorization: str | None = Header(None)):
    _auth(authorization)
    if participant(fsp_id) is None:
        raise HTTPException(404, "participant not found")
    return results(fsp_id)


@app.get("/health")
def health():
    return {"ok": True}
