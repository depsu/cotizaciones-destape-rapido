-- Migración Fase 6: confianza de la IA (para notificación selectiva).
ALTER TABLE correos ADD COLUMN confianza TEXT;   -- 'alta' | 'baja' | NULL
ALTER TABLE correos ADD COLUMN motivo_revision TEXT;  -- por qué la IA quiere que lo revises (si baja)
