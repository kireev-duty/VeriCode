"""End-to-end scenario from the spec (3.3): registration -> survey -> test -> category -> employer finds the
category -> invitation with salary -> acceptance -> contacts; plus the classic application flow."""

from app.core.db import SessionLocal
from app.models import AssessmentItem, AssessmentSession
from tests.conftest import auth, register


def _answer_correctly(session_id: int) -> object:
    """Test helper: reads the server-side key so the simulated candidate answers right."""
    with SessionLocal() as db:
        s = db.get(AssessmentSession, session_id)
        item = [i for i in s.items if i.is_correct is None][-1]
        return item.id, item.answer["answer"]


def test_login_requires_verified_email(client):
    r = client.post("/api/auth/register", json={"email": "nv@example.com", "password": "password123",
                                                "role": "candidate"})
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={"email": "nv@example.com", "password": "password123"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "email_not_verified"


def test_full_reverse_matching_flow(client):
    cand = auth(register(client, "cand@example.com", "candidate"))
    emp = auth(register(client, "hr@acme.ru", "employer", "ACME"))

    # survey before consent is fine, test requires the survey
    r = client.post("/api/assessment/sessions", json={"target_grade": "middle"}, headers=cand)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "onboarding_required"

    client.post("/api/candidate/consents", json={"processing": True, "publication": True}, headers=cand)
    r = client.post("/api/candidate/onboarding", headers=cand, json={
        "industries": ["Финтех и банки"], "specialization": "backend", "experience_years": 3,
        "declared_grade": "middle", "stack": [{"id": "python", "years": 3}, {"id": "django", "years": 2},
                                              {"id": "postgresql", "years": 3}],
        "work_formats": ["remote", "hybrid"]})
    assert r.status_code == 200, r.text
    client.put("/api/candidate/profile", headers=cand, json={
        "full_name": "Иван Петров", "phone": "+79990001122", "headline": "Python backend developer",
        "salary_expectation": 250000, "city": "Москва"})

    r = client.post("/api/assessment/sessions", json={"target_grade": "middle"}, headers=cand)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json()["current_item"]["prompt"]
    assert "answer" not in r.json()["current_item"]

    for _ in range(30):
        item_id, ans = _answer_correctly(sid)
        r = client.post(f"/api/assessment/sessions/{sid}/answer", headers=cand,
                        json={"item_id": item_id, "response": ans})
        assert r.status_code == 200, r.text
        if r.json()["status"] == "finished":
            break
    res = r.json()["result"]
    assert res["outcome"] in ("confirmed", "upgrade_available")
    assert res["grade"] == "middle"

    # answering an old item is rejected
    r = client.post(f"/api/assessment/sessions/{sid}/answer", headers=cand, json={"item_id": item_id, "response": 1})
    assert r.status_code == 409

    # same grade cannot be re-tested right away
    elig = client.get("/api/assessment/eligibility", headers=cand).json()
    middle = next(g for g in elig["grades"] if g["grade"] == "middle")
    assert middle["allowed"] is False

    # employer: need -> shortlist with explanation, contacts hidden
    client.put("/api/employer/company", headers=emp, json={"name": "ACME", "website": "acme.ru", "inn": "7707083893"})
    parsed = client.post("/api/employer/needs/parse", headers=emp, json={
        "text": "Ищем Middle Python-разработчика на бэкенд: Django, PostgreSQL. Будет плюсом Redis. "
                "Удалённо, 220–300 тыс. руб."}).json()
    assert parsed["specialization"] == "backend" and parsed["grade"] == "middle"
    assert "python" in parsed["must_skills"] and "redis" in parsed["nice_skills"]
    assert parsed["salary_from"] == 220000 and parsed["salary_to"] == 300000
    r = client.post("/api/employer/needs", headers=emp, json={
        "title": "Python backend", "raw_text": "Django PostgreSQL", "specialization": "backend", "grade": "middle",
        "must_skills": parsed["must_skills"], "nice_skills": parsed["nice_skills"], "work_formats": ["remote"],
        "salary_from": 220000, "salary_to": 300000})
    assert r.status_code == 201, r.text
    need_id = r.json()["id"]
    sl = client.post(f"/api/employer/needs/{need_id}/shortlist", headers=emp, json={}).json()
    assert sl["candidates"], sl
    top = sl["candidates"][0]
    assert top["match"]["chips"] and "full_name" not in top
    cand_id = top["id"]

    card = client.get(f"/api/employer/candidates/{cand_id}", headers=emp).json()
    assert card["contacts_open"] is False and card["contacts"] is None
    assert card["test_integrity"]["items"] > 0 and {"paste_events", "blur_events", "fast_correct"} <= set(card["test_integrity"])

    # salary is mandatory, preview tells whether the range fits without revealing the number
    r = client.post("/api/employer/invitations", headers=emp, json={
        "candidate_id": cand_id, "position_title": "Backend", "message": "x" * 30, "contact_method": "tg"})
    assert r.status_code == 422
    pv = client.post("/api/employer/invitations/preview", headers=emp,
                     json={"candidate_id": cand_id, "salary_from": 220000, "salary_to": 300000}).json()
    assert pv["salary_status"] == "fits"
    r = client.post("/api/employer/invitations", headers=emp, json={
        "candidate_id": cand_id, "need_id": need_id, "position_title": "Python backend developer",
        "message": "Добрый день! Команда платёжного шлюза ищет разработчика.", "salary_from": 220000,
        "salary_to": 300000, "contact_method": "@acme_hr"})
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]

    invs = client.get("/api/candidate/invitations", headers=cand).json()
    assert invs[0]["salary_from"] == 220000 and invs[0]["company"]["name"] == "ACME"
    client.post(f"/api/candidate/invitations/{inv_id}/view", headers=cand)
    assert client.get("/api/employer/invitations", headers=emp).json()[0]["status"] == "viewed"
    r = client.post(f"/api/candidate/invitations/{inv_id}/accept", headers=cand)
    assert r.json()["status"] == "accepted"

    card = client.get(f"/api/employer/candidates/{cand_id}", headers=emp).json()
    assert card["contacts_open"] is True and card["contacts"]["full_name"] == "Иван Петров"

    # classic flow: vacancy -> application opens contacts for another company
    emp2 = auth(register(client, "hr@beta.ru", "employer", "Beta"))
    client.put("/api/employer/company", headers=emp2, json={"name": "Beta"})
    v = client.post("/api/employer/vacancies", headers=emp2, json={
        "title": "Backend", "specialization": "backend", "grade": "middle", "must_skills": ["python"],
        "salary_from": 200000, "salary_to": 260000}).json()
    assert client.get(f"/api/employer/candidates/{cand_id}", headers=emp2).json()["contacts_open"] is False
    r = client.post(f"/api/candidate/vacancies/{v['id']}/apply", headers=cand, json={"cover_letter": "Здравствуйте"})
    assert r.status_code == 200, r.text
    apps = client.get(f"/api/employer/vacancies/{v['id']}/applications", headers=emp2).json()
    assert apps[0]["candidate"]["contacts"]["phone"] == "+79990001122"


def test_candidate_without_fsp_is_searchable_and_fsp_link_works(client):
    cand = auth(register(client, "nofsp@example.com", "candidate"))
    prof = client.get("/api/candidate/profile", headers=cand).json()
    assert prof["achievements"] == [] and prof["fsp_id"] is None
    start = client.get("/api/candidate/fsp/start", headers=cand).json()
    state = start["url"].split("state=")[1]
    r = client.post("/api/candidate/fsp/callback", headers=cand, json={"code": "mock:FSP-123457", "state": state})
    assert r.status_code == 200, r.text
    assert r.json()["fsp_id"] == "FSP-123457" and len(r.json()["achievements"]) >= 1
    # unknown participant
    r = client.post("/api/candidate/fsp/callback", headers=cand, json={"code": "mock:FSP-999999", "state": state})
    assert r.status_code == 404


def test_access_control(client):
    cand = auth(register(client, "ac@example.com", "candidate"))
    emp = auth(register(client, "ac@corp.ru", "employer", "Corp"))
    assert client.get("/api/employer/company", headers=cand).status_code == 403
    assert client.get("/api/candidate/profile", headers=emp).status_code == 403
    assert client.get("/api/candidate/profile").status_code == 401
    with SessionLocal() as db:
        other = db.query(AssessmentItem).first()
    if other:
        r = client.get(f"/api/assessment/sessions/{other.session_id}", headers=cand)
        assert r.status_code == 404
