"""Las diez paradas del camino de la ingesta y lo que las mantiene honradas.

Cada parada dice qué cuenta y a qué ficha remite; las cifras las pone el
exportador desde el dato. Tres guardias:

- `redactar` no deja un hueco sin rellenar: una plantilla con un hueco sin cifra
  falla, no se publica con el hueco vacío.
- `cotejar` compara cada cifra recalculada con la que publicó su ficha. El
  instrumento también miente (trampa 004): si no cuadra, se para.
- `validar_prueba` comprueba el contrato con la página antes de escribir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from project.config import RAIZ

LIMITE_BYTES = 2_000_000

CAPITULOS = [
    {"n": 1, "nombre": "Introducción"},
    {"n": 2, "nombre": "Estado del arte"},
    {"n": 3, "nombre": "Análisis del problema"},
    {"n": 4, "nombre": "Solución propuesta"},
    {"n": 5, "nombre": "Implantación"},
    {"n": 6, "nombre": "Conclusiones"},
]

ADQUISICION = "Adquisición de datos"

PARADAS: list[dict] = [
    {
        "id": "P1",
        "capitulo": 1,
        "apartado": "Motivación y objetivos",
        "fecha": "2026-08-14",
        "titulo": "La idea y el barrido de fuentes",
        "texto": (
            "De {candidatas} fuentes candidatas en València, {capturadas} "
            "publican en tiempo real y se capturan desde el primer día. "
            "Metrovalencia no publica posiciones y queda fuera."
        ),
        "remite": ["doc:03_fuentes_valencia_primer_barrido"],
        "cotejo": [],
    },
    {
        "id": "P2",
        "capitulo": 3,
        "apartado": "Análisis de riesgos",
        "fecha": "2026-08-15",
        "titulo": "Ninguna fuente guarda el pasado",
        "texto": (
            "Lo que no se captura, se pierde. Desde el {primer_sondeo} el colector "
            "guarda cada respuesta tal como llega, antes de parsearla: "
            "{payloads} payloads crudos."
        ),
        "remite": ["doc:01_viabilidad_fuentes_valencia"],
        "cotejo": [],
    },
    {
        "id": "P3",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "La EMT alterna UTC y hora local",
        "texto": (
            "En las primeras {horas} h de captura, la EMT cambia de convención "
            "horaria {alternancias} veces en {sondeos} sondeos. Con un desfase "
            "fijo, el {desplazadas} % de las posiciones quedaría dos horas "
            "desplazado, sin ningún error."
        ),
        "remite": ["trampa:002"],
        "cotejo": [
            {"cifra": "alternancias", "esperado": 342, "ficha": "bitácora 053"},
            {"cifra": "sondeos", "esperado": 1236, "ficha": "bitácora 053"},
            {
                "cifra": "desplazadas",
                "esperado": 20.2,
                "tolerancia": 0.0025,
                "ficha": "bitácora 053",
            },
        ],
    },
    {
        "id": "P4",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "El gid identifica al refresco, no al vehículo",
        "texto": (
            "Entre dos sondeos distintos no se repite ni un gid: {comun} en común "
            "en {pares} pares seguidos del {dia}. El gid numera la recarga de la "
            "tabla, no al autobús, así que la identidad del vehículo hay que "
            "reconstruirla."
        ),
        "remite": ["trampa:001"],
        "cotejo": [{"cifra": "comun", "esperado": 0, "ficha": "trampa 001"}],
    },
    {
        "id": "P5",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "La fuente falla sin avisar",
        "texto": (
            "Del {desde} al {hasta} (UTC), las capas del geoportal no entregan "
            "nada durante {horas} h, y Renfe, en el mismo colector, no tiene en "
            "ese tiempo ningún hueco de más de {renfe_min} min. Nada avisó. "
            "Además, la EMT "
            "deja de publicar casi toda la línea {linea}."
        ),
        "remite": ["bitacora:021", "bitacora:025"],
        "cotejo": [
            {
                "cifra": "horas",
                "esperado": 103.7,
                "tolerancia": 0.001,
                "ficha": "bitácora 021",
            },
        ],
    },
    {
        "id": "P6",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "El bloque a medio reinsertar",
        "texto": (
            "A veces la EMT sirve el sondeo a medio cargar: la misma tabla con "
            "{filas_a} filas y, segundos después, con {filas_b}. Como el crudo se "
            "guarda entero, curar se queda con la captura completa: "
            "{completados} sondeos recuperados en todo el corpus."
        ),
        "remite": ["bitacora:020", "trampa:011"],
        "cotejo": [{"cifra": "completados", "minimo": 1200, "ficha": "trampa 011"}],
    },
    {
        "id": "P7",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "En periodo lectivo la capa 192 despierta y la 188 sigue congelada",
        "texto": (
            "En periodo lectivo, la capa de estado pasa a una mediana de {tramos} "
            "tramos densos o congestionados por laborable, con forma de hora punta. "
            "La de intensidad repite los mismos {valores} valores todos los días: "
            "está congelada. El tráfico se lee de la capa de estado."
        ),
        "remite": ["bitacora:031", "bitacora:052"],
        # La 031 publicó 34 con el 18/09 a medias; con el día entero, 43 (052).
        "cotejo": [
            {"cifra": "tramos", "esperado": 43, "ficha": "bitácora 052"},
            {"cifra": "valores", "esperado": 243, "ficha": "bitácora 031"},
        ],
    },
    {
        "id": "P8",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "Kafka no hace falta",
        "texto": (
            "Las fuentes capturadas suman {payloads} payloads al día: "
            "{por_segundo} por segundo y {mb} MB sin comprimir. Un broker "
            "resuelve un problema que esta captura no tiene; el crudo en disco "
            "basta."
        ),
        "remite": ["bitacora:033"],
        "cotejo": [
            {
                "cifra": "payloads",
                "esperado": 6336,
                "tolerancia": 0.02,
                "ficha": "bitácora 033",
            },
            {
                "cifra": "mb",
                "esperado": 297,
                "tolerancia": 0.02,
                "ficha": "bitácora 033",
            },
        ],
    },
    {
        "id": "P9",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "La infraestructura también falla",
        "texto": (
            "En {dias} días de captura hay {cortes} cortes de la EMT de más de una "
            "hora, {horas} h en total, de las que {horas_fuente} son la caída de "
            "las capas del geoportal de septiembre. Se encontraron después, "
            "contando sondeos: el colector no avisa de lo que no recibe, ni de "
            "lo que recibe sin datos, como los errores del geoportal que "
            "tumbaron un día de la prueba."
        ),
        "remite": [
            "bitacora:035",
            "bitacora:044",
            "bitacora:051",
            "bitacora:054",
            "trampa:016",
            "trampa:018",
        ],
        "cotejo": [
            {
                "cifra": "horas_fuente",
                "esperado": 103.7,
                "tolerancia": 0.001,
                "ficha": "bitácora 021",
            },
        ],
    },
    {
        "id": "P10",
        "capitulo": 5,
        "apartado": "Resultados",
        "titulo": "La prueba pierde el día que parecía completo",
        "texto": (
            "Del {desde} al {hasta}, la captura guarda el {pct} % de los sondeos "
            "de la EMT que da su cadencia, y {utiles} de {dias} días de prueba no "
            "tienen ningún hueco de más de una hora. El {caidos}, el geoportal "
            "respondió con errores durante {minutos_caida} min; contando líneas del "
            "crudo, el día parecía completo. El criterio de día útil lo descarta."
        ),
        "remite": ["bitacora:050", "bitacora:057", "bitacora:059", "trampa:018"],
        # La 050 contó 17.119 líneas del crudo; sin los payloads sin filas, 17.109.
        "cotejo": [
            {"cifra": "sondeos_cotejo", "esperado": 17109, "ficha": "bitácora 059"},
            {"cifra": "utiles", "esperado": 12, "ficha": "bitácora 057"},
            {
                "cifra": "minutos_caida",
                "esperado": 225,
                "tolerancia": 0.01,
                "ficha": "trampa 018",
            },
        ],
    },
]

# tipo de ficha -> (carpeta, campo de la fecha, nombre que se enseña)
CARPETAS = {
    "bitacora": (RAIZ / "docs" / "bitacora", "fecha", "bitácora"),
    "trampa": (RAIZ / ".claude" / "trampas", "detectada", "trampa"),
    "doc": (RAIZ / "docs", None, "docs"),
}

# tipo de prueba -> claves que la página necesita
CLAVES = {
    "lista": {"elementos"},
    "pares": {"registros", "resalta"},
    "serie": {"x", "series", "sombras", "anotaciones"},
    "cifra": {"valor", "decimales", "etiqueta", "detalle"},
}


def es(x: float, dec: int | None = None) -> str:
    """Número en castellano: punto de miles y coma decimal."""
    if dec is None:
        dec = 0 if float(x).is_integer() else (3 if abs(x) < 1 else 1)
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def redactar(plantilla: str, valores: dict) -> str:
    cifras = {k: v if isinstance(v, str) else es(v) for k, v in valores.items()}
    return plantilla.format_map(cifras)


def ficha(ref: str) -> dict:
    tipo, clave = ref.split(":")
    carpeta, campo, nombre = CARPETAS[tipo]
    hallados = sorted(carpeta.glob(f"{clave}*.md"))
    if not hallados:
        raise FileNotFoundError(f"{ref}: no hay ficha en {carpeta}")
    texto = hallados[0].read_text(encoding="utf-8")
    if campo is None:
        titulo = re.search(r"^# (.+)$", texto, re.M).group(1)
        return {
            "ficha": f"{nombre}/{hallados[0].name}",
            "fecha": None,
            "titulo": titulo,
        }
    return {
        "ficha": f"{nombre} {clave}",
        "fecha": re.search(rf"^{campo}:\s*(\S+)", texto, re.M).group(1),
        "titulo": re.search(r"^titulo:\s*(.+)$", texto, re.M).group(1),
    }


def fecha_parada(p: dict) -> str:
    """La más temprana de sus fichas; P1 y P2 remiten a docs sin fecha y la traen."""
    fechas = [f["fecha"] for f in map(ficha, p["remite"]) if f["fecha"]]
    return min(fechas) if fechas else p["fecha"]


class CotejoError(ValueError):
    """Una cifra recalculada no cuadra con la que publicó su ficha."""


def cotejar(parada: str, valores: dict, cotejo: list[dict]) -> list[str]:
    informe, fallos = [], []
    for c in cotejo:
        v = valores[c["cifra"]]
        if "minimo" in c:
            ok, ref = v >= c["minimo"], f">= {c['minimo']}"
        else:
            tol = c.get("tolerancia", 0.0)
            ok = abs(v - c["esperado"]) <= tol * abs(c["esperado"])
            ref = f"{c['esperado']} ±{tol:.1%}"
        linea = f"{parada} {c['cifra']}: {v} frente a {ref} ({c['ficha']})"
        informe.append(("  ok    " if ok else "  FALLA ") + linea)
        if not ok:
            fallos.append(linea)
    if fallos:
        raise CotejoError("; ".join(fallos))
    return informe


def validar_prueba(prueba: dict) -> None:
    falta = CLAVES[prueba["tipo"]] - set(prueba)
    if falta:
        raise ValueError(f"prueba {prueba['tipo']} sin {sorted(falta)}")
    if prueba["tipo"] == "pares" and len(prueba["registros"]) != 2:
        raise ValueError("una prueba de pares lleva exactamente dos registros")
    if prueba["tipo"] == "serie":
        x0, x1 = prueba["x"][0], prueba["x"][-1]
        for s in prueba["series"]:
            if len(s["valores"]) != len(prueba["x"]):
                raise ValueError(f"serie {s['nombre']}: valores y días no casan")
        for marca in prueba["sombras"] + prueba["anotaciones"]:
            for f in (marca.get("desde"), marca.get("hasta"), marca.get("x")):
                if f is not None and not x0 <= f <= x1:
                    raise ValueError(f"{f} cae fuera de la serie ({x0} a {x1})")


def escribir_foto(foto: dict, destino: Path) -> int:
    """`window.DATOS = {...};`: un script, porque `fetch` no abre `file://`."""
    texto = (
        "window.DATOS = "
        + json.dumps(foto, ensure_ascii=False, default=lambda o: o.item())
        + ";\n"
    )
    n = len(texto.encode("utf-8"))
    if n > LIMITE_BYTES:
        raise ValueError(f"la foto pesa {n:,} bytes y el límite es {LIMITE_BYTES:,}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return n
