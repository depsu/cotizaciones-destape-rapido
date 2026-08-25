-- Bota el índice FTS5 y sus triggers ANTES de un `wrangler d1 export`.
-- Reconstruir después con scripts-reconstruir-fts.sql.
DROP TRIGGER IF EXISTS correos_fts_ai;
DROP TRIGGER IF EXISTS correos_fts_ad;
DROP TRIGGER IF EXISTS correos_fts_au;
DROP TABLE IF EXISTS correos_fts;
