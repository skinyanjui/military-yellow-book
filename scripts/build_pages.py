#!/usr/bin/env python3
"""Generate crawlable static pages for search engines into site/.

  site/l/<slug>.html   one page per live listing        (served at /l/<slug>)
  site/c/<slug>.html   one page per category            (served at /c/<category>)
  site/directory.html  every category and listing       (served at /directory)
  site/portals.html    government procurement portals   (served at /portals)
  site/terms.html, site/privacy.html, site/404.html
  site/sitemap.xml, site/robots.txt

The interactive app stays on hash routes (/#biz-<slug>); these pages are the indexable front door and link into it.
Listings come from Supabase (public columns, publishable key). PAGES_SOURCE controls the source:
  (unset)  try Supabase, fall back to the committed supabase/seed.json with a warning
  live     Supabase only; fail the build if it cannot be read (used by the GitHub Action)
  seed     supabase/seed.json only
Called from build_deploy.py; can also be run alone:  python3 scripts/build_pages.py
"""
import html, json, os, re, shutil, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unspsc'))
from mapping import CATEGORY_UNSPSC   # directory category -> UNSPSC families/classes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPABASE_URL = 'https://bfovgafcfetfeqykjfco.supabase.co'
SUPABASE_KEY = 'sb_publishable_FfVpTa_cEtn_LRJ5FNc-VQ_8bvPbVZx'   # publishable key: safe to ship
COLS = ('slug,name,category,supplier,city,country,region,unit,price,moq,lead,certs,ships,verified,years,descr,specs,'
        'domains,branches,is_sample,status,position,created_at,unspsc')
SLUG_OK = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@500&display=swap">'
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
        "fill='%23f5b800'/%3E%3Ctext x='16' y='22' font-family='Arial' font-weight='700' font-size='15' text-anchor='middle' "
        "fill='%23171717'%3EYB%3C/text%3E%3C/svg%3E")
FOOT = ('Complete firearms, ammunition, explosives and weapon systems are not listed. Weapon parts, aircraft parts and '
        'body-armor carriers are sold only by licensed dealers and need export licences and end-user certificates. '
        'Prices and lead times are set by each supplier; confirm terms in writing before you pay.')

CSS = """
:root{--bg:#fff;--fg:#171717;--muted:#666;--line:#e0e0e0;--subtle:#f7f7f7;--accent:#f5b800;--on-accent:#171717;--accent-subtle:#fff4cc;--accent-ink:#7a5800;--link:#0060d6;--ok:#1a7f37;--font:"Geist",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0a0a0a;--fg:#ededed;--muted:#b4b4b4;--line:#2e2e2e;--subtle:#111;--accent:#f5c518;--accent-subtle:#2a2208;--accent-ink:#f5c518;--link:#3291ff;--ok:#5dc36f;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:400 15px/1.55 var(--font);-webkit-font-smoothing:antialiased}
a{color:var(--link)}
:focus-visible{outline:2px solid var(--link);outline-offset:2px}
.wrap{width:100%;max-width:960px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header{border-bottom:1px solid var(--line)}
.bar{display:flex;align-items:center;gap:12px;min-height:56px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;color:var(--fg);text-decoration:none;font-weight:600}
.mark{width:32px;height:32px;border-radius:6px;background:var(--accent);color:var(--on-accent);display:grid;place-items:center;font:500 12px/1 var(--mono)}
.bar .sp{flex:1}
nav.crumbs{margin:20px 0 4px;font-size:13px;color:var(--muted)}
nav.crumbs a{color:var(--muted)}
h1{font-size:clamp(24px,5vw,32px);line-height:1.2;letter-spacing:-.02em;margin:8px 0 4px;text-wrap:balance}
h2{font-size:18px;line-height:1.3;margin:32px 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 16px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px;padding:0;list-style:none}
.badges li{border:1px solid var(--line);border-radius:9999px;padding:2px 10px;font-size:13px}
.badges .ok{color:var(--ok);border-color:currentColor}
.sample{background:var(--accent-subtle);color:var(--accent-ink);border-color:transparent!important;font-weight:500}
.price{font-size:22px;font-weight:600;margin:0 0 16px}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:8px 20px;margin:0;padding:16px;border:1px solid var(--line);border-radius:8px;background:var(--subtle)}
dl.facts dt{color:var(--muted)}
dl.facts dd{margin:0;min-width:0;overflow-wrap:anywhere}
dl.spec{display:grid;grid-template-columns:minmax(120px,max-content) 1fr;gap:0;margin:0;border-top:1px solid var(--line)}
dl.spec dt,dl.spec dd{margin:0;padding:10px 0;border-bottom:1px solid var(--line)}
dl.spec dt{color:var(--muted);padding-right:20px}
.notice{border-left:3px solid var(--accent);padding:8px 12px;margin:16px 0 0;background:var(--subtle)}
.cta{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0 0}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 20px;border-radius:6px;border:1px solid var(--line);text-decoration:none;font-weight:500;color:var(--fg)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
ul.list{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
ul.list li{border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}
ul.list a{font-weight:500;color:var(--fg);text-decoration:none}
ul.list a:hover{text-decoration:underline}
ul.list small{display:block;color:var(--muted)}
ul.plain{margin:0;padding-left:20px}
footer{margin-top:48px;padding:24px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
footer a{color:inherit}
ul.codes{list-style:none;margin:0;padding:0;display:grid;gap:6px}
ul.codes li{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
code.c{font:500 13px var(--mono);border:1px solid var(--line);border-radius:6px;padding:1px 6px;background:var(--subtle)}
.lic{color:var(--muted);font-size:13px}
nav.jump{display:flex;flex-wrap:wrap;gap:8px 16px;margin:16px 0 8px}
ul.portals{list-style:none;margin:0;padding:0;display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
ul.portals li{border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0;display:grid;gap:4px;align-content:start}
ul.portals .pn{font-weight:500;overflow-wrap:anywhere}
ul.portals .pc{color:var(--muted);font-size:13px}
ul.portals .pl{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:14px}
ul.portals .pm{display:flex;flex-wrap:wrap;gap:6px}
ul.portals .pm span{border:1px solid var(--line);border-radius:9999px;padding:0 8px;font-size:12px}
ul.portals .pm .warn{color:var(--accent-ink);background:var(--accent-subtle);border-color:transparent}
ul.portals small{color:var(--muted);font-size:12px;line-height:1.4}
.draft{border:1px dashed var(--line);border-radius:8px;padding:8px 12px;color:var(--muted);font-size:13px;margin:0 0 16px}
.prose{max-width:68ch}.prose h2{margin-top:28px}.prose p,.prose li{margin:8px 0}
@media (max-width:520px){dl.facts{grid-template-columns:1fr;gap:2px}dl.facts dd{margin-bottom:8px}dl.spec{grid-template-columns:1fr}dl.spec dt{border-bottom:0;padding-bottom:0}}
"""


def esc(s):
    return html.escape(str(s), quote=True)


def slugify(t):
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', t.lower()))


def fmt_p(n):
    return '$' + (f'{n:.2f}' if n < 100 else f'{round(n):,}')


def fmt_n(n):
    return f'{int(n):,}'


def read_app_tables():
    """Single source of truth: pull the category/domain/branch/region tables out of src/index.html."""
    s = open(os.path.join(ROOT, 'src', 'index.html'), encoding='utf-8').read()
    cats = json.loads('[' + re.search(r'var CATS = \[(.*?)\];', s).group(1) + ']')
    domains = {d[0]: d[1] for d in json.loads(re.search(r'var DOMAINS = (\[\[.*?\]\]);', s, re.S).group(1))}
    branches = {d[0]: d[1] for d in json.loads(re.search(r'var BRANCHES = (\[\[.*?\]\]);', s, re.S).group(1))}
    regions = dict(re.findall(r'(\w+): "([^"]+)"', re.search(r'var REGIONS = \{(.*?)\};', s).group(1)))
    return cats, domains, branches, regions


def load_listings():
    if os.environ.get("PAGES_SOURCE") != "seed":
        url = (SUPABASE_URL + '/rest/v1/myb_listings?select=' + COLS +
               '&status=eq.live&order=position.asc.nullslast,created_at.asc&limit=2000')
        try:
            req = urllib.request.Request(url, headers={'apikey': SUPABASE_KEY, 'Authorization': 'Bearer ' + SUPABASE_KEY})
            rows = json.load(urllib.request.urlopen(req, timeout=30))
            if rows:
                return rows, 'supabase'
            problem = 'Supabase returned no live listings'
        except Exception as e:
            problem = 'could not read listings from Supabase (%s)' % e
        if os.environ.get('PAGES_SOURCE') == 'live':
            sys.exit('ERROR: ' + problem)
        print('WARNING: %s; using supabase/seed.json' % problem, file=sys.stderr)
    return json.load(open(os.path.join(ROOT, 'supabase', 'seed.json'), encoding='utf-8')), 'seed.json'


def load_unspsc():
    rows = json.load(open(os.path.join(ROOT, 'supabase', 'unspsc.json'), encoding='utf-8'))['rows']
    return {r[0]: (r[5], r[4]) for r in rows}      # code -> (title, access)


def load_portals():
    cols = 'scope,country,region,name,url,feed_url,platform,classification,note,flag,sources,position'
    if os.environ.get('PAGES_SOURCE') != 'seed':
        url = SUPABASE_URL + '/rest/v1/myb_portals?select=' + cols + '&order=position.asc&limit=1000'
        try:
            req = urllib.request.Request(url, headers={'apikey': SUPABASE_KEY, 'Authorization': 'Bearer ' + SUPABASE_KEY})
            rows = json.load(urllib.request.urlopen(req, timeout=30))
            if rows:
                return rows, 'supabase'
            problem = 'Supabase returned no portals'
        except Exception as e:
            problem = 'could not read portals from Supabase (%s)' % e
        if os.environ.get('PAGES_SOURCE') == 'live':
            sys.exit('ERROR: ' + problem)
        print('WARNING: %s; using supabase/portals.json' % problem, file=sys.stderr)
    return json.load(open(os.path.join(ROOT, 'supabase', 'portals.json'), encoding='utf-8')), 'portals.json'


def shape(r, cats, domains, branches, regions):
    """Mirror the app's P()/fromRow() so a listing reads the same on both pages."""
    moq = int(r['moq'] or 1)
    p = float(r['price'] or 0)
    flat = r.get('flat')
    price = flat if flat else (fmt_p(p * 0.86) + '–' + fmt_p(p) + ' / ' + r['unit'])
    specs = []
    for part in (r.get('specs') or '').split('|'):
        k, _, v = part.partition(':')
        if k.strip() and v.strip():
            specs.append((k.strip(), v.strip()))
    return {
        'slug': r['slug'], 'name': r['name'], 'cat': r['category'], 'catslug': slugify(r['category']),
        'supplier': r['supplier'], 'city': r['city'], 'country': r['country'],
        'region': regions.get(r['region'], r['region']), 'price': price,
        'moq': fmt_n(moq) + ' ' + r['unit'] + ('s' if moq > 1 else ''), 'lead': r.get('lead') or '',
        'certs': r.get('certs') or [], 'ships': r['ships'], 'verified': bool(r['verified']), 'years': r['years'],
        'descr': r['descr'], 'specs': specs, 'sample': bool(r.get('is_sample')),
        'domains': [domains.get(k, k) for k in (r.get('domains') or [])],
        'branches': [branches.get(k, k) for k in (r.get('branches') or [])],
        'restricted': r['ships'] == 'Licensed buyers' or r['category'] in (cats[8], cats[9]),
        'unspsc': list(r.get('unspsc') or []),
    }


def trim(text, n=155):
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(' ', 1)[0].rstrip(',;:.') + '…'


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace('<', '\\u003c') + '</script>'


def page(site, path, title, desc, body, crumbs, og_type='website', noindex=False):
    url = site + path
    crumb_ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, **({'item': site + u} if u else {})}
        for i, (n, u) in enumerate(crumbs)]}
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>' + esc(title) + '</title><meta name="description" content="' + esc(desc) + '">'
            '<link rel="canonical" href="' + esc(url) + '">'
            '<meta property="og:type" content="' + og_type + '"><meta property="og:site_name" content="Military Yellow Book">'
            '<meta property="og:title" content="' + esc(title) + '"><meta property="og:description" content="' + esc(desc) + '">'
            '<meta property="og:url" content="' + esc(url) + '"><meta property="og:image" content="' + site + '/og.png">'
            '<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="' + esc(title) + '">'
            '<meta name="twitter:description" content="' + esc(desc) + '"><meta name="twitter:image" content="' + site + '/og.png">'
            '<meta name="theme-color" content="#f5b800">' + ('<meta name="robots" content="noindex">' if noindex else '') + '<link rel="icon" href="' + ICON + '">' + FONTS +
            '<style>' + CSS.strip() + '</style>' + jsonld(crumb_ld) + '</head><body>'
            '<header><div class="wrap bar"><a class="brand" href="/"><span class="mark" aria-hidden="true">YB</span>Military Yellow Book</a>'
            '<span class="sp"></span><a href="/directory">All listings</a></div></header>'
            '<main class="wrap">' + body + '</main>'
            '<footer><div class="wrap"><p><b>Military Yellow Book</b> is a global directory of military suppliers.</p><p>' + esc(FOOT) + '</p>'
            '<p><a href="/portals">Government procurement portals</a> · <a href="/terms">Terms</a> · <a href="/privacy">Privacy</a></p></div></footer>'
            '</body></html>')


def crumb_html(items):
    out = []
    for n, u in items:
        out.append('<a href="' + esc(u) + '">' + esc(n) + '</a>' if u else esc(n))
    return '<nav class="crumbs" aria-label="Breadcrumb">' + ' › '.join(out) + '</nav>'


def card(b):
    return ('<li><a href="/l/' + b['slug'] + '">' + esc(b['name']) + '</a><small>' + esc(b['supplier']) + ' · ' + esc(b['city']) + ', ' +
            esc(b['country']) + '</small><small>' + esc(b['price']) + ' · MOQ ' + esc(b['moq']) + '</small></li>')


def listing_page(site, b, same_cat):
    crumbs = [('Military Yellow Book', '/'), (b['cat'], '/c/' + b['catslug']), (b['supplier'], None)]
    title = f"{b['name']} by {b['supplier']}"
    if len(title) <= 46:
        title += ' | Military Yellow Book'     # keep the brand only while the title still fits a search result
    desc = trim(f"{b['name']} from {b['supplier']} in {b['city']}, {b['country']}. MOQ {b['moq']}, lead time {b['lead'] or 'on request'}. {b['descr']}")
    badges = ['<li class="ok">' + ('✓ Verified supplier' if b['verified'] else 'Not yet verified') + '</li>',
              '<li>' + esc(str(b['years'])) + ' yrs in business</li>', '<li>' + esc(b['cat']) + '</li>']
    if b['sample']:
        badges.insert(0, '<li class="sample">Sample listing: invented for demonstration</li>')
    facts = [('Minimum order', b['moq']), ('Lead time', b['lead'] or 'On request'), ('Ships to', b['ships']),
             ('Origin', b['city'] + ', ' + b['country']), ('Region', b['region'])]
    dl = ''.join('<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>' for k, v in facts)
    for label, vals in (('Domain', b['domains']), ('Branch', b['branches']), ('Features', b['certs'])):
        if vals:
            dl += '<dt>' + label + '</dt><dd>' + esc(', '.join(vals)) + '</dd>'
    spec = ('<h2>Specifications</h2><dl class="spec">' + ''.join('<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>' for k, v in b['specs']) + '</dl>') if b['specs'] else ''
    note = ('This item is export-controlled. Expect to provide a dealer licence or end-user certificate before the supplier quotes.'
            if b['restricted'] else
            'Some military goods are export-controlled. Ask the supplier which licences and end-user certificates apply to your destination before you order, and confirm price and delivery terms in writing.')
    codes = ''
    if b['unspsc']:
        lis, lic = '', False
        for c in b['unspsc']:
            t, a = UN.get(c, ('', 'open'))
            lic = lic or a == 'licensed'
            lis += '<li><code class="c">' + esc(c) + '</code>' + (esc(t) if t else '') + (' <span class="lic">· licence may apply</span>' if a == 'licensed' else '') + '</li>'
        codes = ('<h2>UNSPSC classification</h2><ul class="codes">' + lis + '</ul>' +
                 ('<p class="notice">At least one of these classes is licence-controlled. Ask the supplier which export licences and end-user certificates apply to your destination.</p>' if lic else '') +
                 '<p class="sub">UNSPSC® is the United Nations Standard Products and Services Code, used by many procurement portals to classify what is bought.</p>')
    more = [x for x in same_cat if x['slug'] != b['slug'] and x['supplier'] != b['supplier']][:6]
    more_html = ('<h2>More in ' + esc(b['cat']) + '</h2><ul class="list">' + ''.join(card(x) for x in more) + '</ul>') if more else ''
    body = (crumb_html(crumbs) + '<h1>' + esc(b['name']) + '</h1><p class="sub">' + esc(b['supplier']) + ' · ' + esc(b['city']) + ', ' + esc(b['country']) + '</p>' +
            '<ul class="badges">' + ''.join(badges) + '</ul><p class="price">' + esc(b['price']) + '</p><dl class="facts">' + dl + '</dl>' +
            '<h2>Overview</h2><p>' + esc(b['descr']) + '</p>' + spec + codes + '<h2>Shipping and compliance</h2><p class="notice">' + esc(note) + '</p>' +
            '<div class="cta"><a class="btn primary" href="/#biz-' + b['slug'] + '">Request a quote or see full details</a>'
            '<a class="btn" href="/c/' + b['catslug'] + '">More ' + esc(b['cat']) + ' suppliers</a></div>' + more_html)
    return page(site, '/l/' + b['slug'], title, desc, body, crumbs)


def category_page(site, cat, items):
    crumbs = [('Military Yellow Book', '/'), (cat, None)]
    title = f'{cat} suppliers | Military Yellow Book'
    desc = trim(f'{len(items)} {cat.lower()} suppliers in the Military Yellow Book directory, with prices, minimum orders and lead times.')
    typical = ''
    if cat in CATEGORY_UNSPSC:
        typical = ('<h2>Typical UNSPSC codes</h2><ul class="codes">' + ''.join(
            '<li><code class="c">' + esc(c) + '</code>' + esc(UN.get(c, ('', ''))[0]) + '</li>' for c in CATEGORY_UNSPSC[cat]) + '</ul>')
    body = (crumb_html(crumbs) + '<h1>' + esc(cat) + '</h1><p class="sub">' + str(len(items)) + ' listings</p><ul class="list">' +
            ''.join(card(x) for x in items) + '</ul>' + typical + '<div class="cta"><a class="btn" href="/directory">Browse every category</a></div>')
    return page(site, '/c/' + slugify(cat), title, desc, body, crumbs)


def directory_page(site, groups):
    crumbs = [('Military Yellow Book', '/'), ('All listings', None)]
    total = sum(len(v) for _, v in groups)
    body = crumb_html(crumbs) + '<h1>All listings</h1><p class="sub">' + str(total) + ' listings in ' + str(len(groups)) + ' categories</p>'
    for cat, items in groups:
        body += ('<h2><a href="/c/' + slugify(cat) + '">' + esc(cat) + '</a></h2><ul class="plain">' +
                 ''.join('<li><a href="/l/' + x['slug'] + '">' + esc(x['name']) + '</a> · ' + esc(x['supplier']) + '</li>' for x in items) + '</ul>')
    return page(site, '/directory', 'All listings | Military Yellow Book',
                trim(f'Every supplier listing in the Military Yellow Book, by category: {total} listings.'), body, crumbs)


UN = {}
REGION_NAMES = [('americas', 'Americas'), ('europe', 'Europe'), ('mideast', 'Middle East'), ('africa', 'Africa'), ('asia', 'Asia-Pacific'), (None, 'International and multilateral')]


def portals_page(site, rows):
    crumbs = [('Military Yellow Book', '/'), ('Government procurement portals', None)]
    countries = len({r['country'] for r in rows if r['scope'] == 'national'})
    nav = '<nav class="jump" aria-label="Regions">' + ''.join(
        '<a href="#' + (k or 'intl') + '">' + n + '</a>' for k, n in REGION_NAMES if any(r['region'] == k for r in rows)) + '</nav>'
    body = (crumb_html(crumbs) + '<h1>Government procurement portals</h1>'
            '<p class="sub">' + str(len(rows)) + ' places where governments and international bodies publish tenders, covering ' + str(countries) + ' countries and territories. '
            'Register as a supplier there to bid on military and defence contracts.</p>'
            '<p class="notice"><b>Check before you rely on a link.</b> This list is compiled from the sources named below and has not been verified link by link. '
            'Entries marked &ldquo;check address&rdquo; point at a general government or commercial site rather than a procurement system. '
            'The official portal is always the system of record for a government&rsquo;s tenders. Trading with some countries is restricted by sanctions and export controls: '
            'confirm what applies to you before you bid.</p>' + nav)
    for key, name in REGION_NAMES:
        grp = [r for r in rows if r['region'] == key]
        if not grp:
            continue
        lis = ''
        for r in grp:
            links = ''
            if r['url']:
                links += '<a href="' + esc(r['url']) + '" rel="nofollow noopener noreferrer" target="_blank">Official site</a>'
            if r['feed_url']:
                links += '<a href="' + esc(r['feed_url']) + '" rel="nofollow noopener noreferrer" target="_blank">Tender feed (Open Opps)</a>'
            meta = ''
            if r['scope'] == 'subnational':
                meta += '<span>Regional or state</span>'
            if r['scope'] == 'agency':
                meta += '<span>Agency catalogue</span>'
            if r['platform']:
                meta += '<span>' + esc(r['platform'].capitalize()) + '</span>'
            if r['classification']:
                meta += '<span>Codes: ' + esc(r['classification']) + '</span>'
            if r['flag'] == 'general_site':
                meta += '<span class="warn">Check address</span>'
            if r['flag'] == 'no_url':
                meta += '<span class="warn">No portal listed</span>'
            lis += ('<li><span class="pn">' + esc(r['name']) + '</span><span class="pc">' + esc(r['country']) + '</span>' +
                    ('<span class="pl">' + links + '</span>' if links else '') + ('<span class="pm">' + meta + '</span>' if meta else '') +
                    ('<small>' + esc(r['note']) + '</small>' if r['note'] else '') + '</li>')
        body += '<h2 id="' + (key or 'intl') + '">' + name + ' <small class="lic">(' + str(len(grp)) + ')</small></h2><ul class="portals">' + lis + '</ul>'
    body += ('<h2>Which product codes do portals want?</h2><p>Many portals ask suppliers to classify what they sell: the US uses NAICS and PSC, the EU and UK use CPV, and '
             'UNGM, Australia, New Zealand and Canada use UNSPSC. Every listing in this directory carries UNSPSC codes, so you can reuse them when you register.</p>'
             '<h2>Sources</h2><ul class="plain">'
             '<li>Sell to State, <a href="https://www.selltostate.com/guides/global-government-procurement-portals/" rel="noopener noreferrer" target="_blank">Government Procurement Portals by Country</a> (updated 30 June 2026): one portal for each of 193 countries.</li>'
             '<li>Open Opportunities, <a href="https://openopps.com/sources/" rel="noopener noreferrer" target="_blank">sources</a>: regional, state and international tender sources, linked as feeds.</li>'
             '<li>Inter-American Network on Government Procurement (RICG), <a href="https://ricg.org/en/regional-e-gp-inventory" rel="noopener noreferrer" target="_blank">Regional e-GP inventory</a>: platform type for Latin American and Caribbean systems.</li>'
             '<li>US Department of Veterans Affairs, <a href="https://www.vendorportal.ecms.va.gov/nac" rel="noopener noreferrer" target="_blank">National Acquisition Center contract catalogue</a>.</li>'
             '</ul>')
    return page(site, '/portals', 'Government procurement portals by country | Military Yellow Book',
                trim(f'{len(rows)} government and international procurement portals in {countries} countries, with the product code systems they use. Where to register to sell to defence buyers.'),
                body, crumbs)


LEGAL_DRAFT = True      # set False once a lawyer has reviewed terms and privacy text
CONTACT = os.environ.get('SITE_CONTACT', '').strip()


def legal_page(site, path, title, desc, sections):
    crumbs = [('Military Yellow Book', '/'), (title, None)]
    body = crumb_html(crumbs) + '<h1>' + esc(title) + '</h1><p class="sub">Last updated 3 November 2026</p>'
    if LEGAL_DRAFT:
        body += '<p class="draft">Draft: this text has not yet been reviewed by a lawyer and may change before launch.</p>'
    body += '<div class="prose">'
    for h, paras in sections:
        body += '<h2>' + esc(h) + '</h2>' + ''.join(p if p.startswith('<') else '<p>' + esc(p) + '</p>' for p in paras)
    if CONTACT:
        body += '<h2>Contact</h2><p>' + esc(CONTACT) + '</p>'
    body += '</div>'
    return page(site, path, title + ' | Military Yellow Book', desc, body, crumbs)


def terms_page(site):
    return legal_page(site, '/terms', 'Terms of use', 'The rules for using the Military Yellow Book directory.', [
        ('What this site is', ['The Military Yellow Book is a directory. It helps buyers find suppliers and helps suppliers be found. We do not sell goods, take payments, hold stock or ship orders, and we are not a party to any deal between a buyer and a supplier.',
                               'Listings marked as samples are invented for demonstration. Do not treat a sample listing as a real business.']),
        ('What we list', ['We do not list complete firearms, ammunition, explosives, weapon systems, ballistic armour, or night-vision and thermal imaging equipment, and we remove listings that offer them. Weapon accessories, aircraft parts and similar items are shown as sold to licensed buyers only.',
                          'Listings are classified with UNSPSC codes. We reject codes for the categories above.']),
        ('Your responsibilities', ['You are responsible for complying with export-control, sanctions, import and licensing rules that apply to anything you buy, sell or ship. A listing, quote or review on this site is not a licence or legal advice.',
                                   'Give accurate information. Do not use the site to list or request anything illegal, to impersonate a business, or to harvest other people’s contact details.']),
        ('Accounts and content', ['You need an account to request quotes, list a business, save items and write reviews. Keep your password private. You are responsible for what you submit.',
                                  'By submitting a review or a business listing you let us display it on the site. We may remove content that breaks these terms. A “Verified” badge means we checked the supplier against the steps we describe on the site; it is not a guarantee.']),
        ('No guarantees', ['Prices, lead times and specifications are set by suppliers. Check terms in writing before you pay. The site is provided as it is, without warranties, and to the extent the law allows we are not liable for losses from deals made through it.']),
        ('Changes', ['We may change these terms or the site. Continuing to use the site after a change means you accept the new terms.']),
    ])


def privacy_page(site):
    return legal_page(site, '/privacy', 'Privacy policy', 'What the Military Yellow Book collects, why, and who handles it.', [
        ('What we collect', ['<ul class="plain"><li><b>Account:</b> your name, email address, country, account type (buyer or supplier) and a password, which is stored only as a hash.</li>'
                             '<li><b>What you do on the site:</b> quote requests (product, quantity, target price, delivery destination, your name and contact), supplier submissions (business details, phone, email, website, product codes), saved items and reviews.</li>'
                             '<li><b>On your device:</b> your saved items, chosen language and shipping destination, and a sign-in session. We use no advertising or analytics cookies.</li></ul>']),
        ('Why we use it', ['To run your account, send you the confirmation and password-reset emails you ask for, pass your quote requests to suppliers, review business submissions, show your reviews, and keep the site secure and within usage limits.']),
        ('What is public', ['Business listings are public once approved. A review shows your display name and the rating and text you write. The review also records an identifier for your account, which can be read by anyone using the site’s public interface.']),
        ('Who handles your data', ['<ul class="plain"><li><b>Supabase</b> stores accounts and site data and sends authentication emails. The account system is shared with another product run by the same operator, so a sign-up here also creates a profile record there.</li>'
                                   '<li><b>Vercel</b> hosts the site.</li>'
                                   '<li><b>Google Fonts</b> serves the typeface, so your browser contacts Google when a page loads.</li></ul>',
                                   'We do not sell your data.']),
        ('Keeping and deleting it', ['We keep your account and what you submitted until you ask us to delete it. To see, correct or delete your data, contact us ' + ('at the address below' if CONTACT else 'through the site operator') + '. Quote requests you have already sent to a supplier cannot be recalled from the supplier.']),
        ('Children', ['The site is for businesses and professional buyers and is not meant for anyone under 18.']),
        ('Changes', ['If we change this policy we will update this page and the date above.']),
    ])


def not_found_page(site):
    crumbs = [('Military Yellow Book', '/')]
    body = ('<h1>Page not found</h1><p class="sub">That address does not match a page on the Military Yellow Book.</p>'
            '<div class="cta"><a class="btn primary" href="/">Search the directory</a><a class="btn" href="/directory">Browse every category</a>'
            '<a class="btn" href="/portals">Government procurement portals</a></div>')
    return page(site, '/404', 'Page not found | Military Yellow Book', 'Page not found.', body, crumbs, noindex=True)


def build(site_url, out_dir=None):
    site = site_url.rstrip('/')
    out = out_dir or os.path.join(ROOT, 'site')
    cats, domains, branches, regions = read_app_tables()
    rows, source = load_listings()
    UN.update(load_unspsc())
    if source == 'seed.json':      # the seed file predates the classification: take codes from the reviewed mapping
        tags = json.load(open(os.path.join(ROOT, 'supabase', 'listing_unspsc.json'), encoding='utf-8'))
        for r in rows:
            r.setdefault('unspsc', tags.get(r['slug'], []))
    portals, psource = load_portals()
    listings, seen = [], set()
    for r in rows:
        if not SLUG_OK.match(str(r.get('slug', ''))) or r['slug'] in seen:
            print('WARNING: skipping listing with unusable slug:', r.get('slug'), file=sys.stderr)
            continue
        seen.add(r['slug'])
        listings.append(shape(r, cats, domains, branches, regions))
    by_cat = {c: [b for b in listings if b['cat'] == c] for c in cats}
    for b in listings:
        if b['cat'] not in by_cat:      # a category added in the database but not yet in the app
            by_cat[b['cat']] = [x for x in listings if x['cat'] == b['cat']]
    groups = [(c, v) for c, v in by_cat.items() if v]

    for sub in ('l', 'c'):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
        os.makedirs(os.path.join(out, sub))
    for b in listings:
        open(os.path.join(out, 'l', b['slug'] + '.html'), 'w', encoding='utf-8').write(listing_page(site, b, by_cat[b['cat']]))
    for c, v in groups:
        open(os.path.join(out, 'c', slugify(c) + '.html'), 'w', encoding='utf-8').write(category_page(site, c, v))
    open(os.path.join(out, 'directory.html'), 'w', encoding='utf-8').write(directory_page(site, groups))
    open(os.path.join(out, 'portals.html'), 'w', encoding='utf-8').write(portals_page(site, portals))
    open(os.path.join(out, 'terms.html'), 'w', encoding='utf-8').write(terms_page(site))
    open(os.path.join(out, 'privacy.html'), 'w', encoding='utf-8').write(privacy_page(site))
    open(os.path.join(out, '404.html'), 'w', encoding='utf-8').write(not_found_page(site))

    urls = ['/', '/directory', '/portals', '/terms', '/privacy'] + ['/c/' + slugify(c) for c, _ in groups] + ['/l/' + b['slug'] for b in listings]
    open(os.path.join(out, 'sitemap.xml'), 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        ''.join('<url><loc>' + esc(site + u) + '</loc></url>\n' for u in urls) + '</urlset>\n')
    open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8').write('User-agent: *\nAllow: /\n\nSitemap: ' + site + '/sitemap.xml\n')
    print(f'pages: {len(listings)} listings + {len(groups)} categories + directory + portals ({len(portals)}) + terms + privacy + 404 + sitemap ({len(urls)} URLs), sources: {source}, {psource}')
    return urls


if __name__ == '__main__':
    build(os.environ.get('SITE_URL', 'https://military-yellow-book.vercel.app'))
