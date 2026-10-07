"""Resume upload (POST /api/candidate/resume): a real PDF from the validation set is parsed into a draft."""

from pathlib import Path

from tests.conftest import auth, register

PDF = Path(__file__).resolve().parents[1] / "validation" / "data" / "resumes" / "resume_02_sidebar.pdf"


def test_resume_pdf_is_parsed_into_a_draft(client):
    h = auth(register(client, "resume1@example.com", "candidate"))
    r = client.post("/api/candidate/resume", headers=h, files={"file": ("cv.pdf", PDF.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["full_name"] == "Дмитрий Орлов"  # two-column template: the name comes after the sidebar
    assert d["phone"] == "+79991234567" and d["contact_email"] == "d.orlov@example.org"
    assert d["telegram"] == "@orlov_front" and d["city"] == "Москва"
    assert {"react", "typescript"} <= {s["id"] for s in d["skills"]}
    assert d["specialization"] == "frontend" and d["experience_years"] >= 7
    assert d["source"] == "rules"


def test_resume_rejects_non_pdf(client):
    h = auth(register(client, "resume2@example.com", "candidate"))
    r = client.post("/api/candidate/resume", headers=h, files={"file": ("cv.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400
