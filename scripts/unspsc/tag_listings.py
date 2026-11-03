#!/usr/bin/env python3
"""Suggest UNSPSC codes for each seed listing: best title overlap among non-blocked class/commodity codes under the
listing's category mapping, then apply hand-reviewed overrides. Output: supabase/listing_unspsc.json {slug: [codes]}."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from mapping import CATEGORY_UNSPSC
try:
    from overrides import OVERRIDES
except ImportError:
    OVERRIDES = {}
STOP = set('and or of the for with to in a an by on set kit system systems equipment other related accessories supplies products product services service'.split())
def toks(t):
    out = set()
    for w in re.findall(r'[a-z]+', t.lower()):
        if w in STOP or len(w) < 3: continue
        w = re.sub(r'(ies)$', 'y', w); w = re.sub(r'(es|s)$', '', w) if len(w) > 4 else w
        out.add(w)
    return out
def main(show=True):
    U = json.load(open(os.path.join(ROOT, 'supabase', 'unspsc.json')))['rows']
    seed = json.load(open(os.path.join(ROOT, 'supabase', 'seed.json')))
    res, rep = {}, []
    for l in seed:
        slug = l['slug']
        if slug in OVERRIDES:
            res[slug] = OVERRIDES[slug]; rep.append((slug, l['name'], 'OVERRIDE', res[slug])); continue
        pref = CATEGORY_UNSPSC[l['category']]
        want = toks(l['name'] + ' ' + l['descr'])
        namew = toks(l['name'])
        cands = []
        for r in U:
            c = r[0]
            if r[4] == 'blocked' or r[2] < 3 or not any(c.startswith(p.rstrip('0')) for p in pref): continue
            tt = toks(r[5])
            if not tt: continue
            ov = tt & want
            if not ov: continue
            sc = len(ov) / (len(tt) ** 0.5) + 0.7 * len(tt & namew) + (0.15 if r[2] == 4 else 0)
            cands.append((sc, c, r[5]))
        cands.sort(reverse=True)
        top = cands[:3]
        res[slug] = [c for _, c, _ in top[:2]]
        rep.append((slug, l['name'], l['category'], [(c, t[:34], round(s, 1)) for s, c, t in top]))
    if show:
        for slug, name, cat, c in rep: print(slug, '|', name[:44], '|', cat[:14], '->', c)
    return res
if __name__ == '__main__':
    r = main(show='--quiet' not in sys.argv)
    json.dump(r, open(os.path.join(ROOT, 'supabase', 'listing_unspsc.json'), 'w'), indent=1)
