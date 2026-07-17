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

# Frecuencia de aseo por defecto si la entrega no especifica otra.
ASEO_DEFAULT = "Aseo semanal (cada 7 a 10 días)"


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


def fecha_legible(iso: str) -> str:
    try:
        f = date.fromisoformat(iso)
        return f"{f.day:02d} de {MESES[f.month - 1]} de {f.year}"
    except (ValueError, IndexError):
        return iso


def construir_resumen(e: dict) -> str:
    """Arma el texto plano del resumen de una entrega."""
    lineas = [f"🚚 ENTREGA — {fecha_legible(e.get('fecha', ''))}"]
    if e.get("hora"):
        lineas.append(f"🕐 Hora: {e['hora']}")
    lineas.append("")
    lineas.append(f"👤 Cliente: {e.get('cliente', '—')}")
    lineas.append(f"📍 Dirección: {e.get('direccion', '—')}")
    if e.get("maps_url"):
        # Pin exacto que mandó el cliente (plus de la dirección; clave en condominios).
        lineas.append(f"🗺️ Ubicación exacta: {e['maps_url']}")
    if e.get("telefono"):
        # Con "+" el número queda clicable en WhatsApp (llamar / abrir chat directo).
        tel = solo_digitos(e["telefono"])
        lineas.append(f"📱 Teléfono cliente: {'+' + tel if tel else e['telefono']}")
    if e.get("servicio"):
        lineas.append("")
        lineas.append(f"{icono_banos(cantidad_banos(e))} Servicio: {e['servicio']}")
    # Aseo: usa lo indicado o el valor por defecto.
    lineas.append(f"🧽 Aseo: {e.get('aseo') or ASEO_DEFAULT}")
    pago = e.get("pago") or {}
    if pago.get("monto") is not None:
        lineas.append("")
        lineas.append(f"💵 COBRAR AL CLIENTE: {clp(pago['monto'])}")
        # Desglose breve de cómo se llegó al monto (baño + extras + flete + IVA).
        if pago.get("desglose"):
            lineas.append(f"   ({pago['desglose']})")
        if pago.get("nota"):
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
            lineas.append("   ⚠️ Datos pendientes — pedírselos al cliente al coordinar "
                          "(razón social, RUT, giro, dirección).")
    # NOTA: el bloque "Qué hacer" (detalle) se omite a propósito. El repartidor ya
    # conoce el estándar (instalar, traslado incluido, dejar insumos) y el aseo ya se
    # indica arriba en su propia línea, así que listarlo de nuevo es redundante.
    # El campo "detalle" puede seguir existiendo en entregas.json, pero NO se muestra.
    if e.get("notas"):
        lineas.append("")
        lineas.append(f"📝 Notas: {e['notas']}")
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
