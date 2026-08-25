-- ========================================================================
-- FASE 13 — cerrar la brecha con Gmail:
--   1) adjuntos que MANDA el cliente (hasta ahora se perdían),
--   2) conversaciones destacadas (la estrella de Gmail).
-- Aditivo y no destructivo. Correr ANTES de desplegar el Worker fase13.
-- ========================================================================

-- 1) Adjuntos entrantes. Se guardan en D1 SOLO si son chicos; de los grandes queda
--    el registro (nombre y peso) para que el panel los muestre y diga dónde están.
--    Sin R2: nada de infraestructura nueva (decisión pendiente de Alejandro).
CREATE TABLE IF NOT EXISTS adjuntos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  correo_id INTEGER NOT NULL,
  nombre    TEXT,
  mime      TEXT,
  tamano    INTEGER,                 -- bytes reales del archivo
  cid       TEXT,                    -- Content-ID: imágenes incrustadas en el HTML (src="cid:…")
  inline    INTEGER DEFAULT 0,       -- 1 = va dentro del cuerpo, no se lista como adjunto
  datos_b64 TEXT,                    -- NULL si excedió el tope: solo queda el registro
  creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_adjuntos_correo ON adjuntos(correo_id);

-- 2) Destacados (la estrella de Gmail). A nivel de MENSAJE; el hilo se muestra
--    destacado si cualquiera de sus mensajes lo está.
ALTER TABLE correos ADD COLUMN destacado INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_correos_destacado ON correos(destacado);
