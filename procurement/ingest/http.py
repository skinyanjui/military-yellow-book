"""Polite HTTP client: identifying User-Agent, minimum interval per host, timeouts, exponential back-off
with jitter, Retry-After handling and robots.txt lookups. Every connector goes through this."""
import random
import threading
import time
import urllib.parse
import urllib.robotparser

import requests

from . import USER_AGENT

RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A request that could not be completed after retries. `kind` is a stable label for monitoring."""

    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class Client:
    def __init__(self, min_interval=1.0, timeout=45, retries=4, backoff=2.0, user_agent=USER_AGENT, sleep=time.sleep):
        self.min_interval, self.timeout, self.retries, self.backoff = min_interval, timeout, retries, backoff
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last = {}
        self._lock = threading.Lock()
        self._robots = {}
        self._sleep = sleep

    def _wait(self, host):
        with self._lock:
            now = time.monotonic()
            due = self._last.get(host, 0) + self.min_interval
            self._last[host] = max(now, due)
        if due > now:
            self._sleep(due - now)

    def request(self, method, url, **kw):
        host = urllib.parse.urlsplit(url).netloc
        kw.setdefault("timeout", self.timeout)
        last = None
        for attempt in range(self.retries + 1):
            self._wait(host)
            try:
                r = self.session.request(method, url, **kw)
            except requests.exceptions.ProxyError as e:
                # the egress policy refused the tunnel: retrying does not help
                raise FetchError("blocked_by_egress_policy", str(e)[:300])
            except requests.exceptions.SSLError as e:
                raise FetchError("tls_error", str(e)[:300])
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last = FetchError("timeout" if isinstance(e, requests.exceptions.Timeout) else "connection_error", str(e)[:300])
            else:
                if r.status_code not in RETRY_STATUS:
                    return r
                last = FetchError("http_%d" % r.status_code, "HTTP %d from %s" % (r.status_code, host), r.status_code)
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    self._sleep(min(int(ra), 120))
            if attempt < self.retries:
                self._sleep(self.backoff ** attempt + random.uniform(0, 0.5))
        raise last

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def robots_allows(self, url):
        """True/False from the host's robots.txt, or None when it could not be read (treat None as 'not permitted' for HTML collection)."""
        p = urllib.parse.urlsplit(url)
        base = "%s://%s" % (p.scheme, p.netloc)
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.get(base + "/robots.txt", timeout=20)
                if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower():
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
                elif r.status_code in (404, 410):
                    rp.parse([])
                    self._robots[base] = rp
                else:
                    self._robots[base] = None
            except FetchError:
                self._robots[base] = None
        rp = self._robots[base]
        return None if rp is None else rp.can_fetch(self.session.headers["User-Agent"], url)
