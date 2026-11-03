"""OCDS bulk files from the OCP Data Registry (one JSON line per compiled release in <dataset>/download?name=full.jsonl.gz).
The connector streams the gzip and stops after `limit` lines, so a bounded test never downloads a whole dataset."""
import gzip
import json

from ..bundle import Reject
from ..http import FetchError
from ..ocds import release_to_record
from .base import Connector

REGISTRY = "https://data.open-contracting.org/en/publication/%s/download?name=full.jsonl.gz"


class OcdsBulk(Connector):
    """source_id is the registry child source, e.g. ocp_pub_100. opts: publication (int), country (ISO2), licence, publisher."""
    expected_fields = frozenset({"id", "tag", "date", "ocid"})
    ignorable_fields = frozenset({"buyer", "awards", "tender", "parties", "language", "planning", "contracts", "initiationType", "bids", "relatedProcesses"})

    def __init__(self, client, source_id, **opts):
        super().__init__(client, **opts)
        self.source_id = source_id
        self.publisher, self.licence = opts.get("publisher"), opts.get("licence")

    def fetch(self, *, limit, since=None, until=None):
        r = self.client.get(REGISTRY % self.opts["publication"], stream=True)
        if r.status_code != 200:
            raise FetchError("http_%d" % r.status_code, "OCP download HTTP %d" % r.status_code, r.status_code)
        try:
            with gzip.GzipFile(fileobj=r.raw) as gz:
                for i, line in enumerate(gz):
                    if i >= limit:
                        break
                    try:
                        rel = json.loads(line)
                    except ValueError:
                        yield {"__bad_line__": i + 1}
                        continue
                    self.observe(rel)
                    yield rel
        finally:
            r.close()

    def normalize(self, raw, fetched_at):
        if "__bad_line__" in raw:
            raise Reject("invalid_json_line", {"line": raw["__bad_line__"]})
        return release_to_record(raw, source_id=self.source_id, fetched_at=fetched_at, publisher=self.publisher, licence=self.licence,
                                 source_url=self.opts.get("source_url"), country=self.opts.get("country"))
