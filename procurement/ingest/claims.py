"""Claims about sources must be provable. A reviewed claim carries a URL and a verbatim quote; this module re-fetches the URL and
refuses any claim whose quote is not on the page. 'not_stated' claims only prove the page was reachable and said nothing.
Live-call claims (e.g. 'no credential needed') are generated from the recorded sample runs, never typed in."""
import glob
import json
import os
import re
import sys

from .docs_extract import page_text
from .http import Client, FetchError


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def verify(reviewed, client):
    cache, ok, bad = {}, [], []
    for c in reviewed["claims"]:
        url = c["url"]
        try:
            if c.get("check") in ("robots_disallows", "robots_unreadable"):
                got = client.robots_allows(url)
                passed = got is False if c["check"] == "robots_disallows" else got is None
                (ok if passed else bad).append({**c, "problem": None if passed else "robots result changed: %r" % got})
                continue
            if url not in cache:
                r = client.get(url)
                ct = r.headers.get("content-type", "")
                cache[url] = (r.status_code, norm(page_text(r.text)) if "html" in ct else norm(r.text))
            status, text = cache[url]
        except FetchError as e:
            bad.append({**c, "problem": "unreachable: %s" % e.kind})
            continue
        if status != 200:
            bad.append({**c, "problem": "http_%d" % status})
        elif c["method"] == "not_stated" or norm(c["quote"]) in text:
            ok.append(c)
        else:
            bad.append({**c, "problem": "quote not found on page"})
    return ok, bad


def live_claims(samples_dir, endpoints):
    """From the recorded runs: which sources answered anonymously with schema-valid records, and the licence their records carry."""
    out = []
    for f in sorted(glob.glob(os.path.join(samples_dir, "*.json"))):
        b = json.load(open(f))
        run, recs = b["run"], b["records"]
        sid = run["source_id"]
        if run.get("status") != "success" or not recs:
            continue
        out.append({"source_id": sid, "field": "authentication", "method": "live_call", "url": endpoints.get(sid),
                    "value": "none needed: an anonymous request returned %d records that validated" % len(recs),
                    "quote": "run %s, %s, no credential sent" % (run["run_id"], run["started_at"])})
        lic = sorted({r["licence"] for r in recs if r.get("licence")})
        if lic:
            out.append({"source_id": sid, "field": "licence_in_records", "method": "live_call", "url": endpoints.get(sid),
                        "value": "; ".join(lic), "quote": "licence carried by the records of run %s" % run["run_id"]})
    return out


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    reviewed = json.load(open(os.path.join(base, "evidence", "claims_reviewed.json")))
    manifest = {s["source_id"]: s["endpoint_url"] for s in json.load(open(os.path.join(base, "manifest", "procurement_source_manifest.json")))["sources"]}
    ok, bad = verify(reviewed, Client(min_interval=1.0, timeout=60, retries=2))
    live = live_claims(os.path.join(base, "samples"), manifest)
    json.dump({"verified_on": reviewed["reviewed_on"], "claims": ok + live}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
    print("verified %d, live %d, FAILED %d" % (len(ok), len(live), len(bad)))
    for b in bad:
        print("  FAIL", b["source_id"], b["field"], b["problem"], "|", (b.get("quote") or "")[:80])
    sys.exit(1 if bad else 0)
