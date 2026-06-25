-- ============================================================================
-- Tabla de ESTADO MUTABLE de las entregas (para la página del repartidor).
--
-- El CONTENIDO de cada entrega (cliente, dirección, monto, etc.) vive en
-- entregas.json y se hornea en listado.html. Esta tabla guarda SOLO lo que el
-- repartidor cambia desde el celular: el estado, la fecha reagendada y el cobro;
-- más el flag 'comision_pagada' que marca Alejandro cuando ya le pagaron su 20%.
--
-- La clave 'id' coincide con el id de la entrega en entregas.json
-- (formato AAAA-MM-DD-cliente-kebab).
--
-- Cómo aplicarlo:  Supabase → SQL Editor → pega TODO esto → Run.
-- Es idempotente: se puede correr varias veces sin romper nada.
-- ============================================================================

create table if not exists public.entrega_estado (
  id              text primary key,
  estado          text not null default 'pendiente'
                    check (estado in ('pendiente','en-camino','entregado','cobrado')),
  fecha           date,                      -- override al reagendar; null = usa la de entregas.json
  comision_pagada boolean not null default false,
  pagada_at       timestamptz,               -- hora en que el repartidor marcó el pago (para verificar/revocar)
  nota            text,
  updated_at      timestamptz not null default now()
);

-- Columna añadida después (idempotente para bases ya creadas).
alter table public.entrega_estado add column if not exists pagada_at timestamptz;

-- updated_at automático en cada UPDATE.
create or replace function public.entrega_estado_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists entrega_estado_touch on public.entrega_estado;
create trigger entrega_estado_touch
  before update on public.entrega_estado
  for each row execute function public.entrega_estado_touch();

-- ---------------------------------------------------------------------------
-- RLS: acceso anónimo (la página no tiene login) acotado SOLO a esta tabla.
-- El resto de la base no se ve afectado.
-- ---------------------------------------------------------------------------
alter table public.entrega_estado enable row level security;

drop policy if exists entrega_estado_anon_select on public.entrega_estado;
create policy entrega_estado_anon_select on public.entrega_estado
  for select using (true);

drop policy if exists entrega_estado_anon_insert on public.entrega_estado;
create policy entrega_estado_anon_insert on public.entrega_estado
  for insert with check (true);

drop policy if exists entrega_estado_anon_update on public.entrega_estado;
create policy entrega_estado_anon_update on public.entrega_estado
  for update using (true) with check (true);

-- PostgREST usa el rol 'anon' para peticiones con la anon key.
grant select, insert, update on public.entrega_estado to anon;
