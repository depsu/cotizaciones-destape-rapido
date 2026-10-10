#!/usr/bin/env python3
"""probar-dos-telefonos.py — dos teléfonos en la tarjeta del repartidor, nunca el mismo dos veces.

Pedido de Alejandro (10-oct-2026, 15-chats-enlazados A10, caso real p-407): «salió el mismo
número 2 veces… si tenemos un número de terreno ese sería el principal, y el otro de emergencia
y pagos… que salgan los 2 y no los mismos… en la página el número principal debe ser el de
terreno pero en los detalles igual debe salir eso».

Sin red: arma la entrega tal como la deja el conector (construirEntrega) y mira el texto del
WhatsApp (resumen_repartidor.construir_resumen) y el HTML de la tarjeta (generar_listado.tarjeta).
Uso: python3 resumen-repartidor/tests/probar-dos-telefonos.py
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


def veces(txt: str, num: str) -> int:
    return len(re.findall(re.escape(num), txt))


BASE = {"id": "2026-10-12-carlos-ruiz-moreno-8972", "fecha": "2026-10-12", "hora": "",
        "comuna": "Colina", "direccion": "Camino Lo Pinto 1500", "servicio": "Arriendo de baño químico",
        "cantidad": 1, "periodo": "1 mes",
        "pago": {"monto": 190000, "neto": 190000, "iva": 0, "con_factura": False,
                 "detalle_neto": "baño $160.000 + flete $30.000"}}
COMPRADOR = "Carlos Ruiz Moreno (compra · pagos · emergencia)"

# (a) terreno ≠ comprador: la ficha real de p-407 como la deja el conector nuevo
print("── (a) terreno ≠ comprador ──")
e = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56992978972",
     "contacto_respaldo": COMPRADOR, "telefono_respaldo": "56991292650",
     "notas": "RECIBE: Pablo Flores, maestro · 1 mes"}
r = rr.construir_resumen(e)
ok("👤 Cliente: Carlos Ruiz Moreno" in r, "WhatsApp: «👤 Cliente» es quien compra", r)
ok("📱 Teléfono en terreno: +56992978972" in r, "WhatsApp: el 📱 es el de terreno y se dice", r)
ok("🙋 Recibe en terreno: Pablo Flores, maestro\n" in r, "WhatsApp: RECIBE solo con el nombre", r)
ok("💳 Compra · pagos · emergencia: Carlos Ruiz Moreno +56991292650" in r, "WhatsApp: quien compra con su etiqueta", r)
ok(veces(r, "56992978972") == 1 and veces(r, "56991292650") == 1, "WhatsApp: cada número una sola vez", r)
h = gl.tarjeta(e)
ok('href="tel:56992978972"' in h and 'whatsapp://send?phone=56992978972' in h, "página: 📞 Llamar y WhatsApp van al de terreno", h[:800])
ok("phone=56991292650" not in h and 'href="tel:56991292650"' not in h, "página: ningún botón va al comprador (es el de terreno quien recibe)", h)
ok("Teléfono en terreno</span><p>+56992978972" in h, "página: el detalle dice que el principal es el de terreno", h)
ok('💳 Compra · pagos · emergencia</span><p>Carlos Ruiz Moreno · <a href="tel:+56991292650">+56991292650</a>' in h,
   "página: quien compra en los detalles, con su etiqueta y su número clicable", h)
ok("<b>🙋 Recibe en terreno:</b> Pablo Flores, maestro</li>" in h, "página: RECIBE sin el número repetido", h)
# el de terreno: 2 botones WhatsApp + 2 botones Llamar + el detalle; el del comprador: su enlace y su texto
ok(veces(h, "56992978972") == 5 and veces(h, "56991292650") == 2,
   "página: el de terreno (botones + detalle) y el del comprador (enlace + texto), nada más", h)

# (b) una tarjeta de ANTES del cambio: RECIBE con el número y ese mismo número de principal
print("── (b) tarjeta vieja: RECIBE traía el número del principal ──")
e = {**BASE, "cliente": "Pablo Flores", "telefono": "56992978972",
     "notas": "RECIBE: Pablo Flores, maestro +56992978972 · 1 mes"}
r = rr.construir_resumen(e)
ok("📱 Teléfono cliente: +56992978972" in r and "🙋 Recibe en terreno: Pablo Flores, maestro\n" in r
   and veces(r, "56992978972") == 1, "WhatsApp: se quita el número repetido de RECIBE", r)
h = gl.tarjeta(e)
ok("<b>🙋 Recibe en terreno:</b> Pablo Flores, maestro</li>" in h and "Teléfono</span><p>+56992978972" in h,
   "página: RECIBE sin el número y la etiqueta de siempre", h)

# (c) terreno = comprador: respaldo de la ficha con el MISMO número del principal
print("── (c) terreno = comprador ──")
e = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56991292650",
     "contacto_respaldo": "Carlos Ruiz Moreno", "telefono_respaldo": "56991292650",
     "notas": "RECIBE: Carlos, yo mismo · 1 mes"}
r = rr.construir_resumen(e)
ok("📱 Teléfono cliente: +56991292650" in r and "☎️ Respaldo: Carlos Ruiz Moreno\n" in r
   and veces(r, "56991292650") == 1, "WhatsApp: el respaldo con el mismo número queda solo con el nombre", r)
h = gl.tarjeta(e)
ok("☎️ Respaldo</span><p>Carlos Ruiz Moreno</p>" in h and "tel:+56991292650" not in h and veces(h, "56991292650") == 5,
   "página: el respaldo repetido no vuelve a poner el número (solo los botones y el detalle del principal)", h)

# (d) tres personas: quien compra en la segunda línea y el respaldo propio de la ficha en la tercera
print("── (d) comprador + respaldo propio de la ficha ──")
e = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56992978972",
     "contacto_respaldo": COMPRADOR, "telefono_respaldo": "56991292650",
     "notas": "RECIBE: Pablo Flores, maestro · RESPALDO: Portería +56922223333 · 1 mes"}
r = rr.construir_resumen(e)
ok("💳 Compra · pagos · emergencia: Carlos Ruiz Moreno +56991292650\n☎️ Respaldo: Portería +56922223333" in r,
   "WhatsApp: segunda y tercera línea, en ese orden", r)
ok(all(veces(r, n) == 1 for n in ("56992978972", "56991292650", "56922223333")), "WhatsApp: tres números, cada uno una vez", r)
h = gl.tarjeta(e)
ok("<b>☎️ Respaldo (de la ficha):</b> Portería +56922223333</li>" in h, "página: el respaldo de la ficha tiene su fila", h)
ok("RESPALDO" not in gl.notas_sin_marcas(e["notas"]), "la marca RESPALDO no cae a «Notas»", gl.notas_sin_marcas(e["notas"]))

# (e) sin terreno ni respaldo: la tarjeta de siempre, intacta
print("── (e) sin terreno ──")
e = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56991292650", "notas": "1 mes"}
r = rr.construir_resumen(e)
ok("👤 Cliente: Carlos Ruiz Moreno\n📱 Teléfono cliente: +56991292650\n🙋 Recibe en terreno: el cliente (no se indicó a otra persona)\n" in r
   and "💳" not in r and "☎️" not in r, "WhatsApp: las tres líneas de siempre y nada más", r)
h = gl.tarjeta(e)
ok("Teléfono</span><p>+56991292650" in h and "Respaldo" not in h, "página: etiqueta de siempre, sin respaldo", h)

# (f) PAGA con el número de quien compra: el COBRAR lleva el nombre, el número ya salió
print("── (f) PAGA con el número del comprador ──")
e = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56992978972",
     "contacto_respaldo": COMPRADOR, "telefono_respaldo": "56991292650",
     "notas": "RECIBE: Pablo Flores, maestro · PAGA: Carlos Ruiz Moreno +56991292650 · 1 mes"}
r = rr.construir_resumen(e)
ok("💵 COBRAR a Carlos Ruiz Moreno: $190.000" in r and veces(r, "56991292650") == 1,
   "WhatsApp: «COBRAR a Carlos Ruiz Moreno», sin repetir el número", r)
h = gl.tarjeta(e)
ok("<b>💵 Le cobra a:</b> Carlos Ruiz Moreno</li>" in h, "página: «Le cobra a» sin el número repetido", h)

# (g) R1 · refutación 10-oct: el WhatsApp de COBRO va a quien compra, no a quien recibe
print("── (g) cobro a quien compra (Python META + JS del panel) ──")
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

E_A = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56992978972", "estado": "entregado",
       "contacto_respaldo": COMPRADOR, "telefono_respaldo": "56991292650",
       "notas": "RECIBE: Pablo Flores, maestro · 1 mes"}
E_SOLO = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56991292650", "estado": "entregado"}
E_PORTERIA = {**BASE, "cliente": "Carlos Ruiz Moreno", "telefono": "56991292650", "estado": "entregado",
              "contacto_respaldo": "Portería", "telefono_respaldo": "56922223333"}
E_SIN_TEL = {**E_A, "telefono_respaldo": ""}
m = gl.meta_entrega(E_A)
ok(m["tel"] == "56992978972" and m["tel_cobro"] == "56991292650" and m["nombre_cobro"] == "Carlos Ruiz Moreno",
   "META horneado: tel = terreno, tel_cobro/nombre_cobro = quien compra", str(m))
m = gl.meta_entrega(E_SOLO)
ok(m["tel_cobro"] == "" and m["nombre_cobro"] == "", "META horneado: sin comprador aparte, sin tel_cobro (usa el principal)", str(m))
ok(gl.meta_entrega(E_PORTERIA)["tel_cobro"] == "", "META horneado: un respaldo de siempre (portería) NO recibe el cobro")
ok(gl.meta_entrega(E_SIN_TEL)["tel_cobro"] == "", "META horneado: comprador sin número → cobro al principal")


def funcion_js(nombre: str) -> str:
    """Saca `function nombre(...) {...}` del JS del panel contando llaves."""
    src = gl.SCRIPT_ESTADO
    i = src.index(f"function {nombre}(")
    j = src.index("{", i)
    prof = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            prof += 1
        elif src[k] == "}":
            prof -= 1
            if prof == 0:
                return src[i:k + 1]
    raise ValueError(nombre)


if shutil.which("node") is None:
    ok(False, "node no está instalado: no se pudo probar el JS del cobro")
else:
    js = "\n".join(funcion_js(n) for n in
                   ("soloDigitosJS", "contactoCobroJS", "banosDeJS", "metaDeData", "dateDe", "msgCobro", "telCobro"))
    prueba = js + r"""
var DIAS_JS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
var MESESL = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
function clp(n) { return '$' + (Math.round(Number(n) || 0)).toLocaleString('es-CL'); }
var CASOS = JSON.parse(process.argv[1]), HORNEADO = JSON.parse(process.argv[2]);
var META = {};
function fechaDe(id) { return (META[id] || {}).fecha || ''; }
var out = {};
Object.keys(CASOS).forEach(function (k) {
  // en vivo: META recalculado desde el `data` crudo de Supabase (metaDeData)
  META = {}; META[k] = metaDeData(CASOS[k]);
  var vivo = { tel: telCobro(k), msg: msgCobro(k) };
  // horneado: META tal como lo arma Python (meta_entrega)
  META = {}; META[k] = HORNEADO[k];
  out[k] = { vivo: vivo, horneado: { tel: telCobro(k), msg: msgCobro(k) } };
});
console.log(JSON.stringify(out));
"""
    casos = {"a": E_A, "solo": E_SOLO, "porteria": E_PORTERIA, "sintel": E_SIN_TEL}
    horneado = {k: gl.meta_entrega(v) for k, v in casos.items()}
    res = subprocess.run(["node", "-e", prueba, json.dumps(casos), json.dumps(horneado)],
                         capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        ok(False, "el JS del cobro corre", res.stderr)
    else:
        out = json.loads(res.stdout)
        for modo in ("vivo", "horneado"):
            a = out["a"][modo]
            ok(a["tel"] == "56991292650", f"JS {modo}: el botón Cobrar va al número de quien compra", str(a))
            ok(a["msg"].startswith("Hola Carlos Ruiz Moreno,") and "pendiente el pago de $190.000" in a["msg"],
               f"JS {modo}: el cobro saluda a quien compra", a["msg"])
            ok(out["solo"][modo]["tel"] == "56991292650" and out["solo"][modo]["msg"].startswith("Hola Carlos Ruiz Moreno,"),
               f"JS {modo}: sin comprador aparte, al principal de siempre", str(out["solo"][modo]))
            ok(out["porteria"][modo]["tel"] == "56991292650", f"JS {modo}: la portería no recibe el cobro",
               str(out["porteria"][modo]))
            ok(out["sintel"][modo]["tel"] == "56992978972", f"JS {modo}: comprador sin número → principal",
               str(out["sintel"][modo]))

# los helpers, al desnudo
print("── helpers ──")
ok(gl.sin_el_numero("Pablo Flores, maestro +56992978972", "56992978972") == "Pablo Flores, maestro", "sin_el_numero quita la cola igual")
ok(gl.sin_el_numero("Pablo Flores, maestro +56992978972", "56991292650") == "Pablo Flores, maestro +56992978972", "sin_el_numero deja un número distinto")
ok(gl.sin_el_numero("+56992978972", "992978972") == "", "sin_el_numero: solo el número → vacío (compara la cola de 8)")
ok(gl.sin_el_numero("portón 1234, casa 5678", "56992978972") == "portón 1234, casa 5678", "sin_el_numero no toca cifras que no son teléfono")
ok(gl.comprador_en_respaldo({"contacto_respaldo": COMPRADOR, "telefono_respaldo": "+56991292650"})
   == ("Carlos Ruiz Moreno", "Compra · pagos · emergencia", "56991292650"), "comprador_en_respaldo lee nombre, etiqueta y número")
ok(gl.comprador_en_respaldo({"contacto_respaldo": "Portería", "telefono_respaldo": "+56922223333"}) is None,
   "comprador_en_respaldo: un respaldo de siempre no es el comprador")

print(f"\n{'TODO OK' if malas == 0 else f'{malas} falla(s)'}")
sys.exit(1 if malas else 0)
