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
- (4-nov-2026, pedido de Alejandro: «para una persona que no entiende es confuso, analiza cómo está
  hecho el de baños») la página copia la de baños: SIN filtros arriba, un solo botón punteado
  "Ver completadas (N)" que muestra hechos y cobrados (y queda fijo abajo para volver), en cada
  tarjeta la barra de arriba con la fecha (mover de día ahí mismo) y los dos botones de estado
  "Realizado" y "Cobrado" (blancos sin marcar, de color al marcar), una frase que dice qué toca
  hacer, "Quitar de la agenda" a la vista (el equipo no lo encontraba escondido), la barra de
  avance del día con el 🚛, animaciones suaves al cambiar de lista y Deshacer en el aviso. La
  comisión queda como la de baños: la deuda arriba, "Selecciona las que vas a pagar" con su check,
  "Revisar en WhatsApp" y "Ver toda la info". Los teléfonos van todo juntos (+569…), de un toque.

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
    hasta = int(solo_digitos(d.get("precio_hasta")) or 0)
    if neto and hasta > neto:
        # (31-oct-2026, p-753) un rango: «$70.000 a $90.000», el valor final se confirma en terreno
        valor = (f'<div class="dc-valor"><b>{esc(clp(neto))} a {esc(clp(hasta))}</b>'
                 f'<span class="dc-iva">Se confirma en terreno. {esc(iva_txt(d.get("factura")))}</span></div>')
    else:
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
  --azul-btn:#1F5AA8; --oro-btn:#B8860B; --verde-btn:#16A34A; --real:#1E40AF; --real-bg:#EFF6FF; --real-br:#93C5FD;
  --tinta-2:#334155; --skel-a:#E2E8F0; --skel-b:#EDF2F7; color-scheme:light dark; }
@media (prefers-color-scheme: dark) {
  :root { --azul:#3B82F6; --azul-2:#1E3A8A; --tinta:#E5E7EB; --gris:#94A3B8; --linea:#273244; --fondo:#0B1220;
    --card:#111A2B; --suave:#0F1726; --verde:#4ADE80; --verde-bg:#0F2A1C; --verde-br:#166534;
    --ambar:#FCD34D; --ambar-bg:#3A2A06; --ambar-br:#A16207; --oro:#CA8A04;
    --rojo:#FCA5A5; --rojo-bg:#3A1212; --rojo-br:#7F1D1D;
    --azul-btn:#2563EB; --real:#60A5FA; --real-bg:#172554; --real-br:#1E40AF;
    --tinta-2:#CBD5E1; --skel-a:#1E293B; --skel-b:#273449; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
[hidden] { display:none !important; }
html, body { max-width:100%; overflow-x:hidden; }
body { margin:0; background:var(--fondo); color:var(--tinta);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:16px; line-height:1.45; padding-bottom:calc(40px + env(safe-area-inset-bottom)); }
body.modo-completadas { padding-bottom:calc(150px + env(safe-area-inset-bottom)); }
body.vista-comision { padding-bottom:calc(110px + env(safe-area-inset-bottom)); }
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
.aviso-red { background:var(--ambar-bg); color:var(--ambar); border-radius:10px; padding:8px 12px; font-size:14px; margin-bottom:10px; }
/* Las dos vistas, como en baños: Agenda y Comisión. Nada más arriba. */
.vistas { display:flex; gap:8px; }
.vista-btn { flex:1 1 0; min-height:48px; border-radius:12px; border:1px solid var(--linea); background:var(--card);
  color:var(--tinta); font:inherit; font-weight:700; font-size:16px; cursor:pointer; transition:background .15s, color .15s; }
.vista-btn.activo { background:var(--azul-btn); border-color:var(--azul-btn); color:#fff; }
/* "Ver completadas", igual que en baños: un solo botón punteado. Activo, queda fijo abajo y te sigue. */
.ver-ant { display:block; width:100%; margin-top:12px; min-height:50px; border:1px dashed var(--gris); border-radius:12px;
  background:var(--card); color:var(--tinta); font:inherit; font-weight:700; font-size:15px; cursor:pointer; transition:background .15s; }
.ver-ant.modo-activo { position:fixed; bottom:calc(16px + env(safe-area-inset-bottom)); left:50%; transform:translateX(-50%);
  width:calc(100% - 24px); max-width:536px; z-index:30; background:var(--azul-btn); color:#fff; border:1px solid var(--azul-btn);
  box-shadow:0 6px 18px rgba(15,23,42,.30); }
.modo-titulo { position:fixed; bottom:calc(74px + env(safe-area-inset-bottom)); left:50%; transform:translateX(-50%);
  width:calc(100% - 24px); max-width:536px; z-index:30; margin:0; font-weight:800; color:var(--verde); background:var(--verde-bg);
  border:1px solid var(--verde-br); border-radius:10px; padding:9px 12px; text-align:center; font-size:13px;
  box-shadow:0 4px 14px rgba(15,23,42,.18); }
.resumen-comp { margin:10px 2px 0; font-size:14px; color:var(--gris); font-weight:600; }
/* Título del día con su barra de avance (el 🚛 va en la punta), como la de baños. */
.dia-tit { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800; text-transform:uppercase;
  letter-spacing:.5px; color:var(--gris); margin:16px 0 8px; padding:6px 0; position:sticky; top:var(--hdr-h,70px);
  z-index:5; background:var(--fondo); }
.dia-tit.atrasado { color:var(--rojo); }
.dia-tit.hoy { color:var(--azul); }
.dia-txt { flex:0 1 auto; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.prog { display:flex; align-items:center; gap:12px; flex:1 1 auto; min-width:0; }
.prog-bar { position:relative; flex:1 1 auto; min-width:64px; height:16px; background:var(--linea); border-radius:999px; overflow:visible; }
.prog-fill { position:absolute; left:0; top:0; bottom:0; width:0; background:var(--verde-btn); border-radius:999px;
  display:flex; align-items:center; justify-content:flex-end; transition:width .5s ease; }
.prog-truck { font-size:13px; line-height:1; transform:translateX(42%); filter:drop-shadow(0 1px 1px rgba(0,0,0,.25)); }
.prog-num { flex:none; font-size:12px; font-weight:800; color:var(--gris); font-variant-numeric:tabular-nums; text-transform:none; }
.dia-n { margin-left:auto; flex:none; background:var(--card); border:1px solid var(--linea); border-radius:20px; padding:1px 9px; font-size:12px; color:var(--gris); }
/* La tarjeta: barra de gestión ARRIBA (fecha + Realizado + Cobrado) y el cuerpo abajo, como en baños. */
.dw { position:relative; margin-bottom:12px; border-radius:16px; transition:transform .25s ease, opacity .25s ease; }
.gt { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:9px 12px; background:var(--card);
  border:1px solid var(--linea); border-bottom:none; border-radius:16px 16px 0 0; }
.dw-card { background:var(--card); border:1px solid var(--linea); border-top:none; border-radius:0 0 16px 16px; padding:10px 14px 14px;
  box-shadow:0 1px 3px rgba(15,23,42,.06); }
.gt-fecha { display:flex; align-items:center; gap:5px; font-size:13px; color:var(--gris); font-weight:600; }
.fecha-input { font-family:inherit; font-size:13px; padding:6px 5px; border:1px solid var(--linea); border-radius:8px;
  background:var(--card); color:var(--tinta); min-height:38px; width:118px; box-sizing:border-box; }
.gt-estados { display:flex; gap:6px; margin-left:auto; }
.est-btn { padding:8px 12px; border:1px solid var(--linea); background:var(--card); color:var(--gris); font-size:13.5px; font-weight:700;
  border-radius:9px; cursor:pointer; font-family:inherit; min-height:40px; transition:background .18s, color .18s, transform .12s; }
.est-btn:active { transform:scale(.97); }
.est-btn.b-real.activo { background:var(--real); color:#fff; border-color:var(--real); }
.est-btn.b-cob.activo { background:var(--oro-btn); color:#fff; border-color:var(--oro-btn); }
.chip-atr { width:100%; font-size:12.5px; font-weight:800; color:var(--rojo); background:var(--rojo-bg); border:1px solid var(--rojo-br);
  padding:5px 9px; border-radius:8px; }
.chip-reag { width:100%; font-size:12px; font-weight:800; color:var(--rojo); background:var(--rojo-bg); padding:4px 9px; border-radius:8px; }
/* Color de la tarjeta según estado: azul hecho, dorado cobrado, verde cliente avisado, rojo atrasado. */
.dw.is-realizado > .gt, .dw.is-realizado > .dw-card { border-color:var(--real-br); background:var(--real-bg); }
.dw.is-cobrado > .gt, .dw.is-cobrado > .dw-card { border-color:var(--ambar-br); background:var(--ambar-bg); }
.dw.is-contactado > .gt, .dw.is-contactado > .dw-card { border-color:var(--verde-br); background:var(--verde-bg); }
.dw.is-atrasado > .gt, .dw.is-atrasado > .dw-card { border-color:var(--rojo-br); }
.dw.is-atrasado > .gt { border-width:2px; border-bottom:none; } .dw.is-atrasado > .dw-card { border-width:2px; border-top:none; }
.dw.foco { animation:pulso 1.2s ease-in-out 2; }
@keyframes pulso { 0%,100% { box-shadow:0 0 0 0 rgba(59,130,246,0); } 35% { box-shadow:0 0 0 6px rgba(59,130,246,.45); } }
.dw.nueva { margin-top:22px; box-shadow:0 0 0 2px #93C5FD, 0 4px 16px rgba(59,130,246,.28); }
.dw.nueva::before { content:"✨ Nuevo"; position:absolute; top:-11px; right:14px; background:#3B82F6; color:#fff;
  font-size:11px; font-weight:800; padding:2px 10px; border-radius:999px; box-shadow:0 1px 4px rgba(30,64,175,.35); z-index:2; }
/* Animaciones: entra al pintar un cambio de lista, sale (se encoge) al irse a otra lista. */
.anim-entrar .dw { animation:entrar .28s ease both; }
@keyframes entrar { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
.dw.saliendo { animation:salir .32s ease forwards; overflow:hidden; }
@keyframes salir { to { opacity:0; transform:translateX(-30px); max-height:0; margin-bottom:0; } }
.dw.saliendo { max-height:900px; }
@media (prefers-reduced-motion: reduce) { .sk, .dw, .dw.foco, .anim-entrar .dw, .dw.saliendo, .cobro, .toast { animation:none !important; transition:none !important; } }
.estado-hint { font-size:12.5px; font-weight:700; color:var(--gris); margin-bottom:6px; }
.estado-hint.rojo { color:var(--rojo); } .estado-hint.verde { color:var(--verde); } .estado-hint.azul { color:var(--real); } .estado-hint.oro { color:var(--ambar); }
.hora-pill { display:inline-flex; align-items:center; gap:6px; background:var(--azul-btn); color:#fff; font-weight:800;
  font-size:17px; padding:6px 12px; border-radius:10px; font-variant-numeric:tabular-nums; letter-spacing:.2px; margin-bottom:8px; }
.hora-pill.sin { background:var(--ambar-bg); color:var(--ambar); font-size:15px; }
.hora-pill.hecho { background:var(--suave); color:var(--gris); border:1px solid var(--linea); font-size:15px; }
.dw-serv { font-weight:800; font-size:18px; line-height:1.25; }
.dw-dir { margin-top:6px; font-size:16px; overflow-wrap:anywhere; }
.dw-cli { margin-top:4px; font-size:15px; color:var(--tinta-2); overflow-wrap:anywhere; }
.dw-cli a { color:var(--azul); font-weight:700; text-decoration:none; }
.dc-falta { color:var(--rojo); font-weight:700; }
.dw-valor { margin-top:10px; display:flex; flex-wrap:wrap; align-items:baseline; gap:0 6px; background:var(--verde-bg);
  border:1px solid var(--verde-br); border-radius:12px; padding:8px 12px; color:var(--verde); font-size:16px; }
.dw-valor b { font-size:22px; font-variant-numeric:tabular-nums; }
.dw-valor .nota { flex-basis:100%; font-size:14px; opacity:.92; }
.dw-valor.cob { background:var(--ambar-bg); border-color:var(--ambar-br); color:var(--ambar); }
.dw.is-cobrado .dw-valor.cob { background:var(--card); }
.falta-vf, .tag-falta { flex-basis:100%; font-weight:800; font-size:14px; color:var(--ambar); }
.tag-falta { display:inline-block; background:var(--ambar-bg); border:1px solid var(--ambar-br); border-radius:8px; padding:2px 8px; margin-bottom:4px; }
.dw-prob { margin-top:4px; color:var(--tinta); font-weight:600; }
.dw-linea { margin-top:8px; font-size:15.5px; color:var(--tinta-2); overflow-wrap:anywhere; }
.dw-linea.nota-imp { color:var(--ambar); background:var(--ambar-bg); border-radius:10px; padding:8px 10px; font-weight:600; }
.btn-contacto { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; margin-top:12px; min-height:52px;
  border:none; border-radius:12px; background:var(--verde-btn); color:#fff; font:inherit; font-size:16px; font-weight:800; cursor:pointer; }
.btn-contacto:active { filter:brightness(.95); }
.btn-contacto.hecho { background:var(--verde-bg); color:var(--verde); border:1px solid var(--verde-br); cursor:default; }
.accesos { display:flex; gap:8px; margin-top:8px; }
.acc { flex:1 1 0; display:flex; align-items:center; justify-content:center; gap:6px; min-height:48px; border-radius:12px;
  text-decoration:none; font-weight:700; font-size:15px; }
.acc-wa { background:var(--verde-btn); color:#fff; } .acc-map { background:var(--azul-btn); color:#fff; }
.acc-tel { background:var(--card); color:var(--tinta); border:2px solid var(--gris); }
.acc.suave { background:var(--card); color:var(--tinta); border:2px solid var(--linea); }
.acc:active { filter:brightness(.92); }
/* Cobro: "¿Cuánto se cobró?" con el valor ya puesto */
.cobro { margin-top:12px; background:var(--ambar-bg); border:2px solid var(--oro); border-radius:14px; padding:14px;
  display:grid; gap:10px; animation:abrir .22s ease both; transform-origin:top; }
@keyframes abrir { from { opacity:0; transform:scaleY(.92); } to { opacity:1; transform:none; } }
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
.cobro-sacar { margin-top:10px; padding-top:8px; border-top:1px dashed var(--ambar-br); }
.sacar { background:none; border:none; padding:10px 0; min-height:44px; font:inherit; font-size:15px; font-weight:700;
  color:var(--rojo); cursor:pointer; text-align:left; }
/* Quitar: a la vista (antes estaba escondido y el equipo no lo encontraba). Confirma dentro de la tarjeta. */
.quitar { display:block; margin-top:10px; background:none; border:none; color:var(--gris); font:inherit; font-size:14px; font-weight:700;
  cursor:pointer; padding:8px 0; min-height:44px; text-align:left; }
.quitar:active { color:var(--rojo); }
.confirma { margin-top:10px; display:flex; flex-direction:column; gap:10px; align-items:center; text-align:center; font-size:14.5px;
  font-weight:800; background:var(--rojo-bg); border:2px solid var(--rojo-br); border-radius:12px; padding:12px; color:var(--rojo);
  animation:abrir .2s ease both; }
.conf-acc { display:flex; gap:10px; }
.confirma button { min-height:44px; border-radius:9px; border:none; font:inherit; font-weight:700; padding:0 16px; cursor:pointer; }
.confirma .si { background:#DC2626; color:#fff; } .confirma .no { background:var(--card); color:var(--tinta); border:1px solid var(--linea); }
.vacio { text-align:center; color:var(--gris); padding:36px 12px; }
.vacio small { display:block; margin-top:6px; }
/* Comisión, como la de baños: la deuda arriba, las tarjetas con su check, y abajo el botón fijo de pagar. */
.cp { background:var(--card); border:1px solid var(--linea); border-top:4px solid var(--oro); border-radius:14px; padding:14px; margin-top:12px;
  box-shadow:0 2px 10px rgba(184,134,11,.10); }
.cp-titulo { font-size:15px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--ambar); }
.com-deuda { display:flex; justify-content:space-between; align-items:baseline; gap:10px; background:var(--ambar-bg);
  border:1px solid var(--ambar-br); border-radius:12px; padding:12px 14px; margin-top:12px; color:var(--tinta); }
.com-deuda b { font-size:26px; font-weight:800; color:var(--ambar); font-variant-numeric:tabular-nums; }
.com-deuda.al-dia { background:var(--verde-bg); border-color:var(--verde-br); } .com-deuda.al-dia b { color:var(--verde); }
.com-nota { margin-top:8px; font-size:13px; color:var(--gris); }
.com-sec-tit { font-size:12px; text-transform:uppercase; letter-spacing:.6px; color:var(--gris); font-weight:700; margin:18px 2px 8px; }
.com-sec-tit.cobrar { color:var(--real); }
.com-card { padding:11px 13px; margin-bottom:8px; background:var(--ambar-bg); border:1px solid var(--ambar-br); border-radius:12px; }
.com-card.falta { background:var(--real-bg); border-color:var(--real-br); }
.com-card.pagada { background:var(--verde-bg); border-color:var(--verde-br); opacity:.9; }
.com-top { display:flex; align-items:center; gap:10px; }
.com-check { width:24px; height:24px; flex:none; accent-color:var(--verde-btn); }
.com-main { flex:1 1 140px; min-width:0; }
.com-cli { font-weight:800; font-size:16px; }
.com-dir { color:var(--gris); font-size:13px; overflow-wrap:anywhere; }
.com-monto { font-weight:800; color:var(--ambar); font-variant-numeric:tabular-nums; white-space:nowrap; font-size:18px; text-align:right; }
.com-monto small { display:block; font-size:11px; font-weight:600; color:var(--gris); }
.com-card.pagada .com-monto { color:var(--verde); }
.com-pagada-tag { font-size:10px; font-weight:700; color:var(--verde); background:var(--verde-bg); border:1px solid var(--verde-br); padding:3px 8px;
  border-radius:20px; flex:none; text-transform:uppercase; letter-spacing:.4px; }
.com-revocar { font-size:12px; font-weight:600; padding:6px 9px; border:1px solid var(--linea); background:var(--card); border-radius:8px;
  color:var(--rojo); cursor:pointer; flex:none; }
.com-acciones { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.com-wa, .com-info, .com-cobrar { flex:1 1 0; min-width:0; display:flex; align-items:center; justify-content:center; gap:6px; padding:9px 4px;
  border-radius:9px; font-family:inherit; font-size:12.5px; font-weight:700; cursor:pointer; min-height:44px; text-decoration:none; white-space:nowrap; }
.com-acciones .com-pagada-tag { align-self:center; }
.com-acciones .com-revocar { margin-left:auto; }
.com-wa { background:var(--verde-btn); color:#fff; border:none; }
.com-info { background:var(--card); color:var(--azul); border:1px solid var(--real-br); }
.com-cobrar { background:var(--oro-btn); color:#fff; border:none; }
.com-cobrar.ancho { flex-basis:100%; min-height:50px; font-size:15px; }
.com-detalle { margin-top:10px; background:var(--card); border:1px solid var(--linea); border-radius:10px; padding:10px 12px; font-size:14px;
  display:grid; gap:4px; animation:abrir .2s ease both; }
.com-detalle a { color:var(--azul); font-weight:700; text-decoration:none; }
.com-card .cobro { margin-top:10px; }
.pago-grupo { background:var(--suave); border:1px solid var(--linea); border-radius:14px; padding:12px; margin-bottom:12px; }
.pago-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:8px; }
.pago-tit { font-weight:800; color:var(--verde); } .pago-tot { font-weight:800; color:var(--verde); font-variant-numeric:tabular-nums; }
.barra-pagar { position:fixed; left:0; right:0; bottom:0; z-index:30; padding:10px 16px calc(10px + env(safe-area-inset-bottom));
  background:var(--card); border-top:1px solid var(--linea); box-shadow:0 -4px 12px rgba(0,0,0,.08); }
.btn-pagar { display:block; width:100%; max-width:528px; margin:0 auto; min-height:54px; border:none; border-radius:12px;
  background:var(--verde-btn); color:#fff; font:inherit; font-size:17px; font-weight:800; cursor:pointer; }
.btn-pagar:disabled { background:var(--linea); color:var(--gris); }
.modal { position:fixed; inset:0; z-index:50; background:rgba(2,6,23,.6); display:flex; align-items:flex-end; justify-content:center; }
.modal-box { background:var(--card); color:var(--tinta); width:100%; max-width:560px; border-radius:18px 18px 0 0;
  padding:18px 16px calc(18px + env(safe-area-inset-bottom)); max-height:90vh; overflow:auto; animation:subir .25s ease both; }
@keyframes subir { from { transform:translateY(30px); opacity:0; } to { transform:none; opacity:1; } }
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
  box-shadow:0 6px 18px rgba(0,0,0,.3); display:flex; align-items:center; gap:12px; animation:subir .22s ease both; }
.toast-acc { background:none; border:1px solid rgba(255,255,255,.5); color:#fff; font:inherit; font-weight:800; font-size:14px;
  border-radius:8px; padding:6px 10px; cursor:pointer; }
@media (prefers-color-scheme: dark) { .toast { background:#E5E7EB; color:#0F172A; } .toast-acc { color:#0F172A; border-color:rgba(15,23,42,.4); } }
footer { text-align:center; color:var(--gris); font-size:12px; padding:20px 16px 10px; }
/* Cancelados: al pie, detrás de un botón. Lo perdido y por qué. */
.pie-canc { max-width:560px; margin:0 auto; padding:0 16px 30px; }
.ver-canc { display:block; width:100%; min-height:46px; border:1px dashed var(--rojo-br); border-radius:12px; background:var(--card);
  color:var(--rojo); font:inherit; font-weight:700; font-size:14px; cursor:pointer; }
.ver-canc.abierto { background:var(--rojo-bg); }
.cancelados { margin-top:12px; animation:abrir .2s ease both; }
.canc-hero { background:var(--rojo-bg); border:1px solid var(--rojo-br); border-radius:14px; padding:14px; margin-bottom:10px; }
.canc-hero .r { font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--rojo); }
.canc-hero .v { font-size:30px; font-weight:800; color:var(--rojo); font-variant-numeric:tabular-nums; line-height:1.15; margin-top:2px; }
.canc-hero .s { font-size:13.5px; color:var(--tinta-2); margin-top:4px; }
.canc { background:var(--card); border:1px solid var(--linea); border-radius:12px; padding:11px 13px; margin-bottom:8px; }
.canc-top { display:flex; gap:10px; align-items:flex-start; }
.canc-main { flex:1 1 140px; min-width:0; }
.canc-serv { font-weight:800; font-size:15px; }
.canc-dir { color:var(--gris); font-size:13px; overflow-wrap:anywhere; }
.canc-dir a { color:var(--azul); font-weight:700; text-decoration:none; }
.canc-motivo { margin-top:4px; font-size:13.5px; font-weight:700; color:var(--rojo); overflow-wrap:anywhere; }
.canc-monto { font-weight:800; color:var(--rojo); font-variant-numeric:tabular-nums; white-space:nowrap; font-size:17px; text-align:right; }
.canc-monto small { display:block; font-size:11px; font-weight:600; color:var(--gris); }
.canc-acc { display:flex; gap:8px; margin-top:10px; }
.canc-volver, .canc-sacar { flex:1 1 0; min-height:42px; border-radius:9px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; }
.canc-volver { background:var(--card); color:var(--azul); border:1px solid var(--real-br); }
.canc-sacar { background:var(--card); color:var(--gris); border:1px solid var(--linea); }
.motivo-in { width:100%; font:inherit; font-size:15px; min-height:46px; border-radius:10px; border:1px solid var(--rojo-br); background:var(--card);
  color:var(--tinta); padding:6px 10px; }
.motivo-in::placeholder { color:var(--gris); font-size:14px; }
"""

SCRIPT = r"""
(function () {
  var APP = window.__APP__;
  var H = { apikey: APP.key, Authorization: 'Bearer ' + APP.key };
  var CK_FILAS = 'destapes_filas_v1', CK_EST = 'destapes_estado_v1', CK_VISTOS = 'destapes_vistos_v1', CK_DESEL = 'destapes_desel_v1';
  // modo: 'agenda' (por hacer) o 'completadas' (hechos y cobrados, detrás del botón punteado, como en baños).
  var filas = [], est = {}, modo = 'agenda', vista = 'agenda', confirmando = null, primeraVez = false, vistos = {};
  var cobrando = null, borrador = {}, infoAbierta = {}, deshacerFn = null, resaltarId = null, animarLista = false, cancelAbierto = false;

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
  function diaCorto(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return 'sin fecha';
    var p = iso.split('-');
    return (+p[2]) + ' ' + MESES[+p[1] - 1].slice(0, 3) + ' ' + p[0];
  }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function sinMovimiento() { try { return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } }
  /** Aviso abajo. Con `accion` ({txt, fn}) trae un botón, por ejemplo "Deshacer". */
  function toast(t, accion) {
    var el = document.getElementById('toast');
    el.innerHTML = esc(t) + (accion ? '<button type="button" class="toast-acc" data-acc="toast-deshacer">' + esc(accion.txt) + '</button>' : '');
    el.hidden = false; deshacerFn = accion ? accion.fn : null;
    clearTimeout(toast._t); toast._t = setTimeout(function () { el.hidden = true; deshacerFn = null; }, accion ? 6000 : 3500);
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
  function hecho(id) { var s = estadoDe(id); return s === 'realizado' || s === 'cobrado'; }
  /** (4-nov-2026, regla de Alejandro) una tarjeta sale de la agenda SOLO cuando está realizada Y cobrada, como en
   *  baños: un trabajo hecho que falta cobrar sigue a la vista, en azul, hasta que se cobre. */
  function completada(id) { return estadoDe(id) === 'cobrado'; }
  function fechaEf(f) { return E(f.id).fecha || f.fecha || (f.data && f.data.fecha) || ''; }
  /** Viva = en la agenda. Cancelada = la quitó el equipo desde la página (estado.eliminado) o el bot porque el cliente
   *  canceló (destape.eliminado). Oculta = la sacaron también de la lista de cancelados (data.oculto). */
  function vivo(f) { return !f.eliminado && !E(f.id).eliminado; }
  function esPrueba(f) { return /^prueba/i.test(String((f.data || {}).pedido_id || '')) || /^prueba/i.test(String((f.data || {}).cliente || '')); }
  function cancelada(f) { return (!!f.eliminado || !!E(f.id).eliminado) && !(f.data && f.data.oculto) && !esPrueba(f); }
  function motivoDe(f) { var n = E(f.id).nota; return n ? String(n) : (f.eliminado ? 'Canceló el cliente' : 'Se quitó de la agenda'); }
  function pctDe(f) { var p = f.data && Number(f.data.comision_pct); return p > 0 ? p : APP.pct; }
  function baseDe(f) { var v = Number(E(f.id).valor_final); return v > 0 ? v : (Number(f.data && f.data.precio_neto) || 0); }
  function comDe(f) { return Math.round(baseDe(f) * pctDe(f) / 100); }
  function atrasado(f) { var fe = fechaEf(f); return estadoDe(f.id) === 'pendiente' && !!fe && fe < hoyISO(0); }
  function telDe(f) { return String((f.data || {}).telefono || '').replace(/\D/g, ''); }
  /** El número va TODO JUNTO (+56912345678): así es un link de un toque, como en WhatsApp. */
  function telJunto(d) { return d ? '+' + d : ''; }

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
  function guardarFila(id, cambios) {
    return fetch(APP.url + '/rest/v1/destape?id=eq.' + encodeURIComponent(id), {
      method: 'PATCH', headers: Object.assign({ 'Content-Type': 'application/json', Prefer: 'return=minimal' }, H), body: JSON.stringify(cambios)
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }
  /** ¿La tarjeta se va de la lista que se está mirando con este cambio? (se anima al salir) */
  function seVa(id, cambios) {
    if (vista !== 'agenda') return false;
    if (cambios.eliminado) return true;
    if (cambios.estado === undefined) return false;
    var cobradoDespues = cambios.estado === 'cobrado';
    return modo === 'agenda' ? cobradoDespues : !cobradoDespues;
  }
  /** Cambio optimista: se pinta al tiro y se revierte si Supabase no lo guarda.
   *  op.deshacer = los valores de antes para el botón Deshacer del aviso. */
  function cambiar(id, cambios, okTxt, op) {
    op = op || {};
    var antes = Object.assign({}, E(id));
    est[id] = Object.assign({}, antes, cambios);
    lsSet(CK_EST, est);
    var card = document.querySelector('.dw[data-id="' + id + '"]');
    var anima = card && card.getBoundingClientRect && !sinMovimiento() && seVa(id, cambios);
    if (anima) { card.classList.add('saliendo'); setTimeout(pintar, 330); }
    else { resaltarId = seVa(id, cambios) ? null : id; pintar(); }
    return guardar(id, cambios).then(function () {
      if (okTxt) toast(okTxt, op.deshacer ? { txt: 'Deshacer', fn: function () { cambiar(id, op.deshacer, 'Listo, quedó como estaba'); } } : null);
    }).catch(function () {
      est[id] = antes; lsSet(CK_EST, est); pintar();
      toast('No se pudo guardar. Revisa la señal e intenta de nuevo.');
      throw new Error('no-guardado');
    });
  }

  function cargar() {
    var aviso = document.getElementById('aviso-red');
    Promise.all([
      pedir('destape?select=id,fecha,informado_at,data,eliminado&order=informado_at.desc&limit=400'),
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
      // Si ya está cobrado, se abre "Ver completadas".
      modo = completada(id) ? 'completadas' : 'agenda';
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
  /** El WhatsApp al cliente ("Avisar al cliente que voy"): sin la marca URGENTE ni raya larga. */
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

  /** La frase corta que explica el color de la tarjeta y qué toca hacer ahora. */
  function hintDe(f) {
    var id = f.id, st = estadoDe(id), e = E(id);
    if (st === 'cobrado') return { c: 'oro', t: '🟡 Cobrado ' + (Number(e.valor_final) > 0 ? clp(e.valor_final) + ' · comisión ' + clp(comDe(f)) : '· falta el valor final') };
    if (st === 'realizado') return { c: 'azul', t: '🔵 Realizado · falta cobrar. Toca Cobrado cuando te paguen' };
    if (atrasado(f)) return { c: 'rojo', t: '🔴 Muévelo de día, márcalo realizado o quítalo' };
    if (e.contactado) return { c: 'verde', t: '🟢 Cliente avisado · listo para ir' };
    return { c: '', t: '⚪ Por hacer · avísale al cliente que vas' };
  }

  function wrap(f) {
    var id = f.id, st = estadoDe(id), e = E(id), d = f.data || {};
    var fe = fechaEf(f), orig = f.fecha || '';
    var tel = telDe(f);
    var hora = horaEquipo(d.hora), min = minutosDe(hora);
    var contactado = !!e.contactado, atr = atrasado(f), cob = st === 'cobrado', real = hecho(id);
    var reag = e.fecha && orig && e.fecha !== orig;
    var cls = cob ? ' is-cobrado' : st === 'realizado' ? ' is-realizado' : atr ? ' is-atrasado' : (contactado ? ' is-contactado' : '');
    if (!primeraVez && !vistos[id]) cls += ' nueva';
    if (resaltarId === id) cls += ' foco';
    // Barra de arriba, como en baños: la fecha (se mueve de día ahí mismo) y los dos botones de estado.
    var gt = '<div class="gt">'
      + '<label class="gt-fecha"><input type="date" class="fecha-input" data-acc="fecha" value="' + esc(fe) + '" aria-label="Mover de día"></label>'
      + '<div class="gt-estados" role="group" aria-label="Estado">'
      + '<button type="button" class="est-btn b-real' + (real ? ' activo' : '') + '" data-acc="realizado">' + (real ? '✓ Realizado' : 'Realizado') + '</button>'
      + '<button type="button" class="est-btn b-cob' + (cob ? ' activo' : '') + '" data-acc="cobrar">' + (cob ? '✓ Cobrado' : 'Cobrado') + '</button></div>'
      + (atr ? '<div class="chip-atr">⚠️ Atrasado · era el ' + esc(diaLargo(fe)) + '</div>' : '')
      + (reag && !atr ? '<div class="chip-reag">📅 Cambiado al ' + esc(diaLargo(fe)) + '. Era el ' + esc(diaLargo(orig)) + '</div>' : '')
      + '</div>';
    var neto = Number(d.precio_neto) || 0, vf = Number(e.valor_final) > 0 ? Number(e.valor_final) : 0;
    // (31-oct-2026, p-753) un rango de precios: el piso es precio_neto (la comisión aprox. va sobre él) y el techo precio_hasta
    var hasta = Number(d.precio_hasta) || 0, rango = neto > 0 && hasta > neto ? clp(neto) + ' a ' + clp(hasta) : '';
    var valor;
    if (cob) {
      valor = '<div class="dw-valor cob">' + (vf ? '' : '<span class="falta-vf">⚠️ Falta el valor final</span>')
        + (vf ? 'Se cobró <b>' + clp(baseDe(f)) + '</b>' : rango ? 'Valor <b>' + rango + '</b>' : 'Desde <b>' + clp(baseDe(f)) + '</b>')
        + '<span class="nota">Comisión ' + pctDe(f) + ' %' + (vf ? '' : ' aprox.') + ': ' + clp(comDe(f)) + (e.comision_pagada ? '. Ya pagada' : '') + '</span></div>';
    } else if (!vf && rango) {
      valor = '<div class="dw-valor">Valor <b>' + rango + '</b><span class="nota">' + esc('Se confirma en terreno. ' + ivaTxt(d, neto)) + '</span></div>';
    } else if (vf || neto) {
      valor = '<div class="dw-valor">' + (vf ? 'Valor final' : 'Desde') + ' <b>' + clp(vf || neto) + '</b><span class="nota">' + esc(ivaTxt(d, vf || neto)) + '</span></div>';
    } else valor = '<div class="dw-valor"><b>Valor a confirmar en terreno</b></div>';
    var servicio = d.servicio || 'Destape', trabajo = d.trabajo || '';
    var problema = trabajo && trabajo.trim().toLowerCase() !== servicio.trim().toLowerCase() ? '<div class="dw-linea dw-prob">🛠️ ' + esc(cap(trabajo)) + '</div>' : '';
    var lineas = '';
    if (d.acceso) lineas += '<div class="dw-linea">🚪 ' + esc(d.acceso) + '</div>';
    if (d.nota) lineas += '<div class="dw-linea nota-imp">📝 ' + esc(d.nota) + '</div>';
    var contacto = '';
    if (tel && st === 'pendiente') {
      contacto = contactado ? '<div class="btn-contacto hecho">✓ Cliente avisado</div>'
        : '<button type="button" class="btn-contacto" data-acc="contactar">💬 Avisar al cliente que voy</button>';
    }
    var mapa = mapaDe(d), acc = '';
    var cobrandoAca = cobrando === id && vista === 'agenda';
    // Accesos siempre a la vista. El WhatsApp se esconde solo cuando el botón verde de arriba ya va a WhatsApp.
    if (tel && !(st === 'pendiente' && !contactado)) acc += '<a class="acc acc-wa' + (cob ? ' suave' : '') + '" href="https://wa.me/' + tel + '" target="_blank" rel="noopener">WhatsApp</a>';
    if (tel) acc += '<a class="acc acc-tel" href="tel:+' + tel + '">📞 Llamar</a>';
    if (mapa && !cob) acc += '<a class="acc acc-map" href="' + esc(mapa) + '" target="_blank" rel="noopener">🗺️ Llegar</a>';
    var conf = confirmando === id
      ? '<div class="confirma">¿Quitar este destape de la agenda?'
        + '<input type="text" class="motivo-in" data-acc="motivo" maxlength="120" placeholder="Motivo, si quieres (por ejemplo: no quiso el precio)" value="' + esc(borrador['motivo:' + id] || '') + '">'
        + '<div class="conf-acc"><button type="button" class="si" data-acc="quitar-si">Sí, quitar</button><button type="button" class="no" data-acc="quitar-no">No</button></div></div>'
      : (cob ? '' : '<button type="button" class="quitar" data-acc="quitar">✕ Quitar de la agenda (se canceló o no se hizo)</button>');
    var h = hintDe(f);
    return '<div class="dw' + cls + '" data-id="' + esc(id) + '">' + gt
      + '<div class="dw-card"><div class="estado-hint ' + h.c + '">' + esc(h.t) + '</div>'
      + '<span class="hora-pill' + (real ? ' hecho' : min === null ? ' sin' : '') + '">🕐 ' + esc(hora ? horaBonita(hora) : 'Horario por confirmar') + '</span>'
      + '<div class="dw-serv">' + (ICONOS[d.servicio_clave] || '🔧') + ' ' + esc(servicio) + '</div>'
      + problema
      + '<div class="dw-dir">📍 ' + dirHtml(d) + '</div>'
      + '<div class="dw-cli">👤 ' + esc(d.cliente || 'Cliente sin nombre') + (tel ? ' · <a href="tel:+' + tel + '">' + esc(telJunto(tel)) + '</a>' : '') + '</div>'
      + valor + lineas + contacto
      + (acc && !cobrandoAca ? '<div class="accesos">' + acc + '</div>' : '')
      + (cobrandoAca ? cobroHtml(f) : '')
      + conf + '</div></div>';
  }

  // ── agenda ─────────────────────────────────────────────────────────────
  /** Agrupa por día. Por hacer: primero "Atrasados" (un grupo, cada tarjeta dice su fecha), después hoy y lo que
   *  viene. Completadas (cobrados): por día, lo más reciente arriba. */
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
        if (fa !== fb) return (fa < fb ? -1 : 1) * (reciente ? -1 : 1);
        // por hora programada; los que no tienen hora exacta van al final del día
        var ma = minutosDe(a.data && a.data.hora), mb = minutosDe(b.data && b.data.hora);
        if (ma !== mb) { if (ma === null) return 1; if (mb === null) return -1; return ma - mb; }
        return (b.informado_at || '') < (a.informado_at || '') ? -1 : 1;
      }) };
    });
  }
  /** "miércoles 4 nov": más corto que el largo, para que quepa la barra de avance al lado. */
  function diaMedio(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return 'Sin fecha';
    var p = iso.split('-'), d = new Date(+p[0], +p[1] - 1, +p[2]);
    return DIAS[d.getDay()] + ' ' + d.getDate() + ' ' + MESES[d.getMonth()].slice(0, 3);
  }
  function titDia(k, conBarra) {
    var hoy = hoyISO(0), dia = conBarra ? diaMedio : diaLargo;
    if (k === 'sin') return { t: 'Sin fecha', c: '' };
    if (k === 'atrasados') return { t: '⚠️ Atrasados', c: ' atrasado' };
    if (k === hoy) return { t: 'Hoy · ' + dia(k), c: ' hoy' };
    if (k === hoyISO(1)) return { t: 'Mañana · ' + dia(k), c: '' };
    return { t: cap(dia(k)), c: '' };
  }
  /** Barra de avance del día (hechos / todos los de ese día), como la de baños. */
  function progHtml(k, vivos) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) return '';
    var total = 0, hechos = 0;
    vivos.forEach(function (f) { if (fechaEf(f) === k) { total++; if (hecho(f.id)) hechos++; } });
    if (!total) return '';
    var pct = Math.round(hechos * 100 / total);
    return '<span class="prog"><span class="prog-bar"><span class="prog-fill" style="width:' + pct + '%">' + (pct ? '<span class="prog-truck">🚛</span>' : '') + '</span></span>'
      + '<span class="prog-num">' + hechos + '/' + total + '</span></span>';
  }
  function pintarAgenda() {
    var cont = document.getElementById('agenda');
    var vivos = filas.filter(vivo);
    // A la vista: lo pendiente y lo realizado sin cobrar. Completadas: solo lo cobrado (realizado y pagado).
    var lista0 = vivos.filter(function (f) { return !completada(f.id); }), comp = vivos.filter(function (f) { return completada(f.id); });
    var pend = lista0.filter(function (f) { return estadoDe(f.id) === 'pendiente'; }), real = lista0.filter(function (f) { return estadoDe(f.id) === 'realizado'; });
    if (modo === 'completadas' && !comp.length) modo = 'agenda';
    var hist = modo === 'completadas', lista = hist ? comp : lista0;
    var html = '';
    if (comp.length) {
      html += '<button type="button" class="ver-ant' + (hist ? ' modo-activo' : '') + '" data-acc="modo" data-modo="' + (hist ? 'agenda' : 'completadas') + '">'
        + (hist ? '← Volver a ver los por hacer' : '✓ Ver completadas (' + comp.length + ')') + '</button>';
      if (hist) html += '<p class="modo-titulo">👀 Estás viendo los destapes ya cobrados</p>'
        + '<div class="resumen-comp">' + comp.length + (comp.length === 1 ? ' cobrado' : ' cobrados') + '</div>';
    }
    agrupar(lista, hist).forEach(function (gr) {
      var barra = hist ? '' : progHtml(gr.k, vivos), t = titDia(gr.k, !!barra);
      html += '<section data-grupo="' + esc(gr.k) + '"><h2 class="dia-tit' + t.c + '"><span class="dia-txt">' + esc(t.t) + '</span>'
        + (barra || '<span class="dia-n">' + gr.items.length + '</span>') + '</h2>'
        + gr.items.map(wrap).join('') + '</section>';
    });
    if (!lista.length) html += '<p class="vacio">No hay destapes por hacer. Cuando el bot confirme uno, aparece acá solo.'
      + (comp.length ? '<small>Los ya cobrados están en Ver completadas.</small>' : '') + '</p>';
    cont.innerHTML = html;
    cont.classList.toggle('anim-entrar', animarLista); animarLista = false;
    var nAtr = pend.filter(atrasado).length;
    document.getElementById('hdr-pend').textContent = pend.length;
    document.getElementById('hdr-cobrar').textContent = real.length ? ' · ' + real.length + ' por cobrar' : '';
    document.getElementById('hdr-atr').textContent = nAtr ? ' · ' + nAtr + (nAtr === 1 ? ' atrasado' : ' atrasados') : '';
    document.body.classList.toggle('modo-completadas', hist && vista === 'agenda');
  }

  // ── comisión ───────────────────────────────────────────────────────────
  function desel() { return lsGet(CK_DESEL, {}); }
  function seleccion() {
    var d = desel();
    return porPagar().filter(function (f) { return !d[f.id]; });
  }
  function porPagar() { return filas.filter(function (f) { return vivo(f) && estadoDe(f.id) === 'cobrado' && !E(f.id).comision_pagada; }); }
  function suma(a) { return a.reduce(function (s, f) { return s + comDe(f); }, 0); }
  function detalleHtml(f) {
    var d = f.data || {}, e = E(f.id), tel = telDe(f), vf = Number(e.valor_final) > 0;
    return '<div class="com-detalle">'
      + '<div>' + (ICONOS[d.servicio_clave] || '🔧') + ' ' + esc(d.servicio || 'Destape') + (d.trabajo && d.trabajo !== d.servicio ? ' · ' + esc(d.trabajo) : '') + '</div>'
      + '<div>📍 ' + esc([d.direccion, d.comuna].filter(Boolean).join(', ') || 'sin dirección') + '</div>'
      + '<div>📅 ' + esc(cap(diaLargo(fechaEf(f)))) + (horaEquipo(d.hora) ? ' · ' + esc(horaBonita(horaEquipo(d.hora))) : '') + '</div>'
      + '<div>👤 ' + esc(d.cliente || 'Cliente sin nombre') + (tel ? ' · <a href="tel:+' + tel + '">' + esc(telJunto(tel)) + '</a>' : '') + '</div>'
      + '<div>💵 ' + (vf ? 'Se cobró ' + clp(baseDe(f)) : 'Desde ' + clp(baseDe(f)) + ' (falta el valor final)') + ' · comisión ' + pctDe(f) + ' %: <b>' + clp(comDe(f)) + '</b></div>'
      + '</div>';
  }
  /** tipo: 'deuda' (cobrado sin pagar), 'falta' (realizado, falta cobrar) o 'pagada'. */
  function item(f, tipo) {
    var id = f.id, e = E(id), d = f.data || {}, vf = Number(e.valor_final) > 0, tel = telDe(f);
    var chk = tipo === 'deuda' ? '<input type="checkbox" class="com-check" data-acc="sel" data-id="' + esc(id) + '"' + (desel()[id] ? '' : ' checked') + ' aria-label="Incluir en el pago">' : '';
    var acc = '';
    if (cobrando === id && vista === 'comision') acc = cobroHtml(f);
    else {
      acc = '<div class="com-acciones">';
      // El botón que mueve plata va solo en su fila, grande. Debajo, WhatsApp e info.
      if (tipo === 'falta') acc += '<button type="button" class="com-cobrar ancho" data-acc="cobrar">💰 Cobrado, poner el valor</button>';
      else if (tipo === 'deuda' && !vf) acc += '<button type="button" class="com-cobrar ancho" data-acc="cobrar">✏️ Poner el valor final</button>';
      if (tel) acc += '<a class="com-wa" href="https://wa.me/' + tel + '" target="_blank" rel="noopener">Revisar en WhatsApp</a>';
      acc += '<button type="button" class="com-info" data-acc="info">📋 ' + (infoAbierta[id] ? 'Cerrar la info' : 'Ver toda la info') + '</button></div>';
      if (infoAbierta[id]) acc += detalleHtml(f) + (tipo === 'deuda' && vf ? '<div class="com-acciones"><button type="button" class="com-info" data-acc="cobrar">✏️ Corregir el valor cobrado</button></div>' : '');
    }
    var rev = tipo === 'pagada' ? '<div class="com-acciones"><span class="com-pagada-tag">✓ Pagada</span><button type="button" class="com-revocar" data-acc="revocar">Revocar</button></div>' : '';
    var sub = tipo === 'falta' ? 'Hecho, falta cobrar' : (vf ? 'Se cobró ' + clp(baseDe(f)) : '⚠️ Falta el valor final') + ' · ' + pctDe(f) + ' %';
    return '<div class="com-card' + (tipo === 'pagada' ? ' pagada' : tipo === 'falta' ? ' falta' : '') + '" data-id="' + esc(id) + '">'
      + '<div class="com-top">' + chk
      + '<div class="com-main"><div class="com-cli">' + esc(d.cliente || d.servicio || 'Destape') + '</div>'
      + '<div class="com-dir">📍 ' + esc(d.comuna || d.direccion || '') + ' · ' + esc(diaCorto(fechaEf(f))) + '</div>'
      + '<div class="com-dir">' + esc(sub) + '</div></div>'
      + '<div class="com-monto">' + clp(comDe(f)) + '<small>' + (tipo !== 'pagada' && !vf ? 'comisión aprox.' : 'comisión') + '</small></div></div>'
      + rev + acc + '</div>';
  }
  function pintarComision() {
    var vivos = filas.filter(vivo);
    var deuda = porPagar(), total = suma(deuda);
    var real = vivos.filter(function (f) { return estadoDe(f.id) === 'realizado'; });
    var pagadas = vivos.filter(function (f) { return estadoDe(f.id) === 'cobrado' && E(f.id).comision_pagada; });
    var html = '<div class="cp"><div class="cp-titulo">💰 Comisión a pagar</div>'
      + '<div class="com-deuda' + (total ? '' : ' al-dia') + '"><span>' + (total ? 'Por pagar a Alejandro (cobrados sin pagar)' : 'Estás al día') + '</span><b>' + (total ? clp(total) : '✓') + '</b></div>'
      + '<div class="com-nota">Es el ' + APP.pct + ' % de lo que se cobró en cada destape.' + (pagadas.length ? ' Ya pagado: ' + clp(suma(pagadas)) + '.' : '') + '</div>';
    if (deuda.length) html += '<div class="com-sec-tit">Selecciona las que vas a pagar · ' + deuda.length + '</div>' + deuda.map(function (f) { return item(f, 'deuda'); }).join('');
    if (real.length) html += '<div class="com-sec-tit cobrar">Hechos, falta cobrar · ' + real.length + '</div>' + real.map(function (f) { return item(f, 'falta'); }).join('');
    if (pagadas.length) {
      var g = {};
      pagadas.forEach(function (f) { var k = (E(f.id).pagada_at || '').slice(0, 10) || 'sin-fecha'; (g[k] = g[k] || []).push(f); });
      var ks = Object.keys(g).sort();
      html += '<div class="com-sec-tit">Mis pagos hechos · ' + clp(suma(pagadas)) + '</div>';
      ks.slice().reverse().forEach(function (k) {
        html += '<div class="pago-grupo"><div class="pago-head"><span class="pago-tit">Pago ' + (ks.indexOf(k) + 1) + (k !== 'sin-fecha' ? ' · ' + esc(diaLargo(k)) : '') + '</span><span class="pago-tot">' + clp(suma(g[k])) + '</span></div>'
          + g[k].map(function (f) { return item(f, 'pagada'); }).join('') + '</div>';
      });
    }
    if (!vivos.length) html += '<p class="vacio">Sin destapes todavía.</p>';
    html += '</div>';
    document.getElementById('comision').innerHTML = html;
    var sel = seleccion(), btn = document.getElementById('btn-pagar');
    document.getElementById('barra-pagar').hidden = vista !== 'comision' || !deuda.length || !!cobrando;
    btn.disabled = !sel.length;
    btn.textContent = sel.length ? 'Pagar ' + clp(suma(sel)) + ' (' + sel.length + ')' : 'Marca lo que vas a pagar';
    document.getElementById('hdr-com').textContent = total ? clp(total) : 'al día';
    document.body.classList.toggle('vista-comision', vista === 'comision');
  }

  // ── cancelados (al pie de la página): lo que se perdió y por qué ────────
  function pintarCancelados() {
    var cont = document.getElementById('cancelados'); if (!cont) return;
    var lista = filas.filter(cancelada).sort(function (a, b) { return fechaEf(a) < fechaEf(b) ? 1 : -1; });
    var btn = document.getElementById('btn-cancelados');
    if (!lista.length) { cont.innerHTML = ''; cont.hidden = true; if (btn) btn.hidden = true; cancelAbierto = false; return; }
    if (btn) { btn.hidden = false; btn.textContent = (cancelAbierto ? '▴ Cerrar cancelados' : '✕ Ver cancelados') + ' (' + lista.length + ')'; btn.classList.toggle('abierto', cancelAbierto); }
    cont.hidden = !cancelAbierto;
    if (!cancelAbierto) { cont.innerHTML = ''; return; }
    var perdido = lista.reduce(function (s, f) { return s + baseDe(f); }, 0), comPerdida = lista.reduce(function (s, f) { return s + comDe(f); }, 0);
    var html = '<div class="canc-hero"><div class="r">Cancelados · lo que se perdió</div>'
      + '<div class="v">' + clp(perdido) + '</div><div class="s">en trabajos que no se hicieron · comisión perdida ' + clp(comPerdida) + '</div></div>';
    html += lista.map(function (f) {
      var d = f.data || {}, tel = telDe(f);
      return '<div class="canc" data-id="' + esc(f.id) + '">'
        + '<div class="canc-top"><div class="canc-main"><div class="canc-serv">' + (ICONOS[d.servicio_clave] || '🔧') + ' ' + esc(d.servicio || 'Destape') + '</div>'
        + '<div class="canc-dir">👤 ' + esc(d.cliente || 'Cliente sin nombre') + (tel ? ' · <a href="tel:+' + tel + '">' + esc(telJunto(tel)) + '</a>' : '') + '</div>'
        + '<div class="canc-dir">📍 ' + esc(d.comuna || d.direccion || '') + ' · ' + esc(diaCorto(fechaEf(f))) + '</div>'
        + '<div class="canc-motivo">✕ ' + esc(motivoDe(f)) + '</div></div>'
        + '<div class="canc-monto">' + clp(baseDe(f)) + '<small>comisión ' + clp(comDe(f)) + '</small></div></div>'
        + '<div class="canc-acc"><button type="button" class="canc-volver" data-acc="restaurar">↩ Volver a la agenda</button>'
        + '<button type="button" class="canc-sacar" data-acc="ocultar">Sacar de acá</button></div></div>';
    }).join('');
    cont.innerHTML = html;
  }

  function pintar() {
    pintarAgenda(); pintarComision(); pintarCancelados();
    document.querySelectorAll('.vista').forEach(function (v) { v.hidden = v.getAttribute('data-vista') !== vista; });
    document.querySelectorAll('.vista-btn').forEach(function (b) { b.classList.toggle('activo', b.getAttribute('data-vista') === vista); });
    if (resaltarId) { var id = resaltarId; resaltarId = null; setTimeout(function () { var el = document.querySelector('.dw[data-id="' + id + '"]'); if (el && el.classList) el.classList.remove('foco'); }, 2600); }
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
    if (t.classList.contains('vista-btn')) { vista = t.getAttribute('data-vista'); cobrando = null; animarLista = true; pintar(); window.scrollTo(0, 0); return; }
    var w = t.closest('[data-id]'), id = w && w.getAttribute('data-id');
    var acc = t.getAttribute('data-acc');
    if (acc === 'toast-deshacer') { var fn = deshacerFn; deshacerFn = null; document.getElementById('toast').hidden = true; if (fn) fn(); return; }
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
      if (st === 'cobrado') { toast('Ya está cobrado. Si no se cobró, ábrelo con Cobrado y toca "No se cobró".'); return; }
      if (st === 'pendiente') cambiar(id, { estado: 'realizado' }, 'Realizado. Falta cobrar.', { deshacer: { estado: 'pendiente' } }).catch(function () {});
      else cambiar(id, { estado: 'pendiente' }, 'Vuelve a por hacer.', { deshacer: { estado: 'realizado' } }).catch(function () {});
    } else if (acc === 'cobrar') abrirCobro(id);
    else if (acc === 'cobro-no') { cobrando = null; delete borrador[id]; pintar(); }
    else if (acc === 'cobro-ok') {
      var c = t.closest('.cobro'), inp = c && c.querySelector('.cobro-in');
      guardarCobro(id, inp ? inp.value : '');
    } else if (acc === 'descobrar') {
      if (E(id).comision_pagada) { toast('Su comisión ya está pagada. Revoca el pago antes.'); return; }
      cobrando = null; delete borrador[id];
      cambiar(id, { estado: 'realizado' }, 'Ya no figura como cobrado. Queda en falta cobrar.', { deshacer: { estado: 'cobrado' } }).catch(function () {});
    } else if (acc === 'quitar') { confirmando = id; pintar(); var mi = document.querySelector('.dw[data-id="' + id + '"] .motivo-in'); if (mi && mi.focus) mi.focus(); }
    else if (acc === 'quitar-no') { confirmando = null; delete borrador['motivo:' + id]; pintar(); }
    else if (acc === 'quitar-si') {
      var motivo = String(borrador['motivo:' + id] || '').trim(); confirmando = null; delete borrador['motivo:' + id];
      cambiar(id, { eliminado: true, nota: motivo || null }, 'Quitado de la agenda. Queda en Cancelados.', { deshacer: { eliminado: false, nota: null } }).catch(function () {});
    } else if (acc === 'ver-cancelados') { cancelAbierto = !cancelAbierto; pintar(); if (cancelAbierto) { var sc = document.getElementById('cancelados'); if (sc && sc.scrollIntoView) sc.scrollIntoView({ block: 'start' }); } }
    else if (acc === 'restaurar') {
      // vuelve a la agenda: la marca del equipo y, si la canceló el bot, también la de la fila
      var fr = fila(id); if (!fr) return;
      if (fr.eliminado) { fr.eliminado = false; guardarFila(id, { eliminado: false }).catch(function () { fr.eliminado = true; pintar(); toast('No se pudo guardar. Revisa la señal e intenta de nuevo.'); }); }
      cambiar(id, { eliminado: false, nota: null }, 'Vuelve a la agenda.').catch(function () {});
    } else if (acc === 'ocultar') {
      var fo = fila(id); if (!fo) return;
      var dataAntes = fo.data; fo.data = Object.assign({}, fo.data || {}, { oculto: true }); pintar();
      guardarFila(id, { data: fo.data }).then(function () { toast('Sacado de cancelados.'); }).catch(function () { fo.data = dataAntes; pintar(); toast('No se pudo guardar. Revisa la señal e intenta de nuevo.'); });
    }
    else if (acc === 'modo') { modo = t.getAttribute('data-modo') || 'agenda'; cobrando = null; animarLista = true; pintar(); window.scrollTo(0, 0); }
    else if (acc === 'info') { infoAbierta[id] = !infoAbierta[id]; pintarComision(); }
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
    var t = ev.target; if (!t.getAttribute) return;
    if (t.getAttribute('data-acc') === 'motivo') { var wm = t.closest('[data-id]'); if (wm) borrador['motivo:' + wm.getAttribute('data-id')] = t.value; return; }
    if (t.getAttribute('data-acc') !== 'monto') return;
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
    cambiar(id, cambio, v ? 'Movido al ' + diaLargo(v) : 'Vuelve a su fecha original').catch(function () {});
  });
  document.getElementById('btn-pagar').addEventListener('click', abrirPago);
  document.querySelector('.m-ok').addEventListener('click', confirmarPago);
  document.querySelector('.m-no').addEventListener('click', function () { document.getElementById('modal').hidden = true; });
  document.querySelector('.m-copiar').addEventListener('click', function () {
    var b = APP.banco, t = b.titular + '\n' + b.banco + '\nCuenta RUT ' + b.cuenta + '\n' + b.email;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { toast('Datos copiados'); }).catch(function () { toast(t); });
  });
  window.addEventListener('resize', medirHeader);
  window.addEventListener('hashchange', irAlHash);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) cargar(); });
  // Pruebas sin navegador: expone la lógica pura.
  window.__DESTAPES__ = { comDe: comDe, baseDe: baseDe, fechaEf: fechaEf, estadoDe: estadoDe, porPagar: porPagar,
    clp: clp, leerMonto: leerMonto, conFactura: conFactura, abrirCobro: abrirCobro, guardarCobro: guardarCobro,
    horaLimpia: horaLimpia, horaEquipo: horaEquipo, msgCliente: msgCliente, hintDe: hintDe, cancelada: cancelada, motivoDe: motivoDe,
    _cancelados: function (v) { cancelAbierto = v; }, _confirmar: function (id) { confirmando = id; }, _motivo: function (id, t) { borrador['motivo:' + id] = t; },
    pintar: function () { pintar(); }, _modo: function (m, v) { modo = (m === 'realizados' || m === 'cobrados') ? 'completadas' : m; if (v) vista = v; },
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
  <div class="sub"><b id="hdr-pend"><span class="skel" style="width:14px"></span></b> por hacer<span id="hdr-cobrar"></span><span id="hdr-atr"></span> · <span id="hdr-act">Cargando...</span></div>
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
<div class="pie-canc"><button type="button" id="btn-cancelados" class="ver-canc" data-acc="ver-cancelados" hidden>✕ Ver cancelados</button>
<div id="cancelados" class="cancelados" hidden></div></div>
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
