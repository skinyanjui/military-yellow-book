"""USAspending.gov (public, no key). Prime contract awards (types A-D) by the Department of Defense by default.
'Award Amount' is the total obligation: it is stored in award.obligated_amount, not as a contract or award value."""
from ..bundle import Reject, classification, make_record, money, party, to_ts
from .base import Connector

URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
FIELDS = ["Award ID", "Recipient Name", "Recipient UEI", "Award Amount", "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency", "PSC", "Description", "generated_internal_id"]
REDACTED = ("REDACTED", "MULTIPLE RECIPIENTS")


class UsaSpending(Connector):
    source_id = "usaspending"
    expected_fields = frozenset(FIELDS) | {"internal_id", "awarding_agency_id", "agency_slug"}
    ignorable_fields = frozenset({"prime_award_recipient_id"})

    def fetch(self, *, limit, since, until):
        flt = {"award_type_codes": ["A", "B", "C", "D"], "time_period": [{"start_date": since.strftime("%Y-%m-%d"), "end_date": until.strftime("%Y-%m-%d")}]}
        agency = self.opts.get("agency", "Department of Defense")
        if agency:
            flt["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]
        if self.opts.get("psc"):
            flt["psc_codes"] = self.opts["psc"]
        page, n = 1, 0
        while n < limit:
            j = self.post_json(URL, {"filters": flt, "fields": FIELDS, "limit": min(100, limit - n), "page": page, "sort": "Award Amount", "order": "desc"})
            for it in j.get("results") or []:
                self.observe(it)
                yield it
                n += 1
                if n >= limit:
                    return
            if not (j.get("page_metadata") or {}).get("hasNext"):
                return
            page += 1

    def normalize(self, raw, fetched_at):
        gid, aid = raw.get("generated_internal_id"), raw.get("Award ID")
        if not gid or not aid:
            raise Reject("missing_award_identifiers")
        notes = []
        name = raw.get("Recipient Name")
        if not name or any(x in name.upper() for x in REDACTED):
            sup, notes = [], ["recipient_not_disclosed"]
            slim = {k: v for k, v in raw.items() if k not in ("Recipient Name", "Recipient UEI")}
        else:
            sup, slim = [party(name, raw.get("Recipient UEI"), "US-UEI", "US")], dict(raw)
        psc = raw.get("PSC") or {}
        cls = [classification("PSC", psc["code"], psc.get("description"))] if psc.get("code") else []
        sub, top = raw.get("Awarding Sub Agency"), raw.get("Awarding Agency")
        url = "https://www.usaspending.gov/award/%s" % gid
        desc = raw.get("Description")
        process = {"ocid": "myb-usaspending-%s" % gid, "ocid_native": False, "stage": "award", "title": (desc or "")[:200] or None, "description": desc,
                   "buyer": party(sub or top, None, None, "US"), "country": "US", "main_category": "goods" if (psc.get("code") or "")[:1].isdigit() else None,
                   "published_at": to_ts(raw.get("Start Date")), "updated_at": to_ts(raw.get("Start Date")), "classifications": cls, "language": "en", "url": url}
        awards = [{"award_id": aid, "date": to_ts(raw.get("Start Date")), "obligated": money(raw.get("Award Amount"), "USD"), "suppliers": sup}]
        contracts = [{"contract_id": aid, "award_id": aid, "period_start": to_ts(raw.get("Start Date")), "period_end": to_ts(raw.get("End Date"))}]
        notes.append("buyer_is_awarding_sub_agency_of:%s" % top if top else "buyer_agency_unknown")
        return make_record(source_id=self.source_id, external_id=gid, raw=slim, process=process, fetched_at=fetched_at, source_url=url, publisher="USAspending.gov (US Treasury)",
                           published_at=process["published_at"], source_updated_at=process["updated_at"], language="en", awards=awards, contracts=contracts,
                           validation_notes=notes)
