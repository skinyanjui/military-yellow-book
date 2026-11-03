-- Procurement platform, part 2: registry import keeps live verification, catalogue runs, access-class promotion.

-- 1. A re-import of a catalogue must never downgrade 'verified_live' (the manifest only knows 'verified_documented').
create or replace function procurement._keep_verification(p_old text, p_new text) returns text
language sql immutable as $$
  select case when p_old = 'verified_live' then p_old
              when p_old = 'verified_documented' and p_new like 'pending%' then p_old
              else p_new end
$$;

do $$
declare v_src text := pg_get_functiondef('procurement.import_sources(jsonb)'::regprocedure);
begin
  v_src := replace(v_src,
    $a$verification_status = case when source.verification_status in ('verified_live', 'verified_documented') and excluded.verification_status like 'pending%' then source.verification_status else excluded.verification_status end,$a$,
    $b$verification_status = procurement._keep_verification(source.verification_status, excluded.verification_status),$b$);
  if position('_keep_verification(source.verification_status' in v_src) = 0 then raise exception 'import_sources patch did not apply'; end if;
  execute v_src;
end $$;

-- 2. Explicit, audited change of a source's verification status (used after a live call or a publisher check).
create or replace function procurement.set_verification(p_source text, p_status text, p_note text default null) returns void
language plpgsql set search_path = procurement, public, pg_temp as $$
begin
  if p_status not in ('verified_live', 'verified_documented', 'catalog_confirmed', 'pending_verification', 'documentation_requires_review',
                      'api_requires_discovery', 'dataset_identifiers_require_discovery', 'portal_only', 'restricted_api_access', 'unreachable_from_build_host') then
    raise exception 'unknown verification status %', p_status;
  end if;
  update source set verification_status = p_status, last_verified_at = now(), updated_at = now() where source_id = p_source;
  if not found then raise exception 'unknown source %', p_source; end if;
  insert into audit_event (action, source_id, detail) values ('set_verification', p_source, jsonb_build_object('status', p_status, 'note', p_note));
end $$;

-- 3. A catalogue sync (e.g. the OCP registry) is a run too: it records how many child sources it registered.
create or replace function procurement.record_catalog_run(p jsonb) returns jsonb
language plpgsql set search_path = procurement, public, pg_temp as $$
declare v_src text := p->>'source_id'; v_n int := coalesce((p->>'registered')::int, 0); v_rej int := coalesce((p->>'rejected')::int, 0);
begin
  insert into connector_run (run_id, source_id, mode, started_at, finished_at, status, fetched, accepted, rejected, params, transform_version)
  values (coalesce((p->>'run_id')::uuid, gen_random_uuid()), v_src, 'catalog', coalesce((p->>'started_at')::timestamptz, now()), now(),
          case when v_n > 0 then 'success' else 'failed' end, v_n + v_rej, v_n, v_rej, p->'params', p->>'transform_version')
  on conflict (run_id) do nothing;
  update source set last_run_at = now(), last_success_at = case when v_n > 0 then now() else last_success_at end,
         connector_state = case when v_n > 0 and connector_state in ('none', 'built_untested', 'failing') then 'ingested_unverified' else connector_state end,
         updated_at = now()
   where source_id = v_src;
  insert into audit_event (action, source_id, detail) values ('record_catalog_run', v_src, jsonb_build_object('registered', v_n, 'rejected', v_rej));
  return jsonb_build_object('source_id', v_src, 'registered', v_n);
end $$;

-- 4. 'confirmed_api' means: we called it and got records that validated. Run after a load; never by hand.
create or replace function procurement.refresh_access_classes() returns int
language plpgsql set search_path = procurement, public, pg_temp as $$
declare n int;
begin
  with up as (
    update source s set access_class = 'confirmed_api', updated_at = now()
     where s.source_kind = 'api' and s.access_class = 'documented_api'
       and exists (select 1 from connector_run r where r.source_id = s.source_id and r.status in ('success', 'partial') and r.accepted > 0)
    returning s.source_id)
  select count(*) into n from up;
  if n > 0 then insert into audit_event (action, detail) values ('refresh_access_classes', jsonb_build_object('promoted', n)); end if;
  return n;
end $$;

-- evidence kinds: a catalogue read is its own kind
alter table procurement.source_evidence drop constraint if exists source_evidence_check_kind_check;
alter table procurement.source_evidence add constraint source_evidence_check_kind_check
  check (check_kind in ('documentation', 'endpoint_probe', 'live_call', 'publisher_crosscheck', 'catalog_read'));

revoke all on function procurement._keep_verification(text, text), procurement.set_verification(text, text, text),
  procurement.record_catalog_run(jsonb), procurement.refresh_access_classes() from public, anon, authenticated;
