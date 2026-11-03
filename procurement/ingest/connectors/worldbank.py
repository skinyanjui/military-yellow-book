"""World Bank Finances One, Procurement Notice dataset DS00979 (CC BY 4.0, public). Rows are ordered by id; the newest are at the end."""
from ..bundle import Reject, classification, make_record, to_ts
from .base import Connector

API = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"
Q = {"datasetId": "DS00979", "resourceId": "RS00909", "type": "json"}
TENDER = ("Invitation", "Request for Bids", "Request for Expression", "Request for Proposals", "Specific Procurement", "Invitation for Prequalification")


class WorldBankNotices(Connector):
    source_id = "worldbank_procurement"
    expected_fields = frozenset({"id", "bid_description", "country_code", "country_name", "deadline_date", "notice_type", "procurement_category",
                                 "procurement_method", "project_id", "publication_date", "region", "sector", "url"})
    ignorable_fields = frozenset({"publication___fiscal_year", "publication___calendar_year"})

    def fetch(self, *, limit, since, until):
        head = self.get_json(API, params={**Q, "top": 1})
        total = head["count"]
        skip = max(0, total - limit)
        while skip < total:
            j = self.get_json(API, params={**Q, "top": min(500, total - skip), "skip": skip})
            rows = j.get("data") or []
            for r in rows:
                self.observe(r)
                yield r
            if not rows:
                return
            skip += len(rows)

    def normalize(self, raw, fetched_at):
        rid = raw.get("id")
        if rid is None:
            raise Reject("missing_id")
        nt = raw.get("notice_type") or ""
        stage = "award" if "Award" in nt else "planning" if "General Procurement" in nt else "tender" if nt.startswith(TENDER) else "unknown"
        cc = raw.get("country_code")
        country = cc if isinstance(cc, str) and len(cc) == 2 and cc.isalpha() else None
        sectors = [s.strip() for s in (raw.get("sector") or "").split(";") if s.strip()]
        process = {"ocid": "myb-worldbank-%s" % rid, "ocid_native": False, "stage": stage, "title": (raw.get("bid_description") or "")[:200] or None,
                   "description": raw.get("bid_description"), "buyer": None, "country": country.upper() if country else None, "status": nt or None,
                   "procurement_method": raw.get("procurement_method"), "main_category": raw.get("procurement_category"),
                   "published_at": to_ts(raw.get("publication_date")), "updated_at": to_ts(raw.get("publication_date")), "tender_end": to_ts(raw.get("deadline_date")),
                   "classifications": [classification("WB-sector", s) for s in sectors], "financier": "World Bank", "project_id": raw.get("project_id"),
                   "language": "en", "url": raw.get("url")}
        notes = ["buyer_not_in_dataset"] + ([] if country else ["country_code_not_iso2:%s" % cc])
        return make_record(source_id=self.source_id, external_id=str(rid), raw=raw, process=process, fetched_at=fetched_at, source_url=raw.get("url"),
                           publisher="World Bank Group (Finances One)", published_at=process["published_at"], source_updated_at=process["updated_at"],
                           language="en", licence="CC BY 4.0", validation_notes=notes)
