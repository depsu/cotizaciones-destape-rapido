-- ========================================================================
-- FASE 10 — bandeja por conversaciones (nivel Gmail), parte de datos.
-- Aditivo y no destructivo. Correr ANTES de desplegar el Worker fase10.
-- Respaldo previo recomendado: wrangler d1 export ... antes de correr esto.
-- ========================================================================

-- 1) Nombre visible del remitente ("Rita Pérez" en vez de rperez@...).
--    postal-mime ya lo entrega en parsed.from.name; hasta hoy se descartaba.
--    NULL en filas legacy: el panel cae a mostrar la dirección.
ALTER TABLE correos ADD COLUMN de_nombre TEXT;

-- 2) Índice para la lista agrupada por hilo (GROUP BY thread_id + orden por fecha).
CREATE INDEX IF NOT EXISTS idx_correos_thread_fecha
  ON correos(thread_id, recibido_en DESC);

-- Notas (sin DDL):
-- · El threading pasa a estilo Gmail en el Worker: adopta hilo por In-Reply-To/References;
--   si no, busca un correo del MISMO asunto normalizado + misma contraparte en los últimos
--   7 días y adopta su thread_id; si no, crea un hilo NUEVO único. Los thread_id legacy
--   ('s:<asunto>|<contraparte>') siguen siendo válidos: el id es opaco.
-- · 'respondido' pasa a considerarse "en Recibidos" (Gmail: responder no archiva);
--   el hilo sale de Recibidos solo al archivar, y VUELVE solo si llega mensaje nuevo.
-- · No se necesitan flags nuevos de hilo: la carpeta de un hilo se deriva de los estados
--   de sus mensajes en /api/hilos.
