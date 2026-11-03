"""Turns the seed manifest (and, later, other catalogues) into rows for procurement.import_sources.

Rules, from the brief: a portal is never promoted to an API, 'verified_documented' is not 'verified live', and nothing is
'confirmed_api' or 'operational' until a real run and a publisher cross-check say so. This file only *describes* sources;
the database functions and the cross-check decide what is confirmed."""
import json
import re
import sys

# manifest access_type -> (source_kind, access_class). Everything API-like starts as documented_api, never confirmed_api.
ACCESS = {
    "rest_api": ("api", "documented_api"), "socrata": ("api", "documented_api"), "bulk_csv_json_api": ("api", "documented_api"),
    "bulk_ocds": ("bulk", "bulk_download"), "bulk_xml": ("bulk", "bulk_download"),
    "portal": ("portal", "portal_only"), "portal_and_downloads": ("portal", "portal_only"), "marketplace": ("marketplace", "portal_only"),
}
# manifest verification_status values that change the class
DISCOVERY = {"api_requires_discovery": "discovery_needed"}
CREDENTIALS = {"api_key", "registration_ticket"}
# connector code that exists for a source (see ingest/runner.py CONNECTORS); gated ones fail closed without credentials
CONNECTORS = {
    "sam_opportunities": ("sam_opportunities", "stub_credential_gated"), "chile_mercado": ("chile_licitaciones", "stub_credential_gated"),
    "chile_orders": ("chile_ordenes", "stub_credential_gated"),
    "usaspending": ("usaspending", "built_untested"), "ted": ("ted", "built_untested"), "uk_fts": ("uk_fts", "built_untested"),
    "uk_cf": ("uk_cf", "built_untested"), "worldbank_procurement": ("worldbank_procurement", "built_untested"),
    "brazil_pncp": ("brazil_pncp", "built_untested"), "colombia_secop": ("colombia_secop", "built_untested"),
    "ocp_registry": ("ocp_registry", "built_untested"),
}
OWNERS = {  # only where the manifest 'name' / jurisdiction states the institution
    "sam_opportunities": "U.S. General Services Administration", "usaspending": "U.S. Department of the Treasury",
    "worldbank_procurement": "World Bank Group", "ocp_registry": "Open Contracting Partnership",
}


def manifest_to_payload(manifest):
    out = []
    for s in manifest["sources"]:
        kind, cls = ACCESS[s["access_type"]]
        if s["verification_status"] in DISCOVERY:
            cls = DISCOVERY[s["verification_status"]]
        if s["authentication"] in CREDENTIALS:
            cls = "credential_required"
        if s["verification_status"] == "restricted_api_access":
            cls = "restricted_provider"
        if s["source_id"] == "ocp_registry":
            kind = "catalog"
        conn, state = CONNECTORS.get(s["source_id"], (None, "none"))
        out.append({
            "source_id": s["source_id"], "name": s["name"], "canonical_url": s["documentation_url"], "endpoint_url": s["endpoint_url"],
            "country": s["country"], "jurisdiction": s["jurisdiction"], "owner_institution": OWNERS.get(s["source_id"]),
            "source_kind": kind, "access_class": cls, "record_types": [t.strip() for t in s["record_types"].split(",") if t.strip()],
            "authentication": s["authentication"], "suggested_cadence": s["suggested_cadence"],
            "verification_status": s["verification_status"], "connector": conn, "connector_state": state,
            "notes": "seed manifest %s (prepared %s)" % (manifest["manifest_version"], manifest["prepared_date"])})
    return {"origin": "seed_manifest", "sources": out}


if __name__ == "__main__":
    m = json.load(open(sys.argv[1]))
    json.dump(manifest_to_payload(m), open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
    print("wrote", sys.argv[2])
