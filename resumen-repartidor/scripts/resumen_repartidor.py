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


def fecha_legible(iso: str) -> str:
    """'2026-07-20' -> 'Lunes 20 de julio de 2026' (el día evita errores de agenda)."""
    try:
        f = date.fromisoformat(iso)
        return f"{DIAS_SEMANA[f.weekday()]} {f.day:02d} de {MESES[f.month - 1]} de {f.year}"
    except (ValueError, IndexError):
        return iso


# Frecuencia de aseo cuando el arriendo es LARGO (mensual) y la ficha no dice otra cosa.
# En plazos cortos NO se rellena con esto (9-sep, B5/A02): un ciclo de 7 a 10 días en un
# evento de tres días es una promesa que nadie va a cumplir, el baño ya se retiró. Y si
# no se sabe cuánto dura el arriendo, se dice «pendiente», nunca la cadencia mensual.
ASEO_DEFAULT = "Incluido cada 7 a 10 días"
ASEO_SIN_DATO = "Pendiente de confirmar con la oficina"

# Datos que el conector del cliente manda DENTRO de `notas`, como «CLAVE: valor»
# separados por « · », porque el objeto entrega no tiene un campo propio para ellos.
# Acá se sacan de las Notas y se pintan en su lugar del resumen: arriba, donde el
# repartidor los necesita, y no al final mezclados con el resto.
CLAVES_NOTA = ("EQUIPO", "ACCESO", "RECIBE", "PAGA", "PAGO", "RETIRO")

# Un arriendo LARGO (mensual o más): ahí el aseo periódico corre y NO hay retiro
# pedido, sino una fecha de renovación.
RE_LARGO = re.compile(r"mensual|indefinid|permanente|\bmes(?:es)?\b", re.IGNORECASE)
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
        m = re.match(r"^([A-ZÁÉÍÓÚÑ]{4,7})\s*:\s*(.+)$", parte)
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


def construir_resumen(e: dict) -> str:
    """Arma el texto plano del resumen de una entrega.

    ORDEN (9-sep, revisión de experiencia del repartidor): primero lo que condiciona el
    día (hora tope y franja), después lo que sube al camión, dónde se instala, quién
    recibe, hasta cuándo queda puesto y recién al final la plata. Un dato que la ficha
    no trae se dice «pendiente»: nunca se rellena con el estándar.
    """
    marcas, notas_resto = separar_notas(e.get("notas", ""))
    periodo = str(e.get("periodo") or "").strip()
    largo = bool(RE_LARGO.search(f"{periodo} {notas_resto}"))
    notas_resto = _sin_repetir(notas_resto, periodo)

    lineas = [f"🚚 ENTREGA · {fecha_legible(e.get('fecha', ''))}"]
    lineas += lineas_horario(e.get("hora", ""))

    # 1 · QUÉ SUBE AL CAMIÓN. El equipamiento decidía la unidad y vivía enterrado en
    # «📝 Notas», al final del mensaje: era el peor lugar posible para ese dato.
    n = cantidad_banos(e)
    servicio = str(e.get("servicio") or "")
    extras = servicio.split(" + ", 1)[1] if " + " in servicio else ""
    piezas = [x.strip() for x in extras.split(" + ") if x.strip()]
    equipos = [x for x in piezas if not RE_SERVICIO_EXTRA.search(x)]
    servicios = [x for x in piezas if RE_SERVICIO_EXTRA.search(x)]
    carga = f"{n} baño{'s' if n != 1 else ''} químico{'s' if n != 1 else ''}"
    for x in equipos:
        carga += f" + {x}"
    carga += f" · equipo: {marcas['EQUIPO']}" if marcas.get("EQUIPO") \
        else " · equipo: pendiente de confirmar"
    lineas.append("")
    lineas.append(f"{icono_banos(n)} CARGAR: {carga}")
    if marcas.get("EQUIPO"):
        # A11: si el cliente EXIGIÓ una configuración, el despacho no puede resolverse
        # «según stock». Se vende una cosa y se entrega esa, o se avisa antes de salir.
        lineas.append("   Esa configuración es la acordada: si no hay, avisar antes de salir.")

    # 2 · DÓNDE se instala (con la comuna, que antes no se imprimía nunca) y cómo se entra.
    direccion = str(e.get("direccion") or "—")
    comuna = str(e.get("comuna") or "").strip()
    if comuna and comuna.lower() not in direccion.lower():
        direccion = f"{direccion}, {comuna}"
    lineas.append(f"📍 Instalación: {direccion}")
    if e.get("maps_url"):
        # Pin exacto que mandó el cliente (plus de la dirección; clave en condominios).
        lineas.append(f"🗺️ Ubicación exacta: {e['maps_url']}")
    lineas.append(f"🚪 Acceso: {marcas['ACCESO']}" if marcas.get("ACCESO")
                  else "🚪 Acceso: pendiente de coordinar con quien recibe")

    # 3 · QUIÉN. Quien recibe en terreno y quien paga pueden ser personas distintas.
    lineas.append("")
    lineas.append(f"👤 Cliente: {e.get('cliente', '—')}")
    if e.get("telefono"):
        # Con "+" el número queda clicable en WhatsApp (llamar / abrir chat directo).
        tel = solo_digitos(e["telefono"])
        lineas.append(f"📱 Teléfono cliente: {'+' + tel if tel else e['telefono']}")
    lineas.append(f"🙋 Recibe en terreno: {marcas['RECIBE']}" if marcas.get("RECIBE")
                  else "🙋 Recibe en terreno: el cliente (no se indicó a otra persona)")
    if e.get("telefono_respaldo") or e.get("contacto_respaldo"):
        # Contacto de respaldo opcional (jefe, portería): a quién llamar si no contesta.
        rtel = solo_digitos(e.get("telefono_respaldo", ""))
        partes = [p for p in [e.get("contacto_respaldo"), ("+" + rtel if rtel else "")] if p]
        lineas.append(f"☎️ Respaldo: {' '.join(partes)}")

    # 4 · HASTA CUÁNDO queda puesto. Fin del uso, retiro acordado y renovación son tres
    # cosas distintas (A18): la fecha de fin sale de la duración que dijo el cliente, y
    # eso NO es un retiro coordinado. En mensual no hay retiro, hay renovación.
    retiro_f = str((e.get("retiro") or {}).get("fecha") or "").strip()
    # La nota del retiro de las entregas escritas a mano («Fin del primer mes, renovable
    # si la obra sigue») explica el plazo: se conserva. La del flujo del bot es la propia
    # duración, y repetirla al lado de «Uso» no aporta.
    retiro_nota = str((e.get("retiro") or {}).get("nota") or "").strip()
    if _clave(retiro_nota) in (_clave(periodo), ""):
        retiro_nota = ""
    lineas.append("")
    if largo:
        lineas.append(f"⏳ Uso: {periodo or 'arriendo mensual'}")
        # sin fecha de fin, la renovación se cuenta desde la entrega con los meses del
        # plazo: es aritmética sobre lo que dijo el cliente, y se dice de dónde sale
        m_meses = re.search(r"(\d+)\s*mes", periodo, re.IGNORECASE)
        meses = int(m_meses.group(1)) if m_meses else 1
        renov = retiro_f or _mas_meses(str(e.get("fecha") or ""), meses)
        lineas.append(
            f"🔁 Renovación: {fecha_legible(renov)}"
            + ("" if retiro_f else f" ({meses} mes{'es' if meses != 1 else ''} desde la entrega)")
            if renov else "🔁 Renovación: pendiente de confirmar")
        lineas.append(f"↩️ Retiro acordado: {marcas['RETIRO']}" if marcas.get("RETIRO")
                      else "↩️ Retiro: no solicitado")
    else:
        uso = periodo or "pendiente de confirmar"
        # el fin de uso solo aporta si NO es el mismo día de la entrega («1 día» dejaba
        # «fin de uso el viernes 18» debajo de «ENTREGA · viernes 18»: ruido puro)
        if retiro_f and retiro_f != str(e.get("fecha") or ""):
            uso += f", fin de uso el {fecha_legible(retiro_f).lower()}"
        if retiro_nota:
            uso += f" · {retiro_nota}"
        lineas.append(f"⏳ Uso: {uso}")
        lineas.append(f"↩️ Retiro acordado: {marcas['RETIRO']}" if marcas.get("RETIRO")
                      else "↩️ Retiro: pendiente de coordinar")
    # Un aseo INCLUIDO ya agendado (limpiezas sin `tipo: extra`) prueba por sí solo que
    # el arriendo lleva ciclo periódico, aunque el plazo no venga escrito.
    aseo_agendado = any(isinstance(x, dict) and str(x.get("tipo") or "") != "extra"
                        for x in (e.get("limpiezas") or []))
    lineas.append("🧽 Aseo: " + str(e.get("aseo")
                  or (ASEO_DEFAULT if (largo or aseo_agendado) else ASEO_SIN_DATO)))
    # Visitas de limpieza con fecha: el repartidor las ve el día que le tocan, con su
    # valor y si ya se cobraron (así no las cobra dos veces).
    agendadas = []
    for lim in (e.get("limpiezas") or []):
        if not isinstance(lim, dict):
            continue
        etq = str(lim.get("etiqueta") or "Limpieza").strip()
        agendadas.append(etq.lower())
        detalle = [f"🧴 {etq[:1].upper()}{etq[1:]}: {fecha_legible(str(lim.get('fecha') or ''))}"]
        if lim.get("valor"):
            detalle.append(f"valor {clp(lim['valor'])}")
        if lim.get("nota"):
            detalle.append(str(lim["nota"]))
        lineas.append(" · ".join(detalle))
    # Un servicio extra SIN fecha propia igual tiene que verse, y marcado como servicio:
    # si ya salió arriba con su día agendado, no se repite.
    for extra in servicios:
        if extra.lower() not in agendadas:
            lineas.append(f"🧴 Servicio aparte (no es carga): {extra}")

    # 5 · LA PLATA, al final y diciendo a quién se le cobra y por qué período.
    pago = e.get("pago") or {}
    if pago.get("monto") is not None:
        lineas.append("")
        lineas.append(f"💵 COBRAR a {marcas['PAGA']}: {clp(pago['monto'])}" if marcas.get("PAGA")
                      else f"💵 COBRAR AL CLIENTE: {clp(pago['monto'])}")
        if periodo:
            lineas.append(f"   Corresponde a: {periodo}")
        # Desglose breve de cómo se llegó al monto (baño + extras + flete + IVA).
        if pago.get("desglose"):
            lineas.append(f"   {pago['desglose']}")
        if marcas.get("PAGO"):
            lineas.append(f"   Forma de pago: {marcas['PAGO']}")
        # La nota del pago repetía LAS MISMAS notas de abajo, palabra por palabra: se
        # imprime solo cuando de verdad dice algo distinto.
        if pago.get("nota") and str(pago["nota"]).strip() != str(e.get("notas") or "").strip():
            lineas.append(f"   ({pago['nota']})")
    factura = e.get("factura") or {}
    if factura.get("requiere") or factura.get("razon_social"):
        lineas.append("")
        lineas.append("🧾 Factura:")
        if factura.get("razon_social"):
            lineas.append(f"   Razón social: {factura['razon_social']}")
        if factura.get("rut"):
            lineas.append(f"   RUT: {factura['rut']}")
        if factura.get("giro"):
            lineas.append(f"   Giro: {factura['giro']}")
        if factura.get("direccion"):
            lineas.append(f"   Dirección: {factura['direccion']}")
        if factura.get("email"):
            lineas.append(f"   Email: {factura['email']}")
        # Si requiere factura pero aún no tenemos los datos, avisar que se los pida al cliente.
        if factura.get("requiere") and not factura.get("razon_social"):
            lineas.append("   ⚠️ Datos pendientes: pedírselos al cliente al coordinar "
                          "(razón social, RUT, giro, dirección).")
    # NOTA: el bloque "Qué hacer" (detalle) se omite a propósito. El repartidor ya
    # conoce el estándar (instalar, traslado incluido, dejar insumos) y el aseo ya se
    # indica arriba en su propia línea, así que listarlo de nuevo es redundante.
    # El campo "detalle" puede seguir existiendo en entregas.json, pero NO se muestra.
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
