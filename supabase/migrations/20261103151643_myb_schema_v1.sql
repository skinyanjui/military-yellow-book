-- Military Yellow Book: tables are prefixed myb_ because this project is shared with Kazi.

create table public.myb_listings (
  slug text primary key check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name text not null check (char_length(name) between 2 and 160),
  category text not null,
  supplier text not null check (char_length(supplier) between 2 and 120),
  city text not null default '',
  country text not null,
  region text not null check (region in ('americas','europe','africa','mideast','asia')),
  unit text not null default 'unit',
  price numeric(12,2) not null default 0 check (price >= 0),
  moq integer not null default 1 check (moq >= 1),
  lead text not null default '',
  certs text[] not null default '{}',
  ships text not null default 'Worldwide',
  verified boolean not null default false,
  years integer not null default 0 check (years >= 0),
  descr text not null default '',
  specs text not null default '',
  contact text not null default '',
  flat text,
  domains text[] not null default '{}',
  branches text[] not null default '{}',
  sample_rating numeric(2,1) check (sample_rating between 0 and 5),
  sample_reviews integer not null default 0 check (sample_reviews >= 0),
  is_sample boolean not null default false,
  status text not null default 'live' check (status in ('live','hidden')),
  owner_id uuid references auth.users(id) on delete set null,
  position integer,
  created_at timestamptz not null default now()
);
create index myb_listings_live_idx on public.myb_listings (status, position);
create index myb_listings_owner_idx on public.myb_listings (owner_id);

create table public.myb_reviews (
  id bigint generated always as identity primary key,
  listing_slug text not null references public.myb_listings(slug) on delete cascade on update cascade,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  author text not null default '' check (char_length(author) <= 60),
  rating smallint not null check (rating between 1 and 5),
  body text not null check (char_length(btrim(body)) between 10 and 1000),
  created_at timestamptz not null default now(),
  unique (listing_slug, user_id)
);
create index myb_reviews_listing_idx on public.myb_reviews (listing_slug, created_at desc);
create index myb_reviews_user_idx on public.myb_reviews (user_id);

create table public.myb_favourites (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  listing_slug text not null references public.myb_listings(slug) on delete cascade on update cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, listing_slug)
);
create index myb_favourites_listing_idx on public.myb_favourites (listing_slug);

create table public.myb_quote_requests (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  listing_slug text references public.myb_listings(slug) on delete set null on update cascade,
  product text not null check (char_length(btrim(product)) between 2 and 200),
  quantity text not null check (char_length(btrim(quantity)) between 1 and 80),
  target_price text check (char_length(target_price) <= 80),
  ship_to text not null check (char_length(btrim(ship_to)) between 2 and 80),
  buyer_name text not null check (char_length(btrim(buyer_name)) between 1 and 100),
  buyer_contact text not null check (char_length(btrim(buyer_contact)) between 3 and 160),
  notes text check (char_length(notes) <= 1000),
  status text not null default 'new' check (status in ('new','sent','closed')),
  created_at timestamptz not null default now()
);
create index myb_quotes_user_idx on public.myb_quote_requests (user_id, created_at desc);
create index myb_quotes_listing_idx on public.myb_quote_requests (listing_slug);

create table public.myb_submissions (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  business_name text not null check (char_length(btrim(business_name)) between 2 and 120),
  category text not null check (char_length(category) <= 80),
  country text not null check (char_length(btrim(country)) between 2 and 80),
  city text not null check (char_length(btrim(city)) between 1 and 80),
  min_order text check (char_length(min_order) <= 80),
  offers text not null check (char_length(btrim(offers)) between 5 and 1000),
  phone text check (char_length(phone) <= 40),
  email text check (char_length(email) <= 160),
  website text check (char_length(website) <= 200),
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  listing_slug text references public.myb_listings(slug) on delete set null on update cascade,
  created_at timestamptz not null default now(),
  check (coalesce(btrim(phone), '') <> '' or coalesce(btrim(email), '') <> '')
);
create index myb_submissions_user_idx on public.myb_submissions (user_id, created_at desc);
create index myb_submissions_listing_idx on public.myb_submissions (listing_slug);

create table public.myb_rate_events (
  user_id uuid not null,
  kind text not null,
  at timestamptz not null default now()
);
create index myb_rate_events_idx on public.myb_rate_events (user_id, kind, at desc);

alter table public.myb_listings enable row level security;
alter table public.myb_reviews enable row level security;
alter table public.myb_favourites enable row level security;
alter table public.myb_quote_requests enable row level security;
alter table public.myb_submissions enable row level security;
alter table public.myb_rate_events enable row level security;

create policy myb_listings_read on public.myb_listings for select to anon, authenticated using (status = 'live');

create policy myb_reviews_read on public.myb_reviews for select to anon, authenticated using (true);
create policy myb_reviews_insert on public.myb_reviews for insert to authenticated with check (user_id = (select auth.uid()));
create policy myb_reviews_delete on public.myb_reviews for delete to authenticated using (user_id = (select auth.uid()));

create policy myb_fav_read on public.myb_favourites for select to authenticated using (user_id = (select auth.uid()));
create policy myb_fav_insert on public.myb_favourites for insert to authenticated with check (user_id = (select auth.uid()));
create policy myb_fav_delete on public.myb_favourites for delete to authenticated using (user_id = (select auth.uid()));

create policy myb_quotes_read on public.myb_quote_requests for select to authenticated using (user_id = (select auth.uid()));
create policy myb_quotes_insert on public.myb_quote_requests for insert to authenticated with check (user_id = (select auth.uid()) and status = 'new');

create policy myb_subs_read on public.myb_submissions for select to authenticated using (user_id = (select auth.uid()));
create policy myb_subs_insert on public.myb_submissions for insert to authenticated with check (user_id = (select auth.uid()) and status = 'pending' and listing_slug is null);

-- Grants: read-only for listings, column-limited inserts for everything users write.
revoke all on public.myb_listings, public.myb_reviews, public.myb_favourites, public.myb_quote_requests, public.myb_submissions, public.myb_rate_events from anon, authenticated;
grant select on public.myb_listings to anon, authenticated;
grant select on public.myb_reviews to anon, authenticated;
grant insert (listing_slug, rating, body) on public.myb_reviews to authenticated;
grant delete on public.myb_reviews to authenticated;
grant select on public.myb_favourites to authenticated;
grant insert (listing_slug) on public.myb_favourites to authenticated;
grant delete on public.myb_favourites to authenticated;
grant select on public.myb_quote_requests to authenticated;
grant insert (listing_slug, product, quantity, target_price, ship_to, buyer_name, buyer_contact, notes) on public.myb_quote_requests to authenticated;
grant select on public.myb_submissions to authenticated;
grant insert (business_name, category, country, city, min_order, offers, phone, email, website) on public.myb_submissions to authenticated;

-- Per-user rate limiting (own table, independent of Kazi's).
create function public.myb_consume_quota(p_user uuid, p_kind text, p_limit integer, p_window interval)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('myb:' || p_kind || ':' || p_user::text, 0));
  if (select count(*) from public.myb_rate_events r where r.user_id = p_user and r.kind = p_kind and r.at > now() - p_window) >= p_limit then
    return false;
  end if;
  insert into public.myb_rate_events (user_id, kind) values (p_user, p_kind);
  return true;
end $$;

create function public.myb_before_review() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  new.author := left(coalesce(nullif(btrim((select u.raw_user_meta_data->>'name' from auth.users u where u.id = new.user_id)), ''), 'Member'), 60);
  if not public.myb_consume_quota(new.user_id, 'review', 10, interval '1 day') then
    raise exception 'review_limit' using hint = 'You have reached today''s review limit. Try again tomorrow.';
  end if;
  return new;
end $$;
create trigger myb_before_review before insert on public.myb_reviews for each row execute function public.myb_before_review();

create function public.myb_before_quote() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if not public.myb_consume_quota(new.user_id, 'quote', 20, interval '1 day') then
    raise exception 'quote_limit' using hint = 'You have sent the maximum number of quote requests for today.';
  end if;
  return new;
end $$;
create trigger myb_before_quote before insert on public.myb_quote_requests for each row execute function public.myb_before_quote();

create function public.myb_before_submission() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if not public.myb_consume_quota(new.user_id, 'submission', 5, interval '1 day') then
    raise exception 'submission_limit' using hint = 'You have reached today''s limit for supplier submissions.';
  end if;
  return new;
end $$;
create trigger myb_before_submission before insert on public.myb_submissions for each row execute function public.myb_before_submission();

-- Owner-only: turn a pending submission into a live listing (run from the SQL editor).
create function public.myb_approve_submission(p_id bigint, p_region text)
returns text language plpgsql security definer set search_path = '' as $$
declare s public.myb_submissions; base text; sl text; n integer := 1;
begin
  select * into s from public.myb_submissions where id = p_id and status = 'pending' for update;
  if s.id is null then raise exception 'submission_not_found_or_not_pending'; end if;
  if p_region not in ('americas','europe','africa','mideast','asia') then raise exception 'bad_region'; end if;
  base := trim(both '-' from regexp_replace(lower(s.business_name), '[^a-z0-9]+', '-', 'g'));
  if base = '' then raise exception 'bad_name'; end if;
  sl := base;
  while exists (select 1 from public.myb_listings where slug = sl) loop n := n + 1; sl := base || '-' || n; end loop;
  insert into public.myb_listings (slug, name, category, supplier, city, country, region, unit, price, moq, lead, certs, ships, verified, years, descr, specs, contact, flat, domains, branches, status, owner_id)
  values (sl, left(s.business_name, 160), s.category, s.business_name, s.city, s.country, p_region, 'unit', 0, 1, 'Ask supplier', '{}', 'Ask supplier', false, 0, s.offers,
          'Minimum order:' || coalesce(nullif(btrim(s.min_order), ''), 'Ask supplier'), coalesce(nullif(btrim(s.email), ''), s.phone, ''), 'Quote-based', '{joint}', '{joint}', 'live', s.user_id);
  update public.myb_submissions set status = 'approved', listing_slug = sl where id = p_id;
  return sl;
end $$;

revoke execute on function public.myb_consume_quota(uuid, text, integer, interval) from public, anon, authenticated;
revoke execute on function public.myb_before_review() from public, anon, authenticated;
revoke execute on function public.myb_before_quote() from public, anon, authenticated;
revoke execute on function public.myb_before_submission() from public, anon, authenticated;
revoke execute on function public.myb_approve_submission(bigint, text) from public, anon, authenticated;
