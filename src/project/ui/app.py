from datetime import datetime, timezone

import requests
from nicegui import run, ui

from project.config import settings

# La UI habla con la API por HTTP y nada más: no importa `services/` ni carga el
# modelo. Si la página necesita un dato nuevo, se añade un endpoint.
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
   cuánto suele ganar o perder en el tramo que le queda, y lo corrige con el
   retraso de otros buses de su línea en el último 1, 5 y 15 min y con lo que ha
   ganado o perdido toda la flota en ese mismo tramo en los últimos 5-15 min.
   El resultado es la probabilidad de llegar a tu parada más de 5 min tarde.
"""


def _min(segundos: float) -> str:
    return f"{segundos / 60:+.1f} min".replace(".", ",")


def _utc(iso: str) -> datetime:
    t = datetime.fromisoformat(iso)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _hora_local(iso: str) -> str:
    return _utc(iso).astimezone(settings.zona_horaria).strftime("%H:%M")


def _edad_s(iso: str, ahora: datetime | None = None) -> float:
    """Segundos desde `iso` hasta el reloj de ahora, no hasta el `ahora_utc` del
    ciclo: con la respuesta en caché este se queda hasta 40 s atrás."""
    ahora = ahora or datetime.now(timezone.utc)
    return (ahora - _utc(iso)).total_seconds()


def _aviso(estado: dict) -> str | None:
    """El error del ciclo, con la hora local del último sondeo bueno si lo hubo."""
    if not estado["error"]:
        return None
    aviso = estado["error"]["mensaje"]
    if estado["datos_hasta_utc"]:
        aviso += (
            f" (último sondeo bueno a las {_hora_local(estado['datos_hasta_utc'])})"
        )
    return aviso


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


def gris(fila: dict) -> bool:
    # Gris solo sin modelo y sin nada congelado: con congelada hay predicción.
    return fila["Modelo P(>5 min)"] == SIN_MODELO


def pedir(ruta: str, timeout: float) -> tuple[dict | list | None, str | None]:
    """GET a la API: (datos, None), o (None, el error que se enseña)."""
    try:
        r = requests.get(f"{API_URL}{ruta}", timeout=timeout)
    except requests.Timeout:
        return (
            None,
            "La API está ocupada calculando; vuelve a intentarlo en unos segundos",
        )
    except requests.RequestException:
        return None, f"API no disponible en {API_URL}"
    # Un proxy o una página de error no traen JSON: sin esto, la excepción deja
    # el spinner girando y la página sin mensaje.
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    if r.status_code == 404:
        return None, "Parada desconocida"
    if r.status_code == 503:
        return None, (cuerpo or {}).get("detail", "Demo no disponible")
    if not r.ok:
        return None, f"La API respondió {r.status_code}"
    if cuerpo is None:
        return None, "La API respondió algo que no es JSON"
    return cuerpo, None


def vista(estado: dict) -> dict:
    """Lo que se pinta de una parada, sin pintarlo."""
    m = estado["marcador"]
    return {
        "aviso": _aviso(estado),
        "edad": estado["datos_hasta_utc"]
        and f"Dato de hace {_edad_s(estado['datos_hasta_utc']):.0f} s",
        "filas": [fila_tabla(f) for f in estado["filas"]],
        "marcador": (
            f"**modelo {m['aciertos_modelo']}/{m['verificados']} · "
            f"regla simple {m['aciertos_regla']}/{m['verificados']} · "
            f"casos en que discrepan: {m['discrepan']}**"
        ),
    }


TABLA = [{"name": c, "label": c, "field": c, "align": "left"} for c in COLUMNAS]


def pintar(estado: dict | None, error: str | None) -> None:
    if error:
        ui.label(error).classes("text-negative")
        return
    v = vista(estado)
    if v["aviso"]:
        ui.label(v["aviso"]).classes("text-warning")
    if v["edad"]:
        ui.label(v["edad"]).classes("text-caption text-grey")
    if v["filas"]:
        filas = [{"id": i, "gris": gris(f), **f} for i, f in enumerate(v["filas"])]
        tabla = ui.table(columns=TABLA, rows=filas)
        tabla.props[":table-row-class-fn"] = "row => row.gris ? 'text-grey' : ''"
    else:
        ui.label("Ningún bus en camino a esta parada ahora mismo.")
    ui.markdown(v["marcador"])
    ui.label(
        "Regla simple = persistencia: «si ya va más de 5 min tarde, llegará tarde»."
    ).classes("text-caption text-grey")


@ui.page("/")
async def pagina() -> None:
    ui.label("Retrasos de la EMT en vivo, por parada").classes("text-h4")
    cabecera = ui.column()
    spinner = ui.spinner(size="lg")
    spinner.visible = False
    contenido = ui.column()
    with ui.expansion("¿Cómo se calcula esto?"):
        ui.markdown(ANEXO)

    # Las peticiones van en un hilo (`run.io_bound`): una parada en punta tarda
    # un ciclo entero y, en el bucle de eventos, congelaría la página de todos.
    await ui.context.client.connected()
    selector: ui.select | None = None

    async def cargar_paradas() -> None:
        # Si falla, el siguiente tic lo reintenta: la página se recupera sola
        # cuando vuelve la API, sin recargar a mano.
        nonlocal selector
        respuesta = await run.io_bound(pedir, "/vivo/paradas", TIMEOUT_PARADAS_S)
        if respuesta is None:  # la app se apaga o se canceló la llamada
            return
        paradas, error = respuesta
        cabecera.clear()
        with cabecera:
            if error:
                ui.label(error).classes("text-negative")
                return
            if not paradas:
                ui.label("Hoy no hay paradas con servicio.")
                return
            selector = ui.select(
                {p["stop_id"]: f"{p['nombre']} ({p['stop_id']})" for p in paradas},
                label="Parada",
                value=paradas[0]["stop_id"],
                with_input=True,
            ).classes("w-96")
        selector.on_value_change(cambiar)
        await refrescar()

    async def cambiar() -> None:
        # Cambiar de parada no espera al siguiente tic, y lo de la anterior no
        # se queda debajo de la nueva mientras responde la API.
        contenido.clear()
        await refrescar()

    en_curso: set[str] = set()

    async def refrescar() -> None:
        if selector is None:
            await cargar_paradas()
            return
        stop_id = selector.value
        if stop_id is None or stop_id in en_curso:  # el tic llega con la anterior
            return
        en_curso.add(stop_id)
        spinner.visible = True
        try:
            ruta = f"/vivo/parada/{stop_id}"
            respuesta = await run.io_bound(pedir, ruta, TIMEOUT_PARADA_S)
        finally:
            en_curso.discard(stop_id)
        # Si se cambió de parada mientras esperaba, la respuesta ya no toca.
        if respuesta is None or stop_id != selector.value:
            return
        spinner.visible = False
        contenido.clear()
        with contenido:
            pintar(*respuesta)

    ui.timer(REFRESCO_S, refrescar)


def main() -> None:
    ui.run(title="EMT en vivo", reload=False, show=False)  # 0.0.0.0:8080


if __name__ in {"__main__", "__mp_main__"}:
    main()
