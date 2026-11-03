"""Candidate-quote extraction from official documentation pages.
Deterministic step: fetch a page (politely, robots-aware), strip it to text, and list sentences that mention authentication, rate limits or licensing.
Interpretation step (done by a person or the AI, reviewed): turn a quote into a claim in evidence/claims_reviewed.json.
Verification step (verify_claims.py): re-fetch and prove every claimed quote still appears verbatim on its page."""
import json
import re
import sys

from bs4 import BeautifulSoup

from .http import Client, FetchError

FIELDS = {
    "authentication": r"api[ _-]?key|authenticat|anonymous|without (?:an? )?(?:registration|key|token)|no (?:registration|authentication|api key)|\bticket\b|\btoken\b|oauth|credential|sign[ -]?up|register",
    "rate_limit": r"rate[ -]?limit|requests? (?:per|/|a) ?(?:second|minute|hour|day)|per (?:second|minute|hour|day)|throttl|too many requests|\b429\b|\blimit(?:s|ed)? of \d",
    "licence": r"licen[cs]e|terms of (?:use|service)|creative commons|open government|public domain|\bCC[- ]BY|re-?use|copyright|conditions of use",
}


def page_text(html):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text) if 30 <= len(s.strip()) <= 420]


def candidates(text, per_field=3):
    out = {}
    ss = sentences(text)
    for f, rx in FIELDS.items():
        pat = re.compile(rx, re.I)
        out[f] = [s for s in ss if pat.search(s)][:per_field]
    return out


def fetch_text(client, url):
    try:
        r = client.get(url)
    except FetchError as e:
        return None, "%s: %s" % (e.kind, str(e)[:120])
    if r.status_code != 200:
        return None, "http_%d" % r.status_code
    ct = r.headers.get("content-type", "")
    return (page_text(r.text) if "html" in ct or "xml" in ct else r.text[:200000]), None


def run(pages, out):
    c = Client(min_interval=1.5, timeout=60, retries=2)
    res = []
    for source_id, url in pages:
        if not c.robots_allows(url):
            res.append({"source_id": source_id, "url": url, "error": "robots_disallow"})
            continue
        text, err = fetch_text(c, url)
        res.append({"source_id": source_id, "url": url, "error": err, "chars": len(text or ""), "candidates": candidates(text) if text else {}})
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    return res


# Pages whose text was read for the registry (all fetched through the polite client above).
PAGES = [
    ("sam_opportunities", "https://open.gsa.gov/api/get-opportunities-public-api/"),
    ("ted", "https://docs.ted.europa.eu/api/latest/search.html"),
    ("ted_xml", "https://ted.europa.eu/en/simap/xml-bulk-download"),
    ("uk_fts", "https://www.find-tender.service.gov.uk/Developer/Documentation"),
    ("uk_fts", "https://www.find-tender.service.gov.uk/apidocumentation/1.0/GET-ocdsReleasePackages"),
    ("uk_cf", "https://www.contractsfinder.service.gov.uk/apidocumentation"),
    ("worldbank_procurement", "https://financesone.worldbank.org/procurement%20notice/DS00979"),
    ("chile_mercado", "https://www.chilecompra.cl/api/"),
    ("chile_ocds", "https://datos-abiertos.chilecompra.cl/descargas/procesos-ocds"),
    ("colombia_secop", "https://www.colombiacompra.gov.co/transparencia/datos-abiertos"),
    ("ocp_registry", "https://data.open-contracting.org/en/search/"),
    ("usaspending", "https://api.usaspending.gov/docs/endpoints"),
    ("brazil_pncp", "https://pncp.gov.br/api/consulta/swagger-ui/index.html"),
]

if __name__ == "__main__":
    r = run(PAGES, sys.argv[1])
    for x in r:
        print(x["source_id"], x["url"][:70], x.get("error"), x.get("chars"), {k: len(v) for k, v in x.get("candidates", {}).items()})
