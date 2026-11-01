#!/usr/bin/env python3
"""Genera la AGENDA DE DESTAPES (destapes.html): página mobile-first del área de
camión, hidrojet y cámara de Destape Rápido. Gemela de la de baños pero separada:
lee y escribe SOLO las tablas `destape` y `destape_estado` de Supabase.

- `tarjeta(d)` arma la tarjeta de un destape (la reutiliza subir_destape.py para el
  `card_html`, igual que en baños: el template no se porta a JS).
- La página, al cargar, pide las filas vivas a Supabase. Mientras tanto muestra un
  esqueleto. Si Supabase no contesta usa el caché de la última visita y, si tampoco
  hay, el respaldo horneado acá (las filas que había al generar).
- El porcentaje de Destape Rápido sale de un solo lugar:
  DIXDY/clientes/destaperapido/conexiones/avisar-destape.json → comision_por_destino.
- Montos en la página con el formato de plata de siempre ("$140.000"). El campo del valor
  final acepta "140", "140 mil", "140.000" o "$140.000" y lo muestra como "$140.000".
  ("140 mil" es solo para lo que el bot le escribe al cliente por WhatsApp, no para acá.)
- Cobrar = botón "Cobrado" → "¿Cuánto se cobró?" → guarda valor_final y estado cobrado
  juntos. La comisión sale de ese valor final.

Uso:
    python3 resumen-destapes/scripts/generar_destapes.py            # escribe ../destapes.html
    python3 resumen-destapes/scripts/generar_destapes.py --sin-red  # sin hornear respaldo
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent              # resumen-destapes/
REPO = BASE.parent                                         # cotizaciones-destape-rapido/
SALIDA = BASE / "destapes.html"

# URL + anon key + datos bancarios + WhatsApp de aviso: la MISMA fuente que baños
# (generar_listado.py), para no tener dos copias de la llave.
sys.path.insert(0, str(REPO / "resumen-repartidor" / "scripts"))
import generar_listado as gl  # noqa: E402

SUPABASE_URL = gl.SUPABASE_URL
SUPABASE_ANON_KEY = gl.SUPABASE_ANON_KEY

# El número del equipo que tiene esta página (Benjamín Chávez, Alcantarillados Chávez).
DESTINO_PAGINA = "56965889226"
PCT_RESPALDO = 25
AVISAR_DESTAPE_JSON = Path(os.environ.get("AVISAR_DESTAPE_JSON") or (
    REPO.parent.parent / "DIXDY" / "clientes" / "destaperapido" / "conexiones" / "avisar-destape.json"))

ICONO_SERVICIO = {
    "destape-hydrojet": "💦",
    "destape-camion": "🚛",
    "video-inspeccion": "📹",
    "succion-fosa": "🚛",
    "destape-domiciliario": "🔧",
    "destape-vertical": "🏢",
}


def hora_limpia(h) -> str:
    """La hora o franja como la ve el equipo. El conector marca la urgencia como «HOY, lo antes posible — URGENTE»
    (conexiones.json, hora_urgente): la raya larga no se muestra (ley de textos) y la urgencia queda como ⚡ Urgente."""
    t = re.sub(r"\s*[—–-]\s*URGENTE\b", " ⚡ Urgente", str(h or ""), flags=re.I)
    return re.sub(r"[.,;\s—–-]+$", "", t).strip()


def config_avisos() -> dict:
    try:
        return json.loads(AVISAR_DESTAPE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pct_comision(destino: str = DESTINO_PAGINA) -> int:
    """Porcentaje de Destape Rápido para ese número del equipo (un solo lugar)."""
    try:
        return int(config_avisos().get("comision_por_destino", {}).get(destino) or PCT_RESPALDO)
    except (TypeError, ValueError):
        return PCT_RESPALDO


esc = gl.esc
clp = gl.clp  # $160.000


def con_factura(factura) -> bool | None:
    """¿Pidió factura? True = sí ("si", "sí", "si, con factura", "con factura"),
    False = no ("no", "sin factura", "boleta"), None = no se sabe ("").
    OJO: "sin factura" empieza con "si", por eso se mira la palabra entera."""
    t = str(factura if factura is not None else "").strip().lower().replace("í", "i")
    if not t:
        return None
    if re.match(r"(sin|no|boleta|false)\b", t):
        return False
    if re.match(r"(si|true)\b", t) or t.startswith("con factura") or t == "factura":
        return True
    return None


def iva_txt(factura) -> str:
    """El valor es NETO. Regla del dueño: si pide factura se suma el IVA (19 %)."""
    fac = con_factura(factura)
    if fac is True:
        return "Con factura: + IVA"
    if fac is False:
        return "Sin factura"
    return "Si pide factura se suma el IVA"


def solo_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def tel_bonito(d: str) -> str:
    d = solo_digitos(d)
    if len(d) == 11 and d.startswith("569"):
        return f"+56 9 {d[3:7]} {d[7:]}"
    return f"+{d}" if d else ""


def maps_de(d: dict) -> str:
    if d.get("maps_url"):
        return str(d["maps_url"])
    q = ", ".join(x for x in (d.get("direccion"), d.get("comuna")) if x)
    return "https://maps.google.com/?q=" + urllib.parse.quote(q) if q else ""


def direccion_html(d: dict) -> str:
    dire = str(d.get("direccion") or "").strip()
    comuna = str(d.get("comuna") or "").strip()
    if not dire and not comuna:
        return '<span class="dc-falta">Falta la dirección. Pídesela al cliente.</span>'
    if comuna and comuna.lower() not in dire.lower():
        return f"<b>{esc(dire)}</b>, {esc(comuna)}" if dire else f"<b>{esc(comuna)}</b>"
    return f"<b>{esc(dire)}</b>"


def tarjeta(d: dict) -> str:
    """Tarjeta de un destape (solo contenido). Los botones de estado los pone el JS."""
    servicio = d.get("servicio") or "Destape"
    icono = ICONO_SERVICIO.get(d.get("servicio_clave", ""), "🔧")
    hora = hora_limpia(d.get("hora")) or "Horario a coordinar"
    neto = int(solo_digitos(d.get("precio_neto")) or 0)
    valor = (f'<div class="dc-valor">desde <b>{esc(clp(neto))}</b>'
             f'<span class="dc-iva">{esc(iva_txt(d.get("factura")))}</span></div>'
             if neto else '<div class="dc-valor"><b>Valor a confirmar en terreno</b></div>')
    tel = solo_digitos(d.get("telefono"))
    cliente = d.get("cliente") or "Cliente sin nombre"
    mapa = maps_de(d)
    trabajo = d.get("trabajo") or ""
    extras = []
    if trabajo and trabajo.strip().lower() != servicio.strip().lower():
        extras.append(f'<div class="dc-linea">🛠️ {esc(trabajo[:1].upper() + trabajo[1:])}</div>')
    if d.get("acceso"):
        extras.append(f'<div class="dc-linea">🚪 {esc(d["acceso"])}</div>')
    if d.get("nota"):
        extras.append(f'<div class="dc-linea dc-nota">📝 {esc(d["nota"])}</div>')
    botones = []
    if tel:
        botones.append(f'<a class="dc-btn dc-wa" data-accion="wa" href="https://wa.me/{tel}" '
                       f'target="_blank" rel="noopener">{gl.WA_ICON} WhatsApp</a>')
        botones.append(f'<a class="dc-btn dc-tel" href="tel:+{tel}">📞 Llamar</a>')
    if mapa:
        botones.append(f'<a class="dc-btn dc-map" href="{esc(mapa)}" target="_blank" rel="noopener">🗺️ Mapa</a>')
    return (
        f'<article class="dc" data-id="{esc(d.get("id", ""))}">'
        f'<div class="dc-top"><span class="dc-serv">{icono} {esc(servicio)}</span>'
        f'<span class="dc-hora">🕐 {esc(hora)}</span></div>'
        f'<div class="dc-dir">📍 {direccion_html(d)}</div>'
        f'{valor}'
        f'<div class="dc-cli">👤 {esc(cliente)}{(" · " + esc(tel_bonito(tel))) if tel else ""}</div>'
        f'{"".join(extras)}'
        f'<div class="dc-acc">{"".join(botones)}</div>'
        f'</article>'
    )


def filas_vivas() -> list[dict]:
    """Las filas que hay hoy en Supabase, para hornearlas como respaldo."""
    url = (f"{SUPABASE_URL}/rest/v1/destape?select=id,fecha,informado_at,data,card_html"
           f"&eliminado=eq.false&order=informado_at.desc")
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_ANON_KEY,
                                               "Authorization": f"Bearer {SUPABASE_ANON_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError):
        return []


def estado_vivo() -> dict:
    """El estado de cada destape (cobrado, valor final...) para el respaldo horneado.
    Sin esto, sin red y sin caché los ya cobrados se verían como atrasados."""
    url = f"{SUPABASE_URL}/rest/v1/destape_estado?select=*"
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_ANON_KEY,
                                               "Authorization": f"Bearer {SUPABASE_ANON_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {f["id"]: f for f in json.loads(r.read().decode())}
    except (urllib.error.URLError, ValueError, KeyError, TypeError):
        return {}


CSS = r"""
:root { --azul:#1F5AA8; --azul-2:#163F78; --tinta:#0F172A; --gris:#64748B; --linea:#E2E8F0; --fondo:#F1F5F9;
  --card:#fff; --suave:#F8FAFC; --verde:#166534; --verde-bg:#F0FDF4; --verde-br:#BBF7D0;
  --ambar:#92400E; --ambar-bg:#FEF3C7; --ambar-br:#FCD34D; --oro:#B8860B;
  --rojo:#B91C1C; --rojo-bg:#FEF2F2; --rojo-br:#FCA5A5;
  --azul-btn:#1F5AA8; --oro-btn:#A16207; --verde-btn:#15803D;
  --tinta-2:#334155; --skel-a:#E2E8F0; --skel-b:#EDF2F7; color-scheme:light dark; }
@media (prefers-color-scheme: dark) {
  :root { --azul:#3B82F6; --azul-2:#1E3A8A; --tinta:#E5E7EB; --gris:#94A3B8; --linea:#273244; --fondo:#0B1220;
    --card:#111A2B; --suave:#0F1726; --verde:#4ADE80; --verde-bg:#0F2A1C; --verde-br:#166534;
    --ambar:#FCD34D; --ambar-bg:#3A2A06; --ambar-br:#A16207; --oro:#CA8A04;
    --rojo:#FCA5A5; --rojo-bg:#3A1212; --rojo-br:#7F1D1D;
    --azul-btn:#2563EB;
    --tinta-2:#CBD5E1; --skel-a:#1E293B; --skel-b:#273449; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
[hidden] { display:none !important; }
html, body { max-width:100%; overflow-x:hidden; }
body { margin:0; background:var(--fondo); color:var(--tinta);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:16px; line-height:1.45; padding-bottom:calc(90px + env(safe-area-inset-bottom)); }
header { position:sticky; top:0; z-index:20; background:var(--azul-2); color:#fff;
  padding:max(12px,env(safe-area-inset-top)) 16px 12px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
@media (prefers-color-scheme: light) { header { background:var(--azul); } }
header h1 { margin:0; font-size:19px; }
header .sub { margin-top:3px; font-size:14px; opacity:.92; }
.hdr-com { font-weight:700; }
header .skel { display:inline-block; vertical-align:middle; height:11px; width:70px; border-radius:6px;
  background:rgba(255,255,255,.3); }
main { max-width:560px; margin:0 auto; padding:12px 16px 30px; opacity:0; transition:opacity .25s;
  animation:velo 0s linear 10s forwards; }
main.listo { opacity:1; }
@keyframes velo { to { opacity:1; } }
body.listo #skel { display:none; }
#skel { max-width:560px; margin:0 auto; padding:12px 16px 0; }
.sk { border-radius:12px; margin-bottom:10px;
  background:linear-gradient(90deg,var(--skel-a) 25%,var(--skel-b) 45%,var(--skel-a) 65%);
  background-size:400% 100%; animation:brillo 1.3s ease-in-out infinite; }
.sk-tabs { height:48px; } .sk-tit { height:14px; width:40%; margin:16px 4px 10px; } .sk-card { height:150px; }
@keyframes brillo { 0% { background-position:100% 0; } 100% { background-position:0 0; } }
@media (prefers-reduced-motion: reduce) { .sk { animation:none; } }
.aviso-red { background:var(--ambar-bg); color:var(--ambar); border-radius:10px; padding:8px 12px; font-size:14px; margin-bottom:10px; }
.vistas { display:flex; gap:8px; }
.vista-btn { flex:1 1 0; min-height:48px; border-radius:12px; border:1px solid var(--linea); background:var(--card);
  color:var(--tinta); font:inherit; font-weight:700; font-size:16px; cursor:pointer; }
.vista-btn.activo { background:var(--azul-btn); border-color:var(--azul-btn); color:#fff; }
/* Botones para ver lo realizado y lo cobrado (como "Ver completadas" de baños) */
.filtros { display:flex; gap:8px; margin-top:10px; }
.filtro { flex:1 1 0; min-width:0; min-height:48px; border-radius:12px; border:2px solid var(--linea); background:var(--card);
  color:var(--tinta); font:inherit; font-weight:700; font-size:14.5px; line-height:1.2; cursor:pointer; padding:4px 6px; }
.filtro.activo { background:var(--azul-btn); border-color:var(--azul-btn); color:#fff; }
.filtro.alerta { border:2px solid var(--oro); background:var(--ambar-bg); color:var(--ambar); }
.espacio-fijo { height:84px; }
.volver-fijo { position:fixed; left:16px; right:16px; bottom:calc(14px + env(safe-area-inset-bottom)); max-width:528px;
  margin:0 auto; z-index:30; min-height:54px; border:none; border-radius:14px; background:var(--azul-btn); color:#fff;
  font:inherit; font-size:16px; font-weight:800; cursor:pointer; box-shadow:0 6px 18px rgba(15,23,42,.3); }
.dia-tit { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800; text-transform:uppercase;
  letter-spacing:.5px; color:var(--gris); margin:16px 0 8px; padding:6px 0; position:sticky; top:var(--hdr-h,70px);
  z-index:5; background:var(--fondo); }
.dia-tit.atrasado { color:var(--rojo); }
.dia-tit.hoy { color:var(--azul); }
.dia-n { margin-left:auto; background:var(--card); border:1px solid var(--linea); border-radius:20px; padding:1px 9px; font-size:12px; color:var(--gris); }
.dw { position:relative; background:var(--card); border:1px solid var(--linea); border-radius:16px; margin-bottom:14px;
  box-shadow:0 1px 3px rgba(15,23,42,.06); }
.dw.is-contactado { border-color:var(--verde-br); background:var(--verde-bg); }
.dw.is-atrasado { border:2px solid var(--rojo-br); }
.dw.is-realizado { border-color:#93C5FD; }
.dw.is-cobrado { border-color:var(--ambar-br); }
@media (prefers-color-scheme: dark) { .dw.is-realizado { border-color:#1E40AF; } }
.dw.foco { animation:pulso 1.3s ease-in-out 3; }
@keyframes pulso { 0%,100% { box-shadow:0 0 0 0 rgba(59,130,246,0); } 35% { box-shadow:0 0 0 6px rgba(59,130,246,.5); } }
/* NUEVO (este teléfono no lo había visto): anillo azul y chip flotante, igual que en baños */
.dw.nueva { margin-top:20px; box-shadow:0 0 0 2px #93C5FD, 0 4px 16px rgba(59,130,246,.28); }
.dw.nueva::before { content:"✨ Nuevo"; position:absolute; top:-10px; right:14px; background:#3B82F6; color:#fff;
  font-size:11px; font-weight:800; padding:2px 10px; border-radius:999px; box-shadow:0 1px 4px rgba(30,64,175,.35); z-index:2; }
.dw-top { display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:12px 14px 0; }
.hora-pill { display:inline-flex; align-items:center; gap:6px; background:var(--azul-btn); color:#fff; font-weight:800;
  font-size:17px; padding:6px 12px; border-radius:10px; font-variant-numeric:tabular-nums; letter-spacing:.2px; }
.hora-pill.sin { background:var(--ambar-bg); color:var(--ambar); font-size:15px; }
/* Ya hecho (realizado o cobrado): la hora deja de ser lo importante */
.hora-pill.hecho { background:var(--suave); color:var(--gris); border:1px solid var(--linea); font-size:15px; }
.pill-atr { display:inline-flex; align-items:center; gap:6px; background:var(--rojo-bg); color:var(--rojo);
  border:1px solid var(--rojo-br); font-weight:800; font-size:15.5px; padding:6px 12px; border-radius:10px; }
.hora-chica { font-size:15.5px; font-weight:800; color:var(--tinta-2); }
.chip { margin-left:auto; font-size:12.5px; font-weight:800; padding:4px 10px; border-radius:20px; white-space:nowrap; }
.chip.real { background:#DBEAFE; color:#1E40AF; }
.chip.cob { background:var(--ambar-bg); color:var(--ambar); }
.chip.cont { background:#DCFCE7; color:#166534; }
@media (prefers-color-scheme: dark) { .chip.real { background:#172554; color:#93C5FD; } .chip.cont { background:#052E16; color:#86EFAC; } }
.reag { margin:8px 14px 0; font-size:14px; font-weight:700; color:var(--rojo); }
.dw-body { padding:10px 14px 14px; }
.dw-serv { font-weight:800; font-size:18px; line-height:1.25; }
.dw-dir { margin-top:6px; font-size:16px; overflow-wrap:anywhere; }
.dw-cli { margin-top:4px; font-size:15px; color:var(--tinta-2); overflow-wrap:anywhere; }
.dc-falta { color:var(--rojo); font-weight:700; }
.dw-valor { margin-top:10px; display:flex; flex-wrap:wrap; align-items:baseline; gap:0 6px; background:var(--verde-bg);
  border:1px solid var(--verde-br); border-radius:12px; padding:8px 12px; color:var(--verde); font-size:16px; }
.dw-valor b { font-size:22px; font-variant-numeric:tabular-nums; }
.dw-valor .nota { flex-basis:100%; font-size:14px; opacity:.92; }
.dw-valor.cob { background:var(--ambar-bg); border-color:var(--ambar-br); color:var(--ambar); }
.falta-vf, .tag-falta { flex-basis:100%; font-weight:800; font-size:14px; color:var(--ambar); }
.tag-falta { display:inline-block; background:var(--ambar-bg); border:1px solid var(--ambar-br); border-radius:8px; padding:2px 8px; margin-bottom:4px; }
.dw-prob { margin-top:4px; color:var(--tinta); font-weight:600; }
.dw-linea { margin-top:8px; font-size:15.5px; color:var(--tinta-2); overflow-wrap:anywhere; }
.dw-linea.nota-imp { color:var(--ambar); background:var(--ambar-bg); border-radius:10px; padding:8px 10px; font-weight:600; }
.btn-contacto { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; margin-top:12px; min-height:52px;
  border:none; border-radius:12px; background:var(--verde-btn); color:#fff; font:inherit; font-size:16px; font-weight:800; cursor:pointer; }
.btn-contacto:active { filter:brightness(.95); }
.accesos { display:flex; gap:8px; margin-top:8px; }
.acc { flex:1 1 0; display:flex; align-items:center; justify-content:center; gap:6px; min-height:48px; border-radius:12px;
  text-decoration:none; font-weight:700; font-size:15px; }
.acc-wa { background:var(--verde-btn); color:#fff; } .acc-map { background:var(--azul-btn); color:#fff; }
.acc-tel { background:var(--card); color:var(--tinta); border:2px solid var(--gris); }
.acc.suave { background:var(--card); color:var(--tinta); border:2px solid var(--linea); }
.acc:active { filter:brightness(.92); }
.est-row { display:flex; gap:8px; margin-top:12px; }
.est-btn { flex:1 1 0; min-height:54px; border-radius:12px; font:inherit; font-weight:800; font-size:16px; cursor:pointer;
  border:2px solid var(--linea); background:var(--card); color:var(--tinta); }
.est-btn.b-real { border-color:var(--gris); font-size:15px; line-height:1.2; padding:4px 8px; }
.est-btn.b-cob { background:var(--oro-btn); border-color:var(--oro-btn); color:#fff; font-size:17px; }
.est-btn.b-real.on { background:#1E40AF; border-color:#1E40AF; color:#fff; }
.dw.is-realizado .est-btn.b-cob, .est-btn.b-cob.fuerte { background:var(--oro-btn); border-color:var(--oro-btn); color:#fff; }
.est-btn.b-corr { border-color:var(--ambar-br); }
.est-btn.b-corr.fuerte, .com-btn.fuerte { background:var(--oro-btn); border-color:var(--oro-btn); color:#fff; }
/* Cobro: "¿Cuánto se cobró?" con el valor ya puesto */
.cobro { margin-top:12px; background:var(--ambar-bg); border:2px solid var(--oro); border-radius:14px; padding:14px;
  display:grid; gap:10px; }
.cobro-lbl { display:grid; gap:6px; font-weight:800; font-size:18px; color:var(--tinta); }
.cobro-lbl small { font-size:15px; font-weight:700; color:var(--tinta); }
.cobro-in { font:inherit; font-size:26px; font-weight:800; min-height:58px; width:100%; border-radius:12px;
  border:2px solid var(--linea); background:var(--card); color:var(--tinta); padding:6px 14px; font-variant-numeric:tabular-nums; }
.cobro-in:focus { outline:none; border-color:var(--oro); box-shadow:0 0 0 3px rgba(202,138,4,.3); }
.cobro-calc { font-size:15.5px; color:var(--tinta); }
.cobro-calc b { white-space:nowrap; }
.cobro-ok { min-height:56px; border:none; border-radius:12px; background:var(--verde-btn); color:#fff; font:inherit;
  font-size:18px; font-weight:800; cursor:pointer; }
.cobro-ok:disabled { background:var(--linea); color:var(--gris); }
.cobro-no { min-height:50px; border-radius:12px; border:2px solid var(--linea); background:var(--card); color:var(--tinta);
  font:inherit; font-size:16px; font-weight:700; cursor:pointer; }
/* La acción que deshace va lejos de Cancelar y pide confirmación */
.cobro-sacar { margin-top:10px; padding-top:8px; border-top:1px dashed var(--ambar-br); }
.sacar { background:none; border:none; padding:10px 0; min-height:44px; font:inherit; font-size:15px; font-weight:700;
  color:var(--rojo); cursor:pointer; text-align:left; }
.dw-mas { margin-top:12px; border-top:1px dashed var(--linea); padding-top:2px; }
.dw-mas > summary { list-style:none; cursor:pointer; color:var(--azul); font-weight:700; font-size:15px; padding:10px 0; }
.dw-mas > summary::-webkit-details-marker { display:none; }
.dw-mas > summary::after { content:" ▾"; }
.dw-mas[open] > summary::after { content:" ▴"; }
.mas-cuerpo { display:grid; gap:10px; padding-bottom:2px; }
.campo { display:flex; flex-direction:column; gap:4px; font-size:14px; font-weight:700; color:var(--gris); }
.campo input { font:inherit; font-size:16px; min-height:48px; border-radius:10px; border:1px solid var(--linea);
  background:var(--suave); color:var(--tinta); padding:6px 10px; width:100%; }
.quitar { justify-self:start; background:none; border:none; color:var(--rojo); font:inherit; font-size:15px; font-weight:700;
  cursor:pointer; padding:8px 0; min-height:44px; }
.confirma { display:flex; gap:8px; align-items:center; font-size:15px; flex-wrap:wrap; background:var(--rojo-bg);
  border-radius:10px; padding:8px 10px; color:var(--rojo); }
.confirma button { min-height:44px; border-radius:9px; border:none; font:inherit; font-weight:700; padding:0 14px; cursor:pointer; }
.confirma .si { background:#DC2626; color:#fff; } .confirma .no { background:var(--card); color:var(--tinta); }
.vacio { text-align:center; color:var(--gris); padding:36px 12px; }
/* Comisión */
.com-hero { background:var(--card); border:1px solid var(--linea); border-radius:14px; padding:16px; margin-top:12px; }
.com-hero .r { font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--gris); }
.com-hero .v { font-size:36px; font-weight:800; font-variant-numeric:tabular-nums; color:var(--ambar); line-height:1.15; margin-top:2px; }
.com-hero .v.al-dia { color:var(--verde); }
.com-hero .s { font-size:14px; color:var(--gris); margin-top:4px; }
.sec-tit { font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--gris); margin:20px 0 8px; }
.com-item { display:flex; flex-wrap:wrap; gap:10px; align-items:center; background:var(--card); border:1px solid var(--linea);
  border-radius:12px; padding:12px; margin-bottom:8px; }
.com-item input[type=checkbox] { width:24px; height:24px; flex:none; accent-color:var(--azul); }
.com-txt { flex:1 1 0; min-width:0; font-size:14px; }
.com-txt b { display:block; font-size:15px; }
.com-txt span { display:block; color:var(--gris); font-size:13.5px; overflow-wrap:anywhere; }
.com-monto { font-weight:800; font-size:16px; font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--ambar); text-align:right; }
.com-monto small { display:block; font-size:11.5px; font-weight:600; color:var(--gris); }
.com-item.pagada .com-monto { color:var(--verde); }
.com-acc { flex-basis:100%; display:flex; gap:8px; }
.com-btn { flex:1 1 auto; min-height:48px; border-radius:12px; border:2px solid var(--ambar-br); background:var(--card);
  color:var(--tinta); font:inherit; font-weight:800; font-size:15px; cursor:pointer; }
.com-btn.cob { border-color:var(--oro-btn); background:var(--oro-btn); color:#fff; }
.com-item .cobro { flex-basis:100%; margin-top:0; }
.pagos { margin-top:20px; }
.pagos > summary { list-style:none; cursor:pointer; min-height:50px; display:flex; align-items:center; justify-content:center;
  border:1px dashed var(--gris); border-radius:12px; background:var(--card); color:var(--tinta); font-weight:700; font-size:15px; }
.pagos > summary::-webkit-details-marker { display:none; }
.pagos[open] > summary { margin-bottom:10px; }
.pago-grupo { background:var(--card); border:1px solid var(--verde-br); border-radius:14px; padding:10px 12px; margin-bottom:10px; }
.pago-head { display:flex; justify-content:space-between; gap:8px; font-weight:800; margin-bottom:6px; }
.pago-head span { color:var(--verde); white-space:nowrap; }
.pago-grupo .com-item { border:none; padding:6px 0; margin:0; background:none; }
.revocar { background:none; border:1px solid var(--linea); color:var(--gris); border-radius:8px; font:inherit; font-size:13px;
  padding:6px 10px; min-height:36px; cursor:pointer; }
.barra-pagar { position:fixed; left:0; right:0; bottom:0; z-index:30; padding:10px 16px calc(10px + env(safe-area-inset-bottom));
  background:var(--card); border-top:1px solid var(--linea); box-shadow:0 -4px 12px rgba(0,0,0,.08); }
.btn-pagar { display:block; width:100%; max-width:528px; margin:0 auto; min-height:54px; border:none; border-radius:12px;
  background:var(--verde-btn); color:#fff; font:inherit; font-size:17px; font-weight:800; cursor:pointer; }
.btn-pagar:disabled { background:var(--linea); color:var(--gris); }
.modal { position:fixed; inset:0; z-index:50; background:rgba(2,6,23,.6); display:flex; align-items:flex-end; justify-content:center; }
.modal-box { background:var(--card); color:var(--tinta); width:100%; max-width:560px; border-radius:18px 18px 0 0;
  padding:18px 16px calc(18px + env(safe-area-inset-bottom)); max-height:90vh; overflow:auto; }
.modal-box h2 { margin:0 0 6px; font-size:20px; }
.modal-box .s { color:var(--gris); font-size:14px; }
.banco { background:var(--suave); border:1px solid var(--linea); border-radius:12px; padding:12px; margin:12px 0; font-size:15px; }
.banco div { display:flex; justify-content:space-between; gap:10px; padding:3px 0; }
.banco span { color:var(--gris); }
.modal-acc { display:grid; gap:8px; margin-top:12px; }
.modal-acc button { min-height:52px; border-radius:12px; border:none; font:inherit; font-weight:800; font-size:16px; cursor:pointer; }
.m-ok { background:var(--verde-btn); color:#fff; } .m-copiar { background:var(--suave); color:var(--tinta); border:1px solid var(--linea) !important; }
.m-no { background:none; color:var(--gris); }
.toast { position:fixed; left:50%; bottom:calc(84px + env(safe-area-inset-bottom)); transform:translateX(-50%); z-index:60;
  background:#0F172A; color:#fff; padding:12px 16px; border-radius:12px; font-size:15px; width:max-content; max-width:calc(100vw - 32px);
  box-shadow:0 6px 18px rgba(0,0,0,.3); }
@media (prefers-color-scheme: dark) { .toast { background:#E5E7EB; color:#0F172A; } }
footer { text-align:center; color:var(--gris); font-size:12px; padding:20px 16px 30px; }
"""

SCRIPT = r"""
(function () {
  var APP = window.__APP__;
  var H = { apikey: APP.key, Authorization: 'Bearer ' + APP.key };
  var CK_FILAS = 'destapes_filas_v1', CK_EST = 'destapes_estado_v1', CK_VISTOS = 'destapes_vistos_v1', CK_DESEL = 'destapes_desel_v1';
  // modo: 'agenda' (por hacer), 'realizados' (falta cobrar) o 'cobrados'. Como "Ver completadas" de baños.
  var filas = [], est = {}, modo = 'agenda', vista = 'agenda', confirmando = null, primeraVez = false, vistos = {};
  var cobrando = null, borrador = {}, masAbierto = {};

  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sin espacio o modo privado */ } }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function hoyISO(delta) {
    var d = new Date(Date.now() + (delta || 0) * 864e5);
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago' }).format(d);
  }
  var DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  function diaLargo(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return 'Sin fecha';
    var p = iso.split('-'), d = new Date(+p[0], +p[1] - 1, +p[2]);
    return DIAS[d.getDay()] + ' ' + d.getDate() + ' de ' + MESES[d.getMonth()];
  }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function toast(t) {
    var el = document.getElementById('toast'); el.textContent = t; el.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(function () { el.hidden = true; }, 3500);
  }

  // ── plata ──────────────────────────────────────────────────────────────
  /** 140000 → "$140.000" (el formato de plata de siempre en la página). */
  function clp(n) { n = Math.round(Number(n) || 0); return (n < 0 ? '-$' : '$') + Math.abs(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
  /** Lee lo que escribe la persona: "140", "140 mil", "140.000", "$140.000", "17 mil 750",
   *  "140 lucas", "1,5 millones". Un número solo menor a mil se lee en miles (140 = $140.000).
   *  Devuelve 0 si no se entendió. */
  function leerMonto(txt) {
    var t = String(txt == null ? '' : txt).toLowerCase()
      .replace(/mill[oó]n(es)?/g, ' M ').replace(/mil|lucas?|k/g, ' K ').replace(/[^0-9.,\sMK]/g, ' ');
    var re = /(\d+(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)\s*([MK])?/g, m, total = 0, mult = false, alguno = false;
    while ((m = re.exec(t))) {
      var s = m[1], dec = s.match(/[.,](\d{1,2})$/), n;
      n = dec ? parseFloat(s.slice(0, -dec[0].length).replace(/[.,\s]/g, '') + '.' + dec[1]) : parseInt(s.replace(/[.,\s]/g, ''), 10);
      if (isNaN(n)) continue;
      alguno = true;
      if (m[2] === 'M') { n *= 1e6; mult = true; } else if (m[2] === 'K') { n *= 1e3; mult = true; }
      total += n;
    }
    if (!alguno) return 0;
    if (!mult && total > 0 && total < 1000) total *= 1000;
    return Math.round(total);
  }

  // ── datos ──────────────────────────────────────────────────────────────
  function E(id) { return est[id] || {}; }
  function fila(id) { for (var i = 0; i < filas.length; i++) if (filas[i].id === id) return filas[i]; return null; }
  function estadoDe(id) { return E(id).estado || 'pendiente'; }
  function fechaEf(f) { return E(f.id).fecha || f.fecha || (f.data && f.data.fecha) || ''; }
  function vivo(f) { return !E(f.id).eliminado; }
  function pctDe(f) { var p = f.data && Number(f.data.comision_pct); return p > 0 ? p : APP.pct; }
  function baseDe(f) { var v = Number(E(f.id).valor_final); return v > 0 ? v : (Number(f.data && f.data.precio_neto) || 0); }
  function comDe(f) { return Math.round(baseDe(f) * pctDe(f) / 100); }
  function atrasado(f) { var fe = fechaEf(f); return estadoDe(f.id) === 'pendiente' && !!fe && fe < hoyISO(0); }

  function pedir(ruta) {
    return fetch(APP.url + '/rest/v1/' + ruta, { headers: H }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status); return r.json();
    });
  }
  function guardar(id, cambios) {
    var cuerpo = Object.assign({ id: id }, cambios);
    return fetch(APP.url + '/rest/v1/destape_estado?on_conflict=id', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates,return=minimal' }, H),
      body: JSON.stringify(cuerpo)
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }
  // Cambio optimista: se pinta al tiro y se revierte si Supabase no lo guarda.
  function cambiar(id, cambios, okTxt) {
    var antes = Object.assign({}, E(id));
    est[id] = Object.assign({}, antes, cambios);
    lsSet(CK_EST, est); pintar();
    return guardar(id, cambios).then(function () { if (okTxt) toast(okTxt); }).catch(function () {
      est[id] = antes; lsSet(CK_EST, est); pintar();
      toast('No se pudo guardar. Revisa la señal e intenta de nuevo.');
      throw new Error('no-guardado');
    });
  }

  function cargar() {
    var aviso = document.getElementById('aviso-red');
    Promise.all([
      pedir('destape?select=id,fecha,informado_at,data,card_html&eliminado=eq.false&order=informado_at.desc'),
      pedir('destape_estado?select=*')
    ]).then(function (res) {
      filas = res[0]; est = {};
      res[1].forEach(function (r) { est[r.id] = r; });
      lsSet(CK_FILAS, filas); lsSet(CK_EST, est);
      aviso.hidden = true;
      listo('Actualizado ' + new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' }));
    }).catch(function () {
      var cf = lsGet(CK_FILAS, null);
      if (cf) { filas = cf; est = lsGet(CK_EST, {}); aviso.textContent = 'Sin conexión. Estás viendo lo último guardado en este teléfono.'; }
      else { filas = APP.respaldo || []; est = APP.respaldo_estado || {}; aviso.textContent = 'Sin conexión. Estás viendo un respaldo antiguo.'; }
      aviso.hidden = false;
      listo('Sin conexión');
    });
  }
  function listo(txt) {
    vistos = lsGet(CK_VISTOS, null);
    if (!vistos) { primeraVez = true; vistos = {}; }
    document.getElementById('hdr-act').textContent = txt;
    pintar();
    var nuevos = {}; filas.forEach(function (f) { nuevos[f.id] = 1; });
    lsSet(CK_VISTOS, Object.assign({}, vistos, nuevos));
    document.querySelector('main').classList.add('listo'); document.body.classList.add('listo');
    medirHeader(); irAlHash();
  }
  function medirHeader() {
    var h = document.querySelector('header').offsetHeight;
    document.documentElement.style.setProperty('--hdr-h', h + 'px');
  }
  function irAlHash() {
    var id = decodeURIComponent((location.hash || '').slice(1)).replace(/"/g, '');
    if (!id) return;
    var sel = '.dw[data-id="' + id + '"]', el = document.querySelector(sel);
    if (!el && fila(id)) {
      // Si está realizado o cobrado, se abre esa lista (fuera de la agenda principal).
      var s = estadoDe(id);
      modo = s === 'cobrado' ? 'cobrados' : s === 'realizado' ? 'realizados' : 'agenda';
      vista = 'agenda'; pintar(); el = document.querySelector(sel);
    }
    if (el) { el.classList.add('foco'); el.scrollIntoView({ block: 'center' }); setTimeout(function () { el.classList.remove('foco'); }, 4000); }
  }

  // ── tarjeta ────────────────────────────────────────────────────────────
  var ICONOS = { 'destape-hydrojet': '💦', 'destape-camion': '🚛', 'video-inspeccion': '📹', 'succion-fosa': '🚛', 'destape-domiciliario': '🔧', 'destape-vertical': '🏢' };
  /** Minutos desde medianoche de la hora pedida ("de 9 a 12" → 540). null = sin hora exacta ("en la tarde"). */
  function minutosDe(h) {
    var t = String(h || '').toLowerCase(), m = t.match(/(\d{1,2})(?:[:.](\d{2}))?/);
    if (!m) return null;
    var n = +m[1]; if (n > 23) return null;
    if (n < 8 && /tarde|pm|noche/.test(t)) n += 12;
    return n * 60 + (+(m[2] || 0));
  }
  /** La marca de urgencia del conector ("HOY, lo antes posible — URGENTE") es para la ruta: al cliente no se le
   *  manda y en la página va sin raya larga (ley de textos), como "⚡ Urgente". */
  function esUrgente(h) { return /[—–-]\s*URGENTE\b/i.test(String(h || '')); }
  function horaLimpia(h) {
    return String(h || '').replace(/\s*[—–-]\s*URGENTE\b/i, '').replace(/[.,;\s—–-]+$/, '').trim();
  }
  function horaEquipo(h) { var t = horaLimpia(h); return t ? t + (esUrgente(h) ? ' ⚡ Urgente' : '') : ''; }
  function horaBonita(h) {
    var t = String(h || '').trim();
    var r = t.match(/^(?:de\s+|entre\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:a|y|-|hasta)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:hrs?|horas)?$/i);
    if (r) return r[1] + ':' + (r[2] || '00') + ' a ' + r[3] + ':' + (r[4] || '00') + ' hrs';
    var u = t.match(/^(?:a las\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:hrs?|horas)?$/i);
    if (u) return u[1] + ':' + (u[2] || '00') + ' hrs';
    return cap(t);
  }
  /** El WhatsApp al cliente ("Avisar al cliente que vamos"): sin la marca URGENTE ni raya larga. */
  function msgCliente(f) {
    var d = f.data || {}, h = horaLimpia(d.hora);
    return 'Hola, le escribo de Destape Rápido, soy del equipo que va a hacer el ' + (d.servicio || 'destape').toLowerCase()
      + '. Vamos ' + diaRelativo(fechaEf(f)) + (h ? ', ' + h : '') + (d.direccion ? ', a ' + d.direccion : '') + '. ¿Me confirma que nos puede recibir?';
  }
  function diaRelativo(iso) {
    if (iso === hoyISO(0)) return 'hoy';
    if (iso === hoyISO(1)) return 'mañana ' + diaLargo(iso);
    return 'el ' + diaLargo(iso);
  }
  function dirHtml(d) {
    var dire = String(d.direccion || '').trim(), com = String(d.comuna || '').trim();
    if (!dire && !com) return '<span class="dc-falta">Falta la dirección. Pídesela al cliente.</span>';
    if (com && dire.toLowerCase().indexOf(com.toLowerCase()) < 0) return dire ? '<b>' + esc(dire) + '</b>, ' + esc(com) : '<b>' + esc(com) + '</b>';
    return '<b>' + esc(dire) + '</b>';
  }
  function mapaDe(d) {
    if (d.maps_url) return d.maps_url;
    var q = [d.direccion, d.comuna].filter(Boolean).join(', ');
    return q ? 'https://maps.google.com/?q=' + encodeURIComponent(q) : '';
  }
  function telBonito(d) { return d.length === 11 && d.indexOf('569') === 0 ? '+56 9 ' + d.slice(3, 7) + ' ' + d.slice(7) : '+' + d; }
  /** ¿Pidió factura? true = sí ("si", "sí", "si, con factura", "con factura"), false = no
   *  ("no", "sin factura", "boleta"), null = no se sabe (""). OJO: "sin factura" empieza con
   *  "si", por eso se mira la palabra entera. Igual que con_factura() en Python. */
  function conFactura(v) {
    var t = String(v == null ? '' : v).trim().toLowerCase().replace(/í/g, 'i');
    if (!t) return null;
    if (/^(sin|no|boleta|false)\b/.test(t)) return false;
    if (/^(si|true)\b/.test(t) || /^con factura/.test(t) || t === 'factura') return true;
    return null;
  }
  /** El valor es NETO. Regla del dueño: si pide factura se suma el IVA (19 %). */
  function ivaTxt(d, n) {
    var fac = conFactura(d.factura);
    if (fac === true) return 'Con factura: + IVA' + (n ? ' (' + clp(Math.round(n * 1.19)) + ' en total)' : '');
    if (fac === false) return 'Sin factura';
    return 'Si pide factura se suma el IVA';
  }

  // ── cobro: "¿Cuánto se cobró?" ─────────────────────────────────────────
  function calcTxt(f, n) {
    if (!n) return 'Escribe el valor. Por ejemplo 140 o 140.000.';
    return 'Se guarda <b>' + clp(n) + '</b>. Comisión ' + pctDe(f) + ' %: <b>' + clp(Math.round(n * pctDe(f) / 100)) + '</b>'
      + (conFactura((f.data || {}).factura) === true ? '<br>Con factura el cliente paga <b>' + clp(Math.round(n * 1.19)) + '</b> con IVA' : '');
  }
  function cobroHtml(f) {
    var id = f.id, d = f.data || {}, ya = estadoDe(id) === 'cobrado', base = baseDe(f);
    var txt = borrador[id] != null ? borrador[id] : (base ? clp(base) : '');
    var n = leerMonto(txt), fac = conFactura(d.factura);
    return '<div class="cobro">'
      + '<label class="cobro-lbl">¿Cuánto se cobró?' + (fac === false ? '' : '<small>Escribe el valor sin IVA</small>')
      + '<input class="cobro-in" type="text" inputmode="numeric" autocomplete="off" enterkeyhint="done" data-acc="monto" value="' + esc(txt) + '"></label>'
      + '<div class="cobro-calc">' + calcTxt(f, n) + '</div>'
      + '<button type="button" class="cobro-ok" data-acc="cobro-ok"' + (n ? '' : ' disabled') + '>' + (ya ? 'Guardar valor' : 'Guardar cobrado') + '</button>'
      + '<button type="button" class="cobro-no" data-acc="cobro-no">Cancelar</button>'
      + (ya ? '<div class="cobro-sacar"><button type="button" class="sacar" data-acc="descobrar">No se cobró, sacar de cobrados</button></div>' : '')
      + '</div>';
  }
  function abrirCobro(id) {
    if (!id || !fila(id)) return;
    if (E(id).comision_pagada) { toast('Su comisión ya está pagada. Revoca el pago antes de cambiar el valor.'); return; }
    cobrando = id; delete borrador[id]; pintar();
    var inp = document.querySelector('.vista:not([hidden]) .cobro-in');
    if (inp && inp.focus) { inp.focus(); if (inp.select) inp.select(); }
  }
  /** Guarda valor final y estado cobrado JUNTOS (un solo guardado). */
  function guardarCobro(id, txt) {
    var f = fila(id); if (!f) return Promise.resolve(false);
    var n = leerMonto(txt);
    if (!n) { toast('Escribe cuánto se cobró. Por ejemplo 140.000.'); return Promise.resolve(false); }
    if (E(id).comision_pagada) { toast('Su comisión ya está pagada. Revoca el pago antes de cambiar el valor.'); return Promise.resolve(false); }
    var ya = estadoDe(id) === 'cobrado', com = Math.round(n * pctDe(f) / 100);
    cobrando = null; delete borrador[id];
    return cambiar(id, { estado: 'cobrado', valor_final: n }, (ya ? 'Valor corregido: ' : 'Cobrado ') + clp(n) + '. Comisión ' + clp(com) + '.')
      .then(function () { return true; }, function () { cobrando = id; borrador[id] = txt; pintar(); return false; });
  }

  function wrap(f) {
    var id = f.id, st = estadoDe(id), e = E(id), d = f.data || {};
    var fe = fechaEf(f), orig = f.fecha || '';
    var tel = String(d.telefono || '').replace(/\D/g, '');
    var hora = horaEquipo(d.hora), min = minutosDe(hora);
    var contactado = !!e.contactado, atr = atrasado(f);
    var reag = e.fecha && orig && e.fecha !== orig;
    var cls = atr ? ' is-atrasado' : st !== 'pendiente' ? ' is-' + st : (contactado ? ' is-contactado' : '');
    if (!primeraVez && !vistos[id]) cls += ' nueva';
    var chip = st === 'cobrado' ? '<span class="chip cob">💰 Cobrado</span>'
      : st === 'realizado' ? '<span class="chip real">Falta cobrar</span>'
      : contactado ? '<span class="chip cont">✓ Cliente avisado</span>' : '';
    var top = '<div class="dw-top">'
      + (atr ? '<span class="pill-atr">⚠️ Atrasado · ' + esc(diaLargo(fe)) + '</span>' + (hora ? '<span class="hora-chica">🕐 ' + esc(horaBonita(hora)) + '</span>' : '')
        : '<span class="hora-pill' + (st !== 'pendiente' ? ' hecho' : min === null ? ' sin' : '') + '">🕐 ' + esc(hora ? horaBonita(hora) : 'Horario por confirmar') + '</span>')
      + chip + '</div>'
      + (reag ? '<div class="reag">Cambiado de fecha. Era el ' + esc(diaLargo(orig)) + '</div>' : '');
    var neto = Number(d.precio_neto) || 0, vf = Number(e.valor_final) > 0 ? Number(e.valor_final) : 0;
    var valor;
    if (st === 'cobrado') {
      valor = '<div class="dw-valor cob">' + (vf ? '' : '<span class="falta-vf">⚠️ Falta el valor final</span>')
        + (vf ? 'Se cobró' : 'Desde') + ' <b>' + clp(baseDe(f)) + '</b>'
        + '<span class="nota">Comisión ' + pctDe(f) + ' %' + (vf ? '' : ' aprox.') + ': ' + clp(comDe(f)) + (e.comision_pagada ? '. Ya pagada' : '') + '</span></div>';
    } else if (vf || neto) {
      valor = '<div class="dw-valor">' + (vf ? 'Valor final' : 'Desde') + ' <b>' + clp(vf || neto) + '</b><span class="nota">' + esc(ivaTxt(d, vf || neto)) + '</span></div>';
    } else valor = '<div class="dw-valor"><b>Valor a confirmar en terreno</b></div>';
    var servicio = d.servicio || 'Destape', trabajo = d.trabajo || '';
    var problema = trabajo && trabajo.trim().toLowerCase() !== servicio.trim().toLowerCase() ? '<div class="dw-linea dw-prob">🛠️ ' + esc(cap(trabajo)) + '</div>' : '';
    var lineas = '';
    if (d.acceso) lineas += '<div class="dw-linea">🚪 ' + esc(d.acceso) + '</div>';
    if (d.nota) lineas += '<div class="dw-linea nota-imp">📝 ' + esc(d.nota) + '</div>';
    var contacto = tel && st === 'pendiente' && !contactado
      ? '<button type="button" class="btn-contacto" data-acc="contactar">💬 Avisar al cliente que vamos</button>' : '';
    var mapa = mapaDe(d), acc = '';
    var cobrandoAca = cobrando === id && vista === 'agenda';
    if (tel && (contactado || st !== 'pendiente')) acc += '<a class="acc acc-wa' + (st === 'cobrado' ? ' suave' : '') + '" href="https://wa.me/' + tel + '" target="_blank" rel="noopener">WhatsApp</a>';
    if (tel) acc += '<a class="acc acc-tel" href="tel:+' + tel + '">📞 Llamar</a>';
    if (mapa && st !== 'cobrado') acc += '<a class="acc acc-map" href="' + esc(mapa) + '" target="_blank" rel="noopener">🗺️ Llegar</a>';
    var acciones;
    if (cobrandoAca) acciones = cobroHtml(f);
    else if (st === 'cobrado') acciones = '<div class="est-row"><button type="button" class="est-btn b-corr' + (vf ? '' : ' fuerte') + '" data-acc="cobrar">✏️ ' + (vf ? 'Corregir valor cobrado' : 'Poner valor final') + '</button></div>';
    else acciones = '<div class="est-row">'
      + '<button type="button" class="est-btn b-cob" data-acc="cobrar">💰 Cobrado</button>'
      + '<button type="button" class="est-btn b-real' + (st === 'realizado' ? ' on' : '') + '" data-acc="realizado">' + (st === 'realizado' ? '✓ Realizado' : 'Realizado, falta cobrar') + '</button></div>';
    var conf = confirmando === id
      ? '<div class="confirma">¿Quitar este destape de la agenda? <button type="button" class="si" data-acc="quitar-si">Sí, quitar</button><button type="button" class="no" data-acc="quitar-no">No</button></div>'
      : '<button type="button" class="quitar" data-acc="quitar">✕ Quitar de la agenda</button>';
    var mas = st === 'cobrado' ? '' : '<details class="dw-mas" data-mas="' + esc(id) + '"' + (masAbierto[id] || confirmando === id ? ' open' : '') + '><summary>Cambiar fecha o quitar</summary><div class="mas-cuerpo">'
      + '<label class="campo">📅 Nueva fecha<input type="date" data-acc="fecha" value="' + esc(fe) + '"></label>'
      + conf + '</div></details>';
    return '<div class="dw' + cls + '" data-id="' + esc(id) + '">' + top
      + '<div class="dw-body"><div class="dw-serv">' + (ICONOS[d.servicio_clave] || '🔧') + ' ' + esc(servicio) + '</div>'
      + problema
      + '<div class="dw-dir">📍 ' + dirHtml(d) + '</div>'
      + '<div class="dw-cli">👤 ' + esc(d.cliente || 'Cliente sin nombre') + (tel ? ' · ' + esc(telBonito(tel)) : '') + '</div>'
      + valor + lineas + contacto
      + (acc && !cobrandoAca ? '<div class="accesos">' + acc + '</div>' : '')
      + acciones + mas + '</div></div>';
  }

  // ── agenda ─────────────────────────────────────────────────────────────
  /** Agrupa por día. En la agenda: primero "Atrasados" (un grupo, cada tarjeta dice su fecha:
   *  "Atrasado · jueves 29 de octubre"), después hoy y lo que viene. En realizados y cobrados:
   *  lo más reciente arriba. */
  function agrupar(lista, reciente) {
    var g = {}, orden = [];
    lista.forEach(function (f) {
      var k = !reciente && atrasado(f) ? 'atrasados' : (fechaEf(f) || 'sin');
      if (!g[k]) { g[k] = []; orden.push(k); } g[k].push(f);
    });
    function peso(k) { return k === 'atrasados' ? '0' : k === 'sin' ? (reciente ? '0' : '9') : '1' + k; }
    orden.sort(function (a, b) { var r = peso(a) < peso(b) ? -1 : peso(a) > peso(b) ? 1 : 0; return reciente ? -r : r; });
    return orden.map(function (k) {
      return { k: k, items: g[k].sort(function (a, b) {
        var fa = fechaEf(a), fb = fechaEf(b);
        if (fa !== fb) return fa < fb ? -1 : 1;
        // por hora programada; los que no tienen hora exacta van al final del día
        var ma = minutosDe(a.data && a.data.hora), mb = minutosDe(b.data && b.data.hora);
        if (ma !== mb) { if (ma === null) return 1; if (mb === null) return -1; return ma - mb; }
        return (b.informado_at || '') < (a.informado_at || '') ? -1 : 1;
      }) };
    });
  }
  function titDia(k, hist) {
    var hoy = hoyISO(0);
    if (k === 'sin') return { t: 'Sin fecha', c: '' };
    if (k === 'atrasados') return { t: '⚠️ Atrasados', c: ' atrasado' };
    if (k === hoy) return { t: 'Hoy · ' + diaLargo(k), c: hist ? '' : ' hoy' };
    if (k === hoyISO(1)) return { t: 'Mañana · ' + diaLargo(k), c: '' };
    return { t: cap(diaLargo(k)), c: '' };
  }
  function pintarAgenda() {
    var cont = document.getElementById('agenda');
    var vivos = filas.filter(vivo);
    function de(s) { return vivos.filter(function (f) { return estadoDe(f.id) === s; }); }
    var pend = de('pendiente'), real = de('realizado'), cob = de('cobrado');
    if ((modo === 'realizados' && !real.length) || (modo === 'cobrados' && !cob.length)) modo = 'agenda';
    var hist = modo !== 'agenda', lista = modo === 'realizados' ? real : modo === 'cobrados' ? cob : pend;
    var html = '';
    function filtro(m, txt, n, extra) {
      var on = modo === m;
      return '<button type="button" class="filtro' + (on ? ' activo' : (extra || '')) + '" data-acc="modo" data-modo="' + m + '" aria-pressed="' + on + '">' + txt + ' (' + n + ')</button>';
    }
    if (real.length || cob.length) {
      html += '<div class="filtros">' + filtro('agenda', 'Por hacer', pend.length)
        + (real.length ? filtro('realizados', 'Falta cobrar', real.length, ' alerta') : '')
        + (cob.length ? filtro('cobrados', 'Cobrados', cob.length) : '') + '</div>';
    }
    agrupar(lista, hist).forEach(function (gr) {
      var t = titDia(gr.k, hist);
      html += '<section data-grupo="' + esc(gr.k) + '"><h2 class="dia-tit' + t.c + '">' + esc(t.t) + '<span class="dia-n">' + gr.items.length + '</span></h2>'
        + gr.items.map(wrap).join('') + '</section>';
    });
    if (!lista.length) html += '<p class="vacio">No hay destapes por hacer. Cuando el bot confirme uno, aparece acá solo.</p>';
    if (hist) html += '<div class="espacio-fijo"></div><button type="button" class="volver-fijo" data-acc="modo" data-modo="agenda">← Volver a la agenda</button>';
    cont.innerHTML = html;
    var nAtr = pend.filter(atrasado).length;
    document.getElementById('hdr-pend').textContent = pend.length;
    document.getElementById('hdr-atr').textContent = nAtr ? ' · ' + nAtr + (nAtr === 1 ? ' atrasado' : ' atrasados') : '';
  }

  // ── comisión ───────────────────────────────────────────────────────────
  function desel() { return lsGet(CK_DESEL, {}); }
  function seleccion() {
    var d = desel();
    return porPagar().filter(function (f) { return !d[f.id]; });
  }
  function porPagar() { return filas.filter(function (f) { return vivo(f) && estadoDe(f.id) === 'cobrado' && !E(f.id).comision_pagada; }); }
  function suma(a) { return a.reduce(function (s, f) { return s + comDe(f); }, 0); }
  /** tipo: 'deuda' (cobrado sin pagar), 'falta' (realizado, falta cobrar) o 'pagada'. */
  function item(f, tipo) {
    var id = f.id, e = E(id), d = f.data || {}, vf = Number(e.valor_final) > 0;
    var chk = tipo === 'deuda' ? '<input type="checkbox" data-acc="sel" data-id="' + esc(id) + '"' + (desel()[id] ? '' : ' checked') + ' aria-label="Incluir en el pago">' : '';
    var det = (vf ? (tipo === 'falta' ? 'Valor final ' : 'Se cobró ') : 'Desde ') + clp(baseDe(f)) + ' · ' + pctDe(f) + ' %';
    var acc = '';
    if (cobrando === id && vista === 'comision') acc = cobroHtml(f);
    else if (tipo === 'deuda') acc = '<div class="com-acc"><button type="button" class="com-btn' + (vf ? '' : ' fuerte') + '" data-acc="cobrar">✏️ ' + (vf ? 'Corregir valor cobrado' : 'Poner valor final') + '</button></div>';
    else if (tipo === 'falta') acc = '<div class="com-acc"><button type="button" class="com-btn cob" data-acc="cobrar">💰 Cobrado</button></div>';
    var rev = tipo === 'pagada' ? '<button type="button" class="revocar" data-acc="revocar">Revocar</button>' : '';
    return '<div class="com-item' + (tipo === 'pagada' ? ' pagada' : '') + '" data-id="' + esc(id) + '">' + chk
      + '<div class="com-txt">' + (tipo === 'deuda' && !vf ? '<span class="tag-falta">⚠️ Falta valor final</span>' : '')
      + '<b>' + esc(cap(diaLargo(fechaEf(f)))) + ' · ' + esc(d.servicio || 'Destape') + '</b>'
      + '<span>' + esc([d.direccion, d.comuna].filter(Boolean).join(', ')) + '</span>'
      + '<span>' + esc(det) + '</span></div>'
      + '<div class="com-monto">' + clp(comDe(f)) + '<small>' + (tipo !== 'pagada' && !vf ? 'comisión aprox.' : 'comisión') + '</small></div>' + rev + acc + '</div>';
  }
  function pintarComision() {
    var vivos = filas.filter(vivo);
    var deuda = porPagar(), total = suma(deuda);
    var real = vivos.filter(function (f) { return estadoDe(f.id) === 'realizado'; });
    var pagadas = vivos.filter(function (f) { return estadoDe(f.id) === 'cobrado' && E(f.id).comision_pagada; });
    var html = '<div class="com-hero"><div class="r">Comisión por pagar</div>'
      + '<div class="v' + (total ? '' : ' al-dia') + '">' + (total ? clp(total) : 'Al día ✓') + '</div>'
      + '<div class="s">Es el ' + APP.pct + ' % de lo que se cobró en cada destape.' + (pagadas.length ? ' Ya pagado: ' + clp(suma(pagadas)) + '.' : '') + '</div></div>';
    if (deuda.length) html += '<h2 class="sec-tit">Cobrados, comisión sin pagar · ' + deuda.length + '</h2>' + deuda.map(function (f) { return item(f, 'deuda'); }).join('');
    if (real.length) html += '<h2 class="sec-tit">Realizados, falta cobrar · ' + real.length + '</h2>' + real.map(function (f) { return item(f, 'falta'); }).join('');
    if (pagadas.length) {
      var g = {};
      pagadas.forEach(function (f) { var k = (E(f.id).pagada_at || '').slice(0, 10) || 'sin-fecha'; (g[k] = g[k] || []).push(f); });
      var ks = Object.keys(g).sort();
      html += '<details class="pagos"><summary>Ver pagos hechos (' + ks.length + ')</summary>';
      ks.slice().reverse().forEach(function (k) {
        html += '<div class="pago-grupo"><div class="pago-head">Pago ' + (ks.indexOf(k) + 1) + (k !== 'sin-fecha' ? ' · ' + esc(diaLargo(k)) : '') + '<span>' + clp(suma(g[k])) + '</span></div>'
          + g[k].map(function (f) { return item(f, 'pagada'); }).join('') + '</div>';
      });
      html += '</details>';
    }
    if (!vivos.length) html += '<p class="vacio">Sin destapes todavía.</p>';
    document.getElementById('comision').innerHTML = html;
    var sel = seleccion(), btn = document.getElementById('btn-pagar');
    document.getElementById('barra-pagar').hidden = vista !== 'comision' || !deuda.length || !!cobrando;
    btn.disabled = !sel.length;
    btn.textContent = sel.length ? 'Pagar ' + clp(suma(sel)) + ' (' + sel.length + ')' : 'Marca lo que vas a pagar';
    document.getElementById('hdr-com').textContent = total ? clp(total) : 'al día';
  }

  function pintar() {
    pintarAgenda(); pintarComision();
    document.querySelectorAll('.vista').forEach(function (v) { v.hidden = v.getAttribute('data-vista') !== vista; });
    document.querySelectorAll('.vista-btn').forEach(function (b) { b.classList.toggle('activo', b.getAttribute('data-vista') === vista); });
  }

  // ── pago ───────────────────────────────────────────────────────────────
  function abrirPago() {
    var sel = seleccion(); if (!sel.length) return;
    var total = suma(sel), b = APP.banco;
    document.getElementById('modal-cuerpo').innerHTML = '<h2>Pagar ' + clp(total) + '</h2>'
      + '<div class="s">Transfiere a esta cuenta y después toca "Ya transferí". Se abre WhatsApp con el detalle para avisar.</div>'
      + '<div class="banco"><div><span>Titular</span><b>' + esc(b.titular) + '</b></div><div><span>Banco</span><b>' + esc(b.banco) + '</b></div>'
      + '<div><span>Cuenta RUT</span><b>' + esc(b.cuenta) + '</b></div><div><span>Monto</span><b>' + clp(total) + '</b></div></div>';
    document.getElementById('modal').hidden = false;
  }
  function confirmarPago() {
    var sel = seleccion(); if (!sel.length) return;
    var ts = new Date().toISOString(), total = 0;
    var btn = document.querySelector('.m-ok'); btn.disabled = true; btn.textContent = 'Guardando...';
    var antes = {};
    sel.forEach(function (f) { antes[f.id] = Object.assign({}, E(f.id)); total += comDe(f); });
    Promise.all(sel.map(function (f) { return guardar(f.id, { comision_pagada: true, pagada_at: ts }); })).then(function () {
      sel.forEach(function (f) { est[f.id] = Object.assign({}, E(f.id), { comision_pagada: true, pagada_at: ts }); });
      lsSet(CK_EST, est);
      var lineas = ['Hola Alejandro, te transferí ' + clp(total) + ' de comisión de destapes:'];
      sel.forEach(function (f) { var d = f.data || {}; lineas.push('- ' + cap(diaLargo(fechaEf(f))) + ', ' + (d.servicio || 'Destape') + ', ' + (d.direccion || '') + ': ' + clp(comDe(f))); });
      document.getElementById('modal').hidden = true; pintar(); toast('Pago guardado');
      window.open('https://wa.me/' + APP.whatsapp + '?text=' + encodeURIComponent(lineas.join('\n')), '_blank');
    }).catch(function () {
      // Si una falló, se deshace todo para no dejar un pago a medias.
      Promise.all(sel.map(function (f) { return guardar(f.id, { comision_pagada: !!antes[f.id].comision_pagada, pagada_at: antes[f.id].pagada_at || null }).catch(function () {}); }));
      est = Object.assign(est, antes); lsSet(CK_EST, est); pintar();
      toast('No se pudo guardar el pago. No se marcó nada. Intenta de nuevo.');
    }).then(function () { btn.disabled = false; btn.textContent = 'Ya transferí, avisar por WhatsApp'; });
  }

  // ── eventos ────────────────────────────────────────────────────────────
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-acc],[data-vista]'); if (!t) return;
    if (t.classList.contains('vista-btn')) { vista = t.getAttribute('data-vista'); cobrando = null; pintar(); window.scrollTo(0, 0); return; }
    var w = t.closest('[data-id]'), id = w && w.getAttribute('data-id');
    var acc = t.getAttribute('data-acc');
    if (acc === 'contactar' && id) {
      var f = fila(id), d = (f && f.data) || {}, tel = String(d.telefono || '').replace(/\D/g, '');
      if (E(id).contactado || !tel) return;
      // Se presenta y pregunta UNA cosa, como en baños. Sin emoji ni exclamación.
      var msg = msgCliente(f);
      cambiar(id, { contactado: true }, 'Cliente avisado').catch(function () {});
      window.location.href = 'https://wa.me/' + tel + '?text=' + encodeURIComponent(msg);
      return;
    }
    if (acc === 'realizado') {
      var st = estadoDe(id);
      cambiar(id, { estado: st === 'pendiente' ? 'realizado' : 'pendiente' },
        st === 'pendiente' ? 'Realizado. Queda en Falta cobrar.' : 'Vuelve a la agenda.').catch(function () {});
    } else if (acc === 'cobrar') abrirCobro(id);
    else if (acc === 'cobro-no') { cobrando = null; delete borrador[id]; pintar(); }
    else if (acc === 'cobro-ok') {
      var c = t.closest('.cobro'), inp = c && c.querySelector('.cobro-in');
      guardarCobro(id, inp ? inp.value : '');
    } else if (acc === 'descobrar') {
      if (E(id).comision_pagada) { toast('Su comisión ya está pagada. Revoca el pago antes.'); return; }
      if (!confirm('¿Sacar de cobrados? Vuelve a la lista Falta cobrar.')) return;
      cobrando = null; delete borrador[id];
      cambiar(id, { estado: 'realizado' }, 'Ya no figura como cobrado. Queda en Falta cobrar.').catch(function () {});
    } else if (acc === 'quitar') { confirmando = id; pintar(); }
    else if (acc === 'quitar-no') { confirmando = null; pintar(); }
    else if (acc === 'quitar-si') { confirmando = null; cambiar(id, { eliminado: true }, 'Quitado de la agenda').catch(function () {}); }
    else if (acc === 'modo') { modo = t.getAttribute('data-modo') || 'agenda'; cobrando = null; pintar(); window.scrollTo(0, 0); }
    else if (acc === 'revocar') {
      if (confirm('¿Revocar este pago? La comisión vuelve a quedar por pagar.')) cambiar(id, { comision_pagada: false, pagada_at: null }, 'Pago revocado').catch(function () {});
    } else if (acc === 'sel') {
      var d2 = desel();
      if (t.checked) delete d2[id]; else d2[id] = 1;
      lsSet(CK_DESEL, d2); pintarComision();
    }
  });
  // Mientras se escribe el valor: se muestra cómo se va a guardar y la comisión.
  document.addEventListener('input', function (ev) {
    var t = ev.target; if (!t.getAttribute || t.getAttribute('data-acc') !== 'monto') return;
    var w = t.closest('[data-id]'), id = w && w.getAttribute('data-id'), f = id && fila(id); if (!f) return;
    borrador[id] = t.value;
    var n = leerMonto(t.value), c = t.closest('.cobro');
    c.querySelector('.cobro-calc').innerHTML = calcTxt(f, n);
    c.querySelector('.cobro-ok').disabled = !n;
  });
  // Al salir del campo se muestra como plata: "140" o "140 mil" → "$140.000".
  document.addEventListener('focusout', function (ev) {
    var t = ev.target; if (!t.getAttribute || t.getAttribute('data-acc') !== 'monto') return;
    var n = leerMonto(t.value), w = t.closest('[data-id]');
    if (n) { t.value = clp(n); if (w) borrador[w.getAttribute('data-id')] = t.value; }
  });
  document.addEventListener('keydown', function (ev) {
    var t = ev.target; if (ev.key !== 'Enter' || !t.getAttribute || t.getAttribute('data-acc') !== 'monto') return;
    ev.preventDefault();
    var w = t.closest('[data-id]'); if (w) guardarCobro(w.getAttribute('data-id'), t.value);
  });
  document.addEventListener('change', function (ev) {
    var t = ev.target, acc = t.getAttribute && t.getAttribute('data-acc'); if (acc !== 'fecha') return;
    var w = t.closest('[data-id]'), id = w && w.getAttribute('data-id'); if (!id) return;
    var f = fila(id), v = t.value || null;
    var cambio = (!v || v === (f && f.fecha)) ? { fecha: null } : { fecha: v };
    cambiar(id, cambio, v ? 'Nueva fecha: ' + diaLargo(v) : 'Fecha original').catch(function () {});
  });
  document.getElementById('btn-pagar').addEventListener('click', abrirPago);
  document.querySelector('.m-ok').addEventListener('click', confirmarPago);
  document.querySelector('.m-no').addEventListener('click', function () { document.getElementById('modal').hidden = true; });
  document.querySelector('.m-copiar').addEventListener('click', function () {
    var b = APP.banco, t = b.titular + '\n' + b.banco + '\nCuenta RUT ' + b.cuenta + '\n' + b.email;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { toast('Datos copiados'); }).catch(function () { toast(t); });
  });
  document.addEventListener('toggle', function (ev) {
    var t = ev.target; if (!t.getAttribute || !t.hasAttribute('data-mas')) return;
    masAbierto[t.getAttribute('data-mas')] = t.open;
  }, true);
  window.addEventListener('resize', medirHeader);
  window.addEventListener('hashchange', irAlHash);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) cargar(); });
  // Pruebas sin navegador: expone la lógica pura.
  window.__DESTAPES__ = { comDe: comDe, baseDe: baseDe, fechaEf: fechaEf, estadoDe: estadoDe, porPagar: porPagar,
    clp: clp, leerMonto: leerMonto, conFactura: conFactura, abrirCobro: abrirCobro, guardarCobro: guardarCobro,
    horaLimpia: horaLimpia, horaEquipo: horaEquipo, msgCliente: msgCliente,
    pintar: function () { pintar(); }, _modo: function (m, v) { modo = m; if (v) vista = v; },
    _set: function (f, e) { filas = f; est = e; } };
  cargar();
})();
"""

PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#163F78">
<title>Agenda de destapes · Destape Rápido</title>
<style>@@CSS@@</style>
</head>
<body>
<header>
  <h1>🚛 Agenda de destapes</h1>
  <div class="sub"><b id="hdr-pend"><span class="skel" style="width:14px"></span></b> por hacer<span id="hdr-atr"></span> · <span id="hdr-act">Cargando...</span></div>
  <div class="sub hdr-com">💰 Comisión por pagar: <span id="hdr-com"><span class="skel"></span></span></div>
</header>
<div id="skel" aria-hidden="true">
  <div class="sk sk-tabs"></div><div class="sk sk-tit"></div><div class="sk sk-card"></div><div class="sk sk-card"></div>
</div>
<main>
  <div id="aviso-red" class="aviso-red" hidden></div>
  <div class="vistas">
    <button type="button" class="vista-btn activo" data-vista="agenda">📅 Agenda</button>
    <button type="button" class="vista-btn" data-vista="comision">💰 Comisión</button>
  </div>
  <div class="vista" data-vista="agenda"><div id="agenda"></div></div>
  <div class="vista" data-vista="comision" hidden><div id="comision"></div></div>
</main>
<div id="barra-pagar" class="barra-pagar" hidden><button type="button" id="btn-pagar" class="btn-pagar" disabled>Marca lo que vas a pagar</button></div>
<div id="modal" class="modal" hidden><div class="modal-box"><div id="modal-cuerpo"></div>
  <div class="modal-acc"><button type="button" class="m-ok">Ya transferí, avisar por WhatsApp</button>
  <button type="button" class="m-copiar">Copiar datos de la cuenta</button>
  <button type="button" class="m-no">Cancelar</button></div></div></div>
<div id="toast" class="toast" role="status" hidden></div>
<footer>Destape Rápido · área camión, hidrojet y cámara</footer>
<script>window.__APP__ = @@APP@@;</script>
<script>@@SCRIPT@@</script>
</body>
</html>
"""


def construir_html(respaldo: list[dict], respaldo_estado: dict | None = None) -> str:
    app = {
        "url": SUPABASE_URL,
        "key": SUPABASE_ANON_KEY,
        "pct": pct_comision(),
        "banco": gl.DATOS_BANCARIOS,
        "whatsapp": gl.WHATSAPP_COMISION,
        "respaldo": respaldo,
        "respaldo_estado": respaldo_estado or {},
        "generado": date.today().isoformat(),
    }
    app_json = json.dumps(app, ensure_ascii=False).replace("</", "<\\/")
    return (PAGINA.replace("@@CSS@@", CSS).replace("@@SCRIPT@@", SCRIPT).replace("@@APP@@", app_json))


def main() -> None:
    sin_red = "--sin-red" in sys.argv
    respaldo = [] if sin_red else filas_vivas()
    estado = {} if sin_red else estado_vivo()
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), SALIDA))
    out.write_text(construir_html(respaldo, estado), encoding="utf-8")
    print(f"✅ {out} ({len(respaldo)} destapes en el respaldo, comisión {pct_comision()} %)")


if __name__ == "__main__":
    main()
