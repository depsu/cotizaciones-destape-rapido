#!/usr/bin/env python3
"""probar-cobro-iva.py — el COBRO con su IVA y el ASEO según el plazo, en el WhatsApp del
repartidor (resumen_repartidor.construir_resumen) y en su tarjeta web (generar_listado.tarjeta).

Nació el 5-oct-2026 con el pedido de Alejandro («que el valor final, si va el IVA, se vea el
IVA, y el mensaje para el repartidor con el valor total con el IVA incluido») y el error de la
vista previa real de p-339 («dos semanas» salía «Sin aseo programado (7 días)»).

Sin red ni Supabase: arma entregas como las arma el conector del bot y mira el texto.
Uso: python3 resumen-repartidor/tests/probar-cobro-iva.py   (sale 1 si algo falla)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generar_listado as gl  # noqa: E402
import resumen_repartidor as rr  # noqa: E402

malas = 0


def ok(bien: bool, que: str, extra: str = "") -> None:
    global malas
    print(("✓ " if bien else "✗ ") + que + ("" if bien else f"\n    {extra[:600]}"))
    if not bien:
        malas += 1


def entrega(**pago) -> dict:
    """Una entrega como la arma el conector (integracion.construirEntrega) desde el 5-oct."""
    base = {"id": "2026-10-10-prueba-0001", "cliente": "Prueba", "telefono": "56911111111",
            "fecha": "2026-10-10", "servicio": "Arriendo de baño químico x2", "cantidad": 2,
            "direccion": "Av. Siempre Viva 123", "comuna": "Maipú", "periodo": "3 días",
            "notas": "3 días", "estado": "pendiente",
            "aseo": "Sin aseo programado (3 días): incluye traslado, instalación y retiro"}
    con = pago.pop("_con_factura_entrega", None)
    base["pago"] = {"nota": "3 días", **pago}
    if con:
        base["factura"] = {"requiere": True}
    return base


def texto_tarjeta(e: dict) -> str:
    h = gl.tarjeta(e)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", h))


print("── con factura: el total con IVA, y el neto + IVA debajo ──")
e = entrega(monto=773500, neto=650000, iva=123500, con_factura=True,
            detalle_neto="2 baños $600.000 + flete $50.000",
            desglose="2 baños $600.000 + flete $50.000 = $650.000 neto + IVA = $773.500",
            _con_factura_entrega=True)
r = rr.construir_resumen(e)
ok("💵 COBRAR AL CLIENTE: $773.500 (IVA incluido)" in r, "WhatsApp: «COBRAR AL CLIENTE: $773.500 (IVA incluido)»", r)
ok("   Neto $650.000 + IVA $123.500 · con factura" in r, "WhatsApp: «Neto $650.000 + IVA $123.500 · con factura»", r)
ok("   Detalle del neto: 2 baños $600.000 + flete $50.000" in r, "WhatsApp: el detalle del neto", r)
ok("= $650.000 neto + IVA = $773.500" not in r, "WhatsApp: el desglose viejo ya no se repite", r)
t = texto_tarjeta(e)
ok("💵 $773.500 con IVA" in t, "tarjeta cerrada: «💵 $773.500 con IVA»", t)
ok("IVA incluido" in t and "Neto $650.000 + IVA $123.500 · con factura" in t,
   "tarjeta: «IVA incluido» y «Neto $650.000 + IVA $123.500 · con factura»", t)

print("── sin factura: el neto, y se dice ──")
e = entrega(monto=650000, neto=650000, iva=0, con_factura=False,
            detalle_neto="2 baños $600.000 + flete $50.000",
            desglose="2 baños $600.000 + flete $50.000 = $650.000")
r = rr.construir_resumen(e)
ok("💵 COBRAR AL CLIENTE: $650.000 (neto, sin factura)" in r, "WhatsApp: «$650.000 (neto, sin factura)»", r)
ok("   Detalle: 2 baños $600.000 + flete $50.000" in r and "IVA $" not in r, "WhatsApp: el detalle, sin IVA", r)
t = texto_tarjeta(e)
ok("💵 $650.000 neto" in t and "Neto, sin factura" in t, "tarjeta: «$650.000 neto» y «Neto, sin factura»", t)

print("── quién paga: la marca PAGA cambia el destinatario, no la cuenta ──")
e = entrega(monto=214200, neto=180000, iva=34200, con_factura=True, _con_factura_entrega=True)
e["notas"] = "PAGA: Grace +56977608721 · 1 día"
r = rr.construir_resumen(e)
ok("💵 COBRAR a Grace +56977608721: $214.200 (IVA incluido)" in r, "WhatsApp: «COBRAR a <quien paga>: $214.200 (IVA incluido)»", r)

print("── entregas viejas: lo que no dice si lleva IVA se muestra como siempre ──")
e = entrega(monto=95200, desglose="baño $80.000 = $80.000 neto + IVA = $95.200")
r = rr.construir_resumen(e)
ok("💵 COBRAR AL CLIENTE: $95.200\n" in r and "   baño $80.000 = $80.000 neto + IVA = $95.200" in r,
   "sin marca: el monto y el desglose de siempre, sin afirmar nada", r)
e = entrega(monto=190400, desglose="baño $160.000 = $160.000 neto + IVA = $190.400", _con_factura_entrega=True)
r = rr.construir_resumen(e)
ok("$190.400 (IVA incluido)" in r and "Neto $160.000 + IVA $30.400 · con factura" in r,
   "con factura.requiere (despachos de antes del 5-oct): el neto se recupera del monto", r)
e = entrega(monto=773500, desglose="2 baños $600.000 + flete $50.000 = $650.000 neto + IVA = $773.500",
            _con_factura_entrega=True)
r = rr.construir_resumen(e)
ok("Detalle del neto: 2 baños $600.000 + flete $50.000" in r, "con factura.requiere: el detalle sale del desglose de antes", r)

print("── el neto se recupera exacto del total (mismo redondeo que el PDF) ──")
peores = [n for n in range(0, 2_000_001, 10) if gl.cuenta_cobro(
    {"pago": {"monto": n + round(n * 0.19)}, "factura": {"requiere": True}})["neto"] != n]
ok(not peores, "de 0 a 2.000.000 (cada 10 pesos): neto + IVA vuelve al mismo neto", str(peores[:5]))

print("── varios meses: la tarjeta dice que es el valor de cada mes ──")
e = entrega(monto=190400, neto=160000, iva=30400, con_factura=True, meses=2, _con_factura_entrega=True)
e["periodo"], e["notas"] = "al menos 2 meses", "al menos 2 meses"
t = texto_tarjeta(e)
ok("1.er mes (de 2) · se cobra mes a mes" in t, "tarjeta: «1.er mes (de 2) · se cobra mes a mes» (pago.meses)", t)
e = entrega(monto=190400, desglose="baño $160.000 = $160.000 neto + IVA = $190.400", _con_factura_entrega=True)
e["periodo"], e["notas"] = None, "Arriendo 2 meses (prolongable)"
ok("1.er mes (de 2) · se cobra mes a mes" in texto_tarjeta(e), "entrega de antes (sin marca): los meses se leen de su plazo escrito")
e = entrega(monto=190400, neto=160000, iva=30400, con_factura=True, _con_factura_entrega=True)
e["periodo"], e["notas"] = "1 mes", "1 mes"
ok("1.er mes" not in texto_tarjeta(e), "un mes: sin esa línea")

print("── refutación: los meses del cobro salen de UN lugar (pago.meses del despacho) ──")
e = entrega(monto=226100, neto=190000, iva=36100, con_factura=True, meses=2, _con_factura_entrega=True)
e["periodo"], e["notas"] = "2 meses", "aprox 51 días"
r = rr.construir_resumen(e)
ok("   Corresponde a: 1.er mes (de 2) · se cobra mes a mes" in r, "WhatsApp: «Corresponde a: 1.er mes (de 2)» con pago.meses", r)
ok("1.er mes (de 2) · se cobra mes a mes" in texto_tarjeta(e), "tarjeta: el mismo «1.er mes (de 2)»")
e = entrega(monto=226100, neto=190000, iva=36100, con_factura=True, _con_factura_entrega=True)
e["periodo"], e["notas"] = "2 meses", "aprox 44 días"
ok(gl.meses_del_cobro(e) == 1 and "1.er mes" not in texto_tarjeta(e),
   "despacho nuevo sin pago.meses: un mes, aunque el periodo redondeado diga «2 meses»")

print("── refutación: con IVA no es «pidió factura» ──")
e = entrega(monto=154700, neto=130000, iva=24700, con_factura=True, _con_factura_entrega=True)
e["factura"] = {"requiere": True, "pedida": False}
r = rr.construir_resumen(e)
ok("Con IVA. Si el cliente necesita factura, pedirle razón social, RUT, giro y dirección al coordinar." in r
   and "Datos pendientes" not in r, "WhatsApp: sin «⚠️ Datos pendientes» cuando nadie pidió factura", r)
ok("Si el cliente necesita factura, pedirle sus datos al coordinar." in texto_tarjeta(e), "tarjeta: lo mismo")
e["factura"] = {"requiere": True}
ok("⚠️ Datos pendientes" in rr.construir_resumen(e), "factura pedida sin datos: se piden como siempre")

print("── plazos en palabras y el aseo del tarifario (desde una semana corre el aseo) ──")
ok(gl.dias_del_plazo("media semana") == 4 and gl.texto_aseo({"periodo": "media semana"}).startswith("Sin aseo periódico"),
   "«media semana» es menos de una semana")
for txt, dias in [("dos semanas", 14), ("una semana", 7), ("medio mes", 15), ("quince días", 15),
                  ("3 semanas", 21), ("una semana y media", 11), ("3 días", 3), ("un día", 1),
                  ("fin de semana", 2), ("una quincena", 15), ("mensual", None), ("evento", None)]:
    ok(gl.dias_del_plazo(txt) == dias, f"«{txt}» = {dias} días", str(gl.dias_del_plazo(txt)))
for txt in ["dos semanas", "una semana", "medio mes", "15 días", "3 semanas", "un mes", "mensual", "7 días"]:
    ok(gl.texto_aseo({"periodo": txt}) == gl.ASEO_LARGO, f"aseo con «{txt}»: {gl.ASEO_LARGO}", gl.texto_aseo({"periodo": txt}))
for txt, dias in [("3 días", 3), ("6 días", 6), ("un día", 1)]:
    ok(gl.texto_aseo({"periodo": txt}).startswith(f"Sin aseo periódico ({dias} día"), f"aseo con «{txt}»: sin ciclo",
       gl.texto_aseo({"periodo": txt}))
ok(not gl.RE_LARGO.search("medio mes") and not rr.RE_LARGO.search("medio mes") and gl.RE_LARGO.search("un mes"),
   "«medio mes» no es un arriendo mensual (en los dos archivos)")
r = rr.construir_resumen({**entrega(monto=154700, neto=130000, iva=24700, con_factura=True),
                          "periodo": "medio mes", "notas": "medio mes", "aseo": ""})
ok("🔁 Renovación" not in r and "↩️ Retiro: pendiente de coordinar" in r, "WhatsApp: «medio mes» no promete renovación mensual", r)

print("\nTODO VERDE" if malas == 0 else f"\n{malas} mala(s)")
sys.exit(1 if malas else 0)
