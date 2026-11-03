import pytest
import requests

from ingest.http import Client, FetchError


class Resp:
    def __init__(self, status, headers=None, text="", ctype="application/json"):
        self.status_code, self.headers, self.text = status, {"content-type": ctype, **(headers or {})}, text


def make(monkeypatch, script, **kw):
    sleeps, calls = [], []
    c = Client(sleep=sleeps.append, **kw)
    it = iter(script)

    def fake(method, url, **k):
        calls.append((method, url))
        x = next(it)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(c.session, "request", fake)
    return c, sleeps, calls


def test_retries_5xx_with_backoff_then_succeeds(monkeypatch):
    c, sleeps, calls = make(monkeypatch, [Resp(503), Resp(502), Resp(200)], min_interval=0, retries=3, backoff=2.0)
    assert c.get("https://example.org/a").status_code == 200
    assert len(calls) == 3 and len(sleeps) == 2
    assert 1.0 <= sleeps[0] <= 1.5 and 2.0 <= sleeps[1] <= 2.5          # 2**0 and 2**1 plus < 0.5 s of jitter


def test_honours_retry_after_and_caps_it(monkeypatch):
    c, sleeps, _ = make(monkeypatch, [Resp(429, {"Retry-After": "7"}), Resp(429, {"Retry-After": "9999"}), Resp(200)], min_interval=0, retries=3)
    c.get("https://example.org/a")
    assert 7 in sleeps and 120 in sleeps and max(sleeps) <= 120


def test_does_not_retry_client_errors(monkeypatch):
    c, _, calls = make(monkeypatch, [Resp(404)], min_interval=0, retries=3)
    assert c.get("https://example.org/a").status_code == 404 and len(calls) == 1


def test_gives_up_after_retries_with_a_stable_error_kind(monkeypatch):
    c, _, calls = make(monkeypatch, [Resp(503)] * 3, min_interval=0, retries=2)
    with pytest.raises(FetchError) as e:
        c.get("https://example.org/a")
    assert e.value.kind == "http_503" and e.value.status == 503 and len(calls) == 3


def test_egress_block_is_not_retried(monkeypatch):
    c, _, calls = make(monkeypatch, [requests.exceptions.ProxyError("403 Forbidden")], min_interval=0, retries=3)
    with pytest.raises(FetchError) as e:
        c.get("https://blocked.example/")
    assert e.value.kind == "blocked_by_egress_policy" and len(calls) == 1


def test_timeouts_are_retried_then_reported(monkeypatch):
    c, _, calls = make(monkeypatch, [requests.exceptions.Timeout("t")] * 2, min_interval=0, retries=1)
    with pytest.raises(FetchError) as e:
        c.get("https://example.org/a")
    assert e.value.kind == "timeout" and len(calls) == 2


def test_minimum_interval_per_host(monkeypatch):
    sleeps = []
    c = Client(min_interval=5.0, sleep=sleeps.append)
    monkeypatch.setattr(c.session, "request", lambda m, u, **k: Resp(200))
    c.get("https://a.example/1")
    c.get("https://a.example/2")
    c.get("https://b.example/1")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 5.0                      # second call to the same host waited; a different host did not


def test_identifying_user_agent_without_personal_email():
    c = Client()
    ua = c.session.headers["User-Agent"]
    assert "MilitaryYellowBookIngest" in ua and "github.com" in ua and "@" not in ua


def test_robots_unreadable_means_not_permitted(monkeypatch):
    c, _, _ = make(monkeypatch, [Resp(500), Resp(500), Resp(500)], min_interval=0, retries=2)
    assert c.robots_allows("https://example.org/page") is None


def test_robots_rules_are_applied(monkeypatch):
    c, _, _ = make(monkeypatch, [Resp(200, text="User-agent: *\nDisallow: /private\n", ctype="text/plain")], min_interval=0)
    assert c.robots_allows("https://example.org/private/x") is False
    assert c.robots_allows("https://example.org/public") is True
