-- ========================================================================
-- FASE 17 (C1, oct-2026) — contratos para que dixdybot proyecte y opere el buzón.
-- NO HACE FALTA CORRERLA A MANO: el Worker la aplica solo al arrancar (src/contratos.js,
-- migrarC1), una vez por isolate y de forma idempotente. Queda aquí como referencia y para
-- bases que se quieran preparar antes del deploy. Aditiva: no borra ni cambia nada.
-- Ojo: los ALTER fallan si el Worker ya migró ("duplicate column"): en ese caso no hace falta.
-- ========================================================================

-- 1) Marca de cambio (ms UNIX) y revisión por mensaje. Las mantienen los triggers de abajo
--    en TODO insert/update (incluidos los que se hagan a mano), no el código de cada ruta.
ALTER TABLE correos ADD COLUMN modificado_en INTEGER;
ALTER TABLE correos ADD COLUMN revision INTEGER;

-- 2) Lápidas: un DELETE real deja rastro para el feed /api/cambios.
CREATE TABLE IF NOT EXISTS correos_borrados (id INTEGER PRIMARY KEY, borrado_en INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_correos_borrados_en ON correos_borrados(borrado_en, id);

-- 3) Idempotencia de escrituras (solicitud_id → mismo resultado).
CREATE TABLE IF NOT EXISTS operaciones (
  id TEXT PRIMARY KEY, ruta TEXT NOT NULL, huella TEXT NOT NULL, estado TEXT NOT NULL,
  http INTEGER, resultado TEXT, creado_en INTEGER NOT NULL, actualizado_en INTEGER NOT NULL);

-- 4) Backfill del histórico (ANTES de los triggers): última actividad conocida.
UPDATE correos SET
  modificado_en = COALESCE(modificado_en, MIN(COALESCE(
    CAST((julianday(respondido_en) - 2440587.5) * 86400000 AS INTEGER),
    CAST((julianday(recibido_en)   - 2440587.5) * 86400000 AS INTEGER),
    CAST((julianday(creado_en)     - 2440587.5) * 86400000 AS INTEGER),
    CAST((julianday('now')         - 2440587.5) * 86400000 AS INTEGER)),
    CAST((julianday('now')         - 2440587.5) * 86400000 AS INTEGER))),  -- nunca en el futuro
  revision = COALESCE(revision, 1)
WHERE modificado_en IS NULL OR revision IS NULL;
CREATE INDEX IF NOT EXISTS idx_correos_modificado ON correos(modificado_en, id);

-- 5) Triggers.
CREATE TRIGGER IF NOT EXISTS correos_rev_ai AFTER INSERT ON correos
BEGIN
  UPDATE correos SET modificado_en = CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER), revision = 1
  WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS correos_rev_au AFTER UPDATE ON correos
WHEN NEW.revision IS OLD.revision
BEGIN
  UPDATE correos SET modificado_en = CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER),
                     revision = COALESCE(OLD.revision, 0) + 1
  WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS correos_rev_ad AFTER DELETE ON correos
BEGIN
  INSERT OR REPLACE INTO correos_borrados (id, borrado_en)
  VALUES (OLD.id, CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER));
END;
CREATE TRIGGER IF NOT EXISTS adjuntos_rev_ai AFTER INSERT ON adjuntos
BEGIN
  UPDATE correos SET leido = leido WHERE id = NEW.correo_id;
END;
