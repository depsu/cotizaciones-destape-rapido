-- Migración Fase 5: cola de "Ajuste IA".
ALTER TABLE correos ADD COLUMN ajuste_pedido TEXT;            -- instrucción en lenguaje natural del dueño
ALTER TABLE correos ADD COLUMN ajuste_enviar INTEGER DEFAULT 0; -- 1 = aplicar y ENVIAR (saltar validación)
