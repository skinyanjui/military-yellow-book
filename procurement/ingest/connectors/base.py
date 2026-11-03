import datetime

from ..http import FetchError


class MissingCredential(Exception):
    pass


class Connector:
    source_id = None
    expected_fields = frozenset()      # keys a raw record is expected to carry; anything else, or a missing key, is reported as drift
    ignorable_fields = frozenset()
    report_unexpected = True           # wide open-data tables (Socrata) omit null columns, so unexpected-field drift is only meaningful elsewhere
    credential_env = None              # name of the environment variable holding a key/ticket, if the source needs one
    overlap = datetime.timedelta(days=1)

    def __init__(self, client, **opts):
        self.client, self.opts = client, opts
        self.seen = set()
        self.publisher = None
        self.licence = None

    def check_credentials(self):
        import os
        if self.credential_env and not os.environ.get(self.credential_env):
            raise MissingCredential("%s needs a credential in $%s; none is configured" % (self.source_id, self.credential_env))

    def observe(self, raw):
        if isinstance(raw, dict):
            self.seen |= set(raw)

    def drift(self):
        if not self.expected_fields:
            return None
        return {"missing": sorted(self.expected_fields - self.seen),
                "unexpected": sorted(self.seen - self.expected_fields - self.ignorable_fields) if self.report_unexpected else []}

    # subclasses implement:
    def fetch(self, *, limit, since, until):
        raise NotImplementedError

    def normalize(self, raw, fetched_at):
        raise NotImplementedError

    def get_json(self, url, **kw):
        r = self.client.get(url, headers={"Accept": "application/json"}, **kw)
        if r.status_code >= 400:
            raise FetchError("http_%d" % r.status_code, "%s -> HTTP %d: %s" % (url.split("?")[0], r.status_code, r.text[:160].replace("\n", " ")), r.status_code)
        try:
            return r.json()
        except ValueError:
            raise FetchError("not_json", "%s did not return JSON (content-type %s)" % (url.split("?")[0], r.headers.get("content-type")))

    def post_json(self, url, body, **kw):
        r = self.client.post(url, json=body, headers={"Accept": "application/json"}, **kw)
        if r.status_code >= 400:
            raise FetchError("http_%d" % r.status_code, "%s -> HTTP %d: %s" % (url.split("?")[0], r.status_code, r.text[:200].replace("\n", " ")), r.status_code)
        try:
            return r.json()
        except ValueError:
            raise FetchError("not_json", "%s did not return JSON" % url.split("?")[0])
