# UNSPSC data

`supabase/unspsc.json` is generated from the UNGM UNSPSC export (Excel, 3 Nov 2026) by `build_unspsc.py <xlsx>`.
UNSPSC® is the United Nations Standard Products and Services Code (https://www.unspsc.org); the export comes from UNGM (https://www.ungm.org).

Each row: `[code, parent_code, level, ungm_group, access, title, note]` (level 1 segment, 2 family, 3 class, 4 commodity).
`access` is derived by `build_unspsc.py`:

- `blocked`: complete weapons, ammunition, explosives, ballistic armour, night-vision and thermal gear. Never listable (a database trigger rejects it).
- `licensed`: listable, but buyers need an export or end-user licence (weapon accessories, aircraft, pharmaceuticals, and so on).
- `open`: everything else.

`mapping.py` suggests codes per directory category; `overrides.py` holds the hand-reviewed codes for the 103 sample listings;
`tag_listings.py` writes `supabase/listing_unspsc.json`. Load order: migration, then `supabase/loaders/unspsc_load.sql`.
