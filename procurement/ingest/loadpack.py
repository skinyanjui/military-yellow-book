"""Builds the JSON payloads that are loaded into the registry: documentation/probe evidence, live-call evidence from recorded runs, verified claims.
(Transport into the database is separate: the same payloads can be applied with psql, psycopg, or the Supabase SQL tool.)"""
import glob
import json
import os
import sys

BASE = os.path.join(os.path.dirname(__file__), "..")
KIND = {"documentation": "documentation", "endpoint_probe": "endpoint_probe"}


def evidence_payload(verify_file, claims_file, samples_dir, endpoints):
    v = json.load(open(verify_file))
    ev = []
    for r in v["rows"]:
        detail = {k: r[k] for k in ("bytes", "title", "ms", "robots_allows") if k in r and r[k] is not None}
        ev.append({"source_id": r["source_id"], "check_kind": KIND[r["check"]], "url": r["url"], "checked_at": r["checked_at"], "status": r.get("status"),
                   "verdict": r["verdict"], "final_url": r.get("final_url"), "content_type": r.get("content_type"), "detail": detail})
    for f in sorted(glob.glob(os.path.join(samples_dir, "*.json"))):
        b = json.load(open(f))
        run = b["run"]
        ev.append({"source_id": run["source_id"], "check_kind": "live_call", "url": endpoints.get(run["source_id"]), "checked_at": run["started_at"], "status": 200,
                   "verdict": "records_returned" if b["records"] else "no_records", "detail": {"run_id": run["run_id"], "records": len(b["records"]), "rejected": len(b["rejected"]),
                                                                                           "drift": run.get("drift"), "mode": run["mode"]}})
    claims = [{**{k: c.get(k) for k in ("source_id", "field", "value", "method", "quote")}, "evidence_url": c.get("url"), "checked_on": json.load(open(claims_file))["verified_on"]}
              for c in json.load(open(claims_file))["claims"]]
    return {"evidence": ev, "claims": claims}


if __name__ == "__main__":
    from .connectors import pncp, secop, ted, uk, usaspending, worldbank
    ep = {"uk_fts": uk.UkFindATender.BASE, "uk_cf": uk.UkContractsFinder.BASE, "ted": ted.Ted.URL, "brazil_pncp": pncp.BASE + "/contratacoes/publicacao",
          "usaspending": usaspending.URL, "worldbank_procurement": worldbank.API, "colombia_secop": secop.URL}
    p = evidence_payload(os.path.join(BASE, "evidence", "verify_2026-11-03.json"), os.path.join(BASE, "evidence", "claims_verified_2026-11-03.json"), os.path.join(BASE, "samples"), ep)
    json.dump(p, open(sys.argv[1], "w"), ensure_ascii=False)
    print("evidence", len(p["evidence"]), "claims", len(p["claims"]))
