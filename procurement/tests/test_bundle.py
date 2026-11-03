import pytest

from ingest import bundle as B


def test_money_is_decimal_string_with_currency():
    assert B.money("1234.5", "eur") == {"amount": "1234.50", "currency": "EUR"}
    assert B.money(1000, "USD") == {"amount": "1000.00", "currency": "USD"}
    assert B.money("1,234,567.891", "GBP")["amount"] == "1234567.89"
    assert B.money(None, "USD") is None and B.money("", "USD") is None


@pytest.mark.parametrize("amount,cur,reason", [("abc", "USD", "bad_amount"), ("NaN", "USD", "bad_amount"), ("1e30", "USD", "bad_amount"),
                                               ("10", None, "bad_currency"), ("10", "US", "bad_currency"), ("10", "123", "bad_currency")])
def test_money_rejects_junk_instead_of_guessing(amount, cur, reason):
    with pytest.raises(B.Reject) as e:
        B.money(amount, cur)
    assert e.value.reason == reason


@pytest.mark.parametrize("raw,expected", [
    ("2026-10-31+01:00", "2026-10-31T00:00:00+01:00"), ("2026-10-31Z", "2026-10-31T00:00:00+00:00"), ("20261031", "2026-10-31T00:00:00+00:00"),
    ("01-Nov-2026", "2026-11-01T00:00:00+00:00"), ("2026-11-01", "2026-11-01T00:00:00+00:00"), ("2026-11-01T10:30:00", "2026-11-01T10:30:00+00:00"),
    ("2026-11-01T10:30:00Z", "2026-11-01T10:30:00+00:00"), ("2026-11-01T10:30:00.123-0300", "2026-11-01T10:30:00-03:00"), (None, None), ("", None)])
def test_to_ts_shapes(raw, expected):
    assert B.to_ts(raw) == expected


def test_to_ts_applies_the_caller_assumed_zone_only_when_the_source_gives_none():
    assert B.to_ts("2026-11-01T10:30:00", "-03:00") == "2026-11-01T10:30:00-03:00"
    assert B.to_ts("2026-11-01T10:30:00+02:00", "-03:00") == "2026-11-01T10:30:00+02:00"


def test_to_ts_rejects_garbage():
    with pytest.raises(B.Reject):
        B.to_ts("next tuesday")


def test_hash_is_stable_under_key_order_and_changes_with_content():
    assert B.sha256_hex({"a": 1, "b": [1, 2]}) == B.sha256_hex({"b": [1, 2], "a": 1})
    assert B.sha256_hex({"a": 1}) != B.sha256_hex({"a": 2})


def _rec(**over):
    p = {"ocid": "x-1", "ocid_native": False, "stage": "tender", "title": "t", "country": "GB"}
    return B.make_record(source_id="s", external_id="1", raw={"k": 1}, process={**p, **over}, fetched_at="2026-11-03T12:00:00+00:00")


def test_a_minimal_bundle_validates():
    b = {"run": {"run_id": "4f0e3a1e-8f9d-4d51-9a53-0d0f0f0f0f0f", "source_id": "s", "mode": "test"}, "records": [_rec()], "rejected": []}
    assert B.schema_errors(b) == []


@pytest.mark.parametrize("bad", [{"country": "gb"}, {"country": "GBR"}, {"stage": "bidding"}, {"value": {"amount": "12.345", "currency": "GBP"}},
                                 {"value": {"amount": "12.30", "currency": "gbp"}}, {"published_at": "2026-11-03"}, {"buyer": {"id": "1", "name": "x"}}])
def test_schema_catches_what_the_database_would_reject(bad):
    b = {"run": {"run_id": "4f0e3a1e-8f9d-4d51-9a53-0d0f0f0f0f0f", "source_id": "s", "mode": "test"}, "records": [_rec(**bad)], "rejected": []}
    assert B.schema_errors(b), bad


def test_make_record_requires_an_identifier():
    with pytest.raises(B.Reject):
        B.make_record(source_id="s", external_id="", raw={}, process={}, fetched_at="x")
