#!/usr/bin/env python3
"""Genera un resumen ordenado de entrega(s) y un link de WhatsApp pre-escrito.

Lee entregas.json y arma, para la(s) entrega(s) seleccionada(s):
  - Un resumen en texto plano, ordenado, pensado para el repartidor.
  - Un link wa.me con ese resumen ya pre-cargado (solo abrir y enviar).
  - Un link de Google Maps para llegar a la dirección.

Uso:
    python scripts/resumen_repartidor.py --hoy
    python scripts/resumen_repartidor.py --fecha 2026-06-25
    python scripts/resumen_repartidor.py --id 2026-06-25-ignacio-cancino

Si no se pasa filtro, muestra todas las entregas pendientes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote

# Módulo hermano: sube la entrega a Supabase para que aparezca sola en la página
# del repartidor (sin regenerar ni publicar el HTML). Ver sync_entregas_supabase.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_entregas_supabase as sync  # noqa: E402
# El generador de la tarjeta web: comparte con este resumen la regla del aseo, para que
# el WhatsApp del repartidor y su tarjeta no digan cosas distintas del mismo arriendo.
import generar_listado as gl  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent.parent / "entregas.json"

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]



def cargar() -> dict:
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"❌ No se encontró {DATA_PATH}")
    except json.JSONDecodeError as e:
        sys.exit(f"❌ entregas.json tiene un error de formato: {e}")


def solo_digitos(telefono: str) -> str:
    """Deja solo dígitos y asegura prefijo país Chile (56) si falta."""
    d = re.sub(r"\D", "", telefono or "")
    if d.startswith("56"):
        return d
    if d.startswith("9") and len(d) == 9:  # móvil chileno sin prefijo
        return "56" + d
    return d


def clp(monto) -> str:
    """Formatea un número como pesos chilenos: 160000 -> $160.000."""
    try:
        n = int(round(float(monto)))
    except (TypeError, ValueError):
        return str(monto)
    return "$" + f"{n:,}".replace(",", ".")


def cantidad_banos(e: dict) -> int:
    """Cantidad de baños de la entrega: usa 'cantidad' o la infiere del texto del servicio."""
    c = e.get("cantidad")
    if isinstance(c, int) and c > 0:
        return c
    m = re.search(r"(\d+)\s*ba[ñn]o", e.get("servicio", ""), re.IGNORECASE)
    return int(m.group(1)) if m else 1


def icono_banos(n: int) -> str:
    """Ícono(s) de baño: 1–4 baños => esa cantidad de 🚽; más de 4 => 🚽+."""
    if n <= 0:
        n = 1
    return "🚽+" if n > 4 else "🚽" * n


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def fecha_legible(iso: str, hoy: date | None = None) -> str:
    """'2026-10-06' -> 'martes 6 de octubre' (el día de la semana evita errores de agenda).
    Simplificada el 6-oct-2026 a pedido de Alejandro («el 2026 está demás»): sin cero a la
    izquierda y el año solo cuando no es el de hoy. `hoy` se inyecta en las pruebas."""
    try:
        f = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    ref = hoy or date.today()
    anio = f" de {f.year}" if f.year != ref.year else ""
    return f"{DIAS_SEMANA[f.weekday()].lower()} {f.day} de {MESES[f.month - 1]}{anio}"


def cabecera_entrega(iso: str, hoy: date | None = None) -> str:
    """La primera línea del aviso al repartidor. Lo de HOY grita (🚨 y «HOY»), lo de mañana
    avisa, el resto solo dice el día: «🚨 ENTREGA HOY · martes 6 de octubre»,
    «🚚 ENTREGA MAÑANA · miércoles 7 de octubre», «🚚 ENTREGA · sábado 10 de octubre»."""
    ref = hoy or date.today()
    try:
        f = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return f"🚚 ENTREGA · {iso}"
    if f == ref:
        return f"🚨 ENTREGA HOY · {fecha_legible(iso, ref)}"
    if (f - ref).days == 1:
        return f"🚚 ENTREGA MAÑANA · {fecha_legible(iso, ref)}"
    return f"🚚 ENTREGA · {fecha_legible(iso, ref)}"


# Frecuencia de aseo cuando el arriendo es LARGO (mensual) y la ficha no dice otra cosa.
# En plazos cortos NO se rellena con esto (9-sep, B5/A02): un ciclo de 7 a 10 días en un
# evento de tres días es una promesa que nadie va a cumplir, el baño ya se retiró. Y si
# no se sabe cuánto dura el arriendo, se dice «pendiente», nunca la cadencia mensual.
# Los textos y la regla viven en generar_listado (`texto_aseo`) desde el 10-sep: la
# tarjeta web decía «Aseo semanal» donde el WhatsApp decía «pendiente». Una sola fuente.
ASEO_DEFAULT = gl.ASEO_LARGO
ASEO_SIN_DATO = gl.ASEO_SIN_DATO

# Datos que el conector del cliente manda DENTRO de `notas`, como «CLAVE: valor»
# separados por « · », porque el objeto entrega no tiene un campo propio para ellos.
# Acá se sacan de las Notas y se pintan en su lugar del resumen: arriba, donde el
# repartidor los necesita, y no al final mezclados con el resto.
# RESPALDO (10-oct-2026, A10): el respaldo PROPIO de la ficha cuando la segunda línea la ocupa
# quien compra (pagos y emergencia); ver «3 · QUIÉN» en construir_resumen.
CLAVES_NOTA = ("EQUIPO", "ACCESO", "RECIBE", "PAGA", "PAGO", "RETIRO", "RESPALDO")

# Un arriendo LARGO (mensual o más): ahí el aseo periódico corre y NO hay retiro
# pedido, sino una fecha de renovación.
# «Medio mes» es una quincena, no un mes (5-oct-2026): misma regla que generar_listado.
RE_LARGO = re.compile(r"mensual|indefinid|permanente|(?<!medi[oa] )\bmes(?:es)?\b", re.IGNORECASE)
RE_HORA_EXACTA = re.compile(r"^\d{1,2}[:.]\d{2}$")
# Un extra que es SERVICIO (se hace) y no EQUIPO (se sube al camión). «CARGAR: 1 baño +
# limpieza extra» hacía que el repartidor buscara una limpieza en la bodega.
RE_SERVICIO_EXTRA = re.compile(r"limpieza|aseo|mantenci|recambio|retiro|traslado|flete",
                               re.IGNORECASE)


def _mas_meses(iso: str, meses: int) -> str:
    """Misma fecha, `meses` más adelante (para la renovación de un arriendo mensual)."""
    try:
        f = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return ""
    total = f.month - 1 + meses
    anio, mes = f.year + total // 12, total % 12 + 1
    dia = f.day
    while dia > 28:
        try:
            return date(anio, mes, dia).isoformat()
        except ValueError:
            dia -= 1
    return date(anio, mes, dia).isoformat()


def separar_notas(notas) -> tuple[dict, str]:
    """Parte las notas en {CLAVE: valor} conocidas y el resto en texto."""
    marcas: dict[str, str] = {}
    resto: list[str] = []
    for parte in [p.strip() for p in str(notas or "").split("·")]:
        if not parte:
            continue
        m = re.match(r"^([A-ZÁÉÍÓÚÑ]{4,8})\s*:\s*(.+)$", parte)
        if m is not None and m.group(1) in CLAVES_NOTA:
            marcas.setdefault(m.group(1), m.group(2).strip())
        else:
            resto.append(parte)
    return marcas, " · ".join(resto)


def _clave(texto: str) -> str:
    """Misma frase escrita distinto = la misma frase, para comparar.

    `periodo` lo REESCRIBE integracion.js («1 dia» → «1 día»), mientras las notas y la
    nota del retiro conservan lo que tecleó el dueño. Comparando literal, «1 dia» no
    coincidía con «1 día» y la duración salía DOS veces («⏳ Uso: 1 día · 1 dia» más
    «📝 Notas: 1 dia»). Se compara sin tildes, sin mayúsculas y sin espacios de más.
    """
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _sin_repetir(notas_resto: str, periodo: str) -> str:
    """Saca de las Notas lo que ya se dijo en «⏳ Uso» (la duración venía duplicada)."""
    ref = _clave(periodo)
    partes = [p for p in [x.strip() for x in notas_resto.split(" · ")] if p]
    return " · ".join(p for p in partes if _clave(p) != ref)


def lineas_horario(hora) -> list[str]:
    """Franja solicitada, hora tope y hora confirmada son TRES cosas distintas.

    Antes «entre 10 y 12» se despachaba como «🕐 Hora: 10:00» y «antes de las 9:30»
    perdía el «antes» (A17): una preferencia se volvía una cita, y un límite se volvía
    una cita más tarde de lo que el cliente aguantaba. Acá cada concepto lleva su
    propia línea, con el texto TAL CUAL lo dijo el cliente.
    """
    partes = [p.strip() for p in str(hora or "").split("·") if p.strip()]
    if not partes:
        return ["🕐 Horario: pendiente de coordinar"]
    topes, exactas, franjas = [], [], []
    for p in partes:
        pl = p.lower()
        if "antes de" in pl or "más tardar" in pl or "mas tardar" in pl or "tope" in pl:
            topes.append(p)
        elif RE_HORA_EXACTA.match(p):
            exactas.append(p)
        else:
            franjas.append(p)
    lineas = [f"⏰ INSTALAR {t}" for t in topes]
    lineas += [f"🕐 Franja solicitada: {f}" for f in franjas]
    lineas += [f"🕐 Hora confirmada: {x}" for x in exactas]
    return lineas


RE_NUMERO_PLAZO = re.compile(r"\d|\b(?:un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|"
                             r"veinte|treinta|medi[oa])\b", re.IGNORECASE)


def lineas_retiro(e: dict, periodo: str, largo: bool, marcas: dict) -> list[str]:
    """CUÁNDO SE RETIRA (o se renueva), en UNA línea que el repartidor pueda agendar (22-oct-2026, caso real p-573).

    Antes salían tres líneas que se contradecían: «⏳ Uso: evento · ↩️ Retiro: pendiente de coordinar · 🧽 Aseo: Sin
    aseo programado (1 día)», o «Uso: 3 días, fin de uso el martes 20» con «Retiro: pendiente de coordinar» justo
    abajo. Ahora: un retiro ACORDADO manda; si no, el día en que termina el uso (la fecha que integracion.js saca de
    los días que dijo el cliente, nunca una cuenta propia sobre un plazo ambiguo) con la hora por coordinar; si no
    dijo cuántos días, se dice eso. Un mensual no tiene retiro: tiene renovación.
    """
    retiro_f = str((e.get("retiro") or {}).get("fecha") or "").strip()
    retiro_nota = str((e.get("retiro") or {}).get("nota") or "").strip()
    if _clave(retiro_nota) in (_clave(periodo), ""):
        retiro_nota = ""
    nota = f" · {retiro_nota}" if retiro_nota else ""
    acordado = marcas.get("RETIRO", "")
    if largo:
        lineas = [f"⏳ Uso: {periodo or 'arriendo mensual'}{nota}"]
        # sin fecha de fin, la renovación se cuenta desde la entrega con los meses del plazo: es aritmética sobre
        # lo que dijo el cliente, y se dice de dónde sale
        m_meses = re.search(r"(\d+)\s*mes", periodo, re.IGNORECASE)
        meses = int(m_meses.group(1)) if m_meses else 1
        renov = retiro_f or _mas_meses(str(e.get("fecha") or ""), meses)
        if renov:
            lineas.append(f"🔁 Renovación: {fecha_legible(renov)}"
                          + ("" if retiro_f else f" ({meses} mes{'es' if meses != 1 else ''} desde la entrega)"))
        if acordado:
            lineas.append(f"↩️ Retiro acordado: {acordado}")
        return lineas
    if acordado:
        return [f"↩️ Retiro acordado: {acordado}" + (f" ({periodo})" if periodo else "") + nota]
    if retiro_f:
        cuando = ("el mismo día de la entrega" if retiro_f == str(e.get("fecha") or "")
                  else f"el {fecha_legible(retiro_f)}")
        return [f"↩️ Retiro: termina el uso {cuando} ({periodo or 'plazo de la ficha'}), "
                "coordinar la hora con quien recibe" + nota]
    if periodo and not RE_NUMERO_PLAZO.search(periodo):
        return [f"↩️ Retiro: por coordinar, el cliente no dijo cuántos días (plazo: {periodo})" + nota]
    if periodo:
        return [f"↩️ Retiro: por coordinar con el cliente (plazo: {periodo})" + nota]
    return ["↩️ Retiro: por coordinar, la ficha no trae el plazo"]


def construir_resumen(e: dict) -> str:
    """Arma el texto plano del resumen de una entrega.

    ORDEN (22-oct-2026, caso real p-573: el dueño lo leyó «desordenado»): lo que el repartidor necesita, en el
    orden en que lo usa. Qué subir al camión, dónde va, cuándo se entrega, cuándo se retira, a quién se le entrega y
    su teléfono, y al final cuánto se cobra y cómo. Lo que no se sabe no ocupa una línea «pendiente»: se dice una
    vez, donde importa (la hora junto a la entrega, los días junto al retiro). Nunca se rellena con el estándar.
    """
    marcas, notas_resto = separar_notas(e.get("notas", ""))
    periodo = str(e.get("periodo") or "").strip()
    largo = bool(RE_LARGO.search(f"{periodo} {notas_resto}"))
    notas_resto = _sin_repetir(notas_resto, periodo)

    lineas = [cabecera_entrega(e.get('fecha', ''))]

    # 1 · QUÉ SUBE AL CAMIÓN. El equipamiento decide la unidad: va arriba, nunca enterrado en «📝 Notas».
    n = cantidad_banos(e)
    servicio = str(e.get("servicio") or "")
    extras = servicio.split(" + ", 1)[1] if " + " in servicio else ""
    piezas = [x.strip() for x in extras.split(" + ") if x.strip()]
    equipos = [x for x in piezas if not RE_SERVICIO_EXTRA.search(x)]
    servicios = [x for x in piezas if RE_SERVICIO_EXTRA.search(x)]
    carga = f"{n} baño{'s' if n != 1 else ''} químico{'s' if n != 1 else ''}"
    for x in equipos:
        carga += f" + {x}"
    # sin acuerdo especial va la unidad estándar del tarifario (con lavamanos adentro)
    carga += f" · equipo: {marcas['EQUIPO']}" if marcas.get("EQUIPO") \
        else " · equipo: estándar con lavamanos"
    lineas.append("")
    lineas.append(f"{icono_banos(n)} CARGAR: {carga}")
    if marcas.get("EQUIPO"):
        # A11: si el cliente EXIGIÓ una configuración, el despacho no puede resolverse «según stock».
        lineas.append("   Esa configuración es la acordada: si no hay, avisar antes de salir.")
    agendadas = {str(lim.get("etiqueta") or "Limpieza").strip().lower()
                 for lim in (e.get("limpiezas") or []) if isinstance(lim, dict)}
    for extra in servicios:
        if extra.lower() not in agendadas:          # la que tiene su día sale abajo, con su fecha
            lineas.append(f"🧴 Servicio aparte (no es carga): {extra}")

    # 2 · DÓNDE se instala (con la comuna) y cómo se entra, si se sabe.
    direccion = str(e.get("direccion") or "").strip()
    comuna = str(e.get("comuna") or "").strip()
    if direccion and comuna and comuna.lower() not in direccion.lower():
        direccion = f"{direccion}, {comuna}"
    elif not direccion:
        # SIN CALLE, PERO CON PIN (10-sep): el cliente mandó su ubicación y nunca dictó la calle
        direccion = (f"{comuna} — sin calle: el cliente mandó el pin del mapa (abajo)"
                     if e.get("maps_url") else (comuna or "—"))
    lineas.append(f"📍 Instalación: {direccion}")
    if e.get("maps_url"):
        lineas.append(f"🗺️ Ubicación exacta: {e['maps_url']}")
    if marcas.get("ACCESO"):
        lineas.append(f"🚪 Acceso: {marcas['ACCESO']}")

    # 3 · CUÁNDO se entrega (el día ya va en la cabecera): franja, tope y hora confirmada son TRES cosas (A17);
    # sin ninguna, la hora se coordina con quien recibe.
    horario = lineas_horario(e.get("hora", ""))
    if horario == ["🕐 Horario: pendiente de coordinar"]:
        horario = ["🕐 Hora: a coordinar con quien recibe"]
    lineas += horario

    # 4 · CUÁNDO se retira (o se renueva) y el aseo que corresponde a ese plazo.
    lineas += lineas_retiro(e, periodo, largo, marcas)
    # la regla del aseo es la MISMA de la tarjeta web (generar_listado.texto_aseo)
    lineas.append(f"🧽 Aseo: {gl.texto_aseo(e)}")
    for lim in (e.get("limpiezas") or []):
        if not isinstance(lim, dict):
            continue
        etq = str(lim.get("etiqueta") or "Limpieza").strip()
        detalle = [f"🧴 {etq[:1].upper()}{etq[1:]}: {fecha_legible(str(lim.get('fecha') or ''))}"]
        if lim.get("valor"):
            detalle.append(f"valor {clp(lim['valor'])}")
        if lim.get("nota"):
            detalle.append(str(lim["nota"]))
        lineas.append(" · ".join(detalle))

    # 5 · QUIÉN. DOS TELÉFONOS, NUNCA EL MISMO DOS VECES (A10, 10-oct-2026, caso p-407): el 📱 es el de TERRENO
    # (así lo manda el conector); quien compra va en el respaldo con su etiqueta y sale en su línea.
    lineas.append("")
    tel_principal = solo_digitos(e.get("telefono") or "")
    comprador = gl.comprador_en_respaldo(e)
    rtel = solo_digitos(e.get("telefono_respaldo") or "")
    if rtel and rtel[-8:] == tel_principal[-8:]:
        rtel = ""
    lineas.append(f"👤 Cliente: {e.get('cliente', '—')}")
    if e.get("telefono"):
        etq_tel = "Teléfono en terreno" if comprador else "Teléfono cliente"
        lineas.append(f"📱 {etq_tel}: {'+' + tel_principal if tel_principal else e['telefono']}")
    recibe = gl.sin_el_numero(marcas.get("RECIBE", ""), tel_principal)
    lineas.append(f"🙋 Recibe en terreno: {recibe}" if recibe
                  else "🙋 Recibe en terreno: el cliente (no se indicó a otra persona)")
    if e.get("telefono_respaldo") or e.get("contacto_respaldo"):
        if comprador:
            partes = [p for p in [comprador[0], ("+" + rtel if rtel else "")] if p]
            lineas.append(f"💳 {comprador[1]}: {' '.join(partes)}")
        else:
            partes = [p for p in [e.get("contacto_respaldo"), ("+" + rtel if rtel else "")] if p]
            if partes:
                lineas.append(f"☎️ Respaldo: {' '.join(partes)}")
    if marcas.get("RESPALDO"):
        propio = gl.sin_el_numero(marcas["RESPALDO"], tel_principal, rtel)
        if propio:
            lineas.append(f"☎️ Respaldo: {propio}")

    # 6 · LA PLATA, al final: a quién se le cobra, cuánto, si trae IVA y cómo se paga.
    pago = e.get("pago") or {}
    factura = e.get("factura") or {}
    datos_factura = any(factura.get(k) for k in ("razon_social", "rut", "giro", "direccion", "email"))
    if pago.get("monto") is not None:
        lineas.append("")
        condicion, detalle_cobro = gl.lineas_cobro(e)
        cobro = clp(pago["monto"]) + (f" ({condicion})" if condicion else "")
        paga = gl.sin_el_numero(marcas.get("PAGA", ""), tel_principal, rtel)
        lineas.append(f"💵 COBRAR a {paga}: {cobro}" if paga
                      else f"💵 COBRAR AL CLIENTE: {cobro}")
        # en varios meses el monto es el de CADA mes (F6), con el MISMO número de meses que la confirmación
        meses = gl.meses_del_cobro(e)
        if meses >= 2:
            lineas.append(f"   Corresponde a: 1.er mes (de {meses}) · se cobra mes a mes")
        for linea in detalle_cobro:
            lineas.append(f"   {linea}")
        if marcas.get("PAGO"):
            lineas.append(f"   Forma de pago: {marcas['PAGO']}")
        if pago.get("nota") and str(pago["nota"]).strip() != str(e.get("notas") or "").strip():
            lineas.append(f"   ({pago['nota']})")
        # (22-oct-2026, p-573) el IVA va porque es lo normal, pero nadie pidió factura: una línea, no un bloque
        if factura.get("requiere") and factura.get("pedida") is False and not datos_factura:
            lineas.append("   Si pide factura: pedirle razón social, RUT, giro y dirección.")
    if datos_factura or (factura.get("requiere") and factura.get("pedida") is not False):
        lineas.append("")
        lineas.append("🧾 Factura:")
        for etq, clave in (("Razón social", "razon_social"), ("RUT", "rut"), ("Giro", "giro"),
                           ("Dirección", "direccion"), ("Email", "email")):
            if factura.get(clave):
                lineas.append(f"   {etq}: {factura[clave]}")
        if not factura.get("razon_social"):
            lineas.append("   ⚠️ Datos pendientes: pedírselos al cliente al coordinar "
                          "(razón social, RUT, giro, dirección).")
    if notas_resto:
        lineas.append("")
        lineas.append(f"📝 Notas: {notas_resto}")
    return "\n".join(lineas)


def link_whatsapp(numero_repartidor: str, texto: str) -> str:
    """Link wa.me con el texto pre-cargado.

    Si hay número del repartidor, va dirigido a él; si no, link sin número
    (WhatsApp deja elegir el contacto al abrir).
    """
    num = solo_digitos(numero_repartidor)
    base = f"https://wa.me/{num}" if num else "https://wa.me/"
    return f"{base}?text={quote(texto)}"


def link_maps(direccion: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote(direccion)}"


def abrir_whatsapp(numero_repartidor: str, texto: str) -> bool:
    """Abre WhatsApp con el mensaje ya escrito (solo falta presionar enviar).

    En macOS usa la app de WhatsApp si está instalada (apertura directa);
    si no, abre wa.me en el navegador. Devuelve True si lanzó la apertura.
    """
    import os
    import subprocess
    import sys

    num = solo_digitos(numero_repartidor)
    web_url = link_whatsapp(numero_repartidor, texto)
    app_url = f"whatsapp://send?phone={num}&text={quote(texto)}" if num else web_url

    try:
        if sys.platform == "darwin":
            destino = app_url if (num and os.path.isdir("/Applications/WhatsApp.app")) else web_url
            subprocess.run(["open", destino], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", web_url], check=False)
        else:  # windows
            os.startfile(web_url)  # type: ignore[attr-defined]
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   ↳ no se pudo abrir automáticamente: {e}")
        return False


def enviar_whatsapp(numero_repartidor: str, texto: str, espera: float = 4.0) -> bool:
    """Abre WhatsApp con el mensaje y presiona ENVIAR automáticamente (solo macOS).

    Requiere WhatsApp Desktop y permiso de Accesibilidad para el terminal.
    Si no es macOS o falta el número, hace fallback a solo abrir.
    """
    import subprocess
    import sys
    import time

    num = solo_digitos(numero_repartidor)
    if sys.platform != "darwin" or not num:
        return abrir_whatsapp(numero_repartidor, texto)

    app_url = f"whatsapp://send?phone={num}&text={quote(texto)}"
    subprocess.run(["open", app_url], check=False)
    time.sleep(espera)  # esperar a que cargue el chat y el texto

    # Activar WhatsApp y presionar Return (key code 36) para enviar.
    script = (
        'tell application "WhatsApp" to activate\n'
        'delay 0.6\n'
        'tell application "System Events" to key code 36'
    )
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        print("   ↳ no se pudo enviar automáticamente "
              f"(¿falta permiso de Accesibilidad?): {res.stderr.strip()}")
        return False
    return True


def seleccionar(data: dict, args) -> list:
    entregas = data.get("entregas", [])
    if args.id:
        sel = [e for e in entregas if e.get("id") == args.id]
        if not sel:
            sys.exit(f"❌ No se encontró ninguna entrega con id '{args.id}'.")
        return sel
    if args.fecha:
        return [e for e in entregas if e.get("fecha") == args.fecha]
    if args.hoy:
        hoy = date.today().isoformat()
        return [e for e in entregas if e.get("fecha") == hoy]
    # Por defecto: pendientes (incluye 'en-camino').
    return [e for e in entregas if e.get("estado", "pendiente") != "entregado"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumen de entregas + link de WhatsApp.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--id", help="ID exacto de una entrega.")
    grupo.add_argument("--fecha", help="Fecha en formato AAAA-MM-DD.")
    grupo.add_argument("--hoy", action="store_true", help="Entregas de hoy.")
    parser.add_argument("--abrir", action="store_true",
                        help="Abre WhatsApp con el mensaje listo (tú presionas enviar).")
    parser.add_argument("--enviar", action="store_true",
                        help="Abre WhatsApp y ENVÍA solo (presiona Enter automáticamente). macOS.")
    args = parser.parse_args()

    data = cargar()
    repartidor = data.get("repartidor", {})
    seleccion = seleccionar(data, args)

    if not seleccion:
        print("No hay entregas que coincidan con el filtro.")
        return

    for i, e in enumerate(seleccion, start=1):
        resumen = construir_resumen(e)
        wa = link_whatsapp(repartidor.get("telefono", ""), resumen)
        maps = link_maps(e.get("direccion", ""))

        print("=" * 56)
        print(resumen)
        print("-" * 56)
        print(f"🗺️  Mapa para llegar:\n{maps}")
        print()
        destino = repartidor.get("nombre") or "el repartidor"
        if args.enviar:
            if enviar_whatsapp(repartidor.get("telefono", ""), resumen):
                print(f"💬 ✅ Mensaje ENVIADO a {destino} por WhatsApp (automático).")
            else:
                print(f"💬 No se pudo enviar solo. Link para enviar manual:\n{wa}")
        elif args.abrir:
            if abrir_whatsapp(repartidor.get("telefono", ""), resumen):
                print(f"💬 ✅ Abriendo WhatsApp para enviar a {destino} — solo presiona ENVIAR.")
            else:
                print(f"💬 Enviar a {destino} por WhatsApp:\n{wa}")
        else:
            print(f"💬 Enviar a {destino} por WhatsApp (link pre-escrito):\n{wa}")
        # Al confirmar la entrega al repartidor (enviar/abrir), súbela a Supabase:
        # aparece sola en la página (más reciente arriba), sin regenerar ni publicar.
        if args.enviar or args.abrir:
            if sync.upsert_entrega(e):
                print("🗂️  Entrega publicada en Supabase → aparece sola en la página del repartidor.")
            else:
                print("⚠️  No se pudo subir a Supabase (el WhatsApp sí se envió). "
                      "Corre sync_entregas_supabase.py o revisa la conexión.")
        print("=" * 56)
        if i < len(seleccion):
            print()


if __name__ == "__main__":
    main()
