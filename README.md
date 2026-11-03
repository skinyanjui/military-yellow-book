# Military Yellow Book

The global directory of military suppliers: uniforms, boots, field gear, rations, vehicles, aircraft parts, naval, optics, communications, armor and protective gear, unmanned systems and more. Browse by domain, branch, category, region and country, open an Alibaba-style details page for any listing, request quotes, and submit a supplier for listing.

**Live:** https://military-yellow-book.vercel.app

> **All 103 listings are invented samples** and are flagged as such in the UI. Real suppliers need licence verification before they are listed. The directory deliberately carries no complete firearms, ammunition, explosives or weapon systems, and weapon-related parts are accessories only, shown as "Licensed buyers".

## How it is built

A single-file vanilla-JS site, backed by Supabase and hosted on Vercel.

| Path | What it is |
| --- | --- |
| `src/index.html` | Full source: markup, CSS, JS and the embedded sample data. Also works standalone with no backend. |
| `scripts/build_deploy.py` | Strips the embedded data, minifies CSS/JS with esbuild, injects the Supabase config, adds SEO/Open Graph tags and writes `site/index.html` and `site/vercel.json` (security headers, CSP hashes). |
| `scripts/build_pages.py` | Called by the build. Writes a crawlable static page for every live listing (`/l/<slug>`), every category (`/c/<category>`), an all-listings index (`/directory`), the government procurement portals page (`/portals`), `/terms`, `/privacy`, a branded `404.html`, `sitemap.xml` and `robots.txt`. Reads listings and portals from Supabase, with `supabase/seed.json` and `supabase/portals.json` as the fallback. |
| `scripts/unspsc/` | Builds the UNSPSC taxonomy from the UNGM export, maps directory categories to codes, and holds the reviewed codes for the 103 sample listings (see its README). |
| `scripts/portals/` | Merges the government-procurement-portal lists (Sell to State, Open Opps, RICG, VA NAC) into `supabase/portals.json`. |
| `.github/workflows/rebuild-site.yml` | Rebuilds and commits `site/` when `src/` or the scripts change, and once a day so newly approved suppliers get a page. |
| `site/` | The deployable bundle: `index.html`, `vercel.json`, `og.png` (share image), `robots.txt`, `sitemap.xml`, the static pages in `l/` and `c/`, `directory.html`, and `vendor/` (self-hosted supabase-js, so no third-party script runs). This is what Vercel serves. |
| `supabase/migrations/` | Schema for the `myb_*` tables, RLS policies, grants, triggers, RPCs and the audit follow-ups. |
| `supabase/seed.json` | The 103 sample listings loaded into `myb_listings`. |
| `supabase/unspsc.json`, `supabase/listing_unspsc.json`, `supabase/portals.json` | Source data for the UNSPSC tables, the per-listing codes and the portals table. |
| `supabase/loaders/` | One-off SQL that loads those files into Supabase (the database fetches the JSON from GitHub, pinned to a commit). |
| `docs/AUDIT.md` | Findings and status of the November 2026 site and flow audit. |

With no `window.MYB_BACKEND` set, the site runs entirely from its embedded data. With it set, listings, sign-in, favourites, reviews, quote requests and supplier submissions all go through Supabase.

## Build and deploy

```sh
python3 scripts/build_deploy.py      # needs Python 3 and npx (esbuild); rewrites site/
SITE_URL=https://your-domain.example python3 scripts/build_deploy.py   # when the canonical URL changes
```

The page ships with a strict Content-Security-Policy that allows only the two inline scripts by hash. Any change to the JS changes those hashes, so always rebuild with the script (it rewrites `site/vercel.json` too) and commit both files together. The GitHub Action does this for you if you only push `src/` changes; the build is deterministic (esbuild is pinned), so a run with nothing new commits nothing.

`PAGES_SOURCE` picks where the static pages get their listings: unset tries Supabase and falls back to `supabase/seed.json` with a warning; `live` fails the build if Supabase can't be read (the Action uses this, so an outage never replaces real pages with stale ones); `seed` uses the seed file only.

GitHub pauses scheduled workflows after 60 days without repository activity; re-enable it from the Actions tab if that happens.

The Vercel project is connected to this repo with Root Directory `site`, so every push to `main` deploys to production automatically and other branches get preview URLs. Commit the rebuilt `site/` along with any change to `src/`, because Vercel serves `site/` as-is and runs no build.

## Backend

Supabase tables: `myb_listings`, `myb_reviews`, `myb_favourites`, `myb_quote_requests`, `myb_submissions`, `myb_rate_events`, plus the reference tables `myb_unspsc_groups`, `myb_unspsc` (13,482 codes), `myb_category_unspsc` and `myb_portals` (240 procurement portals). The reference tables are read-only for everyone except the database owner. Every table has row-level security. Writes go through column-level grants and per-user rate limiting, and the admin functions have `execute` revoked from `anon` and `authenticated`.

Notes:

- The site reads `myb_listings` with an explicit column list. `anon` and `authenticated` have column-level SELECT on it that omits `owner_id`, so a `select=*` from outside the site is refused. When you add a column the site should read, `grant select (new_column) on public.myb_listings to anon, authenticated;` in a migration.
- **UNSPSC classification.** `myb_listings.unspsc` and `myb_submissions.unspsc` hold up to 5 codes. A trigger rejects a code that does not exist, is a segment or family (level 1-2), or is `blocked`. `myb_unspsc.access` is `open`, `licensed` (listable; shown with a licence note) or `blocked` (complete weapons, ammunition, explosives, ballistic armour, night-vision and thermal gear: never listable). The rules live in `scripts/unspsc/build_unspsc.py`; change them there, regenerate `supabase/unspsc.json` and reload. `myb_approve_submission` copies a submission's codes to the new listing.
- Displayed ratings come from real reviews once a listing has any: `myb_reviews` has a trigger that keeps `review_count` and `rating_avg` on `myb_listings` current. Until then the sample rating is shown.
- `myb_rate_events` (the rate-limit ledger) is pruned daily by the pg_cron job `myb-prune-rate-events`.
- Reviewer `user_id` is publicly readable on `myb_reviews` (used to show a Delete button on your own review). That is a known, accepted exposure.

The publishable key in `site/index.html` is safe to expose. Never commit a service-role key.

Approve a supplier submission:

```sql
select myb_approve_submission(<id>, '<region>');  -- americas | europe | africa | mideast | asia
```

## Before launch

These are dashboard settings that cannot be changed from code:

- Add `https://military-yellow-book.vercel.app/**` under Supabase Authentication → URL Configuration → Redirect URLs, so confirmation and password-reset links return to the site.
- Configure custom SMTP (for example Resend) and send a real test signup. Supabase's built-in sender is heavily rate-limited and only delivers to team addresses.
- Turn on CAPTCHA for sign-up, raise the minimum password length to 8 or more, and enable leaked-password protection.
- Quote requests are saved but not yet emailed to suppliers.
- After the first deploy with the sitemap, submit `https://military-yellow-book.vercel.app/sitemap.xml` in Google Search Console and Bing Webmaster Tools. Listings carry a "Sample listing" label; indexing invented suppliers is fine for a demo, but remove or noindex the sample pages before real suppliers go live if you do not want them in search results.
- This project shares a Supabase project with another app (every sign-up here also creates a `profiles` row there). Moving the Yellow Book to its own project is the clean long-term fix.
- **Terms and Privacy** (`/terms`, `/privacy`) are drafts, flagged as such on the page (`LEGAL_DRAFT` in `scripts/build_pages.py`). Have a lawyer review them, then set it to `False`. Set the repository variable `SITE_CONTACT` (Settings > Secrets and variables > Actions > Variables) to the address people should write to; until you do, neither page shows a contact, and the privacy text points people to "the site operator". There is also no self-service account deletion yet.
- **Portal links** on `/portals` are unverified (the build sandbox cannot reach them). 31 are flagged where the address looks like a general government or commercial site.

## Procurement data and open tenders

The site's `/opportunities` page lists open government tenders and recent contract awards taken from official publishers that have passed
record-by-record checks and whose licence allows reuse. How the data is collected and verified: [docs/PROCUREMENT_PLATFORM.md](docs/PROCUREMENT_PLATFORM.md).
What is covered and what is not: [docs/SOURCE_COVERAGE.md](docs/SOURCE_COVERAGE.md).
