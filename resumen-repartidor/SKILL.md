---
name: resumen-repartidor
description: Gestiona las entregas de Destape Rápido para el repartidor. Úsalo cuando el usuario pida "haz un resumen para el repartidor", "resumen de entrega", "agenda/registra una entrega", "pásame el WhatsApp para el repartidor", "muéstrame las entregas", "genera/actualiza el listado de entregas" o similar. Produce (1) un resumen ordenado con un link de WhatsApp pre-escrito para mandar al repartidor, y (2) una página web mobile-first (listado.html) con las entregas, con botones de WhatsApp al cliente, mapa para llegar y llamar.
---

# Resumen para el repartidor + listado de entregas

Skill para que el repartidor de **Destape Rápido** sepa exactamente a dónde ir, qué entregar, y pueda hablarle al cliente y llegar desde el celular. Todo sale de un único archivo de datos: `entregas.json`.

## Flujo rápido (POR DEFECTO — una sola pasada, sin preguntar de más)

Cuando Alejandro diga **"resumen para repartidor"** y pegue un chat de cliente confirmado, ejecutar TODO de corrido. **No hacer preguntas salvo que falte un dato crítico: dirección, fecha o valor.** Todo lo demás se asume con los defaults.

> 🔝 **REGLA DE PRIORIDAD: lo PRIMERO es enviar el WhatsApp al repartidor.** Apenas se tenga la entrega, correr el script con `--enviar`: abre WhatsApp Desktop y **envía solo** el mensaje (presiona Enter automático; Alejandro no hace nada). **Antes de enviar, verificar que los datos extraídos estén correctos**, porque el envío es automático y sin confirmación manual. Pegar también el link en el chat como respaldo. **Recién después** seguir con lo demás (publicar la página, historial).

1. **Extraer del chat:** cliente, teléfono, dirección, fecha (convertir "el jueves" a la fecha real), hora, servicio, valor, datos de factura.
2. **Cobro (REGLA FIJA, NO preguntar):** el repartidor es el dueño/jefe y **siempre cobra**. `pago.monto` = el valor acordado; **si el cliente lleva factura, el monto es neto + IVA 19%**. Incluir los datos de facturación en `factura`. Nunca preguntar la forma/método de cobro: solo dejar los datos. **Aseo:** si el chat no especifica, queda el default (semanal 7–10 días).
3. **Agregar** la entrega a `entregas.json`.
4. **🔝 ENVIAR PRIMERO (automático):** verificar que los datos estén correctos y correr `python3 resumen-repartidor/scripts/resumen_repartidor.py --id <id> --enviar` → abre WhatsApp y envía solo el mensaje al repartidor. Pegar también el link en el chat como respaldo. (Si se prefiere revisar antes de enviar, usar `--abrir` en vez de `--enviar`.)
5. **Después**, en el mismo turno: **publicar** con `bash resumen-repartidor/publicar.sh "agrega entrega <cliente>"` y **actualizar** la ficha en `clientes/historial.md`. Confirmar al final que la página quedó en línea.

## Fuente de datos: `entregas.json`

Cada entrega tiene esta forma:

```json
{
  "id": "2026-06-25-cliente-ejemplo",
  "cliente": "Nombre Cliente",
  "telefono": "+56 9 1111 2222",
  "direccion": "Calle 123, Comuna, Región Metropolitana",
  "fecha": "2026-06-25",
  "hora": "",
  "servicio": "1 baño químico — arriendo mensual",
  "cantidad": 1,
  "aseo": "",
  "pago": { "monto": 160000, "nota": "Mensual. Cobrar al entregar." },
  "factura": { "requiere": true, "razon_social": "Empresa SpA", "rut": "76.123.456-7", "email": "pagos@empresa.cl" },
  "detalle": ["Instalar 1 baño químico.", "Dejar insumos: papel y desodorizante."],
  "notas": "Confirmar con el cliente antes de llegar.",
  "estado": "pendiente"
}
```

- **`id`**: único. Convención `AAAA-MM-DD-<cliente-kebab>`.
- **`estado`**: `pendiente` | `en-camino` | `entregado`.
- **`hora`**: opcional.
- **`pago`** (OBLIGATORIO): `monto` en CLP = lo que el repartidor (dueño) **le cobra al cliente**, y `nota` (forma/momento de pago). Es el dato clave de la entrega.
- **`cantidad`**: número de baños. Se muestra como íconos 🚽 (1–4 baños = esa cantidad de 🚽; más de 4 = `🚽+`), tanto en el resumen de WhatsApp como en la página. Si se omite, se infiere del texto del `servicio` (ej. "2 baños…" → 2); por defecto 1.
- **`aseo`**: frecuencia de limpieza. **Si se deja vacío o se omite, por defecto es "Aseo semanal (cada 7 a 10 días)"** (se aplica automáticamente en el resumen y la página).
- **`factura`** (opcional): solo si el cliente la requiere. Campos: `requiere`, `razon_social`, `rut`, `giro`, `direccion`, `email` (los que se tengan).
- El bloque `repartidor` (arriba del archivo) tiene `nombre` y `telefono` del repartidor (para dirigirle el WhatsApp). Si `telefono` está vacío, el link igual funciona: abre WhatsApp para elegir el contacto.

> **Una entrega se crea SOLO cuando Alejandro lo confirma por WhatsApp** (típicamente: dice "resumen para repartidor" y pega el chat). **Haber enviado una cotización/PDF NO confirma una entrega** — esos son leads en seguimiento, no entregas. De un chat confirmado se extrae todo: cliente, dirección, teléfono, servicio, **valor a cobrar**, aseo, factura (si aplica), fecha.

## Qué hace Claude según lo que pidan

### 1. "Haz un resumen para el repartidor" → texto + link de WhatsApp

Ejecutar `scripts/resumen_repartidor.py`. Devuelve, por cada entrega: el resumen ordenado en texto plano, un **link `wa.me` con ese resumen ya pre-cargado** (solo abrir y enviar) y un link de Google Maps.

```bash
python scripts/resumen_repartidor.py --hoy          # entregas de hoy
python scripts/resumen_repartidor.py --fecha 2026-06-25
python scripts/resumen_repartidor.py --id 2026-06-25-ignacio-cancino
python scripts/resumen_repartidor.py                # todas las pendientes
```

Al responder en el chat: entregar el **link de WhatsApp** de forma destacada (es lo que el usuario va a tocar) y, si ayuda, mostrar también el resumen en texto.

### 2. "Agenda / registra una entrega"

Agregar (o editar) el objeto correspondiente en `entregas.json`. Extraer del mensaje del usuario o de una cotización existente: cliente, teléfono, dirección, fecha, servicio, detalle, notas. Mantener el `id` con la convención. Tras editar, **regenerar el listado** (paso 3).

### 3. "Muéstrame / genera / actualiza el listado de entregas" → página web

Ejecutar `scripts/generar_listado.py`. Genera `listado.html`: página **mobile-first, autocontenida** (sin dependencias), con las entregas agrupadas por fecha; al tocar una se despliega el detalle, con botones de **WhatsApp al cliente**, **Cómo llegar** (Google Maps) y **Llamar**.

```bash
python scripts/generar_listado.py            # genera listado.html
```

Para que el repartidor la vea desde su celular, subir `listado.html` al hosting (vía File Manager del panel) y pasarle el enlace. También se puede abrir localmente.

**Importante:** cada vez que se modifica `entregas.json`, hay que regenerar `listado.html` para que refleje los cambios.

## Reglas

- **Teléfonos:** los links de WhatsApp y mapas se construyen solos desde los datos. Para Chile, si el número viene sin prefijo país, se asume `+56`.
- **No inventar datos:** si falta dirección o teléfono de una entrega, pedirlo; sin dirección no hay link de mapa, sin teléfono no hay botón de WhatsApp al cliente.
- **Coherencia con cotizaciones:** los datos de una entrega suelen venir de una cotización ya hecha (ver skill `cotizaciones-destape-rapido`). Reutilizar cliente/teléfono/dirección de ahí cuando aplique.
- **Empresa:** Destape Rápido (tel. +56 9 3647 0112).

## Aprender de cada cliente (para negociar)

Existe un historial en `../clientes/historial.md` (raíz del proyecto). **Mantenerlo actualizado**: cada vez que se cotiza, entrega o negocia con un cliente, agregar o actualizar su ficha (precio acordado, sensibilidad al precio, condiciones, qué gancho funcionó, estado).

Cuando Alejandro pregunte **cómo abordar o negociar un cliente** (sobre todo casos dudosos o atípicos: precio fuera de lo común, regateo, gran volumen, duda de cierre), **leer primero `clientes/historial.md`** y basar la recomendación en lo aprendido (qué precios se han aceptado por comuna/tipo de cliente, qué objeciones aparecen, qué cierres funcionaron). Dar una recomendación concreta, no genérica.

## Archivos del skill

- `SKILL.md` — este archivo
- `entregas.json` — datos de las entregas (lo edita Claude/el usuario)
- `scripts/resumen_repartidor.py` — resumen + link de WhatsApp para el repartidor
- `scripts/generar_listado.py` — genera `listado.html` (página mobile-first)
- `listado.html` — salida generada (subir al hosting para verla en el celular)
