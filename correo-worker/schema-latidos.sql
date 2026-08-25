-- Latidos de los motores locales (rondas). La torre de control (y el celular vía
-- GET /api/latidos) los lee para mostrar 🟢 "última pasada hace Xs".
-- Aplicar una vez por cliente:  npx wrangler d1 execute <db> --remote --file=schema-latidos.sql
CREATE TABLE IF NOT EXISTS latidos (
  loop   TEXT PRIMARY KEY,   -- ej: "correo-ronda", "ads-ronda"
  ultimo TEXT NOT NULL,      -- ISO 8601 UTC de la última pasada
  nota   TEXT                -- opcional: "3 respondidos, 1 dudoso"
);
