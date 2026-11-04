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
COLS = ('slug,name,category,supplier,city,state,country,region,unit,price,moq,lead,certs,ships,verified,years,descr,specs,'
        'domains,branches,is_sample,status,position,created_at,unspsc')
SLUG_OK = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">'
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
        "fill='%23f5b800'/%3E%3Ctext x='16' y='22' font-family='Arial' font-weight='700' font-size='15' text-anchor='middle' "
        "fill='%23171717'%3EYB%3C/text%3E%3C/svg%3E")
FOOT = ('Complete firearms, ammunition, explosives and weapon systems are not listed. Weapon parts, aircraft parts and '
        'body-armor carriers are sold only by licensed dealers and need export licences and end-user certificates. '
        'Prices and lead times are set by each supplier; confirm terms in writing before you pay.')

LCSS = """
.lg{--fg:var(--text);--muted:var(--text-2);--line:var(--border);--subtle:var(--surface);--subtle-2:var(--surface-2);max-width:1040px;padding-top:var(--s-4)}
.lg.nt h1{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}\n.lg h1{font-size:var(--fs-xl);line-height:1.25;font-weight:600;letter-spacing:-.02em;margin:var(--s-2) 0 var(--s-1);text-wrap:balance}
.lg h2{font-size:var(--fs-md);line-height:1.3;font-weight:600;letter-spacing:-.01em;margin:var(--s-8) 0 var(--s-3)}
.lg h3{font-size:var(--fs);line-height:1.3;font-weight:600;margin:var(--s-6) 0 var(--s-2)}
.lg a{color:var(--link)}
.lg h2 a{color:var(--text);text-decoration:none}
.lg h2 a:hover{text-decoration:underline}
.lg nav.crumbs{margin:0 0 var(--s-2);font-size:var(--fs-sm);color:var(--text-2)}
.lg nav.crumbs a{color:var(--text-2);text-decoration:none}
.lg nav.crumbs a:hover{text-decoration:underline}
.lg .sub{color:var(--text-2);margin:0 0 var(--s-4);max-width:62ch}
.lg .badges{display:flex;flex-wrap:wrap;gap:var(--s-2);margin:0 0 var(--s-5);padding:0;list-style:none}
.lg .badges li{border-radius:var(--r-full);padding:2px 10px;font-size:var(--fs-sm);background:var(--surface-2);color:var(--text)}
.lg .badges .ok{color:var(--ok);background:var(--ok-subtle)}
.lg .badges .sample{background:var(--accent-subtle);color:var(--accent-ink);font-weight:500}
.lg .price{font-size:var(--fs-lg);font-weight:600;margin:0 0 var(--s-4)}
.lg dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:var(--s-2) var(--s-5);margin:0;padding:var(--s-4) var(--s-5);border-radius:var(--r-lg);background:var(--surface)}
.lg dl.facts dt{color:var(--text-2)}
.lg dl.facts dd{margin:0;min-width:0;overflow-wrap:anywhere}
.lg dl.spec{display:grid;grid-template-columns:minmax(120px,max-content) 1fr;margin:0;border-top:1px solid var(--border)}
.lg dl.spec dt,.lg dl.spec dd{margin:0;padding:var(--s-2) 0;border-bottom:1px solid var(--border)}
.lg dl.spec dt{color:var(--text-2);padding-right:var(--s-5)}
.lg .notice{border-radius:var(--r-lg);background:var(--surface);padding:var(--s-3) var(--s-4);margin:var(--s-4) 0 0}
.lg .cta{display:flex;flex-wrap:wrap;gap:var(--s-3);margin:var(--s-5) 0 0}
.lg .btn{display:inline-flex;align-items:center;justify-content:center;height:var(--ctl-lg);padding:0 var(--s-4);border-radius:var(--r);background:var(--surface-2);color:var(--text);text-decoration:none;font-weight:500}
.lg .btn:hover{background:var(--surface-3)}
.lg .btn.primary{background:var(--text);color:var(--bg)}
.lg ul.list,.lg ul.portals,.lg ul.opps{list-style:none;margin:0;padding:0;display:grid;gap:var(--s-3)}
.lg ul.list{grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.lg ul.list li{border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-3) var(--s-4);min-width:0}
.lg ul.list li:hover{background:var(--surface)}
.lg ul.list a{font-weight:600;color:var(--text);text-decoration:none}
.lg ul.list a:hover{text-decoration:underline}
.lg ul.list small{display:block;color:var(--text-2)}
.lg ul.plain{margin:0;padding-left:var(--s-5)}
.lg ul.codes{list-style:none;margin:0;padding:0;display:grid;gap:var(--s-2)}
.lg ul.codes li{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.lg code.c{font:500 var(--fs-sm) var(--mono);border-radius:var(--r);padding:1px 6px;background:var(--surface-2)}
.lg .lic{color:var(--text-2);font-size:var(--fs-sm)}
.lg nav.jump{display:flex;flex-wrap:wrap;gap:var(--s-2);margin:var(--s-4) 0 var(--s-2)}
.lg nav.jump a{text-decoration:none;font-weight:500;color:var(--text);background:var(--surface-2);padding:2px 10px;border-radius:var(--r)}
.lg nav.jump a:hover{background:var(--surface-3)}
.lg ol.steps{margin:0;padding-left:22px}.lg ol.steps li{margin:6px 0}
.lg .draft{border:1px dashed var(--border-strong);border-radius:var(--r-lg);padding:var(--s-2) var(--s-3);color:var(--text-2);font-size:var(--fs-sm);margin:0 0 var(--s-4)}
.lg .prose{max-width:68ch}.lg .prose p,.lg .prose li{margin:var(--s-2) 0}
.lg .cards{display:grid;gap:var(--s-3);grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));margin-top:var(--s-5)}
.lg .cc{border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-4) var(--s-5);min-width:0}
.lg .cc h2{margin:0;font-size:var(--fs-md);line-height:1.3}
.lg .cc .cn{margin:2px 0 var(--s-3);color:var(--text-2);font-size:var(--fs-sm)}
.lg .cc ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--s-2)}
.lg .cc li{display:grid;min-width:0}
.lg .cc li a{text-decoration:none;font-weight:500;color:var(--text);overflow-wrap:anywhere}
.lg .cc li a:hover{text-decoration:underline}
.lg .cc li small{color:var(--text-2);font-size:var(--fs-sm)}
@media (max-width:520px){.lg dl.facts{grid-template-columns:1fr;gap:2px}.lg dl.facts dd{margin-bottom:var(--s-2)}.lg dl.spec{grid-template-columns:1fr}.lg dl.spec dt{border-bottom:0;padding-bottom:0}}
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


OPP_COLS = 'id,kind,source_id,title,buyer,supplier,country,country_name,amount,currency,published_at,deadline,url,publisher,licence,refreshed_at'


def load_opportunities():
    """Published by procurement.publish_opportunities(): only operational, licence-cleared sources."""
    if os.environ.get('PAGES_SOURCE') != 'seed':
        url = SUPABASE_URL + '/rest/v1/myb_opportunities?select=' + OPP_COLS + '&limit=5000'
        try:
            req = urllib.request.Request(url, headers={'apikey': SUPABASE_KEY, 'Authorization': 'Bearer ' + SUPABASE_KEY})
            rows = json.load(urllib.request.urlopen(req, timeout=30))
            return rows, 'supabase'
        except Exception as e:
            if os.environ.get('PAGES_SOURCE') == 'live':
                sys.exit('ERROR: could not read opportunities (%s)' % e)
            print('WARNING: could not read opportunities (%s); using supabase/opportunities.json' % e, file=sys.stderr)
    f = os.path.join(ROOT, 'supabase', 'opportunities.json')
    return (json.load(open(f, encoding='utf-8')) if os.path.exists(f) else []), 'opportunities.json'


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
        'supplier': r['supplier'], 'city': r['city'], 'state': r.get('state') or '', 'country': r['country'],
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
    """Content page (listing, category, directory, legal, 404): the same shell as every other page."""
    section = 'discover' if path.startswith(('/l/', '/c/', '/directory')) else ''
    return wpage(site, path, title, desc, section, None, '', None, '<div class="lg' + ('' if path.startswith('/l/') else ' nt') + '">' + body + '</div>', crumbs,
                 og_type=og_type, noindex=noindex, extra_css=LCSS)


def crumb_html(items):
    out = []
    for n, u in items:
        out.append('<a href="' + esc(u) + '">' + esc(n) + '</a>' if u else esc(n))
    return '<nav class="crumbs" aria-label="Breadcrumb">' + ' › '.join(out) + '</nav>'


def loc(b):
    return ', '.join(x for x in (b['city'], b.get('state'), b['country']) if x)


def card(b):
    return ('<li><a href="/l/' + b['slug'] + '">' + esc(b['name']) + '</a><small>' + esc(b['supplier']) + ' · ' + esc(loc(b)) + '</small><small>' + esc(b['price']) + ' · MOQ ' + esc(b['moq']) + '</small></li>')


def listing_page(site, b, same_cat):
    crumbs = [('Military Yellow Book', '/'), (b['cat'], '/c/' + b['catslug']), (b['supplier'], None)]
    title = f"{b['name']} by {b['supplier']}"
    if len(title) <= 46:
        title += ' | Military Yellow Book'     # keep the brand only while the title still fits a search result
    desc = trim(f"{b['name']} from {b['supplier']} in {loc(b)}. MOQ {b['moq']}, lead time {b['lead'] or 'on request'}. {b['descr']}")
    badges = ['<li class="ok">' + ('✓ Verified supplier' if b['verified'] else 'Not yet verified') + '</li>',
              '<li>' + esc(str(b['years'])) + ' yrs in business</li>', '<li>' + esc(b['cat']) + '</li>']
    if b['sample']:
        badges.insert(0, '<li class="sample">Sample listing: invented for demonstration</li>')
    facts = [('Minimum order', b['moq']), ('Lead time', b['lead'] or 'On request'), ('Ships to', b['ships']),
             ('Origin', loc(b)), ('Region', b['region'])]
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
    body = (crumb_html(crumbs) + '<h1>' + esc(b['name']) + '</h1><p class="sub">' + esc(b['supplier']) + ' · ' + esc(', '.join(x for x in (b['city'], b.get('state'), b['country']) if x)) + '</p>' +
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
    body += '<div class="cards">'
    for cat, items in groups:
        body += ('<section class="cc"><h2><a href="/c/' + slugify(cat) + '">' + esc(cat) + ' <span aria-hidden="true">→</span></a></h2>'
                 '<p class="cn">' + str(len(items)) + ' listing' + ('' if len(items) == 1 else 's') + '</p><ul>' +
                 ''.join('<li><a href="/l/' + x['slug'] + '">' + esc(x['name']) + '</a><small>' + esc(x['supplier']) + '</small></li>' for x in items) + '</ul></section>')
    body += '</div>'
    return page(site, '/directory', 'All listings | Military Yellow Book',
                trim(f'Every supplier listing in the Military Yellow Book, by category: {total} listings.'), body, crumbs)


UN = {}
REGION_NAMES = [('americas', 'Americas'), ('europe', 'Europe'), ('mideast', 'Middle East'), ('africa', 'Africa'), ('asia', 'Asia-Pacific'), (None, 'International and multilateral')]


SOURCE_NAMES = {'uk_fts': ('UK Find a Tender', 'https://www.find-tender.service.gov.uk/'), 'uk_cf': ('UK Contracts Finder', 'https://www.contractsfinder.service.gov.uk/'),
                'worldbank_procurement': ('World Bank procurement notices', 'https://projects.worldbank.org/en/projects-operations/procurement'),
                'colombia_secop': ('Colombia SECOP II (datos.gov.co)', 'https://www.datos.gov.co/d/jbjy-vk9h'),
                'ted': ('EU TED', 'https://ted.europa.eu/'), 'brazil_pncp': ('Brazil PNCP', 'https://pncp.gov.br/'), 'usaspending': ('USAspending.gov', 'https://www.usaspending.gov/')}


def fmt_money(amount, cur):
    if amount in (None, ''):
        return None
    a = float(amount)
    txt = ('%.1fbn' % (a / 1e9)) if a >= 1e9 else ('%.1fm' % (a / 1e6)) if a >= 1e6 else ('{:,.0f}'.format(a))
    return (cur or '') + ' ' + txt


def fmt_date(ts):
    import datetime as _d
    if not ts:
        return None
    d = _d.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    return d.strftime('%-d %b %Y'), d


ICONS = {
    'search': '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/>',
    'heart': '<path d="M8 13.5S2.5 10 2.5 6.2A2.9 2.9 0 0 1 8 5a2.9 2.9 0 0 1 5.5 1.2C13.5 10 8 13.5 8 13.5z"/>',
    'doc': '<path d="M4 2.5h5.5L12 5v8.5H4z"/><path d="M9.5 2.5V5H12M6 8h4M6 10.5h4"/>',
    'award': '<circle cx="8" cy="6.5" r="3.5"/><path d="M6 9.5L5 14l3-1.5 3 1.5-1-4.5"/>',
    'globe': '<circle cx="8" cy="8" r="5.5"/><path d="M2.5 8h11M8 2.5c2 1.8 2 9.2 0 11M8 2.5c-2 1.8-2 9.2 0 11"/>',
    'plus': '<path d="M8 3v10M3 8h10"/>',
    'file': '<path d="M4 2.5h5.5L12 5v8.5H4z"/><path d="M9.5 2.5V5H12"/>',
    'panel': '<rect x="2" y="2.5" width="12" height="11" rx="2"/><path d="M6 2.5v11"/>',
    'x': '<path d="M4 4l8 8M12 4l-8 8"/>',
}


def ico(n):
    return '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[n] + '</svg>'


def side_item(href, icon, label, section, cur):
    return '<a class="side-item" href="' + href + '"' + (' aria-current="page"' if section == cur else '') + '>' + ico(icon) + '<span class="si-l">' + label + '</span></a>'


def wpage(site, path, title, desc, section, heading, meta, filters, body, crumbs, og_type='website', noindex=False, extra_css=''):
    """Workspace page: the same shell as the supplier directory (top bar, sidebar, one filter row)."""
    url = site + path
    crumb_ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, **({'item': site + u} if u else {})} for i, (n, u) in enumerate(crumbs)]}
    top = ('<a class="skip" href="#main">Skip to content</a>'
           '<header class="topbar" id="nav"><div class="topbar-in">'
           '<button class="icon-btn side-toggle" id="btn-side" type="button" aria-controls="sidebar" aria-expanded="true" aria-label="Show or hide the sidebar">' + ico('panel') + '</button>'
           '<a class="brand" href="/" aria-label="Military Yellow Book home"><span class="mark" aria-hidden="true">YB</span><span class="brand-name">Military Yellow Book</span></a>'
           '<div class="gsearch" role="search"><label class="sr" for="q">Search suppliers, products or codes</label>' + ico('search').replace('<svg ', '<svg class="gs-i" ') +
           '<input id="q" type="search" placeholder="Search suppliers, products or codes" autocomplete="off" enterkeyhint="search"><span class="gs-k" aria-hidden="true"><kbd id="kbd-mod">Ctrl</kbd><kbd>K</kbd></span></div>'
           '<div class="top-actions"><a class="top-cta" href="/?list=1" aria-label="List your business">' + ico('plus') + '<span class="lbl">List your business</span></a><a class="top-btn" href="/?saved=1" aria-label="Saved">' + ico('heart') + '<span class="lbl">Saved</span></a><a class="top-btn" href="/?signin=1"><span>Sign in</span></a></div></div></header>')
    side = ('<aside class="sidebar" id="sidebar" aria-label="Workspace"><div class="sidebar-in">'
            '<div class="side-head"><span class="brand"><span class="mark" aria-hidden="true">YB</span>Military Yellow Book</span><button class="icon-btn" type="button" data-side-close aria-label="Close menu">' + ico('x') + '</button></div>'
            '<nav class="side-group" aria-label="Suppliers">' + side_item('/', 'search', 'Discover suppliers', 'discover', section) + side_item('/?saved=1', 'heart', 'Saved suppliers', 'saved', section) +
            '<a class="side-item" href="/directory">' + ico('doc') + '<span class="si-l">All listings (plain pages)</span></a></nav>'
            '<nav class="side-group" aria-labelledby="sl-proc"><div class="side-label" id="sl-proc">Procurement</div>' +
            side_item('/opportunities', 'doc', 'Tenders', 'tenders', section) + side_item('/awards', 'award', 'Contract awards', 'awards', section) + side_item('/portals', 'globe', 'Procurement portals', 'portals', section) + '</nav>'
            '<nav class="side-group" aria-labelledby="sl-biz"><div class="side-label" id="sl-biz">Account and business</div>'
            '<a class="side-item side-mob" href="/?list=1">' + ico('plus') + '<span class="si-l">List your business</span></a>'
            '<a class="side-item" href="/?rfq=1">' + ico('file') + '<span class="si-l">Request a quote</span></a>'
            '<a class="side-item" href="/?ship=1">' + ico('globe') + '<span class="si-l">Ship to</span></a>'
            '<a class="side-item" href="/?lang=1">' + ico('globe') + '<span class="si-l">Language</span></a></nav></div></aside>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>' + esc(title) + '</title><meta name="description" content="' + esc(desc) + '">'
            '<link rel="canonical" href="' + esc(url) + '">'
            '<meta property="og:type" content="' + og_type + '"><meta property="og:site_name" content="Military Yellow Book">'
            '<meta property="og:title" content="' + esc(title) + '"><meta property="og:description" content="' + esc(desc) + '">'
            '<meta property="og:url" content="' + esc(url) + '"><meta property="og:image" content="' + site + '/og.png">'
            '<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="' + esc(title) + '"><meta name="twitter:description" content="' + esc(desc) + '"><meta name="twitter:image" content="' + site + '/og.png">'
            '<meta name="theme-color" content="#f5b800">' + ('<meta name="robots" content="noindex">' if noindex else '') + '<link rel="icon" href="' + ICON + '">' + FONTS + '<link rel="stylesheet" href="/assets/ui.css">' +
            '<style>.wsx{padding:0 var(--s-6) var(--s-10)}@media(max-width:759px){.wsx{padding:0 var(--s-4) var(--s-8)}}.wsx p{max-width:72ch}.tbl td.wrapc{overflow-wrap:break-word}@media(max-width:1399px){.tbl th,.tbl td{padding-inline:6px}.tbl td.nw,.tbl td.n,.tbl th{white-space:normal}.tbl .badge{white-space:normal}}@media(min-width:1400px){.tbl td.wrapc{min-width:150px}.tbl td{min-width:90px}.tbl td[data-k=title]{min-width:240px}}.tbl .badge{white-space:nowrap}.tbl a.t-main:hover{text-decoration:underline}.tbl a.t-main{text-decoration:none}@media(max-width:759px){.tbl td,.tbl td.wrapc,.tbl td[data-k=title]{min-width:0}}.ws-note{margin:var(--s-4) 0}.tbl a.t-main{font-weight:500}.ws-foot{margin-top:var(--s-8)}' + extra_css + '</style>' + jsonld(crumb_ld) + '</head><body>' +
            top + '<div class="shell">' + side + '<div class="main">' + (filters or '') +
            '<main class="content wsx" id="main">' + ('<div class="page-head sr"><h1>' + heading + '</h1><span class="meta" id="tcount" role="status" aria-live="polite">' + meta + '</span></div>' if heading else '') + body +
            '<footer class="site-foot ws-foot"><p><b>Military Yellow Book</b> is a global directory of military suppliers. ' + esc(FOOT) + '</p>'
            '<nav aria-label="Footer"><a href="/directory">Directory</a> · <a href="/opportunities">Tenders</a> · <a href="/awards">Contract awards</a> · <a href="/portals">Procurement portals</a> · <a href="/terms">Terms</a> · <a href="/privacy">Privacy</a></nav></footer>'
            '</main></div></div><div class="side-scrim" id="side-scrim" hidden></div><script src="/assets/table.js"></script></body></html>')


def fbar(selects, placeholder):
    """The single filter row: search-in-table, filter selects, active chips."""
    s = ''.join('<label class="fsel"><span class="sr">' + esc(lbl) + '</span><select data-filter="' + k + '" aria-label="' + esc(lbl) + '"><option value="">' + esc(lbl) + '</option>' +
                ''.join('<option value="' + esc(v) + '">' + esc(t) + '</option>' for v, t in opts) + '</select></label>' for k, lbl, opts in selects)
    return ('<div class="filterbar" role="region" aria-label="Filters and sorting"><div class="filterbar-in">'
            '<label class="sr" for="tq">' + esc(placeholder) + '</label><input class="input" id="tq" type="search" placeholder="' + esc(placeholder) + '" autocomplete="off" style="flex:0 0 auto;width:min(280px,60vw)">' + s + '</div></div>')


def th(label, key=None, num=False, cls=''):
    inner = '<button type="button" data-sort="' + key + '"' + (' data-type="num"' if num else '') + '>' + esc(label) + '</button>' if key else esc(label)
    return '<th scope="col" class="' + cls + '"' + (' aria-sort="none"' if key else '') + '>' + inner + '</th>'


def src_link(r):
    name = SOURCE_NAMES.get(r['source_id'], (r.get('publisher') or r['source_id'], None))[0]
    return '<a href="' + esc(r['url']) + '" rel="nofollow noopener noreferrer" target="_blank">' + esc(name) + '<span class="sr"> (opens the official notice)</span></a>'


def iso_day(ts):
    return (ts or '')[:10]


def tenders_page(site, rows, portals):
    crumbs = [('Military Yellow Book', '/'), ('Tenders', None)]
    tenders = [r for r in rows if r['kind'] == 'open_tender']
    awards = [r for r in rows if r['kind'] == 'award']
    fresh = max((r['refreshed_at'] for r in rows), default=None)
    countries = sorted({r.get('country_name') or 'Not stated' for r in tenders})
    srcs = sorted({r['source_id'] for r in tenders})
    flt = fbar([('country', 'Country', [(c, c) for c in countries]),
                ('source', 'Source', [(s, SOURCE_NAMES.get(s, (s,))[0]) for s in srcs]),
                ('open', 'Status', [('open', 'Open'), ('closed', 'Closed')])], 'Search tenders')
    trs = ''
    for r in sorted(tenders, key=lambda r: (r['deadline'] is None, r['deadline'] or '', r['title'] or '')):
        c = r.get('country_name') or 'Not stated'
        m = fmt_money(r.get('amount'), r.get('currency'))
        pub = fmt_date(r['published_at'])[0] if r.get('published_at') else ''
        dl = fmt_date(r['deadline'])[0] if r.get('deadline') else ''
        hay = ' '.join(str(x or '') for x in (r['title'], r.get('buyer'), c, r.get('currency'), SOURCE_NAMES.get(r['source_id'], ('',))[0])).lower()
        trs += ('<tr data-s="' + esc(hay) + '" data-deadline="' + esc(r.get('deadline') or '') + '" data-f-country="' + esc(c) + '" data-f-source="' + esc(r['source_id']) + '">'
                '<td data-k="title" data-v="' + esc((r['title'] or '').lower()) + '" data-l="Tender"><a class="t-main" href="' + esc(r['url']) + '" rel="nofollow noopener noreferrer" target="_blank">' + esc(r['title']) + '</a></td>'
                '<td class="wrapc" data-k="buyer" data-v="' + esc((r.get('buyer') or '').lower()) + '" data-l="Buyer">' + esc(r.get('buyer') or 'Not stated') + '</td>'
                '<td data-k="country" data-v="' + esc(c) + '" data-l="Country">' + esc(c) + '</td>'
                '<td class="n" data-k="value" data-v="' + ('' if r.get('amount') in (None, '') else str(float(r['amount']))) + '" data-l="Value">' + (esc(m) if m else '<span class="muted">Not stated</span>') + '</td>'
                '<td class="n" data-k="pub" data-v="' + iso_day(r.get('published_at')) + '" data-l="Published">' + esc(pub) + '</td>'
                '<td class="n" data-k="close" data-v="' + iso_day(r.get('deadline')) + '" data-l="Closes">' + (esc(dl) if dl else '<span class="muted">See notice</span>') + '</td>'
                '<td data-status data-l="Status"></td>'
                '<td data-l="Official source">' + src_link(r) + '</td></tr>')
    table = ('<div class="tbl-wrap"><table class="tbl stack" data-table data-sort="close:asc"><caption class="sr">Open government tenders</caption><thead><tr>' +
             th('Tender', 'title') + th('Buyer', 'buyer') + th('Country', 'country') + th('Value', 'value', True, 'n') + th('Published', 'pub', False, 'n') + th('Closes', 'close', False, 'n') + th('Status') + th('Official source') +
             '</tr></thead><tbody>' + trs + '</tbody></table></div>'
             '<div class="state" id="tempty" hidden role="status"><h2>No tenders match</h2><p>Remove a filter or search for a different word. Tenders only appear here when an official publisher supplies them.</p></div>'
             '<div class="more"><button class="btn btn-secondary" id="tmore" type="button" hidden>Show more</button></div>')
    note = ('<div class="callout ws-note"><div>Every row links to the original notice on the publisher&rsquo;s site: eligibility, lots and the exact deadline are only valid there. Bid through the publisher, never through this site. '
            'Values are in the publisher&rsquo;s currency and are not converted. A blank value or date means the publisher did not state it. The status is worked out from the stated deadline when you open the page. '
            'Procurement categories are not yet supplied by these sources, so there is no category column. ' +
            ('Data refreshed ' + esc(fmt_date(fresh)[0]) + '. ' if fresh else '') + 'Sources are listed at the foot of the page. Need to register to bid? See the <a href="/portals">procurement portals</a>.</div></div>')
    srcs_all = sorted({r['source_id'] for r in rows})
    foot = ('<h2 class="ws-h">Where this comes from</h2><p>Each source is fetched by a tested connector, checked record by record against the publisher, and has a licence that allows reuse. Natural persons are never shown as suppliers.</p><ul class="plain">' +
            ''.join('<li><a href="' + esc(u) + '" rel="noopener noreferrer" target="_blank">' + esc(n) + '</a></li>' for n, u in (SOURCE_NAMES[x] for x in srcs_all if x in SOURCE_NAMES)) + '</ul>'
            '<div class="callout"><div>Coming next: EU TED, Brazil PNCP and USAspending already pass the record checks and will appear once their reuse licences are confirmed; SAM.gov and ChileCompra need API credentials. Confirm sanctions and export-control rules before you bid.</div></div>')
    return wpage(site, '/opportunities', 'Government tenders: search open procurement notices | Military Yellow Book',
                 trim('%d open government tenders from official publishers, searchable by buyer, country and deadline, with links to the original notice.' % len(tenders)),
                 'tenders', 'Tenders', str(len(tenders)) + ' results', flt, '<div id="tactives" class="actives" hidden></div>' + (table if tenders else '<div class="state"><h2>No open tenders from cleared sources right now</h2><p>Check the <a href="/portals">procurement portals</a> directly.</p></div>') + note + foot, crumbs)


def awards_page(site, rows):
    crumbs = [('Military Yellow Book', '/'), ('Contract awards', None)]
    awards = [r for r in rows if r['kind'] == 'award']
    fresh = max((r['refreshed_at'] for r in rows), default=None)
    countries = sorted({r.get('country_name') or 'Not stated' for r in awards})
    flt = fbar([('country', 'Country', [(c, c) for c in countries]),
                ('source', 'Source', [(s, SOURCE_NAMES.get(s, (s,))[0]) for s in sorted({r['source_id'] for r in awards})])], 'Search awards')
    trs = ''
    for r in sorted(awards, key=lambda r: r.get('published_at') or '', reverse=True):
        c = r.get('country_name') or 'Not stated'
        m = fmt_money(r.get('amount'), r.get('currency'))
        d = fmt_date(r['published_at'])[0] if r.get('published_at') else ''
        hay = ' '.join(str(x or '') for x in (r['title'], r.get('buyer'), r.get('supplier'), c, r.get('currency'))).lower()
        trs += ('<tr data-s="' + esc(hay) + '" data-f-country="' + esc(c) + '" data-f-source="' + esc(r['source_id']) + '">'
                '<td class="wrapc" data-k="buyer" data-v="' + esc((r.get('buyer') or '').lower()) + '" data-l="Buyer"><span class="t-main">' + esc(r.get('buyer') or 'Not stated') + '</span><span class="t-sub">' + esc(c) + '</span></td>'
                '<td class="wrapc" data-k="supplier" data-v="' + esc((r.get('supplier') or '').lower()) + '" data-l="Awarded to">' + (esc(r['supplier']) if r.get('supplier') else '<span class="muted">Not stated</span>') + '</td>'
                '<td class="wrapc" data-k="title" data-v="' + esc((r['title'] or '').lower()) + '" data-l="Contract">' + esc((r['title'] or '')[:160]) + '</td>'
                '<td class="n" data-k="value" data-v="' + ('' if r.get('amount') in (None, '') else str(float(r['amount']))) + '" data-l="Value">' + (esc(m) if m else '<span class="muted">Not stated</span>') + '</td>'
                '<td class="n" data-k="date" data-v="' + iso_day(r.get('published_at')) + '" data-l="Date">' + esc(d) + '</td>'
                '<td data-l="Source">' + src_link(r) + '</td></tr>')
    table = ('<div class="tbl-wrap"><table class="tbl stack" data-table data-sort="date:desc"><caption class="sr">Recent government contract awards</caption><thead><tr>' +
             th('Buyer', 'buyer') + th('Awarded to', 'supplier') + th('Contract', 'title') + th('Value', 'value', True, 'n') + th('Date', 'date', False, 'n') + th('Source') +
             '</tr></thead><tbody>' + trs + '</tbody></table></div>'
             '<div class="state" id="tempty" hidden role="status"><h2>No awards match</h2><p>Remove a filter or search for a different word.</p></div>'
             '<div class="more"><button class="btn btn-secondary" id="tmore" type="button" hidden>Show more</button></div>')
    note = ('<div class="callout ws-note"><div>Contracts awarded recently, as published by the buyer&rsquo;s official system. Study who wins what, at what price, to position your own bids. Values are in the publisher&rsquo;s currency and are not converted; '
            'a blank means the publisher did not state it. ' + ('Data refreshed ' + esc(fmt_date(fresh)[0]) + '. ' if fresh else '') + 'Individuals are never listed as suppliers. See <a href="/opportunities">open tenders</a> to bid on live notices.</div></div>')
    return wpage(site, '/awards', 'Government contract awards: who is winning | Military Yellow Book',
                 trim('%d recent government contract awards from official publishers: buyer, awarded supplier, value and date, with links to the source notice.' % len(awards)),
                 'awards', 'Contract awards', str(len(awards)) + ' results', flt, '<div id="tactives" class="actives" hidden></div>' + (table if awards else '<div class="state"><h2>No awards published yet</h2></div>') + note, crumbs)


SCOPE_LABEL = {'national': 'National government', 'subnational': 'Regional or state authority', 'agency': 'Agency or catalogue'}


def portals_page(site, rows):
    crumbs = [('Military Yellow Book', '/'), ('Government procurement portals', None)]
    countries = len({r['country'] for r in rows if r['scope'] == 'national'})
    rnames = dict(REGION_NAMES)
    flt = fbar([('region', 'Region', [(k or 'intl', n) for k, n in REGION_NAMES if any(r['region'] == k for r in rows)]),
                ('scope', 'Jurisdiction', [(k, v) for k, v in SCOPE_LABEL.items() if any(r['scope'] == k for r in rows)]),
                ('check', 'Link status', [('ok', 'Listed, not link-checked'), ('warn', 'Needs a check')])], 'Search portals')
    trs = ''
    for r in rows:
        links = ''
        if r['url']:
            links += '<a href="' + esc(r['url']) + '" rel="nofollow noopener noreferrer" target="_blank">Official site<span class="sr"> of ' + esc(r['name']) + '</span></a>'
        if r['feed_url']:
            links += (' · ' if links else '') + '<a href="' + esc(r['feed_url']) + '" rel="nofollow noopener noreferrer" target="_blank">Tender feed<span class="sr"> for ' + esc(r['name']) + '</span></a>'
        warn = r['flag'] in ('general_site', 'no_url')
        stat = ('<span class="badge badge-warn">' + ('No portal listed' if r['flag'] == 'no_url' else 'Check address') + '</span>') if warn else '<span class="badge">Reference, unverified</span>'
        reg = rnames.get(r['region'], 'International')
        hay = ' '.join(str(x or '') for x in (r['name'], r['country'], reg, r.get('platform'), r.get('classification'), r.get('note'))).lower()
        trs += ('<tr data-s="' + esc(hay) + '" data-f-region="' + esc(r['region'] or 'intl') + '" data-f-scope="' + esc(r['scope']) + '" data-f-check="' + ('warn' if warn else 'ok') + '">'
                '<td data-k="country" data-v="' + esc((r['country'] or '').lower()) + '" data-l="Country">' + esc(r['country']) + '<span class="t-sub">' + esc(reg) + '</span></td>'
                '<td class="wrapc" data-k="name" data-v="' + esc(r['name'].lower()) + '" data-l="Portal or entity"><span class="t-main">' + esc(r['name']) + '</span>' + ('<span class="t-sub">' + esc(r['note']) + '</span>' if r['note'] else '') + '</td>'
                '<td data-k="scope" data-v="' + esc(r['scope']) + '" data-l="Jurisdiction">' + esc(SCOPE_LABEL.get(r['scope'], r['scope'])) + '</td>'
                '<td data-l="Platform and codes">' + esc((r['platform'] or '').capitalize()) + ('<span class="t-sub">' + esc(r['classification']) + '</span>' if r['classification'] else '') + '</td>'
                '<td data-l="Status">' + stat + '</td>'
                '<td data-l="Links">' + (links or '<span class="muted">None</span>') + '</td></tr>')
    table = ('<div class="tbl-wrap"><table class="tbl stack" data-table data-sort="country:asc"><caption class="sr">Government procurement portals by country</caption><thead><tr>' +
             th('Country', 'country') + th('Portal or entity', 'name') + th('Jurisdiction', 'scope') + th('Platform and codes') + th('Status') + th('Links') +
             '</tr></thead><tbody>' + trs + '</tbody></table></div>'
             '<div class="state" id="tempty" hidden role="status"><h2>No portals match</h2><p>Remove a filter or try a country name.</p></div>'
             '<div class="more"><button class="btn btn-secondary" id="tmore" type="button" hidden>Show more</button></div>')
    note = ('<div class="callout ws-note"><div><b>Check before you rely on a link.</b> This list is compiled from the sources named below and has not been verified link by link, so nothing here is marked as a confirmed official portal. '
            'No verification date is shown because none has been recorded. &ldquo;Check address&rdquo; means the entry points at a general government or commercial site rather than a procurement system. '
            'The official portal is always the system of record for a government&rsquo;s tenders. Trading with some countries is restricted by sanctions and export controls: confirm what applies to you before you bid. '
            'See <a href="/opportunities">open tenders</a> and <a href="/awards">contract awards</a> taken from official publishers.</div></div>')
    foot = ('<h2 class="ws-h">Which product codes do portals want?</h2><p>Many portals ask suppliers to classify what they sell: the US uses NAICS and PSC, the EU and UK use CPV, and UNGM, Australia, New Zealand and Canada use UNSPSC. '
            'Every listing in this directory carries UNSPSC codes, so you can reuse them when you register.</p>'
            '<h2 class="ws-h">Sources</h2><ul class="plain">'
            '<li>Sell to State, <a href="https://www.selltostate.com/guides/global-government-procurement-portals/" rel="noopener noreferrer" target="_blank">Government Procurement Portals by Country</a> (updated 30 June 2026): one portal for each of 193 countries.</li>'
            '<li>Open Opportunities, <a href="https://openopps.com/sources/" rel="noopener noreferrer" target="_blank">sources</a>: regional, state and international tender sources, linked as feeds.</li>'
            '<li>Inter-American Network on Government Procurement (RICG), <a href="https://ricg.org/en/regional-e-gp-inventory" rel="noopener noreferrer" target="_blank">Regional e-GP inventory</a>: platform type for Latin American and Caribbean systems.</li>'
            '<li>US Department of Veterans Affairs, <a href="https://www.vendorportal.ecms.va.gov/nac" rel="noopener noreferrer" target="_blank">National Acquisition Center contract catalogue</a>.</li></ul>')
    return wpage(site, '/portals', 'Government procurement portals by country | Military Yellow Book',
                 trim(f'{len(rows)} government and international procurement portals in {countries} countries, with the product code systems they use. Where to register to sell to defence buyers.'),
                 'portals', 'Procurement portals', str(len(rows)) + ' results', flt, '<div id="tactives" class="actives" hidden></div>' + table + note + foot, crumbs)


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
            '<a class="btn" href="/opportunities">Open tenders</a><a class="btn" href="/portals">Government procurement portals</a></div>')
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
    opps, osource = load_opportunities()
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
    open(os.path.join(out, 'opportunities.html'), 'w', encoding='utf-8').write(tenders_page(site, opps, portals))
    open(os.path.join(out, 'awards.html'), 'w', encoding='utf-8').write(awards_page(site, opps))
    os.makedirs(os.path.join(out, 'assets'), exist_ok=True)
    for f in ('ui.css', 'table.js'):
        shutil.copyfile(os.path.join(ROOT, 'src', 'assets', f), os.path.join(out, 'assets', f))
    shutil.copytree(os.path.join(ROOT, 'src', 'assets', 'flags'), os.path.join(out, 'assets', 'flags'), dirs_exist_ok=True)
    open(os.path.join(out, 'terms.html'), 'w', encoding='utf-8').write(terms_page(site))
    open(os.path.join(out, 'privacy.html'), 'w', encoding='utf-8').write(privacy_page(site))
    open(os.path.join(out, '404.html'), 'w', encoding='utf-8').write(not_found_page(site))

    urls = ['/', '/directory', '/opportunities', '/awards', '/portals', '/terms', '/privacy'] + ['/c/' + slugify(c) for c, _ in groups] + ['/l/' + b['slug'] for b in listings]
    open(os.path.join(out, 'sitemap.xml'), 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        ''.join('<url><loc>' + esc(site + u) + '</loc></url>\n' for u in urls) + '</urlset>\n')
    open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8').write('User-agent: *\nAllow: /\n\nSitemap: ' + site + '/sitemap.xml\n')
    print(f'pages: {len(listings)} listings + {len(groups)} categories + directory + portals ({len(portals)}) + opportunities ({len(opps)}, {osource}) + terms + privacy + 404 + sitemap ({len(urls)} URLs), sources: {source}, {psource}')
    return urls


if __name__ == '__main__':
    build(os.environ.get('SITE_URL', 'https://military-yellow-book.vercel.app'))
