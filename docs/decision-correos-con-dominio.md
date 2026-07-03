# Decisión: cómo creamos correos con dominio propio (sin baneos, gratis)

> **Estado:** Aceptada · **Fecha:** 2026-06-28 · **Aplica a:** todos los proyectos/clientes
> Documento de decisión + playbook reutilizable. Detalle paso a paso en
> [`tutorial-correo-cloudflare.md`](./tutorial-correo-cloudflare.md).

---

## 1. Problema
Los correos del tipo `contacto@dominio.cl` alojados en **hosting compartido gratuito**
(ej. `panel.freehosting.com`) fallan: IP compartida "sucia", **baneo de IP por
anti-fuerza-bruta**, sin API y con SPF/DKIM mal configurados → caen en spam o dejan de
enviar/recibir. No escala para alguien que administra **varias empresas/clientes**.

## 2. Decisión
Separar el correo en **dos capas**, ambas con infraestructura seria y gratis al inicio:

| Capa | Servicio | Por qué |
|---|---|---|
| **Recibir** | **Cloudflare Email Routing** | Gratis, reenvía a un Gmail, API/MCP, sin baneos |
| **Enviar / responder / automatizar** | **Resend** (o Amazon SES a escala) | DKIM/SPF correctos, API + MCP, reputación por dominio |
| **Buzón final** | El **Gmail** del usuario (o Proton) | Se lee/responde desde la app de siempre |

- **Recibir** nunca cuesta. **Enviar** es gratis hasta los límites de Resend (3.000/mes, 1 dominio).
- La **separación por cliente** se hace en el panel propio o con cuentas Resend por cliente,
  **no** pagando "Teams" de Resend (cada team se factura aparte).

## 3. Alternativas consideradas (y por qué no)
| Alternativa | Veredicto |
|---|---|
| Seguir en hosting gratuito | ❌ banea, sin API, mala entrega |
| Zoho Mail Free | 🟡 buzón propio gratis, pero **sin IMAP** (no app de Gmail) y 1 dominio |
| Google Workspace | 🟡 lo mejor en fiabilidad, pero ~US$6/usuario |
| Resend "Teams" (uno por cliente) | ❌ cada team se factura aparte (~US$20 c/u) |
| ImprovMX (reenvío vía MX) | ✅ válido si NO se quiere mover nameservers a Cloudflare |

## 4. Arquitectura
```
   Quien escribe ──→ contacto@dominio.cl
                          │
                    ☁️ Cloudflare Email Routing   (recibe, gratis)
                          │  reenvía
                          ▼
                    📥 Gmail del usuario  ──responde con──┐
                                                          ▼
                                          📤 Resend SMTP/API  (envía como @dominio)
```
- Requisito: el dominio usa **nameservers de Cloudflare**.
- Los registros del **sitio** (Vercel/otros) se recrean en Cloudflare en modo **"solo DNS"**
  para no romper el SSL del hosting.

## 5. Costos
| Escala | Costo |
|---|---|
| 1 dominio (recibir + enviar) | **US$0** (Cloudflare + Resend free) |
| Varios dominios en 1 cuenta Resend | US$20/mes (Pro, hasta 10) |
| Muchos dominios | 1 cuenta Resend gratis **por cliente** (US$0) o **Amazon SES** (~US$0,10/1.000) |

## 6. Playbook para un dominio nuevo
Resumen (detalle en el tutorial). Lo de **Cloudflare se automatiza por API**;
el cambio de nameservers es **manual** (registradores como NIC `.cl` no tienen API).

```
1. Crear la zona del dominio en Cloudflare              [API]
2. Recrear registros del sitio + CAA + verificaciones   [API]  (modo "solo DNS")
3. Cambiar nameservers en el registrador → Cloudflare    [MANUAL, 1 vez]
4. Esperar propagación → zona "active"                   [espera]
5. Activar Email Routing + regla contacto@ → Gmail       [API]
6. (Opcional) Resend para "responder como" / automatizar [API]
```

### Pasos manuales inevitables
- **Cambio de nameservers** en el registrador (NIC Chile no tiene API/MCP).
- **Crear la cuenta Resend** del cliente (si se usa el modelo "una cuenta por cliente").
- 1 clic para verificar el Gmail destino (si no estaba verificado antes en la cuenta).

## 7. Modelo multi-cliente
- **El cliente es dueño** de su dominio y (si aplica) de su cuenta Resend → US$0 para la agencia.
- La agencia **cobra la instalación/configuración**; la automatización (cotizaciones, etc.)
  es un **plus pagado**.
- Correo "maestro" del cliente = `admin@sudominio.cl` (catch-all a un Gmail) para registrar
  servicios (Resend, Facebook, Google Business…).

## 8. Monitoreo (resumen)
Para saber si seguimos "sanos" (no baneados / no en spam) — ver doc de monitoreo:
- **DMARC** con `rua=` → reportes de autenticación/spoofing.
- **Google Postmaster Tools** → reputación y % de spam en Gmail.
- **Test de colocación** periódico (mail-tester / GlockApps) vía **Worker con cron** de Cloudflare.
- **Resend API** → tasas de rebote/queja.

## 9. Caso real aplicado: `destaperapido.cl` (2026-06-28)
- Estaba en **Vercel** (DNS) + correo en **freehosting** (baneaba).
- Se creó la zona en Cloudflare, se recrearon los registros del sitio Vercel
  (CNAME apex + wildcard, CAA, google-site-verification) en "solo DNS".
- Nameservers cambiados en NIC Chile → `annalise.ns.cloudflare.com` / `carl.ns.cloudflare.com`.
- Email Routing → `contacto@destaperapido.cl` reenvía a `rivera.ale98@gmail.com`.
- Pendiente/opcional: "responder como" vía Resend.

---

> **Regla de oro:** recibir = Cloudflare (gratis, siempre). Enviar = Resend/SES (gratis al
> inicio). Nunca volver a hosting compartido gratuito para correo.
