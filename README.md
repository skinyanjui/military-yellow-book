# Military Yellow Book

The global directory of military suppliers: uniforms, boots, field gear, rations, vehicles, aircraft parts, naval, optics, communications, armor and protective gear, unmanned systems and more. Browse by domain, branch, category, region and country, open an Alibaba-style details page for any listing, request quotes, and submit a supplier for listing.

**Live:** https://military-yellow-book.vercel.app

> **All 103 listings are invented samples** and are flagged as such in the UI. Real suppliers need licence verification before they are listed. The directory deliberately carries no complete firearms, ammunition, explosives or weapon systems, and weapon-related parts are accessories only, shown as "Licensed buyers".

## How it is built

A single-file vanilla-JS site, backed by Supabase and hosted on Vercel.

| Path | What it is |
| --- | --- |
| `src/index.html` | Full source: markup, CSS, JS and the embedded sample data. Also works standalone with no backend. |
| `scripts/build_deploy.py` | Strips the embedded data, minifies CSS/JS with esbuild, injects the Supabase config and writes `site/`. |
| `site/` | The deployable bundle (`index.html`, `vercel.json`). This is what Vercel serves. |
| `supabase/migrations/` | Schema for the `myb_*` tables, RLS policies, grants, triggers and RPCs. |
| `supabase/seed.json` | The 103 sample listings loaded into `myb_listings`. |

With no `window.MYB_BACKEND` set, the site runs entirely from its embedded data. With it set, listings, sign-in, favourites, reviews, quote requests and supplier submissions all go through Supabase.

## Build and deploy

```sh
python3 scripts/build_deploy.py      # needs Python 3 and npx (esbuild)
cd site && vercel deploy --prod      # or set the Vercel project's Root Directory to `site`
```

## Backend

Supabase tables: `myb_listings`, `myb_reviews`, `myb_favourites`, `myb_quote_requests`, `myb_submissions`, `myb_rate_events`. Every table has row-level security. Writes go through column-level grants and per-user rate limiting, and the admin functions have `execute` revoked from `anon` and `authenticated`.

The publishable key in `site/index.html` is safe to expose. Never commit a service-role key.

Approve a supplier submission:

```sql
select myb_approve_submission(<id>, '<region>');  -- americas | europe | africa | mideast | asia
```

## Before launch

- Add the live URL under Supabase Authentication → URL Configuration → Redirect URLs.
- Configure custom SMTP: Supabase's built-in sender is heavily rate-limited.
- Quote requests are saved but not yet emailed to suppliers.
