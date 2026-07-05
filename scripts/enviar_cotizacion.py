#!/usr/bin/env python3
"""Envía una cotización en PDF por correo usando el SMTP del hosting.

Lee las credenciales de config/smtp.local.json y manda el PDF como adjunto
con un cuerpo formal. Pensado para ejecutarse como paso separado, después de
generar la cotización con generar_cotizacion.py (así revisas el PDF antes).

Uso:
    python scripts/enviar_cotizacion.py <ruta_pdf> <email_destino> [opciones]

Opciones:
    --cliente "Nombre"     Nombre del cliente (personaliza el saludo y el asunto).
    --asunto  "Texto"      Asunto personalizado (sobrescribe el asunto por defecto).
    --cc      "a@b.cl"     Copia (CC). Se puede repetir.
    --mensaje "Texto"      Cuerpo personalizado (sobrescribe el texto por defecto).

Ejemplos:
    python scripts/enviar_cotizacion.py cotizaciones/cotizacion-20260622-juan.pdf juan@cliente.cl --cliente "Juan Pérez"
"""

from __future__ import annotations

import argparse
import base64
import json
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "smtp.local.json"
RESEND_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "resend.local.json"
AGENTE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "agente.local.json"

# User-Agent de navegador: Resend está detrás de Cloudflare y responde 403 (error 1010)
# al User-Agent por defecto de urllib. Con uno de navegador el envío pasa sin problema.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Datos de la empresa, para la firma del correo.
EMPRESA = "Destape Rápido"
TELEFONO = "+56 9 3647 0112"
WEB = "destaperapido.cl"


def cargar_config() -> dict:
    """Carga y valida la configuración SMTP local."""
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        sys.exit(f"❌ No se encontró el archivo de configuración: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        sys.exit(f"❌ El JSON de configuración tiene un error de formato: {e}")

    faltantes = [k for k in ("host", "port", "user", "password") if not cfg.get(k)]
    if faltantes:
        sys.exit(f"❌ Faltan campos en smtp.local.json: {', '.join(faltantes)}")
    if str(cfg.get("password", "")).startswith("PEGA-AQUI"):
        sys.exit("❌ La contraseña en smtp.local.json todavía es el texto de ejemplo.")
    return cfg


def cargar_config_resend() -> dict | None:
    """Carga la config de Resend si existe y es válida; si no, devuelve None.

    Resend es la vía por defecto (el correo migró a Cloudflare Email Routing +
    Resend; el SMTP del hosting gratuito quedó baneado). El SMTP queda de respaldo.
    """
    if not RESEND_CONFIG_PATH.exists():
        return None
    try:
        with RESEND_CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not cfg.get("api_key"):
        return None
    return cfg


def enviar_resend(cfg: dict, *, from_name: str, from_email: str, destino: str,
                  cc: list[str], bcc: str | None, asunto: str, cuerpo: str,
                  ruta_pdf: Path) -> str:
    """Envía la cotización por la API de Resend (con adjunto PDF). Devuelve el id."""
    pdf_b64 = base64.b64encode(ruta_pdf.read_bytes()).decode()
    payload = {
        "from": f"{from_name} <{from_email}>",
        "to": [destino],
        "subject": asunto,
        "text": cuerpo,
        "attachments": [{"filename": ruta_pdf.name, "content": pdf_b64}],
    }
    if cc:
        payload["cc"] = cc
    if bcc:
        payload["bcc"] = [bcc]

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": BROWSER_UA,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data.get("id", "")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:300]
        sys.exit(f"❌ Resend rechazó el envío (HTTP {e.code}): {detalle}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"❌ No se pudo enviar por Resend: {type(e).__name__}: {e}")


def registrar_en_panel(*, destino: str, asunto: str, cuerpo: str,
                       ruta_pdf: Path, resend_id: str | None) -> dict | None:
    """Registra la cotización enviada en el panel (worker D1) para que aparezca
    en la pestaña 'Enviados'. Best-effort: si falla, solo avisa (el correo ya salió).

    Necesita config/agente.local.json con 'worker_url' y 'panel_pass'. Si no está,
    no hace nada (retrocompatibilidad).
    """
    if not AGENTE_CONFIG_PATH.exists():
        return None
    try:
        with AGENTE_CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    worker_url = (cfg.get("worker_url") or "").rstrip("/")
    panel_pass = cfg.get("panel_pass")
    if not worker_url or not panel_pass:
        return None

    pdf_b64 = base64.b64encode(ruta_pdf.read_bytes()).decode()
    payload = {
        "para": destino,
        "asunto": asunto,
        "cuerpo": cuerpo,
        "adjunto_nombre": ruta_pdf.name,
        "adjunto_b64": pdf_b64,
        "resend_id": resend_id or None,
    }
    req = urllib.request.Request(
        f"{worker_url}/api/registrar-enviada",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-panel-pass": panel_pass,
            "User-Agent": BROWSER_UA,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:200]
        print(f"⚠️  No se pudo registrar en el panel (HTTP {e.code}): {detalle}")
        return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f"⚠️  No se pudo registrar en el panel: {type(e).__name__}: {e}")
        return None


def construir_cuerpo(cliente: str | None, mensaje: str | None) -> str:
    """Arma el texto del correo. Usa un cuerpo formal por defecto."""
    if mensaje:
        return mensaje

    saludo = f"Estimado/a {cliente}:" if cliente else "Estimado/a cliente:"
    return (
        f"{saludo}\n\n"
        "Junto con saludar, adjunto la cotización solicitada en formato PDF.\n\n"
        "Quedamos atentos a cualquier consulta o ajuste que necesite. "
        "Agradecemos su preferencia.\n\n"
        "Saludos cordiales,\n"
        f"{EMPRESA}\n"
        f"Tel: {TELEFONO}\n"
        f"{WEB}"
    )


def adjuntar_pdf(msg: EmailMessage, ruta_pdf: Path) -> None:
    """Adjunta el PDF al mensaje."""
    datos = ruta_pdf.read_bytes()
    msg.add_attachment(
        datos,
        maintype="application",
        subtype="pdf",
        filename=ruta_pdf.name,
    )


def enviar(cfg: dict, msg: EmailMessage) -> None:
    """Envía el mensaje según el modo (SSL o STARTTLS) configurado."""
    host = cfg["host"]
    port = int(cfg["port"])
    modo = cfg.get("secure", "ssl").lower()
    user = cfg["user"]
    password = cfg["password"]
    contexto = ssl.create_default_context()

    try:
        if modo == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=30, context=contexto) as server:
                server.login(user, password)
                server.send_message(msg)
        else:  # tls / starttls
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=contexto)
                server.ehlo()
                server.login(user, password)
                server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        sys.exit("❌ Error de autenticación: revisa usuario/contraseña en smtp.local.json.")
    except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
        sys.exit(f"❌ No se pudo enviar el correo: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Envía una cotización PDF por correo.")
    parser.add_argument("pdf", help="Ruta al archivo PDF de la cotización.")
    parser.add_argument("destino", help="Email del destinatario.")
    parser.add_argument("--cliente", help="Nombre del cliente (para saludo y asunto).")
    parser.add_argument("--asunto", help="Asunto personalizado.")
    parser.add_argument("--cc", action="append", default=[], help="Email en copia (repetible).")
    parser.add_argument("--mensaje", help="Cuerpo del correo personalizado.")
    args = parser.parse_args()

    ruta_pdf = Path(args.pdf)
    if not ruta_pdf.is_file():
        sys.exit(f"❌ No se encontró el PDF: {ruta_pdf}")
    if ruta_pdf.suffix.lower() != ".pdf":
        sys.exit(f"❌ El archivo no parece un PDF: {ruta_pdf}")

    asunto = args.asunto or (
        f"Cotización {EMPRESA} — {args.cliente}" if args.cliente else f"Cotización {EMPRESA}"
    )
    cuerpo = construir_cuerpo(args.cliente, args.mensaje)

    resend_cfg = cargar_config_resend()
    resend_id = None

    if resend_cfg:
        # Vía por defecto: Resend (dominio destaperapido.cl verificado).
        from_email = resend_cfg.get("from_email", "contacto@destaperapido.cl")
        from_name = resend_cfg.get("from_name", EMPRESA)
        # Por defecto NO se envía copia a contacto@ (ensuciaba el panel con correos
        # a uno mismo). Resend ya deja registro del envío; el respaldo era del hosting.
        guardar_copia = bool(resend_cfg.get("guardar_copia", False))
        bcc = from_email if (guardar_copia and from_email != args.destino) else None

        resend_id = enviar_resend(
            resend_cfg,
            from_name=from_name,
            from_email=from_email,
            destino=args.destino,
            cc=args.cc,
            bcc=bcc,
            asunto=asunto,
            cuerpo=cuerpo,
            ruta_pdf=ruta_pdf,
        )
        via = f"Resend (id {resend_id})" if resend_id else "Resend"
    else:
        # Respaldo: SMTP del hosting (config/smtp.local.json).
        cfg = cargar_config()
        from_email = cfg.get("from_email", cfg["user"])
        guardar_copia = bool(cfg.get("guardar_copia", False))

        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = formataddr((cfg.get("from_name", EMPRESA), from_email))
        msg["To"] = args.destino
        if args.cc:
            msg["Cc"] = ", ".join(args.cc)
        if guardar_copia and from_email != args.destino:
            msg["Bcc"] = from_email
        msg.set_content(cuerpo)
        adjuntar_pdf(msg, ruta_pdf)
        enviar(cfg, msg)
        via = "SMTP"
        bcc = from_email if (guardar_copia and from_email != args.destino) else None

    # Registrar en el panel (pestaña "Enviados") — best-effort, no bloquea el envío.
    registro = registrar_en_panel(
        destino=args.destino, asunto=asunto, cuerpo=cuerpo,
        ruta_pdf=ruta_pdf, resend_id=resend_id,
    )

    destinatarios = args.destino + (f" (CC: {', '.join(args.cc)})" if args.cc else "")
    print(f"✅ Cotización enviada a {destinatarios}")
    print(f"   Adjunto: {ruta_pdf.name}")
    print(f"   Asunto:  {asunto}")
    print(f"   Vía:     {via}")
    if bcc:
        print(f"   Copia de respaldo (CCO): {bcc}")
    if registro and registro.get("ok"):
        extra = " (ya estaba)" if registro.get("ya_registrada") else ""
        print(f"   Panel:   registrada en 'Enviados'{extra}")


if __name__ == "__main__":
    main()
