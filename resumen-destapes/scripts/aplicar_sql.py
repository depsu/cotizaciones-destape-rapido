#!/usr/bin/env python3
"""Aplica un .sql al proyecto Supabase por la Management API (sin CLI ni psql).

Usa SUPABASE_ACCESS_TOKEN del entorno (nunca se imprime). Cloudflare bloquea el
User-Agent de Python (error 1010), por eso va uno de navegador.

Uso:
    python3 resumen-destapes/scripts/aplicar_sql.py resumen-destapes/supabase/destape.sql
    python3 resumen-destapes/scripts/aplicar_sql.py --query "select 1"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REF = os.environ.get("SUPABASE_PROJECT_REF") or "abmzkzraptmjgebwjzys"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def correr(query: str):
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        sys.exit("Falta SUPABASE_ACCESS_TOKEN en el entorno.")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{REF}/database/query",
        data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase rechazó el SQL (HTTP {e.code}): {e.read().decode()[:600]}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--query":
        q = sys.argv[2]
    elif len(sys.argv) == 2:
        q = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        sys.exit(__doc__)
    print(json.dumps(correr(q), ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
