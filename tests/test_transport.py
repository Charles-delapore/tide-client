"""Tests for the HTTP transport: retries, errors, caching."""

import json
import tempfile
import unittest
from pathlib import Path

from tide_client.exceptions import TideNotFoundError, TideRateLimitError, TideServerError
from tide_client.transport import Transport


class FakeResponse:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.headers = headers or {}

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.headers = {}

    def request(self, method, url, timeout=None, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class TestTransportRetries(unittest.TestCase):
    def test_429_then_success(self):
        session = FakeSession(
            [
                FakeResponse(429, b"", {"Retry-After": "0"}),
                FakeResponse(200, b"ok"),
            ]
        )
        transport = Transport(session=session, max_retries=2)
        self.assertEqual(transport.get_text("https://example.org/x"), "ok")
        self.assertEqual(session.calls, 2)

    def test_429_exhausted(self):
        session = FakeSession([FakeResponse(429, b"") for _ in range(3)])
        transport = Transport(session=session, max_retries=1)
        with self.assertRaises(TideRateLimitError):
            transport.get_text("https://example.org/x")

    def test_500_then_success(self):
        session = FakeSession([FakeResponse(500, b""), FakeResponse(200, b"ok")])
        transport = Transport(session=session, max_retries=1)
        self.assertEqual(transport.get_text("https://example.org/x"), "ok")
        self.assertEqual(session.calls, 2)

    def test_404(self):
        session = FakeSession([FakeResponse(404, b"")])
        transport = Transport(session=session)
        with self.assertRaises(TideNotFoundError):
            transport.get_text("https://example.org/x")

    def test_non_json(self):
        session = FakeSession([FakeResponse(200, b"not json")])
        transport = Transport(session=session)
        with self.assertRaises(TideServerError):
            transport.get_json("https://example.org/x")


class TestTransportCache(unittest.TestCase):
    def test_second_call_uses_cache(self):
        session = FakeSession([FakeResponse(200, b"cached-body")])
        with tempfile.TemporaryDirectory() as tmp:
            transport = Transport(session=session, cache_dir=tmp)
            first = transport.get_text("https://example.org/x")
            second = transport.get_text("https://example.org/x")
            self.assertEqual(first, "cached-body")
            self.assertEqual(second, "cached-body")
            self.assertEqual(session.calls, 1)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_cache_key_includes_params(self):
        session = FakeSession([FakeResponse(200, b"a"), FakeResponse(200, b"b")])
        with tempfile.TemporaryDirectory() as tmp:
            transport = Transport(session=session, cache_dir=tmp)
            self.assertEqual(transport.get_text("https://example.org/x", {"p": "1"}), "a")
            self.assertEqual(transport.get_text("https://example.org/x", {"p": "2"}), "b")
            self.assertEqual(session.calls, 2)


if __name__ == "__main__":
    unittest.main()
