# Probadores del panel del repartidor

El panel es JavaScript suelto dentro de un HTML generado: no lo mira ningún linter ni
ningún test del repo. Estos arneses lo cargan en un contexto de `vm` con un `document`
de mentira y comprueban lo que se rompe callado.

## `probar-mes.cjs` — la vista del mes

Comprueba que tocar la ganancia de la cabecera abre la vista, que se pinta aunque la red
no haya respondido, que el selector cambia de mes, que el filtro «Todas / Por cobrar»
muestra una sola lista, y que las vistas de Entregas y Comisión siguen funcionando.

```sh
python3 resumen-repartidor/scripts/generar_listado.py /tmp/listado-nuevo.html
python3 - <<'PY'
import re, pathlib
html = pathlib.Path("/tmp/listado-nuevo.html").read_text(encoding="utf-8")
for i, b in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
    pathlib.Path(f"/tmp/js-{i}.js").write_text(b, encoding="utf-8")
PY
node resumen-repartidor/tests/probar-mes.cjs
```

## Por qué un DOM de mentira y no un navegador

Es la ley DIXDY: primero se comprueba desde el código, y el navegador se reserva para
render visual real, CSP o layout. Un clic que cambia de vista y un cálculo de totales se
verifican perfectamente acá, en dos segundos y sin depender de que la extensión esté viva.

## `navegador/` — lo que solo se ve en un navegador de verdad (15-nov-2026)

Cuando el cambio toca **cómo carga o cómo pinta** la página (qué se pide a Supabase, qué tarjetas se
ponen, en qué orden), el DOM de mentira no alcanza. Estos dos corren Chrome sin ventana con los datos
REALES de Supabase: solo leen; toda escritura (POST/PATCH) se intercepta y se anota, nunca llega a la base.

```sh
curl -s https://depsu.github.io/cotizaciones-destape-rapido/resumen-repartidor/listado.html -o /tmp/publicado.html
python3 resumen-repartidor/scripts/generar_listado.py /tmp/nuevo.html
node resumen-repartidor/tests/navegador/probar-equivalencia.mjs /tmp/publicado.html /tmp/nuevo.html p-9t4kqv
node resumen-repartidor/tests/navegador/probar-equivalencia.mjs /tmp/publicado.html /tmp/nuevo.html r-x7m2hd
node resumen-repartidor/tests/navegador/probar-bordes.mjs /tmp/publicado.html /tmp/nuevo.html
```

- `probar-equivalencia.mjs` abre las dos versiones y compara lo que se ve: cabecera, reparto de hoy, cada día
  con su barra, cada tarjeta (orden, clases, texto), Comisión, Mes, el modo completadas, el modal «Ver toda la
  info» y las escrituras que harían Entregado, Cobrado y reagendar. Si los datos cambian entre una pasada y la
  otra (alguien marcó algo), puede dar una diferencia falsa: correrlo de nuevo.
- `probar-bordes.mjs`: sin clave (cero pedidos), sin red con y sin caché, la caché de tarjetas se usa y se
  invalida por `updated_at`, el delta de la 2.ª visita, falla parcial del paso 2, el ancla del WhatsApp.
- Necesitan `playwright-core` (lo buscan en el proyecto, en DIXDY o en la caché de npx) y Chrome.

