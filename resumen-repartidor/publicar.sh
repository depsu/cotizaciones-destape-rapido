#!/usr/bin/env bash
# Regenera el listado de entregas y lo publica en GitHub Pages en un solo paso.
# Uso: bash resumen-repartidor/publicar.sh "mensaje del commit"
set -e
cd "$(dirname "$0")/.."

python3 resumen-repartidor/scripts/generar_listado.py
git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit 0
fi
git commit -q -m "${1:-actualiza entregas}"
git push -q origin main
echo "✅ Publicado. Página: https://depsu.github.io/cotizaciones-destape-rapido/"
