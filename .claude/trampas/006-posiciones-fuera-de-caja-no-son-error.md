---
id: 006
titulo: Las posiciones fuera del área urbana no son error de GPS
estado: cerrada
capa: etiquetado
detectada: 2026-08-16
test: tests/test_mapmatching.py::test_lejos_del_centro_pero_sobre_la_ruta_no_se_descarta
---

## Síntoma

1.364 posiciones de la primera captura caen por debajo de 39,36° de latitud, muy
al sur del casco urbano. Parecen deriva de GPS o coordenadas corruptas.

## Causa

Son correctas: pertenecen a las **líneas 24 y 25**, que bajan por la costa hacia
El Perellonet. La red de la EMT sale del término urbano.

Medido en `docs/05_hallazgos_primera_captura.md`, sección 5.

## Por qué se vuelve a caer aquí

Filtrar por caja geográfica es el primer saneamiento que se le ocurre a
cualquiera ante una nube de puntos con outliers, y es una línea de código que
parece obviamente correcta. Nada avisa: el filtro no falla, solo borra dos
líneas enteras.

El daño es peor que perder datos. Las líneas 24 y 25 son de las **peor cubiertas
por sensores de tráfico** (20 % y 28 %). Eliminarlas sesga la muestra hacia los
corredores bien cubiertos e infla la aparente utilidad de la fusión con tráfico,
que es la contribución central del TFM. Un sesgo de selección invisible,
favorable a la hipótesis y con la etiqueta intacta.

## Guardia

`tests/test_mapmatching.py::test_lejos_del_centro_pero_sobre_la_ruta_no_se_descarta`:
un recorrido 22 km al sur, a ~39,27°, por debajo del corte que usaría una caja.
El test comprueba primero que el escenario baja de 39,36°, porque si no, no
guardaría nada.

La regla que implementa `mapmatching.emparejar()`: se descarta por **distancia al
trazado GTFS de su línea**, nunca por caja. Verificada por mutación —añadir un
filtro por latitud pone el test rojo (mutante 045, `docs/11_auditoria_tests.md`)—
y sobre los 17 días: las 24 y 25 quedan a 2-4 m de mediana de su trazado
(`docs/bitacora/016-el-map-matching-casa-con-el-gtfs.md`).
