#!/usr/bin/env python3
"""Merge the government-procurement-portal lists into supabase/portals.json.

Sources (all fetched 3 Nov 2026; none of the links has been checked, the build sandbox cannot reach them):
  sources/selltostate.txt  Sell to State, "Government Procurement Portals by Country" (updated 30 Jun 2026): one portal per country
  sources/openopps.txt     Open Opportunities, openopps.com/sources: 100 sources incl. sub-national and international ones (feed pages only)
  RICG below               Inter-American Network on Government Procurement, Regional e-GP inventory (platform type per system)
  EXTRA below              added by hand: UNGM, TED, and the VA National Acquisition Center catalogue

Rows: scope, country, region, name, url, feed_url, platform, classification, note, flag, sources, position.
Nothing here claims a link works. `flag` marks rows we doubt from the URL alone.
Run from the repo root:  python3 scripts/portals/build_portals.py
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

REGION_COUNTRIES = {
    'americas': 'Antigua and Barbuda|Argentina|Bahamas|Barbados|Belize|Bolivia|Brazil|Canada|Cayman Islands|Chile|Colombia|Costa Rica|Cuba|Dominica|Dominican Republic|Ecuador|El Salvador|Grenada|Guatemala|Guyana|Haiti|Honduras|Jamaica|Mexico|Montserrat|Nicaragua|Panama|Paraguay|Peru|Saint Kitts and Nevis|Saint Lucia|Saint Vincent and the Grenadines|Suriname|Trinidad and Tobago|United States|Uruguay|Venezuela',
    'europe': 'Albania|Andorra|Austria|Belarus|Belgium|Bosnia and Herzegovina|Bulgaria|Croatia|Cyprus|Czech Republic|Denmark|Estonia|Finland|France|Germany|Greece|Hungary|Iceland|Ireland|Italy|Kosovo|Latvia|Lithuania|Luxembourg|Malta|Moldova|Monaco|Montenegro|Netherlands|North Macedonia|Norway|Poland|Portugal|Romania|Russia|Serbia|Slovakia|Slovenia|Spain|Sweden|Switzerland|Ukraine|United Kingdom',
    'mideast': 'Bahrain|Iran|Iraq|Israel|Jordan|Kuwait|Lebanon|Oman|Palestine|Qatar|Saudi Arabia|Syria|Turkey|UAE|Yemen',
    'africa': 'Algeria|Angola|Benin|Botswana|Burkina Faso|Burundi|Cameroon|Cape Verde|Central African Republic|Chad|Comoros|DR Congo|Djibouti|Egypt|Equatorial Guinea|Eritrea|Eswatini|Ethiopia|Gabon|Gambia|Ghana|Guinea|Guinea-Bissau|Ivory Coast|Kenya|Lesotho|Liberia|Libya|Madagascar|Malawi|Mali|Mauritania|Mauritius|Morocco|Mozambique|Namibia|Niger|Nigeria|Republic of Congo|Rwanda|São Tomé and Príncipe|Senegal|Seychelles|Sierra Leone|Somalia|South Africa|South Sudan|Sudan|Tanzania|Togo|Tunisia|Uganda|Zambia|Zimbabwe',
    'asia': 'Afghanistan|Armenia|Australia|Azerbaijan|Bangladesh|Bhutan|Brunei|Cambodia|China|Fiji|Georgia|Hong Kong|India|Indonesia|Japan|Kazakhstan|Kiribati|Kyrgyzstan|Laos|Malaysia|Maldives|Marshall Islands|Micronesia|Mongolia|Myanmar|Nauru|Nepal|New Zealand|Pakistan|Palau|Papua New Guinea|Philippines|Samoa|Singapore|Solomon Islands|South Korea|Sri Lanka|Taiwan|Tajikistan|Thailand|Timor-Leste|Tonga|Turkmenistan|Tuvalu|Uzbekistan|Vanuatu|Vietnam',
}
REGION = {c: r for r, names in REGION_COUNTRIES.items() for c in names.split('|')}

# Sell to State rows whose URL looks like a general government, regulator-training or commercial site rather than a procurement system
GENERAL_SITE = {'UAE', 'Equatorial Guinea', 'Eritrea', 'Kiribati', 'Libya', 'Marshall Islands', 'Micronesia', 'Palau', 'Samoa', 'Tuvalu', 'Vanuatu',
                'Monaco', 'Andorra', 'Belize', 'Lesotho', 'Suriname', 'São Tomé and Príncipe', 'Somalia', 'Sudan', 'Syria', 'Lebanon', 'Qatar',
                'Tonga', 'Sweden', 'Austria', 'Brunei', 'Turkmenistan'}

# Open Opps source -> the Sell to State row it duplicates ("country|openopps name" -> sts country, sts name). Anything not listed is added as its own row.
MERGE = {k: v for k, v in [
    ('Spain|Plataforma de Contratacion del Estado', ('Spain', 'PLACE')), ('France|Marches Publics (PLACE)', ('France', 'PLACE / BOAMP')),
    ('Bulgaria|Bulgaria Public Procurement', ('Bulgaria', 'CAIS')), ('Lithuania|CVP Lithuania', ('Lithuania', 'CVP IS')),
    ('Croatia|Croatia Public Procurement', ('Croatia', 'EOJN')), ('Czech Republic|Czech Republic Public Procurement', ('Czech Republic', 'NEN')),
    ('Norway|Doffin', ('Norway', 'Doffin')), ('Hungary|Hungary Public Procurement', ('Hungary', 'EKR')),
    ('Luxembourg|Luxembourg Public Procurement', ('Luxembourg', 'Portail des marchés publics')), ('Poland|Poland Public Procurement', ('Poland', 'BZP / TED')),
    ('Portugal|Portugal Public Procurement', ('Portugal', 'BASE')), ('Belgium|Public Procurement Belgium', ('Belgium', 'e-Procurement')),
    ('Romania|Romania Public Procurement', ('Romania', 'SEAP')), ('Slovenia|Slovenia Public Procurement', ('Slovenia', 'e-JN')),
    ('Netherlands|TenderNed', ('Netherlands', 'TenderNed')), ('Finland|Tenders Electronic Daily Finland', ('Finland', 'Hilma')),
    ('Denmark|Udbud Denmark', ('Denmark', 'Udbud.dk')), ('Ireland|eTenders Ireland', ('Ireland', 'eTenders')),
    ('Malta|eTenders Malta', ('Malta', 'ePPS')), ('Switzerland|simap', ('Switzerland', 'simap.ch')),
    ('Argentina|Comprar Argentina', ('Argentina', 'COMPR.AR')), ('Brazil|Comprasnet', ('Brazil', 'ComprasNet / gov.br Compras')),
    ('Colombia|SECOP', ('Colombia', 'SECOP II')), ('Costa Rica|SICOP', ('Costa Rica', 'SICOP')),
    ('Dominican Republic|DGCP', ('Dominican Republic', 'DGCP')), ('Ecuador|SERCOP', ('Ecuador', 'SERCOP')),
    ('Jamaica|GOJEP', ('Jamaica', 'GOJ eProcurement')), ('Chile|Mercado Publico', ('Chile', 'Mercado Público')),
    ('Mexico|CompraNet', ('Mexico', 'Compras MX')), ('Panama|PanamaCompra', ('Panama', 'PanamaCompra')),
    ('Peru|SEACE', ('Peru', 'SEACE')), ('Uruguay|ARCE', ('Uruguay', 'ARCE')),
    ('Australia|AusTender', ('Australia', 'AusTender')), ('New Zealand|GETS', ('New Zealand', 'GETS')),
    ('Singapore|GeBIZ', ('Singapore', 'GeBIZ')), ('India|Government e-Marketplace', ('India', 'GeM / CPPP')),
    ('South Korea|KONEPS', ('South Korea', 'KONEPS')), ('Malaysia|MyPROCUREMENT', ('Malaysia', 'MyProcurement')),
    ('Philippines|PhilGEPS', ('Philippines', 'PhilGEPS')), ('Taiwan|Government e-Procurement', ('Taiwan', 'PCC')),
    ('Thailand|e-GP', ('Thailand', 'Thai EGP')), ('Vietnam|National Bidding Network', ('Vietnam', 'VNEPS')),
    ('Canada|CanadaBuys', ('Canada', 'CanadaBuys')), ('US (federal)|SAM.gov', ('United States', 'SAM.gov')),
    ('Bahrain|Tender Board', ('Bahrain', 'Bahrain Tender Board')), ('Egypt|Egypt Tenders', ('Egypt', 'Egypt e-Procurement Portal')),
    ('Saudi Arabia|Etimad', ('Saudi Arabia', 'Etimad')), ('Kuwait|Central Agency for Public Tenders', ('Kuwait', 'Kuwait Central Agency for Public Tenders')),
    ('Morocco|Procurement Portal', ('Morocco', 'Portail Marchés Publics')), ('Oman|Tender Board', ('Oman', 'Oman Tender Board')),
    ('Qatar|Qatar Procurement', ('Qatar', 'Qatar e-Government Procurement')), ('UAE|Federal Procurement', ('UAE', 'UAE Procurement Portal')),
    ('Kenya|PPIP', ('Kenya', 'PPIP / IFMIS')), ('Nigeria|BPP', ('Nigeria', 'NOCOPO / BPP')), ('South Africa|eTenders', ('South Africa', 'eTenders')),
    ('UK|Contracts Finder', ('United Kingdom', 'Contracts Finder')),
]}

# Product-classification system each portal asks suppliers to use: only where we are sure
CLASSIFICATION = {
    ('United States', 'SAM.gov'): 'NAICS, PSC', ('Australia', 'AusTender'): 'UNSPSC', ('New Zealand', 'GETS'): 'UNSPSC',
    ('Canada', 'CanadaBuys'): 'UNSPSC, GSIN', ('United Kingdom', 'Contracts Finder'): 'CPV', ('United Kingdom', 'Find a Tender Service'): 'CPV',
    ('European Union', 'TED'): 'CPV', ('International', 'UNGM'): 'UNSPSC',
}

# RICG regional e-GP inventory (Latin America and Caribbean): country -> [(system, type, portal as listed or None)]
RICG = {
    'Argentina': [('CONTRAT.AR (public works)', 'Transactional', 'contratar.gob.ar')], 'Bolivia': [('SICOES', 'Informative', 'sicoes.gob.bo')],
    'Brazil': [('COMPRASNET 4.0', 'Transactional', 'gov.br/compras/pt-br')], 'Chile': [('MERCADOPUBLICO', 'Transactional', 'chilecompra.cl')],
    'Colombia': [('SECOP I', 'Informative', 'colombiacompra.gov.co'), ('SECOP II', 'Transactional', None), ('TVEC', 'Transactional', None)],
    'Costa Rica': [('SICOP', 'Transactional', 'sicop.go.cr/index.jsp')], 'Dominican Republic': [('COMPRAS DOMINICANA', 'Transactional', 'dgcp.gob.do')],
    'Ecuador': [('SOCE', 'Transactional', 'compraspublicas.gob.ec')], 'El Salvador': [('COMPRASAL', 'Informative', 'comprasal.gob.sv')],
    'Guatemala': [('GUATECOMPRAS', 'Transactional', 'guatecompras.gt')], 'Haiti': [('Journal Électronique des Marchés Publics', 'Informative', 'cnmp.gouv.ht')],
    'Honduras': [('HONDUCOMPRAS I', 'Transactional', 'honducompras.gob.hn'), ('HONDUCOMPRAS II', 'Transactional', None), ('Catálogo Electrónico', 'Transactional', None)],
    'Mexico': [('COMPRANET 5.0', 'Transactional', 'gob.mx/compranet'), ('TDGF (Tienda Digital del Gobierno Federal)', 'Transactional', None)],
    'Panama': [('PANAMACOMPRA', 'Transactional', 'dgcp.gob.pa')], 'Paraguay': [('SICP', 'Transactional', 'contrataciones.gov.py')],
    'Peru': [('SEACE', 'Transactional', 'gob.pe/osce'), ('RNP (supplier registry)', 'Transactional', None), ('CEAM (framework agreement catalogues)', 'Transactional', None)],
    'Trinidad and Tobago': [('Procurement Depository (Office of Procurement Regulation)', 'Transactional', 'oprtt.org')],
    'Uruguay': [('SICE', 'Transactional', 'gub.uy/agencia-reguladora-compras-estatales/')],
}
RICG_OBSERVERS = [  # countries the Sell to State list lacks
    ('Cayman Islands', 'Bonfire', 'https://procure.gov.ky', 'Transactional'), ('Montserrat', 'Mytenders', 'https://tenders.gov.ms', 'Informative'),
]

EXTRA = [  # (scope, country, region, name, url, feed_slug, classification, note, sources)
    ('international', 'International', None, 'UNGM (United Nations Global Marketplace)', 'https://www.ungm.org', 'ungm', 'UNSPSC',
     'Common supplier registration for UN agencies. UNGM publishes the UNSPSC list this directory uses for product codes.', ['openopps', 'manual']),
    ('international', 'European Union', None, 'TED (Tenders Electronic Daily)', 'https://ted.europa.eu', 'ted', 'CPV',
     'Official journal for EU public tenders.', ['openopps', 'manual']),
    ('agency', 'United States', 'americas', 'VA National Acquisition Center: Contract Catalog Search Tool', 'https://www.vendorportal.ecms.va.gov/nac', None, None,
     'Public catalogue of 1,700+ active US Department of Veterans Affairs healthcare contract vehicles (Federal Supply Schedule, BPAs, national contracts) with ~1 million line items. '
     'Useful market research for medical and protective suppliers. Reference only: pricing differences go to the contractor or contracting officer.', ['va-nac']),
]


def norm_region(country):
    return REGION.get(country)


def main():
    rows, by_key = [], {}
    for line in open(os.path.join(HERE, 'sources', 'selltostate.txt'), encoding='utf-8'):
        country, name, url = line.rstrip('\n').split('|')
        r = {'scope': 'national', 'country': country, 'region': norm_region(country), 'name': name, 'url': url or None, 'feed_url': None, 'platform': None,
             'classification': CLASSIFICATION.get((country, name)), 'note': None, 'flag': None, 'sources': ['selltostate']}
        assert r['region'], country
        if not url:
            r['name'] = 'No national portal listed'
            r['flag'] = 'no_url'
            r['note'] = 'Sell to State says this government publishes through its official gazette and ministries.'
        elif country in GENERAL_SITE:
            r['flag'] = 'general_site'
            r['note'] = 'The listed address looks like a general government or commercial website, not a procurement portal. Check before relying on it.'
        rows.append(r)
        by_key[(country, name)] = r

    # Open Opps: attach the feed page to the same system, or add a row of its own
    sub_country = {'US': 'United States', 'UK': 'United Kingdom'}
    for line in open(os.path.join(HERE, 'sources', 'openopps.txt'), encoding='utf-8'):
        label, name, slug = line.rstrip('\n').split('|')
        feed = 'https://openopps.com/sources/' + slug + '/'
        key = label + '|' + name
        if key in MERGE:
            r = by_key[MERGE[key]]
            r['feed_url'] = feed
            r['sources'].append('openopps')
            continue
        m = re.match(r'^(.*?) \((.*)\)$', label)
        scope, place = 'national', label
        if m and m.group(2) != 'federal':
            scope, place = 'subnational', sub_country.get(m.group(1), m.group(1))
            if m.group(2).lower() not in name.lower():
                name = f'{name} ({m.group(2)})'
        elif m:
            place = sub_country.get(m.group(1), m.group(1))
        elif label in ('Scotland', 'Wales'):
            scope, place = 'subnational', 'United Kingdom'
            if label.lower() not in name.lower():
                name = f'{name} ({label})'
        elif label in sub_country:
            place = sub_country[label]
        elif label in ('International', 'Regional', 'EU'):
            scope, place = 'international', ('European Union' if label == 'EU' else 'International')
        if (place, name) in {(c, n) for c, n in [('European Union', 'TED'), ('International', 'UNGM')]} or place == 'International' and name == 'UNGM':
            continue   # covered by EXTRA with a confirmed address
        if place == 'European Union' and name == 'TED':
            continue
        r = {'scope': scope, 'country': place, 'region': norm_region(place), 'name': name, 'url': None, 'feed_url': feed, 'platform': None,
             'classification': CLASSIFICATION.get((place, name)), 'note': 'Tender notices via the Open Opps feed; the official portal address is not recorded here yet.',
             'flag': None, 'sources': ['openopps']}
        assert scope == 'international' or r['region'], (label, name)
        rows.append(r)

    for scope, country, region, name, url, slug, cls, note, sources in EXTRA:
        rows.append({'scope': scope, 'country': country, 'region': region or norm_region(country), 'name': name, 'url': url,
                     'feed_url': ('https://openopps.com/sources/' + slug + '/') if slug else None, 'platform': None, 'classification': cls, 'note': note,
                     'flag': None, 'sources': sources})

    # RICG: platform type, plus the systems that have no row of their own
    for country, systems in RICG.items():
        main_rows = [r for r in rows if r['country'] == country and r['scope'] == 'national' and r['sources'][0] == 'selltostate']
        assert main_rows, country
        r = main_rows[0]
        r['sources'].append('ricg')
        if len(systems) == 1:
            r['platform'] = systems[0][1].lower()
        others = '; '.join(f"{s} ({t.lower()}{', ' + d if d else ''})" for s, t, d in systems)
        r['note'] = ((r['note'] + ' ') if r['note'] else '') + 'RICG lists: ' + others + '.'
    for country, name, url, typ in RICG_OBSERVERS:
        rows.append({'scope': 'national', 'country': country, 'region': norm_region(country), 'name': name, 'url': url, 'feed_url': None,
                     'platform': typ.lower(), 'classification': None, 'note': 'Observer country in the RICG inventory.', 'flag': None, 'sources': ['ricg']})

    order = {'americas': 0, 'europe': 1, 'mideast': 2, 'africa': 3, 'asia': 4, None: 5}
    scope_order = {'national': 0, 'subnational': 1, 'agency': 2, 'international': 3}
    rows.sort(key=lambda r: (order[r['region']], r['country'], scope_order[r['scope']], r['name'].lower()))
    for i, r in enumerate(rows):
        r['position'] = i + 1
        r['sources'] = sorted(set(r['sources']))
    keys = [(r['country'], r['name']) for r in rows]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
    json.dump(rows, open(os.path.join(ROOT, 'supabase', 'portals.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    by = {}
    for r in rows:
        by[r['scope']] = by.get(r['scope'], 0) + 1
    print(len(rows), 'portals', by, '| with address:', sum(1 for r in rows if r['url']), '| feed-only:', sum(1 for r in rows if not r['url'] and r['feed_url']),
          '| flagged:', sum(1 for r in rows if r['flag']), '| with open-opps feed:', sum(1 for r in rows if r['feed_url']))


if __name__ == '__main__':
    main()
