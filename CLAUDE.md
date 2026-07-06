# cotizaciones-destape-rapido

Genera y envía **cotizaciones** de Destape Rápido (PDF + correo), gestiona las **entregas del
repartidor** (WhatsApp + página web) y el panel de correo. Todo el detalle fino vive en los
`SKILL.md`; este archivo es el mapa del flujo de punta a punta para no perderse.

> 🧭 **Doctrina DIXDY (obligatoria):** este es un clon DIXDY. NO agregues APIs de Anthropic,
> loops, crons ni workers nuevos sin revisar los motores que YA existen
> (`/Users/alejandroriveracarrasco/SaSS/DIXDY/docs/23-doctrina-dixdy.md`). OK de Alejandro SOLO
> por plata o gestión externa. Registra lo que hagas con
> `python3 /Users/alejandroriveracarrasco/SaSS/DIXDY/scripts/actividad.py`.

## Los dos skills (no mezclar)

| Skill | Cuándo | Destino |
|---|---|---|
| `cotizaciones-destape-rapido` (raíz) | El cliente pide una **cotización a su correo** | **Correo al CLIENTE** (Resend) |
| `resumen-repartidor/` | El trato **está cerrado** y hay que entregar | **WhatsApp al REPARTIDOR** + página web |

**Regla de ruteo (crítica):** un chat de WhatsApp con el cliente pidiendo cotización a su correo
→ va por **correo al cliente**. "Pásasela al repartidor" / trato cerrado → **WhatsApp al
repartidor**. Ante duda de si el destino es cliente-correo o repartidor-WhatsApp, **preguntar
antes de enviar** (enviar es difícil de revertir).

## Flujo completo de un trato (los 3 pasos que suele pedir Alejandro)

Cuando Alejandro dice **"enviar cotización al correo, el whatsapp y subir la página"** (trato
cerrado), se hace todo de corrido, en este orden:

### 1. Cotización → correo del cliente
```bash
# a) Escribir el JSON en cotizaciones/ (schema en SKILL.md). Nombre OBLIGATORIO:
#    cotizaciones/cotizacion-AAAAMMDD-<cliente-kebab>.json
# b) Generar el PDF (mismo nombre, .pdf):
python3 scripts/generar_cotizacion.py \
  cotizaciones/cotizacion-AAAAMMDD-<cliente>.json \
  cotizaciones/cotizacion-AAAAMMDD-<cliente>.pdf
# c) Enviarlo al cliente (Resend por defecto; queda en el panel "Enviados"):
python3 scripts/enviar_cotizacion.py \
  cotizaciones/cotizacion-AAAAMMDD-<cliente>.pdf <email-cliente> \
  --cliente "Nombre Cliente" \
  --asunto "Cotización Destape Rápido — Arriendo de baño químico" \
  --mensaje "<cuerpo en texto plano, ~12 líneas, cifra mensual protagonista>"
```

### 2. WhatsApp → repartidor (SOLO si el trato está cerrado)
```bash
# a) Agregar la entrega a resumen-repartidor/entregas.json
#    (id = AAAA-MM-DD-<cliente-kebab>; pago.monto OBLIGATORIO; factura solo si la requiere)
# b) Verificar los datos y enviar (automático: abre WhatsApp y manda solo):
python3 resumen-repartidor/scripts/resumen_repartidor.py --id <id> --enviar
```
`--enviar` manda de una (sin confirmación manual) → **revisar los datos antes**. Usar `--abrir`
si se quiere revisar en WhatsApp antes de mandar. **Además de mandar el WhatsApp, el `--enviar`
sube la entrega a Supabase → aparece sola en la página del repartidor.**

### 3. La página del repartidor se actualiza SOLA
El paso 2 (`--enviar`) ya subió la entrega a Supabase, así que **aparece sola** en
https://depsu.github.io/cotizaciones-destape-rapido/ — **NO hace falta `publicar.sh`** para agregar
una entrega. `publicar.sh` solo se usa si cambia el CÓDIGO/diseño de la página o para refrescar el
respaldo horneado. Detalle en `resumen-repartidor/ARQUITECTURA.md`.

### 4. Dejar registro
- Actualizar la ficha del cliente en `clientes/historial.md` (precio, condiciones, estado).
- Registrar la actividad con `actividad.py` (doctrina DIXDY).

## Reglas de negocio que no se preguntan

- **Emisor SIEMPRE Destape Rápido** (tel. **+56 9 3647 0112**, destaperapido.cl), aunque el chat
  venga bajo la marca "Limpia Fosas y Destape" / Full Fosas (son empresas distintas).
- **Con factura** → el valor es **neto + IVA 19%** (usar bloque `factura` en la entrega; el
  repartidor cobra el total con IVA). **Sin factura / boleta** → **sin IVA, el valor es el
  total**; en el JSON de la cotización usar `"solo_neto": true`.
- **Cifra protagonista = mensual** en arriendos (nunca el acumulado del contrato como principal).
- **Cotizar ≠ entregar:** haber mandado un PDF NO crea una entrega. La entrega (paso 2) se agenda
  **solo cuando el trato está confirmado**. Si el cliente se cae después de agendar, quitar la
  entrega de `entregas.json` y **avisar al repartidor que no vaya**.
- **Evento corto (< 1 semana):** agregar a las condiciones "Cada limpieza extra durante el evento
  tiene un costo de $20.000".

## Config y transporte

- **Correo:** Resend por defecto (`config/resend.local.json`), SMTP del hosting de respaldo
  (`config/smtp.local.json`). `enviar_cotizacion.py` registra el envío en el panel ("Enviados").
- **Página repartidor:** GitHub Pages. Lee las entregas **en vivo desde Supabase** (tabla `entrega`);
  las horneadas quedan de respaldo. Agregar una entrega = `--enviar` (sube sola); `publicar.sh`
  (regenera + re-sincroniza Supabase + push) solo para cambios de código/diseño. Ver
  `resumen-repartidor/ARQUITECTURA.md`.
- **Estados/comisión de entregas:** los cambia el repartidor desde la página (Supabase, tablas
  `entrega_estado`/`tarea_estado`), no a mano.
