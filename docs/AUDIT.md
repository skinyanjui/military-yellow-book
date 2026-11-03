# Site and flow audit, 3 November 2026

Scope: the live site (https://military-yellow-book.vercel.app), every signed-in and signed-out flow, and the Supabase project behind it. Tested in real Chromium at desktop and 400 px mobile widths, against production. All test accounts and rows were deleted afterwards.

## Result

All 18 flow steps pass on production with no uncaught errors and no CSP violations. The 33 database permission checks pass. No security advisor finding touches a `myb_*` object.

## Fixed

| Area | Before | After |
| --- | --- | --- |
| Layout shift on load | CLS 1.049 (page jumped when listings arrived) | CLS 0.026; skeleton cards reserve the space |
| Accessibility | Findings fixed in the audit commit (`632adc2`) | axe-core 4.10.2: 0 violations; mobile has no horizontal scroll |
| Security headers | Hardened in the audit commit | Strict CSP (`default-src 'none'`, the two inline scripts allowed by SHA-256 hash), Permissions-Policy, `nosniff`, Referrer-Policy, `X-Frame-Options: SAMEORIGIN` |
| Third-party code | Script came from outside the site | supabase-js is self-hosted in `site/vendor/` with an immutable cache; the CSP allows no third-party script |
| SEO and sharing | No description or share card | Description, canonical URL, Open Graph and Twitter tags, `og.png`, `robots.txt` |
| Ratings | Always the sample rating | Real reviews drive the shown rating and count (trigger keeps `review_count` and `rating_avg` current); deleting the last review reverts to the sample rating |
| Form errors | Some errors only in a toast | Inline `role="alert"` message inside the dialog; the toast is moved into the open dialog so it is not hidden behind it |
| Network failures | Could read as a generic "could not save" error | Offline and unreachable-server cases say so and leave the form usable |
| Unknown listing link | No explanation | A clear "not found" message |
| Password-reset dialog | Uncaught `TypeError` if you left the dialog while the request was in flight (reproduced, fixed in `3f62945`) | No error; late replies are ignored |
| `owner_id` on listings | Readable by anyone through the API | Column-level SELECT omits it (migration `myb_audit_02`) |
| Rate-limit ledger | Grew without bound | Pruned daily by pg_cron job `myb-prune-rate-events`; explicit deny-all policy added |

## Flows exercised on production

Signed out: request-a-quote gate, wrong password message, reset-password dialog, sign-up validation. Signed in: sign-in resumes the pending quote request with the form prefilled; empty and valid quote submit (a double-click sends one request); review with an HTML/script payload renders as text and never executes; review persists across reload; deleting a review reverts the rating; favourite on and off, persisted to the server and restored after signing out and back in; sign-out clears local favourites and the session; supplier submission (empty and valid, double-click sends one); offline submit shows an inline error and re-enables the button; dialogs fit a 366 px wide phone without overflow.

## Database permission checks (33)

Checked with the publishable key and two real users over the REST API: anonymous users cannot read quotes, the rate ledger or admin functions; a user cannot forge another user's `user_id`, set review `author`, change a quote or submission status, or write to listings; user B cannot read or delete user A's quotes, favourites, submissions or reviews; check constraints reject a rating of 6, a too-short review and an oversize product; the foreign key rejects a review on a missing listing; a duplicate review returns 409; the daily quote limit blocks request 21 with a user-facing message; a forged JWT is rejected; `owner_id` is now refused.

## Still open

- **Dashboard settings** (not changeable from code): add the live URL to Auth redirect URLs, configure custom SMTP, turn on CAPTCHA, set a password minimum of 8 or more, enable leaked-password protection (the advisor flags this).
- **Email delivery** to ordinary inboxes is unverified because Supabase is not yet using Resend SMTP. Send a real test signup after setting it up.
- **Crawlability**: fixed after the audit. Every listing and category now has a static page, there is a sitemap, and an Action keeps them current (see the README). Submit the sitemap to Google Search Console and Bing.
- **Shared Supabase project**: sign-ups here also create a row in the other app's `profiles` table. Its advisor notes were left untouched: six `SECURITY DEFINER` functions callable by signed-in users (`delete_job`, `is_moderator`, `moderate_report`, `my_applied_job_ids`, `restore_job`, `withdraw_application`), two tables with RLS and no policy (`moderator_emails`, `rate_events`), plus performance notes on its `jobs` policies and unused indexes.
- **Accepted**: reviewer `user_id` is public on `myb_reviews`.
- **Process**: `site/` is rebuilt and committed by the `rebuild-site` GitHub Action on source changes and daily.
- **Quotes** are stored but not emailed to suppliers yet.

## Update: UNSPSC, procurement portals and sign-up (3 November 2026, evening)

- **UNSPSC taxonomy** loaded from the UNGM export: 13,482 codes in 10 groups (11,601 open, 1,826 licensed, 55 blocked). Blocked is enforced by a database trigger, not only by the picker. All 103 sample listings carry 1-3 reviewed codes; none is blocked.
- **Site**: listing pages (app and static) show the codes with titles and a licence note; search matches codes, code prefixes and code titles; the "List your business" form has a code picker (typeahead, up to 5, never offers a blocked code, ranks the chosen category's codes first); category pages list typical codes.
- **Procurement portals**: 240 entries from Sell to State (193 countries), Open Opps (feeds, state and international sources), RICG (platform types) and the VA NAC catalogue, on a new `/portals` page with sources credited. Links are unverified; 31 are flagged.
- **Sign-up flow**: a resend-confirmation button on "email not confirmed" and on the "check your email" notice, an "Email confirmed" message when the link is opened, the interrupted action (list a business, request a quote) resumes after confirmation, and a consent line links to new `/terms` and `/privacy` pages. Share now copies the crawlable `/l/<slug>` address. Unknown addresses get a branded 404.
- **Checks**: 121 browser checks pass (static pages at desktop and 400 px, light and dark: no axe violations, no overflow, no CSP violations; app flows with mocked auth). Database checks: a blocked code, a family-level code, a missing code and a sixth code are each rejected; duplicates are collapsed; anonymous users can read the reference tables but not write to them.
- **Open**: Terms and Privacy need a lawyer's review and a contact address (`SITE_CONTACT`); no account-deletion flow; the dashboard settings above are still pending.
