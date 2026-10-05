"""Rule-based Russian/English IT text understanding: skills, grade, specialization, salary, work format, city.

Deterministic and dependency-free so that every scenario works without an LLM. When an LLM provider is
configured, app.modules.llm refines the result, but this module stays the fallback and the baseline.
"""

import math
import re
from collections import Counter

from app.catalog import SKILLS, SPECIALIZATIONS

CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Самара",
          "Ростов-на-Дону", "Краснодар", "Пермь", "Воронеж", "Уфа", "Томск", "Иннополис", "Калининград", "Владивосток"]
_CITY_STEMS = {c: c.lower()[: max(5, len(c) - 2)] for c in CITIES}
_CITY_STEMS["Санкт-Петербург"] = "петербург"
_CITY_STEMS["Москва"] = "москв"

_SPEC_KEYWORDS = {
    "backend": ["backend", "бэкенд", "бекенд", "back-end", "серверн", "api"],
    "frontend": ["frontend", "фронтенд", "front-end", "верстк", "вёрстк", "интерфейс", "spa"],
    "data": ["data scien", "machine learning", "ml-инженер", "ml engineer", "аналитик данных", "data analyst",
             "дата-сайент", "модел"],
    "qa": ["qa", "тестировщик", "тестирован", "quality assurance", "автотест"],
    "devops": ["devops", "sre", "инфраструктур", "девопс", "platform engineer"],
}
_GRADE_PATTERNS = [
    ("senior", r"\b(senior|сеньор|синьор|ведущ\w*|lead|тимлид|архитектор)\b"),
    ("middle", r"\b(middle|мидл|миддл)\b"),
    ("junior", r"\b(junior|джун\w*|младш\w*)\b"),
    ("intern", r"\b(intern|стаж[её]р\w*|стажировк\w*|практикант\w*)\b"),
]
_NICE_MARKERS = r"(будет плюсом|желательно|приветствуется|nice to have|плюсом будет|будет преимуществом|как плюс)"


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


def _skill_patterns():
    pats = []
    for s in SKILLS:
        # ids like "cv" ("curriculum vitae") or "dl" collide with ordinary words: match them by title/synonyms only
        ids = () if s.id in ("cv", "dl", "rest", "browser", "cloud") else (s.id,)
        for term in (s.title, *s.synonyms, *ids):
            t = term.lower().replace("ё", "е")
            if len(t) < 2:
                continue
            esc = re.escape(t)
            pats.append((s.id, re.compile(rf"(?<![\w+#.]){esc}(?![\w+#])")))
    return pats


_PATTERNS = _skill_patterns()


def extract_skills(text: str) -> list[str]:
    t = _norm(text)
    found: list[str] = []
    for sid, pat in _PATTERNS:
        if sid not in found and pat.search(t):
            found.append(sid)
    return found


def split_must_nice(text: str) -> tuple[list[str], list[str]]:
    """Skills after a "nice to have" marker (until the end of that sentence/bullet) are optional."""
    t = text.replace("ё", "е")
    nice_chunks = []
    for m in re.finditer(_NICE_MARKERS, t, flags=re.IGNORECASE):
        rest = t[m.end():]
        stop = re.search(r"[\n;•]|\.\s", rest)
        after = rest[: stop.start()] if stop else rest
        nice_chunks.append(after)
        if not extract_skills(after):
            # postfix form "Redis будет плюсом": take the current sentence/bullet before the marker
            head = t[:m.start()]
            bounds = [head.rfind(x) for x in ("\n", ". ", ";", "•", ":")]
            nice_chunks.append(head[max(bounds) + 1:])
    rest = t
    for chunk in nice_chunks:
        if chunk.strip():
            rest = rest.replace(chunk, " ")
    must = extract_skills(rest)  # a skill mentioned outside the optional parts stays required
    nice = []
    for chunk in nice_chunks:
        for s in extract_skills(chunk):
            if s not in nice and s not in must:
                nice.append(s)
    return must, nice


def detect_grade(text: str) -> str | None:
    t = _norm(text)
    for grade, pat in _GRADE_PATTERNS:
        if re.search(pat, t):
            return grade
    m = re.search(r"опыт\w*\s+(?:работы\s+)?(?:от|более|не менее|больше)?\s*(\d+)[\s-]*(?:х|ти|и)?\s*(?:год|лет)", t)
    if m:
        years = int(m.group(1))
        return "senior" if years >= 5 else "middle" if years >= 2 else "junior" if years >= 1 else "intern"
    return None


def detect_specialization(text: str, skills: list[str] | None = None) -> str | None:
    t = _norm(text)
    skills = skills if skills is not None else extract_skills(text)
    best, best_score = None, 0.0
    for spec in SPECIALIZATIONS:
        score = sum(2.0 for kw in _SPEC_KEYWORDS[spec.id] if kw in t)
        score += sum(spec.core_skills.get(s, 0) * 3 + (0.5 if s in spec.stack_options else 0) for s in skills)
        if score > best_score:
            best, best_score = spec.id, score
    return best


def _to_rub(num: str, suffix: str) -> int:
    v = float(num.replace(" ", "").replace(" ", "").replace(",", "."))
    if suffix and suffix.strip().lower() in ("k", "к", "тыс", "тыс."):
        v *= 1000
    elif v < 1000:
        v *= 1000  # "200–300" in a salary context means thousands
    return int(v)


def detect_salary(text: str) -> tuple[int | None, int | None]:
    t = text.lower().replace(" ", " ")
    num = r"(\d[\d ]{0,8}(?:[.,]\d+)?)"
    suf = r"\s*(k|к|тыс\.?|000)?"
    m = re.search(rf"от\s*{num}{suf}\s*(?:₽|руб\w*|р\.)?\s*до\s*{num}{suf}", t)
    if not m:
        m = re.search(rf"{num}{suf}\s*[-–—]\s*{num}{suf}\s*(?:₽|руб|р\.|k|к|тыс)", t)
    if m:
        a, sa, b, sb = m.groups()
        sa = sa or sb
        return _to_rub(a, sa or ""), _to_rub(b, sb or "")
    m = re.search(rf"(?:от|from)\s*{num}{suf}\s*(?:₽|руб|р\.|k|к|тыс)", t)
    if m:
        lo = _to_rub(m.group(1), m.group(2) or "")
        return lo, None
    m = re.search(rf"до\s*{num}{suf}\s*(?:₽|руб|р\.|k|к|тыс)", t)
    if m:
        return None, _to_rub(m.group(1), m.group(2) or "")
    return None, None


def detect_formats(text: str) -> list[str]:
    t = _norm(text)
    out = []
    if re.search(r"удален|удалён|remote|дистанц", t):
        out.append("remote")
    if re.search(r"гибрид|hybrid", t):
        out.append("hybrid")
    if re.search(r"офис|office|on-site|onsite", t):
        out.append("office")
    return out


def detect_city(text: str) -> str:
    t = _norm(text)
    for city, stem in _CITY_STEMS.items():
        if stem in t:
            return city
    return ""


def parse_need(text: str) -> dict:
    must, nice = split_must_nice(text)
    spec = detect_specialization(text, must + nice)
    lo, hi = detect_salary(text)
    return {
        "specialization": spec,
        "grade": detect_grade(text),
        "must_skills": must,
        "nice_skills": nice,
        "work_formats": detect_formats(text),
        "city": detect_city(text),
        "salary_from": lo,
        "salary_to": hi,
    }


# ------------------------------------------------------------------------------------------------ similarity


def _grams(text: str, n: int = 4) -> Counter:
    t = re.sub(r"[^\w+#]+", " ", text.lower().replace("ё", "е"))
    grams: Counter = Counter()
    for word in t.split():
        w = f"_{word}_"
        if len(w) <= n:
            grams[w] += 1
        for i in range(len(w) - n + 1):
            grams[w[i:i + n]] += 1
    return grams


def text_similarity(a: str, b: str) -> float:
    """Character 4-gram cosine: robust to Russian morphology without a stemmer."""
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return 0.0
    dot = sum(v * gb.get(k, 0) for k, v in ga.items())
    return dot / (math.sqrt(sum(v * v for v in ga.values())) * math.sqrt(sum(v * v for v in gb.values())))
