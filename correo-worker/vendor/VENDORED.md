# Librerías vendoreadas (licencias verificadas)

Servidas por el propio Worker en `/vendor/*` (sin CDN externo, sin build step).
Solo licencias permisivas — **prohibido agregar aquí código GPL/AGPL**.

| Archivo | Proyecto | Versión | Licencia | Origen |
|---|---|---|---|---|
| `purify.min.js.txt` | DOMPurify (Cure53) | 3.4.13 | Apache-2.0 OR MPL-2.0 (usamos Apache-2.0) | github.com/cure53/DOMPurify |
| `squire.js.txt` | Squire (Fastmail) | 2.4.8 | MIT | github.com/fastmail/Squire |

> La extensión `.txt` es a propósito: con `.js`, el bundler de Wrangler intenta **ejecutarlas
> dentro del Worker** (y usan `document`, que no existe ahí). Se sirven como texto en
> `/vendor/purify.min.js` y `/vendor/squire.js`.

Además, inline dentro de `panel.html` (marcado con comentario de licencia):
- Detector de gestos swipe (~40 líneas propias inspiradas en swiped-events, MIT, john-doherty/swiped-events).

Para actualizar: descargar el dist oficial desde jsDelivr con la versión fijada y
actualizar esta tabla. Nada de `npm install` — el panel es single-file sin build.
