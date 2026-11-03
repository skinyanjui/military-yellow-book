#!/usr/bin/env python3
"""Build the deployable bundle in site/ from src/index.html.

- strips the embedded sample data (listings are served from Supabase)
- minifies CSS and JS with esbuild (needs npx)
- self-hosts supabase-js from site/vendor/ (no third-party script at runtime)
- writes vercel.json with a content security policy whose script hashes match the inline scripts
Run from the repository root:  python3 scripts/build_deploy.py
"""
import base64, hashlib, json, os, re, subprocess, sys

SUPABASE_URL = 'https://bfovgafcfetfeqykjfco.supabase.co'
SUPABASE_KEY = 'sb_publishable_FfVpTa_cEtn_LRJ5FNc-VQ_8bvPbVZx'   # publishable key: safe to ship
SITE_URL = os.environ.get('SITE_URL', 'https://military-yellow-book.vercel.app').rstrip('/')
VENDOR = '/vendor/supabase-js-2.45.4.js'

s = open('src/index.html', encoding='utf-8').read()

# 1. strip embedded listings
i = s.index('  var DATA = ['); j = s.index('\n  ];', i) + len('\n  ];')
s = s[:i] + '  var DATA = [];' + s[j:]
s, n1 = re.subn(r'var RATINGS = \[\[.*?\]\];', 'var RATINGS = [];', s, count=1, flags=re.S)
s, n2 = re.subn(r'var DOM = \[\[.*?\]\];', 'var DOM = [];', s, count=1, flags=re.S)
assert n1 == 1 and n2 == 1

# 2. split blocks
st = s.index('<style>'); se = s.index('</style>')
css = s[st + 7:se]
sc = s.rindex('<script>'); sce = s.rindex('</script>')
js = s[sc + 8:sce]
head_pre = s[:st]
mid = s[se + 8:sc]

def esb(code, loader):
    r = subprocess.run(['npx', '--yes', 'esbuild', '--minify', '--line-limit=700', '--loader=' + loader],
                       input=code, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr); sys.exit(1)
    return r.stdout

css_m = esb(css, 'css'); js_m = esb(js, 'js')
mid = re.sub(r'\n\s+', '\n', mid)
mid = re.sub(r'<!--.*?-->', '', mid, flags=re.S)

title = re.search(r'<title>(.*?)</title>', head_pre).group(1)
fonts = re.findall(r'<link[^>]+fonts[^>]*>', head_pre)
desc = ('The global directory of military suppliers: uniforms, boots, field gear, vehicles, aircraft parts, '
        'naval, optics, space, cyber and more. Search by domain, branch, category and country.')
icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
        "fill='%23f5b800'/%3E%3Ctext x='16' y='22' font-family='Arial' font-weight='700' font-size='15' text-anchor='middle' "
        "fill='%23171717'%3EYB%3C/text%3E%3C/svg%3E")

cfg_js = 'window.MYB_BACKEND=' + json.dumps({'url': SUPABASE_URL, 'key': SUPABASE_KEY}) + ';'
def sha(code): return "'sha256-" + base64.b64encode(hashlib.sha256(code.encode('utf-8')).digest()).decode() + "'"

meta = (
    '<meta name="description" content="' + desc + '">'
    '<link rel="canonical" href="' + SITE_URL + '/">'
    '<meta property="og:type" content="website"><meta property="og:site_name" content="' + title + '">'
    '<meta property="og:title" content="' + title + ': the global directory of military suppliers">'
    '<meta property="og:description" content="' + desc + '">'
    '<meta property="og:url" content="' + SITE_URL + '/">'
    '<meta property="og:image" content="' + SITE_URL + '/og.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
    '<meta property="og:image:alt" content="Military Yellow Book, the global directory of military suppliers">'
    '<meta name="twitter:card" content="summary_large_image">'
    '<meta name="twitter:title" content="' + title + '"><meta name="twitter:description" content="' + desc + '">'
    '<meta name="twitter:image" content="' + SITE_URL + '/og.png">'
    '<meta name="theme-color" content="#f5b800">'
)
html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<title>' + title + '</title>' + meta + '<link rel="icon" href="' + icon + '">' + ''.join(fonts) +
        '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}'
        'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '<style>' + css_m + '</style></head><body class="is-loading">' + mid +
        '<script src="' + VENDOR + '"></script><script>' + cfg_js + '</script>'
        '<script>' + js_m + '</script></body></html>')

csp = '; '.join([
    "default-src 'none'",
    "script-src 'self' " + sha(cfg_js) + ' ' + sha(js_m),
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self' " + SUPABASE_URL,
    "base-uri 'none'", "form-action 'none'", "frame-ancestors 'self'", "object-src 'none'",
])
sec = [
    {"key": "Content-Security-Policy", "value": csp},
    {"key": "X-Content-Type-Options", "value": "nosniff"},
    {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
    {"key": "X-Frame-Options", "value": "SAMEORIGIN"},
    {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"},
]
vercel = {
    "cleanUrls": True,
    "headers": [
        {"source": "/(.*)", "headers": sec},
        {"source": "/vendor/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
        {"source": "/og.png", "headers": [{"key": "Cache-Control", "value": "public, max-age=86400"}]},
    ],
}
os.makedirs('site', exist_ok=True)
open('site/index.html', 'w', encoding='utf-8').write(html)
open('site/vercel.json', 'w', encoding='utf-8').write(json.dumps(vercel, indent=2) + '\n')
print('site/index.html', len(html.encode('utf-8')), 'bytes; style blocks:', html.count('<style>'), '; inline scripts hashed: 2')
