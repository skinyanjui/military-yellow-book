"""Publisher cross-check: take records that are stored, re-read each one from its publisher BY IDENTIFIER (a different request from the list/search
query that fetched it), normalise the fresh copy with the same connector code, and compare the fields that matter.
The route used is recorded per check: 'independent' = a different endpoint or page than ingestion used; 'same_api_by_id' = the same API queried by id.
A source needs >= 3 matches and 0 mismatches (enforced in the database by procurement.record_crosscheck) before it can become operational."""
import json
import os
import re
import sys

from . import bundle as B
from .connectors import pncp, secop, ted, uk, usaspending, worldbank
from .docs_extract import page_text
from .http import Client, FetchError

BASE = os.path.join(os.path.dirname(__file__), "..")
NOW = B.now_iso()


def norm_text(s):
    return B.norm_name(s)


def key_fields(rec):
    """The fields compared between the stored record and the fresh publisher copy."""
    p = rec["process"]
    out = {"title": p.get("title"), "country": p.get("country"), "buyer": (p.get("buyer") or {}).get("name"), "value": p.get("value")}
    out["awards"] = sorted([{"id": a["award_id"], "obligated": a.get("obligated"), "value": a.get("value"),
                             "suppliers": sorted((s.get("id") or s["name"]) for s in a.get("suppliers", []) if s)} for a in rec.get("awards", [])], key=lambda x: x["id"])
    out["contracts"] = sorted([{"id": c["contract_id"], "value": c.get("value")} for c in rec.get("contracts", [])], key=lambda x: x["id"])
    return out


def compare(stored, fresh, skip=()):
    a, b = key_fields(stored), key_fields(fresh)
    diffs = {k: {"stored": a[k], "publisher": b[k]} for k in a if k not in skip and a[k] != b[k]}
    return diffs, {"hash_equal": stored["content_hash"] == fresh["content_hash"], "fields": [k for k in a if k not in skip]}


def result(rec, route, url, verdict, status=None, compared=None, note=None):
    return {"external_id": rec["external_id"], "url": url, "status": status, "verdict": verdict, "route": route, "compared": compared, "note": note}


def run_generic(rec, route, url, fetch_fresh, skip=()):
    try:
        fresh = fetch_fresh(rec)
    except FetchError as e:
        return result(rec, route, url, "unreachable", e.status, note="%s: %s" % (e.kind, str(e)[:160]))
    if fresh is None:
        return result(rec, route, url, "unreachable", 404, note="publisher returned no record for this identifier")
    diffs, info = compare(rec, fresh, skip)
    return result(rec, route, url, "mismatch" if diffs else "match", 200, {**info, "diffs": diffs}, None if not diffs else "fields differ: " + ", ".join(diffs))


# ---- per-source routes -------------------------------------------------------------------------------------------------------
def uk_fts(c):
    conn = uk.UkFindATender(c)

    def one(rec):
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages/%s" % rec["external_id"]
        pkg = conn.get_json(url)
        conn.publisher, conn.licence = (pkg.get("publisher") or {}).get("name"), pkg.get("license")
        rel = next((r for r in pkg.get("releases", []) if r.get("id") == rec["external_id"]), None)
        return conn.normalize(rel, NOW) if rel else None
    return lambda rec: run_generic(rec, "independent", "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages/%s" % rec["external_id"], one)


def uk_cf(c):
    conn = uk.UkContractsFinder(c)

    def one(rec):
        pkg = conn.get_json("https://www.contractsfinder.service.gov.uk/Published/OCDS/Release/%s" % rec["external_id"])
        conn.publisher, conn.licence = (pkg.get("publisher") or {}).get("name"), pkg.get("license")
        rel = next((r for r in pkg.get("releases", []) if r.get("id") == rec["external_id"]), None)
        return conn.normalize(rel, NOW) if rel else None
    return lambda rec: run_generic(rec, "independent", "https://www.contractsfinder.service.gov.uk/Published/OCDS/Release/%s" % rec["external_id"], one)


def ted_(c):
    conn = ted.Ted(c)

    def one(rec):
        j = conn.post_json(ted.Ted.URL, {"query": "publication-number=%s" % rec["external_id"], "fields": ted.FIELDS, "limit": 1, "page": 1, "scope": "ALL", "paginationMode": "PAGE_NUMBER"})
        n = next((x for x in j.get("notices", []) if x.get("publication-number") == rec["external_id"]), None)
        return conn.normalize(n, NOW) if n else None
    return lambda rec: run_generic(rec, "same_api_by_id", ted.Ted.URL + "?publication-number=" + rec["external_id"], one)


def usaspending_(c):
    conn = usaspending.UsaSpending(c)

    def one(rec):
        j = conn.get_json("https://api.usaspending.gov/api/v2/awards/%s/" % rec["external_id"])
        a = rec["awards"][0]
        diffs = {}
        if j.get("piid") != a["award_id"]:
            diffs["award_id"] = {"stored": a["award_id"], "publisher": j.get("piid")}
        amt = B.money(j.get("total_obligation"), "USD")
        if amt != a.get("obligated"):
            diffs["obligated"] = {"stored": a.get("obligated"), "publisher": amt}
        if a["suppliers"] and norm_text((j.get("recipient") or {}).get("recipient_name")) != norm_text(a["suppliers"][0]["name"]):
            diffs["supplier"] = {"stored": a["suppliers"][0]["name"], "publisher": (j.get("recipient") or {}).get("recipient_name")}
        if (rec["process"].get("title") or "") != (j.get("description") or "")[:200]:
            diffs["title"] = {"stored": rec["process"].get("title"), "publisher": (j.get("description") or "")[:200]}
        start = ((j.get("period_of_performance") or {}).get("start_date") or "")[:10]
        if not (rec["contracts"][0].get("period_start") or "").startswith(start):
            diffs["period_start"] = {"stored": rec["contracts"][0].get("period_start"), "publisher": start}
        return diffs
    def check(rec):
        url = "https://api.usaspending.gov/api/v2/awards/%s/" % rec["external_id"]
        try:
            diffs = one(rec)
        except FetchError as e:
            return result(rec, "independent", url, "unreachable", e.status, note="%s" % e.kind)
        return result(rec, "independent", url, "mismatch" if diffs else "match", 200, {"fields": ["award_id", "obligated", "supplier", "title", "period_start"], "diffs": diffs})
    return check


def worldbank_(c):
    conn = worldbank.WorldBankNotices(c)

    def one(rec):
        j = conn.get_json(worldbank.API, params={**worldbank.Q, "top": 2, "filter": "id = %s" % rec["external_id"]})
        return conn.normalize(j["data"][0], NOW) if j.get("data") else None
    return lambda rec: run_generic(rec, "same_api_by_id", worldbank.API + "?filter=id = " + rec["external_id"], one)


def secop_(c):
    conn = secop.ColombiaSecop(c)

    def one(rec):
        rows = conn.get_json(secop.URL, params={"id_contrato": rec["external_id"], "$limit": 2})
        return conn.normalize(rows[0], NOW) if rows else None
    return lambda rec: run_generic(rec, "same_api_by_id", secop.URL + "?id_contrato=" + rec["external_id"], one)


def pncp_(c):
    conn = pncp.BrazilPncp(c)

    def one(rec):
        raw = rec["raw"]
        if rec["external_id"].startswith("compra:"):
            o = raw["orgaoEntidade"]
            j = conn.get_json("%s/orgaos/%s/compras/%s/%s" % (pncp.BASE.replace("/consulta", ""), o["cnpj"], raw["anoCompra"], raw["sequencialCompra"])) if False else None
            d = (raw.get("dataPublicacaoPncp") or "")[:10].replace("-", "")
            for page in range(1, 40):
                j = conn.get_json(pncp.BASE + "/contratacoes/publicacao", params={"dataInicial": d, "dataFinal": d, "codigoModalidadeContratacao": raw["modalidadeId"], "cnpj": o["cnpj"], "pagina": page, "tamanhoPagina": 50})
                hit = next((x for x in j.get("data", []) if x.get("numeroControlePNCP") == raw["numeroControlePNCP"]), None)
                if hit or page >= (j.get("totalPaginas") or 0):
                    break
            return conn.normalize(hit, NOW) if hit else None
        d = (raw.get("dataAtualizacao") or raw.get("dataAssinatura") or "")[:10].replace("-", "")
        cnpj = (raw.get("orgaoEntidade") or {}).get("cnpj")
        for page in range(1, 40):
            j = conn.get_json(pncp.BASE + "/contratos/atualizacao", params={"dataInicial": d, "dataFinal": d, "cnpjOrgao": cnpj, "pagina": page, "tamanhoPagina": 50})
            hit = next((x for x in j.get("data", []) if x.get("numeroControlePNCP") == raw["numeroControlePNCP"]), None)
            if hit or page >= (j.get("totalPaginas") or 0):
                break
        return conn.normalize(hit, NOW) if hit else None
    return lambda rec: run_generic(rec, "same_api_by_id", pncp.BASE + ("/contratacoes/publicacao" if rec["external_id"].startswith("compra:") else "/contratos/atualizacao") + "#" + rec["external_id"], one)


ROUTES = {"uk_fts": uk_fts, "uk_cf": uk_cf, "ted": ted_, "usaspending": usaspending_, "worldbank_procurement": worldbank_, "colombia_secop": secop_, "brazil_pncp": pncp_}


def crosscheck(source_id, n=5, client=None):
    c = client or Client(min_interval=1.0, timeout=60, retries=2)
    bundle = json.load(open(os.path.join(BASE, "samples", source_id + ".json")))
    recs = bundle["records"]
    step = max(1, len(recs) // n)
    sample = recs[::step][:n]
    return {"source_id": source_id, "checks": [ROUTES[source_id](c)(r) for r in sample]}


if __name__ == "__main__":
    out = {}
    for sid in (sys.argv[2:] or ROUTES):
        out[sid] = crosscheck(sid, int(os.environ.get("N", "5")))
        v = [c["verdict"] for c in out[sid]["checks"]]
        print(sid, {x: v.count(x) for x in set(v)})
        for c in out[sid]["checks"]:
            if c["verdict"] != "match":
                print("   ", c["external_id"], c["verdict"], c.get("note"), json.dumps((c.get("compared") or {}).get("diffs"), ensure_ascii=False)[:400])
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
