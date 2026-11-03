#!/usr/bin/env python3
"""Normalise the UNGM UNSPSC spreadsheet into supabase/unspsc.json.

  python3 scripts/unspsc/build_unspsc.py path/to/UNGM_UNSPSC.xlsx

Input columns: Key, Parent key, Code, Title. Rows 1..10 are the UNGM groups A-J, then segment > family > class > commodity.
Output rows: [code, parent_code, level, ungm_group, access, title]
  level   1 segment, 2 family, 3 class, 4 commodity (depth in the UNGM tree)
  access  open | licensed | blocked
          blocked   must never be listed in this directory (weapons, ammunition, explosives, ballistic armour,
                    thermal/night-vision gear, armoured and military platforms). Enforced by a database trigger.
          licensed  listable, but export-controlled or regulated: the listing should say "Licensed buyers".
          open      everything else.
Duplicate codes in the sheet (the same code under two parents) are merged; codes whose parent key is missing
(UNGM's humanitarian segment 57) fall back to the nearest structural parent.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'supabase', 'unspsc.json')

# ---- access rules (default-deny on anything that names a weapon, munition, explosive or ballistic/NV item) ----
BLOCK_PREFIX = {
    '461015': 'firearms', '461016': 'ammunition', '461017': 'ammunition handling', '4611': 'conventional war weapons',
    '4612': 'missiles', '4613': 'rockets', '4614': 'launchers', '46100000': 'light weapons and ammunition',
    '251317': 'military aircraft', '251319': 'military aircraft', '251117': 'military watercraft', '251020': 'war vehicles',
}
BLOCK_CODES = {
    '46151504': 'body armour', '46181502': 'ballistic armour', '46151508': 'ballistic helmet', '46151509': 'ballistic equipment',
    '46151506': 'impact weapons', '46151602': 'impact weapons', '46171626': 'night vision', '41115325': 'thermal imaging',
    '46171615': 'night vision', '46191510': 'thermal imaging', '46171637': 'interception equipment', '46171625': 'interception equipment',
    '46221503': 'detonators', '46221504': 'mine laying', '46221509': 'mine components', '46221510': 'mine components',
    '46221501': 'mine components', '92112100': 'nuclear warfare', '92112400': 'armed conflicts',
}
BLOCK_TITLE = re.compile(r'armou?red|ballistic|bullet ?proof|night vision|thermal (imag|observ)|explosive (material|charge|compound|device)s?\b|'
                         r'detonat|propellant|ammunition|munition|grenade|missile|warhead|torpedo|howitzer|artillery|firearm|handgun', re.I)
BLOCK_TITLE_SEGS = {'12', '25', '46', '41', '92'}
# explicit exceptions to the rules above (reviewed by hand)
OVERRIDE = {
    '46101800': ('licensed', 'arms accessories: licensed dealers only'),   # slings, holsters, rails: accessories only
    '46220000': ('licensed', 'demining and ordnance disposal'),
    '25111724': ('licensed', 'research and pollution-control vessels'), '25111725': ('licensed', 'research and pollution-control vessels'),
    '25111726': ('licensed', 'research and pollution-control vessels'),
    '92121800': ('open', ''),                                              # cash-in-transit, not a military platform
}
LICENSED_PREFIX = {
    '461018': 'arms accessories: licensed dealers only', '4620': 'weapons training equipment', '4622': 'demining and ordnance disposal',
    '46151800': 'explosives control', '46151900': 'chemical and biological control', '46151605': 'weapon and explosives detection',
    '25132': 'unmanned aircraft', '2513': 'aircraft', '2514': 'aircraft', '2515': 'spacecraft and satellites', '2520': 'aerospace components',
    '2519': 'aviation and space support', '2517': 'vehicle components', '25171': 'vehicle components', '9211': 'military services',
    '2614': 'nuclear', '12': 'regulated chemicals', '51': 'regulated pharmaceuticals', '81102810': 'counter-IED',
}
LICENSED_PREFIX.pop('2517'); LICENSED_PREFIX.pop('25171'); LICENSED_PREFIX.pop('2519')   # ordinary vehicle parts stay open


def classify(code, title):
    if code in OVERRIDE:
        return OVERRIDE[code]
    for p, why in BLOCK_PREFIX.items():
        if code.startswith(p):
            return 'blocked', why
    if code in BLOCK_CODES:
        return 'blocked', BLOCK_CODES[code]
    if code[:2] in BLOCK_TITLE_SEGS and BLOCK_TITLE.search(title):
        return 'blocked', 'title names a weapon, munition or ballistic/night-vision item'
    for p in sorted(LICENSED_PREFIX, key=len, reverse=True):
        if code.startswith(p):
            return 'licensed', LICENSED_PREFIX[p]
    return 'open', ''


def main(xlsx):
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, read_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]
    bykey = {r[0]: r for r in rows}
    groups = {}
    for r in rows:
        if not str(r[2]).isdigit():
            groups[r[0]] = (str(r[2]), (r[3] or '').strip())
    codes, first = {}, {}
    for r in rows:
        c = str(r[2])
        if c.isdigit() and c not in first:
            first[c] = r
    def struct_parent(c):
        for cut in (6, 4, 2):
            p = c[:cut].ljust(8, '0')
            if p != c and p in first:
                return p
        return None
    depth_cache = {}
    def depth(c):
        if c in depth_cache:
            return depth_cache[c]
        r = first[c]
        p = bykey.get(r[1])
        pc = str(p[2]) if p is not None and str(p[2]).isdigit() and str(p[2]) in first else None
        if p is not None and p[0] in groups:        # direct child of a UNGM group: a segment
            d, parent, g = 1, None, groups[p[0]][0]
        else:
            parent = pc or struct_parent(c)
            if parent is None:
                d, g = 1, None
            else:
                d = depth(parent)[0] + 1; g = depth(parent)[2]
        depth_cache[c] = (d, parent, g)
        return depth_cache[c]
    out = []
    for c in sorted(first):
        d, parent, g = depth(c)
        title = (first[c][3] or '').strip()
        acc, why = classify(c, title)
        out.append([c, parent, min(d, 4), g, acc, title, why])
    # a parent is at most 'licensed' even if some children are blocked, unless its own title/prefix is blocked
    json.dump({'groups': sorted(v for v in groups.values()), 'rows': out}, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    import collections
    print('codes', len(out), '| levels', dict(collections.Counter(r[2] for r in out)), '| access', dict(collections.Counter(r[4] for r in out)))
    print('wrote', OUT, os.path.getsize(OUT) // 1024, 'KB')


if __name__ == '__main__':
    main(sys.argv[1])
