-- One-off loader for the UNSPSC taxonomy (run after migration myb_unspsc_01_taxonomy, once).
-- The database fetches the committed JSON itself, pinned to a commit so the data cannot change underneath it,
-- so no 1 MB statement has to be pasted. The http extension is installed for the load and dropped afterwards.
create extension if not exists http with schema extensions;
select extensions.http_set_curlopt('CURLOPT_TIMEOUT', '60');
create temp table _u as
  select content::jsonb as j from extensions.http_get(
    'https://raw.githubusercontent.com/skinyanjui/military-yellow-book/58cb25431805868c13388e69defee7c97fc2718d/supabase/unspsc.json');
insert into public.myb_unspsc_groups (letter, title)
  select g->>0, g->>1 from _u, jsonb_array_elements(j->'groups') g;
insert into public.myb_unspsc (code, parent_code, level, ungm_group, access, title, note)
  select r->>0, nullif(r->>1, ''), (r->>2)::smallint, nullif(r->>3, ''), r->>4, r->>5, nullif(r->>6, '')
  from _u, jsonb_array_elements(j->'rows') r;
drop extension http;
