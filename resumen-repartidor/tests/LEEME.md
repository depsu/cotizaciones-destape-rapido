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
