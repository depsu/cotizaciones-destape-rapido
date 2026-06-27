# Comprobantes de pago (transferencias de comisión)

Acá van las **fotos de las transferencias** con las que el repartidor te paga la comisión.

## Cómo agregar una

1. Guarda la foto en esta carpeta, por ejemplo `pago-2026-06-24.png`.
2. En `resumen-repartidor/entregas.json`, en el objeto `comprobantes` (al final del archivo),
   mapea la **fecha de pago** (el `pagada_at` de las comisiones de ese pago) a la ruta:

   ```json
   "comprobantes": {
     "2026-06-24": "comprobantes/pago-2026-06-24.png"
   }
   ```

3. Regenera y publica (`python3 scripts/generar_listado.py` + push).

En la vista **💰 Comisión → Mis pagos recibidos**, cada "Pago N" tiene un botón
**📷 Ver transferencia** que abre esta foto. Si la foto aún no está subida, el modal
avisa "Aún no subiste la foto de este pago".
