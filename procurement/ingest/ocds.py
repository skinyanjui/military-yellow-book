"""OCDS release / compiled release -> procurement record. Used by every source that publishes OCDS
(UK Find a Tender, UK Contracts Finder, the OCP Data Registry datasets)."""
from .bundle import Reject, classification, make_record, money, party, to_ts


def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def stage_of(release):
    tags = set(release.get("tag") or [])
    if release.get("contracts") or "contract" in tags or "contractUpdate" in tags:
        return "contract"
    if release.get("awards") or "award" in tags:
        return "award"
    if release.get("tender") or "tender" in tags:
        return "tender"
    if release.get("planning") or "planning" in tags:
        return "planning"
    return "unknown"


def _party_index(release):
    idx = {}
    for p in release.get("parties") or []:
        if p.get("id") is not None:
            idx[str(p["id"])] = p
    return idx


def _ident(p):
    i = (p or {}).get("identifier") or {}
    return (i.get("scheme"), i.get("id")) if i.get("id") else (None, None)


def _org(ref, parties, country=None):
    """Resolve an OCDS organisation reference (id + name) against the parties array."""
    if not ref:
        return None
    full = parties.get(str(ref.get("id"))) if ref.get("id") is not None else None
    name = _first((full or {}).get("name"), ref.get("name"))
    scheme, ident = _ident(full)
    if not ident and ref.get("id") is not None and (full is None):
        scheme, ident = "OCDS-ref", str(ref["id"])
    c = (((full or {}).get("address") or {}).get("countryName"))
    return party(name, ident, scheme, country)


def release_to_record(release, *, source_id, fetched_at, publisher=None, licence=None, source_url=None, country=None, ocid_native=True):
    if not isinstance(release, dict) or not release.get("ocid"):
        raise Reject("not_an_ocds_release", {"keys": sorted(release)[:12] if isinstance(release, dict) else str(type(release))})
    parties = _party_index(release)
    tender = release.get("tender") or {}
    awards_src = release.get("awards") or []
    notes = []
    buyer = _org(release.get("buyer"), parties, country)
    cls, seen = [], set()
    for c in [tender.get("classification")] + [(i or {}).get("classification") for i in tender.get("items") or []]:
        if c and c.get("id") and (c.get("scheme"), c["id"]) not in seen:
            seen.add((c.get("scheme"), c["id"]))
            cls.append(classification(c.get("scheme") or "unknown", c["id"], c.get("description")))
    value = tender.get("value") or {}
    try:
        tv = money(value.get("amount"), value.get("currency")) if value.get("amount") is not None else None
    except Reject as e:
        tv = None
        notes.append("tender_value_dropped:" + e.reason)
    tp = tender.get("tenderPeriod") or {}
    title = _first(tender.get("title"), (awards_src[0] or {}).get("title") if awards_src else None)
    process = {
        "ocid": release["ocid"], "ocid_native": ocid_native, "stage": stage_of(release), "title": title,
        "description": tender.get("description"), "buyer": buyer, "country": country, "status": tender.get("status"),
        "procurement_method": _first(tender.get("procurementMethodDetails"), tender.get("procurementMethod")),
        "main_category": tender.get("mainProcurementCategory"), "value": tv,
        "published_at": to_ts(_first(tender.get("datePublished"), release.get("date"))), "updated_at": to_ts(release.get("date")),
        "tender_start": to_ts(tp.get("startDate")), "tender_end": to_ts(tp.get("endDate")), "classifications": cls,
        "items": [{k: i.get(k) for k in ("id", "description", "classification", "quantity", "unit") if i.get(k) is not None}
                  for i in (tender.get("items") or [])[:50]],
        "language": release.get("language"), "url": source_url,
    }
    awards = []
    for a in awards_src:
        if not a.get("id"):
            notes.append("award_without_id_skipped")
            continue
        sups = [s for s in (_org(x, parties) for x in (a.get("suppliers") or [])) if s]
        try:
            val = money((a.get("value") or {}).get("amount"), (a.get("value") or {}).get("currency")) if (a.get("value") or {}).get("amount") is not None else None
        except Reject as e:
            val = None
            notes.append("award_value_dropped:" + e.reason)
        awards.append({"award_id": str(a["id"]), "title": a.get("title"), "status": a.get("status"), "date": to_ts(a.get("date")), "value": val, "suppliers": sups})
    contracts = []
    for c in release.get("contracts") or []:
        if not c.get("id"):
            notes.append("contract_without_id_skipped")
            continue
        try:
            val = money((c.get("value") or {}).get("amount"), (c.get("value") or {}).get("currency")) if (c.get("value") or {}).get("amount") is not None else None
        except Reject as e:
            val = None
            notes.append("contract_value_dropped:" + e.reason)
        per = c.get("period") or {}
        contracts.append({"contract_id": str(c["id"]), "award_id": c.get("awardID"), "title": c.get("title"), "status": c.get("status"),
                          "date_signed": to_ts(c.get("dateSigned")), "period_start": to_ts(per.get("startDate")), "period_end": to_ts(per.get("endDate")), "value": val})
    return make_record(source_id=source_id, external_id=release.get("id"), raw=release, process=process, fetched_at=fetched_at,
                       source_url=source_url, publisher=publisher, published_at=process["published_at"], source_updated_at=process["updated_at"],
                       language=release.get("language"), licence=licence, awards=awards, contracts=contracts, validation_notes=notes or None)
