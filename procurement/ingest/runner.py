"""Run one connector and write a bundle. Deterministic: pagination, validation, hashing, money, dates and cursors are code.
Transport to the database is separate (sink.py), so the same bundle can be applied by psql, psycopg or the Supabase connector."""
import argparse
import datetime
import json
import os
import re
import sys

from . import bundle as B
from .connectors import gated, pncp, secop, ted, uk, usaspending, worldbank
from .connectors.base import MissingCredential
from .connectors.ocds_bulk import OcdsBulk
from .http import Client, FetchError

CONNECTORS = {c.source_id: c for c in (uk.UkFindATender, uk.UkContractsFinder, ted.Ted, pncp.BrazilPncp, usaspending.UsaSpending,
                                       worldbank.WorldBankNotices, secop.ColombiaSecop, gated.SamOpportunities, gated.ChileLicitaciones, gated.ChileOrdenes)}


CATALOGUE = os.path.join(os.path.dirname(__file__), "..", "catalog", "ocp_registry.json")


def ocp_opts(source_id):
    """publication id, ISO2 country, licence and publisher for an OCP child source, from the catalogue file (not guessed)."""
    for s in json.load(open(CATALOGUE))["sources"]:
        if s["source_id"] == source_id:
            m = re.search(r"country code ([A-Z]{2})", s.get("notes") or "")
            return {"publication": int(source_id.rsplit("_", 1)[1]), "country": m.group(1) if m else None, "licence": s.get("licence"), "publisher": s["owner_institution"]}
    raise SystemExit("%s is not in the OCP catalogue file" % source_id)


def build_connector(source_id, client, **opts):
    if source_id.startswith("ocp_pub_"):
        return OcdsBulk(client, source_id, **{**ocp_opts(source_id), **opts})
    if source_id not in CONNECTORS:
        raise SystemExit("no connector for %s" % source_id)
    return CONNECTORS[source_id](client, **opts)


def run_connector(conn, *, mode, limit, since=None, until=None, cursor=None, overlap=None):
    """-> bundle dict (always; failures are recorded in bundle['run'])."""
    until = until or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    hw = (cursor or {}).get("high_water")
    if since is None:
        since = (datetime.datetime.fromisoformat(hw).replace(tzinfo=None) - (overlap or conn.overlap)) if hw else until - datetime.timedelta(days=int(conn.opts.get("days", 7)))
    run = B.new_run(conn.source_id, mode, params={"limit": limit, "since": since.isoformat(timespec="seconds"), "until": until.isoformat(timespec="seconds"),
                                                   **{k: v for k, v in conn.opts.items() if isinstance(v, (str, int, list))}}, cursor_before=cursor)
    records, rejected, fetched = [], [], 0
    fetched_at = B.now_iso()
    try:
        conn.check_credentials()
        for raw in conn.fetch(limit=limit, since=since, until=until):
            fetched += 1
            try:
                rec = conn.normalize(raw, fetched_at)
                records.append(rec)
            except B.Reject as e:
                rejected.append({"external_id": str(raw.get("id") or raw.get("publication-number") or raw.get("numeroControlePNCP") or raw.get("id_contrato") or "")[:80] or None,
                                 "reason": e.reason, "detail": e.detail})
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                rejected.append({"external_id": None, "reason": "normalize_error:%s" % type(e).__name__, "detail": {"message": str(e)[:200]}})
        run["status"] = "success" if records or not rejected else "failed"
    except MissingCredential as e:
        run.update(status="failed", error_kind="missing_credential", error=str(e))
    except NotImplementedError as e:
        run.update(status="failed", error_kind="not_implemented", error=str(e))
    except FetchError as e:
        run.update(status="partial" if records else "failed", error_kind=e.kind, error=str(e)[:500])
    run["fetched"], run["drift"] = fetched, conn.drift()
    if run.get("status") in ("success", "partial") and records:
        stamps = [r.get("source_updated_at") or r.get("published_at") for r in records if r.get("source_updated_at") or r.get("published_at")]
        run["cursor_after"] = {"high_water": max(stamps)[:19] if stamps else until.isoformat(timespec="seconds")}
    out = {"run": run, "records": records, "rejected": rejected}
    errs = B.schema_errors(out)
    if errs:
        run.update(status="failed", error_kind="bundle_schema", error="; ".join(errs[:5]))
        out["records"] = []
    run["params"]["schema_errors"] = len(errs)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a connector and write a bundle JSON file")
    ap.add_argument("source_id")
    ap.add_argument("--mode", default="test", choices=["test", "incremental", "backfill"])
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--cursor-file")
    ap.add_argument("--opt", action="append", default=[], help="key=value connector option (repeatable)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    opts = {"days": a.days}
    for kv in a.opt:
        k, _, v = kv.partition("=")
        opts[k] = int(v) if v.isdigit() else (v.split(",") if "," in v else v)
    conn = build_connector(a.source_id, Client(min_interval=float(os.environ.get("INGEST_MIN_INTERVAL", "1.0"))), **opts)
    cur = json.load(open(a.cursor_file)) if a.cursor_file and os.path.exists(a.cursor_file) else None
    parse = lambda s: datetime.datetime.fromisoformat(s) if s else None
    b = run_connector(conn, mode=a.mode, limit=a.limit, since=parse(a.since), until=parse(a.until), cursor=cur)
    json.dump(b, open(a.out, "w"), ensure_ascii=False, indent=1)
    r = b["run"]
    print("%s mode=%s status=%s fetched=%s records=%s rejected=%s drift=%s %s" % (r["source_id"], r["mode"], r.get("status"), r.get("fetched"), len(b["records"]), len(b["rejected"]),
          r.get("drift"), r.get("error") or ""))
    return 0 if r.get("status") in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
