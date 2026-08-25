-- ========================================================================
-- FASE 15 — ajustes del panel (firma configurable y compañía).
-- Aditivo. Correr ANTES de desplegar el Worker fase15.
-- ========================================================================

-- Tabla llave/valor para lo que el dueño configura desde el panel.
-- Hoy: firma (texto y HTML), nombre visible, segundos de "deshacer envío".
-- Es llave/valor a propósito: agregar un ajuste nuevo no requiere migrar la base.
CREATE TABLE IF NOT EXISTS ajustes (
  clave       TEXT PRIMARY KEY,
  valor       TEXT,
  actualizado TEXT DEFAULT (datetime('now'))
);

-- Semilla NEUTRA (repo maestro: cero datos de cliente). La firma real se escribe
-- desde el panel (Ajustes) o se siembra en el CLON reemplazando estos valores.
INSERT OR IGNORE INTO ajustes (clave, valor) VALUES
  ('firma_texto', ''),
  ('firma_html', ''),
  ('firma_activa', '1'),
  ('segundos_deshacer', '6');
