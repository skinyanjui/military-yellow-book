# Procurement source coverage, 3 November 2026

Generated from the live registry (`procurement.dashboard_snapshot()`, saved in `procurement/evidence/dashboard_snapshot_2026-11-03.json`).
A source counts as **operational** only after (1) a run fetched and schema-validated real records, (2) at least 3 of its stored records
matched the publisher when re-read by identifier, with no mismatch, and (3) its licence is established from a verified document or the
publisher's own data. Nothing below was inferred from a manifest label alone.

## Summary

| | Count |
| --- | --- |
| Sources in the registry | 350 (29 seed + 136 OCP datasets + 185 national/subnational portals; 9 portal duplicates caught and aliased) |
| Countries and territories named | 196 |
| Operational | 4 |
| Cross-checked, licence not yet established | 3 |
| Ingested, awaiting a publisher cross-check | 3 |
| Credential-gated (connector fails closed) | 3 |
| Failing | 1 (Italy ANAC: publisher dates malformed, 20 of 20 records rejected and kept with reasons) |
| Records stored | 179 source-record versions, 171 procurement processes, 96 awards, 87 contracts, 187 organisations |

## Access classes

| Class | Meaning | Sources |
| --- | --- | --- |
| `confirmed_api` | We called it and got schema-valid records | 7: UK Find a Tender, UK Contracts Finder, EU TED Search, Brazil PNCP, USAspending, World Bank notices, Colombia SECOP (Socrata) |
| `bulk_download` | Official dataset download | 139: 136 OCP registry datasets, the OCP registry, TED XML, ChileCompra OCDS |
| `credential_required` | Documented API that needs a key or ticket | 3: SAM.gov Opportunities (`SAM_GOV_API_KEY`), ChileCompra tenders and orders (`CHILECOMPRA_TICKET`) |
| `restricted_provider` | Access by agency or partner authorisation | 1: UNGM |
| `discovery_needed` | Machine access not yet identified | 1: CanadaBuys |
| `portal_only` | A website to register and bid on; not automated, and never treated as an API | 199 |

No source is classed `permitted_html`: no HTML page is collected. TED's `robots.txt` answers with a challenge page (HTTP 202), so permission for
automated page fetches cannot be established and none are made; the TED API is a different host.

## The core sources

| Source | State | Cross-check route (5 records each, all matched) | Licence evidence |
| --- | --- | --- | --- |
| UK Find a Tender | operational | independent: single release package by id | OGL v3, docs page and the release package |
| UK Contracts Finder | operational | independent: `Published/OCDS/Release/{id}` | OGL v3 in the release package |
| World Bank procurement notices | operational | same API, filtered by notice id | CC BY 4.0, World Bank Data Catalog page |
| Colombia SECOP II contracts | operational | same API, filtered by `id_contrato` | CC BY-SA 4.0 (`licenseId CC_40_BY_SA` in the catalogue metadata) |
| USAspending (DoD prime awards) | licence unconfirmed | independent: `/api/v2/awards/{id}/`; Award Amount equals `total_obligation` | not stated on the pages read |
| EU TED Search | licence unconfirmed | same API, by publication number | not stated on the pages read |
| Brazil PNCP | licence unconfirmed | same API, narrowed by CNPJ and date | not stated on the pages read |
| SAM.gov, ChileCompra (2) | needs credentials | — | ChileCompra: 10,000 requests per day per ticket (quoted) |
| OCP Albania (134), Mexico Veracruz (100) | ingested, awaiting cross-check | no per-record publisher route automated yet | per-dataset licence on the registry page |
| OCP Italy ANAC (117) | failing | — | CC BY 4.0 |

"Same API" checks prove that what is stored equals what the publisher serves now; they are weaker than a separate route, and are marked as such in each evidence row.

## Licences in the OCP registry (136 datasets)

41 are CC BY-NC-SA 4.0 (**non-commercial**), 18 CC BY 4.0, 16 PDDL, 14 "Términos de libre uso MX", 5 CC0, 4 OGL v3, others single cases, and 10 state no licence.
Non-commercial and unstated datasets are never published on the site (`procurement.publishable_sources()` excludes them). 43 are marked by the registry as no longer updated.

## Gaps, stated plainly

- Hospitals, universities, utilities and municipalities are only covered where an OCP dataset or a listed portal happens to include them; there is no systematic list yet.
- Development banks other than the World Bank (ADB, AfDB, AIIB, EBRD) are portals only. AfDB, CanadaBuys, China CCGP and India GeM could not be reached from the build host (403 or connection error) and stay pending verification.
- No currency conversion is applied anywhere; values stay in the publisher's currency.
- TED award notices are not paired with their lots; TED procedures are not yet linked to their contract notices.
