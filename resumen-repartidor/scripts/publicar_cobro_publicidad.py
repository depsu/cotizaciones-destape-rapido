#!/usr/bin/env python3
"""Publica en la página del repartidor un COBRO DE PUBLICIDAD (2026-09-02).

Alejandro paga la publicidad y al repartidor le toca una parte (hoy la mitad). La
rendición la arma `scripts/rendir-publicidad.py` del maestro DIXDY en una carpeta
`<clon>/rendiciones/<desde>_<hasta>[-campaña]/` con `resumen.json` + `cobro.png`.
Este script toma esa carpeta y:

  1. copia `cobro.png` a `resumen-repartidor/publicidad/<id>.png` (+ una miniatura
     `.mini.png` para la cabecera de la página);
  2. sube/actualiza la fila en la tabla `cobro_publicidad` de Supabase (anon key +
     RLS, como todo lo demás de la página), con el monto que le toca al repartidor.

La página la muestra sola (cabecera a la derecha + vista 💰 Comisión como pendiente
por pagar). Las imágenes viajan con el repo: después hay que correr
`bash resumen-repartidor/publicar.sh "…"` para que GitHub Pages las sirva.

Uso:
  python3 publicar_cobro_publicidad.py --rendicion <carpeta> [--fraccion 0.5]
        [--nota "texto"] [--id <id>] [--dry]
  python3 publicar_cobro_publicidad.py --listar
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import generar_listado as gl  # noqa: E402

PUB_DIR = BASE / "publicidad"


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": gl.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {gl.SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    h.update(extra or {})
    return h


def _req(path: str, data: dict | None = None, extra: dict | None = None, method: str | None = None):
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    req = urllib.request.Request(f"{gl.SUPABASE_URL}/rest/v1/{path}", data=body,
                                 headers=_headers(extra), method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"❌ Supabase {e.code}: {e.read().decode()[:300]}")


def listar() -> None:
    filas = _req("cobro_publicidad?select=id,campana,desde,hasta,gasto_total,fraccion,monto,pagado,pagada_at,eliminado&order=hasta.desc")
    if not filas:
        print("Sin cobros de publicidad publicados.")
        return
    for f in filas:
        est = "🗑 eliminado" if f["eliminado"] else ("✅ pagado " + (f["pagada_at"] or "")[:10] if f["pagado"] else "⏳ pendiente")
        print(f"{f['id']:<40} {f['campana']:<22} {f['desde']}→{f['hasta']}  gasto ${f['gasto_total']:,}  "
              f"le toca ${f['monto']:,} ({float(f['fraccion']):.0%})  {est}".replace(",", "."))


def publicar(carpeta: Path, fraccion: float, nota: str | None, id_forzado: str | None, dry: bool) -> None:
    resumen_p = carpeta / "resumen.json"
    png = carpeta / "cobro.png"
    if not resumen_p.exists() or not png.exists():
        sys.exit(f"❌ La carpeta debe traer resumen.json y cobro.png: {carpeta}")
    r = json.loads(resumen_p.read_text(encoding="utf-8"))
    cobro = r.get("cobro") or {}
    gasto = int(round(cobro.get("gasto_total") or 0))
    if gasto <= 0:
        sys.exit("❌ El resumen no trae gasto_total > 0")
    cid = id_forzado or carpeta.name
    monto = int(round(gasto * fraccion))
    contactos = cobro.get("contactos")
    detalle = {
        "clics": cobro.get("clics"),
        "contactos": (int(contactos) if contactos is not None and float(contactos).is_integer() else contactos),
        "costo_por_contacto": int(round(cobro.get("costo_por_contacto") or 0)) or None,
        "moneda": cobro.get("moneda") or "CLP",
        "dias_sin_gasto": cobro.get("dias_sin_gasto") or [],
        "montos": r.get("montos"),
    }
    fila = {
        "id": cid,
        "campana": r.get("campana") or "publicidad",
        "plataforma": r.get("plataforma") or "Google Ads",
        "desde": r["desde"],
        "hasta": r["hasta"],
        "gasto_total": gasto,
        "fraccion": fraccion,
        "monto": monto,
        "imagen": f"publicidad/{cid}.png",
        "miniatura": f"publicidad/{cid}.mini.png",
        "detalle": detalle,
        "nota": nota,
        "eliminado": False,
    }
    print(f"📣 {fila['campana']} · {fila['plataforma']} · {fila['desde']} → {fila['hasta']}")
    print(f"   gasto total ${gasto:,}  →  le toca al repartidor ${monto:,} ({fraccion:.0%})".replace(",", "."))
    if dry:
        print("   (--dry: no se copia ni se sube nada)")
        print(json.dumps(fila, ensure_ascii=False, indent=1))
        return

    PUB_DIR.mkdir(exist_ok=True)
    destino = PUB_DIR / f"{cid}.png"
    mini = PUB_DIR / f"{cid}.mini.png"
    shutil.copyfile(png, destino)
    # Miniatura para la cabecera (sips viene con macOS; si falla, la página usa la grande).
    try:
        subprocess.run(["sips", "-Z", "480", str(destino), "--out", str(mini)],
                       check=True, capture_output=True)
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ sin miniatura ({e}); la cabecera usará la imagen grande")
        fila["miniatura"] = fila["imagen"]

    # Upsert que NO pisa pagado/pagada_at si ya existía (los marca el repartidor).
    previa = _req(f"cobro_publicidad?select=pagado,pagada_at&id=eq.{cid}")
    if previa:
        fila["pagado"] = previa[0]["pagado"]
        fila["pagada_at"] = previa[0]["pagada_at"]
    _req("cobro_publicidad", fila, {"Prefer": "resolution=merge-duplicates,return=minimal"})
    print(f"✅ Publicado en Supabase (id {cid}). Imagen: {destino.relative_to(BASE)}")
    print("   Ahora: bash resumen-repartidor/publicar.sh \"cobro de publicidad …\"  (sube la imagen a GitHub Pages)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rendicion", type=Path, help="carpeta con resumen.json + cobro.png")
    ap.add_argument("--fraccion", type=float, default=0.5, help="parte que paga el repartidor (0.5 = la mitad)")
    ap.add_argument("--nota", default=None)
    ap.add_argument("--id", default=None, help="id de la fila (por defecto, el nombre de la carpeta)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()
    if a.listar:
        listar()
        return
    if not a.rendicion:
        ap.error("falta --rendicion (o usa --listar)")
    if not (0 < a.fraccion <= 1):
        ap.error("--fraccion debe estar entre 0 y 1")
    publicar(a.rendicion.resolve(), a.fraccion, a.nota, a.id, a.dry)


if __name__ == "__main__":
    main()
