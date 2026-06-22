#!/usr/bin/env python3
"""Diagnóstico de conexión SMTP.

Prueba varias combinaciones de host/puerto/seguridad usando las credenciales
de config/smtp.local.json y reporta cuál permite autenticarse correctamente.
No envía ningún correo: solo verifica login.

Uso:
    python scripts/test_smtp.py
"""

import json
import smtplib
import ssl
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "smtp.local.json"


def cargar_config() -> dict:
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"❌ No se encontró el archivo de configuración: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        sys.exit(f"❌ El JSON de configuración tiene un error de formato: {e}")


def probar(host: str, port: int, modo: str, user: str, password: str) -> bool:
    """Intenta autenticarse contra el servidor. Devuelve True si lo logra."""
    contexto = ssl.create_default_context()
    try:
        if modo == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=15, context=contexto) as server:
                server.login(user, password)
        else:  # tls / starttls
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=contexto)
                server.ehlo()
                server.login(user, password)
        return True
    except Exception as e:  # noqa: BLE001 — queremos ver cualquier fallo en el diagnóstico
        print(f"   ↳ falló: {type(e).__name__}: {e}")
        return False


def main() -> None:
    cfg = cargar_config()

    user = cfg.get("user", "")
    password = cfg.get("password", "")
    host_base = cfg.get("host", "").strip()

    if not password or password.startswith("PEGA-AQUI"):
        sys.exit(
            "❌ Falta la contraseña en config/smtp.local.json "
            "(el campo 'password' todavía tiene el texto de ejemplo)."
        )

    # Combinaciones más comunes a probar, en orden de probabilidad.
    dominio = user.split("@")[-1] if "@" in user else host_base
    hosts = []
    for h in (host_base, f"mail.{dominio}", f"smtp.{dominio}", dominio):
        if h and h not in hosts:
            hosts.append(h)

    intentos = []
    for h in hosts:
        intentos.append((h, 465, "ssl"))
        intentos.append((h, 587, "tls"))

    print(f"🔎 Probando autenticación SMTP para: {user}\n")

    exito = None
    for host, port, modo in intentos:
        print(f"• {host}:{port} ({modo.upper()}) ...")
        if probar(host, port, modo, user, password):
            print("   ✅ ¡Conexión y login correctos!")
            exito = (host, port, modo)
            break

    print()
    if exito:
        host, port, modo = exito
        print("🎉 Configuración que funciona:")
        print(f"   host    = {host}")
        print(f"   port    = {port}")
        print(f"   secure  = {modo}")
        print("\nActualiza estos valores en config/smtp.local.json si son distintos,")
        print("y ya podemos armar el envío de cotizaciones.")
    else:
        print("⚠️  Ninguna combinación funcionó.")
        print("Posibles causas:")
        print("  1. Contraseña incorrecta → cámbiala en el panel (E-mail Accounts).")
        print("  2. El hosting bloquea SMTP externo (común en planes gratuitos).")
        print("     En ese caso pasamos al plan B (servicio de envío gratuito).")


if __name__ == "__main__":
    main()
