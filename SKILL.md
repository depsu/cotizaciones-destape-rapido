---
name: cotizaciones-destape-rapido
description: Genera cotizaciones formales en PDF para la empresa Destape Rápido (servicios sanitarios y arriendo de baños químicos en Maipú, RM). Usa este skill SIEMPRE que el usuario pida crear, armar o generar una "cotización", "presupuesto formal", "propuesta comercial" o "PDF de cotización" — incluso si no menciona explícitamente a Destape Rápido. También úsalo cuando el usuario diga cosas como "cotiza para [cliente]", "hazme un presupuesto para [servicio]", "cotización para baño químico" o mencione valores de arriendo de baños químicos con o sin limpieza/mantención/arnés.
---

# Cotizaciones Destape Rápido

Este skill genera cotizaciones formales en PDF con los datos de la empresa **Destape Rápido** ya precargados. El objetivo es producir un documento profesional, listo para enviar al cliente por email o WhatsApp, usando un diseño consistente (paleta azul corporativo, tipografía Helvetica, estructura clara).

## Datos FIJOS del emisor (no preguntarlos)

- **Empresa:** Destape Rápido
- **Giro:** Servicios sanitarios y arriendo de baños químicos
- **Dirección:** Maipú, Región Metropolitana
- **Teléfono:** +56 9 3647 0112
- **Sitio web:** destaperapido.cl

Si el usuario da datos adicionales del emisor (RUT, email, responsable que firma), usarlos. Si no los da, no inventarlos.

## Precios base de referencia

Todos los valores son **netos** (se les suma IVA 19%). Si el usuario indica un valor distinto, usar el valor que el usuario indique, no estos.

| Servicio | Valor neto |
|---|---|
| Arriendo mensual: 1 baño químico + limpieza semanal | $180.000 |
| Arriendo mensual: 2 baños químicos + limpieza semanal (30% dcto 2da unidad) | $306.000 |
| Arriendo mensual: baño químico con arnés (para obra / izaje) | $200.000 |
| Adicional mensual: limpieza 2 veces por semana | +$30.000 |
| Evento corto (hasta 5 días): 1 baño químico | $100.000 |

## Flujo de trabajo

1. **Revisar lo que el usuario ya entregó** en el mensaje. Los datos típicos a extraer son:
   - Nombre o razón social del cliente
   - RUT del cliente (si está)
   - Email o teléfono de contacto
   - Dirección o lugar de instalación
   - Período del servicio (mensual, o fechas específicas como "20-24 de mayo")
   - Servicio solicitado (cuántos baños, con/sin arnés, frecuencia de limpieza)
   - Valor (si el usuario especifica uno distinto a los base)

2. **Preguntar solo lo que falte Y sea importante.** No preguntar todo de una vez. Si falta solo dirección, preguntar solo eso. Si el usuario dice "no tengo los datos del cliente" o "omite cliente", generar el PDF solo con el emisor.

3. **Asumir razonablemente** lo que no dice:
   - IVA: siempre 19% sobre el valor neto.
   - Validez: 15 días desde emisión.
   - Cobertura: Región Metropolitana.
   - Mantención: según lo pedido (si no dice, asumir 1 vez/semana para mensual).

4. **Generar el PDF** ejecutando el script `scripts/generar_cotizacion.py` con los parámetros correspondientes. Ver sección "Uso del script".
   - **Ruta y nombre OBLIGATORIOS:** guardar siempre en `cotizaciones/` con el formato `cotizacion-AAAAMMDD-<cliente>.pdf` (cliente en kebab-case, ej. `cotizacion-20260622-ignacio-cancino.pdf`). **Nunca** generar en `/tmp`.

5. **Enviar el PDF por correo automáticamente** (modalidad elegida: "generar y enviar de una"):
   - **Si hay email del cliente** → ejecutar `scripts/enviar_cotizacion.py` para enviarlo directo. Ver sección "Envío automático por correo".
   - **Si NO hay email del cliente** → no enviar; entregar el PDF y el resumen para correo (sección "Resumen para correo") para que el usuario lo mande manualmente, e indicar que faltó el email.
   - **EXCEPCIÓN — Modo análisis (NO enviar):** ver sección "Modo análisis: dudas o comparación de precios". Si el usuario quiere analizar/comparar precios o tiene dudas antes de responder, generar los PDF pero **NO** enviar hasta que él lo confirme explícitamente.

6. **Confirmar al usuario** qué se hizo: ruta del PDF, montos clave (neto / IVA / total mensual), y —si se envió— a qué correo, con qué asunto.

## Modo análisis: dudas o comparación de precios (NO enviar hasta confirmar)

A veces Alejandro no quiere "generar y enviar de una": quiere **analizar un precio o comparar opciones antes de responder el correo**, o simplemente resolver una duda. En esos casos el envío automático queda **suspendido**.

**Cómo detectarlo (señales en el mensaje):**
- Pide explícitamente comparar o evaluar: "ofrecer 2 tipos de cotizaciones", "me gustaría analizar", "cuánto me recomiendas", "qué valor cobro", "compara opción 1 vs 2".
- Plantea una duda de precio/estrategia antes de cerrar: "¿está bien este valor?", "¿cuánto le cobro?", "ayúdame a decidir".
- Dice expresamente que no mande aún: "no mandes el correo", "primero quiero ver/analizar".

**Qué hacer en modo análisis:**
1. **Generar los PDF igual** (en `cotizaciones/` con el nombre correcto), porque sirven para revisar el documento real. Si son varias alternativas, un PDF por opción con sufijo claro (ej. `...-opcion-a.pdf`, `...-opcion-b.pdf`).
2. **NO ejecutar `enviar_cotizacion.py`.** Nada de correos hasta que Alejandro confirme.
3. **Entregar el análisis en el chat:** tabla comparativa con neto / IVA 19% / total mensual por opción, la diferencia entre opciones, una **recomendación clara** (cuál ofrecer como principal y por qué), y los supuestos aplicados (arnés sí/no, descuentos por volumen, etc.).
4. **Cerrar preguntando** si ajusta algo o si ya lo envía, y a qué correo.
5. **Enviar solo cuando lo confirme** ("mándalo", "está bueno, envíalo"). Si pidió comparar varias opciones para que el cliente elija, por defecto **enviar todas las opciones en un solo correo** (un PDF adjunto por opción), con un cuerpo que las resuma; el script `enviar_cotizacion.py` adjunta un solo PDF, así que para varios adjuntos se arma el `EmailMessage` reutilizando sus funciones (`cargar_config`, `adjuntar_pdf`, `enviar`).

**Regla de oro:** ante cualquier duda sobre si Alejandro quiere enviar ahora o solo analizar, **NO enviar** y preguntar. El envío a un cliente es difícil de revertir.

## Resumen para correo (cuando NO hay email del cliente)

Si el cliente **no** tiene email (no se puede enviar automático), junto con el PDF se debe entregar el resumen para que el usuario lo copie y pegue al enviar manualmente:

1. **Email destinatario** — indicar a qué dirección enviar el correo. Tomarlo del email del contacto del cliente (campo `Email` de los datos del cliente). Si no hay email, decirlo explícitamente: "no se entregó email del cliente, agregarlo manualmente al enviar".
2. **Asunto** — una línea, formato: `Cotización <servicio breve> – <proyecto o cliente>`.
3. **Cuerpo del correo** — texto plano, **listo para copiar y pegar**. NO usar markdown blockquote (`>`), NO usar tablas, NO usar negritas con asteriscos. Solo texto plano con guiones simples para bullets. Envolver el bloque en una code fence ```` ``` ```` para que se pueda copiar limpio desde el chat sin la línea vertical de cita.

**Estructura del cuerpo:**

```
Estimad[o/a] <Nombre del contacto>,

Junto con saludar, adjunto cotización formal por <servicio breve y específico> para <proyecto / uso>, considerando <detalle relevante de ubicación / fechas / cantidad>.

Resumen comercial:
- <cantidad y descripción del servicio>
- <frecuencia de limpieza / mantención>
- <inclusiones: despacho, instalación, retiro, disposición final>
- Valor unitario: $<X> neto / mes <(aclarar si es tarifa por volumen)>
- Total mensual: $<neto> neto · $<con IVA> con IVA
- Modalidad: <mensual con renovación / período específico>
- Facturación: <a 30 días / contra entrega / según se acuerde>

En la cotización adjunta encontrarán el detalle completo, condiciones del servicio y observaciones.

Quedamos atentos para coordinar <visita técnica / instalación / próximos pasos>. Cualquier consulta no dude en escribirnos o llamarnos al +56 9 3647 0112.

Saludos cordiales,
Destape Rápido – Servicios sanitarios y arriendo de baños químicos
destaperapido.cl
```

**Reglas para el cuerpo:**
- Saludo personalizado con el nombre del contacto si está disponible; si no, "Estimados,".
- Resumen comercial siempre con cifras mensuales como protagonistas (ver "Valores SIEMPRE mensuales").
- Si el proyecto se extiende varios meses, mencionar el dato como referencia secundaria al final del resumen comercial (ej: "- Duración estimada: 8 meses (total contrato $X con IVA)"), pero nunca reemplazar la cifra mensual.
- Mantener el correo corto: máximo ~12 líneas de cuerpo. El detalle va en el PDF, el correo es el "elevator pitch".

## Uso del script

El script `scripts/generar_cotizacion.py` acepta los datos mediante un archivo JSON de configuración. Esto permite generar cualquier cotización sin modificar el script.

### Pasos para Claude:

1. Crear un archivo JSON temporal con los datos de la cotización (ver schema más abajo).
2. Ejecutar: `python scripts/generar_cotizacion.py <ruta-al-json> <ruta-salida.pdf>`
3. El PDF queda listo.

### Schema del JSON

```json
{
  "numero_cotizacion": "N° 2026-0423-001",          // opcional, autogenera si se omite
  "subtitulo": "Arriendo de baño químico",           // texto bajo "COTIZACIÓN"
  "cliente": {                                        // OMITIR este objeto completo si no hay datos
    "titulo": "CLIENTE",                              // o "SOLICITANTE" según corresponda
    "campos": [
      ["Razón social", "Inmobiliaria Nacional S.A."],
      ["RUT", "79.809.460-2"],
      ["Email", "contacto@empresa.cl"],
      ["Dirección", "Las Condes, RM"]
    ]
  },
  "items": [
    {
      "descripcion_titulo": "Arriendo mensual de baño químico con arnés",
      "descripcion_bullets": [
        "Unidad equipada con arnés de seguridad.",
        "Despacho, instalación y retiro incluidos.",
        "Limpieza semanal y disposición final de residuos."
      ],
      "cantidad": 1,
      "valor_unitario_neto": 200000
    }
  ],
  "condiciones_extra": [                              // opcional — se agregan a las estándar
    ["Período", "Del 20 al 24 de mayo"]
  ],
  "observaciones_extra": [                            // opcional — se agregan a las estándar
    "El cliente debe asegurar acceso vehicular."
  ]
}
```

### Ejemplo completo

```bash
# 1. Escribir el JSON con el schema de arriba (ej. cotizaciones/cotizacion-20260622-ignacio-cancino.json)
# 2. Generar el PDF en cotizaciones/ con el nombre correcto:
python scripts/generar_cotizacion.py \
  cotizaciones/cotizacion-20260622-ignacio-cancino.json \
  cotizaciones/cotizacion-20260622-ignacio-cancino.pdf
# 3. Si hay email del cliente, enviarlo:
python scripts/enviar_cotizacion.py \
  cotizaciones/cotizacion-20260622-ignacio-cancino.pdf \
  Ignacio17cancino@gmail.com \
  --cliente "Ignacio Cancino" \
  --asunto "Cotización Destape Rápido — Arriendo de baño químico"
```

## Envío automático por correo

Cuando el cliente tiene email, después de generar el PDF se envía con el script `scripts/enviar_cotizacion.py`, que usa el SMTP del hosting (`config/smtp.local.json`, fuera de git).

### Uso

```bash
python scripts/enviar_cotizacion.py <ruta-pdf> <email-cliente> \
  --cliente "Nombre Cliente" \
  --asunto "Cotización Destape Rápido — <servicio breve>" \
  --mensaje "<cuerpo del correo en texto plano>"
```

Opciones: `--cliente`, `--asunto`, `--cc correo@x.cl` (repetible), `--mensaje`. Si se omite `--asunto` o `--mensaje`, el script usa valores por defecto formales.

### Reglas para Claude al enviar

1. **Asunto:** `Cotización Destape Rápido — <servicio breve>` (ej. "— Arriendo de baño químico").
2. **Cuerpo (`--mensaje`):** construirlo en **texto plano** siguiendo la misma estructura y reglas de la sección "Resumen para correo" (saludo personalizado, resumen comercial con cifras **mensuales** como protagonistas, máximo ~12 líneas). El detalle completo va en el PDF adjunto.
3. **Valores mensuales:** aplica la REGLA DURA — nunca poner el total acumulado del proyecto como cifra principal en el correo.
4. **Confirmar:** tras enviar, reportar a qué correo se mandó y con qué asunto. Recordar al usuario revisar que no caiga en spam la primera vez que se escribe a un dominio nuevo.

### Configuración SMTP (ya operativa)

- Host: `panel.freehosting.com` · Puerto `465` (SSL) · Usuario `contacto@destaperapido.cl`.
- Las credenciales viven en `config/smtp.local.json` (ignorado por git). Si el envío falla por autenticación, revisar ese archivo o correr `python scripts/test_smtp.py` para diagnosticar.

## Estilo del PDF

- **Colores:** azul `#1F5AA8` (primario), azul claro `#E8F0FB` (fondos), gris `#666666` (texto secundario), verde `#0E8F5E` (destacar descuentos).
- **Tipografía:** Helvetica.
- **Tamaño:** carta (letter).
- **Márgenes:** 20mm laterales, 35mm top, 22mm bottom.
- **Moneda:** CLP con separador de miles con punto (ej: `$180.000`).
- **Numeración:** `N° {AAAA}-{MMDD}-{correlativo}` si no se especifica.
- **Header:** logo textual "DESTAPE RÁPIDO" + subtítulo + contacto a la derecha, línea azul.
- **Footer:** datos de contacto centrados + número de página.

## Puntos de atención

- **Netos vs. con IVA:** por defecto asumir que los valores dados son **netos**. Si hay duda, avisar al final ("los valores están tratados como netos + IVA 19%; si querías que X fuera total final, me avisas").
- **Período mensual vs. evento corto:** ajustar la redacción de condiciones. Para eventos cortos (fechas puntuales), hablar de "período del servicio" y "retiro al finalizar". Para mensuales, hablar de "renovación automática" y "facturación mensual".
- **Valores SIEMPRE mensuales (REGLA DURA):** la cifra protagonista de cualquier cotización de arriendo es **el valor mensual**, sin excepciones. Aplica tanto al PDF como al cuerpo del correo.
  - En la tabla de ítems del PDF: `cantidad = nº de unidades` y `valor_unitario_neto = valor mensual por unidad`. El recuadro "TOTAL" debe mostrar la **mensualidad** con IVA (no el acumulado del proyecto).
  - En el correo: en "Resumen comercial" la línea "Total mensual: $X neto · $Y con IVA" es la cifra principal.
  - Si el cliente indica una duración en meses (3, 6, 12 meses, etc.) o un proyecto largo, el total del contrato (mensual × meses) se menciona **solo como referencia secundaria**: en el PDF dentro de `condiciones_extra` u `observaciones_extra`, y en el correo como una línea adicional al final del resumen comercial (ej: `- Duración estimada: 6 meses (referencia total contrato: $Z con IVA)`).
  - **Nunca** poner el total acumulado del proyecto como cifra principal, ni en el PDF ni en el correo, aunque el cliente lo pida así.
  - Razón: el cliente compromete pagos mensuales recurrentes, no un desembolso único. Mostrar el acumulado como cifra principal asusta innecesariamente y distorsiona la comparación con la competencia.
- **Arnés:** mencionar **"con arnés" solo cuando la unidad realmente lo lleve**. NUNCA escribir "sin arnés" en ningún contexto (ni en descripciones, bullets, condiciones ni observaciones): el baño básico/estándar se entiende sin arnés por defecto, no hace falta aclararlo. Si el cliente pide expresamente "básicos", es estándar (sin arnés) → describirlo simplemente como "baño químico" o "baño químico estándar", sin la coletilla. Si el servicio es para obra/construcción con izaje en altura y lleva arnés, ahí sí indicar "con arnés" y aclarar en condiciones que el izaje queda a cargo del cliente.
- **Múltiples opciones:** si el usuario pide una cotización con varias alternativas (ej: opción 1 vs opción 2), usar múltiples `items` en el JSON y agregar una sección de resumen.

## Archivos del skill

- `SKILL.md` — este archivo
- `scripts/generar_cotizacion.py` — script que genera el PDF a partir del JSON
- `scripts/enviar_cotizacion.py` — envía el PDF por correo (SMTP del hosting)
- `scripts/test_smtp.py` — diagnóstico de conexión SMTP
- `scripts/requirements.txt` — dependencias (reportlab)
- `config/smtp.local.json` — credenciales SMTP (NO se versiona; ignorado por git)
