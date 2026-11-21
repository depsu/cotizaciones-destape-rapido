-- ============================================================================
-- POSTVENTA (21-nov-2026): lo que pasa con cada baño DESPUÉS de entregarlo.
--
-- La página destaperapido.cl/postventa (resumen-repartidor/postventa.html) lee las
-- entregas de la tabla 'entrega' y les suma lo que el equipo anota desde el celular:
--
--   · postventa_evento   una fila por cosa hecha o acordada, nunca se borra (control):
--                        limpieza hecha, extensión del plazo (renovó por llamada),
--                        retiro, ubicación exacta corregida o una nota. Un error se
--                        anula (anulado = true) y queda a la vista en el historial.
--   · postventa_geo      el punto del mapa de cada entrega (caché): sale del link de
--                        Google Maps, de la dirección buscada en OpenStreetMap o del
--                        centro de la comuna. 'q' guarda lo que se buscó: si cambia la
--                        dirección, se vuelve a buscar.
--   · bucket postventa-fotos   la foto del baño limpio (respaldo de la limpieza).
--
-- El conector del bot (clientes/destaperapido/conexiones/agenda-del-equipo.py) lee
-- postventa_evento: la extensión mueve el fin del servicio, la limpieza cuenta como
-- hecha y el retiro cierra el servicio. Así el bot y la página dicen lo mismo.
--
-- Idempotente: se puede correr varias veces.
-- ============================================================================

create table if not exists public.postventa_evento (
  id          uuid primary key default gen_random_uuid(),
  entrega_id  text not null,
  tipo        text not null check (tipo in ('limpieza','extension','retiro','ubicacion','nota')),
  fecha       date,              -- limpieza / retiro: el día que se hizo · extensión: hasta cuándo queda
  nota        text,              -- ubicación: el link de Google Maps o la dirección exacta
  por         text,              -- quién lo anotó (el nombre que puso en su teléfono)
  foto        text,              -- ruta dentro del bucket postventa-fotos
  anulado     boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists postventa_evento_entrega on public.postventa_evento (entrega_id);

create or replace function public.postventa_evento_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;
drop trigger if exists postventa_evento_touch on public.postventa_evento;
create trigger postventa_evento_touch
  before update on public.postventa_evento
  for each row execute function public.postventa_evento_touch();

alter table public.postventa_evento enable row level security;
drop policy if exists postventa_evento_anon_select on public.postventa_evento;
create policy postventa_evento_anon_select on public.postventa_evento for select using (true);
drop policy if exists postventa_evento_anon_insert on public.postventa_evento;
create policy postventa_evento_anon_insert on public.postventa_evento for insert with check (true);
-- solo se actualiza para ANULAR (o des-anular) una anotación: nada se borra
drop policy if exists postventa_evento_anon_update on public.postventa_evento;
create policy postventa_evento_anon_update on public.postventa_evento for update using (true) with check (true);
grant select, insert, update on public.postventa_evento to anon;
revoke update on public.postventa_evento from anon;
grant update (anulado) on public.postventa_evento to anon;

create table if not exists public.postventa_geo (
  id          text primary key,      -- id de la entrega
  q           text,                  -- lo que se buscó (dirección o link)
  lat         double precision,
  lng         double precision,
  fuente      text check (fuente in ('link','osm','comuna','nada')),
  updated_at  timestamptz not null default now()
);
alter table public.postventa_geo enable row level security;
drop policy if exists postventa_geo_anon_select on public.postventa_geo;
create policy postventa_geo_anon_select on public.postventa_geo for select using (true);
drop policy if exists postventa_geo_anon_insert on public.postventa_geo;
create policy postventa_geo_anon_insert on public.postventa_geo for insert with check (true);
drop policy if exists postventa_geo_anon_update on public.postventa_geo;
create policy postventa_geo_anon_update on public.postventa_geo for update using (true) with check (true);
grant select, insert, update on public.postventa_geo to anon;

-- Fotos: bucket público de lectura (la foto se ve con su link), la página sube con la anon key.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('postventa-fotos', 'postventa-fotos', true, 3145728, array['image/jpeg','image/webp','image/png'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "postventa-fotos: anon sube" on storage.objects;
create policy "postventa-fotos: anon sube" on storage.objects
  for insert to anon with check (bucket_id = 'postventa-fotos');
drop policy if exists "postventa-fotos: se leen" on storage.objects;
create policy "postventa-fotos: se leen" on storage.objects
  for select to anon using (bucket_id = 'postventa-fotos');
