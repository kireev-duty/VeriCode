"""Resume (PDF) -> structured profile draft. The candidate reviews and confirms every field before saving.

Rule-based extraction works offline; if an LLM provider is configured, app.modules.llm.refine_resume() fills
gaps (name, positions, skills described in prose), but the result of this module is always the baseline.
"""

import re
from datetime import date

import pymupdf

from app.catalog import SOFT_SKILLS, TEAM_ROLES
from app.modules import llm, nlp

MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6, "июл": 7, "авг": 8, "сен": 9,
          "окт": 10, "ноя": 11, "дек": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
# PDF text breaks lines inside table cells: "настоящее\nвремя"
PRESENT = r"(?:(?:по\s+)?настоящее\s+время|по\s+настоящее|по\s+сей\s+день|н\.?\s?в\.?|present|now|сейчас|текущ\w*)"
POSITION_WORDS = r"(разработчик|developer|engineer|инженер|программист|тестировщик|аналитик|analyst|qa|devops|" \
                 r"тимлид|team ?lead|архитектор|architect|scientist|стажер|стажёр|intern)"


def pdf_to_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _month(token: str) -> int:
    token = token.lower()[:3]
    return MONTHS.get(token, 1)


def _parse_periods(text: str) -> list[tuple[date, date]]:
    t = text.lower().replace("ё", "е")
    periods = []
    mon = r"([а-яa-z]{3,9}\.?\s+)?"
    year = r"((?:19|20)\d\d)"
    today = date.today()
    dash = r"\s*[-–—]\s*"
    patterns = [
        # "Январь 2020 — настоящее время", "Sep 2021 – Present", "2016–2019"
        (re.compile(rf"{mon}{year}{dash}(?:{mon}{year}|{PRESENT})"), "names"),
        # "03.2019 – 05.2021", "11.2020 – н.в."
        (re.compile(rf"(\d{{1,2}})\.{year}{dash}(?:(\d{{1,2}})\.{year}|{PRESENT})"), "numbers"),
        # "с 2016 по 2019", "с 2019 по настоящее время"
        (re.compile(rf"(?<![\w])с\s+(){year}\s+(?:по\s+(){year}|{PRESENT})"), "names"),
    ]
    for pat, kind in patterns:
        for m in pat.finditer(t):
            m1, y1, m2, y2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            if kind == "numbers":
                start_month, end_month = int(m1), int(m2) if m2 else 12
            else:
                start_month, end_month = _month(m1) if m1 else 1, _month(m2) if m2 else 12
            if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
                continue
            start = date(y1, start_month, 1)
            end = date(int(y2), end_month, 1) if y2 else today
            if start <= end <= today.replace(year=today.year + 1) and (start, end) not in periods:
                periods.append((start, end))
    return periods


def _total_years(periods: list[tuple[date, date]]) -> float:
    """Union of periods, so overlapping jobs are not double-counted."""
    if not periods:
        return 0.0
    periods = sorted(periods)
    total, (cs, ce) = 0, periods[0]
    for s, e in periods[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += (ce - cs).days
            cs, ce = s, e
    total += (ce - cs).days
    return round(total / 365.25, 1)


def _name(lines: list[str]) -> str:
    """2-3 capitalised words on a line of their own. The top of the page first; two-column templates put the
    contacts sidebar before the name in the text layer, so the whole page is the fallback."""
    for scope in (lines[:8], lines):
        for pattern in (r"[А-ЯЁ][а-яё\-]+", r"[A-Z][a-z\-]+"):
            for line in scope:
                words = line.strip().split()
                if 2 <= len(words) <= 3 and all(re.fullmatch(pattern, w) for w in words):
                    return " ".join(words)
    return ""


def _phone(text: str) -> str:
    m = nlp.PHONE_RE.search(text)
    if not m:
        return ""
    digits = re.sub(r"\D", "", m.group(0))
    return "+7" + digits[-10:]  # 8 (999) ... and +7 999 ... are the same number


def parse_resume_text(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    low = text.lower()
    email = nlp.EMAIL_RE.search(text)
    tg = nlp.TELEGRAM_RE.search(text)

    explicit = re.search(r"опыт работы[^\d]{0,20}(\d+)\s*(?:год|лет|г\.)(?:\D{0,5}(\d+)\s*мес)?", low)
    if explicit:
        years = int(explicit.group(1)) + (int(explicit.group(2)) / 12 if explicit.group(2) else 0)
    else:
        years = _total_years(_parse_periods(text))

    positions = []
    for line in lines:
        if re.search(POSITION_WORDS, line.lower()) and len(line) < 90 and line.strip() not in positions:
            positions.append(line.strip())

    skills = nlp.extract_skills(text)
    soft = [s for s in SOFT_SKILLS if s.lower()[:6] in low]
    roles = [r for r in TEAM_ROLES if r.lower()[:6] in low]
    if re.search(r"капитан", low) and "Капитан команды" not in roles:
        roles.append("Капитан команды")
    grade = nlp.detect_grade(text) or ("senior" if years >= 5 else "middle" if years >= 2 else
                                       "junior" if years >= 1 else "intern")
    return {
        "full_name": _name(lines),
        "contact_email": email.group(0) if email else "",
        "phone": _phone(text),
        "telegram": "@" + tg.group(1) if tg else "",
        "city": nlp.detect_city(text),
        "experience_years": round(years, 1),
        "skills": [{"id": s, "years": None} for s in skills],
        "headline": positions[0] if positions else "",
        "positions": positions[:6],
        "team_roles": roles,
        "soft_skills": soft,
        "specialization": nlp.detect_specialization(text, skills),
        "declared_grade_hint": grade,
        "work_formats": nlp.detect_formats(text),
    }


def parse_resume_pdf(data: bytes) -> dict:
    text = pdf_to_text(data)
    result, source = llm.refine_resume(text, parse_resume_text(text))
    result["chars"] = len(text)
    result["source"] = source
    return result
