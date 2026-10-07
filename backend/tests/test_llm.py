"""LLM layer: refines the rules, never trusts the model blindly, falls back on any failure."""

import json

import pytest

from app.modules import llm, nlp
from app.modules.resume import parse_resume_text


class FakeProvider(llm.LLMProvider):
    name = "fake"

    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.calls = 0

    def chat(self, system: str, user: str) -> str:
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture(autouse=True)
def no_provider():
    yield
    llm.set_provider(None)


TEXT = ("Нужен сильный бэкендер на Python, знание реляционных баз, опыт с очередями сообщений приветствуется. "
        "Удалёнка, до 300 тысяч.")


def test_without_provider_rules_are_returned():
    llm.set_provider(None)
    rules = nlp.parse_need(TEXT)
    out, source = llm.refine_need(TEXT, rules)
    assert out == rules and source == llm.RULES


def test_refine_need_validates_against_catalog():
    reply = json.dumps({"specialization": "backend", "grade": "senior", "must_skills": ["python", "sql", "cobol9000"],
                        "nice_skills": ["rabbitmq", "kafka"], "work_formats": ["remote", "spaceship"], "city": "",
                        "salary_from": None, "salary_to": 300000})
    llm.set_provider(FakeProvider("Вот разбор:\n```json\n" + reply + "\n```"))
    rules = nlp.parse_need(TEXT)
    out, source = llm.refine_need(TEXT, rules)
    assert source == llm.RULES_LLM
    assert "cobol9000" not in out["must_skills"] + out["nice_skills"], "unknown skill ids are dropped"
    assert {"python", "sql"} <= set(out["must_skills"])
    assert "python" not in out["nice_skills"], "a skill is either required or optional"
    assert set(out["nice_skills"]) >= {"rabbitmq", "kafka"}
    assert out["salary_to"] == rules["salary_to"] == 300000, "exact fields keep the rule value"
    assert out["work_formats"] == ["remote"]


@pytest.mark.parametrize("reply", [RuntimeError("timeout"), "не JSON", "[1, 2]"])
def test_failures_fall_back_to_rules(reply):
    llm.set_provider(FakeProvider(reply))
    rules = nlp.parse_need(TEXT)
    out, source = llm.refine_need(TEXT, rules)
    assert out == rules and source == llm.RULES


def test_malformed_fields_are_ignored():
    llm.set_provider(FakeProvider('{"must_skills": "python", "grade": "guru", "salary_from": "много"}'))
    rules = nlp.parse_need(TEXT)
    out, _ = llm.refine_need(TEXT, rules)
    assert out["must_skills"] == rules["must_skills"]
    assert out["grade"] == rules["grade"] and out["salary_from"] == rules["salary_from"]


def test_answers_are_cached():
    fake = FakeProvider('{"specialization": "backend"}')
    llm.set_provider(fake)
    llm.refine_need(TEXT, nlp.parse_need(TEXT))
    llm.refine_need(TEXT, nlp.parse_need(TEXT))
    assert fake.calls == 1


def test_refine_resume_keeps_exact_contacts():
    text = "Иван Петров\nPython-разработчик\nivan@example.com +7 999 000-11-22\nДелал API на FastAPI и PostgreSQL."
    rules = parse_resume_text(text)
    llm.set_provider(FakeProvider(json.dumps({
        "full_name": "Иван Петров", "headline": "Python-разработчик", "experience_years": 4,
        "skills": ["fastapi", "postgresql", "docker", "nonexistent"], "specialization": "backend",
        "soft_skills": ["Коммуникация", "Телепатия"], "team_roles": ["Тимлид"]})))
    out, source = llm.refine_resume(text, rules)
    assert source == llm.RULES_LLM
    assert out["contact_email"] == "ivan@example.com" and out["phone"] == rules["phone"]
    ids = {s["id"] for s in out["skills"]}
    assert {"fastapi", "postgresql", "docker"} <= ids and "nonexistent" not in ids
    assert "Телепатия" not in out["soft_skills"] and "Коммуникация" in out["soft_skills"]


def test_rubric_point_needs_a_real_quote():
    answer = "Сначала посмотрю метрики и логи, затем воспроизведу проблему на стенде и только потом откачу релиз."
    reply = json.dumps({"points": [
        {"index": 0, "covered": True, "quote": "посмотрю метрики и логи"},
        {"index": 1, "covered": True, "quote": "напишу постмортем для команды"},  # not in the answer
        {"index": 2, "covered": False, "quote": ""},
    ]})
    llm.set_provider(FakeProvider(reply))
    covered = llm.grade_approach("Инцидент в проде", ["Диагностика", "Постмортем", "Откат"], answer)
    assert covered == [True, False, False]


def test_chain_falls_through_to_the_next_provider():
    down, up = FakeProvider(RuntimeError("connect timeout")), FakeProvider('{"specialization": "backend"}')
    llm.set_provider(llm.ChainProvider([down, up]))
    _, source = llm.refine_need(TEXT, nlp.parse_need(TEXT))
    assert source == llm.RULES_LLM and down.calls == up.calls == 1


def test_chain_all_down_falls_back_to_rules():
    llm.set_provider(llm.ChainProvider([FakeProvider(RuntimeError("a")), FakeProvider(RuntimeError("b"))]))
    rules = nlp.parse_need(TEXT)
    assert llm.refine_need(TEXT, rules) == (rules, llm.RULES)


def test_provider_chain_from_settings(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "gigachat, local")
    monkeypatch.setattr(llm.settings, "llm_api_key", "key")
    llm._provider_ready = False
    p = llm.get_provider()
    assert isinstance(p, llm.ChainProvider) and p.name == "gigachat,local"
    monkeypatch.setattr(llm.settings, "llm_provider", "local")
    llm._provider_ready = False
    assert isinstance(llm.get_provider(), llm.LocalProvider)


def test_local_provider_strips_reasoning(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '<think>{"x": 1}</think>\n{"specialization": "qa"}'}}]}

    sent = {}
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: sent.update(url=url, **kw) or Resp())
    out = llm.LocalProvider("http://ollama:11434/v1/", "qwen3:4b", "", 5).chat("sys", "user")
    assert llm._first_json(out) == {"specialization": "qa"}
    assert sent["url"] == "http://ollama:11434/v1/chat/completions" and "Authorization" not in sent["headers"]
