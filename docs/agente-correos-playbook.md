# Playbook: Agente de Cotizaciones por correo (PWA + IA + aprendizaje)

> Guía completa para **entender** el sistema que armamos para `destaperapido.cl` y para
> **replicarlo** en un proyecto nuevo o existente (esté el dominio en **Vercel** o en **Cloudflare**).
> No contiene secretos (van en `config/*.local.json` gitignored o como secretos del Worker).

---

## 1. Qué es y para qué sirve

Un **agente de correo** para un negocio: recibe correos de clientes, los muestra en un **panel propio
(instalable como app en el iPhone)**, **redacta respuestas con IA** (con PDF de cotización adjunto),
y **solo te notifica cuando duda**. Tú validas o le dejas **ajustes en lenguaje natural**; aprende con
cada corrección. Todo **gratis/casi gratis** y **sin baneos** (no usa hosting compartido).

**Objetivo de diseño:** que la IA responda sola y el dueño intervenga **solo en lo no estándar**,
delegando cada vez más.

---

## 2. Arquitectura

```
   Cliente ──► contacto@tudominio.cl
                    │ (Cloudflare Email Routing → acción "worker")
                    ▼
            ☁️ EMAIL WORKER (Cloudflare)
              ├─ parsea (postal-mime) y guarda en D1
              ├─ reenvía a tu Gmail (respaldo humano)
              ├─ sirve el PANEL (PWA: HTML+JS, manifest, service worker, íconos)
              ├─ API /api/* (auth por PANEL_PASS): correos, borrador, enviar, adjuntar,
              │   ajuste, push-subscribe, test-push, vapid
              └─ CRON (cada 20 min): manda PUSH (aes128gcm) solo si hay algo que revisar
                    │
        ┌───────────┴───────────────┐
        ▼                           ▼
   🗄️ D1 (SQLite)              🖥️ PANEL / PWA (panel.tudominio.cl)
   tabla `correos`             - se instala en el iPhone (push nativo)
   tabla `push_subs`           - auto-refresca cada 15s
                               - "Ajuste IA" en lenguaje natural

   🧠 CEREBRO = Claude Code (tu suscripción, NO API externa de IA)
      ├─ LOCAL: /loop 3m /revisa-correos  (tu PC, motor principal)
      └─ NUBE:  routine (respaldo cuando el PC está apagado)
      Lee correos de D1 → redacta + PDF → confianza alta/baja → deja borrador
      Procesa cola de "Ajuste IA" (y envía si dijiste "envíalo") → aprende

   📤 ENVÍO = Resend (envía como contacto@tudominio.cl, con PDF adjunto, sin baneos)
```

---

## 3. Decisiones clave (y el porqué)

| Decisión | Por qué |
|---|---|
| **Recibir = Cloudflare Email Routing** (gratis) | El hosting compartido gratis banea la IP y no tiene API. Cloudflare reenvía gratis, ilimitado, con API/MCP. |
| **Enviar = Resend** (gratis 3.000/mes, 1 dominio) | DKIM/SPF correctos → no cae en spam ni banea. A escala: Amazon SES. |
| **Cerebro = Claude Code, NO API externa** | El dueño no quería pagar API por mensaje. Claude Code (suscripción) es el que redacta, en loop. |
| **Panel propio = Worker sirve HTML/JS vanilla** (no Next.js) | Stack probado del usuario; un solo deploy; PWA instalable. |
| **Almacén = D1** (no Supabase) | Nativo al Worker, no se pausa (Supabase free se pausa), robusto para captura 24/7. |
| **Aprobación humana por defecto** | Las cotizaciones tienen precios sensibles ("modo análisis antes de enviar"). La IA deja borradores; el dueño aprueba. |
| **Notificación selectiva por confianza** | Que la IA moleste solo cuando duda; lo estándar queda listo en silencio. |
| **Ajuste en lenguaje natural + cola** | El dueño escribe "cóbrale 200mil por baño" → la IA ajusta; "...envíalo" salta la validación. |
| **PWA + Web Push aes128gcm** | iOS solo soporta push para PWA agregada a inicio, con cifrado `aes128gcm` (RFC 8291). |
| **Repo privado para la routine** | El repo del sitio era público → la PII/banco no debe ir ahí; la routine clona un repo PRIVADO. |

---

## 4. Componentes y archivos

**Worker (`correo-worker/`):**
- `wrangler.toml` — D1 binding, cron `*/20 * * * *`, vars (`FORWARD_TO`, `VAPID_PUBLIC`), reglas Text(.html)/Data(.png).
- `src/index.js` — `email()` (captura+reenvío), `scheduled()` (push), `fetch()` (panel + API).
- `src/webpush.js` — cifrado **aes128gcm** + VAPID hechos a mano (Web Crypto). Las librerías comunes usan `aesgcm` viejo que iOS rechaza.
- `panel.html` — PWA (manifest, sw, push, auto-refresh, "Ajuste IA").
- `schema*.sql` — migraciones D1.

**Scripts / loop (`scripts/`, `.claude/commands/`):**
- `agente_correos.py` — helper que habla con el panel (nuevos, correo, borrador, adjuntar, ajustes, respondidos). Lee `config/agente.local.json` **o** env `WORKER_URL`/`PANEL_PASS` (cloud-ready). **OJO:** manda User-Agent de navegador (Cloudflare bloquea UAs no-navegador con error 1010).
- `generar_cotizacion.py` — JSON → PDF (reportlab).
- `.claude/commands/revisa-correos.md` — el "cerebro" del loop (procesa ajustes, redacta con confianza, aprende).

**Conocimiento (`clientes/`):**
- `historial.md` — memoria por cliente (PII → gitignored).
- `reglas-aprendidas.md` — correcciones del dueño → reglas a futuro (gitignored).
- `.aprendidos.txt` — ids ya aprendidos.

**Config (`config/*.local.json`, gitignored):** `cloudflare`, `resend`, `vercel`, `agente`, `vapid`.

**D1 `correos`:** `id, de, para, asunto, cuerpo_texto/html, dominio, estado(nuevo|borrador|ajuste|respondido),
recibido_en, respuesta_borrador, respuesta_enviada, adjunto_nombre/b64, ajuste_pedido, ajuste_enviar,
confianza(alta|baja), motivo_revision, notificado`. Tabla `push_subs(endpoint,p256dh,auth)`.

---

## 5. Flujo del día a día

1. Llega un correo a `contacto@` → Worker lo guarda en D1 y lo reenvía a tu Gmail.
2. **Tu PC con `/loop 3m /revisa-correos`** (o la routine si el PC está off) lo redacta + PDF, marca confianza.
3. Si la IA **duda (baja)** → el cron te manda **push al iPhone** ("X cotizaciones por revisar").
4. Abres la PWA → panel auto-actualizado → revisas el borrador (badge ⚠️ Revisar + motivo).
5. **Apruebas** ("Aprobar y enviar" → Resend manda con PDF) **o** dejas **"Ajuste IA"**
   ("cóbrale 200mil por baño"; agrega "envíalo" para que la IA mande sin pedirte confirmación).
6. Cada corrección tuya → `reglas-aprendidas.md` → la IA acierta más la próxima.

---

## 6. Playbook de replicación (proyecto nuevo o existente)

### Requisitos
- Dominio propio del cliente. Cuenta **Cloudflare** (gratis) + **Resend** (gratis). Gmail destino.
- Claude Code (para el loop) y, si quieres respaldo en nube, GitHub + plan con routines.

### Paso 0 — ¿Dónde está el DNS del dominio hoy?
Revísalo: `dig +short NS dominio.cl`.

### CASO A — el sitio/dominio está en **Vercel** (DNS en Vercel)
Para usar Email Routing necesitas el DNS en Cloudflare (el sitio sigue en Vercel):
1. En **Cloudflare → Add a site** → agrega el dominio (plan Free).
2. **Recrea los registros del sitio** que estaban en Vercel (Vercel → Project → Domains te dice cuáles: un `A`/`CNAME` a Vercel), en modo **"solo DNS"** (sin proxy, para que el SSL de Vercel funcione). Copia también verificaciones (`google-site-verification`) y `CAA`.
3. Cambia los **nameservers** en el registrador (ej. NIC Chile `clientes.nic.cl`) a los 2 de Cloudflare. *(NIC no tiene API → este paso es manual.)*
4. Espera propagación → zona "Active".
> Alternativa sin mover nameservers: **ImprovMX** (agregas MX en el DNS de Vercel) — pero pierdes la integración Cloudflare.

### CASO B — el dominio ya está en **Cloudflare**
Te saltas todo lo anterior. Directo al Paso 1.

### Paso 1 — Email Routing (recibir)
- Cloudflare → Email → **Enable Email Routing** (agrega MX/SPF solo).
- Agrega tu **Gmail destino** y verifícalo (1 clic).
- Regla `contacto@` (o catch-all) → de momento al Gmail (luego al Worker).
> Todo esto se puede hacer por **API de Cloudflare** con un token (Zone DNS + Email Routing) o el Global API Key.

### Paso 2 — Resend (enviar)
- Crea cuenta en resend.com → **Add Domain** → agrega los registros DKIM/SPF (subdominio `send`) en Cloudflare → **Verify**.
- Crea una **API key**.

### Paso 3 — Worker + D1 + Panel (copia `correo-worker/`)
- `wrangler d1 create <db>` → pega el `database_id` en `wrangler.toml`.
- Aplica los `schema*.sql`.
- Secretos: `wrangler secret put PANEL_PASS`, `RESEND_API_KEY`, `VAPID_PRIVATE`.
- Genera VAPID: `npx web-push generate-vapid-keys` (público va en `wrangler.toml`, privado = escalar `d` como secreto).
- `wrangler deploy`.
- Repunta Email Routing (contacto@ + catch-all) → acción **worker**.
- (Opcional) **Dominio del panel:** `panel.tudominio.cl` vía Cloudflare Workers custom domain (API `/accounts/{id}/workers/domains`).

### Paso 4 — Loop (cerebro)
- Copia `scripts/agente_correos.py`, `generar_cotizacion.py`, `.claude/commands/revisa-correos.md`, `clientes/`.
- `config/agente.local.json` con `worker_url` + `panel_pass`.
- Corre: **`/loop 3m /revisa-correos`** en tu terminal.

### Paso 5 — Respaldo en la nube (opcional, routine)
- Crea un **repo PRIVADO** con scripts + comando + conocimiento (NO en el repo público del sitio).
- Crea la routine (`/schedule`) apuntando al repo privado. **Config web:** env vars `WORKER_URL`/`PANEL_PASS`,
  acceso de red al dominio del Worker, acceso GitHub al repo privado.
- **Mínimo de cadencia en la nube = 1 hora.** Lo ideal: que un **cron de Cloudflare (gratis)** dispare la
  routine **solo si hay cola** (event-gated), no un horario fijo.

### Paso 6 — PWA en el iPhone
- Abre `panel.tudominio.cl` en **Safari** → Compartir → **Añadir a pantalla de inicio** → ábrelo desde el ícono.
- Toca 🔔 → permite notificaciones (se suscribe). Prueba con `POST /api/test-push`.

---

## 7. Gotchas aprendidos (importantes)

- **Cloudflare bloquea User-Agents no-navegador** (`error 1010`) → scripts deben mandar UA de Chrome.
- **iOS Web Push exige `aes128gcm` (RFC 8291) + `Authorization: vapid`.** PushForge y @block65 usan
  el viejo `aesgcm` → NO sirven. Implementado a mano en `webpush.js` (verificado con round-trip).
- **iOS:** push solo funciona con la PWA **agregada a inicio** y abierta desde el ícono (no en pestaña Safari).
- **Routines (nube):** mínimo 1 hora; tope diario de runs por plan → batch (1 run procesa toda la cola).
- **NIC Chile (.cl):** sin API → el cambio de nameservers es manual. Cloudflare Registrar no soporta `.cl`.
- **Repo público:** nunca subir `clientes/historial.md` (PII) ni datos de banco. Usar repo privado para la routine.
- **D1:** límite ~2MB por valor (PDFs de cotización pesan poco, OK como base64).
- **VAPID:** la clave pública del panel debe ser **par** de la privada del Worker.

---

## 8. Estado actual (destaperapido.cl) y pendientes

**Hecho:** recepción (Cloudflare), envío (Resend), Worker+D1+panel, captura, redacción con PDF,
adjuntos, push iOS (aes128gcm verificado), panel vivo, "Ajuste IA" con cola y auto-envío,
confianza + notificación selectiva, aprendizaje (`reglas-aprendidas.md`), repo privado + routine creada.

**Pendiente:**
- Config web de la routine (env vars + red + acceso GitHub) y **habilitarla**.
- **Event-gating**: cron Cloudflare dispara la routine solo si hay cola y el PC no la atendió.
- **Modo autónomo (Nivel 3):** que la alta confianza se envíe sola.
- 🔐 Regenerar el **Global API Key** de Cloudflare.

> Doc relacionada: `decision-correos-con-dominio.md`, `tutorial-correo-cloudflare.md`.
