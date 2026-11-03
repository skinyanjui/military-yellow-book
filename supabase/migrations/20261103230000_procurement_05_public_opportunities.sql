-- Procurement platform, part 5: the public face. Only records from sources that are operational AND have an established,
-- non-NonCommercial licence are published, each with its publisher, licence and original link. Refreshed daily.

create table if not exists public.myb_opportunities (
  id            text primary key,
  kind          text not null check (kind in ('open_tender', 'award')),
  source_id     text not null,
  title         text,
  buyer         text,
  supplier      text,
  country       text,
  country_name  text,
  amount        numeric,
  currency      text check (currency is null or currency ~ '^[A-Z]{3}$'),
  published_at  timestamptz,
  deadline      timestamptz,
  url           text,
  publisher     text,
  licence       text,
  refreshed_at  timestamptz not null default now()
);
create index if not exists myb_opportunities_kind_idx on public.myb_opportunities (kind, country, deadline);
alter table public.myb_opportunities enable row level security;
drop policy if exists myb_opportunities_read on public.myb_opportunities;
create policy myb_opportunities_read on public.myb_opportunities for select to anon, authenticated using (true);
revoke all on public.myb_opportunities from public, anon, authenticated;
grant select on public.myb_opportunities to anon, authenticated;

create or replace function procurement.publishable_sources() returns setof text
language sql stable set search_path = procurement, public, pg_temp as $$
  select s.source_id from source s
   where s.connector_state = 'operational' and licence_established(s.source_id)
     and coalesce(s.licence, '') !~* 'noncommercial'
     and not exists (select 1 from source_claim c where c.source_id = s.source_id and c.field in ('licence', 'licence_in_records') and c.value ~* 'noncommercial')
$$;

create or replace function procurement.publish_opportunities() returns jsonb
language plpgsql set search_path = procurement, public, pg_temp as $$
declare v_up int; v_del int;
begin
  create temp table _opp on commit drop as
  with ok as (select publishable_sources() as source_id),
  base as (
    select p.*, sr.publisher, sr.licence, sr.source_url, o.name as buyer_name, sr.raw
      from process p join ok on ok.source_id = p.first_source_id
      join source_record sr on sr.id = p.current_record_id
      left join organization o on o.id = p.buyer_org_id)
  select p.first_source_id || ':' || p.ocid as id, 'open_tender'::text as kind, p.first_source_id as source_id, p.title, p.buyer_name as buyer, null::text as supplier,
         p.country, coalesce(p.raw->>'country_name', case p.country when 'GB' then 'United Kingdom' when 'CO' then 'Colombia' end, p.country) as country_name,
         p.value_amount as amount, p.value_currency as currency, p.published_at, p.tender_end as deadline, coalesce(p.source_url, p.url) as url, p.publisher, p.licence
    from base p
   where p.stage = 'tender' and (p.tender_end >= now() or (p.tender_end is null and p.published_at > now() - interval '30 days')) and p.title is not null
  union all
  select p.first_source_id || ':' || p.ocid || ':' || a.award_id, 'award', p.first_source_id, p.title, p.buyer_name, so.name,
         p.country, coalesce(p.raw->>'country_name', case p.country when 'GB' then 'United Kingdom' when 'CO' then 'Colombia' end, p.country),
         coalesce(c.value_amount, a.value_amount), coalesce(c.value_currency, a.value_currency), coalesce(a.date, p.published_at), null, coalesce(p.source_url, p.url), p.publisher, p.licence
    from base p join award a on a.process_id = p.id
    join award_supplier asup on asup.award_pk = a.id join organization so on so.id = asup.org_id
    left join contract c on c.process_id = p.id and c.award_id = a.award_id
   where p.title is not null and coalesce(a.date, p.published_at) > now() - interval '180 days';

  insert into public.myb_opportunities as t (id, kind, source_id, title, buyer, supplier, country, country_name, amount, currency, published_at, deadline, url, publisher, licence, refreshed_at)
  select distinct on (id) id, kind, source_id, left(title, 300), buyer, supplier, country, country_name, amount, currency, published_at, deadline, url, publisher, licence, now() from _opp
  on conflict (id) do update set kind = excluded.kind, title = excluded.title, buyer = excluded.buyer, supplier = excluded.supplier, country = excluded.country,
     country_name = excluded.country_name, amount = excluded.amount, currency = excluded.currency, published_at = excluded.published_at, deadline = excluded.deadline,
     url = excluded.url, publisher = excluded.publisher, licence = excluded.licence, refreshed_at = now();
  get diagnostics v_up = row_count;
  delete from public.myb_opportunities where id not in (select id from _opp);
  get diagnostics v_del = row_count;
  insert into audit_event (action, detail) values ('publish_opportunities', jsonb_build_object('upserted', v_up, 'removed', v_del));
  return jsonb_build_object('upserted', v_up, 'removed', v_del, 'sources', (select jsonb_agg(x) from publishable_sources() x));
end $$;
revoke all on function procurement.publishable_sources(), procurement.publish_opportunities() from public, anon, authenticated;

-- a failed last run shows as failing even before the source is scheduled
create or replace view procurement.v_source_status as
select s.source_id, s.name, s.country, s.parent_source_id, s.source_kind, s.access_class, s.connector, s.connector_state,
       s.verification_status, s.suggested_cadence, s.last_verified_at, s.last_run_at, s.last_success_at, s.crosscheck_passed_at,
       lr.status as last_run_status, lr.error_kind as last_error_kind,
       coalesce(rt.accepted, 0) as run_accepted, coalesce(rt.rejected, 0) as run_rejected,
       coalesce(sr.versions, 0) as source_records, coalesce(pc.processes, 0) as processes,
       case
         when s.connector_state = 'stub_credential_gated' then 'needs_credentials'
         when s.connector_state = 'disabled' then 'disabled'
         when s.connector_state = 'licence_unconfirmed' then 'awaiting_licence'
         when lr.status = 'failed' and s.connector is not null then 'failing'
         when s.connector_state = 'none' and s.connector is null and s.access_class in ('portal_only', 'informational', 'restricted_provider') then 'not_automated'
         when s.connector_state = 'none' and s.connector is null then 'no_connector'
         when s.connector_state = 'none' then 'not_scheduled'
         when s.connector_state = 'failing' or lr.status = 'failed' then 'failing'
         when s.last_success_at is null then 'never_succeeded'
         when s.last_success_at < now() - procurement.cadence_interval(s.suggested_cadence) * 2 then 'stale'
         when s.connector_state = 'operational' then 'healthy'
         else 'awaiting_publisher_check'
       end as health,
       (s.last_verified_at is null or s.verification_status like 'pending%' or s.verification_status like '%require%') as pending_verification
  from procurement.source s
  left join lateral (select status, error_kind from procurement.connector_run r where r.source_id = s.source_id and r.status <> 'running' order by started_at desc limit 1) lr on true
  left join (select source_id, sum(accepted) accepted, sum(rejected) rejected from procurement.connector_run where status <> 'running' group by source_id) rt using (source_id)
  left join (select source_id, count(*) versions from procurement.source_record group by 1) sr using (source_id)
  left join (select first_source_id source_id, count(*) processes from procurement.process group by 1) pc using (source_id);


revoke all on procurement.v_source_status from public, anon, authenticated;

select cron.schedule('myb-publish-opportunities', '50 4 * * *', $c$select procurement.publish_opportunities()$c$);
