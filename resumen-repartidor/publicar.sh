#!/usr/bin/env bash
# Regenera el listado de entregas y lo publica en GitHub Pages en un solo paso.
# Uso: bash resumen-repartidor/publicar.sh "mensaje del commit"
set -e
cd "$(dirname "$0")/.."

# GitHub Pages corre Jekyll por defecto y se atasca/erra con este sitio estático.
# .nojekyll hace que publique los HTML tal cual (build ~15s). Lo garantizamos siempre.
[ -f .nojekyll ] || touch .nojekyll

python3 resumen-repartidor/scripts/generar_listado.py

# Mantener Supabase consistente con entregas.json (card_html fresco). La página lee
# de Supabase; esto evita que quede una tarjeta vieja si se editó una entrega. No es
# fatal: si Supabase está pausado, igual publicamos el respaldo horneado.
python3 resumen-repartidor/scripts/sync_entregas_supabase.py \
  || echo "⚠️  No se pudo sincronizar Supabase (se publica el respaldo horneado igual)."

git add -A
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit 0
fi
git commit -q -m "${1:-actualiza entregas}"
git push -q origin main
echo "✅ Publicado. Página: https://depsu.github.io/cotizaciones-destape-rapido/"
