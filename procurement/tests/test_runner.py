"""The runner with fake connectors: cursors, partial failures, rejects, credentials, schema failures, and resuming without duplicates."""
import datetime

import pytest

from conftest import NOW, NoNetwork
from ingest import bundle as B
from ingest import runner
from ingest.connectors import gated
from ingest.connectors.base import Connector, MissingCredential
from ingest.http import FetchError


def rec(i, updated="2026-11-01T00:00:00+00:00", **proc):
    p = {"ocid": "myb-fake-%s" % i, "ocid_native": False, "stage": "tender", "title": "t%s" % i, "country": "GB", **proc}
    return B.make_record(source_id="fake", external_id=str(i), raw={"id": i, "u": updated}, process=p, fetched_at=NOW, source_updated_at=updated, published_at=updated)


class Fake(Connector):
    source_id = "fake"
    expected_fields = frozenset({"id", "u"})

    def __init__(self, rows, fail_after=None, **kw):
        super().__init__(NoNetwork(), **kw)
        self.rows, self.fail_after, self.calls = rows, fail_after, []

    def fetch(self, *, limit, since, until):
        self.calls.append((since, until, limit))
        for i, r in enumerate(self.rows):
            if self.fail_after is not None and i >= self.fail_after:
                raise FetchError("http_503", "upstream down", 503)
            if i >= limit:
                return
            self.observe(r)
            yield r

    def normalize(self, raw, fetched_at):
        if raw.get("bad"):
            raise B.Reject("bad_amount", {"amount": "x"})
        if raw.get("boom"):
            raise KeyError("missing")
        return rec(raw["id"], raw["u"])


def run(conn, **kw):
    return runner.run_connector(conn, mode=kw.pop("mode", "test"), limit=kw.pop("limit", 10), **kw)


def test_success_bundle_validates_and_sets_cursor_to_newest_record():
    b = run(Fake([{"id": 1, "u": "2026-11-01T00:00:00+00:00"}, {"id": 2, "u": "2026-11-02T08:00:00+00:00"}]))
    assert b["run"]["status"] == "success" and len(b["records"]) == 2 and b["run"]["cursor_after"] == {"high_water": "2026-11-02T08:00:00"}
    assert B.schema_errors(b) == [] and b["run"]["drift"] == {"missing": [], "unexpected": []}


def test_bad_records_are_rejected_with_reasons_not_dropped_silently():
    b = run(Fake([{"id": 1, "u": "2026-11-01T00:00:00+00:00"}, {"id": 2, "u": "x", "bad": 1}, {"id": 3, "u": "x", "boom": 1}]))
    assert len(b["records"]) == 1 and len(b["rejected"]) == 2
    assert {r["reason"] for r in b["rejected"]} == {"bad_amount", "normalize_error:KeyError"}
    assert b["run"]["status"] == "success" and b["run"]["fetched"] == 3


def test_all_records_rejected_is_a_failed_run():
    b = run(Fake([{"id": 1, "u": "x", "bad": 1}]))
    assert b["run"]["status"] == "failed" and not b["records"]


def test_upstream_failure_midway_keeps_what_arrived_and_is_partial():
    b = run(Fake([{"id": i, "u": "2026-11-01T00:00:00+00:00"} for i in range(5)], fail_after=3))
    assert b["run"]["status"] == "partial" and len(b["records"]) == 3 and b["run"]["error_kind"] == "http_503" and "cursor_after" in b["run"]


def test_upstream_failure_before_any_record_is_failed_and_has_no_cursor():
    b = run(Fake([{"id": 1, "u": "x"}], fail_after=0))
    assert b["run"]["status"] == "failed" and "cursor_after" not in b["run"]


def test_incremental_run_resumes_from_checkpoint_minus_overlap():
    conn = Fake([])
    until = datetime.datetime(2026, 11, 3, 12, 0, 0)
    run(conn, mode="incremental", cursor={"high_water": "2026-11-02T08:00:00"}, until=until)
    since = conn.calls[0][0]
    assert since == datetime.datetime(2026, 11, 1, 8, 0, 0)                  # one-day overlap so late updates are not missed


def test_without_a_cursor_the_window_is_the_configured_number_of_days():
    conn = Fake([], days=3)
    until = datetime.datetime(2026, 11, 3, 12, 0, 0)
    run(conn, until=until)
    assert conn.calls[0][0] == until - datetime.timedelta(days=3)


def test_backfill_window_is_explicit_and_not_overridden():
    conn = Fake([])
    run(conn, mode="backfill", since=datetime.datetime(2020, 1, 1), until=datetime.datetime(2020, 2, 1))
    assert conn.calls[0][:2] == (datetime.datetime(2020, 1, 1), datetime.datetime(2020, 2, 1))


def test_rerunning_the_same_window_yields_the_same_hashes_so_the_database_sees_no_change():
    rows = [{"id": i, "u": "2026-11-01T00:00:00+00:00"} for i in range(3)]
    a, b = run(Fake(rows)), run(Fake(rows))
    assert [r["content_hash"] for r in a["records"]] == [r["content_hash"] for r in b["records"]]
    assert a["run"]["run_id"] != b["run"]["run_id"]                          # a new run id each time; the content hash is what makes the write idempotent


def test_drift_is_reported_when_fields_appear_or_vanish():
    b = run(Fake([{"id": 1, "u": "2026-11-01T00:00:00+00:00", "new_field": 1}]))
    assert b["run"]["drift"] == {"missing": [], "unexpected": ["new_field"]}


def test_schema_invalid_output_is_never_sent_on():
    class Broken(Fake):
        def normalize(self, raw, fetched_at):
            r = rec(raw["id"])
            r["process"]["country"] = "gb"
            return r
    b = run(Broken([{"id": 1, "u": "x"}]))
    assert b["run"]["status"] == "failed" and b["run"]["error_kind"] == "bundle_schema" and b["records"] == []


@pytest.mark.parametrize("cls", [gated.SamOpportunities, gated.ChileLicitaciones, gated.ChileOrdenes])
def test_credential_gated_sources_fail_closed_without_touching_the_network(cls, monkeypatch):
    for k in ("SAM_GOV_API_KEY", "CHILECOMPRA_TICKET"):
        monkeypatch.delenv(k, raising=False)
    b = run(cls(NoNetwork()))                                              # NoNetwork raises if the connector uses the client at all
    assert b["run"]["status"] == "failed" and b["run"]["error_kind"] == "missing_credential" and b["records"] == []


def test_a_present_credential_still_does_not_pretend_to_work(monkeypatch):
    monkeypatch.setenv("SAM_GOV_API_KEY", "x")
    b = run(gated.SamOpportunities(NoNetwork()))
    assert b["run"]["status"] == "failed" and b["run"]["error_kind"] == "not_implemented" and b["records"] == []


def test_every_registered_connector_has_a_distinct_source_id():
    ids = [c.source_id for c in runner.CONNECTORS.values()]
    assert len(ids) == len(set(ids)) and "sam_opportunities" in ids and "ted" in ids


def test_unknown_source_is_refused_not_guessed():
    with pytest.raises(SystemExit):
        runner.build_connector("nonexistent_source", NoNetwork())
