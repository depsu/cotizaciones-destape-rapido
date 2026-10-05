-- Fase 18 (5-oct-2026) — consumo de D1. La crea sola la migración del Worker
-- (src/contratos.js · migrarC1); este archivo es la referencia manual.
-- Índice sobre la clave de hilo + fecha/id del «último mensaje»: el GROUP BY de /api/hilos y
-- /api/buscar lo recorre en orden (sin ordenamiento temporal), el último mensaje de cada hilo
-- sale sin ordenar, y las consultas `COALESCE(thread_id,'id:'||id) = ?` dejan de leer la
-- tabla entera.
CREATE INDEX IF NOT EXISTS idx_correos_hilo ON correos(
  COALESCE(thread_id, 'id:'||id),
  datetime(COALESCE(respondido_en, recibido_en, creado_en)) DESC,
  id DESC);

-- Dedup e hilo de la captura (3 consultas por correo entrante filtran por message_id).
CREATE INDEX IF NOT EXISTS idx_correos_message_id ON correos(message_id);
