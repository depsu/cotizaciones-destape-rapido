-- ============================================================================
-- Agenda de DESTAPES (área camión, hidrojet y cámara). 24-oct-2026.
--
-- Gemela de la página de baños (tablas entrega / entrega_estado) pero SEPARADA:
-- las dos áreas nunca se cruzan. Dos tablas:
--
--   destape         CONTENIDO de cada destape (lo sube subir_destape.py cuando el bot
--                   confirma y avisa al equipo). card_html = tarjeta ya renderizada.
--   destape_estado  ESTADO que cambia el equipo desde el celular (realizado, cobrado,
--                   fecha reagendada, valor final cobrado, comisión pagada).
--
-- Idempotente: se puede correr varias veces. Se aplica por la Management API
-- (ver resumen-repartidor/ARQUITECTURA.md §Aplicar migraciones).
-- ============================================================================

create table if not exists public.destape (
  id            text primary key,              -- AAAA-MM-DD-<servicio>-<4 últimos del teléfono>
  fecha         date,
  informado_at  timestamptz not null default now(),
  data          jsonb not null,
  card_html     text,
  eliminado     boolean not null default false,
  updated_at    timestamptz not null default now()
);
create index if not exists destape_informado_at_idx on public.destape (informado_at desc);
create index if not exists destape_pedido_idx on public.destape ((data->>'pedido_id'));

create table if not exists public.destape_estado (
  id              text primary key,            -- = destape.id
  estado          text not null default 'pendiente'
                    check (estado in ('pendiente','realizado','cobrado')),
  fecha           date,                        -- reagendado; null = la fecha del destape
  valor_final     integer,                     -- neto que se cobró de verdad (si cambió en terreno)
  comision_pagada boolean not null default false,
  pagada_at       timestamptz,
  contactado      boolean not null default false,
  eliminado       boolean not null default false,
  nota            text,
  updated_at      timestamptz not null default now()
);

-- updated_at automático
create or replace function public.destape_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists destape_touch on public.destape;
create trigger destape_touch before update on public.destape
  for each row execute function public.destape_touch();

drop trigger if exists destape_estado_touch on public.destape_estado;
create trigger destape_estado_touch before update on public.destape_estado
  for each row execute function public.destape_touch();

-- ---------------------------------------------------------------------------
-- RLS: acceso anónimo (la página no tiene login) acotado SOLO a estas dos tablas.
-- ---------------------------------------------------------------------------
alter table public.destape enable row level security;
drop policy if exists destape_anon_select on public.destape;
create policy destape_anon_select on public.destape for select using (true);
drop policy if exists destape_anon_insert on public.destape;
create policy destape_anon_insert on public.destape for insert with check (true);
drop policy if exists destape_anon_update on public.destape;
create policy destape_anon_update on public.destape for update using (true) with check (true);
grant select, insert, update on public.destape to anon;

alter table public.destape_estado enable row level security;
drop policy if exists destape_estado_anon_select on public.destape_estado;
create policy destape_estado_anon_select on public.destape_estado for select using (true);
drop policy if exists destape_estado_anon_insert on public.destape_estado;
create policy destape_estado_anon_insert on public.destape_estado for insert with check (true);
drop policy if exists destape_estado_anon_update on public.destape_estado;
create policy destape_estado_anon_update on public.destape_estado for update using (true) with check (true);
grant select, insert, update on public.destape_estado to anon;
