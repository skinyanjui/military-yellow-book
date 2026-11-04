-- Supplier logo: a public URL in the listing-images bucket (validated client-side against the bucket prefix).
alter table public.myb_listings add column if not exists logo text;
alter table public.myb_listings drop constraint if exists myb_listings_logo_check;
alter table public.myb_listings add constraint myb_listings_logo_check check (logo is null or (logo ~ '^https://' and char_length(logo) <= 500));
grant select (logo) on public.myb_listings to anon, authenticated;
