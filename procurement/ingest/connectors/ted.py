"""EU TED Search API v3 (POST /v3/notices/search, anonymous). Defence, security and related supplies: CPV division 35 by default.
Notices are not linked into procedures here (each publication number is its own process) - see docs/PROCUREMENT_PLATFORM.md."""
from ..bundle import Reject, classification, make_record, money, party, to_ts
from ..countries import ISO3_TO_ISO2
from .base import Connector

FIELDS = ["publication-number", "notice-identifier", "notice-title", "notice-type", "buyer-name", "buyer-country", "publication-date", "dispatch-date",
          "classification-cpv", "contract-nature", "procedure-type", "winner-name", "winner-country", "description-lot",
          "deadline-receipt-tender-date-lot", "total-value", "total-value-cur", "legal-basis"]


def pick(v, prefer=("eng",)):
    """TED returns multilingual values as {lang: text-or-list}; prefer English, else the first language present."""
    if isinstance(v, dict):
        for lang in list(prefer) + sorted(v):
            if lang in v and v[lang]:
                v = v[lang]
                break
        else:
            return None
    if isinstance(v, list):
        return v[0] if v else None
    return v


class Ted(Connector):
    source_id = "ted"
    URL = "https://api.ted.europa.eu/v3/notices/search"
    expected_fields = frozenset({"publication-number", "notice-identifier", "notice-title", "notice-type", "buyer-name", "buyer-country", "publication-date",
                                 "dispatch-date", "classification-cpv", "contract-nature", "procedure-type", "description-lot", "legal-basis", "links"})
    ignorable_fields = frozenset({"winner-name", "winner-country", "deadline-receipt-tender-date-lot", "total-value", "total-value-cur"})

    def fetch(self, *, limit, since, until):
        cpv = self.opts.get("cpv", "35*")
        query = "classification-cpv=%s AND publication-date>=%s AND publication-date<=%s" % (cpv, since.strftime("%Y%m%d"), until.strftime("%Y%m%d"))
        page, n = 1, 0
        while n < limit:
            body = {"query": query, "fields": FIELDS, "limit": min(100, limit - n), "page": page, "scope": "ALL", "paginationMode": "PAGE_NUMBER"}
            j = self.post_json(self.URL, body)
            notices = j.get("notices") or []
            self.total = j.get("totalNoticeCount")
            for nt in notices:
                self.observe(nt)
                yield nt
                n += 1
            if not notices or n >= (self.total or 0):
                return
            page += 1

    def normalize(self, raw, fetched_at):
        num = raw.get("publication-number")
        if not num:
            raise Reject("missing_publication_number")
        links = raw.get("links") or {}
        url = ((links.get("htmlDirect") or links.get("html") or {}).get("ENG")) or "https://ted.europa.eu/en/notice/-/detail/%s" % num
        slim = {k: v for k, v in raw.items() if k != "links"}
        slim["links"] = {"xml": (links.get("xml") or {}).get("MUL"), "html": url}
        buyer_country = (raw.get("buyer-country") or [None])[0]
        country = ISO3_TO_ISO2.get(buyer_country)
        notes = [] if country or not buyer_country else ["unmapped_country:" + str(buyer_country)]
        ntype = raw.get("notice-type") or ""
        stage = "award" if ntype.startswith("can") else "tender" if ntype.startswith("cn") else "planning" if ntype.startswith("pin") else "contract" if ntype.startswith("cm") else "unknown"
        cur = (raw.get("total-value-cur") or [None])[0]
        try:
            value = money(raw.get("total-value"), cur) if raw.get("total-value") is not None else None
        except Reject as e:
            value, notes = None, notes + ["value_dropped:" + e.reason]
        cpvs, seen = [], set()
        for c in raw.get("classification-cpv") or []:
            if c not in seen:
                seen.add(c)
                cpvs.append(classification("CPV", c))
        bname = pick(raw.get("buyer-name"))
        deadline = (raw.get("deadline-receipt-tender-date-lot") or [None])[0]
        winners = []
        w = raw.get("winner-name")
        for name in (w if isinstance(w, list) else (pick(w, ()) if isinstance(w, dict) else [])) or []:
            if isinstance(name, list):
                name = name[0] if name else None
            if name and name not in winners:
                winners.append(name)
        awards = [{"award_id": "%s-awarded" % num, "title": None, "status": "active",
                   "date": to_ts(raw.get("publication-date")), "value": None, "suppliers": [party(x) for x in winners]}] if stage == "award" and winners else []
        process = {
            "ocid": "myb-ted-%s" % num, "ocid_native": False, "stage": stage, "title": pick(raw.get("notice-title")),
            "description": pick(raw.get("description-lot")), "buyer": party(bname, None, None, country), "country": country,
            "procurement_method": raw.get("procedure-type"), "main_category": (raw.get("contract-nature") or [None])[0], "value": value,
            "published_at": to_ts(raw.get("publication-date")), "updated_at": to_ts(raw.get("dispatch-date") or raw.get("publication-date")),
            "tender_end": to_ts(deadline) if deadline else None, "classifications": cpvs, "url": url,
        }
        return make_record(source_id=self.source_id, external_id=num, raw=slim, process=process, fetched_at=fetched_at, source_url=url,
                           publisher="Publications Office of the European Union (TED)", published_at=process["published_at"],
                           source_updated_at=process["updated_at"], awards=awards, validation_notes=notes or None)
