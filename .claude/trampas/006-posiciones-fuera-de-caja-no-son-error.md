---
id: 006
titulo: Las posiciones fuera del área urbana no son error de GPS
estado: vigente
capa: etiquetado
detectada: 2026-08-16
test: ninguno
---

## Síntoma

1.364 posiciones de la primera captura caen por debajo de 39,36° de latitud, muy
al sur del casco urbano de València. Parecen deriva de GPS o coordenadas
corruptas.

## Causa

Son correctas. Pertenecen a las **líneas 25 y 24**, que efectivamente bajan por la
costa hacia El Perellonet. La red de la EMT sale del término urbano.

Medido en `docs/05_hallazgos_primera_captura.md`, sección 5.

## Por qué se vuelve a caer aquí

Filtrar por caja geográfica es el primer saneamiento que se le ocurre a
cualquiera ante una nube de puntos con outliers, y aquí es una operación de una
línea que parece obviamente correcta. Nada avisa: el filtro no falla, solo borra
dos líneas enteras del dataset.

El daño es peor que perder datos. Las líneas 24 y 25 son de las **peor cubiertas
por sensores de tráfico** (20 % y 28 % de cobertura). Eliminarlas por caja
geográfica sesga la muestra justo hacia los corredores bien cubiertos, y con ello
infla la aparente utilidad de la fusión con tráfico — que es la contribución
central del TFM. Un sesgo de selección invisible, favorable a la hipótesis, y con
la etiqueta intacta.

Es exactamente el tipo de hallazgo que el tribunal busca.

## Guardia

Ninguna. No hay filtro geográfico en el código hoy, así que la trampa está latente
en vez de activa: muerde en cuanto alguien decida sanear coordenadas.

**Pendiente:**
1. Si se introduce filtro espacial, que sea por pertenencia a la traza del GTFS de
   la línea, nunca por caja.
2. Test que verifique que las líneas 24 y 25 sobreviven a cualquier saneamiento
   de coordenadas.

Regla general: **antes de descartar una posición por rara, comprobar a qué línea
pertenece.**
