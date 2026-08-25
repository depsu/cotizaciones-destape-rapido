-- ========================================================================
-- FASE 16 — SUBCUENTAS del mismo dominio (ventas@, facturas@ además de contacto@).
-- Aditivo. Correr ANTES de desplegar el Worker fase16.
--
-- La lista de cuentas vive en `[vars] CUENTAS` del wrangler.toml (CSV, formato
-- "correo" o "correo|Etiqueta"); sin esa var, el Worker usa CONTACT_EMAIL como
-- única cuenta y todo sigue funcionando igual que antes.
-- ========================================================================

-- Suscripción push por cuenta: NULL = avisar de todas (comportamiento histórico).
ALTER TABLE push_subs ADD COLUMN cuenta TEXT;

-- ⚠️ MIGRACIÓN MANUAL para bases creadas ANTES de esta fase (el CREATE INDEX de
-- schema-fase8.sql era sobre message_id solo, y descartaba la 2ª entrega de un
-- correo dirigido a dos cuentas nuestras). Correr EN UN SOLO `d1 execute --command`
-- para minimizar la ventana sin unicidad (el pre-check del Worker la cubre):
--
--   DROP INDEX IF EXISTS idx_correos_mid_uniq;
--   CREATE UNIQUE INDEX idx_correos_mid_uniq ON correos(message_id, para)
--     WHERE message_id IS NOT NULL AND message_id <> '';
--
-- Antes de correrlo, verificar que no existan pares que rompan el CREATE:
--   SELECT message_id, para, COUNT(*) FROM correos
--    WHERE message_id IS NOT NULL AND message_id <> ''
--    GROUP BY 1,2 HAVING COUNT(*) > 1;
