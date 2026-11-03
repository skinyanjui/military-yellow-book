-- Government procurement portals by country (Sell to State, Open Opps, RICG, VA NAC). Links are unverified; see scripts/portals/build_portals.py.
-- Data is loaded by supabase/loaders/portals_load.sql.
create table public.myb_portals (
  id             bigint generated always as identity primary key,
  scope          text not null check (scope in ('national', 'subnational', 'agency', 'international')),
  country        text not null check (length(country) between 1 and 80),
  region         text check (region in ('americas', 'europe', 'africa', 'mideast', 'asia')),
  name           text not null check (length(name) between 1 and 200),
  url            text check (url ~ '^https?://'),
  feed_url       text check (feed_url ~ '^https://openopps\.com/sources/'),
  platform       text check (platform in ('transactional', 'informative')),
  classification text check (length(classification) <= 60),
  note           text check (length(note) <= 800),
  flag           text check (flag in ('general_site', 'no_url')),
  sources        text[] not null default '{}',
  position       integer not null,
  unique (country, name)
);
create index myb_portals_region_idx on public.myb_portals (region, position);
alter table public.myb_portals enable row level security;
create policy myb_portals_read on public.myb_portals for select to anon, authenticated using (true);
revoke all on public.myb_portals from anon, authenticated;
grant select on public.myb_portals to anon, authenticated;
