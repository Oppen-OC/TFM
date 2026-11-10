from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from project.config import settings

# La UI habla con la API por HTTP y nada más: no importa `services/` ni carga el
# modelo. Si Streamlit necesita un dato nuevo, se añade un endpoint.
API_URL = settings.api_url

# El `CICLO_S` de `services/vivo.py`, copiado: la UI no puede importarlo.
REFRESCO_S = 40
# Una parada en hora punta tarda un ciclo entero (30-40 s) en responder.
TIMEOUT_PARADA_S = 90
TIMEOUT_PARADAS_S = 10

COLUMNAS = ["Línea", "A", "Va ahora", "Modelo P(>5 min)", "Regla simple", "Resultado"]

ANEXO = """
1. **Dónde está cada bus.** La EMT publica cada ~30 s la posición GPS de toda
   la flota, pero no dice qué bus es cuál: borra la tabla y la vuelve a llenar.
   La identidad se reconstruye emparejando cada posición con la del sondeo
   anterior que sea más cercana y físicamente posible (nada de saltos a más de
   70 km/h, `tracking.VEL_MAX_KMH`).
2. **Por dónde va en su ruta.** Cada posición se proyecta sobre el trazado de
   su línea, sacado del GTFS de la EMT, y se convierte en metros recorridos
   desde la cabecera.
3. **Qué horario sigue.** Con las tres primeras paradas del viaje se busca en
   el GTFS el viaje programado que mejor encaja con lo observado.
4. **Cuándo pasó por cada parada.** El bus casi nunca se ve justo en la parada:
   el instante de paso se interpola entre la última posición antes y la primera
   después.
5. **Si va tarde.** Retraso = hora real de paso − hora programada. Se conoce
   unos 80 s después del paso, cuando llega la posición siguiente y el viaje ya
   está asignado.
6. **La predicción.** El modelo parte del retraso que el bus lleva ahora y de
   cuánto suele ganar o perder en el tramo que le queda, y lo corrige con lo que
   han hecho en ese mismo tramo otros buses de su línea en los últimos 5-15 min.
   El resultado es la probabilidad de llegar a tu parada más de 5 min tarde.
"""


def _min(segundos: float) -> str:
    return f"{segundos / 60:+.1f} min".replace(".", ",")


def _utc(iso: str) -> datetime:
    t = datetime.fromisoformat(iso)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _veredicto(tarde: bool) -> str:
    return "tarde" if tarde else "a tiempo"


SIN_MODELO = "sin modelo"


def _modelo(f: dict) -> str:
    """La P(>5 min) de la fila; si la congelada (la que puntúa el marcador)
    difiere, se enseñan las dos. Sin modelo para el horizonte de ahora pero con
    una congelada (el bus pasó de h con modelo a h sin él), se enseña esa."""
    c = f["congelada"]
    congelada = c and f"{c['probabilidad']:.0%} · {_veredicto(c['llega_tarde'])}"
    if f["probabilidad"] is None:
        return f"ahora: sin modelo (congelada: {congelada})" if c else SIN_MODELO
    ahora = f"{f['probabilidad']:.0%} · {_veredicto(f['llega_tarde'])}"
    if c and c["llega_tarde"] != f["llega_tarde"]:
        return f"{ahora} (congelada: {congelada})"
    return ahora


def _regla(f: dict) -> str:
    """La regla simple que puntúa el marcador: la de la congelada. Si la de ahora
    difiere se enseña también; sin retraso en el último paso ni congelada, no hay
    dato (no «a tiempo»)."""
    c, ahora = f["congelada"], f["regla_llega_tarde"]
    if c is None:
        return "sin dato" if ahora is None else _veredicto(ahora)
    congelada = _veredicto(c["regla_llega_tarde"])
    if ahora is not None and ahora != c["regla_llega_tarde"]:
        return f"{congelada} (ahora: {_veredicto(ahora)})"
    return congelada


def _marca(ok: bool) -> str:
    return "✅" if ok else "❌"


def _resultado(f: dict) -> str:
    r = f["resultado"]
    if r is None:
        return "⏳"
    return (
        f"modelo {_marca(r['acierta_modelo'])} · regla {_marca(r['acierta_regla'])}"
        f" · real {_min(r['retraso_real_s'])}"
    )


def fila_tabla(f: dict) -> dict:
    va_ahora = "sin dato"
    if f["retraso_actual_s"] is not None:
        va_ahora = f"{_min(f['retraso_actual_s'])} (hace {f['edad_s']:.0f} s)"
    return dict(
        zip(
            COLUMNAS,
            [
                f["linea"],
                f["paradas"],
                va_ahora,
                _modelo(f),
                _regla(f),
                _resultado(f),
            ],
        )
    )


def _gris(fila: pd.Series) -> list[str]:
    # Gris solo sin modelo y sin nada congelado: con congelada hay predicción.
    estilo = "color: gray" if fila["Modelo P(>5 min)"] == SIN_MODELO else ""
    return [estilo] * len(fila)


def pedir(ruta: str, timeout: float) -> dict | list | None:
    """GET a la API; pinta el error y devuelve None si no hay datos."""
    try:
        r = requests.get(f"{API_URL}{ruta}", timeout=timeout)
    except requests.RequestException:
        st.error(f"API no disponible en {API_URL}")
        return None
    if r.status_code == 404:
        st.error("Parada desconocida")
    elif r.status_code == 503:
        st.error(r.json().get("detail", "Demo no disponible"))
    elif not r.ok:
        st.error(f"La API respondió {r.status_code}")
    else:
        return r.json()
    return None


def pintar_parada(stop_id: str) -> None:
    estado = pedir(f"/vivo/parada/{stop_id}", TIMEOUT_PARADA_S)
    if estado is None:
        return
    if estado["error"]:
        st.warning(estado["error"]["mensaje"])
    if estado["datos_hasta_utc"]:
        edad = (
            _utc(estado["ahora_utc"]) - _utc(estado["datos_hasta_utc"])
        ).total_seconds()
        st.caption(f"Dato de hace {edad:.0f} s")

    if estado["filas"]:
        tabla = pd.DataFrame([fila_tabla(f) for f in estado["filas"]])
        st.dataframe(tabla.style.apply(_gris, axis=1), hide_index=True)
    else:
        st.info("Ningún bus en camino a esta parada ahora mismo.")

    m = estado["marcador"]
    st.markdown(
        f"**modelo {m['aciertos_modelo']}/{m['verificados']} · "
        f"regla simple {m['aciertos_regla']}/{m['verificados']} · "
        f"casos en que discrepan: {m['discrepan']}**"
    )
    st.caption(
        "Regla simple = persistencia: «si ya va más de 5 min tarde, llegará tarde»."
    )


# El fragmento se repinta solo cada ciclo del servicio; el selector queda fuera
# para que cambiar de parada no espere al siguiente refresco.
@st.fragment(run_every=REFRESCO_S)
def refrescar(stop_id: str) -> None:
    pintar_parada(stop_id)


def main() -> None:
    st.title("Retrasos de la EMT en vivo, por parada")
    paradas = pedir("/vivo/paradas", TIMEOUT_PARADAS_S)
    if paradas:
        elegida = st.selectbox(
            "Parada",
            paradas,
            format_func=lambda p: f"{p['nombre']} ({p['stop_id']})",
        )
        refrescar(elegida["stop_id"])
    elif paradas == []:
        st.info("Hoy no hay paradas con servicio.")
    with st.expander("¿Cómo se calcula esto?"):
        st.markdown(ANEXO)


if __name__ == "__main__":  # `streamlit run` ejecuta el guion como __main__
    main()
