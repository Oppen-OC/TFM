---
description: Sondea las fuentes en vivo y detecta drift de esquema contra los fixtures
---

Comprueba si las fuentes del TFM siguen vivas y si su esquema ha cambiado.
Ninguna fuente publica histórico: un cambio silencioso de esquema rompe capturas
que no se pueden repetir.

## Pasos

1. Corre el sondeo:

   ```
   python demo/explore.py
   ```

2. Para cada una de las cuatro fuentes, clasifica el resultado en exactamente uno
   de estos estados:
   - **viva** — responde y el esquema coincide con `demo/fixtures.json`
   - **caída** — no responde, timeout, o error HTTP
   - **drift** — responde, pero algún campo apareció, desapareció o cambió de tipo

   Fuentes: buses `EMT/Seguimiento_EMT/384`, tráfico `OPENDATA/Trafico/192` y
   `188`, Valenbisi `228`, y `flota.json` de Renfe (filtrado por
   `nucleo == "40"`).

3. Si hay drift, di el campo exacto, su tipo anterior y el nuevo, con una muestra
   del valor. No lo resumas como "el esquema cambió".

4. Revisa la salud de la captura ya escrita:

   ```
   python demo/diagnose.py
   ```

   Busca huecos temporales, snapshots duplicados y saltos en el volumen de filas.

5. Cierra con la validación offline, que debe quedar en verde:

   ```
   python demo/selftest.py
   ```

## Antes de reportar drift

Lee las fichas de `.claude/trampas/` con `capa: fuentes` — el índice ya lo tienes
en contexto. **Varias rarezas de estas fuentes son comportamiento conocido y
esperado, no drift.** Reportarlas como novedad es ruido; confundir una de ellas
con un fallo lleva a "arreglar" código correcto.

Si aparece una rareza nueva que no está fichada y que cualquiera volvería a
malinterpretar, abre ficha siguiendo la plantilla del README.

## Salida

Una tabla de cuatro filas: fuente, estado, evidencia. Después, el arreglo mínimo
si hay drift. Si todo está vivo, una línea basta.
