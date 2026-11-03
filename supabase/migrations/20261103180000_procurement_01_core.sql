-- Procurement data platform, core schema.
-- Private schema: nothing here is exposed through the Supabase API (no grants to anon/authenticated,
-- RLS on with a deny-all policy). Ingestion and the dashboard run as the database owner / service role.
-- All writes from connectors go through procurement.ingest_bundle(jsonb), so every transport
-- (GitHub Action with a DB URL, the Supabase connector, a local psql) exercises the same code.

create schema if not exists procurement;
revoke all on schema procurement from public, anon, authenticated;
alter default privileges in schema procurement revoke all on tables from public, anon, authenticated;
alter default privileges in schema procurement revoke execute on functions from public, anon, authenticated;

-- ---------------------------------------------------------------- helpers
create or replace function procurement.url_key(u text) returns text
language sql immutable set search_path = '' as $$
  select nullif(regexp_replace(regexp_replace(lower(btrim(coalesce(u, ''))), '^https?://(www\.)?', ''), '/+$', ''), '')
$$;

create or replace function procurement.name_norm(n text) returns text
language sql immutable set search_path = '' as $$
  select btrim(regexp_replace(lower(coalesce(n, '')), '[^[:alnum:]]+', ' ', 'g'))
$$;

create or replace function procurement.cadence_interval(c text) returns interval
language sql immutable set search_path = '' as $$
  select case when c in ('daily', 'daily_check', 'real_time', 'hourly') then interval '1 day'
              when c = 'weekly' then interval '7 days' else interval '30 days' end
$$;

-- ---------------------------------------------------------------- source registry
create table procurement.source (
  source_id            text primary key check (source_id ~ '^[a-z0-9_]+$'),
  parent_source_id     text references procurement.source(source_id),
  name                 text not null,
  canonical_url        text not null,
  canonical_key        text not null,
  endpoint_url         text,
  country              text,
  jurisdiction         text,
  owner_institution    text,
  source_kind          text not null check (source_kind in ('api', 'bulk', 'portal', 'marketplace', 'catalog', 'informational')),
  access_class         text not null check (access_class in ('confirmed_api', 'documented_api', 'bulk_download', 'permitted_html',
                                                             'restricted_provider', 'portal_only', 'informational', 'discovery_needed', 'credential_required')),
  record_types         text[] not null default '{}',
  formats              text[] not null default '{}',
  authentication       text,
  licence              text,
  licence_url          text,
  redistribution       text,
  rate_limit           text,
  robots_note          text,
  update_frequency     text,
  suggested_cadence    text,
  coverage_from        date,
  coverage_to          date,
  verification_status  text not null default 'pending_verification',
  last_verified_at     timestamptz,
  connector            text,
  connector_state      text not null default 'none' check (connector_state in ('none', 'stub_credential_gated', 'built_untested',
                                                             'ingested_unverified', 'operational', 'failing', 'disabled')),
  crosscheck_passed_at timestamptz,
  last_run_at          timestamptz,
  last_success_at      timestamptz,
  origin               text not null default 'manifest',
  notes                text,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
-- the same portal listed twice (different id, same address and endpoint) is a duplicate, not a second source
create unique index source_canonical_uq on procurement.source (canonical_key, coalesce(endpoint_url, ''));
create index source_country_idx on procurement.source (country);
create index source_parent_idx on procurement.source (parent_source_id);

create table procurement.source_alias (
  id bigserial primary key,
  attempted_source_id text not null,
  duplicate_of        text not null references procurement.source(source_id),
  origin              text not null,
  detail              jsonb,
  seen_at             timestamptz not null default now(),
  unique (attempted_source_id, origin)
);

create table procurement.source_evidence (
  id          bigserial primary key,
  source_id   text not null references procurement.source(source_id),
  check_kind  text not null check (check_kind in ('documentation', 'endpoint_probe', 'live_call', 'publisher_crosscheck')),
  url         text,
  checked_at  timestamptz not null default now(),
  status      int,
  verdict     text not null,
  final_url   text,
  content_type text,
  detail      jsonb,
  unique (source_id, check_kind, url, checked_at)
);
create index source_evidence_source_idx on procurement.source_evidence (source_id, check_kind, checked_at desc);

-- a claim is one statement about a source (authentication, licence, rate limit...) with where it was read
create table procurement.source_claim (
  id           bigserial primary key,
  source_id    text not null references procurement.source(source_id),
  field        text not null,
  value        text not null,
  method       text not null check (method in ('doc_read', 'live_call', 'manifest', 'not_stated')),
  evidence_url text,
  quote        text,
  checked_on   date not null,
  unique (source_id, field, method, evidence_url)
);

-- ---------------------------------------------------------------- runs, checkpoints, provenance
create table procurement.connector_run (
  run_id            uuid primary key,
  source_id         text not null references procurement.source(source_id),
  mode              text not null check (mode in ('test', 'incremental', 'backfill', 'catalog')),
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  status            text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
  fetched           int not null default 0,
  accepted          int not null default 0,
  rejected          int not null default 0,
  new_versions      int not null default 0,
  unchanged         int not null default 0,
  error_kind        text,
  error             text,
  cursor_before     jsonb,
  cursor_after      jsonb,
  params            jsonb,
  transform_version text
);
create index connector_run_source_idx on procurement.connector_run (source_id, started_at desc);

create table procurement.checkpoint (
  source_id  text not null references procurement.source(source_id),
  key        text not null default 'default',
  cursor     jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (source_id, key)
);

create table procurement.source_record (
  id                bigserial primary key,
  source_id         text not null references procurement.source(source_id),
  external_id       text not null,
  version           int not null,
  is_current        boolean not null default true,
  content_hash      text not null,
  source_url        text,
  publisher         text,
  published_at      timestamptz,
  source_updated_at timestamptz,
  fetched_at        timestamptz not null,
  last_seen_at      timestamptz not null default now(),
  run_id            uuid references procurement.connector_run(run_id),
  language          text,
  licence           text,
  transform_version text,
  validation_status text not null default 'valid' check (validation_status in ('valid', 'warnings')),
  validation_notes  jsonb,
  raw               jsonb,
  raw_stored        boolean not null default true,
  withdrawn_at      timestamptz,
  unique (source_id, external_id, version),
  unique (source_id, external_id, content_hash)
);
create unique index source_record_current_uq on procurement.source_record (source_id, external_id) where is_current;
create index source_record_run_idx on procurement.source_record (run_id);

-- ---------------------------------------------------------------- OCDS-compatible entities
create table procurement.organization (
  id          bigserial primary key,
  scheme      text,
  ident       text,
  name        text not null,
  name_norm   text not null,
  country     text,
  roles       text[] not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check ((ident is null) = (scheme is null))
);
create unique index organization_ident_uq on procurement.organization (scheme, ident) where ident is not null;
create unique index organization_name_uq on procurement.organization (name_norm, (coalesce(country, ''))) where ident is null;
create index organization_trgm on procurement.organization using gin (name_norm gin_trgm_ops);

create table procurement.process (
  id                bigserial primary key,
  ocid              text not null unique,
  ocid_native       boolean not null,
  title             text,
  description       text,
  buyer_org_id      bigint references procurement.organization(id),
  country           text check (country is null or country ~ '^[A-Z]{2}$'),
  status            text,
  stage             text check (stage in ('planning', 'tender', 'award', 'contract', 'unknown')),
  procurement_method text,
  main_category     text,
  value_amount      numeric(20, 2),
  value_currency    text check (value_currency is null or value_currency ~ '^[A-Z]{3}$'),
  published_at      timestamptz,
  updated_at        timestamptz,
  tender_start      timestamptz,
  tender_end        timestamptz,
  classifications   jsonb not null default '[]',
  items             jsonb not null default '[]',
  financier         text,
  project_id        text,
  language          text,
  url               text,
  first_source_id   text not null references procurement.source(source_id),
  current_record_id bigint references procurement.source_record(id),
  canonical_of      bigint references procurement.process(id),
  search            tsvector generated always as (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, ''))) stored,
  created_at        timestamptz not null default now(),
  check (value_amount is null or value_currency is not null)
);
create index process_search_idx on procurement.process using gin (search);
create index process_title_trgm on procurement.process using gin (title gin_trgm_ops);
create index process_country_idx on procurement.process (country, published_at desc);
create index process_buyer_idx on procurement.process (buyer_org_id);
create index process_class_idx on procurement.process using gin (classifications jsonb_path_ops);

create table procurement.process_source (
  process_id       bigint not null references procurement.process(id) on delete cascade,
  source_record_id bigint not null references procurement.source_record(id) on delete cascade,
  source_id        text not null,
  external_id      text not null,
  primary key (process_id, source_record_id)
);
create index process_source_ext_idx on procurement.process_source (source_id, external_id);

-- contract value, award value, obligated value and actual payment are different quantities and stay in different columns
create table procurement.award (
  id                bigserial primary key,
  process_id        bigint not null references procurement.process(id) on delete cascade,
  award_id          text not null,
  title             text,
  status            text,
  date              timestamptz,
  value_amount      numeric(20, 2),
  value_currency    text check (value_currency is null or value_currency ~ '^[A-Z]{3}$'),
  obligated_amount  numeric(20, 2),
  source_record_id  bigint references procurement.source_record(id),
  unique (process_id, award_id)
);
create table procurement.award_supplier (
  award_pk bigint not null references procurement.award(id) on delete cascade,
  org_id   bigint not null references procurement.organization(id),
  primary key (award_pk, org_id)
);
create table procurement.contract (
  id                bigserial primary key,
  process_id        bigint not null references procurement.process(id) on delete cascade,
  contract_id       text not null,
  award_id          text,
  title             text,
  status            text,
  date_signed       timestamptz,
  period_start      timestamptz,
  period_end        timestamptz,
  value_amount      numeric(20, 2),
  value_currency    text check (value_currency is null or value_currency ~ '^[A-Z]{3}$'),
  paid_amount       numeric(20, 2),
  source_record_id  bigint references procurement.source_record(id),
  unique (process_id, contract_id)
);

create table procurement.rejected_record (
  id          bigserial primary key,
  run_id      uuid references procurement.connector_run(run_id),
  source_id   text not null,
  external_id text,
  reason      text not null,
  detail      jsonb,
  excerpt     jsonb,
  created_at  timestamptz not null default now()
);
create index rejected_record_run_idx on procurement.rejected_record (run_id);

create table procurement.duplicate_candidate (
  id           bigserial primary key,
  process_a    bigint not null references procurement.process(id) on delete cascade,
  process_b    bigint not null references procurement.process(id) on delete cascade,
  score        real not null,
  reasons      jsonb not null,
  status       text not null default 'pending' check (status in ('pending', 'confirmed_duplicate', 'not_duplicate')),
  reviewed_by  text,
  reviewed_at  timestamptz,
  created_at   timestamptz not null default now(),
  check (process_a < process_b),
  unique (process_a, process_b)
);

create table procurement.classification_code (
  scheme      text not null,
  code        text not null,
  title       text not null,
  parent_code text,
  note        text,
  primary key (scheme, code)
);

create table procurement.audit_event (
  id        bigserial primary key,
  at        timestamptz not null default now(),
  actor     text not null default current_user,
  action    text not null,
  source_id text,
  detail    jsonb
);

-- ---------------------------------------------------------------- registry import
create or replace function procurement.import_sources(p jsonb) returns jsonb
language plpgsql set search_path = procurement, public, pg_temp as $$
declare
  s jsonb; v_origin text := coalesce(p->>'origin', 'manifest');
  v_ins int := 0; v_upd int := 0; v_skip jsonb := '[]'; v_new boolean; v_dup text;
begin
  for s in select * from jsonb_array_elements(p->'sources') loop
    begin
      insert into source (source_id, parent_source_id, name, canonical_url, canonical_key, endpoint_url, country, jurisdiction, owner_institution,
                          source_kind, access_class, record_types, formats, authentication, licence, licence_url, update_frequency,
                          suggested_cadence, coverage_from, coverage_to, verification_status, connector, connector_state, origin, notes)
      values (s->>'source_id', nullif(s->>'parent_source_id', ''), s->>'name', s->>'canonical_url', url_key(s->>'canonical_url'),
              nullif(s->>'endpoint_url', ''), s->>'country', s->>'jurisdiction', s->>'owner_institution',
              s->>'source_kind', s->>'access_class',
              coalesce(array(select jsonb_array_elements_text(s->'record_types')), '{}'),
              coalesce(array(select jsonb_array_elements_text(s->'formats')), '{}'),
              s->>'authentication', s->>'licence', s->>'licence_url', s->>'update_frequency', s->>'suggested_cadence',
              nullif(s->>'coverage_from', '')::date, nullif(s->>'coverage_to', '')::date,
              coalesce(s->>'verification_status', 'pending_verification'), s->>'connector',
              coalesce(s->>'connector_state', 'none'), v_origin, s->>'notes')
      on conflict (source_id) do update set
        name = excluded.name, canonical_url = excluded.canonical_url, canonical_key = excluded.canonical_key,
        endpoint_url = excluded.endpoint_url, country = excluded.country, jurisdiction = excluded.jurisdiction,
        owner_institution = coalesce(excluded.owner_institution, source.owner_institution),
        source_kind = excluded.source_kind, access_class = excluded.access_class,
        record_types = excluded.record_types, formats = case when cardinality(excluded.formats) > 0 then excluded.formats else source.formats end,
        authentication = coalesce(excluded.authentication, source.authentication),
        licence = coalesce(excluded.licence, source.licence), licence_url = coalesce(excluded.licence_url, source.licence_url),
        update_frequency = coalesce(excluded.update_frequency, source.update_frequency),
        suggested_cadence = coalesce(excluded.suggested_cadence, source.suggested_cadence),
        coverage_from = coalesce(excluded.coverage_from, source.coverage_from), coverage_to = coalesce(excluded.coverage_to, source.coverage_to),
        verification_status = case when source.verification_status in ('verified_live', 'verified_documented') and excluded.verification_status like 'pending%' then source.verification_status else excluded.verification_status end,
        connector = coalesce(excluded.connector, source.connector),
        notes = coalesce(excluded.notes, source.notes), parent_source_id = coalesce(excluded.parent_source_id, source.parent_source_id),
        updated_at = now()
      returning (xmax = 0) into v_new;
      if v_new then v_ins := v_ins + 1; else v_upd := v_upd + 1; end if;
    exception when unique_violation then
      select source_id into v_dup from source where canonical_key = url_key(s->>'canonical_url') and coalesce(endpoint_url, '') = coalesce(nullif(s->>'endpoint_url', ''), '') limit 1;
      if v_dup is null then raise; end if;
      insert into source_alias (attempted_source_id, duplicate_of, origin, detail)
      values (s->>'source_id', v_dup, v_origin, jsonb_build_object('name', s->>'name', 'url', s->>'canonical_url'))
      on conflict (attempted_source_id, origin) do nothing;
      v_skip := v_skip || jsonb_build_array(jsonb_build_object('source_id', s->>'source_id', 'duplicate_of', v_dup));
    end;
  end loop;
  insert into audit_event (action, detail) values ('import_sources', jsonb_build_object('origin', v_origin, 'inserted', v_ins, 'updated', v_upd, 'skipped_duplicates', jsonb_array_length(v_skip)));
  return jsonb_build_object('origin', v_origin, 'inserted', v_ins, 'updated', v_upd, 'skipped_duplicates', v_skip);
end $$;

-- ---------------------------------------------------------------- ingestion
create or replace function procurement._upsert_org(o jsonb, p_role text) returns bigint
language plpgsql set search_path = procurement, public, extensions, pg_temp as $$
declare v_id bigint; v_name text := nullif(btrim(o->>'name'), ''); v_scheme text := nullif(o->>'scheme', ''); v_ident text := nullif(o->>'id', '');
        v_country text := nullif(upper(o->>'country'), '');
begin
  if o is null or v_name is null then return null; end if;
  if v_ident is not null and v_scheme is null then v_scheme := 'unknown'; end if;
  if v_ident is not null then
    insert into organization (scheme, ident, name, name_norm, country, roles)
    values (v_scheme, v_ident, v_name, name_norm(v_name), v_country, array[p_role])
    on conflict (scheme, ident) where ident is not null do update
      set name = excluded.name, name_norm = excluded.name_norm, country = coalesce(excluded.country, organization.country),
          roles = (select array_agg(distinct r) from unnest(organization.roles || excluded.roles) r), updated_at = now()
    returning id into v_id;
  else
    insert into organization (name, name_norm, country, roles)
    values (v_name, name_norm(v_name), v_country, array[p_role])
    on conflict (name_norm, (coalesce(country, ''))) where ident is null do update
      set roles = (select array_agg(distinct r) from unnest(organization.roles || excluded.roles) r), updated_at = now()
    returning id into v_id;
  end if;
  return v_id;
end $$;

create or replace function procurement._ingest_record(p_src text, p_run uuid, rec jsonb) returns text
language plpgsql set search_path = procurement, public, extensions, pg_temp as $$
declare
  proc jsonb := rec->'process'; v_ext text := rec->>'external_id'; v_cur record; v_ver int; v_rid bigint; v_pid bigint; v_buyer bigint;
  v_old_ts timestamptz; v_in_ts timestamptz; v_newer boolean; a jsonb; c jsonb; sup jsonb; v_aid bigint; v_org bigint; v_keep text[];
begin
  if coalesce(v_ext, '') = '' then raise exception 'missing external_id'; end if;
  if coalesce(proc->>'ocid', '') = '' then raise exception 'missing process.ocid'; end if;
  if coalesce(rec->>'content_hash', '') = '' then raise exception 'missing content_hash'; end if;

  select id, version, content_hash into v_cur from source_record where source_id = p_src and external_id = v_ext and is_current;
  if found and v_cur.content_hash = rec->>'content_hash' then
    update source_record set last_seen_at = now() where id = v_cur.id;
    return 'unchanged';
  end if;
  if found then
    update source_record set is_current = false where id = v_cur.id;
    v_ver := v_cur.version + 1;
  else
    v_ver := 1;
  end if;

  insert into source_record (source_id, external_id, version, content_hash, source_url, publisher, published_at, source_updated_at, fetched_at, run_id,
                             language, licence, transform_version, validation_status, validation_notes, raw, raw_stored, withdrawn_at)
  values (p_src, v_ext, v_ver, rec->>'content_hash', rec->>'source_url', rec->>'publisher', (rec->>'published_at')::timestamptz,
          (rec->>'source_updated_at')::timestamptz, (rec->>'fetched_at')::timestamptz, p_run, rec->>'language', rec->>'licence',
          rec->>'transform_version', coalesce(rec->>'validation_status', 'valid'), rec->'validation_notes', rec->'raw',
          coalesce((rec->>'raw_stored')::boolean, true), (rec->>'withdrawn_at')::timestamptz)
  returning id into v_rid;

  v_buyer := _upsert_org(proc->'buyer', 'buyer');
  select id, coalesce(updated_at, published_at) into v_pid, v_old_ts from process where ocid = proc->>'ocid';
  v_in_ts := coalesce((proc->>'updated_at')::timestamptz, (proc->>'published_at')::timestamptz);
  v_newer := v_pid is null or v_old_ts is null or v_in_ts is null or v_in_ts >= v_old_ts;

  if v_pid is null then
    insert into process (ocid, ocid_native, title, description, buyer_org_id, country, status, stage, procurement_method, main_category,
                         value_amount, value_currency, published_at, updated_at, tender_start, tender_end, classifications, items,
                         financier, project_id, language, url, first_source_id, current_record_id)
    values (proc->>'ocid', coalesce((proc->>'ocid_native')::boolean, false), left(proc->>'title', 1000), proc->>'description', v_buyer,
            upper(proc->>'country'), proc->>'status', coalesce(proc->>'stage', 'unknown'), proc->>'procurement_method', proc->>'main_category',
            (proc->'value'->>'amount')::numeric(20, 2), upper(proc->'value'->>'currency'),
            (proc->>'published_at')::timestamptz, (proc->>'updated_at')::timestamptz, (proc->>'tender_start')::timestamptz, (proc->>'tender_end')::timestamptz,
            coalesce(proc->'classifications', '[]'), coalesce(proc->'items', '[]'), proc->>'financier', proc->>'project_id', proc->>'language', proc->>'url', p_src, v_rid)
    returning id into v_pid;
  elsif v_newer then
    update process set
      title = coalesce(left(proc->>'title', 1000), title), description = coalesce(proc->>'description', description),
      buyer_org_id = coalesce(v_buyer, buyer_org_id), country = coalesce(upper(proc->>'country'), country), status = coalesce(proc->>'status', status),
      stage = case when proc->>'stage' is null or proc->>'stage' = 'unknown' then stage else proc->>'stage' end,
      procurement_method = coalesce(proc->>'procurement_method', procurement_method), main_category = coalesce(proc->>'main_category', main_category),
      value_amount = coalesce((proc->'value'->>'amount')::numeric(20, 2), value_amount),
      value_currency = coalesce(upper(proc->'value'->>'currency'), value_currency),
      published_at = coalesce((proc->>'published_at')::timestamptz, published_at), updated_at = coalesce((proc->>'updated_at')::timestamptz, updated_at),
      tender_start = coalesce((proc->>'tender_start')::timestamptz, tender_start), tender_end = coalesce((proc->>'tender_end')::timestamptz, tender_end),
      classifications = case when jsonb_array_length(coalesce(proc->'classifications', '[]')) > 0 then proc->'classifications' else classifications end,
      items = case when jsonb_array_length(coalesce(proc->'items', '[]')) > 0 then proc->'items' else items end,
      financier = coalesce(proc->>'financier', financier), project_id = coalesce(proc->>'project_id', project_id),
      language = coalesce(proc->>'language', language), url = coalesce(proc->>'url', url), current_record_id = v_rid
    where id = v_pid;
  else
    update process set title = coalesce(title, left(proc->>'title', 1000)), description = coalesce(description, proc->>'description'),
      buyer_org_id = coalesce(buyer_org_id, v_buyer), country = coalesce(country, upper(proc->>'country')) where id = v_pid;
  end if;
  insert into process_source (process_id, source_record_id, source_id, external_id) values (v_pid, v_rid, p_src, v_ext) on conflict do nothing;

  for a in select * from jsonb_array_elements(coalesce(rec->'awards', '[]')) loop
    insert into award (process_id, award_id, title, status, date, value_amount, value_currency, obligated_amount, source_record_id)
    values (v_pid, a->>'award_id', a->>'title', a->>'status', (a->>'date')::timestamptz, (a->'value'->>'amount')::numeric(20, 2),
            upper(a->'value'->>'currency'), (a->'obligated'->>'amount')::numeric(20, 2), v_rid)
    on conflict (process_id, award_id) do update set
      title = coalesce(excluded.title, award.title), status = coalesce(excluded.status, award.status), date = coalesce(excluded.date, award.date),
      value_amount = coalesce(excluded.value_amount, award.value_amount), value_currency = coalesce(excluded.value_currency, award.value_currency),
      obligated_amount = coalesce(excluded.obligated_amount, award.obligated_amount), source_record_id = excluded.source_record_id
    returning id into v_aid;
    for sup in select * from jsonb_array_elements(coalesce(a->'suppliers', '[]')) loop
      v_org := _upsert_org(sup, 'supplier');
      if v_org is not null then insert into award_supplier (award_pk, org_id) values (v_aid, v_org) on conflict do nothing; end if;
    end loop;
  end loop;

  for c in select * from jsonb_array_elements(coalesce(rec->'contracts', '[]')) loop
    insert into contract (process_id, contract_id, award_id, title, status, date_signed, period_start, period_end, value_amount, value_currency, paid_amount, source_record_id)
    values (v_pid, c->>'contract_id', c->>'award_id', c->>'title', c->>'status', (c->>'date_signed')::timestamptz, (c->>'period_start')::timestamptz,
            (c->>'period_end')::timestamptz, (c->'value'->>'amount')::numeric(20, 2), upper(c->'value'->>'currency'), (c->'paid'->>'amount')::numeric(20, 2), v_rid)
    on conflict (process_id, contract_id) do update set
      award_id = coalesce(excluded.award_id, contract.award_id), title = coalesce(excluded.title, contract.title), status = coalesce(excluded.status, contract.status),
      date_signed = coalesce(excluded.date_signed, contract.date_signed), period_start = coalesce(excluded.period_start, contract.period_start),
      period_end = coalesce(excluded.period_end, contract.period_end), value_amount = coalesce(excluded.value_amount, contract.value_amount),
      value_currency = coalesce(excluded.value_currency, contract.value_currency), paid_amount = coalesce(excluded.paid_amount, contract.paid_amount),
      source_record_id = excluded.source_record_id;
  end loop;
  return 'new_version';
end $$;

create or replace function procurement.ingest_bundle(p jsonb) returns jsonb
language plpgsql set search_path = procurement, public, extensions, pg_temp as $$
declare
  v_run jsonb := p->'run'; v_src text := v_run->>'source_id'; v_run_id uuid; rec jsonb;
  v_fetched int := 0; v_acc int := 0; v_rej int := 0; v_new int := 0; v_unch int := 0; v_res text; v_status text; r jsonb; v_state text; v_before text;
begin
  if not exists (select 1 from source where source_id = v_src) then raise exception 'unknown_source: %', v_src; end if;
  v_run_id := (v_run->>'run_id')::uuid;
  if v_run_id is null then raise exception 'run.run_id is required'; end if;
  if exists (select 1 from connector_run where run_id = v_run_id and finished_at is not null) then
    return jsonb_build_object('status', 'already_ingested', 'run_id', v_run_id);
  end if;
  insert into connector_run (run_id, source_id, mode, started_at, status, params, cursor_before, transform_version)
  values (v_run_id, v_src, v_run->>'mode', coalesce((v_run->>'started_at')::timestamptz, now()), 'running', v_run->'params', v_run->'cursor_before', v_run->>'transform_version')
  on conflict (run_id) do nothing;

  for rec in select * from jsonb_array_elements(coalesce(p->'records', '[]')) loop
    v_fetched := v_fetched + 1;
    begin
      v_res := _ingest_record(v_src, v_run_id, rec);
      v_acc := v_acc + 1;
      if v_res = 'new_version' then v_new := v_new + 1; else v_unch := v_unch + 1; end if;
    exception when others then
      v_rej := v_rej + 1;
      insert into rejected_record (run_id, source_id, external_id, reason, detail, excerpt)
      values (v_run_id, v_src, rec->>'external_id', 'db_validation: ' || sqlerrm, jsonb_build_object('sqlstate', sqlstate), rec->'process');
    end;
  end loop;
  for r in select * from jsonb_array_elements(coalesce(p->'rejected', '[]')) loop
    v_fetched := v_fetched + 1; v_rej := v_rej + 1;
    insert into rejected_record (run_id, source_id, external_id, reason, detail, excerpt)
    values (v_run_id, v_src, r->>'external_id', coalesce(r->>'reason', 'rejected'), r->'detail', r->'excerpt');
  end loop;

  v_status := coalesce(v_run->>'status', case when v_acc = 0 and v_rej > 0 then 'failed' when v_rej > 0 then 'partial' else 'success' end);
  if v_status = 'success' and v_rej > 0 then v_status := 'partial'; end if;
  update connector_run set finished_at = now(), status = v_status, fetched = v_fetched, accepted = v_acc, rejected = v_rej,
         new_versions = v_new, unchanged = v_unch, error_kind = v_run->>'error_kind', error = left(v_run->>'error', 2000), cursor_after = v_run->'cursor_after'
   where run_id = v_run_id;

  if v_status in ('success', 'partial') and v_run->'cursor_after' is not null and (v_run->>'mode') in ('incremental', 'backfill') then
    insert into checkpoint (source_id, key, cursor) values (v_src, coalesce(v_run->>'checkpoint_key', 'default'), v_run->'cursor_after')
    on conflict (source_id, key) do update set cursor = excluded.cursor, updated_at = now();
  end if;

  select connector_state into v_before from source where source_id = v_src;
  v_state := v_before;
  if v_status in ('success', 'partial') and v_acc > 0 then
    v_state := case when exists (select 1 from source where source_id = v_src and crosscheck_passed_at is not null) then 'operational' else 'ingested_unverified' end;
  elsif v_status = 'failed' and v_before in ('operational', 'ingested_unverified', 'failing') then
    v_state := 'failing';
  end if;
  update source set last_run_at = now(), last_success_at = case when v_status in ('success', 'partial') and v_acc > 0 then now() else last_success_at end,
         connector_state = v_state, updated_at = now() where source_id = v_src;
  insert into audit_event (action, source_id, detail) values ('ingest_bundle', v_src,
    jsonb_build_object('run_id', v_run_id, 'status', v_status, 'accepted', v_acc, 'rejected', v_rej, 'new_versions', v_new, 'unchanged', v_unch));
  return jsonb_build_object('status', v_status, 'run_id', v_run_id, 'fetched', v_fetched, 'accepted', v_acc, 'rejected', v_rej, 'new_versions', v_new, 'unchanged', v_unch);
end $$;

-- ---------------------------------------------------------------- verification and the operational gate
create or replace function procurement.record_evidence(p jsonb) returns int
language plpgsql set search_path = procurement, public, pg_temp as $$
declare e jsonb; n int := 0;
begin
  for e in select * from jsonb_array_elements(p->'evidence') loop
    insert into source_evidence (source_id, check_kind, url, checked_at, status, verdict, final_url, content_type, detail)
    values (e->>'source_id', e->>'check_kind', e->>'url', coalesce((e->>'checked_at')::timestamptz, now()), (e->>'status')::int, e->>'verdict',
            e->>'final_url', e->>'content_type', e->'detail')
    on conflict do nothing;
    n := n + 1;
  end loop;
  for e in select * from jsonb_array_elements(coalesce(p->'claims', '[]')) loop
    insert into source_claim (source_id, field, value, method, evidence_url, quote, checked_on)
    values (e->>'source_id', e->>'field', e->>'value', e->>'method', e->>'evidence_url', e->>'quote', coalesce((e->>'checked_on')::date, current_date))
    on conflict (source_id, field, method, evidence_url) do update set value = excluded.value, quote = excluded.quote, checked_on = excluded.checked_on;
  end loop;
  return n;
end $$;

-- A source becomes operational only when a stored ingestion exists AND a re-fetch from the publisher matched the stored values.
create or replace function procurement.record_crosscheck(p jsonb) returns jsonb
language plpgsql set search_path = procurement, public, pg_temp as $$
declare v_src text := p->>'source_id'; c jsonb; v_match int := 0; v_mismatch int := 0; v_unreach int := 0; v_ok boolean;
begin
  for c in select * from jsonb_array_elements(p->'checks') loop
    insert into source_evidence (source_id, check_kind, url, status, verdict, detail)
    values (v_src, 'publisher_crosscheck', c->>'url', (c->>'status')::int, c->>'verdict', jsonb_build_object('external_id', c->>'external_id', 'compared', c->'compared', 'note', c->>'note'))
    on conflict do nothing;
    if c->>'verdict' = 'match' then v_match := v_match + 1; elsif c->>'verdict' = 'mismatch' then v_mismatch := v_mismatch + 1; else v_unreach := v_unreach + 1; end if;
  end loop;
  v_ok := v_mismatch = 0 and v_match >= 3
          and exists (select 1 from connector_run where source_id = v_src and status in ('success', 'partial') and accepted > 0);
  if v_ok then
    update source set crosscheck_passed_at = now(), connector_state = 'operational', updated_at = now() where source_id = v_src;
  end if;
  insert into audit_event (action, source_id, detail) values ('record_crosscheck', v_src,
    jsonb_build_object('match', v_match, 'mismatch', v_mismatch, 'unreachable', v_unreach, 'operational', v_ok));
  return jsonb_build_object('source_id', v_src, 'match', v_match, 'mismatch', v_mismatch, 'unreachable', v_unreach, 'operational', v_ok);
end $$;

-- ---------------------------------------------------------------- duplicate candidates (never merges automatically)
create or replace function procurement.detect_duplicates(p_days int default 21, p_min real default 0.6) returns int
language plpgsql set search_path = procurement, public, extensions, pg_temp as $$
declare n int;
begin
  insert into duplicate_candidate (process_a, process_b, score, reasons)
  select least(a.id, b.id), greatest(a.id, b.id), similarity(a.title, b.title),
         jsonb_build_object('title_similarity', similarity(a.title, b.title), 'same_country', a.country = b.country,
                            'days_apart', round(abs(extract(epoch from (coalesce(a.published_at, a.updated_at) - coalesce(b.published_at, b.updated_at))) / 86400)::numeric, 1),
                            'sources', jsonb_build_array(a.first_source_id, b.first_source_id))
    from process a join process b on a.id < b.id and a.first_source_id <> b.first_source_id and a.country is not distinct from b.country
   where a.title is not null and b.title is not null and similarity(a.title, b.title) >= p_min
     and abs(extract(epoch from (coalesce(a.published_at, a.updated_at) - coalesce(b.published_at, b.updated_at)))) <= p_days * 86400
  on conflict (process_a, process_b) do nothing;
  get diagnostics n = row_count;
  return n;
end $$;

-- ---------------------------------------------------------------- monitoring views
create or replace view procurement.v_source_status as
select s.source_id, s.name, s.country, s.parent_source_id, s.source_kind, s.access_class, s.connector, s.connector_state,
       s.verification_status, s.suggested_cadence, s.last_verified_at, s.last_run_at, s.last_success_at, s.crosscheck_passed_at,
       coalesce(r.accepted, 0) as records_accepted, coalesce(r.rejected, 0) as records_rejected, coalesce(pc.processes, 0) as processes,
       case
         when s.connector_state = 'stub_credential_gated' then 'needs_credentials'
         when s.connector_state = 'disabled' then 'disabled'
         when s.connector_state = 'none' and s.access_class in ('portal_only', 'informational', 'restricted_provider') then 'not_automated'
         when s.connector_state = 'none' then 'no_connector'
         when s.connector_state = 'failing' then 'failing'
         when s.last_success_at is null then 'never_succeeded'
         when s.last_success_at < now() - procurement.cadence_interval(s.suggested_cadence) * 2 then 'stale'
         when s.connector_state = 'operational' then 'healthy'
         else 'awaiting_publisher_check'
       end as health,
       (s.last_verified_at is null or s.verification_status like 'pending%' or s.verification_status like '%require%') as pending_verification
  from procurement.source s
  left join (select source_id, sum(accepted) accepted, sum(rejected) rejected from procurement.connector_run where status <> 'running' group by source_id) r using (source_id)
  left join (select first_source_id source_id, count(*) processes from procurement.process group by 1) pc using (source_id);

create or replace view procurement.v_coverage_by_country as
select coalesce(p.country, '??') as country, p.first_source_id as source_id, count(*) as processes,
       count(*) filter (where p.stage = 'tender') as tenders, count(*) filter (where p.stage in ('award', 'contract')) as with_awards,
       min(p.published_at) as earliest, max(p.published_at) as latest, max(sr.fetched_at) as last_fetched
  from procurement.process p left join procurement.source_record sr on sr.id = p.current_record_id
 group by 1, 2;

create or replace view procurement.v_alert as
select source_id, name, health as problem, last_run_at, last_success_at from procurement.v_source_status
 where health in ('failing', 'stale', 'never_succeeded') and connector_state not in ('none', 'stub_credential_gated', 'disabled')
union all
select s.source_id, s.name, 'recent_rejections', s.last_run_at, s.last_success_at
  from procurement.source s join procurement.connector_run r on r.source_id = s.source_id
 where r.started_at > now() - interval '2 days' and r.rejected > 0 and r.rejected * 4 > greatest(r.fetched, 1);

-- ---------------------------------------------------------------- lock down
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'procurement' loop
    execute format('alter table procurement.%I enable row level security', t);
    execute format('create policy deny_all on procurement.%I for all using (false) with check (false)', t);
  end loop;
end $$;
revoke all on all tables in schema procurement from public, anon, authenticated;
revoke all on all sequences in schema procurement from public, anon, authenticated;
revoke execute on all functions in schema procurement from public, anon, authenticated;
