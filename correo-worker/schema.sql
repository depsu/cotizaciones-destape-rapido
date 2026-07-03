-- Esquema D1 para la captura de correos entrantes (Fase 1).
CREATE TABLE IF NOT EXISTS correos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id   TEXT,
  de           TEXT,                       -- remitente (from)
  para         TEXT,                       -- destinatario (to)
  asunto       TEXT,
  cuerpo_texto TEXT,
  cuerpo_html  TEXT,
  dominio      TEXT,                        -- derivado de 'para' (multi-dominio futuro)
  estado       TEXT DEFAULT 'nuevo',        -- nuevo | leido (respondido en fases siguientes)
  recibido_en  TEXT,                        -- fecha del correo (ISO)
  creado_en    TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_correos_recibido ON correos(recibido_en DESC);
CREATE INDEX IF NOT EXISTS idx_correos_dominio  ON correos(dominio);
