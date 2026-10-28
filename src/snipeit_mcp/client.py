"""A small Snipe-IT API client: the calls the tools and the seeder need, nothing more.

Snipe-IT answers most errors with HTTP 200 and {"status": "error", "messages": …}; `call` turns those into
SnipeITError so callers see one kind of failure.
"""

import os
import time
from typing import Any

import httpx


class SnipeITError(Exception):
    pass


class SnipeIT:
    def __init__(self, url: str | None = None, token: str | None = None, transport: httpx.BaseTransport | None = None):
        url = url or os.environ.get("SNIPEIT_URL", "http://127.0.0.1:8088")
        token = token or os.environ.get("SNIPEIT_TOKEN", "")
        if not token:
            raise SnipeITError("SNIPEIT_TOKEN is not set (scripts/up.sh writes it to .env)")
        self.http = httpx.Client(
            base_url=url.rstrip("/") + "/api/v1/",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
            transport=transport,
        )

    def call(self, method: str, path: str, **kw: Any) -> Any:
        for wait in (1, 2, 4, 8, 0):  # Snipe-IT rate-limits the API (120 a minute by default)
            r = self.http.request(method, path, **kw)
            if r.status_code != 429 or not wait:
                break
            time.sleep(wait)
        if r.status_code == 404:
            raise SnipeITError("not found")
        if r.status_code >= 400:
            raise SnipeITError(f"Snipe-IT answered {r.status_code}")
        body = r.json()
        if isinstance(body, dict) and body.get("status") == "error":
            raise SnipeITError(_messages(body.get("messages")))
        return body

    def get(self, path: str, **params: Any) -> Any:
        return self.call("GET", path, params=params)

    def post(self, path: str, data: dict) -> Any:
        return self.call("POST", path, json=data)

    def rows(self, path: str, **params: Any) -> list[dict]:
        """Every row of a list endpoint, page by page."""
        out: list[dict] = []
        while True:
            page = self.get(path, limit=500, offset=len(out), **params)
            rows = page.get("rows", [])
            out += rows
            if not rows or len(out) >= page.get("total", 0):
                return out


def _messages(m: Any) -> str:
    if isinstance(m, dict):
        return "; ".join(f"{k}: {' '.join(v) if isinstance(v, list) else v}" for k, v in m.items())
    return str(m)
