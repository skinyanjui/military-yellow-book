-- Military Yellow Book audit, step 1 (additive, safe to deploy before the site change).
-- 1) Real review aggregates on listings, kept current by a trigger.
alter table public.myb_listings
  add column if not exists review_count integer not null default 0 check (review_count >= 0),
  add column if not exists rating_avg numeric(3,2) check (rating_avg between 1 and 5);

create or replace function public.myb_refresh_rating()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare s text := case when tg_op = 'DELETE' then old.listing_slug else new.listing_slug end;
begin
  update public.myb_listings l set
    review_count = (select count(*) from public.myb_reviews r where r.listing_slug = s),
    rating_avg   = (select round(avg(r.rating)::numeric, 2) from public.myb_reviews r where r.listing_slug = s)
  where l.slug = s;
  return null;
end
$$;
revoke all on function public.myb_refresh_rating() from public, anon, authenticated;

drop trigger if exists myb_reviews_rating on public.myb_reviews;
create trigger myb_reviews_rating
  after insert or update or delete on public.myb_reviews
  for each row execute function public.myb_refresh_rating();

update public.myb_listings l set
  review_count = coalesce(x.n, 0),
  rating_avg = x.avg
from (select listing_slug, count(*) n, round(avg(rating)::numeric, 2) avg from public.myb_reviews group by 1) x
where l.slug = x.listing_slug;

-- 2) myb_rate_events is server-only: say so explicitly with a deny-all policy.
drop policy if exists myb_rate_events_deny_all on public.myb_rate_events;
create policy myb_rate_events_deny_all on public.myb_rate_events
  for all to anon, authenticated using (false) with check (false);

-- 3) Keep the rate-limit ledger small: prune entries older than 7 days every night (quota windows are 1 day).
do $$ begin perform cron.unschedule('myb-prune-rate-events'); exception when others then null; end $$;
select cron.schedule('myb-prune-rate-events', '17 3 * * *', $cron$delete from public.myb_rate_events where at < now() - interval '7 days'$cron$);
