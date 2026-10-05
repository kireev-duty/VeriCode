"""FSP ID (OIDC, Keycloak-compatible) and registry client.

Linking flow:
  1. GET  /api/candidate/fsp/start   -> authorize URL of FSP ID (Keycloak realm "fsp") with a signed state;
  2. FSP ID redirects the browser to {PUBLIC_URL}/fsp/callback?code=...&state=...;
  3. POST /api/candidate/fsp/callback -> code is exchanged for tokens, the fsp_id claim identifies the participant;
  4. the registry is queried by fsp_id, achievements are stored as read-only verified records.
Without Keycloak (FSP_OIDC_ENABLED=false) step 1 points to a built-in mock login page, keeping the same flow.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings
from app.modules.fsp import registry_app


class FspError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def redirect_uri() -> str:
    return f"{settings.public_url}/fsp/callback"


def make_state(candidate_id: int) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=15)
    return jwt.encode({"cid": candidate_id, "purpose": "fsp_link", "exp": exp}, settings.jwt_secret, "HS256")


def check_state(state: str, candidate_id: int) -> None:
    try:
        data = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise FspError("invalid_state", "Сессия привязки устарела, начните заново") from None
    if data.get("cid") != candidate_id or data.get("purpose") != "fsp_link":
        raise FspError("invalid_state", "Неверный параметр state")


def authorize_url(candidate_id: int) -> dict:
    state = make_state(candidate_id)
    if not settings.fsp_oidc_enabled:
        return {"mode": "mock", "url": f"{settings.public_url}/fsp/mock-login?" + urlencode({"state": state})}
    params = {"client_id": settings.fsp_oidc_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
              "scope": "openid profile", "state": state}
    return {"mode": "oidc",
            "url": f"{settings.fsp_oidc_public_issuer}/protocol/openid-connect/auth?" + urlencode(params)}


def exchange_code(code: str) -> str:
    """Returns fsp_id of the authenticated participant."""
    if not settings.fsp_oidc_enabled:
        if not code.startswith("mock:"):
            raise FspError("invalid_code", "Неверный код авторизации")
        return code.removeprefix("mock:").strip().upper()
    try:
        resp = httpx.post(f"{settings.fsp_oidc_issuer}/protocol/openid-connect/token", timeout=10, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
            "client_id": settings.fsp_oidc_client_id, "client_secret": settings.fsp_oidc_client_secret})
        resp.raise_for_status()
        tokens = resp.json()
        info = httpx.get(f"{settings.fsp_oidc_issuer}/protocol/openid-connect/userinfo", timeout=10,
                         headers={"Authorization": f"Bearer {tokens['access_token']}"})
        info.raise_for_status()
        claims = info.json()
    except (httpx.HTTPError, KeyError) as exc:
        raise FspError("oidc_failed", f"ФСП ID не подтвердил вход: {exc}") from None
    fsp_id = claims.get("fsp_id") or claims.get("preferred_username")
    if not fsp_id:
        raise FspError("oidc_failed", "В токене ФСП ID нет идентификатора участника")
    return str(fsp_id).upper()


def fetch_registry(fsp_id: str) -> tuple[dict, list[dict]]:
    """Participant card and results. Falls back to the in-process mock when the registry service is down (dev)."""
    headers = {"Authorization": f"Bearer {registry_app.REGISTRY_TOKEN}"}
    try:
        p = httpx.get(f"{settings.fsp_registry_url}/api/v1/participants/{fsp_id}", headers=headers, timeout=5)
        if p.status_code == 404:
            raise FspError("fsp_not_found", "Участник с таким ФСП ID не найден в реестре")
        p.raise_for_status()
        r = httpx.get(f"{settings.fsp_registry_url}/api/v1/participants/{fsp_id}/results", headers=headers, timeout=5)
        r.raise_for_status()
        return p.json(), r.json()
    except httpx.HTTPError:
        part = registry_app.participant(fsp_id)
        if part is None:
            raise FspError("fsp_not_found", "Участник с таким ФСП ID не найден в реестре") from None
        return part.model_dump(mode="json"), [x.model_dump(mode="json") for x in registry_app.results(fsp_id)]
