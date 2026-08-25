-- Reconstruye el índice de búsqueda FTS5 tras un `wrangler d1 export`.
-- (El export no soporta tablas virtuales: hay que botar y volver a crear.)
-- Uso completo del respaldo manual:
--   npx wrangler d1 execute agente-correos-db --remote -y --file=scripts-botar-fts.sql
--   npx wrangler d1 export  agente-correos-db --remote --output respaldos/....sql
--   npx wrangler d1 execute agente-correos-db --remote -y --file=scripts-reconstruir-fts.sql
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
INSERT INTO correos_fts(correos_fts) VALUES ('rebuild');
