-- Product and service photos for listings.
-- images holds public URLs in the listing-images bucket (https only, validated by the CHECK below).
-- Sample listings have none: the site shows an honest "No photos yet" tile instead of stock or generated art.
alter table public.myb_listings add column if not exists images text[] not null default '{}';
alter table public.myb_listings drop constraint if exists myb_listings_images_check;
alter table public.myb_listings add constraint myb_listings_images_check
  check (cardinality(images) <= 8 and array_to_string(images, ' ') !~ '[[:space:]<>"'']');
grant select (images) on public.myb_listings to anon, authenticated;

-- Public bucket, 5 MB, web image types only. Anyone can read; a signed-in user can write only inside their own folder.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('listing-images', 'listing-images', true, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "listing images: owner write" on storage.objects;
create policy "listing images: owner write" on storage.objects for insert to authenticated
  with check (bucket_id = 'listing-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "listing images: owner update" on storage.objects;
create policy "listing images: owner update" on storage.objects for update to authenticated
  using (bucket_id = 'listing-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "listing images: owner delete" on storage.objects;
create policy "listing images: owner delete" on storage.objects for delete to authenticated
  using (bucket_id = 'listing-images' and (storage.foldername(name))[1] = (select auth.uid())::text);
