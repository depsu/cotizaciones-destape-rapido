-- ========================================================================
-- FASE 11 — leer y escribir nivel Gmail: contactos, búsqueda FTS5,
-- confianza de imágenes por remitente. Aditivo y no destructivo.
-- Correr ANTES de desplegar el Worker fase11.
--
-- ⚠️ IMPORTANTE PARA RESPALDOS: `wrangler d1 export` NO soporta tablas
-- virtuales (FTS5). Desde esta fase, para exportar hay que botar el índice
-- primero y reconstruirlo después:
--   1) wrangler d1 execute ... --command "DROP TABLE IF EXISTS correos_fts"
--      (los triggers se caen solos al no existir la tabla? NO: botarlos aparte, ver abajo)
--   2) wrangler d1 export ...
--   3) wrangler d1 execute ... --file=scripts-reconstruir-fts.sql
-- El respaldo automático primario sigue siendo Time Travel de D1 (30 días).
-- ========================================================================

-- 1) Contactos para autocompletar (se alimenta solo: cada correo entrante o enviado).
CREATE TABLE IF NOT EXISTS contactos (
  email      TEXT PRIMARY KEY,               -- lower-case
  nombre     TEXT,
  veces      INTEGER DEFAULT 1,
  ultima_vez TEXT DEFAULT (datetime('now'))
);

-- 2) Remitentes cuyas imágenes remotas se muestran siempre ("Mostrar imágenes → siempre").
CREATE TABLE IF NOT EXISTS imagenes_confiables (
  remitente  TEXT PRIMARY KEY,               -- email lower-case
  creado_en  TEXT DEFAULT (datetime('now'))
);

-- 3) Búsqueda de texto completo (RF-28): índice externo sincronizado por triggers.
--    tokenizer unicode61 con diacríticos plegados: "cotizacion" encuentra "cotización".
CREATE VIRTUAL TABLE IF NOT EXISTS correos_fts USING fts5(
  asunto, cuerpo_texto, de, de_nombre,
  content='correos', content_rowid='id',
  tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS correos_fts_ai AFTER INSERT ON correos BEGIN
  INSERT INTO correos_fts(rowid, asunto, cuerpo_texto, de, de_nombre)
  VALUES (new.id, new.asunto, new.cuerpo_texto, new.de, new.de_nombre);
END;
CREATE TRIGGER IF NOT EXISTS correos_fts_ad AFTER DELETE ON correos BEGIN
  INSERT INTO correos_fts(correos_fts, rowid, asunto, cuerpo_texto, de, de_nombre)
  VALUES ('delete', old.id, old.asunto, old.cuerpo_texto, old.de, old.de_nombre);
END;
CREATE TRIGGER IF NOT EXISTS correos_fts_au AFTER UPDATE OF asunto, cuerpo_texto, de, de_nombre ON correos BEGIN
  INSERT INTO correos_fts(correos_fts, rowid, asunto, cuerpo_texto, de, de_nombre)
  VALUES ('delete', old.id, old.asunto, old.cuerpo_texto, old.de, old.de_nombre);
  INSERT INTO correos_fts(rowid, asunto, cuerpo_texto, de, de_nombre)
  VALUES (new.id, new.asunto, new.cuerpo_texto, new.de, new.de_nombre);
END;

-- 4) Poblar el índice con el histórico existente (idempotente vía 'rebuild').
INSERT INTO correos_fts(correos_fts) VALUES ('rebuild');

-- 5) Backfill de contactos desde el histórico (clientes reales: no spam/bloqueados).
INSERT INTO contactos (email, nombre, veces, ultima_vez)
  SELECT lower(de), MAX(COALESCE(NULLIF(de_nombre,''), NULL)), COUNT(*), MAX(COALESCE(recibido_en, creado_en))
  FROM correos
  WHERE de LIKE '%@%' AND lower(de) <> 'contacto@destaperapido.cl'
    AND estado NOT IN ('spam','bloqueado')
  GROUP BY lower(de)
ON CONFLICT(email) DO NOTHING;

-- Nuevo valor de 'estado' (TEXT libre, sin ALTER): 'borrador_salida' = correo NUEVO
-- redactado desde el panel aún no enviado. Nunca aparece en Recibidos/Enviados;
-- vive en la pestaña Borradores.
