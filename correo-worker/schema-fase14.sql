-- ========================================================================
-- FASE 14 — posponer conversaciones ("snooze" de Gmail).
-- Aditivo y no destructivo. Correr ANTES de desplegar el Worker fase14.
-- ========================================================================

-- Fecha/hora (UTC, formato datetime de SQLite) hasta la que la conversación
-- se esconde de Recibidos. Al cumplirse, vuelve sola y arriba de todo.
-- NULL = no está pospuesta (el caso normal).
ALTER TABLE correos ADD COLUMN pospuesto_hasta TEXT;
CREATE INDEX IF NOT EXISTS idx_correos_pospuesto ON correos(pospuesto_hasta);

-- El cron que ya existe (cada 20 min) despierta lo vencido: no hace falta
-- infraestructura nueva ni otro worker.
