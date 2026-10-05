import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["SMTP_HOST"] = ""  # no mail server in tests: registration works via the dev verification link

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def register(client, email: str, role: str, company_name: str | None = None) -> str:
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "role": role,
                                                "company_name": company_name})
    assert r.status_code == 201, r.text
    token = r.json()["dev_verify_link"].split("token=")[1]
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
