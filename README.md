# Skill: Cotizaciones Destape Rápido

Skill para Claude Code que genera cotizaciones formales en PDF para la empresa **Destape Rápido** (Maipú, RM).

## ¿Qué hace?

Cuando le pidas a Claude algo como *"cotización para Juan, 2 baños químicos en Las Condes"*, este skill se activa automáticamente y:

1. Usa los datos de emisor ya precargados (Destape Rápido, Maipú, teléfono, web).
2. Aplica los precios base (o los que tú indiques).
3. Genera un PDF profesional con diseño corporativo (azul, Helvetica, estructura formal).
4. Calcula automáticamente IVA 19%.
5. Omite la sección de cliente si no tienes los datos.

## Instalación en Claude Code

### 1. Verifica que tengas Claude Code instalado

```bash
claude --version
```

Si no lo tienes, instala desde: https://docs.claude.com/en/docs/claude-code/overview

### 2. Copia la carpeta a la ruta de skills

**Opción A — Skill global** (disponible en todos tus proyectos):

```bash
mkdir -p ~/.claude/skills
cp -r cotizaciones-destape-rapido ~/.claude/skills/
```

**Opción B — Skill por proyecto** (solo dentro de un proyecto específico):

```bash
cd /ruta/a/tu/proyecto
mkdir -p .claude/skills
cp -r /ruta/al/skill/cotizaciones-destape-rapido .claude/skills/
```

### 3. Instala la dependencia Python

El skill usa `reportlab` para generar el PDF:

```bash
pip install reportlab
```

o con `uv`:

```bash
uv pip install reportlab
```

### 4. ¡Listo!

Abre una sesión de Claude Code en tu terminal y escribe algo como:

> *"hazme una cotización para María González, 1 baño químico con arnés, obra en Providencia, precio 200 lucas neto"*

Claude detectará el skill, te pedirá lo que falte y generará el PDF.

## Estructura de la carpeta

```
cotizaciones-destape-rapido/
├── SKILL.md                    ← instrucciones para Claude (cuándo activarse, qué hacer)
├── README.md                   ← este archivo
├── ejemplo_config.json         ← JSON de ejemplo para entender el schema
└── scripts/
    ├── generar_cotizacion.py   ← script Python que genera el PDF
    └── requirements.txt        ← dependencias
```

## Datos del emisor (ya configurados)

- **Empresa:** Destape Rápido
- **Giro:** Servicios sanitarios y arriendo de baños químicos
- **Dirección:** Maipú, Región Metropolitana
- **Teléfono:** +56 9 3647 0112
- **Web:** destaperapido.cl

Si necesitas cambiar estos datos (por ejemplo, agregar RUT), edita el diccionario `EMISOR` al inicio de `scripts/generar_cotizacion.py`.

## Precios base (editables)

| Servicio | Valor neto |
|---|---|
| 1 baño químico + limpieza semanal (mensual) | $180.000 |
| 2 baños químicos + limpieza semanal (mensual, 30% dcto 2da unidad) | $306.000 |
| Baño químico con arnés (mensual) | $200.000 |
| Adicional: limpieza 2 veces/semana | +$30.000 |
| Evento corto hasta 5 días | $100.000 |

Estos valores están documentados en `SKILL.md`. Claude los usa como referencia, pero si tú le das un valor distinto, usa ese.

## Probar el script manualmente

Si quieres probar que todo funcione sin pasar por Claude:

```bash
cd cotizaciones-destape-rapido
python scripts/generar_cotizacion.py ejemplo_config.json /tmp/prueba.pdf
open /tmp/prueba.pdf    # macOS
# o
xdg-open /tmp/prueba.pdf    # Linux
```

Si se genera el PDF correctamente, el skill está listo.

## Personalizar el skill

- **Cambiar colores:** edita las constantes `BRAND`, `BRAND_SOFT`, etc. al inicio del script.
- **Cambiar precios base:** edita la tabla en `SKILL.md`.
- **Agregar campos al cliente:** no requiere cambios; el JSON acepta cualquier par `[label, value]` en `cliente.campos`.
- **Cambiar condiciones estándar:** edita la lista `condiciones` dentro de la función `generar()` en el script.
