"""Sign-in and secret storage. Email, password, device id and session token all live in
Windows Credential Manager (via keyring); nothing secret is written to the project folder."""
import os
import secrets
from pathlib import Path

import keyring

from . import client

SERVICE = "wfm-api"   # Windows Credential Manager entry name
LEGACY_TOKEN_FILE = Path(__file__).resolve().parent.parent / ".wfm_token"


class NotSignedIn(Exception):
    """No stored credentials: the user has to sign in first."""


def _get(key):
    try:
        return keyring.get_password(SERVICE, key)
    except Exception:
        return None


def _set(key, value):
    keyring.set_password(SERVICE, key, value)


def _delete(key):
    try:
        keyring.delete_password(SERVICE, key)
    except Exception:
        pass


def save_credentials(email, password):
    _set("email", email)
    _set("password", password)


def get_credentials():
    return _get("email"), _get("password")


def has_credentials():
    email, password = get_credentials()
    return bool(email and password)


def stored_email():
    return _get("email")


def device_id():
    """One random device id, generated once and reused, instead of a new one per login."""
    value = os.environ.get("WFM_DEVICE_ID") or _get("device_id")
    if not value:
        value = secrets.token_hex(16)
        _set("device_id", value)
    return value


def login(email, password):
    """Sign in and return the session token. Raises client.WfmError on failure."""
    if not email or not password:
        raise ValueError("Email and password are required.")
    payload = {
        "auth_type": "header",
        "email": email,
        "password": password,
        "device_id": device_id(),
    }
    try:
        response = client.request(
            "POST", f"{client.API_V1}/auth/signin",
            json=payload, extra_headers={"Authorization": "JWT"}, raw=True,
        )
    except client.WfmError as exc:
        if exc.status in (400, 401, 403) and "Cloudflare" not in str(exc):
            raise client.WfmError("Sign-in rejected: check the email and password.", exc.status) from exc
        raise
    header = response.headers.get("Authorization") or ""
    if not header.startswith("JWT "):
        raise client.WfmError("Sign-in succeeded but no session token was returned.")
    return header[4:]


def token_is_valid(token):
    """True/False for a definite answer; raises WfmError when the network is the problem,
    so a connection blip does not trigger a password login."""
    try:
        client.get(f"{client.API_V2}/me", token=token)
        return True
    except client.WfmError as exc:
        if exc.status in (401, 403):
            return False
        raise


def _migrate_legacy_token():
    """Move the old plaintext .wfm_token file into Credential Manager, then remove the file."""
    if not LEGACY_TOKEN_FILE.exists():
        return
    try:
        token = LEGACY_TOKEN_FILE.read_text().strip()
        if token and not _get("token"):
            _set("token", token)
        LEGACY_TOKEN_FILE.unlink()
    except Exception:
        pass


def get_token():
    """Environment override -> cached token -> fresh login with stored credentials."""
    env_token = os.environ.get("WFM_JWT", "").strip()
    if env_token.startswith("JWT "):
        env_token = env_token[4:]
    if env_token and token_is_valid(env_token):
        return env_token

    _migrate_legacy_token()
    cached = _get("token")
    if cached and token_is_valid(cached):
        return cached

    email, password = get_credentials()
    if not email or not password:
        raise NotSignedIn("No stored credentials. Sign in first.")
    token = login(email, password)
    _set("token", token)
    return token


def sign_in(email, password):
    """Verify the credentials by logging in, and only then store them."""
    token = login(email.strip(), password)
    save_credentials(email.strip(), password)
    _set("token", token)
    return token


def sign_out():
    for key in ("email", "password", "token"):
        _delete(key)


def profile(token):
    """Signed-in user's profile data."""
    data = client.get(f"{client.API_V2}/me", token=token)
    return data.get("data", data) if isinstance(data, dict) else {}


def my_orders(token):
    try:
        return client.get(f"{client.API_V2}/orders/my", token=token)["data"]
    except (KeyError, TypeError) as exc:
        raise client.WfmError("Unexpected order format from warframe.market.") from exc
