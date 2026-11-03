"""Direct database transport for scheduled runs (GitHub Actions). Reads the checkpoint, runs the connector, sends the bundle to
procurement.ingest_bundle, and republishes the public opportunities. Needs DATABASE_URL (a Postgres connection string for the
project, kept as a repository secret). Not exercised in the build sandbox, which has no database connection string."""
import json
import os
import sys

import psycopg

from .http import Client
from .runner import build_connector, run_connector


def run(source_id, limit, days):
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as db:
        row = db.execute("select cursor from procurement.checkpoint where source_id = %s and key = 'default'", (source_id,)).fetchone()
        conn = build_connector(source_id, Client(min_interval=float(os.environ.get("INGEST_MIN_INTERVAL", "1.0"))), days=days)
        bundle = run_connector(conn, mode="incremental", limit=limit, cursor=row[0] if row else None)
        res = db.execute("select procurement.ingest_bundle(%s::jsonb)", (json.dumps(bundle, ensure_ascii=False),)).fetchone()[0]
        print(source_id, json.dumps(res), "drift:", json.dumps(bundle["run"].get("drift")))
        return res


if __name__ == "__main__":
    ids = sys.argv[1:] or ["uk_fts", "uk_cf", "worldbank_procurement", "colombia_secop", "ted", "brazil_pncp", "usaspending"]
    failed = 0
    for sid in ids:
        try:
            r = run(sid, int(os.environ.get("INGEST_LIMIT", "500")), int(os.environ.get("INGEST_DAYS", "3")))
            failed += r.get("status") == "failed"
        except Exception as e:      # one source failing must not stop the others; the run row and v_alert record it
            print(sid, "ERROR", type(e).__name__, str(e)[:300]); failed += 1
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as db:
        print("publish:", db.execute("select procurement.publish_opportunities()").fetchone()[0])
        print("alerts:", db.execute("select coalesce(jsonb_agg(a), '[]') from procurement.v_alert a").fetchone()[0])
    sys.exit(1 if failed == len(ids) else 0)
