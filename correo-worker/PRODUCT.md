# Bandeja de cotizaciones — Destape Rápido

**Register:** product (app UI: se opera, no se lee)

## Qué es
Una bandeja de correo propia para una pyme chilena de destapes y arriendo de baños químicos.
No es un cliente de correo genérico: es el puesto de trabajo donde el dueño **revisa y aprueba
cotizaciones** que un agente de IA redactó por él. Corre como PWA sobre un Cloudflare Worker + D1.

## Quién la usa
Alejandro y el dueño del negocio. Un gásfiter/empresario, no un oficinista: mira el teléfono
entre visitas a terreno, muchas veces con una mano, a veces con mala señal en una obra. En
escritorio la deja abierta todo el día en una pestaña.

## El trabajo que resuelve
Que le contesten rápido y bien las cotizaciones sin estar pegado al correo. El éxito se mide en
**minutos hasta responder**, no en correos archivados.

## Jerarquía de la interfaz
1. Qué necesita respuesta AHORA y cuánto lleva esperando.
2. Qué escribió la IA y si se puede aprobar tal cual.
3. Todo lo demás (buscar, archivar, etiquetas).

## Restricciones
- Un solo archivo `panel.html` servido por el Worker: sin framework, sin compilación.
- Librerías solo con licencia permisiva, incrustadas (`vendor/`): es un producto que se vende.
- Debe funcionar con mala conexión y en pantalla de teléfono.

## Identidad visual (ya comprometida, no reinventar)
Verde petróleo `#0F6E6E` como color de marca, con su versión suave `#EAF4F2`; ámbar `#E0A82E`
para avisos; tinta `#1E2A2A`; gris `#5F6B6B`; líneas `#e3e8e8`; fondo `#f5f7f7`.
Tipografía del sistema (San Francisco / Segoe / Roboto): es una herramienta de trabajo, no una
pieza de marca.

## Referencia deliberada
Gmail. El dueño ya sabe usarlo; cada desviación gratuita le cuesta tiempo. Se copian sus medidas
y su vocabulario, y solo se mejora donde Gmail falla para este caso (tiempo de espera visible,
rastreadores bloqueados de verdad, borrador de la IA a la vista).
