-- Procurement platform, part 4: a source is operational only when its licence is established too.
-- A source whose records match the publisher but whose licence is not established from a document or the publisher's own data
-- sits in 'licence_unconfirmed' (cross-checked, not yet cleared for use).

do $$
declare c text;
begin
  select conname into c from pg_constraint where conrelid = 'procurement.source'::regclass and contype = 'c' and pg_get_constraintdef(oid) like '%connector_state%';
  if c is not null then execute format('alter table procurement.source drop constraint %I', c); end if;
end $$;
alter table procurement.source add constraint source_connector_state_check
  check (connector_state in ('none', 'stub_credential_gated', 'built_untested', 'ingested_unverified', 'licence_unconfirmed', 'operational', 'failing', 'disabled'));

create or replace function procurement.licence_established(p_source text) returns boolean
language sql stable set search_path = procurement, public, pg_temp as $$
  select exists (select 1 from source_claim where source_id = p_source and field in ('licence', 'licence_in_records') and method in ('doc_read', 'live_call'))
$$;

create or replace function procurement.record_crosscheck(p jsonb) returns jsonb
language plpgsql set search_path = procurement, public, pg_temp as $$
declare v_src text := p->>'source_id'; c jsonb; v_match int := 0; v_mismatch int := 0; v_unreach int := 0; v_ok boolean; v_lic boolean; v_state text;
begin
  for c in select * from jsonb_array_elements(p->'checks') loop
    insert into source_evidence (source_id, check_kind, url, status, verdict, detail)
    values (v_src, 'publisher_crosscheck', c->>'url', (c->>'status')::int, c->>'verdict',
            jsonb_build_object('external_id', c->>'external_id', 'compared', c->'compared', 'note', c->>'note', 'route', c->>'route'))
    on conflict do nothing;
    if c->>'verdict' = 'match' then v_match := v_match + 1; elsif c->>'verdict' = 'mismatch' then v_mismatch := v_mismatch + 1; else v_unreach := v_unreach + 1; end if;
  end loop;
  v_ok := v_mismatch = 0 and v_match >= 3
          and exists (select 1 from connector_run where source_id = v_src and status in ('success', 'partial') and accepted > 0);
  v_lic := licence_established(v_src);
  v_state := null;
  if v_ok then
    v_state := case when v_lic then 'operational' else 'licence_unconfirmed' end;
    update source set crosscheck_passed_at = now(), connector_state = v_state, updated_at = now() where source_id = v_src;
  elsif v_mismatch > 0 then
    update source set connector_state = 'failing', updated_at = now() where source_id = v_src and connector_state in ('operational', 'licence_unconfirmed', 'ingested_unverified');
    v_state := 'failing';
  end if;
  insert into audit_event (action, source_id, detail) values ('record_crosscheck', v_src,
    jsonb_build_object('match', v_match, 'mismatch', v_mismatch, 'unreachable', v_unreach, 'licence_established', v_lic, 'state', v_state));
  return jsonb_build_object('source_id', v_src, 'match', v_match, 'mismatch', v_mismatch, 'unreachable', v_unreach, 'licence_established', v_lic, 'state', v_state);
end $$;

-- a later successful ingest keeps a cleared source cleared (ingest_bundle only knows 'operational' vs 'ingested_unverified')
do $$
declare v text := pg_get_functiondef('procurement.ingest_bundle(jsonb)'::regprocedure);
begin
  v := replace(v, $a$v_state := case when exists (select 1 from source where source_id = v_src and crosscheck_passed_at is not null) then 'operational' else 'ingested_unverified' end;$a$,
                  $b$v_state := case when exists (select 1 from source where source_id = v_src and crosscheck_passed_at is not null) then (case when procurement.licence_established(v_src) then 'operational' else 'licence_unconfirmed' end) else 'ingested_unverified' end;$b$);
  if position('licence_established(v_src)' in v) = 0 then raise exception 'ingest_bundle patch did not apply'; end if;
  v := replace(v, $a$elsif v_status = 'failed' and v_before in ('operational', 'ingested_unverified', 'failing') then$a$, $b$elsif v_status = 'failed' and v_before in ('operational', 'licence_unconfirmed', 'ingested_unverified', 'failing') then$b$);
  execute v;
end $$;

drop view if exists procurement.v_alert;
drop view if exists procurement.v_source_status;

create view procurement.v_source_status as
select s.source_id, s.name, s.country, s.parent_source_id, s.source_kind, s.access_class, s.connector, s.connector_state,
       s.verification_status, s.suggested_cadence, s.last_verified_at, s.last_run_at, s.last_success_at, s.crosscheck_passed_at,
       lr.status as last_run_status, lr.error_kind as last_error_kind,
       coalesce(rt.accepted, 0) as run_accepted, coalesce(rt.rejected, 0) as run_rejected,
       coalesce(sr.versions, 0) as source_records, coalesce(pc.processes, 0) as processes,
       case
         when s.connector_state = 'stub_credential_gated' then 'needs_credentials'
         when s.connector_state = 'disabled' then 'disabled'
         when s.connector_state = 'licence_unconfirmed' then 'awaiting_licence'
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

create view procurement.v_alert as
select source_id, name, health as problem, coalesce(last_error_kind, '') as detail, last_run_at, last_success_at from procurement.v_source_status
 where health in ('failing', 'stale', 'never_succeeded') and connector_state not in ('stub_credential_gated', 'disabled')
union all
select s.source_id, s.name, 'recent_rejections', r.rejected || ' of ' || r.fetched || ' records rejected', s.last_run_at, s.last_success_at
  from procurement.source s join procurement.connector_run r on r.source_id = s.source_id
 where r.started_at > now() - interval '2 days' and r.rejected > 0 and r.rejected * 4 > greatest(r.fetched, 1) and r.status <> 'failed';


do $$
declare v text := pg_get_functiondef('procurement.dashboard_snapshot()'::regprocedure);
begin
  v := replace(v, $a$'operational', count(*) filter (where connector_state = 'operational'),$a$, $b$'operational', count(*) filter (where connector_state = 'operational'), 'licence_unconfirmed', count(*) filter (where connector_state = 'licence_unconfirmed'),$b$);
  if position('licence_unconfirmed' in v) = 0 then raise exception 'dashboard_snapshot patch did not apply'; end if;
  execute v;
end $$;

revoke all on procurement.v_source_status, procurement.v_alert from public, anon, authenticated;
revoke all on function procurement.licence_established(text), procurement.record_crosscheck(jsonb), procurement.ingest_bundle(jsonb), procurement.dashboard_snapshot() from public, anon, authenticated;
