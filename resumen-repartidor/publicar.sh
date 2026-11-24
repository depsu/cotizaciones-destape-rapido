#!/usr/bin/env bash
# Regenera la página del repartidor y la publica en GitHub Pages en un solo paso.
# Uso: bash resumen-repartidor/publicar.sh "mensaje del commit" [--sincronizar]
#
# (15-nov-2026) Dos cambios de seguridad:
#  - Ya NO re-sincroniza entregas.json sobre Supabase por defecto. Ese archivo quedó en agosto y la
#    sincronización pisaba con datos viejos las entregas que el bot corrigió después. Las entregas
#    nuevas entran solas (resumen_repartidor.py --enviar o el bot). Si de verdad hace falta: --sincronizar.
#  - Ya NO hace `git add -A`. Este repo es PÚBLICO y en la carpeta hay planillas e informes con datos
#    de clientes sin rastrear (una vez ya se subieron cotizaciones con RUT y correos). Solo se agregan
#    los archivos de la página.
set -euo pipefail
cd "$(dirname "$0")/.."

MENSAJE="actualiza la página del repartidor"
SINCRONIZAR=0
for a in "$@"; do
  if [ "$a" = "--sincronizar" ]; then SINCRONIZAR=1; else MENSAJE="$a"; fi
done

# GitHub Pages corre Jekyll por defecto y se atasca/erra con este sitio estático.
# .nojekyll hace que publique los HTML tal cual (build ~15s). Lo garantizamos siempre.
[ -f .nojekyll ] || touch .nojekyll

python3 resumen-repartidor/scripts/generar_listado.py

if [ "$SINCRONIZAR" = "1" ]; then
  python3 resumen-repartidor/scripts/sync_entregas_supabase.py \
    || echo "⚠️  No se pudo sincronizar Supabase."
fi

git add .nojekyll resumen-repartidor/listado.html resumen-repartidor/listado-nuevo.html resumen-repartidor/scripts/generar_listado.py \
  resumen-repartidor/publicidad resumen-repartidor/comprobantes
if git diff --cached --quiet; then
  echo "Sin cambios que publicar."
  exit 0
fi
git commit -q -m "$MENSAJE"
git push -q origin main
echo "✅ Publicado (GitHub Pages tarda ~1 min). Página: https://www.destaperapido.cl/entregas"
