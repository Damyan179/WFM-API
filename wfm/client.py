"""One HTTP client for every warframe.market call.

- Chrome-impersonating session (plain `requests` gets Cloudflare-challenged)
- global rate limit, shared by all threads
- timeouts on every request
- retry with backoff on HTTP 429 / 5xx
- every failure surfaces as WfmError with a readable message
"""
import threading
import time

from curl_cffi import requests as cffi_requests

API_V1 = "https://api.warframe.market/v1"
API_V2 = "https://api.warframe.market/v2"

TIMEOUT = 15            # seconds, per request
MIN_INTERVAL = 0.35     # seconds between request starts (just under 3 requests/second)
MAX_RETRIES = 3

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Language": "en",
    "Platform": "pc",
}


class WfmError(Exception):
    """Any failed call to warframe.market. `status` is the HTTP status, or None for network errors."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


_lock = threading.Lock()   # serialises requests: enforces the rate limit and keeps the session single-threaded
_last_request = 0.0
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = cffi_requests.Session(impersonate="chrome", headers=BROWSER_HEADERS)
    return _session


def _send(method, url, headers, json):
    """Single rate-limited HTTP call. Returns the raw response object."""
    global _last_request
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            return _get_session().request(method, url, headers=headers, json=json, timeout=TIMEOUT)
        except Exception as exc:  # curl_cffi raises several unrelated exception types
            raise WfmError(f"Network error: {exc}") from exc
        finally:
            _last_request = time.monotonic()


def request(method, url, token=None, json=None, extra_headers=None, raw=False):
    """Call the API and return the decoded JSON body (or the raw response when raw=True)."""
    headers = dict(BROWSER_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    # A POST may already have been processed when the connection fails or the server answers 5xx,
    # so repeating it could create a duplicate (e.g. two identical orders). Only 429 is safe to retry.
    repeatable = method.upper() != "POST"

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = _send(method, url, headers, json)
        except WfmError as exc:
            if attempt == MAX_RETRIES or not repeatable:
                if not repeatable:
                    raise WfmError(f"{exc} The request may or may not have gone through: "
                                   "check your orders before trying again.") from exc
                raise
            time.sleep(1.5 * (attempt + 1))
            continue

        status = response.status_code
        if status >= 500 and not repeatable:
            raise WfmError(f"warframe.market answered HTTP {status}. The request may or may not have gone "
                           "through: check your orders before trying again.", status)
        if status == 429 or status >= 500:
            if attempt == MAX_RETRIES:
                raise WfmError(f"warframe.market keeps answering HTTP {status}. Try again later.", status)
            try:
                delay = float(response.headers.get("Retry-After", ""))
            except (TypeError, ValueError):
                delay = 1.5 * (attempt + 1)
            time.sleep(min(delay, 10))
            continue

        if "text/html" in response.headers.get("content-type", ""):
            raise WfmError(f"Blocked by a Cloudflare challenge (HTTP {status}). Retry later.", status)
        if status >= 400:
            raise WfmError(f"HTTP {status}: {response.text[:300]}", status)
        if raw:
            return response
        if not response.text.strip():      # e.g. 204 No Content after a delete
            return {}
        try:
            return response.json()
        except Exception as exc:
            raise WfmError("warframe.market returned a response that is not JSON.", status) from exc

    raise WfmError("Request failed.")  # not reachable; keeps linters quiet


def get(url, token=None):
    return request("GET", url, token=token)


def patch(url, token, json):
    return request("PATCH", url, token=token, json=json)


def delete(url, token):
    return request("DELETE", url, token=token)
