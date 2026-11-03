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
| `site/` | The deployable bundle: `index.html`, `vercel.json`, `og.png` (share image), `robots.txt` and `vendor/` (self-hosted supabase-js, so no third-party script runs). This is what Vercel serves. |
| `supabase/migrations/` | Schema for the `myb_*` tables, RLS policies, grants, triggers, RPCs and the audit follow-ups. |
| `supabase/seed.json` | The 103 sample listings loaded into `myb_listings`. |
| `docs/AUDIT.md` | Findings and status of the November 2026 site and flow audit. |

With no `window.MYB_BACKEND` set, the site runs entirely from its embedded data. With it set, listings, sign-in, favourites, reviews, quote requests and supplier submissions all go through Supabase.

## Build and deploy

```sh
python3 scripts/build_deploy.py      # needs Python 3 and npx (esbuild); rewrites site/
SITE_URL=https://your-domain.example python3 scripts/build_deploy.py   # when the canonical URL changes
```

The page ships with a strict Content-Security-Policy that allows only the two inline scripts by hash. Any change to the JS changes those hashes, so always rebuild with the script (it rewrites `site/vercel.json` too) and commit both files together.

The Vercel project is connected to this repo with Root Directory `site`, so every push to `main` deploys to production automatically and other branches get preview URLs. Commit the rebuilt `site/` along with any change to `src/`, because Vercel serves `site/` as-is and runs no build.

## Backend

Supabase tables: `myb_listings`, `myb_reviews`, `myb_favourites`, `myb_quote_requests`, `myb_submissions`, `myb_rate_events`. Every table has row-level security. Writes go through column-level grants and per-user rate limiting, and the admin functions have `execute` revoked from `anon` and `authenticated`.

Notes:

- The site reads `myb_listings` with an explicit column list. `anon` and `authenticated` have column-level SELECT on it that omits `owner_id`, so a `select=*` from outside the site is refused. When you add a column the site should read, `grant select (new_column) on public.myb_listings to anon, authenticated;` in a migration.
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
- Listings open on hash routes (`#biz-<slug>`), which search engines do not index. Per-listing static pages would fix that.
- This project shares a Supabase project with another app (every sign-up here also creates a `profiles` row there). Moving the Yellow Book to its own project is the clean long-term fix.
