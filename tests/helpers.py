"""Shared test helpers: a fake transport and fixture loading."""

from __future__ import annotations

import json
from pathlib import Path

from tide_client.client import TideClient
from tide_client.transport import Transport

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeTransport(Transport):
    """Transport that answers from a URL-pattern -> body mapping.

    Patterns are substrings matched against the request URL. Values are
    either a string (returned by get_text), a dict (returned by
    get_json / post_form), or bytes (returned by get_bytes).
    """

    def __init__(self, mapping: dict[str, str | dict | bytes]) -> None:
        super().__init__(cache_dir=None)
        self.mapping = mapping
        self.calls: list[tuple[str, str]] = []

    def _match(self, url: str) -> str | dict | bytes:
        for pattern, body in self.mapping.items():
            if pattern in url:
                return body
        raise AssertionError(f"no fixture for URL: {url}")

    def _key(self, url: str, params: dict | None) -> str:
        if not params:
            return url
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{url}?{query}"

    def get_text(self, url: str, params: dict | None = None) -> str:
        self.calls.append(("GET", url))
        body = self._match(self._key(url, params))
        if isinstance(body, bytes):
            return body.decode("utf-8")
        if isinstance(body, dict):
            return json.dumps(body)
        return body

    def get_bytes(self, url: str, params: dict | None = None) -> bytes:
        self.calls.append(("GET", url))
        body = self._match(self._key(url, params))
        if isinstance(body, bytes):
            return body
        if isinstance(body, dict):
            return json.dumps(body).encode("utf-8")
        return body.encode("utf-8")

    def get_json(self, url: str, params: dict | None = None) -> dict:
        self.calls.append(("GET", url))
        body = self._match(self._key(url, params))
        if isinstance(body, dict):
            return body
        if isinstance(body, (str, bytes)):
            return json.loads(body)
        raise AssertionError(f"fixture for {url} is not JSON")

    def post_form(self, url: str, data: dict) -> dict:
        self.calls.append(("POST", url))
        body = self._match(url)
        if isinstance(body, dict):
            return body
        return json.loads(body)


def client_with(mapping: dict[str, str | dict | bytes]) -> TideClient:
    """Build a TideClient whose transport answers from the mapping."""
    return TideClient(transport=FakeTransport(mapping))
