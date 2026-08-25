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

-- Firma inicial: la que estaba escrita a mano dentro del panel.
-- Al quedar aquí, se edita sin tocar código y la usan tanto el panel como la IA.
INSERT OR IGNORE INTO ajustes (clave, valor) VALUES
  ('firma_texto', '—
Destape Rápido
contacto@destaperapido.cl
www.destaperapido.cl'),
  ('firma_html', '<div>—</div><div><b>Destape Rápido</b></div><div>contacto@destaperapido.cl</div><div>www.destaperapido.cl</div>'),
  ('firma_activa', '1'),
  ('segundos_deshacer', '6');
