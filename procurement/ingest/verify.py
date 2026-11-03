"""Deterministic source verification: what does the publisher's documentation URL and endpoint actually return
from this machine today? Produces evidence rows. It never decides licence or authentication terms: those are
read from the documentation and recorded in evidence/claims.json together with the page they came from."""
import concurrent.futures as cf
import datetime
import json
import re
import sys
import time

from .http import Client, FetchError

TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def probe(client, url, kind):
    t0 = time.monotonic()
    row = {"check": kind, "url": url, "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    try:
        r = client.get(url, allow_redirects=True, headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
        body = r.text[:200000] if "text" in r.headers.get("content-type", "") or "json" in r.headers.get("content-type", "") else ""
        m = TITLE.search(body)
        row.update(status=r.status_code, final_url=r.url, content_type=r.headers.get("content-type", "")[:120], bytes=len(r.content),
                   title=re.sub(r"\s+", " ", m.group(1)).strip()[:160] if m else None, ms=int((time.monotonic() - t0) * 1000))
        row["verdict"] = ("reachable" if r.status_code < 300 else "site_denied" if r.status_code in (401, 403) else
                          "not_found" if r.status_code in (404, 410) else "method_or_params_needed" if r.status_code in (400, 405, 422) else "http_error")
    except FetchError as e:
        row.update(status=e.status, verdict=e.kind, error=str(e)[:200], ms=int((time.monotonic() - t0) * 1000))
    return row


def verify_all(manifest_path, out_path, workers=6):
    sources = json.load(open(manifest_path))["sources"]
    client = Client(min_interval=1.0, timeout=30, retries=1)
    jobs = []
    for s in sources:
        jobs.append((s["source_id"], "documentation", s["documentation_url"]))
        if s.get("endpoint_url"):
            jobs.append((s["source_id"], "endpoint_probe", s["endpoint_url"]))
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(probe, client, u, k): (sid, k, u) for sid, k, u in jobs}
        rows = []
        for f in cf.as_completed(futs):
            row = f.result()
            row["source_id"] = futs[f][0]
            row["robots_allows"] = client.robots_allows(row["url"]) if row["check"] == "documentation" else None
            rows.append(row)
    rows.sort(key=lambda r: (r["source_id"], r["check"]))
    json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "method": "GET with identifying User-Agent from the build sandbox; robots.txt read separately", "rows": rows},
              open(out_path, "w"), indent=1, ensure_ascii=False)
    return rows


if __name__ == "__main__":
    rows = verify_all(sys.argv[1], sys.argv[2])
    for r in rows:
        print("%-24s %-15s %-22s %s %s" % (r["source_id"], r["check"], r["verdict"], r.get("status") or "", (r.get("title") or r.get("error") or "")[:60]))
