"""Rule-based Russian/English IT text understanding: skills, grade, specialization, salary, work format, city.

Deterministic and dependency-free so that every scenario works without an LLM. When an LLM provider is
configured, app.modules.llm.refine_need() refines the result, but this module stays the fallback and the baseline.
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
    ("senior", r"\b(senior|сеньор\w*|синьор\w*|ведущ\w*|lead|тимлид\w*|архитектор\w*)\b"),
    ("middle", r"\b(middle|мидл\w*|миддл\w*)\b"),
    ("junior", r"\b(junior|джун\w*|младш\w*)\b"),
    ("intern", r"\b(intern|стаж[её]р\w*|стажировк\w*|практикант\w*)\b"),
]
_NUM_WORDS = {"одного": 1, "года": 1, "двух": 2, "трех": 3, "трёх": 3, "четырех": 4, "четырёх": 4, "пяти": 5,
              "шести": 6, "семи": 7, "десяти": 10}
# "опыт коммерческой разработки от 3 лет", "опыт от двух лет", "2+ года", "4+ years", "5+ years of experience"
_YEARS = re.compile(r"(?:(опыт\w*|experience)[^.\n]{0,45}?)?(?:от|более|не менее|больше|from|over)?\s*"
                    r"(\d{1,2}|одного|двух|тр[её]х|четыр[её]х|пяти|шести|семи|десяти)\s*(\+)?\s*"
                    r"(?:-?х|-?ти|-?и)?\s*(?:год|лет|years?|yrs)")
# Russian IT jargon and transliterations that are not proper catalog synonyms (kept out of the catalog shown in UI)
_JARGON = {
    "django": ("джанго",), "postgresql": ("постгрес", "постгря"), "redis": ("редис",), "kafka": ("кафка",),
    "kubernetes": ("кубер", "кубернетес", "eks", "gke"), "react": ("реакт",), "typescript": ("тайпскрипт",),
    "javascript": ("джаваскрипт",), "java": ("джава",), "kotlin": ("котлин",), "webpack": ("вебпак",),
    "terraform": ("терраформ", "ансибл"), "docker": ("докер",), "mongodb": ("монга",),
    "asyncio": ("асинк", "асинхронщина", "aiohttp"), "redux": ("ngrx", "pinia", "vuex"),
    "api_testing": ("restassured", "api-автотесты", "api-тестирование"),
    "test_design": ("тест-стратегия", "test design"),
    "system_design": ("distributed systems", "распределенные системы", "high-load"),
    "http": ("сетей",), "algorithms": ("алгоритмическая", "олимпиады"), "statistics": ("проверка гипотез", "матстат", "a/b-тесты"),
    "ml": ("бустинг", "градиентный бустинг"), "clickhouse": ("кликхаус",), "linux": ("линукс",), "git": ("гит",),
}
# a term "go" is a common word: count it only as the name of the language
_EXTRA_PATTERNS = {"go": [r"(?<![\w])(?:на|язык[еа]?|язык программирования)\s+го(?![\w])", r"(?<![\w])go-разраб"]}
_NICE_MARKERS = r"(будет плюсом|желательно|приветствуется|nice to have|плюсом будет|будет преимуществом|как плюс)"


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


_CYR_VOWELS = "аеиоуыэюяйь"


def _term_regex(term: str) -> str:
    """Exact match for Latin terms; Russian words also match their inflected forms ("питоне", "джангу",
    "постгреса", "статистики"): a long Cyrillic last word loses its final vowel and may take an ending."""
    head, _, last = term.rpartition(" ")
    if len(last) >= 5 and "а" <= last[-1] <= "я":
        stem = last[:-1] if last[-1] in _CYR_VOWELS else last
        body = (re.escape(head + " ") if head else "") + re.escape(stem) + "[а-я]{0,4}"
    else:
        body = re.escape(term)
    return rf"(?<![\w+#.]){body}(?![\w+#])"


def _skill_patterns():
    pats = []
    for s in SKILLS:
        # ids like "cv" ("curriculum vitae") or "dl" collide with ordinary words: match them by title/synonyms only
        ids = () if s.id in ("cv", "dl", "rest", "browser", "cloud") else (s.id,)
        for term in (s.title, *s.synonyms, *_JARGON.get(s.id, ()), *ids):
            t = term.lower().replace("ё", "е")
            if len(t) < 2:
                continue
            pats.append((s.id, re.compile(_term_regex(t))))
        for extra in _EXTRA_PATTERNS.get(s.id, []):
            pats.append((s.id, re.compile(extra)))
    return pats


_PATTERNS = _skill_patterns()


def extract_skills(text: str) -> list[str]:
    """Skill ids in order of first mention. Overlapping matches keep the longest one: "GitLab CI" is CI/CD and
    not also Git, "микросервисная архитектура" is microservices and not also system design."""
    t = _norm(text)
    spans = []
    for sid, pat in _PATTERNS:
        for m in pat.finditer(t):
            spans.append((m.start(), m.end(), sid))
    spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    taken: list[tuple[int, int]] = []
    kept = []
    for a, b, sid in spans:
        if all(b <= x or a >= y for x, y in taken):
            taken.append((a, b))
            kept.append((a, sid))
    found: list[str] = []
    for _, sid in sorted(kept):
        if sid not in found:
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
    for m in _YEARS.finditer(t):
        anchor, value, plus = m.group(1), m.group(2), m.group(3)
        if not (anchor or plus or re.search(r"years?|yrs", m.group(0))):
            continue  # "2 года гарантии" is not experience: need "опыт ...", "N+" or English "years"
        years = int(value) if value.isdigit() else _NUM_WORDS.get(value.replace("ё", "е"), 1)
        return "senior" if years >= 5 else "middle" if years >= 2 else "junior" if years >= 1 else "intern"
    if re.search(r"опыт\w*[^.\n]{0,30}?от года", t):
        return "junior"
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


_NUM = r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d+)?"
_THOUSAND = r"(?:k|к|тыс\w*\.?|т\.\s?р\.?|тр\b)"
_RUB = r"(?:₽|руб\w*\.?|р\.|rub)"
# a number followed by one of these is not money: "3 года", "2M RPS", "5 человек", "10ms", "16+"
_NOT_MONEY = re.compile(r"\s*(?:\+|%|год|лет|years?|человек|rps|ms|мс|м\b|m\b|ч\b|час|дн|мин|сек|gb|гб|мб|x\b)")
_SALARY_CONTEXT = re.compile(r"з/?п|зарплат|оклад|вилк|доход|salary|компенсац|на руки|gross|net")
_MONEY = re.compile(rf"{_NUM}\s*({_THOUSAND})?\s*({_RUB})?")


def _amounts(t: str) -> list[dict]:
    out = []
    for m in _MONEY.finditer(t):
        raw = m.group(1)
        if m.start() > 0 and (t[m.start() - 1].isalnum() or t[m.start() - 1] in "./"):
            continue  # part of a version, an id or a date
        thousand, rub = bool(m.group(2)), bool(m.group(3))
        if not (thousand or rub) and _NOT_MONEY.match(t, m.end(1)):
            continue
        v = float(raw.replace(" ", "").replace("\u00a0", ""))
        bare = not (thousand or rub) and v < 1000
        if thousand or v < 1000:
            v *= 1000  # "200–300" in a salary context means thousands
        if 10_000 <= v <= 5_000_000:
            out.append({"value": int(v), "start": m.start(), "end": m.end(), "unit": thousand or rub or v >= 10_000,
                        "bare": bare})
    return out


def detect_salary(text: str) -> tuple[int | None, int | None]:
    """Salary range in rubles: "от 150 000 до 200 000 ₽", "220–300 тыс.", "250к-300к", "до 280 тысяч", "от 200к",
    a single "400к" / "з/п 100 000 руб." (from = to), and bare "200-260" at the end of a vacancy."""
    t = text.lower().replace("\u00a0", " ")
    amounts = _amounts(t)

    def before(a, words: str) -> bool:
        return re.search(rf"(?:{words})\s*$", t[max(0, a["start"] - 6):a["start"]]) is not None

    for i, a in enumerate(amounts[:-1]):
        b = amounts[i + 1]
        gap = t[a["end"]:b["start"]]
        if a["value"] < b["value"] and (re.fullmatch(r"\s*[-–—]\s*", gap) or
                                        (before(a, "от") and re.fullmatch(rf"\s*(?:{_RUB})?\s*до\s*", gap))):
            if a["unit"] or b["unit"] or not (a["bare"] and b["bare"]) or _SALARY_CONTEXT.search(t) or \
                    b["end"] >= len(t.rstrip(" .")) - 1 or re.match(r"\s*$|\s*[,.;)]", t[b["end"]:]):
                return a["value"], b["value"]
    for a in amounts:
        if before(a, "от|from"):
            return a["value"], None
        if before(a, "до|up to"):
            return None, a["value"]
    for a in amounts:
        if a["unit"] and not a["bare"] or _SALARY_CONTEXT.search(t[max(0, a["start"] - 25):a["start"]]):
            return a["value"], a["value"]
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
