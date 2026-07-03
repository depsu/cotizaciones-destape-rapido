#!/usr/bin/env python3
"""Lector de correos entrantes (IMAP) - Destape Rápido

Uso:
    python scripts/leer_correos.py [dias]
    python scripts/leer_correos.py --desde 2026-06-27

Lista los correos recibidos en la casilla configurada desde una fecha.
Por defecto muestra los del último día (desde ayer). Solo LEE, no marca
ni borra nada. Usa las credenciales de config/smtp.local.json (la misma
casilla del SMTP).
"""
import email
import imaplib
import json
import ssl
import sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "smtp.local.json"


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"❌ No existe {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def decodificar(valor: str) -> str:
    """Decodifica cabeceras MIME (asuntos/remitentes con tildes)."""
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:
        return valor


def candidatos_host(user: str, host_smtp: str) -> list[str]:
    dominio = user.split("@")[-1] if "@" in user else host_smtp
    hosts = []
    # OJO: se omite el dominio "pelado" porque suele no tener IMAP y cuelga.
    for h in (host_smtp, f"imap.{dominio}", f"mail.{dominio}"):
        if h and h not in hosts:
            hosts.append(h)
    return hosts


def conectar(hosts: list[str], user: str, password: str) -> imaplib.IMAP4_SSL:
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE  # el cert del hosting no calza con el dominio
    ultimo_error = None
    for host in hosts:
        try:
            server = imaplib.IMAP4_SSL(host, 993, ssl_context=contexto, timeout=15)
            server.login(user, password)
            print(f"✅ Conectado a IMAP {host}:993\n")
            return server
        except Exception as e:  # noqa: BLE001
            print(f"• {host}:993 → falló ({e})")
            ultimo_error = e
    sys.exit(f"\n❌ No se pudo conectar a ningún servidor IMAP. Último error: {ultimo_error}")


def parse_args(argv: list[str]) -> datetime:
    if "--desde" in argv:
        i = argv.index("--desde")
        return datetime.strptime(argv[i + 1], "%Y-%m-%d")
    dias = 1
    for a in argv:
        if a.isdigit():
            dias = int(a)
    return datetime.now() - timedelta(days=dias)


def main() -> None:
    cfg = cargar_config()
    user = cfg.get("user", "")
    password = cfg.get("password", "")
    host_smtp = cfg.get("host", "").strip()
    if not password or password.startswith("PEGA"):
        sys.exit("❌ Falta la contraseña en config/smtp.local.json")

    desde = parse_args(sys.argv[1:])
    print(f"📥 Buscando correos en {user} desde {desde.strftime('%Y-%m-%d')}\n")

    server = conectar(candidatos_host(user, host_smtp), user, password)
    try:
        server.select("INBOX", readonly=True)  # readonly = no marca como leídos
        criterio = f'(SINCE "{desde.strftime("%d-%b-%Y")}")'
        typ, datos = server.search(None, criterio)
        if typ != "OK":
            sys.exit(f"❌ Error en la búsqueda: {typ}")

        ids = datos[0].split()
        if not ids:
            print("📭 No hay correos recibidos en ese rango.")
            return

        print(f"📬 {len(ids)} correo(s) encontrados:\n" + "=" * 60)
        for num in reversed(ids):  # más recientes primero
            typ, raw = server.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])
            de = decodificar(msg.get("From", ""))
            asunto = decodificar(msg.get("Subject", "(sin asunto)"))
            try:
                fecha = parsedate_to_datetime(msg.get("Date", "")).strftime("%Y-%m-%d %H:%M")
            except Exception:  # noqa: BLE001
                fecha = msg.get("Date", "?")

            # Extrae un fragmento del cuerpo en texto plano
            cuerpo = ""
            if msg.is_multipart():
                for parte in msg.walk():
                    if parte.get_content_type() == "text/plain" and "attachment" not in str(
                        parte.get("Content-Disposition", "")
                    ):
                        try:
                            cuerpo = parte.get_payload(decode=True).decode(
                                parte.get_content_charset() or "utf-8", errors="replace"
                            )
                            break
                        except Exception:  # noqa: BLE001
                            pass
            else:
                try:
                    cuerpo = msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:  # noqa: BLE001
                    cuerpo = ""
            fragmento = " ".join(cuerpo.split())[:300]

            print(f"\n📨 {fecha}")
            print(f"   De:     {de}")
            print(f"   Asunto: {asunto}")
            if fragmento:
                print(f"   {fragmento}")
            print("-" * 60)
    finally:
        try:
            server.logout()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
