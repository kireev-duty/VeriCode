"""Visibility rules of the spec (2.2) and the platform policies: contacts, foreign records, quota, grade cooldown."""

from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal, utcnow
from app.models import CandidateProfile, User
from tests.conftest import auth, register


def graded_candidate(client, email: str, *, grade: str = "middle", visible: bool = True) -> tuple[dict, int]:
    """A candidate who passed onboarding; the test result is written directly (the test flow has its own test)."""
    h = auth(register(client, email, "candidate"))
    client.post("/api/candidate/consents", json={"processing": True, "publication": True}, headers=h)
    r = client.post("/api/candidate/onboarding", headers=h, json={
        "industries": ["Финтех и банки"], "specialization": "backend", "experience_years": 3, "declared_grade": grade,
        "stack": [{"id": "python", "years": 3}], "work_formats": ["remote"]})
    assert r.status_code == 200, r.text
    client.put("/api/candidate/profile", headers=h, json={"full_name": "Секретное Имя", "phone": "+79990000000",
                                                          "salary_expectation": 200000})
    with SessionLocal() as db:
        cand = db.query(CandidateProfile).join(User).filter(User.email == email).one()
        cand.grade, cand.theta, cand.skill_theta = grade, 0.5, {"python": 0.6}
        cand.grade_confirmed_at = cand.grade_changed_at = utcnow()
        cand.visible_to_employers = visible
        db.commit()
        return h, cand.id


def employer(client, email: str, name: str) -> dict:
    h = auth(register(client, email, "employer", name))
    client.put("/api/employer/company", headers=h, json={"name": name})
    return h


def invite(client, h: dict, cand_id: int):
    return client.post("/api/employer/invitations", headers=h, json={
        "candidate_id": cand_id, "position_title": "Backend-разработчик", "message": "Здравствуйте! Есть предложение.",
        "salary_from": 200000, "salary_to": 260000, "contact_method": "@hr"})


def test_contacts_stay_hidden_until_accept_and_after_decline(client):
    _, cid = graded_candidate(client, "acc1@example.com")
    cand_h = auth(client.post("/api/auth/login", json={"email": "acc1@example.com", "password": "password123"})
                  .json()["access_token"])
    emp = employer(client, "hr1@alpha.ru", "Alpha")
    card = client.get(f"/api/employer/candidates/{cid}", headers=emp).json()
    assert card["contacts"] is None and "Секретное" not in str(card)
    inv = invite(client, emp, cid).json()
    r = client.post(f"/api/candidate/invitations/{inv['id']}/decline", headers=cand_h, json={"reason": "salary"})
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert client.get(f"/api/employer/candidates/{cid}", headers=emp).json()["contacts"] is None
    # the decline reason adapted this company's weights
    assert client.get("/api/employer/analytics", headers=emp).status_code == 200


def test_foreign_records_are_not_reachable(client):
    _, cid = graded_candidate(client, "acc2@example.com")
    other_h, _ = graded_candidate(client, "acc3@example.com")
    emp_a, emp_b = employer(client, "hr2@alpha.ru", "Alpha2"), employer(client, "hr2@beta.ru", "Beta2")
    inv_id = invite(client, emp_a, cid).json()["id"]
    # another candidate cannot open or accept it
    assert client.post(f"/api/candidate/invitations/{inv_id}/accept", headers=other_h).status_code == 404
    assert all(i["id"] != inv_id for i in client.get("/api/candidate/invitations", headers=other_h).json())
    # another company cannot withdraw it or see it
    assert client.post(f"/api/employer/invitations/{inv_id}/withdraw", headers=emp_b).status_code == 404
    assert all(i["id"] != inv_id for i in client.get("/api/employer/invitations", headers=emp_b).json())


def test_hidden_candidate_is_not_searchable_or_invitable(client):
    _, cid = graded_candidate(client, "acc4@example.com", visible=False)
    emp = employer(client, "hr4@alpha.ru", "Alpha4")
    found = client.post("/api/employer/search", headers=emp, json={}).json()
    assert cid not in {c["id"] for c in (found if isinstance(found, list) else found.get("candidates", []))}
    r = invite(client, emp, cid)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "candidate_unavailable"


def test_weekly_invitation_quota(client, monkeypatch):
    monkeypatch.setattr(settings, "invitation_weekly_quota", 1)
    _, c1 = graded_candidate(client, "acc5@example.com")
    _, c2 = graded_candidate(client, "acc6@example.com")
    emp = employer(client, "hr5@alpha.ru", "Alpha5")
    assert invite(client, emp, c1).status_code == 201
    r = invite(client, emp, c2)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "quota_exceeded"


def test_duplicate_active_invitation_is_rejected(client):
    _, cid = graded_candidate(client, "acc7@example.com")
    emp = employer(client, "hr7@alpha.ru", "Alpha7")
    assert invite(client, emp, cid).status_code == 201
    assert invite(client, emp, cid).json()["detail"]["code"] == "already_invited"


def test_grade_change_cooldown(client):
    h, cid = graded_candidate(client, "acc8@example.com", grade="middle")

    def senior_allowed() -> bool:
        grades = client.get("/api/assessment/eligibility", headers=h).json()["grades"]
        return next(g for g in grades if g["grade"] == "senior")["allowed"]

    assert senior_allowed() is False, "grade confirmed today: no change for 90 days"
    with SessionLocal() as db:
        cand = db.get(CandidateProfile, cid)
        cand.grade_changed_at = cand.grade_confirmed_at = utcnow() - timedelta(days=settings.grade_change_cooldown_days + 1)
        db.commit()
    assert senior_allowed() is True
    r = client.post("/api/assessment/sessions", json={"target_grade": "senior"}, headers=h)
    assert r.status_code == 200, r.text


def test_pilot_survey_and_item_reports_are_own_and_after_finish(client, monkeypatch):
    from tests.test_flow import _answer_correctly

    h, _ = graded_candidate(client, "pilot1@example.com")
    other, _ = graded_candidate(client, "pilot2@example.com")
    with SessionLocal() as db:  # the helper wrote a grade directly: clear it so the first test is allowed
        cand = db.query(CandidateProfile).join(User).filter(User.email == "pilot1@example.com").one()
        cand.grade = cand.grade_confirmed_at = cand.grade_changed_at = None
        db.commit()
    sid = client.post("/api/assessment/sessions", json={"target_grade": "junior"}, headers=h).json()["id"]
    survey = {"experience_years": 2, "position": "Backend-разработчик", "self_grade": "junior", "lead_grade": "middle"}
    r = client.post(f"/api/assessment/sessions/{sid}/survey", json=survey, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_finished"
    for _ in range(30):
        item_id, ans = _answer_correctly(sid)
        r = client.post(f"/api/assessment/sessions/{sid}/answer", headers=h, json={"item_id": item_id, "response": ans})
        if r.json()["status"] == "finished":
            break
    assert client.post(f"/api/assessment/sessions/{sid}/survey", json=survey, headers=other).status_code == 404
    assert client.post(f"/api/assessment/sessions/{sid}/survey", json={**survey, "lead_grade": "guru"},
                       headers=h).status_code == 422
    assert client.post(f"/api/assessment/sessions/{sid}/survey", json=survey, headers=h).json() == {"done": True}
    assert client.get(f"/api/assessment/sessions/{sid}/survey", headers=h).json()["lead_grade"] == "middle"

    rep = {"reason": "unclear", "text": "Не понял условие"}
    assert client.post(f"/api/assessment/sessions/{sid}/items/1/report", json=rep, headers=other).status_code == 404
    assert client.post(f"/api/assessment/sessions/{sid}/items/99/report", json=rep, headers=h).status_code == 404
    assert client.post(f"/api/assessment/sessions/{sid}/items/1/report", json=rep, headers=h).status_code == 200
    review = client.get(f"/api/assessment/sessions/{sid}", headers=h).json()["review"]
    assert review[0]["reported"] and not review[1]["reported"]

    assert client.get("/api/assessment/pilot/export").status_code == 403  # disabled without a token
    monkeypatch.setattr(settings, "pilot_export_token", "secret-token")
    assert client.get("/api/assessment/pilot/export", headers={"X-Pilot-Token": "wrong"}).status_code == 403
    data = client.get("/api/assessment/pilot/export", headers={"X-Pilot-Token": "secret-token"}).json()
    row = next(x for x in data["sessions"] if x["session"] == sid)
    assert row["survey"]["lead_grade"] == "middle" and row["items"][0]["report"]["reason"] == "unclear"
    assert "pilot1" not in str(data) and "Секретное" not in str(data)  # pseudonymised


def test_demo_new_candidate_is_fresh_for_every_expert_and_uses_express_test(client):
    onboarding = {"industries": ["Финтех и банки"], "specialization": "backend", "experience_years": 1,
                  "declared_grade": "junior", "stack": [{"id": "python", "years": 1}], "work_formats": ["remote"]}
    ids = set()
    for _ in range(2):
        r = client.post("/api/auth/demo-login?role=candidate_new")
        assert r.status_code == 200, r.text
        ids.add(r.json()["user"]["id"])
        h = auth(r.json()["access_token"])
        client.post("/api/candidate/consents", json={"processing": True, "publication": True}, headers=h)
        assert client.post("/api/candidate/onboarding", headers=h, json=onboarding).status_code == 200
        s = client.post("/api/assessment/sessions", json={"target_grade": "junior"}, headers=h)
        assert s.status_code in (200, 201), s.text
        assert s.json()["express"] is True and s.json()["max_items"] < 18
    assert len(ids) == 2


def test_unconfirmed_grade_is_shown_below_confirmed_and_can_be_invited(client):
    _, confirmed_id = graded_candidate(client, "conf.tail@test.ru", grade="middle")
    _, unconf_id = graded_candidate(client, "unconf.tail@test.ru", grade="middle")
    with SessionLocal() as db:
        c = db.get(CandidateProfile, unconf_id)
        c.grade, c.claimed_grade, c.theta = None, "middle", 1.5  # strong ability, but the grade failed
        db.commit()
    h = employer(client, "hr.tail@test.ru", "Хвост")
    found = client.post("/api/employer/search", headers=h,
                        json={"q": "", "filters": {"grades": ["middle"]}}).json()
    ids = [x["id"] for x in found]
    assert confirmed_id in ids and unconf_id in ids
    assert all(x["grade_confirmed"] for x in found[:ids.index(unconf_id)])
    card = next(x for x in found if x["id"] == unconf_id)
    assert card["grade_confirmed"] is False and card["claimed_grade"] == "middle"

    assert client.get(f"/api/employer/candidates/{unconf_id}", headers=h).status_code == 200
    p = client.post("/api/employer/invitations/preview", headers=h,
                    json={"candidate_id": unconf_id, "salary_from": 200000, "salary_to": 260000}).json()
    assert "не подтверждён" in p["grade_warning"]
    assert invite(client, h, unconf_id).status_code in (200, 201)
