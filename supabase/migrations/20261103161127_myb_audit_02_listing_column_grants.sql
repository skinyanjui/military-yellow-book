-- Hide myb_listings.owner_id from the public API roles.
-- Table-level SELECT is replaced by a column list that omits owner_id; RLS (status = 'live') still applies.
-- The site always selects explicit columns. Any column added later must be granted here on purpose.
revoke select on public.myb_listings from anon, authenticated;
grant select (
  slug, name, category, supplier, city, country, region, unit, price, moq, lead, certs, ships,
  verified, years, descr, specs, contact, flat, domains, branches, sample_rating, sample_reviews,
  is_sample, status, position, created_at, review_count, rating_avg
) on public.myb_listings to anon, authenticated;
