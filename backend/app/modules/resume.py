"""Resume (PDF) -> structured profile draft. The candidate reviews and confirms every field before saving.

Rule-based extraction works offline; if an LLM provider is configured, app.modules.llm.refine_resume() may
fill gaps, but the result of this module is always the baseline.
"""

import re
from datetime import date

import fitz  # PyMuPDF

from app.catalog import SOFT_SKILLS, TEAM_ROLES
from app.modules import nlp

MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6, "июл": 7, "авг": 8, "сен": 9,
          "окт": 10, "ноя": 11, "дек": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
PRESENT = r"(?:настоящее время|по настоящее|н\.?\s?в\.?|present|now|сейчас|текущ\w*)"
POSITION_WORDS = r"(разработчик|developer|engineer|инженер|программист|тестировщик|аналитик|analyst|qa|devops|" \
                 r"тимлид|team ?lead|архитектор|architect|scientist|стажер|стажёр|intern)"


def pdf_to_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _month(token: str) -> int:
    token = token.lower()[:3]
    return MONTHS.get(token, 1)


def _parse_periods(text: str) -> list[tuple[date, date]]:
    t = text.lower().replace("ё", "е")
    periods = []
    mon = r"([а-яa-z]{3,9}\.?\s+)?"
    pat = re.compile(rf"{mon}((?:19|20)\d\d)\s*[-–—]\s*(?:{mon}((?:19|20)\d\d)|{PRESENT})")
    today = date.today()
    for m in pat.finditer(t):
        m1, y1, m2, y2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        start = date(y1, _month(m1) if m1 else 1, 1)
        end = date(int(y2), _month(m2) if m2 else 12, 1) if y2 else today
        if start <= end <= today.replace(year=today.year + 1):
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
    for line in lines[:8]:
        words = line.strip().split()
        if 2 <= len(words) <= 3 and all(re.fullmatch(r"[А-ЯЁ][а-яё\-]+", w) for w in words):
            return " ".join(words)
    for line in lines[:5]:
        words = line.strip().split()
        if 2 <= len(words) <= 3 and all(re.fullmatch(r"[A-Z][a-z\-]+", w) for w in words):
            return " ".join(words)
    return ""


def parse_resume_text(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    low = text.lower()
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", text)
    tg = re.search(r"(?:t\.me/|telegram[:\s]*@?|tg[:\s]*@?|\s@)([A-Za-z][\w]{4,31})", text)

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
        "phone": re.sub(r"[^\d+]", "", phone.group(0)) if phone else "",
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
    result = parse_resume_text(text)
    result["chars"] = len(text)
    return result
