-- ============================================================================
-- Tabla de CONTENIDO de las entregas (para la página del repartidor).
--
-- Antes el contenido de cada entrega (cliente, dirección, monto, factura, etc.)
-- vivía en entregas.json y se horneaba en listado.html — por eso cada entrega
-- nueva obligaba a regenerar + publicar el HTML. Ahora el contenido vive AQUÍ y
-- la página lo lee en vivo por REST (igual que ya hacía con entrega_estado).
--
-- Modelo simple y flexible: el objeto completo de la entrega va en `data` (jsonb),
-- con la misma forma que tenía en entregas.json. Solo se sacan a columnas los
-- campos que sirven para ordenar/filtrar:
--   id           = mismo id de siempre (AAAA-MM-DD-cliente-kebab), PK.
--   fecha        = fecha de entrega (para agrupar por día).
--   informado_at = CUÁNDO se informó/agregó la entrega. La página ordena por
--                  esto DESC → la más reciente informada queda arriba.
--
-- El ESTADO mutable (entregado/cobrado/reagendado/comisión) sigue en
-- entrega_estado; se une por `id`. Ver entrega_estado.sql.
--
-- Cómo aplicarlo:  Supabase → SQL Editor → pega TODO → Run.  Idempotente.
-- ============================================================================

create table if not exists public.entrega (
  id            text primary key,
  fecha         date,
  informado_at  timestamptz not null default now(),
  data          jsonb not null,
  eliminado     boolean not null default false,
  updated_at    timestamptz not null default now()
);

-- card_html: la tarjeta de la entrega YA renderizada (por la función Python
-- tarjeta() del generador). La página solo pide este HTML y lo inyecta, sin
-- portar el template a JS. Idempotente (por si la tabla ya existía sin la columna).
alter table public.entrega add column if not exists card_html text;

-- índice para el orden por más reciente informada.
create index if not exists entrega_informado_at_idx on public.entrega (informado_at desc);

-- updated_at automático en cada UPDATE.
create or replace function public.entrega_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists entrega_touch on public.entrega;
create trigger entrega_touch
  before update on public.entrega
  for each row execute function public.entrega_touch();

-- ---------------------------------------------------------------------------
-- RLS: acceso anónimo (la página no tiene login) acotado SOLO a esta tabla.
-- ---------------------------------------------------------------------------
alter table public.entrega enable row level security;

drop policy if exists entrega_anon_select on public.entrega;
create policy entrega_anon_select on public.entrega
  for select using (true);

drop policy if exists entrega_anon_insert on public.entrega;
create policy entrega_anon_insert on public.entrega
  for insert with check (true);

drop policy if exists entrega_anon_update on public.entrega;
create policy entrega_anon_update on public.entrega
  for update using (true) with check (true);

grant select, insert, update on public.entrega to anon;
