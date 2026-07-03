# Tutorial: Correo con dominio propio vía Cloudflare

> Objetivo: que `contacto@destaperapido.cl` **reciba** (en tu Gmail) y puedas
> **responder como** esa dirección — **gratis y sin baneos**, reemplazando el
> hosting gratuito que bloqueaba la IP.

---

## 🗺️ Cómo funciona (arquitectura)

```
   Quien te escribe ──→ 📧 contacto@destaperapido.cl
                              │
                        ☁️ CLOUDFLARE (Email Routing)   ← RECIBE, gratis
                              │  reenvía
                              ▼
                        📥 TU GMAIL  ← lees aquí
                              │
                        📤 "Enviar como" (SMTP Resend)  ← RESPONDES como @destaperapido.cl
```

- **Recibir** = Cloudflare Email Routing (gratis).
- **Enviar/responder** = Gmail "Enviar como" + SMTP de Resend (gratis, 1 dominio).
- Cloudflare **solo necesita tu dirección** de Gmail, nunca tu contraseña.

| Capa | Servicio | Costo |
|---|---|---|
| Recibir | Cloudflare Email Routing | $0 |
| Enviar como | Resend (SMTP, free tier) | $0 (1 dominio) |

---

## ✅ Requisitos previos
- [ ] Acceso a **NIC Chile** (`clientes.nic.cl`) para `destaperapido.cl`.
- [ ] Una cuenta de **Gmail** (la que ya usas).
- [ ] Saber dónde está **alojado el sitio** hoy (Vercel, hosting, etc.) para no tumbarlo.

---

## 📌 Estado actual de `destaperapido.cl` (detectado)

| Qué | Valor actual | Implicancia |
|---|---|---|
| Nameservers | `ns1.vercel-dns.com` / `ns2.vercel-dns.com` | El DNS lo maneja **Vercel** |
| MX (correo) | `panel.freehosting.com` | Correo aún en el hosting que banea (hay que cambiarlo) |
| Sitio (A) | `216.198.79.1`, `64.29.17.1` | Web alojada en **Vercel** |
| TXT | `google-site-verification=…` + SPF de freehosting | Recrear el de Google; descartar SPF viejo |

> Como el DNS está en **Vercel**, tienes dos caminos:
> - **Camino A (mover a Cloudflare):** cambias nameservers en NIC → Cloudflare y
>   **recreas los registros del sitio** en Cloudflare. Usa Email Routing (este tutorial).
> - **Camino B (sin mover nameservers):** dejas el DNS en Vercel y agregas MX de
>   **ImprovMX** en el panel de Vercel (ver Parte E). Más rápido y sin riesgo al sitio.

---

# PARTE A — Migrar el DNS a Cloudflare
*(Hazla solo si el dominio NO está aún en Cloudflare. Si ya lo está, salta a la **PARTE D**.)*

### A1. Crear cuenta en Cloudflare
1. Entra a **https://dash.cloudflare.com/sign-up** y crea una cuenta gratis.
2. Verifica tu correo.

### A2. Agregar el dominio y revisar los registros del sitio ⚠️
1. **Add a site** → escribe `destaperapido.cl` → plan **Free**.
2. Cloudflare **escanea** los registros DNS actuales y los importa.
3. **MUY IMPORTANTE (para que el sitio NO se caiga):** revisa que estén los
   registros que hacen funcionar tu **web**. Ejemplos según dónde esté alojada:

   | Si el sitio está en… | Registro que debe existir |
   |---|---|
   | Vercel | `A` → `76.76.21.21` **o** `CNAME` → `cname.vercel-dns.com` |
   | Un hosting | `A` → la IP del hosting |
   | GitHub Pages | `CNAME` → `usuario.github.io` |

   > Si falta alguno, agrégalo manualmente **antes** de cambiar los nameservers.
   > Copia también cualquier registro `TXT`/`CNAME` de verificación que ya tengas
   > (ej. el `google-site-verification=…` que ya existe en tu dominio).

   > ⚠️ **Tu caso (DNS en Vercel):** como hoy usas los nameservers de Vercel, al
   > moverlos a Cloudflare, Vercel marcará el dominio como **"Invalid Configuration"**
   > y te mostrará en **Project → Settings → Domains** los registros exactos que debes
   > poner en Cloudflare (normalmente un `A` para la raíz y un `CNAME`
   > `cname.vercel-dns.com` para `www`). Agrega **esos** en Cloudflare para que la web
   > siga funcionando. **No copies el SPF viejo de freehosting** (lo reemplaza Resend).

### A3. Copiar los nameservers de Cloudflare
Cloudflare te dará **2 nameservers**, por ejemplo:
```
   xara.ns.cloudflare.com
   rob.ns.cloudflare.com
```
*(los tuyos serán distintos — cópialos tal cual)*

### A4. Cambiar los nameservers en NIC Chile
1. Entra a **https://clientes.nic.cl** → inicia sesión.
2. **Mis dominios** → `destaperapido.cl` → **Editar / Cambiar servidores de nombre (DNS)**.
3. Borra los nameservers actuales (los del hosting viejo) y pon los **2 de Cloudflare**.
   - Si NIC te pide la **IP** de cada nameserver, normalmente **no hace falta**
     (basta el nombre). Si el formulario la exige, déjala en blanco o usa la que resuelva.
4. **Guardar**.

> 🔴 Este es el **único paso 100% manual** (NIC Chile no tiene API). También
> puedes delegarlo a un cliente pasándole los 2 nameservers.

### A5. Esperar la activación
- Tarda de **minutos a ~2 horas** (a veces hasta 24 h).
- Cuando Cloudflare muestre **"Active"** en el dominio, sigue a la Parte B.

---

# PARTE B — Activar el correo (recibir)

### B1. Encender Email Routing
1. En Cloudflare → tu dominio → menú **Email** → **Email Routing** → **Enable**.
2. Cloudflare **agrega solo** los registros `MX` + `TXT (SPF)` necesarios. No toques nada.

### B2. Registrar tu Gmail como destino
1. En **Destination addresses** → **Add address** → escribe tu Gmail.
2. Cloudflare manda un correo de confirmación a tu Gmail → abre y haz **clic en confirmar**.
   *(esto se hace 1 sola vez)*

### B3. Crear la regla de reenvío
**Opción simple (una dirección):**
| Custom address | Action | Destination |
|---|---|---|
| `contacto@destaperapido.cl` | Send to | tu-gmail@gmail.com |

**Opción recomendada (catch-all = atrapa todo):**
- Activa **Catch-all** → `*@destaperapido.cl` → tu Gmail.
- Así también recibes `ventas@`, `admin@`, `facebook@`, etc., todo en tu Gmail.

### B4. Probar
- Desde otro correo, escribe a `contacto@destaperapido.cl`.
- Debe llegar a tu Gmail en **segundos**. ✅ *(si no aparece, revisa Spam)*

> 🎉 Con esto tu correo **ya vuelve a recibir**. Si solo necesitabas eso, terminaste.

---

# PARTE C — Instalar en Gmail (responder como contacto@destaperapido.cl)

Para que al responder salga **desde** `contacto@destaperapido.cl` (y no desde tu Gmail
personal), necesitas un emisor SMTP. Usaremos **Resend** (gratis).

### C1. Preparar el emisor (Resend)
1. Crea cuenta gratis en **https://resend.com** (puedes entrar con Google).
2. **Domains** → **Add Domain** → `destaperapido.cl`.
3. Resend te mostrará unos registros DNS. Agrégalos en **Cloudflare → DNS**:

   | Tipo | Nombre (ej.) | Valor (ejemplo — usa los TUYOS del panel Resend) |
   |---|---|---|
   | MX | `send` | `feedback-smtp.us-east-1.amazonses.com` (prioridad 10) |
   | TXT | `send` | `v=spf1 include:amazonses.com ~all` |
   | TXT | `resend._domainkey` | *(clave DKIM larga que te da Resend)* |
   | TXT | `_dmarc` *(opcional)* | `v=DMARC1; p=none;` |

   > ⚠️ Estos van en el **subdominio `send`**, así que **no chocan** con el MX de
   > recepción de Cloudflare (que está en la raíz). Recibir y enviar conviven bien.
4. En Resend pulsa **Verify** (cuando el DNS propague, queda ✅).
5. **API Keys** → **Create API Key** → cópiala (será la "contraseña" del SMTP).

### C2. Agregar "Enviar como" en Gmail
1. Gmail → ⚙️ **Ver toda la configuración** → pestaña **Cuentas e importación**.
2. En **Enviar como** → **Agregar otra dirección de correo**.
3. Datos:
   - **Nombre:** `Destape Rápido`
   - **Correo:** `contacto@destaperapido.cl`
   - **Desmarca** "Tratar como alias".
4. Siguiente → datos del servidor SMTP:
   | Campo | Valor |
   |---|---|
   | Servidor SMTP | `smtp.resend.com` |
   | Puerto | `465` |
   | Usuario | `resend` |
   | Contraseña | *(tu API Key de Resend)* |
   | Conexión | **SSL** |
5. **Agregar cuenta**.

### C3. Confirmar el código
- Gmail envía un código a `contacto@destaperapido.cl`.
- Como ya configuraste el reenvío (Parte B), **ese código llega a tu Gmail**.
- Cópialo y pégalo para confirmar. ✅

### C4. Probar el envío
- Redacta un correo → en **"De:"** elige `contacto@destaperapido.cl` → envíalo a otra cuenta.
- Debe llegar **desde** `contacto@destaperapido.cl`, sin baneos. 🎉

---

# PARTE D — Versión rápida: el sitio YA está en Cloudflare

Si el dominio **ya usa los nameservers de Cloudflare** (porque el sitio ya está ahí),
**te saltas toda la Parte A** (nada de NIC Chile, nada de cambiar nameservers, nada de
esperar propagación). Solo:

1. Cloudflare → tu dominio → **Email → Email Routing → Enable**.
2. **Add destination** → tu Gmail → confirma el clic.
3. **Regla** `contacto@…` → tu Gmail (o **Catch-all**).
4. (Opcional) **Parte C** para responder como el dominio.

```
   Sitio ya en Cloudflare  →  Email Routing (Enable)  →  destino Gmail  →  regla
                              ⏱️ ~5 minutos, sin tocar NIC Chile
```

| | Sitio NO en Cloudflare (Parte A→C) | Sitio YA en Cloudflare (Parte D) |
|---|:---:|:---:|
| Cambiar nameservers en NIC | ✅ sí (manual) | ❌ no |
| Espera de propagación | ⏳ min–horas | ❌ no |
| Tiempo total | ~15–30 min + espera | ~5 min |

---

# PARTE E — Alternativa SIN mover nameservers (DNS en Vercel + ImprovMX)

*(Para tu caso si prefieres **no tocar** los nameservers de Vercel. El sitio no se
toca; solo agregas registros de correo en el DNS de Vercel.)*

### E1. Crear cuenta en ImprovMX
1. Entra a **https://improvmx.com** → crea cuenta gratis.
2. Agrega el dominio `destaperapido.cl`.
3. Define el alias: `contacto@destaperapido.cl` → **tu Gmail** (o `*` catch-all → tu Gmail).

### E2. Agregar los registros en Vercel
1. Vercel → tu proyecto/dominio → **Settings → Domains → DNS Records**.
2. Agrega lo que indique ImprovMX (valores actuales del panel de ImprovMX):

   | Tipo | Nombre | Valor (ej.) | Prioridad |
   |---|---|---|---|
   | MX | `@` | `mx1.improvmx.com` | 10 |
   | MX | `@` | `mx2.improvmx.com` | 20 |
   | TXT | `@` | `v=spf1 include:spf.improvmx.com ~all` | — |

   > Quita/!reemplaza el MX viejo de `panel.freehosting.com` y el SPF de freehosting.
3. En ImprovMX pulsa **verificar**. Cuando propague, recibirás en tu Gmail.

### E3. Responder como `contacto@destaperapido.cl`
- **Recibir** ya funciona (reenvío de ImprovMX).
- Para **responder como** el dominio: igual que la **Parte C**, configura el
  "Enviar como" en Gmail. Puedes usar el **SMTP de Resend** (recomendado) o el SMTP de
  ImprovMX (este último es de pago).

```
   contacto@destaperapido.cl ──→ ImprovMX (MX en DNS de Vercel) ──→ 📥 tu Gmail
   Sitio en Vercel: intacto. Nameservers: sin cambios.
```

---

# 🛠️ Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El sitio web se cayó tras cambiar NS | Faltó copiar el registro `A`/`CNAME` del sitio | Agrégalo en Cloudflare → DNS (Parte A2) |
| No llega el correo de prueba | DNS aún propagando / regla mal | Espera, revisa Spam, verifica la regla |
| Dominio sigue "Pending" en Cloudflare | Nameservers no actualizados en NIC | Reconfirma los 2 NS en `clientes.nic.cl` |
| Gmail no acepta el SMTP de Resend | Dominio no verificado / API key mala | Verifica el dominio en Resend, regenera la key |
| El código de "Enviar como" no llega | Reenvío (Parte B) no estaba activo | Activa primero el reenvío, reintenta |

---

# ✅ Checklist final
- [ ] Dominio **Active** en Cloudflare
- [ ] Email Routing **Enabled**
- [ ] Gmail confirmado como destino
- [ ] Regla `contacto@` (o catch-all) creada
- [ ] Prueba de **recepción** OK
- [ ] *(opcional)* Dominio verificado en Resend
- [ ] *(opcional)* "Enviar como" en Gmail OK
- [ ] *(opcional)* Prueba de **envío** OK

---

## Notas
- **Sin cambiar nameservers:** si NO quieres mover el DNS a Cloudflare, existe el
  camino alternativo con **ImprovMX** (solo agregas registros MX donde tengas el DNS).
  Pero Cloudflare Email Routing requiere su propio DNS.
- **NIC Chile** no tiene API ni MCP: el cambio de nameservers es manual (1 vez).
- Todo lo de **Cloudflare** posterior se puede automatizar por **API/MCP**
  (ver futuro `scripts/crear_cliente.py`).
