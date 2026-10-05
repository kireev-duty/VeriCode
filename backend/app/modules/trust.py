"""Employer trust score: a transparent, explainable protection against fake vacancies and unfair employers.

MVP signals (computed from platform data): INN checksum, corporate email domain = website domain, profile
completeness, account age, candidates' responses to invitations, complaints, salary anomalies vs. the market
of the same category. Post-MVP concept (docs/anti-fraud.md): EGRUL/FNS check, moderation queue by risk.
"""

import re
import statistics
from datetime import UTC
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Company, Complaint, Invitation, Vacancy

FREE_MAIL = {"gmail.com", "mail.ru", "yandex.ru", "ya.ru", "bk.ru", "list.ru", "inbox.ru", "outlook.com",
             "hotmail.com", "icloud.com", "rambler.ru", "proton.me"}


def inn_valid(inn: str) -> bool:
    """Checksum of a Russian INN (10 digits - legal entity, 12 - individual entrepreneur)."""
    if not re.fullmatch(r"\d{10}|\d{12}", inn or ""):
        return False
    d = [int(x) for x in inn]

    def ctrl(coefs):
        return sum(c * x for c, x in zip(coefs, d)) % 11 % 10

    if len(d) == 10:
        return ctrl([2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[9]
    return (ctrl([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[10]
            and ctrl([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[11])


def domain_match(company: Company) -> bool:
    email_domain = (company.contact_email or "").split("@")[-1].lower()
    site = urlparse(company.website if "//" in (company.website or "") else f"//{company.website}").hostname or ""
    site = site.lower().removeprefix("www.")
    return bool(email_domain and site and email_domain not in FREE_MAIL
                and (email_domain == site or email_domain.endswith("." + site)))


def market_anomaly(db: Session, company: Company) -> bool:
    """A salary far above the market median of the same category is a classic lure of fake vacancies."""
    own = db.scalars(select(Vacancy).where(Vacancy.company_id == company.id)).all()
    for v in own:
        peers = db.scalars(select(Vacancy.salary_to).where(Vacancy.specialization == v.specialization,
                                                           Vacancy.grade == v.grade,
                                                           Vacancy.company_id != company.id)).all()
        if len(peers) >= 3 and v.salary_to > 2.5 * statistics.median(peers):
            return True
    return False


def trust_for(db: Session, company: Company) -> dict:
    signals = []
    score = 30

    def add(points: int, text: str, ok: bool):
        nonlocal score
        score += points
        signals.append({"text": text, "ok": ok, "points": points})

    if inn_valid(company.inn):
        add(15, "ИНН корректен", True)
    else:
        add(0, "ИНН не указан или некорректен", False)
    if company.domain_verified or domain_match(company):
        add(15, "Корпоративная почта совпадает с доменом сайта", True)
    filled = sum(bool(x) for x in (company.name, company.description, company.website, company.industry, company.city))
    add(2 * filled, f"Профиль компании заполнен на {filled}/5", filled >= 4)
    created = company.created_at.replace(tzinfo=UTC) if company.created_at.tzinfo is None else company.created_at
    age_days = (utcnow() - created).days
    if age_days >= 30:
        add(5, "На платформе больше месяца", True)

    responded = db.execute(select(Invitation.status, func.count()).where(Invitation.company_id == company.id)
                           .group_by(Invitation.status)).all()
    by = dict(responded)
    accepted, declined = by.get("accepted", 0), by.get("declined", 0)
    if accepted + declined >= 3:
        rate = accepted / (accepted + declined)
        add(round(20 * rate), f"Кандидаты принимают {round(rate * 100)}% приглашений", rate >= 0.3)
    complaints = db.scalar(select(func.count(Complaint.id)).where(Complaint.company_id == company.id)) or 0
    if complaints:
        add(-min(40, 15 * complaints), f"Жалобы кандидатов: {complaints}", False)
    if market_anomaly(db, company):
        add(-20, "Зарплата в вакансии сильно выше рынка категории — проверьте условия", False)
    score = max(0, min(100, score))
    level = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return {"score": score, "level": level, "signals": signals}
