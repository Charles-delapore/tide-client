"""HTTP transport: one session, retries, optional local file cache.

The cache is opt-in (``TideClient(cache_dir=...)``) and stores raw response
bodies keyed by the request URL. It never ships data and never redistributes
upstream files; it only avoids re-downloading a file the user already fetched.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from tide_client.exceptions import (
    TideAuthError,
    TideNotFoundError,
    TideRateLimitError,
    TideServerError,
)

USER_AGENT = "tide-client/0.1.0 (https://github.com/Charles-delapore/tide-client)"


class Transport:
    """Thin wrapper over requests with retry and optional disk cache."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / digest

    def _read_cache(self, key: str) -> bytes | None:
        path = self._cache_path(key)
        if path is not None and path.exists():
            return path.read_bytes()
        return None

    def _write_cache(self, key: str, body: bytes) -> None:
        path = self._cache_path(key)
        if path is not None:
            path.write_bytes(body)

    def _raise_for_status(self, response: requests.Response, url: str) -> None:
        status = response.status_code
        if status == 404:
            raise TideNotFoundError(f"not found at source: {url}")
        if status == 429:
            raise TideRateLimitError(f"rate limited by source: {url}")
        if status in (401, 403):
            raise TideAuthError(f"authentication required by source: {url}")
        if status >= 500:
            raise TideServerError(f"source returned HTTP {status}: {url}")
        if status >= 400:
            raise TideServerError(f"source returned HTTP {status}: {url}")

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise TideServerError(f"request failed: {url}: {exc}") from exc
            if response.status_code == 429 and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else 2**attempt
                time.sleep(min(wait, 60.0))
                continue
            if response.status_code >= 500 and attempt < self.max_retries:
                time.sleep(2**attempt)
                continue
            self._raise_for_status(response, url)
            return response
        raise TideServerError(f"request failed after retries: {url}: {last_exc}")

    def get_text(self, url: str, params: dict | None = None) -> str:
        key = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        cached = self._read_cache(key)
        if cached is not None:
            return cached.decode("utf-8", errors="replace")
        response = self._request_with_retry("GET", url, params=params)
        body = response.content
        self._write_cache(key, body)
        return body.decode("utf-8", errors="replace")

    def get_bytes(self, url: str, params: dict | None = None) -> bytes:
        key = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        cached = self._read_cache(key)
        if cached is not None:
            return cached
        response = self._request_with_retry("GET", url, params=params)
        self._write_cache(key, response.content)
        return response.content

    def get_json(self, url: str, params: dict | None = None) -> dict:
        response = self._request_with_retry("GET", url, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise TideServerError(f"source returned non-JSON: {url}") from exc

    def post_form(self, url: str, data: dict) -> dict:
        response = self._request_with_retry("POST", url, data=data)
        try:
            return response.json()
        except ValueError as exc:
            raise TideServerError(f"source returned non-JSON: {url}") from exc
