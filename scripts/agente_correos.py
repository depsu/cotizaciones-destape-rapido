#!/usr/bin/env python3
"""Helper del Agente de Cotizaciones en modo loop LOCAL.

El "cerebro" que redacta es Claude Code (este terminal), NO una API externa.
Este script solo lee/escribe correos en el panel vía la API del Worker.

Uso:
  python scripts/agente_correos.py nuevos          # correos sin responder (estado=nuevo)
  python scripts/agente_correos.py correo <id>     # un correo completo (cuerpo incluido)
  python scripts/agente_correos.py respondidos     # correos ya enviados (para aprender)
  echo "texto..." | python scripts/agente_correos.py borrador <id>   # guarda borrador
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

CFG = Path(__file__).resolve().parent.parent / "config" / "agente.local.json"


def cargar():
    # Local: archivo de config. Nube (routine): variables de entorno.
    if CFG.exists():
        d = json.load(CFG.open())
        return d["worker_url"].rstrip("/"), d["panel_pass"]
    wu, pw = os.environ.get("WORKER_URL"), os.environ.get("PANEL_PASS")
    if wu and pw:
        return wu.rstrip("/"), pw
    sys.exit(f"❌ Falta {CFG} o las variables de entorno WORKER_URL / PANEL_PASS")


def api(path, method="GET", body=None):
    base, pw = cargar()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "x-panel-pass": pw,
            "content-type": "application/json",
            # Cloudflare bloquea User-Agents no-navegador (error 1010); usar uno de navegador.
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        },
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"error": f"HTTP {e.code}"}


def correos(filtro, page_size=100, max_pages=20):
    """Trae TODA una carpeta paginando (fase8+ el endpoint es paginado por filtro)."""
    out, page = [], 1
    while page <= max_pages:
        d = api(f"/api/correos?filtro={filtro}&page={page}&pageSize={page_size}")
        out.extend(d.get("correos", []))
        if not d.get("hasMore"):
            break
        page += 1
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: nuevos | ajustes | respondidos | correo <id> | borrador <id> (STDIN) | "
                 "spam <id> | enviar <id> (STDIN) | adjuntar <id> <pdf> | "
                 "sin-etiqueta | etiqueta <id> <texto>")
    cmd = sys.argv[1]

    if cmd in ("nuevos", "ajustes"):
        estado = {"nuevos": "nuevo", "ajustes": "ajuste"}[cmd]
        cs = [c for c in correos("recibidos") if c.get("estado") == estado]
        print(json.dumps(cs, ensure_ascii=False, indent=2))

    elif cmd == "respondidos":
        # 'respondido' vive en la carpeta 'enviados' desde fase8.
        cs = [c for c in correos("enviados") if c.get("estado") == "respondido"]
        print(json.dumps(cs, ensure_ascii=False, indent=2))

    elif cmd == "sin-etiqueta":
        # Correos de negocio (recibidos + enviados) que aún no tienen etiquetas -> para el loop de etiquetado IA.
        vistos, cs = set(), []
        for c in correos("recibidos") + correos("enviados"):
            if c["id"] in vistos:
                continue
            vistos.add(c["id"])
            if not (c.get("etiquetas") or "").strip():
                cs.append({k: c.get(k) for k in ("id", "de", "para", "asunto", "estado", "snippet")})
        print(json.dumps(cs, ensure_ascii=False, indent=2))

    elif cmd == "etiqueta":
        if len(sys.argv) < 4:
            sys.exit("uso: etiqueta <id> <texto de la etiqueta>")
        etq = " ".join(sys.argv[3:])
        res = api("/api/etiqueta", "POST", {"id": sys.argv[2], "etiqueta": etq, "accion": "add"})
        print(json.dumps(res, ensure_ascii=False))

    elif cmd == "correo":
        if len(sys.argv) < 3:
            sys.exit("falta id")
        print(json.dumps(api("/api/correo?id=" + sys.argv[2]), ensure_ascii=False, indent=2))

    elif cmd == "borrador":
        if len(sys.argv) < 3:
            sys.exit("falta id  (uso: borrador <id> [confianza alta|baja] [motivo] ; texto por STDIN)")
        texto = sys.stdin.read()
        if not texto.strip():
            sys.exit("❌ sin texto en STDIN")
        body = {"id": sys.argv[2], "texto": texto}
        if len(sys.argv) > 3:
            body["confianza"] = sys.argv[3]
        if len(sys.argv) > 4:
            body["motivo"] = sys.argv[4]
        res = api("/api/borrador", "POST", body)
        print(json.dumps(res, ensure_ascii=False))

    elif cmd == "spam":
        if len(sys.argv) < 3:
            sys.exit("falta id  (uso: spam <id>)")
        res = api("/api/spam", "POST", {"id": sys.argv[2]})
        print(json.dumps(res, ensure_ascii=False))

    elif cmd == "enviar":
        if len(sys.argv) < 3:
            sys.exit("falta id  (uso: enviar <id> ; texto de la respuesta por STDIN)")
        texto = sys.stdin.read()
        if not texto.strip():
            sys.exit("❌ sin texto en STDIN")
        res = api("/api/enviar", "POST", {"id": sys.argv[2], "texto": texto})
        print(json.dumps(res, ensure_ascii=False))

    elif cmd == "adjuntar":
        if len(sys.argv) < 4:
            sys.exit("uso: adjuntar <id> <ruta.pdf>")
        ruta = Path(sys.argv[3])
        if not ruta.exists():
            sys.exit(f"❌ no existe {ruta}")
        b64 = base64.b64encode(ruta.read_bytes()).decode()
        res = api(
            "/api/adjuntar",
            "POST",
            {"id": sys.argv[2], "nombre": ruta.name, "b64": b64},
        )
        print(json.dumps(res, ensure_ascii=False))

    else:
        sys.exit(f"comando desconocido: {cmd}")


if __name__ == "__main__":
    main()
