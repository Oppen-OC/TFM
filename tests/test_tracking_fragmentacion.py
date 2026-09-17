"""El eje que las otras métricas no ven: la trayectoria partida en trozos.

`err_ident`, `saltos`, `contaminadas` y `cola` miden FUSIÓN — que una trayectoria
reconstruida contenga más de un bus real. Todas son ciegas al fallo contrario:
parte un bus en diez trozos y los diez salen puros, así que las cuatro marcan
cero mientras el resultado es inservible aguas abajo. Un trozo de 7 min no
alcanza a cubrir un servicio de 40, y sin trayectoria completa no hay retraso
contra el horario teórico que medir.

`fragmentacion` es ciega en el sentido opuesto: un tracker que lo fusione todo la
deja en 1,0. Por eso los dos bloques se reportan juntos y nunca por separado, que
es lo que fija `test_la_fragmentacion_y_la_fusion_son_ejes_independientes`.

Los escenarios `flip_en` y `parciales` de `simular_flota` existen porque la flota
simulada por defecto no contiene ninguno de los dos fenómenos: ningún bus cambia
de `trayecto` y ningún snapshot llega recortado. Medidos sobre captura real del
27/08/2026, entre los dos explican ~93 % de las roturas de trayectoria.
"""

from __future__ import annotations

import pytest

from project.analysis.medir_tracking import medir
from project.analysis.simulacion import simular_flota
from project.tracking import HUECO_MAX_S, rastrear


def test_la_fragmentacion_y_la_fusion_son_ejes_independientes():
    """Test de discriminación: fija POR QUÉ se reportan las dos cosas.

    Si esta doble ceguera dejase de darse, la razón de ser de `fragmentacion`
    habría caducado y hay que volver a medirla, no borrar el test.
    """
    # Un snapshot recortado al 20 %: las cuatro métricas de fusión dan pleno
    # mientras el bus medio sale partido en 1,8 trozos. `tolerar_hueco=0` es
    # deliberado — lo que se fija aquí es la ceguera de las métricas, no el valor
    # por defecto de `rastrear()`, que ya no fragmenta en este escenario.
    parcial = medir(simular_flota(parciales={7: 0.2}), predictivo=True, tolerar_hueco=0)
    assert parcial["saltos"] == 0
    assert parcial["contaminadas"] == 0.0
    assert parcial["err_ident"] == 0.0
    assert parcial["fragmentacion"] > 1.5, (
        f"el snapshot parcial ya no fragmenta ({parcial['fragmentacion']:.2f}): "
        "remide antes de tocar este umbral"
    )

    # Y al revés: el tracker ingenuo saca fragmentación perfecta contaminando
    # el 5 % de las trayectorias.
    ingenuo = medir(simular_flota(n_snaps=80), predictivo=False, tolerar_hueco=0)
    assert ingenuo["fragmentacion"] == 1.0, (
        f"frag={ingenuo['fragmentacion']:.2f}: el ingenuo ya no es el fusionador "
        "limpio que este test necesita"
    )
    assert ingenuo["saltos"] > 0 and ingenuo["contaminadas"] > 0.0


def test_la_flota_limpia_no_se_fragmenta():
    """Línea base. Sin flip ni recortes, una trayectoria por bus."""
    m = medir(simular_flota(), predictivo=True)
    assert m["fragmentacion"] == 1.0, f"{m['fragmentacion']:.2f}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECTO CONOCIDO: rastrear() agrupa por (linea, trayecto), así que el "
        "giro en cabecera corta la cadena por construcción. Medido: frag=2.00, "
        "un bus por trozo de sentido. Sobre captura real del 27/08/2026 explica "
        "349 de las 375 bajas por hora. Al corregirlo, quitar este marcador."
    ),
)
def test_flip_de_trayecto_en_cabecera_no_parte_la_trayectoria():
    """El bus que da la vuelta sigue siendo el mismo bus.

    El escenario es la versión FÁCIL del problema: sólo cambia la etiqueta, el
    movimiento es continuo. Fallar aquí es fallar sin la dificultad añadida de
    invertir la marcha.
    """
    m = medir(simular_flota(flip_en=8), predictivo=True)
    assert m["fragmentacion"] == 1.0, f"{m['fragmentacion']:.2f}"


def test_flip_de_trayecto_en_cabecera_no_mezcla_identidades():
    """El bus que entra en el grupo del sentido opuesto no se lleva la identidad de otro.

    Fue `xfail` hasta 09/2026: 3 saltos y 1,7 % de trayectorias contaminadas. Lo
    corrigió `_suavizar_intercambios` sin buscarlo —es el mismo mecanismo, un
    intercambio que el sondeo siguiente delata—. La fragmentación del giro en
    cabecera, el test de arriba, sigue abierta.
    """
    m = medir(simular_flota(flip_en=8), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos"
    assert m["contaminadas"] == 0.0


def test_snapshot_parcial_no_parte_la_trayectoria():
    """El payload truncado es un fallo del colector, no una flota que se va.

    Causa en `data/raw/_TRUNCADOS.txt`: un miembro gzip a medias hace que
    `read_raw()` devuelva menos filas en silencio. Antes de `tolerar_hueco`, un
    sondeo al 20 % dejaba `frag=1.80`; sobre la captura real del 27/08/2026, tres
    sondeos parciales causaron 452 de las 883 roturas de la hora — el 51 %.
    """
    m = medir(simular_flota(parciales={7: 0.2}), predictivo=True)
    assert m["fragmentacion"] == 1.0, f"{m['fragmentacion']:.2f}"
    assert m["saltos"] == 0, f"{m['saltos']} saltos: lo arregló fusionando"


def test_tolerar_hueco_es_lo_que_arregla_el_parcial():
    """Discriminación: sin la tolerancia, el mismo escenario se fragmenta.

    Impide que el test de arriba pase por cualquier otro motivo y deje de vigilar
    lo que dice vigilar.
    """
    sin = medir(simular_flota(parciales={7: 0.2}), predictivo=True, tolerar_hueco=0)
    assert sin["fragmentacion"] > 1.5, f"{sin['fragmentacion']:.2f}"


def test_el_puente_se_acota_en_segundos_y_no_en_sondeos():
    """La tolerancia se pide en sondeos, pero un sondeo no siempre dura lo mismo.

    Durante la parada de 445 s del colector del 27/08/2026, «dos sondeos» eran
    7,5 min. La puerta física satura en `SALTO_MAX_M` a partir de 41 s, así que
    más allá de ahí deja de restringir: el puente admitiría a cualquiera dentro
    de 800 m. `HUECO_MAX_S` es lo que impide que eso ocurra.

    A cadencia nominal el puente funciona; a cadencia lenta se niega y el
    vehículo ausente arranca trayectoria nueva. Que la fragmentación reaparezca
    es la señal de que el tope mordió.
    """
    rapido = medir(simular_flota(dt=30.0, parciales={7: 0.2}), predictivo=True)
    assert rapido["fragmentacion"] == 1.0, "a 30 s el puente debería funcionar"

    # 90 s de cadencia: el vehículo ausente lleva 180 s fuera, por encima del tope.
    lento = medir(simular_flota(dt=90.0, parciales={7: 0.2}), predictivo=True)
    assert lento["fragmentacion"] > 1.0, (
        f"frag={lento['fragmentacion']:.2f}: puenteó 180 s con el tope en "
        f"{HUECO_MAX_S:.0f} s"
    )


def test_el_paso_inmediato_no_lo_acota_el_tope():
    """Frontera explícita del tope: solo acota el PUENTE, no el paso directo.

    Si el sondeo intermedio no existe —el colector estuvo parado— el paso largo
    es el paso inmediato, y ese compite siempre. Es deliberado: acotarlo también
    cambiaría el comportamiento histórico con `tolerar_hueco=0`, que es una
    decisión aparte de esta. Este test fija la frontera para que el día que se
    cambie, se cambie a sabiendas.
    """
    sim = simular_flota(n_snaps=12, huecos=(5,), dt=90.0)
    out = rastrear(sim.drop(columns=["verdad"]), tolerar_hueco=2)
    assert out.dropna(subset=["dt_s"])["dt_s"].max() > HUECO_MAX_S
