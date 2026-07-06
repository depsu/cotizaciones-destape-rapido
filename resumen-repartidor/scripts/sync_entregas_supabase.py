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


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": gl.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {gl.SUPABASE_ANON_KEY}",
    }
    if extra:
        h.update(extra)
    return h


def _informado_existente() -> dict:
    """{id: informado_at} de las filas ya en Supabase. Sirve para PRESERVAR el
    orden informado al re-sincronizar (no reescribir el que ya tienen, incluido
    el `now()` que puso el flujo del repartidor). Si falla, devuelve {}."""
    url = f"{gl.SUPABASE_URL}/rest/v1/entrega?select=id,informado_at"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            filas = json.loads(resp.read().decode())
        return {f["id"]: f["informado_at"] for f in filas if f.get("id")}
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        return {}


def fila_de(e: dict, informado_at: str) -> dict:
    """Fila de Supabase para una entrega. `card_html` sale de la MISMA función que
    hornea el listado (no se porta el template a JS)."""
    return {
        "id": e.get("id"),
        "fecha": e.get("fecha") or None,
        "informado_at": informado_at,
        "data": e,
        "card_html": gl.tarjeta(e),
        "eliminado": False,
    }


def construir_filas(entregas: list[dict]) -> list[dict]:
    # Preserva el informado_at ya existente; solo asigna base+index (determinista)
    # a las entregas que aún NO están en Supabase.
    existentes = _informado_existente()
    filas = []
    for i, e in enumerate(entregas):
        eid = e.get("id")
        if not eid:
            continue
        informado = existentes.get(eid) or (_BASE_TS + timedelta(minutes=i)).isoformat()
        filas.append(fila_de(e, informado))
    return filas


def upsert(filas: list[dict]) -> int:
    """Upsert por id. Devuelve el status HTTP. Lanza RuntimeError ante error
    (para no matar el proceso que la use embebida)."""
    url = f"{gl.SUPABASE_URL}/rest/v1/entrega?on_conflict=id"
    body = json.dumps(filas).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers({
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase rechazó el upsert (HTTP {e.code}): {e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a Supabase: {e}")


def upsert_entrega(e: dict, informado_at: str | None = None) -> bool:
    """Sube UNA entrega a Supabase (la usa el flujo del repartidor al avisar).
    Por defecto informado_at = AHORA → queda arriba en la página. No lanza: devuelve
    True/False para no matar el flujo del repartidor si el WhatsApp ya se envió."""
    if not e.get("id"):
        return False
    ts = informado_at or datetime.now(timezone.utc).isoformat()
    try:
        upsert([fila_de(e, ts)])
        return True
    except RuntimeError:
        return False


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
    try:
        status = upsert(filas)
        print(f"✅ Upsert OK ({len(filas)} entregas) — HTTP {status}")
    except RuntimeError as ex:
        sys.exit(f"❌ {ex}")


if __name__ == "__main__":
    main()
