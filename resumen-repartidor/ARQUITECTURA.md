# Arquitectura de la página del repartidor (para un chat nuevo)

> Si vas a **modificar la página web interactiva** (estados, comisión, tareas,
> animaciones, etc.), lee esto primero. Para solo **agregar una entrega**, usa
> `SKILL.md` (es otro flujo).

## Qué es

Una página **mobile-first estática** que usa el repartidor (y el jefe/Alejandro) desde el celular para:
- Ver las entregas del día, marcarlas **Entregado / Cobrado**, reagendar, avisar al cliente por WhatsApp.
- Ver **limpiezas y retiros** pendientes y marcarlos realizados.
- Llevar la **comisión** de Alejandro (20% del neto) y registrar pagos.

**URL pública:** https://depsu.github.io/cotizaciones-destape-rapido/resumen-repartidor/listado.html?repartidor=p-9t4kqv
(desde el 7-nov **sin la clave `?repartidor=` no muestra nada**; `https://www.destaperapido.cl/entregas` redirige
con la clave puesta, y cada relevo tiene la suya: `destaperapido.cl/r/<id>`).
**Repo público:** `github.com/depsu/cotizaciones-destape-rapido` (rama `main`, GitHub Pages). **PÚBLICO**: nunca
`git add -A` acá (hay planillas e informes con datos de clientes sin rastrear; ver `.gitignore`).

## Archivos clave

| Archivo | Qué es |
|---|---|
| `resumen-repartidor/entregas.json` | **Input/registro** de las entregas (curado a mano). Se edita para dar de alta una entrega; el `--enviar` la sube a Supabase. La página **ya no lo lee ni lo hornea** (15-nov-2026); el generador solo saca de acá `comprobantes` y el geo de respaldo de las entregas viejas. |
| `resumen-repartidor/scripts/generar_listado.py` | **Generador** de `listado.html`. Acá viven el HTML, **todo el CSS** y **todo el JavaScript** embebido. Desde el 15-nov-2026 el HTML sale **sin tarjetas**: todas llegan de Supabase al abrir la página. La función `tarjeta(e)` renderiza cada tarjeta (es la que hornea el `card_html` de Supabase). |
| `resumen-repartidor/scripts/sync_entregas_supabase.py` | Sube/actualiza las entregas de `entregas.json` a la tabla **`entrega`** de Supabase (idempotente; `card_html` = `tarjeta(e)`; **preserva** el `informado_at` existente). Expone `upsert_entrega(e)` que usa el flujo del repartidor. |
| `resumen-repartidor/scripts/resumen_repartidor.py` | Arma el resumen + link/envío de WhatsApp al repartidor. Con `--enviar`/`--abrir` **también sube la entrega a Supabase** (aparece sola en la página, más reciente arriba). |
| `resumen-repartidor/listado.html` | Salida generada (autocontenida, sin dependencias). **No editar a mano**, se regenera. |
| `resumen-repartidor/supabase/entrega.sql` | DDL de la tabla **`entrega`** (CONTENIDO de las entregas + `card_html` + `informado_at`). Idempotente. |
| `resumen-repartidor/supabase/entrega_estado.sql` | DDL de las tablas de **ESTADO** (`entrega_estado`, `tarea_estado`). Idempotente. |
| `resumen-repartidor/comprobantes/` | Fotos de las transferencias de comisión (se suben a mano). |
| `index.html` (raíz) | Redirige a `resumen-repartidor/listado.html`. |

## Agregar una entrega / regenerar / publicar

- **Agregar una entrega (flujo normal):** editar `entregas.json` y correr `python3 resumen-repartidor/scripts/resumen_repartidor.py --id <id> --enviar`. Eso manda el WhatsApp al repartidor **y sube la entrega a Supabase** → **aparece sola en la página, sin regenerar ni publicar**.
- **Publicar cambios de CÓDIGO/diseño** de la página: `publicar.sh` regenera `listado.html` y hace commit + push
  **solo de los archivos de la página** (GitHub Pages publica en ~1 min). Desde el 15-nov-2026 **no** re-sincroniza
  `entregas.json` sobre Supabase (pisaba con datos de agosto lo que el bot corrigió después) salvo que se pida con
  `--sincronizar`, y **no** hace `git add -A` (el repo es público).

```bash
python3 resumen-repartidor/scripts/generar_listado.py            # solo regenera listado.html
bash resumen-repartidor/publicar.sh "mensaje del commit"         # regenera + commit/push de la página
```

## Arquitectura: página dinámica desde Supabase (sin respaldo horneado desde el 15-nov-2026)

- El **contenido** de cada entrega (cliente, dirección, monto, servicio…) vive en la tabla **`entrega`** de Supabase, con la tarjeta **ya renderizada** en `card_html` (la genera la misma función Python `tarjeta()`; **NO** se porta el template a JS) y un `informado_at` para el orden.
- **Carga en dos pasos (15-nov-2026, ver abajo).** Antes se bajaba el `card_html` de TODAS (~570 KB comprimidos) y se metían todas al DOM.
- El **estado mutable** que cambia el repartidor desde el celular (entregado/cobrado, fecha reagendada, contactado, comisión pagada, tareas realizadas) vive en **`entrega_estado`**/**`tarea_estado`** y se lee/escribe con la **anon key** vía REST (`/rest/v1/...`). El JS lo aplica encima de las tarjetas. Así el repartidor y Alejandro ven lo mismo en vivo.
- **Orden (2026-07-17):** agrupado por día; los días en **orden CRONOLÓGICO** (atrasado → hoy → futuro, el orden en que se trabaja), y dentro de cada día lo **más recientemente informado primero** (`informado_at` desc). Una entrega nueva (informado = `now()`) queda arriba de su día.
- **Geo en VIVO (2026-07-17):** `aplicarEntregas` recomputa también `GEO` desde el `data` de cada fila (`geoDeData`, puerto JS de `derivar_geo`+`maps_query`; tabla `comunas_geo` en `window.__APP__`). Antes una entrega informada después de hornear caía a "Sin comuna" en el Reparto de hoy. El `APP.geo` horneado queda de respaldo.
- **"✨ Nuevo" (2026-07-17):** las entregas que ESTE dispositivo no había visto se destacan (borde/sombra azul + chip), con memoria en `localStorage` (`entregas_vistas_v1`) — por persona, no choca entre quienes miran el panel. Primera visita solo siembra la memoria, sin marcar.
- **Carga sin parpadeo (2026-09-02, el respaldo horneado se quitó el 15-nov-2026):** el respaldo horneado podía estar VIEJO (entregas.json se
  edita a mano y las entregas nuevas entran por el bot), así que la página ya NO lo revela a los
  1.5 s: muestra un **esqueleto** (`#skel` + cabecera con placeholders) hasta que llegan los datos
  vivos, y recién ahí pinta el contador de pendientes, el «ganado» y la hora real de
  actualización (`#hdr-act`). Si Supabase no responde, usa el **caché de la última visita**
  (`localStorage`: `entregas_lite_v2`, `tarjetas_v2`, `estado_cache_v1`, `publicidad_cache_v1`; desde el
  15-nov-2026 ya no hay respaldo horneado, ver «Carga en dos pasos») con aviso «lo último guardado».
  Fallback CSS a los 10 s por si el JS muere. Probar los caminos con
  `page.route(/supabase\.co/, r => r.abort())` en Playwright (`tests/navegador/probar-bordes.mjs` ya lo hace).
- **Consistencia:** las entregas nuevas entran por `resumen_repartidor.py --enviar` o el bot (upsert con `informado_at = now()`). `publicar.sh --sincronizar` re-sube `entregas.json` (preservando `informado_at`): casi nunca hace falta y pisa lo que el bot corrigió.

### Carga en dos pasos y fluidez (15-nov-2026)

Medido en un celular de gama media simulado (CPU 4x, 4G lenta): la carga pasó de 4,6 s a 2,1 s (1.ª visita) y de
4,5 s a 1,1 s (las siguientes); de 747 KB a ~190 KB; de 18.681 a 1.450 nodos; el toque «Entregado» de 388 a 134 ms y
«Cobrado» de 200 a 38 ms. Con datos reales, una prueba lado a lado (`tests/navegador/probar-equivalencia.mjs`) muestra
EXACTAMENTE lo mismo que la versión anterior (cabecera, reparto, días con su barra, cada tarjeta con sus clases y texto,
Comisión, Mes, completadas, modal, y las mismas escrituras), y las capturas salen idénticas píxel a píxel.

- **Las lecturas salen desde el `<head>`** (`<script id="pre-carga">`, `window.__PRE__`), apenas llega el HTML, y van
  **sin cabeceras propias** (`?apikey=` en la URL): el navegador no hace la consulta previa de CORS (OPTIONS). Las
  escrituras (POST/PATCH) siguen con cabeceras. Las consultas viven en `CONSULTAS` (Python) y llegan al JS en `APP.q`.
- **Paso 1:** `entrega_estado` + `entrega` **sin `card_html`** (`select=id,fecha,informado_at,updated_at,data`, ~60 KB)
  + `cobro_publicidad` + el **delta**: las tarjetas que cambiaron desde la última visita de ese teléfono
  (`updated_at=gt.<marca>`, la marca vive en `localStorage['tarjetas_v2_desde:<clave>']`). Con eso salen META, GEO,
  la cabecera, Comisión, Mes y el reparto de hoy.
- **Paso 2:** el `card_html` **solo de las tarjetas de la lista** (pendientes: no eliminadas y no `cobrado`) que el
  teléfono no tenga al día (caché `tarjetas_v2[:relevo]`, validada por `updated_at`; el trigger `entrega_touch` lo cambia
  en cada cambio de la fila), de a 40 por consulta (`id=in.(...)`). Lo normal en una 2.ª visita: cero tarjetas por pedir.
- **Completadas:** sus tarjetas se traen al tocar «Ver completadas», en tandas (primero las 24 más recientes, el resto
  detrás) y **salen del DOM al volver** (quedan en memoria). Las 24 más recientes se guardan en el teléfono para que
  la próxima vez el botón abra al tiro. «Ver toda la info» de una completada que no está en la página arma la tarjeta
  aparte (`tarjetaSuelta`) o la pide.
- **Lo que antes se contaba en el DOM ahora sale de META**: la barra de progreso de cada día (`actualizarProgreso`) y el
  «Ver completadas (N)» (`contarCompletadas`), porque las cobradas ya no están todas puestas.
- **Por toque:** la pestaña Comisión (todas las comisiones, ~165 tarjetas) se arma solo si está a la vista; si no, queda
  `comisionSucia` y se arma al abrirla. La vista Mes igual. `reubicarCards` solo mueve nodos si el orden cambió. El
  FLIP lee todo y después escribe. El alto del header lo mantiene un `ResizeObserver`. Los botones de Comisión van por
  delegación. El logo de WhatsApp de Comisión es un `<symbol>` único (`#ico-wa-sym`).
- **`#precalentar`:** una tarjeta «Falta cobrar» de muestra, invisible e inerte, que el navegador arma mientras se ve
  el esqueleto (el primer «Entregado» del día gastaba ~5 veces más en armar letras y estilos). Se quita a los 2,5 s.
- **Sin respaldo horneado:** sin red usa `entregas_lite_v2` + `tarjetas_v2` (o la v1 de la versión anterior, que se
  borra tras la primera carga viva). Sin nada: lista vacía y «Sin conexión con la base. Cuando vuelva la señal,
  recarga.» (antes mostraba 33 entregas de junio-agosto como pendientes). Las lecturas se cortan a los 30 s.
- El caché del teléfono bajó de ~1.750 K a ~400 K caracteres (el límite del navegador es ~5 MB por sitio y lo comparte
  con la página de destapes, que vive en el mismo dominio).

### Publicidad: la parte que paga el repartidor (2026-09-02)

Alejandro paga los avisos (Google Ads / Meta) y al repartidor le toca una parte (hoy la mitad).
Cada rendición la arma `scripts/rendir-publicidad.py` del maestro DIXDY (carpeta con
`resumen.json` + `cobro.png`); **`scripts/publicar_cobro_publicidad.py --rendicion <carpeta>
--fraccion 0.5`** copia la imagen a `publicidad/<id>.png` (+ `.mini.png`) y sube la fila a la
tabla **`cobro_publicidad`** (DDL en `supabase/cobro_publicidad.sql`). Luego `publicar.sh` (o un
commit + push) para que GitHub Pages sirva la imagen. `--listar` muestra lo publicado.

En la página: **cabecera** → a la derecha, miniatura del desglose + monto pendiente (o «Al día ✓»);
tocarla abre el modal 📣 Publicidad con cada rendición (total gastado, entraron/contactaron/costo
por contacto, «Tu parte», la imagen completa y «Pagar mi parte»). **Vista 💰 Comisión** → sección
«📣 Publicidad · pendiente por pagar» con checkbox, sumada a «Te deben»; se paga con el MISMO flujo
que las comisiones (en la selección viaja como `pub:<id>`; `montoSel`/`labelSel` resuelven monto y
etiqueta; `upsertPub` hace PATCH a la tabla) y la publicidad pagada entra al «Pago N» de su
`pagada_at`, con «Revocar».

### Supabase

- Proyecto **`abmzkzraptmjgebwjzys`** · URL `https://abmzkzraptmjgebwjzys.supabase.co` (es el mismo de `../destaperapido-app`, **free tier: se pausa por inactividad** → si fallan los fetch, reactivar).
- **anon key** (pública por diseño) está incrustada en `generar_listado.py` (`SUPABASE_ANON_KEY`) y en `destaperapido-app/frontend/.env.local`.
- Tablas (RLS con acceso anónimo solo a ellas):
  - **`entrega`** (CONTENIDO — es lo que la página LEE para mostrar): `id` (= id de la entrega), `fecha`, `informado_at` (timestamptz, orden "más reciente arriba"), `data` (jsonb = objeto completo de la entrega, misma forma que en `entregas.json`), `card_html` (tarjeta ya renderizada por `tarjeta()`), `eliminado`, `updated_at`. DDL: `supabase/entrega.sql`.
  - **`entrega_estado`** (ESTADO mutable): `id` (= id de la entrega), `estado`, `fecha` (override reagendado), `comision_pagada`, `pagada_at`, `contactado`, `reagendar_avisado`, `eliminado` (oculta la entrega y la saca de conteos/comisión), `nota`, `updated_at`.
  - **`tarea_estado`**: `id` (= `"<entrega_id>::lim::<idx>"` o `"<entrega_id>::retiro"`), `contactado`, `realizada`, `realizada_at`, `updated_at`.
  - **`cobro_publicidad`**: `id` (carpeta de la rendición), `campana`, `plataforma`, `desde`, `hasta`, `gasto_total`, `fraccion`, `monto` (lo que le toca), `imagen`, `miniatura`, `detalle` (jsonb), `nota`, `pagado`, `pagada_at`, `eliminado`. DDL: `supabase/cobro_publicidad.sql`.

### Aplicar migraciones / correr SQL (sin CLI ni psql)

Vía **Management API** (token personal `SUPABASE_ACCESS_TOKEN` y `SUPABASE_PROJECT_REF` están en el env del shell y en `destaperapido-app/secret.txt`):

```python
# POST https://api.supabase.com/v1/projects/<ref>/database/query   body {"query": "..."}
# OJO: Cloudflare bloquea el User-Agent por defecto de Python (error 1010) -> mandar UA de navegador.
# Si el proyecto está pausado: POST /v1/projects/<ref>/restore y esperar status ACTIVE_HEALTHY.
```
(Hay ejemplos de este patrón en el historial; el SQL idempotente está en `supabase/entrega.sql` y `supabase/entrega_estado.sql`.)

## Postventa: destaperapido.cl/postventa (21-nov-2026)

Pedido de Alejandro y del repartidor (que ya tiene choferes haciendo limpiezas y necesita control). Hasta el
21-nov `postventa.html` era una **demo fija del 15-oct** (botón «Listo» que no guardaba nada) y el bot igual mandaba
ese link cada mañana. Ahora es una página viva, aparte de la de entregas:

- **Qué muestra:** cada baño ENTREGADO que sigue en terreno, con dirección completa, «Cómo llegar» (el pin del cliente
  si lo hay), llamar y WhatsApp, el plazo (desde, hasta, mes N, extendido N veces) y la limpieza (cuándo toca, la
  última y quién la hizo). Secciones: **Terminó el plazo** (¿renovó o se retira?), **Retiros**, **Toca limpieza** y
  **Al día**. Filtros Todos / Limpiezas / Retiros / Por renovar, buscador (incluye terminados y retirados) y pestaña
  **Mapa** (Leaflet + OpenStreetMap, sin llave ni costo) con todos los baños en color según urgencia.
- **Qué se anota** (tabla `postventa_evento`, `supabase/postventa.sql`; nunca se borra, un error se **anula** y queda
  tachado en el historial): **Limpieza hecha** (fecha, nota y foto al bucket `postventa-fotos`, achicada a 1280 px en
  el teléfono), **Extender** (1 mes, 2 semanas, 1 semana u otra fecha; si el plazo terminó hace rato suma desde el
  fin hasta pasar hoy), **Retirado**, **Ubicación exacta** (link o dirección que manda en «Cómo llegar») y **Nota**.
  Cada anotación lleva **quién** (el nombre se pide una vez por teléfono).
- **Las reglas** (fin del plazo, aseo cada 7 a 10 días, cantidad, comuna) viven en `postventa-logica.js` y son el
  puerto exacto de `generar_listado.py` + `agenda-del-equipo.py`: `node resumen-repartidor/tests/probar-postventa-logica.cjs`
  las compara con Python sobre TODAS las entregas reales. Si cambias una regla en Python, corre ese test.
- **El bot lo sabe:** `conexiones/agenda-del-equipo.py` (clon destaperapido, corre en dixdy-1) lee `postventa_evento`:
  la extensión mueve el `fin`, la limpieza entra en `hechos`/`hechos_at` (cierra tareas y reclamos de aseo) y el retiro
  pone `retiro_hecho` y saca el servicio a los 3 días. Prueba: `python3 conexiones/_probar-agenda-postventa.py`.
- **Mapa:** el punto sale de las coordenadas o link de la ficha, de la caché `postventa_geo` o, si falta, la página lo
  busca en OpenStreetMap (de a uno por segundo) y lo guarda. Los links cortos de Google (maps.app.goo.gl) no se abren
  desde el navegador: `node resumen-repartidor/scripts/geo-postventa.mjs` los resuelve y ubica de una vez lo que falte
  (`--reintentar` vuelve a buscar los que quedaron en el centro de su comuna). Punto con borde punteado = aproximado.
- **Clave:** igual que la de entregas (`?repartidor=p-9t4kqv`); `destaperapido.cl/postventa` la pone sola (vercel.json
  del clon). Sin clave no pide nada a la base.
- **Probar en navegador:** `node resumen-repartidor/tests/navegador/probar-postventa.mjs [carpeta-capturas]` (datos
  reales, toda escritura y OpenStreetMap interceptados).

## Modelo de datos

### Campos por entrega (en `entregas.json` y en la columna `data` de la tabla `entrega`)

Mismos campos en ambos lados (el `data` de Supabase es una copia del objeto de `entregas.json`):
`id, cliente, telefono, direccion, fecha (AAAA-MM-DD), hora, servicio, cantidad, pago{monto, nota}, factura{...}, detalle[], notas, estado`.

Opcionales importantes:
- **`comision: false`** → la entrega NO genera comisión (es un servicio extra: limpieza/mantención/recambio). En el resumen se etiqueta `🧽 Limpieza extra` / `📦 Retiro` / `♻️ Recambio` (según el texto del servicio) y los botones dicen "Realizado" en vez de "Entregado".
- **`comision_pagada: true`** + **`pagada_at: "AAAA-MM-DD"`** → comisión ya pagada (histórico). El `pagada_at` agrupa las comisiones en "Pago 1, Pago 2…".
- **`limpiezas[]`**: `{fecha, etiqueta, tipo (incluida|extra), valor, estado (pendiente|hecha), nota}` → arman la sección **Limpiezas**.
- **`retiro: {fecha, nota}`** → arma la sección **Retiros**.
- Top-level **`comprobantes`**: `{ "<pagada_at>": "comprobantes/foto.png" }` → foto de cada pago (ver `comprobantes/README.md`).

### Estado de la entrega: 2 dimensiones independientes

`estado` combina **entregado** y **cobrado** (independientes):

| estado | entregado | cobrado | color | significado |
|---|---|---|---|---|
| `pendiente` | no | no | blanco | aún no entregado |
| `entregado` | sí | no | azul | entregado, falta cobrar |
| `pagado-pendiente` | no | sí | ámbar | pagó adelantado, falta entregar |
| `cobrado` | sí | sí | dorado | completado (entregado + cobrado) |

Helpers en JS: `entregadoDe(id)`, `cobradoDe(id)`, `estadoDe(id)`. La comisión cuenta cuando `cobradoDe` (pagó), el progreso 🚚 cuenta cuando `entregadoDe`.

### Sub-estados visuales (cards pendientes)

- **Reagendada (rojo)**: la fecha efectiva ≠ original (se movió).
- **Cliente contactado (verde)**: `contactado` y al día.
- **Pendiente reagendar (gris)**: `contactado` + **vencida** (fecha < hoy) sin entregar. El botón pasa a "💬 Pendiente reagendar" (WhatsApp), brilla el reagendar, accesos quedan con Llamar+Llegar. Tras avisar (`reagendar_avisado`) el botón dice "📅 Falta actualizar la fecha" y sigue brillando hasta mover la fecha.

## Inventario de features (lo que ya existe en la página)

**Header:** título, "X pendiente(s)" (en vivo), **"💰 Ganado: $llevan / $total si se cobra todo"** (monto bruto cobrado, no la comisión).

**Vista Entregas** (pestaña 🚚):
- Cards por día (encabezado **sticky**, **colapsable** al pincharlo, con **barra de progreso 🚚** = baños entregados/total del día).
- Gestión arriba de la card: **Reagendar** (date input; al mover, reposiciona con animación FLIP) + **Entregado** / **Cobrado** (toggle, con **confirmación en la card** al des-marcar). En entregas futuras solo se ve el reagendar.
- Botón **"Avisar al cliente"** (WhatsApp con mensaje "voy a entregar hoy/mañana/el X") → se marca contactado (1 vez) → aparecen accesos **💬 WhatsApp · 📞 Llamar · 🗺️ Llegar** + **"Ver toda la info"**.
- Texto sutil que explica el color de cada card.
- **Animación de éxito** al completar (card dorada "✅ Baño entregado / Limpieza realizada con éxito", se desvanece y colapsa suave).
- Secciones **🧽 Limpiezas a realizar** y **📦 Retiros**: cada una es una tarea interactiva (Coordinar por WhatsApp → "Ya lo contacté" + accesos → botón "Realizada" **violeta** con **confirmación** y animación). **Solo aparecen las tareas de entregas ya ENTREGADAS** (filtro por `entregadoDe`, salta las eliminadas). Por defecto muestran hasta **hoy+5 días** (más los vencidos pendientes); dos toggles bajo el título: **"📅 Ver todas — próximas (N)"** (futuras) y **"✓ Ver realizadas (N)"**.
- Cada card de entrega tiene, al final del detalle, un botón **"✕ Eliminar"** (rojo, con confirmación en la card) que marca `eliminado` en Supabase y la saca de la vista, conteos, progreso y comisión.
- Botón **"Ver completadas"**: muestra SOLO las cobradas y oculta el resto; encabezado y botón "Volver" flotan abajo y te siguen; des-marcar una hace que **salga por la izquierda** y cierre el hueco suave.

**Vista Comisión** (pestaña 💰):
- Total "Te deben", "Por cobrar", y **"Mis pagos recibidos" agrupados por pago** (Pago 1, Pago 2… por `pagada_at`) con botón **📷 Ver transferencia** (foto manual).
- Cada comisión: checkbox para seleccionar (se guarda la **deselección** en localStorage), **💬 Revisar en WhatsApp**, **📋 Ver toda la info** (modal con el detalle de la entrega + aviso si fue reagendada).
- Botón **Pagar** → modal con datos bancarios de Alejandro + adjuntar comprobante → marca pagadas (con `pagada_at`) y abre WhatsApp con el detalle. **El pago NO se da por exitoso si falla el guardado** (revierte y avisa).

## Cómo trabajar el código

- **Todo el CSS** está en `ESTILOS_EXTRA` (string normal, llaves simples) y en el `<style>` del f-string final (llaves **dobles** `{{ }}`). El **JS** está en `SCRIPT_ESTADO` (raw string `r"""..."""`, llaves literales). Datos para el JS van en `window.__APP__` (config blob).
- **Regla del `[hidden]`**: hay una regla global `[hidden]{display:none!important}` porque muchos contenedores usan `display:flex/block` que de otro modo le ganan al atributo `hidden`. Úsala en vez de pelear con cada elemento.
- **Antes de publicar un cambio de carga o de pintado** (15-nov-2026): `node resumen-repartidor/tests/navegador/probar-equivalencia.mjs <listado-publicado.html> <listado-nuevo.html> [p-9t4kqv|r-...]`
  compara lado a lado, con los datos reales (solo lecturas; toda escritura se intercepta), todo lo que se ve y lo que se
  escribiría; `probar-bordes.mjs` cubre sin clave, sin red, cachés y el ancla. Ver `tests/LEEME.md`.
- **Probar sin tocar la base**: generar y abrir `listado.html` en Chrome headless y capturar errores. Al cargar, la página hace `fetch` a `entrega_estado`, `entrega` (sin `card_html`), `cobro_publicidad` y, en el paso 2, al `card_html` de las tarjetas que faltan. Dos formas de probar:
  - **Con Supabase real** (recomendado, es lo que valida CORS + datos): servir por `http` (origen válido) y renderizar — `python3 -m http.server 8791` en `resumen-repartidor/` y abrir `http://localhost:8791/listado.html`. La tabla `entrega` tiene RLS anónima, así que trae los datos reales.
  - **Stub de `window.fetch`** para inyectar filas falsas de `entrega` y/o `entrega_estado` (probar orden, fallback si `entrega` da 503, estado, etc.), capturando `window.onerror`/`console.error`.
  ```bash
  # extraer scripts y validar sintaxis
  python3 -c "import re;html=open('resumen-repartidor/listado.html').read();[open(f'/tmp/s{i}.js','w').write(s) for i,s in enumerate(re.findall(r'<script>(.*?)</script>',html,re.S))]"
  node --check /tmp/s1.js
  # render (con Supabase real, servido por http para tener origen válido)
  (cd resumen-repartidor && python3 -m http.server 8791 &) ; sleep 1
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
    --virtual-time-budget=9000 --dump-dom "http://localhost:8791/listado.html"
  ```
  **OJO al verificar el orden por DOM:** las tarjetas se agrupan por su **día efectivo** (reagendado en `entrega_estado`), que puede diferir del `data-fecha`/id original → parsear las cards **anidadas dentro de cada `<section data-fecha>`**, no el atributo suelto de la card.
- **No subir** archivos temporales/capturas al repo. Commits en español, estilo de los existentes.

## Reglas de negocio (memoria de Alejandro)

- Comisión = **20% del NETO**. Si lleva factura, neto = monto/1,19; si es boleta, neto = monto. Nunca sobre limpiezas/aseos extras (`comision:false`).
- El repartidor (dueño) **siempre cobra** al cliente; con factura el monto es neto+IVA.
- IVA por defecto (factura); boleta solo si el cliente lo pide.
- Datos bancarios de la comisión: **BancoEstado · Cuenta RUT 000019955346 · Alejandro Rivera Carrasco** (en `DATOS_BANCARIOS`). WhatsApp de aviso: **+56 9 3015 3632** (`WHATSAPP_COMISION`).
