-- ========================================================================
-- FASE 9 — etiquetas (IA + manuales) + estados archivado/papelera (soft-delete)
-- Aditivo y no destructivo. Correr ANTES de desplegar el Worker fase9,
-- porque /api/correos y /api/correo pasan a seleccionar c.etiquetas.
-- Respaldo previo recomendado: wrangler d1 export ... antes de correr esto.
-- ========================================================================

-- 1) Etiquetas: CSV en minúsculas, sin comas/saltos internos, sin duplicados, tope 12.
--    NULL = sin etiquetas (se trata con COALESCE(etiquetas,'') en todo el código).
ALTER TABLE correos ADD COLUMN etiquetas TEXT;

-- 2) Estado real previo a archivar/eliminar, para restaurarlo.
--    Columna DEDICADA: NO reusar estado_previo (propiedad exclusiva del bloqueo).
ALTER TABLE correos ADD COLUMN estado_prev_papelera TEXT;

-- Nuevos valores de 'estado' (TEXT libre, sin ALTER): 'archivado', 'papelera'.
-- 'archivado' = atendido/sin respuesta (fuera de pendientes). 'papelera' = borrado suave.
