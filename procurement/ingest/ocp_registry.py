"""OCP Data Registry catalogue sync: reads the public search page and each dataset's detail page (robots.txt allows everything;
the pages are CC BY 4.0 'unless otherwise noted') and turns them into source-registry rows. No dataset content is downloaded here."""
import json
import re
import sys

from bs4 import BeautifulSoup

from .http import Client

BASE = "https://data.open-contracting.org"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _t(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def parse_search(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for art in soup.find_all("article"):
        a = art.find("a", href=re.compile(r"^/en/publication/\d+"))
        if not a:
            continue
        pid = int(re.search(r"/publication/(\d+)", a["href"]).group(1))
        flag = art.find("img", src=re.compile(r"/flags/([a-z]{2})\."))
        title = _t(art.find("h3"))
        country, _, publisher = title.partition(": ")
        formats = [_t(d).upper() for d in art.find_all("dd") if _t(d).upper() in ("JSON", "EXCEL", "CSV")]
        out.append({"publication": pid, "title": title, "country": country if publisher else None, "publisher": publisher or title,
                    "iso2": re.search(r"/flags/([a-z]{2})\.", flag["src"]).group(1).upper() if flag else None, "formats": formats})
    return out


def _ym(s):
    m = re.search(r"([A-Z][a-z]{2}) (\d{4})", s or "")
    return "%s-%02d-01" % (m.group(2), MONTHS[m.group(1)]) if m and m.group(1) in MONTHS else None


def _dd(soup, label):
    for dt in soup.find_all("dt"):
        if _t(dt).startswith(label):
            return dt.find_next_sibling("dd")
    return None


def _link(dd):
    a = dd.find("a", href=True) if dd is not None else None
    return (_t(a), a["href"]) if a else (None, None)


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    kv = {}
    for dt in soup.find_all("dt"):
        label = _t(dt).rstrip(":").strip()
        dd = dt.find_next_sibling("dd")
        if label and dd is not None and label not in kv:
            kv[label] = _t(dd)
    counts = {k.replace("Count of ", ""): int(v.replace(",", "")) for k, v in kv.items() if k.startswith("Count of ") and re.fullmatch(r"[\d,]+", v)}
    dates = re.findall(r"[A-Z][a-z]{2} \d{4}", kv.get("Data date range", ""))
    lic_name, lic_url = _link(_dd(soup, "License"))
    _, policy_url = _link(_dd(soup, "Publication policy"))
    _, retrieved_from = _link(_dd(soup, "Retrieved from"))
    freq = kv.get("Update frequency")
    return {
        "coverage_from": _ym(dates[0]) if dates else None, "coverage_to": _ym(dates[-1]) if dates else None,
        "no_longer_updated": "no longer updated by the publisher" in kv.get("Data date range", ""),
        "update_frequency": None if freq in (None, "", "-") else freq, "last_retrieved": kv.get("Last retrieved"),
        "licence": lic_name, "licence_url": lic_url, "publication_policy_url": policy_url, "retrieved_from": retrieved_from,
        "language": kv.get("Main language"), "ocid_prefix": kv.get("OCID prefix"), "counts": counts,
        "downloads": sorted(set(re.findall(r"/download\?name=([A-Za-z0-9.]+)", html))),
    }


STAGE_OF_COUNT = {"planning activities": "planning", "tenders": "tender", "awards": "award", "contracts": "contract"}


def build_rows(search_html, fetch_detail):
    rows, claims = [], []
    for d in parse_search(search_html):
        det = fetch_detail(d["publication"])
        sid, url = "ocp_pub_%d" % d["publication"], "%s/en/publication/%d" % (BASE, d["publication"])
        stages = [v for k, v in STAGE_OF_COUNT.items() if det["counts"].get(k)]
        dl = "full.jsonl.gz" if "full.jsonl.gz" in det["downloads"] else None
        notes = ["OCP registry publication %d" % d["publication"], "country code %s" % d["iso2"], "main language %s" % det["language"], "ocid prefix %s" % det["ocid_prefix"],
                 "counts as shown by the registry: " + json.dumps(det["counts"], separators=(",", ":"))]
        if det["retrieved_from"]:
            notes.append("OCP retrieves it from %s (stated by OCP, not probed here)" % det["retrieved_from"])
        if det["publication_policy_url"]:
            notes.append("publication policy: %s" % det["publication_policy_url"])
        if det["no_longer_updated"]:
            notes.append("the registry says the publisher no longer updates this dataset")
        rows.append({
            "source_id": sid, "parent_source_id": "ocp_registry", "name": d["title"], "canonical_url": url,
            "endpoint_url": "%s/download?name=%s" % (url, dl) if dl else None, "country": d["country"] or d["iso2"], "jurisdiction": "dataset",
            "owner_institution": d["publisher"], "source_kind": "bulk", "access_class": "bulk_download", "record_types": stages,
            "formats": d["formats"], "licence": det["licence"], "licence_url": det["licence_url"],
            "update_frequency": det["update_frequency"] or ("last retrieved " + det["last_retrieved"] if det["last_retrieved"] else None),
            "suggested_cadence": "per_dataset", "coverage_from": det["coverage_from"], "coverage_to": det["coverage_to"],
            "verification_status": "catalog_confirmed", "connector": "ocds_bulk", "connector_state": "none", "notes": "; ".join(notes)})
        claims.append({"source_id": sid, "field": "licence", "value": det["licence"] or "not stated on the registry page",
                       "method": "doc_read" if det["licence"] else "not_stated", "evidence_url": url,
                       "quote": ("License: " + det["licence"]) if det["licence"] else "License: -"})
    return rows, claims


def sync(out_path, limit=None):
    c = Client(min_interval=1.0, timeout=60, retries=3)
    r = c.get(BASE + "/en/search/")
    r.raise_for_status()
    cache = {}

    def fetch_detail(pid):
        if limit is not None and len(cache) >= limit:
            return {"counts": {}, "licence": None, "licence_url": None, "coverage_from": None, "coverage_to": None, "update_frequency": None, "last_retrieved": None,
                    "language": None, "ocid_prefix": None, "no_longer_updated": False, "retrieved_from": None, "publication_policy_url": None, "downloads": []}
        d = c.get("%s/en/publication/%d" % (BASE, pid))
        d.raise_for_status()
        cache[pid] = 1
        return parse_detail(d.text)

    rows, claims = build_rows(r.text, fetch_detail)
    json.dump({"origin": "ocp_registry", "sources": rows, "claims": claims}, open(out_path, "w"), ensure_ascii=False, indent=1)
    return rows


if __name__ == "__main__":
    rows = sync(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(len(rows), "datasets;", sum(1 for r in rows if r["licence"]), "with a licence on the page")
