-- ========================================================================
-- FASE 8 — dedup + hilos + bloqueo/aprendizaje + leído (Agente Cotizaciones)
-- Ejecutar de arriba a abajo. NO crear el índice UNIQUE antes del colapso.
-- Respaldo previo OBLIGATORIO (wrangler d1 export ... antes de correr esto).
-- ========================================================================

-- ---- 1.1 Columnas nuevas en 'correos' (no destructivas; legacy quedan NULL) ----
ALTER TABLE correos ADD COLUMN dedup_hash  TEXT;    -- SHA-256 de (de|asunto|cuerpo[:2000]); solo filas futuras
ALTER TABLE correos ADD COLUMN thread_id   TEXT;    -- 's:<asuntoNorm>|<contraparte>' o thread adoptado por header
ALTER TABLE correos ADD COLUMN in_reply_to TEXT;    -- header In-Reply-To (hoy no se guarda)
ALTER TABLE correos ADD COLUMN referencias TEXT;    -- header References crudo
ALTER TABLE correos ADD COLUMN leido       INTEGER NOT NULL DEFAULT 0;  -- 0=no leído (negrita)
ALTER TABLE correos ADD COLUMN estado_previo TEXT;  -- estado antes de bloquear, para restaurarlo al desbloquear
-- Nuevo valor de 'estado': 'bloqueado' (estado ya es TEXT libre; sin ALTER). Oculto de toda vista.

-- ---- 1.2 Colapso de duplicados CON Message-ID (342 -> ~27). MIN(id) sobrevive. ----
-- PRE-CHECK (correr aparte y confirmar 0 filas antes de borrar):
--   SELECT message_id, count(*) n, count(DISTINCT estado) est, SUM(respuesta_enviada IS NOT NULL) resp
--   FROM correos WHERE message_id IS NOT NULL AND message_id<>'' GROUP BY message_id HAVING n>1
--   AND (est>1 OR resp>0);   -- debe devolver 0 filas; si no, ABORTAR y revisar a mano.
DELETE FROM correos
WHERE message_id IS NOT NULL AND message_id <> ''
  AND id NOT IN (
    SELECT MIN(id) FROM correos
    WHERE message_id IS NOT NULL AND message_id <> ''
    GROUP BY message_id
  );

-- ---- 1.3 Colapso conservador de dupes SIN Message-ID (idénticos y del MISMO estado) ----
DELETE FROM correos
WHERE (message_id IS NULL OR message_id = '')
  AND id NOT IN (
    SELECT MIN(id) FROM correos
    WHERE (message_id IS NULL OR message_id = '')
    GROUP BY de, asunto, substr(cuerpo_texto,1,2000), estado
  );

-- ---- 1.4 Backfill de 'leido': lo archivado/resuelto se considera leído ----
UPDATE correos SET leido = 1 WHERE estado IN ('respondido','enviado','spam','bloqueado');
-- 'nuevo','borrador','ajuste' quedan en 0 (DEFAULT) = no leído.

-- ---- 1.5 Tabla de BLOQUEO permanente (R5). Sobrevive al dedup (independiente de correos) ----
CREATE TABLE IF NOT EXISTS bloqueados (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo      TEXT NOT NULL,                       -- 'email' | 'dominio'
  valor     TEXT NOT NULL,                       -- lower-case: email completo o dominio del REMITENTE
  motivo    TEXT,                                -- obligatorio desde el panel (R8)
  creado_en TEXT DEFAULT (datetime('now')),
  UNIQUE(tipo, valor)
);
CREATE INDEX IF NOT EXISTS idx_bloqueados_valor ON bloqueados(valor);

-- ---- 1.6 Tabla de APRENDIZAJE de la IA (R8). Independiente de correos ----
CREATE TABLE IF NOT EXISTS aprendizaje (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  senal     TEXT NOT NULL,                       -- 'spam' | 'legit' | 'bloqueo' | 'desbloqueo'
  remitente TEXT,                                -- email lower-case
  dominio   TEXT,                                -- dominio del remitente lower-case
  motivo    TEXT,                                -- razón dada por el dueño
  correo_id INTEGER,                             -- correo origen (NULL si no aplica)
  creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_aprendizaje_remitente ON aprendizaje(remitente);
CREATE INDEX IF NOT EXISTS idx_aprendizaje_dominio   ON aprendizaje(dominio);

-- ---- 1.7 Backfill de memoria desde el histórico (da contexto a la IA) ----
INSERT INTO aprendizaje (senal, remitente, dominio, motivo)
  SELECT 'spam', lower(de), lower(substr(de, instr(de,'@')+1)), 'backfill: estaba en spam'
  FROM correos WHERE estado='spam' AND de LIKE '%@%' GROUP BY lower(de);
INSERT INTO aprendizaje (senal, remitente, dominio, motivo)
  SELECT 'legit', lower(de), lower(substr(de, instr(de,'@')+1)), 'backfill: fue respondido'
  FROM correos WHERE estado='respondido' AND de LIKE '%@%' GROUP BY lower(de);

-- ---- 1.8 Índices (RECIÉN ahora, tras el colapso) ----
-- UNIQUE parcial: excluye NULL y '' (permite múltiples 'enviado' sin resend_id y correos sin Message-ID)
CREATE UNIQUE INDEX IF NOT EXISTS idx_correos_mid_uniq ON correos(message_id)
  WHERE message_id IS NOT NULL AND message_id <> '';
CREATE INDEX IF NOT EXISTS idx_correos_dedup_hash  ON correos(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_correos_orden       ON correos(recibido_en DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_correos_thread      ON correos(thread_id);
CREATE INDEX IF NOT EXISTS idx_correos_estado_fecha ON correos(estado, recibido_en DESC);
