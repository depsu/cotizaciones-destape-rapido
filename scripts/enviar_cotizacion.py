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
import json
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "smtp.local.json"

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

    cfg = cargar_config()

    asunto = args.asunto or (
        f"Cotización {EMPRESA} — {args.cliente}" if args.cliente else f"Cotización {EMPRESA}"
    )

    from_email = cfg.get("from_email", cfg["user"])

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((cfg.get("from_name", EMPRESA), from_email))
    msg["To"] = args.destino
    if args.cc:
        msg["Cc"] = ", ".join(args.cc)

    # Copia oculta a nosotros mismos como respaldo (configurable; activado por defecto).
    # No se guarda en "Enviados" de Roundcube, pero llega a la bandeja de entrada como registro.
    guardar_copia = bool(cfg.get("guardar_copia", True))
    if guardar_copia and from_email != args.destino:
        msg["Bcc"] = from_email

    msg.set_content(construir_cuerpo(args.cliente, args.mensaje))

    adjuntar_pdf(msg, ruta_pdf)

    enviar(cfg, msg)

    destinatarios = args.destino + (f" (CC: {', '.join(args.cc)})" if args.cc else "")
    print(f"✅ Cotización enviada a {destinatarios}")
    print(f"   Adjunto: {ruta_pdf.name}")
    print(f"   Asunto:  {asunto}")
    if guardar_copia and from_email != args.destino:
        print(f"   Copia de respaldo (CCO): {from_email}")


if __name__ == "__main__":
    main()
