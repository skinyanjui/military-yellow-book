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
