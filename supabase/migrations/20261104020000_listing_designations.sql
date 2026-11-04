-- SAM.gov-style socioeconomic designations and federal identifiers.
-- Principle: a designation is a CLAIM until checked. designations_basis says who stands behind it:
--   self_reported = the supplier said so; sam_gov = confirmed against the supplier's active SAM.gov registration
-- on designations_checked_at. The UI shows the basis and never calls a self-reported designation verified.
alter table public.myb_listings
  add column if not exists designations text[] not null default '{}',
  add column if not exists designations_basis text not null default 'self_reported',
  add column if not exists designations_checked_at timestamptz,
  add column if not exists uei text,
  add column if not exists cage_code text;
alter table public.myb_listings drop constraint if exists myb_listings_designations_check;
alter table public.myb_listings add constraint myb_listings_designations_check check (
  designations <@ array['sdvosb','vosb','wosb','edwosb','8a','hubzone','small_business','sdb','minority_owned','tribal','anc','nhoo']::text[]
  and designations_basis in ('self_reported','sam_gov')
  and (designations_basis <> 'sam_gov' or (designations_checked_at is not null and uei is not null))
  and (uei is null or uei ~ '^[A-Z0-9]{12}$')
  and (cage_code is null or cage_code ~ '^[A-Z0-9]{5}$'));
grant select (designations, designations_basis, designations_checked_at, uei, cage_code) on public.myb_listings to anon, authenticated;

-- Demonstration only: the six US sample listings carry invented, self-reported designations so the UI can be seen.
-- They remain samples; nothing here is a SAM.gov confirmation.
with us as (select slug, row_number() over (order by position nulls last, slug) rn from public.myb_listings where is_sample and country = 'United States')
update public.myb_listings l set designations = case us.rn
  when 1 then array['sdvosb','small_business'] when 2 then array['minority_owned','small_business'] when 3 then array['tribal','8a']
  when 4 then array['wosb','small_business'] when 5 then array['hubzone','small_business'] else array['vosb'] end
from us where l.slug = us.slug;
