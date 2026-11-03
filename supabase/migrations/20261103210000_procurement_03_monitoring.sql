-- Procurement platform, part 3: monitoring views that answer the dashboard questions, and a single snapshot function.

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

-- Everything the operations dashboard shows, in one call, so the page never needs database access of its own.
create or replace function procurement.dashboard_snapshot() returns jsonb
language sql stable set search_path = procurement, public, pg_temp as $$
select jsonb_build_object(
  'generated_at', now(),
  'totals', (select jsonb_build_object(
      'sources', count(*), 'registry_children', count(*) filter (where parent_source_id is not null),
      'countries', count(distinct country) filter (where country is not null),
      'pending_verification', count(*) filter (where pending_verification),
      'operational', count(*) filter (where connector_state = 'operational'),
      'ingested_unverified', count(*) filter (where connector_state = 'ingested_unverified'),
      'failing', count(*) filter (where health = 'failing'), 'stale', count(*) filter (where health = 'stale'),
      'needs_credentials', count(*) filter (where health = 'needs_credentials')) from v_source_status),
  'records', jsonb_build_object('processes', (select count(*) from process), 'source_record_versions', (select count(*) from source_record),
      'awards', (select count(*) from award), 'contracts', (select count(*) from contract), 'organizations', (select count(*) from organization),
      'rejected', (select count(*) from rejected_record), 'duplicate_candidates_pending', (select count(*) from duplicate_candidate where status = 'pending')),
  'by_access_class', (select coalesce(jsonb_object_agg(access_class, n), '{}') from (select access_class, count(*) n from source group by 1) x),
  'by_connector_state', (select coalesce(jsonb_object_agg(connector_state, n), '{}') from (select connector_state, count(*) n from source group by 1) x),
  'by_health', (select coalesce(jsonb_object_agg(health, n), '{}') from (select health, count(*) n from v_source_status group by 1) x),
  'sources', (select coalesce(jsonb_agg(to_jsonb(v) order by v.parent_source_id nulls first, v.source_id), '[]') from (
      select source_id, name, country, parent_source_id, source_kind, access_class, connector_state, verification_status, health, pending_verification,
             last_run_at, last_success_at, last_run_status, last_error_kind, run_accepted, run_rejected, source_records, processes, crosscheck_passed_at
        from v_source_status) v),
  'runs', (select coalesce(jsonb_agg(to_jsonb(r) order by r.started_at desc), '[]') from (
      select run_id, source_id, mode, started_at, status, fetched, accepted, rejected, new_versions, unchanged, error_kind
        from connector_run order by started_at desc limit 60) r),
  'rejections_by_reason', (select coalesce(jsonb_agg(to_jsonb(x) order by x.n desc), '[]') from (
      select source_id, left(reason, 80) as reason, count(*) n from rejected_record group by 1, 2 order by n desc limit 20) x),
  'coverage', (select coalesce(jsonb_agg(to_jsonb(c) order by c.country, c.source_id), '[]') from v_coverage_by_country c),
  'alerts', (select coalesce(jsonb_agg(to_jsonb(a)), '[]') from v_alert a),
  'crosschecks', (select coalesce(jsonb_agg(to_jsonb(e) order by e.source_id, e.checked_at), '[]') from (
      select source_id, url, verdict, checked_at, detail->>'external_id' as external_id, detail->>'note' as note from source_evidence where check_kind = 'publisher_crosscheck') e)
);
$$;

revoke all on procurement.v_source_status, procurement.v_alert from public, anon, authenticated;
revoke all on function procurement.dashboard_snapshot() from public, anon, authenticated;
