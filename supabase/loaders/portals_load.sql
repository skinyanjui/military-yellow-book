-- One-off loader for myb_portals (after migration myb_portals_01_table). Same pattern as unspsc_load.sql: the database fetches the
-- committed JSON, pinned to a commit; the http extension is installed for the load and dropped afterwards.
create extension if not exists http with schema extensions;
select extensions.http_set_curlopt('CURLOPT_TIMEOUT', '60');
create temp table _p as
  select content::jsonb as j from extensions.http_get(
    'https://raw.githubusercontent.com/skinyanjui/military-yellow-book/4ba41bcde0294a00a7d392467bbafc33f84e75f0/supabase/portals.json');
insert into public.myb_portals (scope, country, region, name, url, feed_url, platform, classification, note, flag, sources, position)
  select r->>'scope', r->>'country', r->>'region', r->>'name', r->>'url', r->>'feed_url', r->>'platform', r->>'classification', r->>'note', r->>'flag',
         array(select jsonb_array_elements_text(r->'sources')), (r->>'position')::int
  from _p, jsonb_array_elements(j) r;
drop extension http;
