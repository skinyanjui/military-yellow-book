-- Monetization foundation. NOT applied automatically and NOT wired to any payment provider.
-- Principle: a commercial subscription is never evidence. Verification is decided only by reviewed
-- evidence rows; a subscription row can fund the review but can never set myb_listings.verified.

create table if not exists public.myb_verification_evidence (
  id            uuid primary key default gen_random_uuid(),
  listing_slug  text not null references public.myb_listings(slug) on delete cascade,
  kind          text not null check (kind in ('business_registry','tax_id','site_visit','certificate','government_listing','other')),
  source_url    text,
  summary       text not null,
  verdict       text not null default 'pending' check (verdict in ('pending','confirmed','rejected','expired')),
  checked_at    timestamptz,
  expires_at    timestamptz,
  reviewer      text,
  created_at    timestamptz not null default now(),
  check (verdict <> 'confirmed' or (checked_at is not null and reviewer is not null and (source_url is not null or kind in ('site_visit','certificate'))))
);
create index if not exists myb_verification_evidence_listing on public.myb_verification_evidence(listing_slug, verdict);

create table if not exists public.myb_subscriptions (
  id                 uuid primary key default gen_random_uuid(),
  owner_id           uuid not null references auth.users(id) on delete cascade,
  listing_slug       text not null references public.myb_listings(slug) on delete cascade,
  product            text not null check (product in ('verification_monthly','sponsored_listing')),
  status             text not null default 'incomplete' check (status in ('incomplete','active','past_due','canceled','expired')),
  provider           text,                       -- e.g. stripe; set by the webhook handler only
  provider_ref       text unique,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index if not exists myb_subscriptions_owner on public.myb_subscriptions(owner_id);

create table if not exists public.myb_sponsorships (
  id            uuid primary key default gen_random_uuid(),
  subscription_id uuid not null references public.myb_subscriptions(id) on delete cascade,
  listing_slug  text not null references public.myb_listings(slug) on delete cascade,
  category      text,                            -- null = any category the listing is in
  starts_at     timestamptz not null,
  ends_at       timestamptz not null,
  approved      boolean not null default false,  -- editorial approval; organic ranking is unaffected
  check (ends_at > starts_at)
);

alter table public.myb_verification_evidence enable row level security;
alter table public.myb_subscriptions         enable row level security;
alter table public.myb_sponsorships          enable row level security;

-- Anyone may read confirmed, unexpired evidence (that is what makes a badge checkable).
create policy evidence_public_confirmed on public.myb_verification_evidence for select to anon, authenticated
  using (verdict = 'confirmed' and (expires_at is null or expires_at > now()));
-- Owners see their own subscriptions; only the service role writes (payment webhooks).
create policy subscriptions_owner_read on public.myb_subscriptions for select to authenticated using (owner_id = (select auth.uid()));
-- Active, approved, in-window sponsorships are public so the app can label them "Sponsored".
create policy sponsorships_public_active on public.myb_sponsorships for select to anon, authenticated
  using (approved and now() between starts_at and ends_at);

-- The single authoritative definition of "verified": reviewed, unexpired, confirmed evidence.
create or replace view public.myb_listing_verification with (security_invoker = true) as
select l.slug,
       exists (select 1 from public.myb_verification_evidence e
               where e.listing_slug = l.slug and e.verdict = 'confirmed' and (e.expires_at is null or e.expires_at > now())) as evidence_confirmed,
       (select max(e.checked_at) from public.myb_verification_evidence e where e.listing_slug = l.slug and e.verdict = 'confirmed') as last_checked_at
from public.myb_listings l;
grant select on public.myb_listing_verification to anon, authenticated;
