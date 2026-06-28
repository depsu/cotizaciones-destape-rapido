# Arquitectura de la página del repartidor (para un chat nuevo)

> Si vas a **modificar la página web interactiva** (estados, comisión, tareas,
> animaciones, etc.), lee esto primero. Para solo **agregar una entrega**, usa
> `SKILL.md` (es otro flujo).

## Qué es

Una página **mobile-first estática** que usa el repartidor (y el jefe/Alejandro) desde el celular para:
- Ver las entregas del día, marcarlas **Entregado / Cobrado**, reagendar, avisar al cliente por WhatsApp.
- Ver **limpiezas y retiros** pendientes y marcarlos realizados.
- Llevar la **comisión** de Alejandro (20% del neto) y registrar pagos.

**URL pública:** https://depsu.github.io/cotizaciones-destape-rapido/resumen-repartidor/listado.html
**Repo público:** `github.com/depsu/cotizaciones-destape-rapido` (rama `main`, GitHub Pages).

## Archivos clave

| Archivo | Qué es |
|---|---|
| `resumen-repartidor/entregas.json` | **Fuente de datos** (curada a mano). Contenido de cada entrega + tareas + comprobantes. |
| `resumen-repartidor/scripts/generar_listado.py` | **Generador**: lee `entregas.json` y produce `listado.html`. Acá viven el HTML, **todo el CSS** y **todo el JavaScript** embebido. |
| `resumen-repartidor/listado.html` | Salida generada (autocontenida, sin dependencias). **No editar a mano**, se regenera. |
| `resumen-repartidor/supabase/entrega_estado.sql` | DDL de las tablas de estado en Supabase (idempotente). |
| `resumen-repartidor/comprobantes/` | Fotos de las transferencias de comisión (se suben a mano). |
| `index.html` (raíz) | Redirige a `resumen-repartidor/listado.html`. |

## Regenerar y publicar

```bash
python3 resumen-repartidor/scripts/generar_listado.py     # regenera listado.html
git add resumen-repartidor/ && git commit -m "..." && git push origin main
```
GitHub Pages lo publica solo en ~1 min. (También existe `publicar.sh` para el flujo de agregar entregas.)

## Arquitectura: estático + estado vivo en Supabase

- El **contenido** (cliente, dirección, monto, servicio…) se **hornea** en `listado.html` desde `entregas.json` al generar.
- El **estado mutable** que cambia el repartidor desde el celular (entregado/cobrado, fecha reagendada, contactado, comisión pagada, tareas realizadas) se guarda en **Supabase** y se lee/escribe con la **anon key** vía REST (`/rest/v1/...`). Así el repartidor y Alejandro ven lo mismo en vivo.
- Al cargar: el JS pinta primero con los datos horneados (META), luego hace `fetch` a Supabase y sobreescribe con el estado real. Hay un "velo" (`main` opacity) que evita el parpadeo.

### Supabase

- Proyecto **`abmzkzraptmjgebwjzys`** · URL `https://abmzkzraptmjgebwjzys.supabase.co` (es el mismo de `../destaperapido-app`, **free tier: se pausa por inactividad** → si fallan los fetch, reactivar).
- **anon key** (pública por diseño) está incrustada en `generar_listado.py` (`SUPABASE_ANON_KEY`) y en `destaperapido-app/frontend/.env.local`.
- Tablas (RLS con acceso anónimo solo a ellas):
  - **`entrega_estado`**: `id` (= id de la entrega), `estado`, `fecha` (override reagendado), `comision_pagada`, `pagada_at`, `contactado`, `reagendar_avisado`, `nota`, `updated_at`.
  - **`tarea_estado`**: `id` (= `"<entrega_id>::lim::<idx>"` o `"<entrega_id>::retiro"`), `contactado`, `realizada`, `realizada_at`, `updated_at`.

### Aplicar migraciones / correr SQL (sin CLI ni psql)

Vía **Management API** (token personal `SUPABASE_ACCESS_TOKEN` y `SUPABASE_PROJECT_REF` están en el env del shell y en `destaperapido-app/secret.txt`):

```python
# POST https://api.supabase.com/v1/projects/<ref>/database/query   body {"query": "..."}
# OJO: Cloudflare bloquea el User-Agent por defecto de Python (error 1010) -> mandar UA de navegador.
# Si el proyecto está pausado: POST /v1/projects/<ref>/restore y esperar status ACTIVE_HEALTHY.
```
(Hay ejemplos de este patrón en el historial; el SQL idempotente está en `supabase/entrega_estado.sql`.)

## Modelo de datos

### `entregas.json` (campos por entrega)

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
- Secciones **🧽 Limpiezas a realizar** y **📦 Retiros**: cada una es una tarea interactiva (Coordinar por WhatsApp → "Ya lo contacté" + accesos → botón "Realizada" con animación; toggle "Ver realizadas").
- Botón **"Ver completadas"**: muestra SOLO las cobradas y oculta el resto; encabezado y botón "Volver" flotan abajo y te siguen; des-marcar una hace que **salga por la izquierda** y cierre el hueco suave.

**Vista Comisión** (pestaña 💰):
- Total "Te deben", "Por cobrar", y **"Mis pagos recibidos" agrupados por pago** (Pago 1, Pago 2… por `pagada_at`) con botón **📷 Ver transferencia** (foto manual).
- Cada comisión: checkbox para seleccionar (se guarda la **deselección** en localStorage), **💬 Revisar en WhatsApp**, **📋 Ver toda la info** (modal con el detalle de la entrega + aviso si fue reagendada).
- Botón **Pagar** → modal con datos bancarios de Alejandro + adjuntar comprobante → marca pagadas (con `pagada_at`) y abre WhatsApp con el detalle. **El pago NO se da por exitoso si falla el guardado** (revierte y avisa).

## Cómo trabajar el código

- **Todo el CSS** está en `ESTILOS_EXTRA` (string normal, llaves simples) y en el `<style>` del f-string final (llaves **dobles** `{{ }}`). El **JS** está en `SCRIPT_ESTADO` (raw string `r"""..."""`, llaves literales). Datos para el JS van en `window.__APP__` (config blob).
- **Regla del `[hidden]`**: hay una regla global `[hidden]{display:none!important}` porque muchos contenedores usan `display:flex/block` que de otro modo le ganan al atributo `hidden`. Úsala en vez de pelear con cada elemento.
- **Probar sin tocar la base**: generar y abrir `listado.html` en Chrome headless, stubbeando `window.fetch` para inyectar estado falso y capturar errores. Patrón:
  ```bash
  # extraer scripts y validar sintaxis
  python3 -c "import re;html=open('resumen-repartidor/listado.html').read();[open(f'/tmp/s{i}.js','w').write(s) for i,s in enumerate(re.findall(r'<script>(.*?)</script>',html,re.S))]"
  node --check /tmp/s1.js
  # render con estado simulado: stub window.fetch (GET devuelve filas, POST ok/falla) + window.onerror
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --virtual-time-budget=3000 --dump-dom "file://$PWD/tmp.html"
  ```
- **No subir** archivos temporales/capturas al repo. Commits en español, estilo de los existentes.

## Reglas de negocio (memoria de Alejandro)

- Comisión = **20% del NETO**. Si lleva factura, neto = monto/1,19; si es boleta, neto = monto. Nunca sobre limpiezas/aseos extras (`comision:false`).
- El repartidor (dueño) **siempre cobra** al cliente; con factura el monto es neto+IVA.
- IVA por defecto (factura); boleta solo si el cliente lo pide.
- Datos bancarios de la comisión: **BancoEstado · Cuenta RUT 000019955346 · Alejandro Rivera Carrasco** (en `DATOS_BANCARIOS`). WhatsApp de aviso: **+56 9 3015 3632** (`WHATSAPP_COMISION`).
