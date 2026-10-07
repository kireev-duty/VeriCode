"""Optional LLM layer over the rule-based NLP: GigaChat, YandexGPT or a local open-weight model (Qwen3 via Ollama)
behind one small interface, optionally as a fallback chain.

The rules (app.modules.nlp, app.modules.resume, app.modules.tasks) always run first and stay the baseline.
The LLM only refines their result, and its output is never trusted as is:
* skills, specializations, grades and work formats are accepted only as ids from the catalog;
* exact fields the rules extract reliably (salary, email, phone) keep the rule value;
* a rubric point counts as covered only if the quote the model cites is really present in the answer.
Any network error, timeout or malformed answer returns None and the caller keeps the rule result, so every
scenario works without a key. Check a key from the command line: `uv run python -m app.modules.llm "текст"`.
"""

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict

import httpx

from app.catalog import GRADE_ORDER, SKILL_BY_ID, SKILLS, SOFT_SKILLS, SPEC_BY_ID, TEAM_ROLES, WORK_FORMATS
from app.core.config import settings

log = logging.getLogger(__name__)

RULES = "rules"
RULES_LLM = "rules+llm"


class LLMProvider:
    name = "none"

    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError


class GigaChatProvider(LLMProvider):
    """Sber GigaChat: the authorization key is exchanged for a 30-minute access token (OAuth, scope)."""

    name = "gigachat"
    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(self, key: str, model: str, scope: str, verify: bool | str, timeout: float):
        self.key, self.model, self.scope, self.verify, self.timeout = key, model or "GigaChat", scope, verify, timeout
        self._token, self._expires = "", 0.0
        self._lock = threading.Lock()
        # Sber hosts drop part of TCP handshakes: fail the connect fast and retry it (only connect errors are retried)
        self._http = httpx.Client(transport=httpx.HTTPTransport(verify=verify, retries=2),
                                  timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)))

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires - 60:
                return self._token
            r = self._http.post(self.OAUTH_URL, data={"scope": self.scope},
                                headers={"Authorization": f"Basic {self.key}", "RqUID": str(uuid.uuid4()),
                                         "Accept": "application/json"})
            r.raise_for_status()
            d = r.json()
            self._token, self._expires = d["access_token"], d.get("expires_at", 0) / 1000 or time.time() + 1500
            return self._token

    def chat(self, system: str, user: str) -> str:
        r = self._http.post(self.CHAT_URL, headers={"Authorization": f"Bearer {self._access_token()}"},
                            json={"model": self.model, "temperature": 0.01, "max_tokens": 1500,
                                  "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class YandexGPTProvider(LLMProvider):
    """YandexGPT (Yandex Cloud Foundation Models): API key of a service account + folder id."""

    name = "yandex"
    URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def __init__(self, key: str, model: str, folder: str, timeout: float):
        self.key, self.model, self.folder, self.timeout = key, model or "yandexgpt-lite/latest", folder, timeout

    def chat(self, system: str, user: str) -> str:
        r = httpx.post(self.URL, timeout=self.timeout,
                       headers={"Authorization": f"Api-Key {self.key}", "x-folder-id": self.folder},
                       json={"modelUri": f"gpt://{self.folder}/{self.model}",
                             "completionOptions": {"stream": False, "temperature": 0.05, "maxTokens": "1500"},
                             "messages": [{"role": "system", "text": system}, {"role": "user", "text": user}]})
        r.raise_for_status()
        return r.json()["result"]["alternatives"][0]["message"]["text"]


class LocalProvider(LLMProvider):
    """Open-weight model on our own server behind an OpenAI-compatible API: Ollama (default, Qwen3 4B, Apache-2.0),
    vLLM or llama.cpp server. Resumes never leave the server, no key is needed."""

    name = "local"

    def __init__(self, url: str, model: str, key: str, timeout: float):
        self.url, self.model, self.key, self.timeout = url.rstrip("/"), model, key, timeout

    def chat(self, system: str, user: str) -> str:
        r = httpx.post(f"{self.url}/chat/completions", timeout=self.timeout,
                       headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                       # "/no_think": Qwen3 skips the reasoning pass, which takes minutes on a CPU
                       json={"model": self.model, "temperature": 0.01, "max_tokens": 1500,
                             "response_format": {"type": "json_object"},
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user + "\n/no_think"}]})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S)


class ChainProvider(LLMProvider):
    """Providers in order (LLM_PROVIDER=gigachat,local): the next one answers when the previous fails."""

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers
        self.name = ",".join(p.name for p in providers)

    def chat(self, system: str, user: str) -> str:
        for i, p in enumerate(self.providers):
            try:
                return p.chat(system, user)
            except Exception as e:  # noqa: BLE001 - try the next provider, the last error goes to the caller
                if i == len(self.providers) - 1:
                    raise
                log.warning("LLM %s failed, trying %s: %s", p.name, self.providers[i + 1].name, e)
        raise RuntimeError("empty provider chain")


_provider: LLMProvider | None = None
_provider_ready = False
_cache: OrderedDict[str, dict] = OrderedDict()
_CACHE_SIZE = 256


def get_provider() -> LLMProvider | None:
    global _provider, _provider_ready
    if not _provider_ready:
        chain: list[LLMProvider] = []
        key = settings.llm_api_key
        for kind in (k.strip() for k in settings.llm_provider.lower().split(",")):
            if kind == "gigachat" and key:
                verify: bool | str = settings.llm_ca_bundle or settings.llm_verify_ssl
                chain.append(GigaChatProvider(key, settings.llm_model, settings.llm_scope, verify, settings.llm_timeout))
            elif kind == "yandex" and key and settings.llm_folder_id:
                chain.append(YandexGPTProvider(key, settings.llm_model, settings.llm_folder_id, settings.llm_timeout))
            elif kind == "local" and settings.local_llm_url:
                chain.append(LocalProvider(settings.local_llm_url, settings.local_llm_model, settings.local_llm_key,
                                           settings.local_llm_timeout))
        _provider = chain[0] if len(chain) == 1 else ChainProvider(chain) if chain else None
        _provider_ready = True
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Tests and the validation script swap the provider explicitly."""
    global _provider, _provider_ready
    _provider, _provider_ready = provider, True
    _cache.clear()


def enabled() -> bool:
    return get_provider() is not None


def _first_json(text: str) -> dict | None:
    """Models wrap JSON in prose or ```json fences: take the outermost {...} object."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def complete_json(system: str, user: str) -> dict | None:
    provider = get_provider()
    if provider is None:
        return None
    key = hashlib.sha256(f"{provider.name}\0{system}\0{user}".encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    try:
        data = _first_json(provider.chat(system, user))
    except Exception as e:  # noqa: BLE001 - network, auth, quota, schema: the rules take over
        log.warning("LLM %s failed: %s", provider.name, e)
        return None
    if data is None:
        log.warning("LLM %s returned no JSON object", provider.name)
        return None
    _cache[key] = data
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return data


# ------------------------------------------------------------------------------------------------ sanitizers


def _skill_ids(value) -> list[str]:
    out: list[str] = []
    for s in value if isinstance(value, list) else []:
        sid = str(s).strip().lower()
        if sid in SKILL_BY_ID and sid not in out:
            out.append(sid)
    return out


def _choice(value, allowed) -> str | None:
    v = str(value).strip().lower() if value is not None else ""
    return v if v in allowed else None


def _money(value) -> int | None:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return None
    return v if 10_000 <= v <= 5_000_000 else None


def _catalog_prompt() -> str:
    return "; ".join(f"{s.id}={s.title}" for s in SKILLS)


# ------------------------------------------------------------------------------------------------ need


NEED_SYSTEM = """Ты разбираешь описание потребности работодателя в ИТ-специалисте. Верни только JSON:
{"specialization": "<id>", "grade": "<id или null>", "must_skills": ["<id>"], "nice_skills": ["<id>"],
 "work_formats": ["office"|"hybrid"|"remote"], "city": "<город или пустая строка>",
 "salary_from": <число в рублях в месяц или null>, "salary_to": <число или null>}
Специализации: """ + ", ".join(SPEC_BY_ID) + """. Грейды: """ + ", ".join(GRADE_ORDER) + """.
Навыки указывай только id из справочника; навык, которого нет в справочнике, пропусти. Если сказано
«будет плюсом», «желательно», «приветствуется» — навык в nice_skills, иначе в must_skills. Синонимы и описания
(«реляционные базы» = sql, «контейнеризация» = docker) сопоставляй со справочником. Справочник навыков: """


def refine_need(text: str, rules: dict) -> tuple[dict, str]:
    data = complete_json(NEED_SYSTEM + _catalog_prompt(), text[:6000])
    if not data:
        return rules, RULES
    llm_must, llm_nice = _skill_ids(data.get("must_skills")), _skill_ids(data.get("nice_skills"))
    must = list(dict.fromkeys(llm_must + [s for s in rules["must_skills"] if s not in llm_nice]))
    nice = [s for s in dict.fromkeys(llm_nice + rules["nice_skills"]) if s not in must]
    lo, hi = _money(data.get("salary_from")), _money(data.get("salary_to"))
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    formats = [f for f in (data.get("work_formats") or []) if f in WORK_FORMATS] if isinstance(
        data.get("work_formats"), list) else []
    out = {
        **rules,
        "specialization": _choice(data.get("specialization"), SPEC_BY_ID) or rules["specialization"],
        "grade": rules["grade"] or _choice(data.get("grade"), GRADE_ORDER),
        "must_skills": must,
        "nice_skills": nice,
        "work_formats": rules["work_formats"] or formats,
        "city": rules["city"] or str(data.get("city") or "").strip()[:100],
        "salary_from": rules["salary_from"] if rules["salary_from"] is not None else lo,
        "salary_to": rules["salary_to"] if rules["salary_to"] is not None else hi,
    }
    return out, RULES_LLM


# ------------------------------------------------------------------------------------------------ resume


RESUME_SYSTEM = """Ты разбираешь текст резюме ИТ-специалиста. Верни только JSON:
{"full_name": "<ФИО>", "headline": "<текущая или последняя должность>", "positions": ["<должность>"],
 "experience_years": <общий стаж в годах, число>, "skills": ["<id>"], "specialization": "<id>",
 "soft_skills": ["<из списка>"], "team_roles": ["<из списка>"]}
Специализации: """ + ", ".join(SPEC_BY_ID) + """. Софт-скиллы: """ + ", ".join(SOFT_SKILLS) + """.
Роли в команде: """ + ", ".join(TEAM_ROLES) + """. Навыки — только id из справочника: """


def refine_resume(text: str, rules: dict) -> tuple[dict, str]:
    data = complete_json(RESUME_SYSTEM + _catalog_prompt(), text[:8000])
    if not data:
        return rules, RULES
    rule_skills = [s["id"] for s in rules["skills"]]
    skills = list(dict.fromkeys(rule_skills + _skill_ids(data.get("skills"))))
    name = str(data.get("full_name") or "").strip()
    name_ok = 2 <= len(name.split()) <= 4 and len(name) <= 80 and not re.search(r"[\d@]", name)
    try:
        years = float(data.get("experience_years"))
    except (TypeError, ValueError):
        years = -1
    soft = [s for s in data.get("soft_skills") or [] if s in SOFT_SKILLS] if isinstance(data.get("soft_skills"), list) else []
    roles = [r for r in data.get("team_roles") or [] if r in TEAM_ROLES] if isinstance(data.get("team_roles"), list) else []
    positions = [str(p).strip()[:90] for p in data.get("positions") or [] if str(p).strip()] if isinstance(
        data.get("positions"), list) else []
    out = {
        **rules,  # email, phone, telegram, city, work formats: exact rule extraction is kept
        "full_name": rules["full_name"] or (name if name_ok else ""),
        "headline": str(data.get("headline") or "").strip()[:200] or rules["headline"],
        "positions": positions[:6] or rules["positions"],
        "experience_years": round(years, 1) if 0 <= years <= 50 and not rules["experience_years"] else rules[
            "experience_years"],
        "skills": [{"id": s, "years": None} for s in skills],
        "specialization": _choice(data.get("specialization"), SPEC_BY_ID) or rules["specialization"],
        "soft_skills": list(dict.fromkeys(rules["soft_skills"] + soft)),
        "team_roles": list(dict.fromkeys(rules["team_roles"] + roles)),
    }
    return out, RULES_LLM


# ------------------------------------------------------------------------------------------------ approach tasks


APPROACH_SYSTEM = """Ты проверяешь ответ кандидата на задачу «предложите подход к решению» по рубрике.
Для каждого пункта рубрики реши, раскрыт ли он в ответе по смыслу (не по словам). Если раскрыт, приведи
дословную цитату из ответа (до 120 символов), которая это показывает. Верни только JSON:
{"points": [{"index": <номер пункта с 0>, "covered": true|false, "quote": "<цитата или пустая строка>"}]}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("ё", "е")).strip(" .,;:«»\"'")


def grade_approach(task_text: str, rubric_points: list[str], answer: str) -> list[bool] | None:
    """Per rubric point: covered (with a verified quote) or not. None if the LLM is unavailable."""
    if not rubric_points or not answer.strip():
        return None
    points = "\n".join(f"{i}. {p}" for i, p in enumerate(rubric_points))
    data = complete_json(APPROACH_SYSTEM, f"Задача:\n{task_text[:3000]}\n\nРубрика:\n{points}\n\nОтвет:\n{answer[:4000]}")
    if not data or not isinstance(data.get("points"), list):
        return None
    covered = [False] * len(rubric_points)
    norm_answer = _norm(answer)
    for p in data["points"]:
        if not isinstance(p, dict):
            continue
        try:
            i = int(p.get("index"))
        except (TypeError, ValueError):
            continue
        quote = _norm(str(p.get("quote") or ""))
        if 0 <= i < len(covered) and p.get("covered") is True and len(quote) >= 8 and quote in norm_answer:
            covered[i] = True
    return covered


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    provider = get_provider()
    print(f"provider: {provider.name if provider else 'none (LLM_PROVIDER / LLM_API_KEY not set)'}")
    sample = " ".join(sys.argv[1:]) or ("Нужен сильный бэкендер на Python, знание реляционных баз, опыт с очередями "
                                        "сообщений приветствуется. Удалёнка, до 300 тысяч.")
    from app.modules import nlp

    rules = nlp.parse_need(sample)
    refined, source = refine_need(sample, rules)
    print(json.dumps({"rules": rules, "refined": refined, "source": source}, ensure_ascii=False, indent=1))
