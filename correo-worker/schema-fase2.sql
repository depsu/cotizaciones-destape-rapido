-- Migración Fase 2: campos de respuesta (borrador, enviada) sobre la tabla correos.
ALTER TABLE correos ADD COLUMN respuesta_borrador TEXT;
ALTER TABLE correos ADD COLUMN respuesta_enviada  TEXT;
ALTER TABLE correos ADD COLUMN respondido_en      TEXT;
-- estado ya existe: nuevo | borrador | respondido
