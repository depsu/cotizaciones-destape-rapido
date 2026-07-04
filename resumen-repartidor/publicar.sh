#!/usr/bin/env bash
# Regenera el listado de entregas y lo publica en GitHub Pages en un solo paso.
# Uso: bash resumen-repartidor/publicar.sh "mensaje del commit"
set -e
cd "$(dirname "$0")/.."

# GitHub Pages corre Jekyll por defecto y se atasca/erra con este sitio estático.
# .nojekyll hace que publique los HTML tal cual (build ~15s). Lo garantizamos siempre.
[ -f .nojekyll ] || touch .nojekyll

python3 resumen-repartidor/scripts/generar_listado.py
git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit 0
fi
git commit -q -m "${1:-actualiza entregas}"
git push -q origin main
echo "✅ Publicado. Página: https://depsu.github.io/cotizaciones-destape-rapido/"
