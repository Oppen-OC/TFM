---
id: 007
titulo: La primera transición de cada trayectoria empareja sin predicción, y con buses en convoy eso es un empate exacto
estado: cerrada
capa: tracking
detectada: 2026-09-01
test: tests/test_tracking_identidad.py::test_convoy_en_fila_india_no_intercambia_identidad
---

## Síntoma

`rastrear()` devolvía trayectorias plausibles —número razonable de vehículos,
velocidades urbanas, cero excepciones— con la identidad intercambiada entre
buses de la misma línea. Sobre convoyes sintéticos con verdad-terreno:

| escenario | precisión | filas contaminadas |
|---|---|---|
| 4 buses a 60 m | **35,0 %** | 26 de 40, los 10 snapshots |
| 6 buses a 120 m | 78,3 % | 13 |
| 3 buses + uno que entra en servicio | 67,6 % | 12 |

`resumen()` no lo delataba: las cifras que imprime (trayectorias, longitud media,
`dist_m` p50/p90) salen prácticamente idénticas con la identidad bien y con la
identidad cruzada, porque los buses de un convoy recorren la misma distancia.

## Causa

La predicción de velocidad constante necesita el paso anterior. En la **primera**
transición de cada trayectoria ese paso no existe (`_plat` es `NaN`), así que
`lat_pred` cae a `lat` y el emparejamiento vuelve a ser vecino más cercano puro.

Con buses colineales a velocidad parecida eso no es un caso difícil: es un
**empate exacto**. Convoy a 15 km/h separado 120 m, paso por refresco 125 m:

```
correcto     : 125,0 + 125,0 = 250,0
intercambiado:   5,0 + 245,0 = 250,0
```

Hungarian desempata por orden de fila, es decir por el orden en que la EMT
serializó el JSON. Y el error no se queda en esa fila: escribe un `_plat`
equivocado, que envenena la predicción del paso siguiente, que vuelve a fallar.
Por eso los 10 snapshots salen contaminados y no solo el primero.

No es un caso de laboratorio. Sobre la captura del 16/08/2026 (280.586 filas,
2.740 snapshots), **el 1,9 % de las posiciones en horario de servicio tiene un compañero de su misma
(línea, trayecto) a menos de un paso de refresco, y el 44 % a menos de 60 m**.
Mediana del vecino más cercano de la misma línea: 100 m. La configuración
degenerada es el caso normal.

Arreglado sembrando la predicción de las filas sin velocidad propia con el
**desplazamiento del centroide** de su grupo `(línea, trayecto)`, que estima el
movimiento de conjunto sin conocer la correspondencia: ver
`_sembrar_por_centroide` en `src/project/tracking.py`.

## Por qué se vuelve a caer aquí

El código dice, y con razón, que la predicción resuelve el cruce de dos buses.
Eso invita a leer el arranque en frío como "una fila sin predicción, ruido de
borde". Son dos suposiciones falsas encadenadas: ni es una fila —el 4,1 % de los
emparejamientos reales se hacen en frío, y 826 de 969 trayectorias de una ventana
diurna nacen fuera del primer snapshot— ni es ruido, porque propaga.

Y el empate es contraintuitivo. Uno espera que dos buses juntos sean un caso
"difícil" que se falla a veces; la aritmética dice que es un caso **imposible**
que se acierta la mitad de las veces por sorteo. La diferencia importa: un caso
difícil se mejora afinando el coste, un empate solo se rompe metiendo información
que no estaba en la matriz.

El instinto correcto —"ante la duda no emparejes, rompe la cadena"— es aquí
**activamente peor**, y esto es lo que más fácil vuelve a costar caro. Medido con
un test de razón sobre el segundo mejor candidato: la cobertura baja al 9-67 % y
la precisión cae *por debajo* de la del código sin arreglar (40 % en convoy).
Cada rotura abre una trayectoria nueva, que vuelve a arrancar en frío, que vuelve
a empatar. Fragmentar realimenta el problema en vez de contenerlo.

Límites que **no** son bugs y no hay que perseguir: vehículos equiespaciados
sobre una ruta en anillo, y dos buses capturados en la misma coordenada exacta.
En ambos, permutar identidades es una simetría de lo observado; ningún método que
solo mire posiciones los distingue, y la capa de la EMT no publica ni rumbo ni
velocidad (solo `gid`, `linea`, `trayecto`, `fecha` y geometría). Están fijados
como `xfail(strict=True)` para que, si alguna vez pasan a verde, alguien
justifique por qué.

## Guardia

`tests/test_tracking_identidad.py`, escenarios deterministas con verdad-terreno
construida a mano. El que fija esta trampa es
`test_convoy_en_fila_india_no_intercambia_identidad`, parametrizado sobre cuatro
configuraciones de convoy; `test_el_convoy_discrimina_entre_predictivo_e_ingenuo`
verifica que el escenario sigue hundiendo al modo ingenuo, para que no se
convierta en un test que aprueba sin ejercer nada.
