import base64
import os
import time
import uuid
from typing import Any

import httpx

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
TOKEN_TTL_SECONDS = 25 * 60

_token_cache: dict[str, tuple[str, float]] = {}


def gigachat_credentials_configured() -> bool:
    if os.getenv("GIGACHAT_AUTH_KEY", "").strip():
        return True
    return bool(
        os.getenv("GIGACHAT_CLIENT_ID", "").strip()
        and os.getenv("GIGACHAT_CLIENT_SECRET", "").strip()
    )


def missing_gigachat_env_keys() -> list[str]:
    if gigachat_credentials_configured():
        return []
    if not os.getenv("GIGACHAT_AUTH_KEY", "").strip():
        return ["GIGACHAT_AUTH_KEY"]
    return ["GIGACHAT_CLIENT_ID", "GIGACHAT_CLIENT_SECRET"]


def _authorization_basic_value() -> str:
    auth_key = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
    if auth_key:
        if auth_key.lower().startswith("basic "):
            return auth_key.split(" ", 1)[1].strip()
        return auth_key
    client_id = os.getenv("GIGACHAT_CLIENT_ID", "").strip()
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError("GigaChat credentials are not configured")
    return base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


def fetch_access_token(*, timeout: float = 30.0) -> str:
    basic = _authorization_basic_value()
    now = time.time()
    cached = _token_cache.get(basic)
    if cached and cached[1] > now:
        return cached[0]

    scope = os.getenv("GIGACHAT_SCOPE", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {basic}",
    }
    with httpx.Client(verify=False, timeout=timeout) as client:
        response = client.post(OAUTH_URL, headers=headers, data={"scope": scope})
    if response.status_code >= 400:
        raise ValueError(f"GigaChat OAuth failed with status {response.status_code}")
    data: dict[str, Any] = response.json()
    token = data.get("access_token")
    if not token:
        raise ValueError("GigaChat OAuth response did not include access_token")
    _token_cache[basic] = (token, now + TOKEN_TTL_SECONDS)
    return token
