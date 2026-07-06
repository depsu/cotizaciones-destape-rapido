#!/usr/bin/env python3
"""Sincroniza el CONTENIDO de las entregas desde entregas.json hacia Supabase
(tabla `entrega`). Idempotente: hace upsert por `id`.

- `data`         = el objeto completo de la entrega (misma forma que en el JSON).
- `fecha`        = fecha de entrega (para agrupar por día en la página).
- `informado_at` = orden en que se informó la entrega. Se deriva del ORDEN del
  array (index 0 = la más antigua informada; la última = la más reciente), anclado
  a una base fija para que re-correr sea determinista. La página ordena por este
  campo DESC → la más reciente informada queda arriba.

Las entregas nuevas que agregue el flujo del repartidor usan `now()` por defecto,
así que siempre quedan por encima de las migradas.

Uso:
    python3 resumen-repartidor/scripts/sync_entregas_supabase.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent          # resumen-repartidor/
ENTREGAS_JSON = BASE / "entregas.json"

# Reutiliza URL + anon key del generador (única fuente de verdad).
sys.path.insert(0, str(BASE / "scripts"))
import generar_listado as gl  # noqa: E402

# Base fija para informado_at de las entregas migradas (determinista).
# Un minuto por posición en el array preserva el orden informado.
_BASE_TS = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)


def cargar_entregas() -> list[dict]:
    data = json.loads(ENTREGAS_JSON.read_text(encoding="utf-8"))
    return data.get("entregas", [])


def construir_filas(entregas: list[dict]) -> list[dict]:
    filas = []
    for i, e in enumerate(entregas):
        eid = e.get("id")
        if not eid:
            continue
        informado = _BASE_TS + timedelta(minutes=i)
        filas.append({
            "id": eid,
            "fecha": e.get("fecha") or None,
            "informado_at": informado.isoformat(),
            "data": e,
            # card_html: la tarjeta ya renderizada por la misma función que hornea
            # el listado. La página la inyecta tal cual (no porta el template a JS).
            "card_html": gl.tarjeta(e),
            "eliminado": False,
        })
    return filas


def upsert(filas: list[dict]) -> None:
    url = f"{gl.SUPABASE_URL}/rest/v1/entrega?on_conflict=id"
    body = json.dumps(filas).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("apikey", gl.SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {gl.SUPABASE_ANON_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"✅ Upsert OK ({len(filas)} entregas) — HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        sys.exit(f"❌ Supabase rechazó el upsert (HTTP {e.code}): {e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"❌ No se pudo conectar a Supabase: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Muestra las filas sin escribir.")
    args = ap.parse_args()

    entregas = cargar_entregas()
    filas = construir_filas(entregas)
    print(f"Entregas en el JSON: {len(entregas)} · filas a sincronizar: {len(filas)}")
    if args.dry_run:
        for f in filas:
            print(f"  {f['informado_at']}  {f['id']}  (fecha {f['fecha']})")
        return
    upsert(filas)


if __name__ == "__main__":
    main()
