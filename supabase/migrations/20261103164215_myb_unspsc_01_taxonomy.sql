-- UNSPSC taxonomy (UNGM export of 3 Nov 2026) and per-listing classification.
-- Data is loaded separately: supabase/loaders/unspsc_load.sql.
-- access: open = listable; licensed = listable, buyers need an export/end-user licence (shown as such);
--         blocked = complete weapons, ammunition, explosives, ballistic armour, night-vision/thermal: can never be listed.

create table public.myb_unspsc_groups (
  letter text primary key check (letter ~ '^[A-Z]$'),
  title  text not null
);

create table public.myb_unspsc (
  code        text primary key check (code ~ '^[0-9]{8}$'),
  title       text not null check (length(title) between 1 and 300),
  level       smallint not null check (level between 1 and 4),   -- 1 segment, 2 family, 3 class, 4 commodity
  parent_code text references public.myb_unspsc (code),
  ungm_group  text references public.myb_unspsc_groups (letter),
  access      text not null check (access in ('open', 'licensed', 'blocked')),
  note        text
);
create index myb_unspsc_parent_idx      on public.myb_unspsc (parent_code);
create index myb_unspsc_group_idx       on public.myb_unspsc (ungm_group);
create index myb_unspsc_code_prefix_idx on public.myb_unspsc (code text_pattern_ops);
create index myb_unspsc_title_trgm_idx  on public.myb_unspsc using gin (title extensions.gin_trgm_ops);

-- which UNSPSC families/classes usually belong to each directory category (used to suggest codes in the supplier form)
create table public.myb_category_unspsc (
  category text not null,
  code     text not null references public.myb_unspsc (code),
  primary key (category, code)
);
create index myb_category_unspsc_code_idx on public.myb_category_unspsc (code);

alter table public.myb_unspsc_groups   enable row level security;
alter table public.myb_unspsc          enable row level security;
alter table public.myb_category_unspsc enable row level security;
create policy myb_unspsc_groups_read   on public.myb_unspsc_groups   for select to anon, authenticated using (true);
create policy myb_unspsc_read          on public.myb_unspsc          for select to anon, authenticated using (true);
create policy myb_category_unspsc_read on public.myb_category_unspsc for select to anon, authenticated using (true);
revoke all on public.myb_unspsc_groups, public.myb_unspsc, public.myb_category_unspsc from anon, authenticated;
grant select on public.myb_unspsc_groups, public.myb_unspsc, public.myb_category_unspsc to anon, authenticated;

-- classification on listings and submissions
alter table public.myb_listings    add column unspsc text[] not null default '{}';
alter table public.myb_submissions add column unspsc text[] not null default '{}';
create index myb_listings_unspsc_gin on public.myb_listings using gin (unspsc);
grant select (unspsc) on public.myb_listings to anon, authenticated;          -- the site reads listings by explicit column list
grant select (unspsc), insert (unspsc) on public.myb_submissions to authenticated;

-- every stored code must exist, be a class or commodity (level 3-4) and not be blocked; at most 5, de-duplicated
create function public.myb_validate_unspsc() returns trigger
language plpgsql set search_path = '' as $$
declare bad text;
begin
  new.unspsc := array(select c from unnest(coalesce(new.unspsc, '{}'::text[])) with ordinality t(c, o) group by c order by min(o));
  if cardinality(new.unspsc) > 5 then
    raise exception 'too_many_unspsc' using hint = 'Choose at most 5 UNSPSC codes.';
  end if;
  select c into bad from unnest(new.unspsc) c
   where not exists (select 1 from public.myb_unspsc u where u.code = c and u.level >= 3 and u.access <> 'blocked')
   limit 1;
  if bad is not null then
    raise exception 'bad_unspsc' using hint = 'Code ' || bad || ' is not a listable UNSPSC class or commodity.';
  end if;
  return new;
end $$;
revoke execute on function public.myb_validate_unspsc() from public, anon, authenticated;

create trigger myb_listings_validate_unspsc    before insert or update of unspsc on public.myb_listings
  for each row execute function public.myb_validate_unspsc();
create trigger myb_submissions_validate_unspsc before insert or update of unspsc on public.myb_submissions
  for each row execute function public.myb_validate_unspsc();

-- approval now carries the classification over to the listing
create or replace function public.myb_approve_submission(p_id bigint, p_region text)
returns text language plpgsql security definer set search_path = '' as $function$
declare s public.myb_submissions; base text; sl text; n integer := 1;
begin
  select * into s from public.myb_submissions where id = p_id and status = 'pending' for update;
  if s.id is null then raise exception 'submission_not_found_or_not_pending'; end if;
  if p_region not in ('americas','europe','africa','mideast','asia') then raise exception 'bad_region'; end if;
  base := trim(both '-' from regexp_replace(lower(s.business_name), '[^a-z0-9]+', '-', 'g'));
  if base = '' then raise exception 'bad_name'; end if;
  sl := base;
  while exists (select 1 from public.myb_listings where slug = sl) loop n := n + 1; sl := base || '-' || n; end loop;
  insert into public.myb_listings (slug, name, category, supplier, city, country, region, unit, price, moq, lead, certs, ships, verified, years, descr, specs, contact, flat, domains, branches, status, owner_id, unspsc)
  values (sl, left(s.business_name, 160), s.category, s.business_name, s.city, s.country, p_region, 'unit', 0, 1, 'Ask supplier', '{}', 'Ask supplier', false, 0, s.offers,
          'Minimum order:' || coalesce(nullif(btrim(s.min_order), ''), 'Ask supplier'), coalesce(nullif(btrim(s.email), ''), s.phone, ''), 'Quote-based', '{joint}', '{joint}', 'live', s.user_id, s.unspsc);
  update public.myb_submissions set status = 'approved', listing_slug = sl where id = p_id;
  return sl;
end $function$;
