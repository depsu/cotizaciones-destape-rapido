#!/usr/bin/env python3
"""Sube (upsert) UN destape a la agenda de destapes (tabla `destape` de Supabase),
con su tarjeta ya renderizada (`card_html`). Idempotente: si el pedido ya tenía
destape, reutiliza su id y lo actualiza (no duplica).

Lo llama solo el conector del bot (DIXDY/clientes/destaperapido/conexiones/
avisar-destape.mjs) cuando sale un aviso real. También sirve a mano.

Entrada: un JSON (texto o ruta a archivo) con los campos del aviso. Acepta los
nombres del conector o los de la tabla:
    _pedidoId|pedido_id, servicio (clave, p. ej. destape-hydrojet), nombre_servicio,
    pedido|trabajo, fecha (AAAA-MM-DD), hora, direccion, comuna, maps_url, acceso,
    nombre|cliente, telefono_cliente|telefono, precio_neto, factura, mensaje|nota,
    comision_pct, destino, id (opcional, si no se arma solo).

Uso:
    python3 resumen-destapes/scripts/subir_destape.py '<json>'        # sube
    python3 resumen-destapes/scripts/subir_destape.py archivo.json --dry-run
    python3 resumen-destapes/scripts/subir_destape.py --eliminar <id>
    python3 resumen-destapes/scripts/subir_destape.py --eliminar-pedido p-613

Imprime en la última línea un JSON {"ok": true, "id": "..."} (lo lee el conector).
Sale con código 1 si Supabase falla (el conector igual manda el aviso).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generar_destapes as gd  # noqa: E402

TABLA = f"{gd.SUPABASE_URL}/rest/v1/destape"

# Palabra corta del servicio para el id legible (2026-10-25-hidrojet-8318).
CORTO = {
    "destape-hydrojet": "hidrojet",
    "destape-camion": "camion",
    "video-inspeccion": "camara",
    "succion-fosa": "fosa",
    "destape-domiciliario": "destape",
}


def _h(extra: dict | None = None) -> dict:
    h = {"apikey": gd.SUPABASE_ANON_KEY, "Authorization": f"Bearer {gd.SUPABASE_ANON_KEY}"}
    h.update(extra or {})
    return h


def _pedir(url: str, metodo: str = "GET", cuerpo=None, extra: dict | None = None):
    data = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=data, method=metodo, headers=_h(extra))
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            txt = r.read().decode() or "null"
            return json.loads(txt)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase respondió HTTP {e.code}: {e.read().decode()[:400]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a Supabase: {e}")


def slug(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _t(a: dict, *claves) -> str:
    for k in claves:
        v = a.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def normalizar(a: dict) -> dict:
    """Del JSON del conector (o uno ya normalizado) a la forma de `data`."""
    clave = _t(a, "servicio_clave", "servicio")
    conf = gd.config_avisos()
    nombre = _t(a, "nombre_servicio") or conf.get("nombres_servicio", {}).get(clave) or _t(a, "servicio") or "Destape"
    if nombre == clave and clave in conf.get("nombres_servicio", {}):
        nombre = conf["nombres_servicio"][clave]
    destino = gd.solo_digitos(_t(a, "destino")) or gd.DESTINO_PAGINA
    fecha = _t(a, "fecha", "fecha_entrega")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        fecha = ""
    tel = gd.solo_digitos(_t(a, "telefono_cliente", "telefono"))
    if len(tel) == 9 and tel.startswith("9"):
        tel = "56" + tel
    try:
        pct = int(float(_t(a, "comision_pct") or 0)) or gd.pct_comision(destino)
    except ValueError:
        pct = gd.pct_comision(destino)
    d = {
        "pedido_id": _t(a, "_pedidoId", "pedido_id"),
        "servicio_clave": clave,
        "servicio": nombre,
        "trabajo": _t(a, "trabajo", "pedido"),
        "fecha": fecha,
        "hora": _t(a, "hora"),
        "direccion": _t(a, "direccion"),
        "comuna": _t(a, "comuna"),
        "maps_url": _t(a, "maps_url"),
        "acceso": _t(a, "acceso"),
        "cliente": _t(a, "cliente", "nombre"),
        "telefono": tel,
        "precio_neto": int(gd.solo_digitos(_t(a, "precio_neto")) or 0),
        "factura": _t(a, "factura"),
        "nota": _t(a, "nota", "mensaje"),
        "comision_pct": pct,
        "destino": destino,
    }
    d["id"] = _t(a, "id") or armar_id(d)
    return d


def armar_id(d: dict) -> str:
    partes = [d.get("fecha") or "sin-fecha",
              CORTO.get(d.get("servicio_clave", ""), slug(d.get("servicio_clave") or "destape")),
              (d.get("telefono") or "")[-4:] or slug(d.get("pedido_id") or "") or "x"]
    return "-".join(p for p in partes if p)


def id_existente(pedido_id: str) -> str | None:
    """Si el pedido ya tiene destape (aunque esté eliminado), su id: así re-subir no duplica."""
    if not pedido_id:
        return None
    url = f"{TABLA}?select=id&data->>pedido_id=eq.{urllib.parse.quote(pedido_id)}&order=informado_at.desc&limit=1"
    filas = _pedir(url) or []
    return filas[0]["id"] if filas else None


def subir(a: dict, dry: bool = False) -> dict:
    d = normalizar(a)
    if not dry:
        previo = id_existente(d["pedido_id"])
        if previo:
            d["id"] = previo
    fila = {"id": d["id"], "fecha": d["fecha"] or None, "data": d,
            "card_html": gd.tarjeta(d), "eliminado": False}
    # informado_at NO se manda: al insertar queda now(), al actualizar conserva el original.
    if dry:
        return fila
    _pedir(f"{TABLA}?on_conflict=id", "POST", [fila],
           {"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"})
    return fila


def eliminar(id_: str | None = None, pedido_id: str | None = None) -> list[str]:
    """Marca eliminado (la tarjeta sale de la página). Devuelve los ids tocados."""
    filtro = (f"id=eq.{urllib.parse.quote(id_)}" if id_
              else f"data->>pedido_id=eq.{urllib.parse.quote(pedido_id or '')}")
    filas = _pedir(f"{TABLA}?{filtro}", "PATCH", {"eliminado": True},
                   {"Content-Type": "application/json", "Prefer": "return=representation"}) or []
    return [f["id"] for f in filas]


def _leer_json(arg: str) -> dict:
    p = Path(arg)
    txt = p.read_text(encoding="utf-8") if not arg.lstrip().startswith("{") and p.exists() else arg
    return json.loads(txt)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    try:
        if "--eliminar" in flags or "--eliminar-pedido" in flags:
            if not args:
                sys.exit("Falta el id o el pedido.")
            ids = eliminar(id_=args[0]) if "--eliminar" in flags else eliminar(pedido_id=args[0])
            print(json.dumps({"ok": True, "eliminados": ids}, ensure_ascii=False))
            return
        if not args:
            sys.exit(__doc__)
        fila = subir(_leer_json(args[0]), dry="--dry-run" in flags)
        if "--dry-run" in flags:
            print(json.dumps(fila, ensure_ascii=False, indent=1))
        print(json.dumps({"ok": True, "id": fila["id"]}, ensure_ascii=False))
    except (RuntimeError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)[:300]}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
