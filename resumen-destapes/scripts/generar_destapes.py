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
}


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
clp = gl.clp


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
    hora = d.get("hora") or "Horario a coordinar"
    neto = int(solo_digitos(d.get("precio_neto")) or 0)
    fac = str(d.get("factura") or "").lower()
    iva_txt = ("Con factura, más IVA" if fac.startswith("si") or fac.startswith("sí")
               else "Sin factura" if fac.startswith("no") else "Si pide factura se suma el IVA")
    valor = (f'<div class="dc-valor">desde <b>{esc(clp(neto))}</b> neto'
             f'<span class="dc-iva">{esc(iva_txt)}. El valor final se confirma en terreno.</span></div>'
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


CSS = r"""
:root { --azul:#1F5AA8; --azul-2:#163F78; --tinta:#0F172A; --gris:#64748B; --linea:#E2E8F0; --fondo:#F1F5F9;
  --card:#fff; --suave:#F8FAFC; --verde:#166534; --verde-bg:#F0FDF4; --verde-br:#BBF7D0;
  --ambar:#92400E; --ambar-bg:#FEF3C7; --rojo:#B91C1C; --rojo-bg:#FEF2F2; --violeta:#5B21B6; --violeta-bg:#EDE9FE;
  --skel-a:#E2E8F0; --skel-b:#EDF2F7; color-scheme:light dark; }
@media (prefers-color-scheme: dark) {
  :root { --azul:#3B82F6; --azul-2:#1E3A8A; --tinta:#E5E7EB; --gris:#94A3B8; --linea:#273244; --fondo:#0B1220;
    --card:#111A2B; --suave:#0F1726; --verde:#4ADE80; --verde-bg:#0F2A1C; --verde-br:#166534;
    --ambar:#FCD34D; --ambar-bg:#3A2A06; --rojo:#F87171; --rojo-bg:#3A1212; --violeta:#C4B5FD; --violeta-bg:#2A1F4A;
    --skel-a:#1E293B; --skel-b:#273449; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
[hidden] { display:none !important; }
html, body { max-width:100%; overflow-x:hidden; }
body { margin:0; background:var(--fondo); color:var(--tinta);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:16px; line-height:1.45; padding-bottom:calc(90px + env(safe-area-inset-bottom)); }
header { position:sticky; top:0; z-index:20; background:var(--azul-2); color:#fff;
  padding:max(14px,env(safe-area-inset-top)) 18px 14px; box-shadow:0 2px 8px rgba(0,0,0,.2); }
@media (prefers-color-scheme: light) { header { background:var(--azul); } }
header h1 { margin:0; font-size:19px; }
header .sub { margin-top:3px; font-size:13px; opacity:.9; }
.hdr-com { font-weight:700; }
header .skel { display:inline-block; vertical-align:middle; height:11px; width:70px; border-radius:6px;
  background:rgba(255,255,255,.3); }
main { max-width:560px; margin:0 auto; padding:12px 12px 30px; opacity:0; transition:opacity .25s;
  animation:velo 0s linear 10s forwards; }
main.listo { opacity:1; }
@keyframes velo { to { opacity:1; } }
body.listo #skel { display:none; }
#skel { max-width:560px; margin:0 auto; padding:12px 12px 0; }
.sk { border-radius:12px; margin-bottom:10px;
  background:linear-gradient(90deg,var(--skel-a) 25%,var(--skel-b) 45%,var(--skel-a) 65%);
  background-size:400% 100%; animation:brillo 1.3s ease-in-out infinite; }
.sk-tabs { height:46px; } .sk-tit { height:14px; width:40%; margin:16px 4px 10px; } .sk-card { height:150px; }
@keyframes brillo { 0% { background-position:100% 0; } 100% { background-position:0 0; } }
@media (prefers-reduced-motion: reduce) { .sk { animation:none; } }
.aviso-red { background:var(--ambar-bg); color:var(--ambar); border-radius:10px; padding:8px 12px; font-size:13px; margin-bottom:10px; }
.vistas { display:flex; gap:8px; margin-bottom:6px; }
.vista-btn { flex:1 1 0; min-height:46px; border-radius:11px; border:1px solid var(--linea); background:var(--card);
  color:var(--tinta); font:inherit; font-weight:700; font-size:15px; cursor:pointer; }
.vista-btn.activo { background:var(--azul); border-color:var(--azul); color:#fff; }
.dia-tit { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:800; text-transform:uppercase;
  letter-spacing:.5px; color:var(--gris); margin:16px 0 8px; padding:6px 4px; position:sticky; top:var(--hdr-h,70px);
  z-index:5; background:var(--fondo); }
.dia-tit.atrasado { color:var(--rojo); }
.dia-tit.hoy { color:var(--azul); }
.dia-n { margin-left:auto; background:var(--card); border:1px solid var(--linea); border-radius:20px; padding:1px 9px; font-size:12px; }
.dw { background:var(--card); border:1px solid var(--linea); border-radius:14px; margin-bottom:12px; overflow:hidden;
  box-shadow:0 1px 2px rgba(15,23,42,.05); transition:opacity .3s, transform .3s; }
.dw.is-realizado { border-color:#93C5FD; }
.dw.is-cobrado { border-color:var(--verde-br); background:var(--verde-bg); }
.dw.foco { box-shadow:0 0 0 3px var(--azul); }
.dw-estado { display:flex; flex-wrap:wrap; align-items:center; gap:6px; padding:10px 14px 0; }
.chip { font-size:11px; font-weight:800; padding:3px 9px; border-radius:20px; text-transform:uppercase; letter-spacing:.4px; }
.chip.pend { background:var(--suave); color:var(--gris); border:1px solid var(--linea); }
.chip.real { background:#DBEAFE; color:#1E40AF; }
.chip.cob { background:#DCFCE7; color:#166534; }
.chip.reag { background:var(--rojo-bg); color:var(--rojo); }
.chip.nuevo { background:var(--violeta-bg); color:var(--violeta); }
@media (prefers-color-scheme: dark) { .chip.real { background:#172554; color:#93C5FD; } .chip.cob { background:#052E16; color:#86EFAC; } }
.dc { padding:10px 14px 4px; }
.dc-top { display:flex; justify-content:space-between; gap:10px; align-items:baseline; }
.dc-serv { font-weight:800; font-size:17px; }
.dc-hora { font-size:14px; color:var(--gris); white-space:nowrap; font-variant-numeric:tabular-nums; }
.dc-dir { margin-top:6px; overflow-wrap:anywhere; }
.dc-falta { color:var(--rojo); font-weight:700; }
.dc-valor { margin-top:8px; background:var(--verde-bg); border:1px solid var(--verde-br); border-radius:10px; padding:8px 12px; color:var(--verde); }
.dc-valor b { font-size:20px; font-variant-numeric:tabular-nums; }
.dc-iva { display:block; font-size:12.5px; opacity:.9; }
.dc-cli { margin-top:8px; font-size:15px; }
.dc-linea { margin-top:6px; font-size:14px; color:var(--gris); }
.dc-acc { display:flex; gap:8px; margin-top:10px; }
.dc-btn { flex:1 1 0; display:flex; align-items:center; justify-content:center; gap:6px; min-height:44px; border-radius:10px;
  text-decoration:none; color:#fff; font-weight:700; font-size:14px; }
.dc-wa { background:#16A34A; } .dc-tel { background:#2563EB; } .dc-map { background:#475569; }
.dc-btn:active { filter:brightness(.92); }
.dw-ctl { padding:10px 14px 14px; display:grid; gap:10px; }
.est-row { display:flex; gap:8px; }
.est-btn { flex:1 1 0; min-height:46px; border-radius:10px; font:inherit; font-weight:800; font-size:15px; cursor:pointer;
  border:2px solid var(--linea); background:var(--card); color:var(--tinta); }
.est-btn.on.b-real { background:#2563EB; border-color:#2563EB; color:#fff; }
.est-btn.on.b-cob { background:#16A34A; border-color:#16A34A; color:#fff; }
.fila2 { display:flex; gap:8px; }
.campo { flex:1 1 0; display:flex; flex-direction:column; gap:3px; font-size:12px; font-weight:700; color:var(--gris);
  text-transform:uppercase; letter-spacing:.4px; min-width:0; }
.campo input { font:inherit; font-size:16px; min-height:44px; border-radius:10px; border:1px solid var(--linea);
  background:var(--suave); color:var(--tinta); padding:6px 10px; width:100%; text-transform:none; letter-spacing:0; }
.campo small { font-weight:500; text-transform:none; letter-spacing:0; font-size:12px; }
.com-linea { font-size:13px; color:var(--gris); }
.com-linea b { color:var(--tinta); }
.quitar { justify-self:end; background:none; border:none; color:var(--rojo); font:inherit; font-size:13px; font-weight:700;
  cursor:pointer; padding:6px 0; }
.confirma { display:flex; gap:8px; align-items:center; font-size:14px; flex-wrap:wrap; background:var(--rojo-bg);
  border-radius:10px; padding:8px 10px; color:var(--rojo); }
.confirma button { min-height:40px; border-radius:9px; border:none; font:inherit; font-weight:700; padding:0 14px; cursor:pointer; }
.confirma .si { background:#DC2626; color:#fff; } .confirma .no { background:var(--card); color:var(--tinta); }
.ver-mas { display:block; width:100%; margin:14px 0 4px; padding:12px; border:1px dashed var(--linea); background:var(--card);
  color:var(--gris); font:inherit; font-size:14px; font-weight:700; border-radius:12px; cursor:pointer; }
.vacio { text-align:center; color:var(--gris); padding:36px 12px; }
.leyenda { font-size:12.5px; color:var(--gris); margin:4px 4px 0; }
/* Comisión */
.com-hero { background:var(--card); border:1px solid var(--linea); border-radius:14px; padding:16px; margin-top:12px; }
.com-hero .r { font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--gris); }
.com-hero .v { font-size:34px; font-weight:800; font-variant-numeric:tabular-nums; color:var(--ambar); }
.com-hero .s { font-size:13px; color:var(--gris); }
.com-mini { display:flex; gap:8px; margin-top:10px; }
.com-mini > div { flex:1 1 0; background:var(--suave); border:1px solid var(--linea); border-radius:10px; padding:8px 10px; }
.com-mini .r { font-size:11px; } .com-mini .v { font-size:18px; color:var(--tinta); }
.sec-tit { font-size:13px; font-weight:800; text-transform:uppercase; letter-spacing:.5px; color:var(--gris); margin:20px 4px 8px; }
.com-item { display:flex; gap:10px; align-items:center; background:var(--card); border:1px solid var(--linea); border-radius:12px;
  padding:10px 12px; margin-bottom:8px; }
.com-item input[type=checkbox] { width:22px; height:22px; flex:none; accent-color:var(--azul); }
.com-txt { flex:1 1 auto; min-width:0; font-size:14px; }
.com-txt b { display:block; font-size:15px; }
.com-txt span { color:var(--gris); font-size:13px; overflow-wrap:anywhere; }
.com-monto { font-weight:800; font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--ambar); }
.com-item.pagada .com-monto { color:var(--verde); }
.pago-grupo { background:var(--card); border:1px solid var(--verde-br); border-radius:14px; padding:10px 12px; margin-bottom:10px; }
.pago-head { display:flex; justify-content:space-between; font-weight:800; margin-bottom:6px; }
.pago-head span { color:var(--verde); }
.pago-grupo .com-item { border:none; padding:6px 0; margin:0; background:none; }
.revocar { background:none; border:1px solid var(--linea); color:var(--gris); border-radius:8px; font:inherit; font-size:12px; padding:4px 8px; cursor:pointer; }
.barra-pagar { position:fixed; left:0; right:0; bottom:0; z-index:30; padding:10px 12px calc(10px + env(safe-area-inset-bottom));
  background:var(--card); border-top:1px solid var(--linea); box-shadow:0 -4px 12px rgba(0,0,0,.08); }
.btn-pagar { display:block; width:100%; max-width:536px; margin:0 auto; min-height:52px; border:none; border-radius:12px;
  background:#16A34A; color:#fff; font:inherit; font-size:17px; font-weight:800; cursor:pointer; }
.btn-pagar:disabled { background:var(--linea); color:var(--gris); }
.modal { position:fixed; inset:0; z-index:50; background:rgba(2,6,23,.6); display:flex; align-items:flex-end; justify-content:center; }
.modal-box { background:var(--card); color:var(--tinta); width:100%; max-width:560px; border-radius:18px 18px 0 0;
  padding:18px 18px calc(18px + env(safe-area-inset-bottom)); max-height:90vh; overflow:auto; }
.modal-box h2 { margin:0 0 6px; font-size:19px; }
.banco { background:var(--suave); border:1px solid var(--linea); border-radius:12px; padding:12px; margin:12px 0; font-size:15px; }
.banco div { display:flex; justify-content:space-between; gap:10px; padding:3px 0; }
.banco span { color:var(--gris); }
.modal-acc { display:grid; gap:8px; margin-top:12px; }
.modal-acc button { min-height:50px; border-radius:12px; border:none; font:inherit; font-weight:800; font-size:16px; cursor:pointer; }
.m-ok { background:#16A34A; color:#fff; } .m-copiar { background:var(--suave); color:var(--tinta); border:1px solid var(--linea) !important; }
.m-no { background:none; color:var(--gris); }
.toast { position:fixed; left:50%; bottom:calc(84px + env(safe-area-inset-bottom)); transform:translateX(-50%); z-index:60;
  background:#0F172A; color:#fff; padding:10px 16px; border-radius:12px; font-size:14px; max-width:92vw; box-shadow:0 6px 18px rgba(0,0,0,.3); }
footer { text-align:center; color:var(--gris); font-size:12px; padding:20px 16px 30px; }
"""

SCRIPT = r"""
(function () {
  var APP = window.__APP__;
  var H = { apikey: APP.key, Authorization: 'Bearer ' + APP.key };
  var CK_FILAS = 'destapes_filas_v1', CK_EST = 'destapes_estado_v1', CK_VISTOS = 'destapes_vistos_v1', CK_DESEL = 'destapes_desel_v1';
  var filas = [], est = {}, verCobrados = false, vista = 'agenda', confirmando = null, primeraVez = false, vistos = {};

  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sin espacio o modo privado */ } }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function clp(n) { n = Math.round(Number(n) || 0); return '$' + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
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
    clearTimeout(toast._t); toast._t = setTimeout(function () { el.hidden = true; }, 3200);
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
      else { filas = APP.respaldo || []; est = {}; aviso.textContent = 'Sin conexión. Estás viendo un respaldo antiguo.'; }
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
    var id = decodeURIComponent((location.hash || '').slice(1));
    if (!id) return;
    var el = document.querySelector('.dw[data-id="' + id.replace(/"/g, '') + '"]');
    if (!el) {
      var f = fila(id);
      if (f && estadoDe(id) === 'cobrado' && !verCobrados) { verCobrados = true; pintar(); el = document.querySelector('.dw[data-id="' + id.replace(/"/g, '') + '"]'); }
    }
    if (el) { el.classList.add('foco'); el.scrollIntoView({ block: 'center' }); setTimeout(function () { el.classList.remove('foco'); }, 4000); }
  }

  // ── agenda ─────────────────────────────────────────────────────────────
  function wrap(f) {
    var id = f.id, st = estadoDe(id), e = E(id);
    var fe = fechaEf(f), orig = f.fecha || '';
    var chips = '';
    chips += st === 'cobrado' ? '<span class="chip cob">Cobrado</span>' : st === 'realizado' ? '<span class="chip real">Realizado, falta cobrar</span>' : '<span class="chip pend">Por hacer</span>';
    if (e.fecha && orig && e.fecha !== orig) chips += '<span class="chip reag">Reagendado (era ' + esc(diaLargo(orig)) + ')</span>';
    if (!primeraVez && !vistos[id]) chips += '<span class="chip nuevo">Nuevo</span>';
    var vf = Number(e.valor_final) > 0 ? Number(e.valor_final) : '';
    var desde = Number(f.data && f.data.precio_neto) || 0;
    var conf = confirmando === id
      ? '<div class="confirma">¿Quitar este destape de la agenda? <button type="button" class="si" data-acc="quitar-si">Sí, quitar</button><button type="button" class="no" data-acc="quitar-no">No</button></div>'
      : '<button type="button" class="quitar" data-acc="quitar">✕ Quitar de la agenda</button>';
    return '<div class="dw is-' + st + '" data-id="' + esc(id) + '">'
      + '<div class="dw-estado">' + chips + '</div>'
      + (f.card_html || '')
      + '<div class="dw-ctl">'
      + '<div class="est-row">'
      + '<button type="button" class="est-btn b-real' + (st !== 'pendiente' ? ' on' : '') + '" data-acc="realizado">' + (st !== 'pendiente' ? '✓ Realizado' : 'Realizado') + '</button>'
      + '<button type="button" class="est-btn b-cob' + (st === 'cobrado' ? ' on' : '') + '" data-acc="cobrado">' + (st === 'cobrado' ? '✓ Cobrado' : 'Cobrado') + '</button>'
      + '</div>'
      + '<div class="fila2">'
      + '<label class="campo">📅 Reagendar<input type="date" data-acc="fecha" value="' + esc(fe) + '"></label>'
      + '<label class="campo">💵 Valor final neto<input type="number" inputmode="numeric" min="0" step="1000" data-acc="valor" placeholder="' + (desde ? esc(desde) : 'sin IVA') + '" value="' + esc(vf) + '"><small>Si en terreno cambió el valor</small></label>'
      + '</div>'
      + '<div class="com-linea">Comisión Destape Rápido (' + pctDe(f) + '%): <b>' + clp(comDe(f)) + '</b>' + (vf ? ' sobre el valor final' : (desde ? ' sobre el valor desde' : '')) + '</div>'
      + conf
      + '</div></div>';
  }

  function pintarAgenda() {
    var cont = document.getElementById('agenda');
    var hoy = hoyISO(0), man = hoyISO(1);
    var vivos = filas.filter(vivo);
    var abiertos = vivos.filter(function (f) { return estadoDe(f.id) !== 'cobrado'; });
    var cobrados = vivos.filter(function (f) { return estadoDe(f.id) === 'cobrado'; });
    var lista = verCobrados ? cobrados : abiertos;
    var grupos = {}, orden = [];
    lista.forEach(function (f) {
      var fe = fechaEf(f), k;
      if (verCobrados) k = fe || 'sin';
      else if (!fe) k = 'sin';
      else if (fe < hoy) k = 'atrasadas';
      else k = fe;
      if (!grupos[k]) { grupos[k] = []; orden.push(k); }
      grupos[k].push(f);
    });
    orden.sort(function (a, b) {
      function peso(k) { return k === 'atrasadas' ? '0' : k === 'sin' ? '9' : '1' + k; }
      var r = peso(a) < peso(b) ? -1 : peso(a) > peso(b) ? 1 : 0;
      return verCobrados ? -r : r;
    });
    var html = '';
    if (verCobrados) html += '<div class="sec-tit">Cobrados · ' + cobrados.length + '</div>';
    orden.forEach(function (k) {
      var items = grupos[k].sort(function (a, b) {
        var fa = fechaEf(a), fb = fechaEf(b);
        if (fa !== fb) return fa < fb ? -1 : 1;
        return (b.informado_at || '') < (a.informado_at || '') ? -1 : 1;
      });
      var tit, cls = '';
      if (k === 'atrasadas') { tit = '⚠️ Atrasados'; cls = ' atrasado'; }
      else if (k === 'sin') tit = 'Sin fecha';
      else if (k === hoy) { tit = 'Hoy · ' + diaLargo(k); cls = ' hoy'; }
      else if (k === man) tit = 'Mañana · ' + diaLargo(k);
      else tit = cap(diaLargo(k));
      html += '<section data-grupo="' + esc(k) + '"><h2 class="dia-tit' + cls + '">' + esc(tit) + '<span class="dia-n">' + items.length + '</span></h2>'
        + items.map(wrap).join('') + '</section>';
    });
    if (!lista.length) html += '<p class="vacio">' + (verCobrados ? 'Todavía no hay destapes cobrados.' : 'No hay destapes agendados por ahora. Cuando el bot confirme uno, aparece acá solo.') + '</p>';
    if (cobrados.length || verCobrados) html += '<button type="button" class="ver-mas" data-acc="ver-cobrados">' + (verCobrados ? '← Volver a la agenda' : '✓ Ver cobrados (' + cobrados.length + ')') + '</button>';
    if (!verCobrados && lista.length) html += '<p class="leyenda">Blanco: por hacer. Azul: realizado, falta cobrar. Verde: cobrado. Al marcar Cobrado el destape pasa a la lista de cobrados y suma a la comisión.</p>';
    cont.innerHTML = html;
    document.getElementById('hdr-pend').textContent = abiertos.length;
  }

  // ── comisión ───────────────────────────────────────────────────────────
  function desel() { return lsGet(CK_DESEL, {}); }
  function seleccion() {
    var d = desel();
    return porPagar().filter(function (f) { return !d[f.id]; });
  }
  function porPagar() { return filas.filter(function (f) { return vivo(f) && estadoDe(f.id) === 'cobrado' && !E(f.id).comision_pagada; }); }
  function item(f, conCheck, pagada) {
    var e = E(f.id), vf = Number(e.valor_final) > 0;
    var d = f.data || {};
    var chk = conCheck ? '<input type="checkbox" data-acc="sel" data-id="' + esc(f.id) + '"' + (desel()[f.id] ? '' : ' checked') + ' aria-label="Incluir en el pago">' : '';
    var rev = pagada ? '<button type="button" class="revocar" data-acc="revocar" data-id="' + esc(f.id) + '">Revocar</button>' : '';
    return '<div class="com-item' + (pagada ? ' pagada' : '') + '">' + chk
      + '<div class="com-txt"><b>' + esc(cap(diaLargo(fechaEf(f)))) + ' · ' + esc(d.servicio || 'Destape') + '</b>'
      + '<span>' + esc([d.direccion, d.comuna].filter(Boolean).join(', ')) + '</span><br>'
      + '<span>' + (vf ? 'Valor final ' : 'Desde ') + clp(baseDe(f)) + ' neto · ' + pctDe(f) + '%</span></div>'
      + '<div class="com-monto">' + clp(comDe(f)) + '</div>' + rev + '</div>';
  }
  function pintarComision() {
    var vivos = filas.filter(vivo);
    var deuda = porPagar();
    var porCobrar = vivos.filter(function (f) { return estadoDe(f.id) !== 'cobrado'; });
    var pagadas = vivos.filter(function (f) { return estadoDe(f.id) === 'cobrado' && E(f.id).comision_pagada; });
    function suma(a) { return a.reduce(function (s, f) { return s + comDe(f); }, 0); }
    var html = '<div class="com-hero"><div class="r">Te deben</div><div class="v">' + clp(suma(deuda)) + '</div>'
      + '<div class="s">Comisión de Destape Rápido (' + APP.pct + '% del neto) de los destapes ya cobrados. Se calcula sobre el valor final si se anotó, o sobre el valor desde.</div>'
      + '<div class="com-mini"><div><div class="r">Por cobrar</div><div class="v">' + clp(suma(porCobrar)) + '</div></div>'
      + '<div><div class="r">Ya pagado</div><div class="v">' + clp(suma(pagadas)) + '</div></div></div></div>';
    if (deuda.length) {
      html += '<div class="sec-tit">Cobrados sin pagar · ' + deuda.length + '</div>' + deuda.map(function (f) { return item(f, true, false); }).join('');
    }
    if (porCobrar.length) {
      html += '<div class="sec-tit">Todavía no cobrados · ' + clp(suma(porCobrar)) + '</div>' + porCobrar.map(function (f) { return item(f, false, false); }).join('');
    }
    if (pagadas.length) {
      var g = {};
      pagadas.forEach(function (f) {
        var k = (E(f.id).pagada_at || '').slice(0, 10) || 'sin-fecha';
        (g[k] = g[k] || []).push(f);
      });
      var ks = Object.keys(g).sort();
      html += '<div class="sec-tit">Mis pagos recibidos · ' + clp(suma(pagadas)) + '</div>';
      ks.slice().reverse().forEach(function (k) {
        var n = ks.indexOf(k) + 1;
        html += '<div class="pago-grupo"><div class="pago-head">Pago ' + n + (k !== 'sin-fecha' ? ' · ' + esc(diaLargo(k)) : '') + '<span>' + clp(suma(g[k])) + '</span></div>'
          + g[k].map(function (f) { return item(f, false, true); }).join('') + '</div>';
      });
    }
    if (!vivos.length) html += '<p class="vacio">Sin destapes todavía.</p>';
    document.getElementById('comision').innerHTML = html;
    var sel = seleccion(), btn = document.getElementById('btn-pagar');
    document.getElementById('barra-pagar').hidden = vista !== 'comision' || !deuda.length;
    btn.disabled = !sel.length;
    btn.textContent = sel.length ? 'Pagar ' + clp(suma(sel)) + ' (' + sel.length + ')' : 'Selecciona lo que vas a pagar';
    document.getElementById('hdr-com').textContent = clp(suma(deuda));
  }

  function pintar() {
    pintarAgenda(); pintarComision();
    document.querySelectorAll('.vista').forEach(function (v) { v.hidden = v.getAttribute('data-vista') !== vista; });
    document.querySelectorAll('.vista-btn').forEach(function (b) { b.classList.toggle('activo', b.getAttribute('data-vista') === vista); });
  }

  // ── pago ───────────────────────────────────────────────────────────────
  function abrirPago() {
    var sel = seleccion(); if (!sel.length) return;
    var total = sel.reduce(function (s, f) { return s + comDe(f); }, 0);
    var b = APP.banco;
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
    var t = ev.target.closest('[data-acc],[data-vista],[data-accion]'); if (!t) return;
    if (t.classList.contains('vista-btn')) { vista = t.getAttribute('data-vista'); pintar(); window.scrollTo(0, 0); return; }
    var w = t.closest('.dw'), id = w && w.getAttribute('data-id');
    var acc = t.getAttribute('data-acc') || t.getAttribute('data-accion');
    if (acc === 'wa' && id) {
      // Mensaje listo para el cliente. El link base ya abre el chat, esto le suma el texto.
      var f = fila(id), d = (f && f.data) || {};
      var txt = 'Hola, le escribo de Destape Rápido por el ' + (d.servicio || 'destape').toLowerCase() + ' agendado para el ' + diaLargo(fechaEf(f)) + (d.hora ? ', ' + d.hora : '') + (d.direccion ? ', en ' + d.direccion : '') + '.';
      t.href = 'https://wa.me/' + (d.telefono || '').replace(/\D/g, '') + '?text=' + encodeURIComponent(txt);
      if (!E(id).contactado) guardar(id, { contactado: true }).then(function () { est[id] = Object.assign({}, E(id), { contactado: true }); lsSet(CK_EST, est); }).catch(function () {});
      return;
    }
    if (acc === 'realizado') {
      var st = estadoDe(id);
      cambiar(id, { estado: st === 'pendiente' ? 'realizado' : 'pendiente' }, st === 'pendiente' ? 'Marcado como realizado' : 'Vuelve a quedar por hacer').catch(function () {});
    } else if (acc === 'cobrado') {
      var st2 = estadoDe(id);
      if (st2 === 'cobrado' && E(id).comision_pagada) { toast('Su comisión ya está pagada. Revoca el pago antes de desmarcarlo.'); return; }
      cambiar(id, { estado: st2 === 'cobrado' ? 'realizado' : 'cobrado' }, st2 === 'cobrado' ? 'Ya no figura como cobrado' : 'Cobrado. Suma a la comisión.').catch(function () {});
    } else if (acc === 'quitar') { confirmando = id; pintar(); }
    else if (acc === 'quitar-no') { confirmando = null; pintar(); }
    else if (acc === 'quitar-si') { confirmando = null; cambiar(id, { eliminado: true }, 'Quitado de la agenda').catch(function () {}); }
    else if (acc === 'ver-cobrados') { verCobrados = !verCobrados; pintar(); window.scrollTo(0, 0); }
    else if (acc === 'revocar') {
      var rid = t.getAttribute('data-id');
      if (confirm('¿Revocar este pago? La comisión vuelve a quedar pendiente.')) cambiar(rid, { comision_pagada: false, pagada_at: null }, 'Pago revocado').catch(function () {});
    } else if (acc === 'sel') {
      var d2 = desel(), sid = t.getAttribute('data-id');
      if (t.checked) delete d2[sid]; else d2[sid] = 1;
      lsSet(CK_DESEL, d2); pintarComision();
    }
  });
  document.addEventListener('change', function (ev) {
    var t = ev.target, acc = t.getAttribute && t.getAttribute('data-acc'); if (!acc) return;
    var w = t.closest('.dw'), id = w && w.getAttribute('data-id'); if (!id) return;
    if (acc === 'fecha') {
      var f = fila(id), v = t.value || null;
      var cambio = (!v || v === (f && f.fecha)) ? { fecha: null } : { fecha: v };
      cambiar(id, cambio, v ? 'Reagendado para el ' + diaLargo(v) : 'Fecha original').catch(function () {});
    } else if (acc === 'valor') {
      var n = parseInt(String(t.value).replace(/\D/g, ''), 10);
      cambiar(id, { valor_final: n > 0 ? n : null }, n > 0 ? 'Valor final guardado: ' + clp(n) : 'Valor final borrado').catch(function () {});
    }
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
  window.__DESTAPES__ = { comDe: comDe, baseDe: baseDe, fechaEf: fechaEf, estadoDe: estadoDe, porPagar: porPagar, pintar: function () { pintar(); },
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
  <div class="sub"><span id="hdr-pend"><span class="skel" style="width:14px"></span></span> por hacer · <span id="hdr-act">Cargando...</span></div>
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
<div id="barra-pagar" class="barra-pagar" hidden><button type="button" id="btn-pagar" class="btn-pagar" disabled>Selecciona lo que vas a pagar</button></div>
<div id="modal" class="modal" hidden><div class="modal-box"><div id="modal-cuerpo"></div>
  <div class="modal-acc"><button type="button" class="m-ok">Ya transferí, avisar por WhatsApp</button>
  <button type="button" class="m-copiar">Copiar datos de la cuenta</button>
  <button type="button" class="m-no">Cancelar</button></div></div></div>
<div id="toast" class="toast" hidden></div>
<footer>Destape Rápido · área camión, hidrojet y cámara</footer>
<script>window.__APP__ = @@APP@@;</script>
<script>@@SCRIPT@@</script>
</body>
</html>
"""


def construir_html(respaldo: list[dict]) -> str:
    app = {
        "url": SUPABASE_URL,
        "key": SUPABASE_ANON_KEY,
        "pct": pct_comision(),
        "banco": gl.DATOS_BANCARIOS,
        "whatsapp": gl.WHATSAPP_COMISION,
        "respaldo": respaldo,
        "generado": date.today().isoformat(),
    }
    app_json = json.dumps(app, ensure_ascii=False).replace("</", "<\\/")
    return (PAGINA.replace("@@CSS@@", CSS).replace("@@SCRIPT@@", SCRIPT).replace("@@APP@@", app_json))


def main() -> None:
    respaldo = [] if "--sin-red" in sys.argv else filas_vivas()
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), SALIDA))
    out.write_text(construir_html(respaldo), encoding="utf-8")
    print(f"✅ {out} ({len(respaldo)} destapes en el respaldo, comisión {pct_comision()} %)")


if __name__ == "__main__":
    main()
