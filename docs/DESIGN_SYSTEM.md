# Design system and workspace UI

Direction: Notion (content first), Geist (precision, neutral colour), Linear (compact, keyboard first). The homepage is the tool: no hero, no counters, no marketing copy.

## Where things live
| What | File |
|---|---|
| Tokens, components, shell (single source of truth) | `src/assets/ui.css` → `/assets/ui.css` |
| Directory app (rows, grid, filters, details, auth, quotes, favourites) | `src/index.html` (built by `scripts/build_deploy.py`) |
| Tenders, contract awards, portals (static, searchable tables) | `scripts/build_pages.py` + `src/assets/table.js` |
| Listing, category, directory, legal pages | `scripts/build_pages.py` (own small stylesheet, same palette) |

## Tokens (light and dark, semantic)
`--bg #fff`, `--surface #f7f7f5`, `--border #e9e9e7`, `--text #37352f`, `--text-2 #787774`, `--accent #f5b800`; Inter; 4 px spacing scale `--s-1…--s-12`; radii 4/6/8; controls 32 px (40 px on coarse pointers); minimal shadow only on popovers. Dark values redefine the same names (`prefers-color-scheme` and `[data-theme]`). Legacy variable names are aliased so older rules keep working.

## Shell
Top bar (brand, dominant search with ⌘/Ctrl+K and `/`, Saved, Account) → one filter + sort row → results. Collapsible sidebar (Discover suppliers, Saved suppliers, Tenders, Contract awards, Procurement portals, Account and business); drawer below 1024 px. Filters live only in that row; "More filters" opens the remaining ones. State is in the URL (`q`, `cat`, `country`, `region`, `domain`, `branch`, `price`, `moq`, `lead`, `years`, `access`, `verified`, `custom`, `rating`, `saved`, `sort`, `view`). Legacy `#cat-<slug>` and `#biz-<slug>` URLs still work. Opening a supplier and going back restores filters and scroll.

## Honesty rules (enforced in code)
- All current listings are samples: the UI shows **Sample**, never **Verified**, for any listing with `is_sample` (see `fromRow`). Verified only appears for a non-sample listing with `verified = true`.
- No invented supplier performance figures (the old "response time / on-time delivery" tiles were removed).
- Tenders and awards come only from `myb_opportunities` (operational, licence-cleared sources). Blank means the publisher did not state it. Tender status is derived from the stated deadline in the visitor's clock.
- Portals are all "Reference, unverified": no link-by-link check or verification date exists, so none is claimed. Entries needing a check are flagged.

## Monetization foundation
`supabase/migrations/20261104000000_monetization_foundation.sql` (committed, **not applied**, no payment UI): evidence rows decide verification (`myb_listing_verification`); subscriptions (`myb_subscriptions`) and sponsorships (`myb_sponsorships`) are separate commercial records written only by a future payment webhook (service role). Payment can fund a review but can never set `verified`. Sponsored rows must be rendered with a visible "Sponsored" badge (`.badge-sponsored` exists). Nothing in the UI claims a working payment or paid verification.

## Accessibility
Skip link, landmarks, `aria-sort` on sortable headers, `aria-live` result counts, visible focus rings, 40 px touch targets on coarse pointers, `prefers-reduced-motion`, inert closed drawer, axe: 0 violations on the directory, tenders, awards and portals pages in light and dark.

## Listing photos
`myb_listings.images` (text[], max 8, https only) holds public URLs in the `listing-images` Supabase bucket (public read, 5 MB, jpeg/png/webp, authenticated users may write only inside their own `<uid>/` folder). The app accepts only URLs under that bucket's public path (anything else is dropped) and the CSP `img-src` allows only that path. The details page shows a gallery when a listing has photos and an honest "No photos yet" note otherwise; grid cards use the first photo. No photo is generated or taken from stock sources: all 103 sample listings currently have none. Migration: `supabase/migrations/20261104010000_listing_images.sql` (applied). There is no upload UI yet.

## Ownership designations (SAM.gov style)
`myb_listings.designations` holds codes from a fixed list: `sdvosb`, `vosb`, `wosb`, `edwosb`, `8a`, `hubzone`, `small_business`, `sdb`, `minority_owned` (MBE), `tribal`, `anc`, `nhoo`; plus `uei` (12 chars) and `cage_code` (5 chars). `designations_basis` is `self_reported` (default) or `sam_gov`; `sam_gov` is only allowed with a UEI and a `designations_checked_at` date (enforced by a CHECK). The UI shows them as small outlined tags under the supplier name (hover for the full name and basis), as an "Ownership" filter in the filter row (URL param `desig`), and in an "Ownership and registration" section on the details page that states the basis. Self-reported designations are never styled as verified. The six US sample listings carry invented, self-reported designations for demonstration; they remain samples. Confirming against SAM.gov needs a SAM.gov API key and is not built yet. Migration: `20261104020000_listing_designations.sql` (applied).
