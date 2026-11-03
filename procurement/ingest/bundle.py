"""Bundle format shared by every connector, plus the small deterministic helpers (hashing, money, dates, names).

A bundle is what procurement.ingest_bundle(jsonb) accepts:
  {"run": {...}, "records": [record...], "rejected": [{external_id, reason, detail, excerpt}...]}
A record is one publisher record (one notice, award, contract...) with its provenance and OCDS-shaped parts.
Money is carried as a decimal string with an ISO 4217 currency; nothing is converted between currencies."""
import datetime
import hashlib
import json
import re
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation

import jsonschema

from . import TRANSFORM_VERSION

STAGES = ("planning", "tender", "award", "contract", "unknown")


class Reject(Exception):
    """A record that cannot be normalised. It is kept, with the reason, in procurement.rejected_record."""

    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason, self.detail = reason, detail or {}


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(o):
    return hashlib.sha256(canon(o).encode("utf-8")).hexdigest()


def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def money(amount, currency):
    """-> {"amount": "1234.50", "currency": "EUR"} or None when there is no amount. Raises Reject on junk."""
    if amount is None or amount == "":
        return None
    try:
        d = Decimal(str(amount).replace(",", "") if isinstance(amount, str) else str(amount))
    except InvalidOperation:
        raise Reject("bad_amount", {"amount": str(amount)[:40]})
    if not d.is_finite() or abs(d) >= Decimal("1e18"):
        raise Reject("bad_amount", {"amount": str(amount)[:40]})
    cur = (currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", cur):
        raise Reject("bad_currency", {"currency": str(currency)[:20]})
    return {"amount": str(d.quantize(Decimal("0.01"))), "currency": cur}


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def to_ts(v, assume_tz="+00:00"):
    """Parse the date shapes the sources use into ISO 8601 with an offset. None for empty. Raises Reject if non-empty and unparseable.
    A value without a zone gets `assume_tz`; callers record that assumption in validation_notes."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})([+-]\d{2}:\d{2}|Z)", s)                          # TED: date plus zone
    if m:
        return "%s-%s-%sT00:00:00%s" % (m[1], m[2], m[3], "+00:00" if m[4] == "Z" else m[4])
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        return "%s-%s-%sT00:00:00%s" % (m[1], m[2], m[3], assume_tz)
    m = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", s)                                       # World Bank: 01-Nov-2026
    if m and m[2].lower() in _MONTHS:
        return "%s-%02d-%02dT00:00:00%s" % (m[3], _MONTHS[m[2].lower()], int(m[1]), assume_tz)
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return "%sT00:00:00%s" % (m[1], assume_tz)
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?", s)
    if m:
        z = m[4] or assume_tz
        if z == "Z":
            z = "+00:00"
        elif re.fullmatch(r"[+-]\d{4}", z):
            z = z[:3] + ":" + z[3:]
        return "%sT%s%s" % (m[1], m[2], z)
    raise Reject("bad_date", {"value": s[:40]})


def party(name, ident=None, scheme=None, country=None):
    name = (name or "").strip()
    if not name:
        return None
    p = {"name": name}
    if ident:
        p["id"], p["scheme"] = str(ident), scheme or "unknown"
    if country:
        p["country"] = country
    return p


def classification(scheme, code, description=None):
    return {k: v for k, v in (("scheme", scheme), ("id", str(code)), ("description", description)) if v}


def make_record(*, source_id, external_id, raw, process, fetched_at, source_url=None, publisher=None, published_at=None,
                source_updated_at=None, language=None, licence=None, awards=None, contracts=None, validation_notes=None, raw_stored=True):
    if not external_id:
        raise Reject("missing_external_id")
    rec = {
        "external_id": str(external_id), "content_hash": sha256_hex(raw), "fetched_at": fetched_at, "source_url": source_url,
        "publisher": publisher, "published_at": published_at, "source_updated_at": source_updated_at, "language": language,
        "licence": licence, "transform_version": TRANSFORM_VERSION, "raw": raw, "raw_stored": raw_stored, "process": process,
        "awards": awards or [], "contracts": contracts or [],
    }
    if validation_notes:
        rec["validation_status"], rec["validation_notes"] = "warnings", validation_notes
    return {k: v for k, v in rec.items() if v is not None}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def new_run(source_id, mode, params=None, cursor_before=None):
    return {"run_id": str(uuid.uuid4()), "source_id": source_id, "mode": mode, "started_at": now_iso(), "params": params or {},
            "cursor_before": cursor_before, "transform_version": TRANSFORM_VERSION}


# ---- JSON Schema for the bundle (validated before anything is sent to the database) ----
_money = {"type": ["object", "null"], "properties": {"amount": {"type": "string", "pattern": r"^-?\d+(\.\d{2})?$"}, "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}},
          "required": ["amount", "currency"], "additionalProperties": False}
_party = {"type": ["object", "null"], "properties": {"name": {"type": "string", "minLength": 1}, "id": {"type": "string"}, "scheme": {"type": "string"}, "country": {"type": "string"}},
          "required": ["name"], "dependentRequired": {"id": ["scheme"]}}
_ts = {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"}
BUNDLE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object", "required": ["run", "records"],
    "properties": {
        "run": {"type": "object", "required": ["run_id", "source_id", "mode"], "properties": {
            "run_id": {"type": "string", "format": "uuid"}, "source_id": {"type": "string", "pattern": "^[a-z0-9_]+$"},
            "mode": {"enum": ["test", "incremental", "backfill", "catalog"]}, "status": {"enum": ["success", "partial", "failed"]}}},
        "records": {"type": "array", "items": {
            "type": "object", "required": ["external_id", "content_hash", "fetched_at", "raw", "process"],
            "properties": {
                "external_id": {"type": "string", "minLength": 1}, "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "fetched_at": _ts, "published_at": _ts, "source_updated_at": _ts,
                "process": {"type": "object", "required": ["ocid", "ocid_native", "stage"], "properties": {
                    "ocid": {"type": "string", "minLength": 1}, "ocid_native": {"type": "boolean"}, "stage": {"enum": list(STAGES)},
                    "title": {"type": ["string", "null"]}, "country": {"type": ["string", "null"], "pattern": "^[A-Z]{2}$"},
                    "buyer": _party, "value": _money, "published_at": _ts, "updated_at": _ts, "tender_start": _ts, "tender_end": _ts,
                    "classifications": {"type": "array", "items": {"type": "object", "required": ["scheme", "id"]}}}},
                "awards": {"type": "array", "items": {"type": "object", "required": ["award_id"], "properties": {
                    "award_id": {"type": "string", "minLength": 1}, "value": _money, "obligated": _money, "date": _ts,
                    "suppliers": {"type": "array", "items": _party}}}},
                "contracts": {"type": "array", "items": {"type": "object", "required": ["contract_id"], "properties": {
                    "contract_id": {"type": "string", "minLength": 1}, "value": _money, "paid": _money,
                    "date_signed": _ts, "period_start": _ts, "period_end": _ts}}}}}},
        "rejected": {"type": "array", "items": {"type": "object", "required": ["reason"]}},
    },
}
_validator = jsonschema.Draft202012Validator(BUNDLE_SCHEMA)


def schema_errors(bundle):
    return ["/".join(str(p) for p in e.absolute_path) + ": " + e.message[:160] for e in _validator.iter_errors(bundle)]
