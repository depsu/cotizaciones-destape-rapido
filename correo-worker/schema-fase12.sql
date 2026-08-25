-- ========================================================================
-- FASE 12 — pulido profesional: plantillas de respuesta (idea de Zoho Mail).
-- Aditivo y no destructivo. Correr ANTES de desplegar el Worker fase12.
-- ========================================================================
CREATE TABLE IF NOT EXISTS plantillas (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre    TEXT NOT NULL,
  cuerpo    TEXT NOT NULL,
  creado_en TEXT DEFAULT (datetime('now'))
);
