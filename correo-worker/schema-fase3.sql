-- Migración Fase 3: adjunto (PDF de cotización) por correo.
ALTER TABLE correos ADD COLUMN adjunto_nombre TEXT;
ALTER TABLE correos ADD COLUMN adjunto_b64    TEXT;  -- PDF en base64 (cotizaciones pesan poco; límite D1 ~2MB)
