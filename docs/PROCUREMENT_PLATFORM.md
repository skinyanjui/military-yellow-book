# Procurement data platform

How the Military Yellow Book turns official procurement sources into verified tenders and awards. AI is used to discover sources and to
read documentation; every retrieval, validation and database write is deterministic code with tests.

## Layout

| Path | What it is |
| --- | --- |
| `procurement/manifest/` | The 29-source seed manifest, as supplied |
| `procurement/ingest/http.py` | Polite client: identifying User-Agent, per-host interval, back-off with jitter, `Retry-After`, robots.txt |
| `procurement/ingest/connectors/` | One class per source; each has `fetch` (pagination, cursors) and `normalize` (to OCDS-shaped records) |
| `procurement/ingest/runner.py` | Runs a connector in `test`, `incremental` or `backfill` mode and writes a schema-validated bundle |
| `procurement/ingest/sink.py` | Scheduled transport: checkpoint → run → `procurement.ingest_bundle` → republish |
| `procurement/ingest/ocp_registry.py` | Syncs the OCP Data Registry catalogue into child sources |
| `procurement/ingest/docs_extract.py`, `claims.py` | Documentation quotes: extracted, reviewed, then re-verified verbatim against the live page |
| `procurement/ingest/crosscheck.py` | Re-reads stored records from each publisher by identifier and compares them |
| `procurement/tests/` | 73 tests on recorded real responses (no network) |
| `procurement/samples/` | The bounded test ingests that are loaded in the database |
| `procurement/evidence/` | Probe results, verified claims, cross-checks, dashboard snapshot |
| `supabase/migrations/*procurement_0[1-6]*` | Schema, registry, monitoring, licence gate, public opportunities |

## Database

Everything lives in the private `procurement` schema: no grants to `anon` or `authenticated`, RLS deny-all on every table, not exposed by the API.
The only public output is `public.myb_opportunities` (read-only), rebuilt by `procurement.publish_opportunities()` at 04:50 UTC by pg_cron.

- Writes: `procurement.ingest_bundle(jsonb)`. Idempotent by run id; a record whose content hash is unchanged is counted `unchanged`; a changed one becomes a new version and the old one stays as history; bad records go to `rejected_record` with the reason.
- Registry: `import_sources` (deduplicates by normalised URL plus endpoint, aliases duplicates), `record_evidence`, `record_catalog_run`, `set_verification`, `refresh_access_classes`.
- Gate: `record_crosscheck` sets `operational` only with ≥ 3 matches, 0 mismatches, a successful run and `licence_established()`; otherwise `licence_unconfirmed`. A mismatch sets `failing`.
- Monitoring: `v_source_status` (health per source), `v_alert`, `v_coverage_by_country`, `dashboard_snapshot()`. Duplicates: `detect_duplicates(days, similarity)` fills a review queue and never merges.

## Running it

```bash
cd procurement
pip install -r requirements.txt
python -m pytest tests -q                                          # 73 tests, no network
python -m ingest.runner uk_fts --limit 20 --out /tmp/uk_fts.json   # bounded live test
python -m ingest.runner ocp_pub_134 --limit 20 --out /tmp/al.json  # any OCP dataset by its registry id
N=5 python -m ingest.crosscheck /tmp/xc.json uk_fts                # publisher cross-check
python -m ingest.claims evidence/claims_verified.json              # re-verify every documentation quote
```

## Deployment

1. **Daily ingestion**: add a repository secret `DATABASE_URL` (Supabase → Project settings → Database → connection string, session pooler, with the database password). The `ingest-procurement` workflow then runs at 03:23 UTC; until the secret exists it does nothing. It has not been run here because the build host has no database connection string.
2. **Credentials** (optional): `SAM_GOV_API_KEY` (free key from your SAM.gov account page) and `CHILECOMPRA_TICKET` (requested with Clave Única). The connectors refuse to run without them and their field mappings still have to be written against real responses.
3. **Licences**: TED, PNCP and USAspending pass the record checks. Add a verified licence claim for each (a quote from an official page) to `procurement/evidence/claims_reviewed.json`, run `claims.py`, load it, and re-run `record_crosscheck`; they then publish automatically.
4. **Site**: `/opportunities` is a static page rebuilt by the `rebuild-site` workflow at 05:17 UTC from `myb_opportunities`.

## Recovery

Every run is a row in `connector_run` with its cursor. A failed incremental run leaves the checkpoint where it was, so the next run re-reads the
same window (1-day overlap). Re-sending a bundle is harmless. To rebuild a source from scratch: `--mode backfill --since … --until …` in windows.

## Known limits

- The shared Supabase project also hosts another app; a dedicated project is the right home once data volume grows (free tier storage is small).
- Bounded samples only (20 records per source) are loaded so far; volume comes from the scheduled workflow.
- No FX conversion; TED lots are not paired with awards; no account-deletion flow on the site (unchanged).
