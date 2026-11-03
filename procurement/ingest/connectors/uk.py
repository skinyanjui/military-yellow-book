"""UK Find a Tender and Contracts Finder: both publish OCDS release packages with cursor pagination (links.next)."""
import datetime

from ..ocds import release_to_record
from .base import Connector

OCDS_FIELDS = frozenset({"ocid", "id", "date", "tag", "initiationType", "parties", "buyer", "tender", "language"})
OCDS_OPTIONAL = frozenset({"awards", "bids", "buyerID", "contracts", "planning", "relatedProcesses", "statistics"})


def _dt(v, fmt):
    return (v if isinstance(v, datetime.datetime) else datetime.datetime.fromisoformat(v)).strftime(fmt)


class UkFindATender(Connector):
    source_id = "uk_fts"
    BASE = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
    expected_fields, ignorable_fields = OCDS_FIELDS, OCDS_OPTIONAL

    def fetch(self, *, limit, since, until):
        params = {"updatedFrom": _dt(since, "%Y-%m-%dT%H:%M:%S"), "updatedTo": _dt(until, "%Y-%m-%dT%H:%M:%S"), "limit": min(100, limit)}
        url, n = self.BASE, 0
        while url and n < limit:
            pkg = self.get_json(url, params=params if url == self.BASE else None)
            self.publisher, self.licence = (pkg.get("publisher") or {}).get("name"), pkg.get("license")
            for rel in pkg.get("releases") or []:
                self.observe(rel)
                yield rel
                n += 1
                if n >= limit:
                    return
            url = (pkg.get("links") or {}).get("next")

    def normalize(self, raw, fetched_at):
        return release_to_record(raw, source_id=self.source_id, fetched_at=fetched_at, publisher=self.publisher, licence=self.licence,
                                 source_url="https://www.find-tender.service.gov.uk/Notice/%s" % raw.get("id"), country="GB")


class UkContractsFinder(Connector):
    source_id = "uk_cf"
    BASE = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
    STAGES = ("tender", "award")
    expected_fields, ignorable_fields = OCDS_FIELDS, OCDS_OPTIONAL

    def fetch(self, *, limit, since, until):
        n = 0
        for stage in self.STAGES:
            params = {"publishedFrom": _dt(since, "%Y-%m-%d"), "publishedTo": _dt(until, "%Y-%m-%d"), "stages": stage, "limit": min(100, limit)}
            url = self.BASE
            while url and n < limit:
                pkg = self.get_json(url, params=params if url == self.BASE else None)
                self.publisher, self.licence = (pkg.get("publisher") or {}).get("name"), pkg.get("license")
                for rel in pkg.get("releases") or []:
                    self.observe(rel)
                    yield rel
                    n += 1
                    if n >= limit:
                        return
                url = (pkg.get("links") or {}).get("next")

    def normalize(self, raw, fetched_at):
        url = None
        for d in ((raw.get("tender") or {}).get("documents") or []) + [d for a in raw.get("awards") or [] for d in a.get("documents") or []]:
            if "contractsfinder.service.gov.uk/Notice/" in (d.get("url") or ""):
                url = d["url"]
                break
        return release_to_record(raw, source_id=self.source_id, fetched_at=fetched_at, publisher=self.publisher, licence=self.licence, source_url=url, country="GB")
