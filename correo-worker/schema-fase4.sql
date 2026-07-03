-- Migración Fase 4: notificaciones push (PWA).
ALTER TABLE correos ADD COLUMN notificado INTEGER DEFAULT 0;  -- 0 = aún no avisado por push

CREATE TABLE IF NOT EXISTS push_subs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint  TEXT UNIQUE,
  p256dh    TEXT,
  auth      TEXT,
  creado_en TEXT DEFAULT (datetime('now'))
);
