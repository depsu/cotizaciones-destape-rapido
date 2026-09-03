-- ============================================================================
-- COBROS DE PUBLICIDAD al repartidor (página del repartidor, 2026-09-02).
--
-- Alejandro paga la publicidad (Google Ads / Meta) y al repartidor le toca una
-- parte (hoy la mitad). Cada rendición (scripts/rendir-publicidad.py del maestro
-- DIXDY) se publica acá con su imagen del desglose; la página la muestra en la
-- cabecera (a la derecha) y en la vista 💰 Comisión como "pendiente por pagar",
-- y se paga con el MISMO flujo que las comisiones (Pagar → transferencia → WhatsApp).
--
-- La escribe scripts/publicar_cobro_publicidad.py (anon key + RLS, como todo lo
-- demás de la página). Idempotente: se puede correr varias veces.
-- ============================================================================

create table if not exists public.cobro_publicidad (
  id            text primary key,          -- "<desde>_<hasta>[-campaña]" (carpeta de la rendición)
  campana       text not null,             -- nombre de la campaña, como la ve el dueño
  plataforma    text not null default 'Google Ads',
  desde         date not null,
  hasta         date not null,
  gasto_total   integer not null,          -- lo que se gastó en total (CLP)
  fraccion      numeric(4,3) not null default 0.5,  -- parte que le toca al repartidor
  monto         integer not null,          -- = round(gasto_total * fraccion)
  imagen        text,                      -- ruta relativa a listado.html (publicidad/<id>.png)
  miniatura     text,                      -- versión chica para la cabecera
  detalle       jsonb not null default '{}'::jsonb,  -- líneas del desglose (clics, contactos, costo…)
  nota          text,
  pagado        boolean not null default false,
  pagada_at     timestamptz,
  eliminado     boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create or replace function public.cobro_publicidad_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists cobro_publicidad_touch on public.cobro_publicidad;
create trigger cobro_publicidad_touch
  before update on public.cobro_publicidad
  for each row execute function public.cobro_publicidad_touch();

alter table public.cobro_publicidad enable row level security;
drop policy if exists cobro_publicidad_anon_select on public.cobro_publicidad;
create policy cobro_publicidad_anon_select on public.cobro_publicidad for select using (true);
drop policy if exists cobro_publicidad_anon_insert on public.cobro_publicidad;
create policy cobro_publicidad_anon_insert on public.cobro_publicidad for insert with check (true);
drop policy if exists cobro_publicidad_anon_update on public.cobro_publicidad;
create policy cobro_publicidad_anon_update on public.cobro_publicidad for update using (true) with check (true);
grant select, insert, update on public.cobro_publicidad to anon;
