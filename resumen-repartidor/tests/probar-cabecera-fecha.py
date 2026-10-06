#!/usr/bin/env python3
"""probar-cabecera-fecha.py — la primera línea del aviso al repartidor y las fechas en palabras.

Pedido de Alejandro (6-oct-2026): «las entregas que sean hoy que diga mejor ENTREGA HOY y con un
icono de alarma; el 2026 está demás; que diga hoy martes; simplificar siempre un poquito».
Sin red: inyecta «hoy» y mira el texto. Uso: python3 resumen-repartidor/tests/probar-cabecera-fecha.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import resumen_repartidor as rr  # noqa: E402

malas = 0


def ok(bien: bool, que: str, extra: str = "") -> None:
    global malas
    print(("✓ " if bien else "✗ ") + que + ("" if bien else f"\n    {extra[:300]}"))
    if not bien:
        malas += 1


HOY = date(2026, 10, 6)  # martes
casos = [
    ("2026-10-06", "🚨 ENTREGA HOY · martes 6 de octubre"),
    ("2026-10-07", "🚚 ENTREGA MAÑANA · miércoles 7 de octubre"),
    ("2026-10-10", "🚚 ENTREGA · sábado 10 de octubre"),
    ("2027-01-04", "🚚 ENTREGA · lunes 4 de enero de 2027"),   # otro año: el año sí se dice
    ("2026-10-05", "🚚 ENTREGA · lunes 5 de octubre"),          # ayer: sin alarma, solo el día
    ("", "🚚 ENTREGA · "),                                       # sin fecha: no revienta
]
for iso, esperado in casos:
    salida = rr.cabecera_entrega(iso, HOY)
    ok(salida == esperado, f"cabecera {iso or '(vacía)'} → «{esperado}»", f"salió «{salida}»")

ok(rr.fecha_legible("2026-10-06", HOY) == "martes 6 de octubre", "fecha_legible sin cero ni año")
ok(rr.fecha_legible("2026-12-25", HOY) == "viernes 25 de diciembre", "fecha_legible día de dos cifras")
ok(rr.fecha_legible("mañana", HOY) == "mañana", "fecha_legible respeta lo que ya viene en palabras")

# el resumen completo de una entrega de HOY empieza con la alarma (lo que lee el repartidor)
entrega = {"fecha": date.today().isoformat(), "hora": "", "cliente": "Prueba", "comuna": "Lampa",
           "direccion": "Calle 1", "telefono": "+56911111111", "servicio": "1 baño químico",
           "periodo": "1 día", "pago": {"monto": 119000, "neto": 100000, "iva": 19000}}
resumen = rr.construir_resumen(entrega)
ok(resumen.startswith("🚨 ENTREGA HOY · "), "el resumen de una entrega de hoy arranca con la alarma", resumen[:80])
ok(" de 20" not in resumen.split("\n")[0], "la cabecera no dice el año", resumen.split("\n")[0])

print(f"\n{'TODO OK' if malas == 0 else f'{malas} falla(s)'}")
sys.exit(1 if malas else 0)
