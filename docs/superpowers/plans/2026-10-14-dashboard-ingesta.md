# Dashboard de la defensa, fase 1 (ingesta) · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una página HTML estática que recorre, parada a parada, el camino del proyecto por la ingesta —de la idea a la captura completa—, con cifras recalculadas del dato y cotejadas con su ficha, y las figuras de la memoria sacadas de la misma foto.

**Architecture:** Un exportador en Python (paquete `project.analysis.dashboard_ingesta`, fuera de DVC) mide cada prueba sobre el crudo, el curado y metrics/curar.json, la coteja con la bitácora o la trampa que la publicó y escribe `window.DATOS` en `dashboard/datos/ingesta.js`. Una página con D3 y GSAP dentro del repo dibuja la línea con los capítulos de la ETSINF como estaciones y anima las diez paradas con una sola línea de tiempo.

**Tech Stack:** Python 3.12 con pandas, duckdb y matplotlib (ya instalados), pytest; D3 7.9.0 y GSAP 3.12.5 en `dashboard/vendor/`; Chrome sin cabeza para verificar la página.

**Spec:** docs/superpowers/specs/2026-10-14-dashboard-ingesta-design.md

## Global Constraints

- Ninguna plantilla `texto` de una parada contiene dígitos: toda cifra sale del dato por `redactar`.
- Cada cifra con ficha se coteja; si se sale de la tolerancia, el exportador se detiene y no escribe nada.
- La página abre como `file://` sin servidor ni red: datos en `window.DATOS`, `<script>` clásicos (ni `fetch` ni módulos ES), librerías en `dashboard/vendor/`, nada de CDN en tiempo de ejecución.
- D3 **7.9.0** y GSAP **3.12.5**, versión fijada y suma sha256 anotada.
- La foto pesa menos de **2 MB** (`LIMITE_BYTES = 2_000_000`).
- Lienzo fijo **1920×1080** escalado con bandas; fondo claro; un color de acento; sin logos ni marcas de la EMT; fuentes del sistema; todo en castellano.
- El exportador vive en `src/project/analysis/dashboard_ingesta/`: nada lo importa, no es stage de DVC, no lee `data/processed/`, etiquetas ni métricas del modelo (prueba del ADR-024).
- Rutas desde `settings` o `RAIZ` de `project.config`; nunca `os.getenv`.
- Tests sin red, con datos sintéticos de verdad conocida; cada guardia nueva lleva su mutante en `auditoria/catalogo.toml`.
- `uv run` para todo; `uv run ruff format . && uv run ruff check --fix .` antes de cada commit.
- La documentación de `docs/` no cita entre comillas invertidas rutas `.py/.json/.md/.toml/.txt` que aún no existan, ni nombres de función con paréntesis que no estén definidos en `src/`: lo comprueba `.claude/tests/test_memoria.py`.
- Commits con prefijo convencional en castellano y la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- El último día del crudo puede estar a medias (el colector sigue escribiendo): las series se dibujan hasta el día anterior → test `test_el_ultimo_dia_del_crudo_se_da_por_incompleto` (Task 2).
- La ventana de la primera captura cruza la medianoche UTC y vive en dos particiones `date=`: la alternancia debe leer las dos → el test de alternancia pone un sondeo en el día siguiente (Task 2).
- Una sombra o una anotación fuera del rango de su serie (p. ej. un incidente posterior al último día del crudo) se dibujaría en el vacío: `validar_prueba` la rechaza → `test_una_anotacion_fuera_de_la_serie_no_se_dibuja_en_el_vacio` (Task 1).
- `data/curated` o metrics/curar.json ausentes (p. ej. con `dvc repro curar` a medias): el exportador dice qué comando ejecutar → `test_sin_las_cuentas_de_curar_el_exportador_dice_que_ejecutar` (Task 4).
- Proyector 4:3 o ventana que no es 16:9: el lienzo se ve entero con bandas, sin recortar → captura a 1024×768 (Task 5, paso 5).

---

## Mapa de ficheros

| fichero | responsabilidad |
|---|---|
| src/project/analysis/dashboard_ingesta/__init__.py | paquete (vacío) |
| src/project/analysis/dashboard_ingesta/paradas.py | capítulos, las 10 paradas (texto, fichas, cotejo) y las guardias: `es`, `redactar`, `ficha`, `fecha_parada`, `cotejar`, `validar_prueba`, `escribir_foto` |
| src/project/analysis/dashboard_ingesta/extraer.py | mediciones sobre el crudo con lógica propia: `completitud`, `ultimo_dia_completo`, `alternancia`, `gid_por_sondeo`, `bloque_a_medias` |
| src/project/analysis/dashboard_ingesta/figuras.py | `figura_serie`: una prueba `serie` a PDF con matplotlib |
| src/project/analysis/dashboard_ingesta/foto.py | una función por parada, `construir`, `main` |
| src/project/analysis/dashboard_ingesta/__main__.py | `python -m` llama a `foto.main` |
| tests/test_dashboard.py | guardias de las cuatro piezas de Python |
| dashboard/index.html, dashboard/estilo.css, dashboard/escena.js | la página |
| dashboard/vendor/d3.min.js, dashboard/vendor/gsap.min.js, dashboard/vendor/VERSIONES.txt | librerías fijadas |
| dashboard/datos/ingesta.js, dashboard/figuras/*.pdf | salida del exportador, en git |

---

### Task 1: Paradas y guardias

**Files:**
- Create: src/project/analysis/dashboard_ingesta/__init__.py (vacío)
- Create: src/project/analysis/dashboard_ingesta/paradas.py
- Create: tests/test_dashboard.py
- Modify: auditoria/catalogo.toml (mutantes 145, 146, 147 y 151 al final)

**Interfaces:**
- Consumes: `RAIZ` de `project.config`.
- Produces:
  - `CAPITULOS: list[dict]` con `{"n": int, "nombre": str}`.
  - `PARADAS: list[dict]`; cada una con `id, capitulo, apartado, titulo, texto, remite: list[str], cotejo: list[dict]` y, P1 y P2, `fecha`.
  - `es(x: float, dec: int | None = None) -> str`
  - `redactar(plantilla: str, valores: dict) -> str` (KeyError si falta un hueco)
  - `ficha(ref: str) -> dict` con `ficha, fecha, titulo` (`ref` = `"bitacora:021"`, `"trampa:002"` o `"doc:03_fuentes_valencia_primer_barrido"`)
  - `fecha_parada(p: dict) -> str` (`YYYY-MM-DD`)
  - `class CotejoError(ValueError)`; `cotejar(parada: str, valores: dict, cotejo: list[dict]) -> list[str]`
  - `validar_prueba(prueba: dict) -> None` (ValueError)
  - `escribir_foto(foto: dict, destino: Path) -> int` (bytes escritos; ValueError si pasa de `LIMITE_BYTES`)

- [ ] **Step 1: Escribir los tests que fallan**

Crea tests/test_dashboard.py:

```python
"""Guardias del dashboard de la defensa, fase 1 (ingesta).

La página enseña cifras al tribunal. Lo que se guarda aquí es que salgan del
dato y no de una plantilla, que cuadren con la ficha que las publicó y que los
extractores midan lo que dicen sobre un crudo de verdad conocida.
"""

from __future__ import annotations

import copy
import json
import re

import pytest

from project.analysis.dashboard_ingesta.paradas import (
    PARADAS,
    CotejoError,
    cotejar,
    escribir_foto,
    fecha_parada,
    redactar,
    validar_prueba,
)

SERIE = {
    "tipo": "serie",
    "x": ["2026-09-01", "2026-09-02", "2026-09-03"],
    "series": [{"nombre": "s", "valores": [1.0, None, 3.0]}],
    "sombras": [{"desde": "2026-09-02", "hasta": "2026-09-02", "etiqueta": "hueco"}],
    "anotaciones": [{"x": "2026-09-03", "texto": "algo"}],
}


def test_las_plantillas_no_llevan_cifras_escritas_a_mano():
    """Un número en la plantilla no sale del dato: es una cifra copiada a mano."""
    con_digitos = [p["id"] for p in PARADAS if re.search(r"\d", p["texto"])]
    assert not con_digitos, con_digitos


def test_un_hueco_sin_cifra_no_se_publica_vacio():
    assert redactar("{a} de {b}", {"a": 3, "b": 1234}) == "3 de 1.234"
    with pytest.raises(KeyError):
        redactar("{a} de {b}", {"a": 3})


def test_las_fechas_del_camino_no_retroceden():
    """El marcador avanza en tiempo de desarrollo: ninguna parada antes que la previa."""
    fechas = [fecha_parada(p) for p in PARADAS]
    assert fechas == sorted(fechas), list(zip([p["id"] for p in PARADAS], fechas))


def test_el_cotejo_para_si_la_cifra_no_cuadra_con_su_ficha():
    exacto = [{"cifra": "n", "esperado": 100, "ficha": "bitácora 999"}]
    tolerado = [{"cifra": "n", "esperado": 100, "tolerancia": 0.02, "ficha": "b"}]
    minimo = [{"cifra": "n", "minimo": 100, "ficha": "trampa 999"}]
    assert cotejar("P0", {"n": 100}, exacto)
    assert cotejar("P0", {"n": 101.5}, tolerado)
    assert cotejar("P0", {"n": 150}, minimo)
    for cotejo, valor in [(exacto, 101), (tolerado, 103), (minimo, 99)]:
        with pytest.raises(CotejoError):
            cotejar("P0", {"n": valor}, cotejo)


def test_la_prueba_cumple_el_contrato_de_la_pagina():
    validar_prueba(SERIE)
    validar_prueba(
        {"tipo": "cifra", "valor": 1.5, "decimales": 1, "etiqueta": "e", "detalle": []}
    )
    with pytest.raises(ValueError):
        validar_prueba({"tipo": "cifra", "valor": 1.5, "etiqueta": "e", "detalle": []})
    with pytest.raises(ValueError):
        validar_prueba({"tipo": "pares", "registros": [{}], "resalta": "k"})
    corta = copy.deepcopy(SERIE)
    corta["series"][0]["valores"] = [1.0]
    with pytest.raises(ValueError):
        validar_prueba(corta)


def test_una_anotacion_fuera_de_la_serie_no_se_dibuja_en_el_vacio():
    fuera = copy.deepcopy(SERIE)
    fuera["anotaciones"] = [{"x": "2026-10-06", "texto": "fuera"}]
    with pytest.raises(ValueError, match="fuera de la serie"):
        validar_prueba(fuera)


def test_la_foto_es_un_script_y_no_pasa_del_limite(tmp_path):
    destino = tmp_path / "datos" / "ingesta.js"
    escribir_foto({"paradas": [], "n": 1}, destino)
    texto = destino.read_text(encoding="utf-8")
    assert texto.startswith("window.DATOS = ") and texto.rstrip().endswith(";")
    cuerpo = texto.removeprefix("window.DATOS = ").rstrip().removesuffix(";")
    assert json.loads(cuerpo) == {"paradas": [], "n": 1}
    with pytest.raises(ValueError, match="límite"):
        escribir_foto({"relleno": "x" * 2_100_000}, destino)
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: ERROR en la colección, `ModuleNotFoundError: No module named 'project.analysis.dashboard_ingesta'`.

- [ ] **Step 3: Implementar**

Crea src/project/analysis/dashboard_ingesta/__init__.py vacío y src/project/analysis/dashboard_ingesta/paradas.py:

```python
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
            {"cifra": "alternancias", "esperado": 338, "tolerancia": 0.02,
             "ficha": "trampa 002"},
            {"cifra": "sondeos", "esperado": 1224, "tolerancia": 0.02,
             "ficha": "trampa 002"},
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
            {"cifra": "horas", "esperado": 103.7, "tolerancia": 0.001,
             "ficha": "bitácora 021"},
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
            "tramos congestionados por laborable, con forma de hora punta. La de "
            "intensidad repite los mismos {valores} valores todos los días: está "
            "congelada. El tráfico se lee de la capa de estado."
        ),
        "remite": ["bitacora:031"],
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
            {"cifra": "payloads", "esperado": 6336, "tolerancia": 0.02,
             "ficha": "bitácora 033"},
            {"cifra": "mb", "esperado": 297, "tolerancia": 0.02,
             "ficha": "bitácora 033"},
        ],
    },
    {
        "id": "P9",
        "capitulo": 4,
        "apartado": ADQUISICION,
        "titulo": "La infraestructura también falla",
        "texto": (
            "En {dias} días de captura hay {cortes} cortes de la EMT de más de una "
            "hora, {horas} h en total. Se encontraron después, contando sondeos: "
            "el colector no avisa de lo que no recibe."
        ),
        "remite": ["bitacora:035", "bitacora:044", "bitacora:051", "trampa:016"],
        "cotejo": [],
    },
    {
        "id": "P10",
        "capitulo": 5,
        "apartado": "Resultados",
        "titulo": "La captura de la prueba, completa",
        "texto": (
            "Del {desde} al {hasta}, la captura guarda el {pct} % de los sondeos "
            "de la EMT que da su cadencia, y {utiles} de {dias} días de prueba no "
            "tienen ningún hueco de más de una hora."
        ),
        "remite": ["bitacora:050"],
        "cotejo": [
            {"cifra": "sondeos_cotejo", "esperado": 17119, "ficha": "bitácora 050"},
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
        return {"ficha": f"{nombre}/{hallados[0].name}", "fecha": None, "titulo": titulo}
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
```

- [ ] **Step 4: Ver que pasan**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Mutantes de las guardias**

Añade al final de auditoria/catalogo.toml:

```toml

[[mutante]]
id = "145"
nombre = "redactar deja vacío el hueco que no tiene cifra"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/paradas.py"
buscar = '''    return plantilla.format_map(cifras)'''
reemplazar = '''    return re.sub(r"\{(\w+)\}", lambda m: cifras.get(m.group(1), ""), plantilla)'''
detector = ["tests/test_dashboard.py::test_un_hueco_sin_cifra_no_se_publica_vacio"]
sondas = []

[[mutante]]
id = "146"
nombre = "el cotejo da por buena cualquier cifra"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/paradas.py"
buscar = '''    if fallos:
        raise CotejoError("; ".join(fallos))'''
reemplazar = '''    if False:
        raise CotejoError("; ".join(fallos))'''
detector = ["tests/test_dashboard.py::test_el_cotejo_para_si_la_cifra_no_cuadra_con_su_ficha"]
sondas = []

[[mutante]]
id = "147"
nombre = "la prueba llega a la página sin las claves que necesita"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/paradas.py"
buscar = '''    falta = CLAVES[prueba["tipo"]] - set(prueba)'''
reemplazar = '''    falta = set()'''
detector = ["tests/test_dashboard.py::test_la_prueba_cumple_el_contrato_de_la_pagina"]
sondas = []

[[mutante]]
id = "151"
nombre = "una anotación fuera del rango de la serie se acepta"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/paradas.py"
buscar = '''                if f is not None and not x0 <= f <= x1:'''
reemplazar = '''                if False:'''
detector = ["tests/test_dashboard.py::test_una_anotacion_fuera_de_la_serie_no_se_dibuja_en_el_vacio"]
sondas = []
```

Comprueba a mano que cada mutante pone su test en rojo (`mutar.py` exige commit; se corre en la Task 6): para cada uno, copia de seguridad del fichero, aplica el reemplazo con un script de Python de una línea (`pathlib.Path(f).write_text(t.replace(buscar, reemplazar, 1))`), corre su detector, restaura la copia.

Expected: cada detector FALLA con el mutante y PASA tras restaurar.

- [ ] **Step 6: Formato y commit**

```bash
uv run ruff format src/project/analysis/dashboard_ingesta tests/test_dashboard.py
uv run ruff check src/project/analysis/dashboard_ingesta
grep -c 'return plantilla.format_map(cifras)' src/project/analysis/dashboard_ingesta/paradas.py   # 1
grep -c 'falta = CLAVES\[prueba\["tipo"\]\] - set(prueba)' src/project/analysis/dashboard_ingesta/paradas.py   # 1
uv run pytest tests/test_dashboard.py -q
git add src/project/analysis/dashboard_ingesta tests/test_dashboard.py auditoria/catalogo.toml
git commit -m "feat(dashboard): paradas de la ingesta con cifras redactadas, cotejadas y validadas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Extractores sobre el crudo

**Files:**
- Create: src/project/analysis/dashboard_ingesta/extraer.py
- Modify: tests/test_dashboard.py (import y cinco tests al final)
- Modify: auditoria/catalogo.toml (mutantes 148, 149 y 150)

**Interfaces:**
- Consumes: `instantes(raw, fuente, desde, hasta)` y `huecos(ts, umbral)` de `project.analysis.medir_completitud`; `parse_emt(payload, ts)` y `read_raw(path)` de `project.ingest.sources`; fixture `fix` de tests/conftest.py; `sources.append_raw(root, source, payload, ts)` escribe en `root/raw/source=X/date=YYYY-MM-DD/payloads.ndjson.gz`.
- Produces:
  - `completitud(raw: Path, fuente: str, desde: str, hasta: str) -> tuple[pd.Series, list[tuple[pd.Timestamp, pd.Timestamp]]]` — índice `YYYY-MM-DD`, días sin crudo a 0; huecos de más de una hora.
  - `ultimo_dia_completo(raw: Path) -> str`
  - `alternancia(raw: Path, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict` con `sondeos, alternancias, desplazadas, par` (dos registros `{"titulo", "campos"}`).
  - `gid_por_sondeo(raw: Path, dia: str) -> dict` con `pares, con_comun, par`.
  - `bloque_a_medias(raw: Path, dias: list[str]) -> dict` con `filas: tuple[int, int], par`.

- [ ] **Step 1: Escribir los tests que fallan**

Añade a los imports de tests/test_dashboard.py (ruff format los ordena):

```python
import pandas as pd

from project.analysis.dashboard_ingesta import extraer
from project.ingest import sources
```

y al final del fichero:

```python
T = pd.Timestamp("2026-08-15T23:50:00Z")


def _emt(gids: range, ts: pd.Timestamp, local: bool) -> dict:
    """Un payload de la EMT con la forma real: la `fecha` de cada bus va 25 s por
    detrás de la captura, en UTC o en hora de Madrid leída como si fuera UTC."""
    fecha = ts - pd.Timedelta(seconds=25)
    if local:
        fecha = fecha.tz_convert("Europe/Madrid").tz_localize(None).tz_localize("UTC")
    ms = int(fecha.timestamp() * 1000)
    return {
        "features": [
            {
                "attributes": {"gid": g, "linea": "70", "trayecto": "A - B", "fecha": ms},
                "geometry": {"x": -0.35, "y": 39.49},
            }
            for g in gids
        ]
    }


def _capturar(root, capturas, inicio=T):
    for gids, segundos, local in capturas:
        ts = inicio + pd.Timedelta(seconds=segundos)
        sources.append_raw(root, "emt_buses", _emt(gids, ts, local), ts)


def test_la_alternancia_se_cuenta_por_sondeo_y_cruza_el_cambio_de_dia(tmp_path):
    """Trampa 002. La EMT sirve a veces el mismo sondeo dos veces con la convención
    contraria, y esa repetición no es una alternancia. La ventana cruza la
    medianoche UTC, como la de la primera captura."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(100, 110), 10, True),  # el mismo sondeo, otra convención
            (range(200, 210), 30, False),
            (range(300, 310), 900, True),  # 00:05 UTC del día siguiente
        ],
    )

    a = extraer.alternancia(
        tmp_path / "raw", T - pd.Timedelta(minutes=1), T + pd.Timedelta(hours=1)
    )

    assert a["sondeos"] == 3 and a["alternancias"] == 1, a
    antes, despues = a["par"]
    assert antes["campos"]["diferencia"] == "+0 h"
    assert despues["campos"]["diferencia"] == "+2 h"
    assert despues["campos"]["convención"] == "hora local"


def test_dos_sondeos_distintos_no_comparten_gid_y_la_repeticion_no_cuenta(tmp_path):
    """Trampa 001. El bloque a medias y el completo son el MISMO sondeo y sí
    comparten gid (trampa 011): cada sondeo se compara con el anterior distinto."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(200, 204), 30, False),  # a medias
            (range(200, 210), 40, False),  # el mismo, completo
            (range(300, 310), 60, False),
        ],
        inicio=pd.Timestamp("2026-08-16T08:00:00Z"),
    )

    g = extraer.gid_por_sondeo(tmp_path / "raw", "2026-08-16")

    assert g["pares"] == 2 and g["con_comun"] == 0, g
    assert g["par"][1]["campos"]["gid en común con el anterior"] == "0"


def test_el_bloque_a_medias_se_encuentra_y_la_copia_identica_no(tmp_path):
    """Trampa 011: la primera captura trae el prefijo de gid del bloque."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(100, 110), 5, False),  # repetición idéntica: no es a medias
            (range(200, 205), 30, False),
            (range(200, 220), 40, False),
        ],
        inicio=pd.Timestamp("2026-08-16T08:00:00Z"),
    )

    b = extraer.bloque_a_medias(tmp_path / "raw", ["2026-08-15", "2026-08-16"])

    assert b["filas"] == (5, 20), b
    assert [r["campos"]["sondeo (gid mínimo)"] for r in b["par"]] == ["200", "200"]


def test_un_dia_sin_crudo_es_un_cero_y_no_desaparece(tmp_path, fix):
    """Bitácora 021: del 10 al 14/09 no hay ni directorio. Si el día falta de la
    serie en vez de valer 0, el hueco no se ve."""
    for ts in ["2026-09-01T10:00Z", "2026-09-01T10:05Z", "2026-09-04T09:00Z"]:
        sources.append_raw(
            tmp_path, "trafico_estado", fix["trafico_estado"], pd.Timestamp(ts)
        )

    n, huecos = extraer.completitud(
        tmp_path / "raw", "trafico_estado", "2026-09-01", "2026-09-04"
    )

    assert list(n.index) == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    assert list(n) == [2, 0, 0, 1]
    assert huecos == [
        (pd.Timestamp("2026-09-01T10:05Z"), pd.Timestamp("2026-09-04T09:00Z"))
    ]


def test_el_ultimo_dia_del_crudo_se_da_por_incompleto(tmp_path):
    """El colector puede estar escribiendo el último día: dibujarlo pinta una
    caída que no existe."""
    for d in ["2026-10-10", "2026-10-11", "2026-10-12"]:
        (tmp_path / "source=emt_buses" / f"date={d}").mkdir(parents=True)
    assert extraer.ultimo_dia_completo(tmp_path) == "2026-10-11"
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: ERROR en la colección, `ImportError: cannot import name 'extraer'`.

- [ ] **Step 3: Implementar**

Crea src/project/analysis/dashboard_ingesta/extraer.py:

```python
"""Las pruebas del camino de la ingesta, medidas sobre el crudo. Solo lectura.

Cada función mide algo que una ficha ya contó en prosa, para que la página lo
enseñe con el dato delante y el exportador lo coteje con la ficha. Nada del
pipeline importa de aquí.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from project.analysis.medir_completitud import huecos, instantes
from project.ingest.sources import parse_emt, read_raw

UNA_HORA = pd.Timedelta(hours=1)
CONVENCION = {"LOCAL_NAIVE": "hora local", "YA_EN_UTC": "UTC"}


def _crudo_emt(raw: Path, dia: str) -> Path:
    return raw / "source=emt_buses" / f"date={dia}" / "payloads.ndjson.gz"


def completitud(
    raw: Path, fuente: str, desde: str, hasta: str
) -> tuple[pd.Series, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """Sondeos por día UTC de `desde` a `hasta` y huecos de más de una hora.

    Un día sin directorio es un día sin captura, no un día que no existe: vale 0.
    Si desapareciera de la serie, el hueco del 10-14/09 no se vería (bitácora 021).
    """
    ts = instantes(raw, fuente, desde, hasta)
    dias = pd.date_range(desde, hasta, freq="D").strftime("%Y-%m-%d")
    por_dia = pd.Series(Counter(f"{t:%Y-%m-%d}" for t in ts), dtype="int64")
    return por_dia.reindex(dias, fill_value=0), huecos(ts, UNA_HORA)


def ultimo_dia_completo(raw: Path) -> str:
    """El día anterior al último del crudo de la EMT.

    El colector puede estar escribiendo el último: dibujarlo pinta una caída que
    no existe.
    """
    # ponytail: si la copia acabó justo a medianoche se pierde un día entero de
    # la serie; basta con traer el día siguiente antes de generar la foto.
    dias = sorted(
        p.name.removeprefix("date=") for p in (raw / "source=emt_buses").glob("date=*")
    )
    return str((pd.Timestamp(dias[-1]) - pd.Timedelta(days=1)).date())


def alternancia(raw: Path, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    """Convención horaria de cada sondeo de la EMT entre `desde` y `hasta` (trampa 002).

    Se cuenta por sondeo, no por captura: la EMT sirve a veces el mismo sondeo
    dos veces, con la otra convención, y esa repetición no es una alternancia.
    Los sondeos DUDOSA no entran en la cuenta.
    """
    vistos: set[int] = set()
    sondeos: list[dict] = []
    for dia in pd.date_range(desde.normalize(), hasta.normalize(), freq="D"):
        fichero = _crudo_emt(raw, f"{dia:%Y-%m-%d}")
        if not fichero.exists():
            continue
        for ts, payload in read_raw(fichero):
            if not desde <= ts <= hasta:
                continue
            df = parse_emt(payload, ts)
            if df.empty:
                continue
            sid = int(df["snapshot_id"].iloc[0])
            if sid in vistos:
                continue
            vistos.add(sid)
            fechas = [f["attributes"]["fecha"] for f in payload["features"]]
            sondeos.append(
                {
                    "ts": ts,
                    "conv": df["tz_convencion"].iloc[0],
                    "filas": len(df),
                    "fecha": pd.to_datetime(max(fechas), unit="ms", utc=True),
                }
            )
    s = [v for v in sondeos if v["conv"] in CONVENCION]
    cambios = [i for i in range(1, len(s)) if s[i]["conv"] != s[i - 1]["conv"]]
    filas: Counter = Counter()
    for v in s:
        filas[v["conv"]] += v["filas"]
    total = sum(filas.values())
    return {
        "sondeos": len(sondeos),
        "alternancias": len(cambios),
        "desplazadas": 100 * min(filas.values()) / total if len(filas) == 2 else 0.0,
        "par": (
            [_convencion(s[cambios[0] - 1]), _convencion(s[cambios[0]])]
            if cambios
            else []
        ),
    }


def _convencion(v: dict) -> dict:
    horas = round((v["fecha"] - v["ts"]) / UNA_HORA)
    return {
        "titulo": f"Sondeo de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "capturado (UTC)": f"{v['ts']:%H:%M:%S}",
            "fecha publicada, leída como UTC": f"{v['fecha']:%H:%M:%S}",
            "diferencia": f"{horas:+d} h",
            "convención": CONVENCION[v["conv"]],
        },
    }


def gid_por_sondeo(raw: Path, dia: str) -> dict:
    """¿Comparten `gid` dos sondeos distintos seguidos? (trampa 001).

    Dos capturas del mismo sondeo sí lo comparten —el bloque a medias y el
    completo, trampa 011—, así que cada sondeo se compara con el anterior
    DISTINTO, el de otro gid mínimo.
    """
    previo, primero = None, None
    pares = comun = 0
    for ts, payload in read_raw(_crudo_emt(raw, dia)):
        filas = [f["attributes"] for f in payload.get("features") or []]
        if not filas:
            continue
        actual = {"ts": ts, "gid": {a["gid"] for a in filas}, "linea": filas[0]["linea"]}
        if previo is not None and min(actual["gid"]) != min(previo["gid"]):
            pares += 1
            comun += bool(actual["gid"] & previo["gid"])
            primero = primero or (previo, actual)
        previo = actual
    if primero is None:
        raise ValueError(f"el {dia} no tiene dos sondeos distintos de la EMT")
    a, b = primero
    return {"pares": pares, "con_comun": comun, "par": [_gid(a, None), _gid(b, a)]}


def _gid(v: dict, anterior: dict | None) -> dict:
    en_comun = "—" if anterior is None else str(len(v["gid"] & anterior["gid"]))
    return {
        "titulo": f"Sondeo de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "buses": str(len(v["gid"])),
            "gid": f"{min(v['gid'])} … {max(v['gid'])}",
            "primer bus": f"línea {v['linea']}",
            "gid en común con el anterior": en_comun,
        },
    }


def bloque_a_medias(raw: Path, dias: list[str]) -> dict:
    """La primera captura a medio reinsertar y su repetición completa (trampa 011).

    Mismo sondeo —mismo gid mínimo— y los gid de la primera son el prefijo de los
    de la segunda: la tabla se leyó a mitad de recarga.
    """
    for dia in dias:
        fichero = _crudo_emt(raw, dia)
        if not fichero.exists():
            continue
        previo = None
        for ts, payload in read_raw(fichero):
            gids = sorted(f["attributes"]["gid"] for f in payload.get("features") or [])
            if not gids:
                continue
            n = len(previo["gid"]) if previo else 0
            if previo and len(gids) > n and gids[:n] == previo["gid"]:
                actual = {"ts": ts, "gid": gids}
                return {"filas": (n, len(gids)), "par": [_bloque(previo), _bloque(actual)]}
            previo = {"ts": ts, "gid": gids}
    raise ValueError(f"ningún bloque a medias entre el {dias[0]} y el {dias[-1]}")


def _bloque(v: dict) -> dict:
    return {
        "titulo": f"Captura de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "sondeo (gid mínimo)": str(v["gid"][0]),
            "filas": str(len(v["gid"])),
            "gid": f"{v['gid'][0]} … {v['gid'][-1]}",
        },
    }
```

- [ ] **Step 4: Ver que pasan**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: `12 passed`.

- [ ] **Step 5: Mutantes**

Añade al final de auditoria/catalogo.toml:

```toml

[[mutante]]
id = "148"
nombre = "la alternancia cuenta capturas, no sondeos"
capa = "dashboard"
# La repetición de un sondeo con la convención contraria pasaría por alternancia.
fichero = "src/project/analysis/dashboard_ingesta/extraer.py"
buscar = '''            if sid in vistos:
                continue'''
reemplazar = '''            if False:
                continue'''
detector = ["tests/test_dashboard.py::test_la_alternancia_se_cuenta_por_sondeo_y_cruza_el_cambio_de_dia"]
sondas = []

[[mutante]]
id = "149"
nombre = "el gid se compara entre capturas seguidas y no entre sondeos distintos"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/extraer.py"
buscar = '''        if previo is not None and min(actual["gid"]) != min(previo["gid"]):'''
reemplazar = '''        if previo is not None and actual["gid"] != previo["gid"]:'''
detector = ["tests/test_dashboard.py::test_dos_sondeos_distintos_no_comparten_gid_y_la_repeticion_no_cuenta"]
sondas = []

[[mutante]]
id = "150"
nombre = "un día sin crudo desaparece de la serie en vez de valer 0"
capa = "dashboard"
fichero = "src/project/analysis/dashboard_ingesta/extraer.py"
buscar = '''    return por_dia.reindex(dias, fill_value=0), huecos(ts, UNA_HORA)'''
reemplazar = '''    return por_dia, huecos(ts, UNA_HORA)'''
detector = ["tests/test_dashboard.py::test_un_dia_sin_crudo_es_un_cero_y_no_desaparece"]
sondas = []
```

Comprueba a mano cada uno como en la Task 1, paso 5.
Expected: cada detector FALLA con su mutante y PASA tras restaurar.

- [ ] **Step 6: Formato y commit**

```bash
uv run ruff format src/project/analysis/dashboard_ingesta tests/test_dashboard.py
uv run ruff check src/project/analysis/dashboard_ingesta tests/test_dashboard.py
grep -c 'if previo is not None and min(actual\["gid"\]) != min(previo\["gid"\]):' src/project/analysis/dashboard_ingesta/extraer.py   # 1
grep -c 'return por_dia.reindex(dias, fill_value=0), huecos(ts, UNA_HORA)' src/project/analysis/dashboard_ingesta/extraer.py   # 1
uv run pytest tests/test_dashboard.py -q
git add src/project/analysis/dashboard_ingesta/extraer.py tests/test_dashboard.py auditoria/catalogo.toml
git commit -m "feat(dashboard): extractores de alternancia, gid, bloque a medias y completitud sobre el crudo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Figuras de la memoria

**Files:**
- Create: src/project/analysis/dashboard_ingesta/figuras.py
- Modify: tests/test_dashboard.py (import y un test)
- Modify: .gitattributes (`*.pdf binary`)

**Interfaces:**
- Consumes: una prueba `serie` como la que valida `validar_prueba`.
- Produces: `figura_serie(prueba: dict, titulo: str, destino: Path) -> None`.

- [ ] **Step 1: Test que falla**

En tests/test_dashboard.py cambia el import a `from project.analysis.dashboard_ingesta import extraer, figuras` y añade al final:

```python
def test_la_figura_de_una_serie_es_un_pdf(tmp_path):
    destino = tmp_path / "figuras" / "P5.pdf"
    figuras.figura_serie(SERIE, "Una serie", destino)
    assert destino.read_bytes()[:5] == b"%PDF-"
```

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: ERROR, `ImportError: cannot import name 'figuras'`.

- [ ] **Step 2: Implementar**

Crea src/project/analysis/dashboard_ingesta/figuras.py:

```python
"""Las paradas de tipo `serie`, en PDF para la memoria, de la misma foto que la página.

Se usa `Figure` y no `pyplot`: sin estado global ni backend de ventanas.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

ACENTO, SOMBRA = "#1f5fa8", "#d9822b"


def figura_serie(prueba: dict, titulo: str, destino: Path) -> None:
    x = pd.to_datetime(prueba["x"])
    n = len(prueba["series"])
    fig = Figure(figsize=(8, 1.6 * n + 0.9))
    ejes = fig.subplots(n, 1, sharex=True, squeeze=False)[:, 0]
    for ax, s in zip(ejes, prueba["series"]):
        valores = [float("nan") if v is None else v for v in s["valores"]]
        ax.plot(x, valores, color=ACENTO, lw=1.4)
        ax.set_ylabel(s["nombre"], fontsize=8)
        ax.set_ylim(bottom=0)  # como en la página: sin eje truncado que exagere
        for sb in prueba["sombras"]:
            fin = pd.Timestamp(sb["hasta"]) + pd.Timedelta(days=1)
            ax.axvspan(pd.Timestamp(sb["desde"]), fin, color=SOMBRA, alpha=0.18, lw=0)
        for a in prueba["anotaciones"]:
            ax.axvline(pd.Timestamp(a["x"]), color="0.4", lw=0.8, ls="--")
        ax.spines[["top", "right"]].set_visible(False)
    for i, a in enumerate(prueba["anotaciones"]):
        ejes[0].annotate(
            a["texto"],
            (pd.Timestamp(a["x"]), 1),
            xycoords=("data", "axes fraction"),
            xytext=(3, 4 + 10 * (i % 2)),
            textcoords="offset points",
            fontsize=7,
        )
    ejes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.suptitle(titulo, fontsize=11)
    fig.tight_layout()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino)
```

Añade a .gitattributes, en el bloque de binarios, la línea:

```
*.pdf       binary
```

- [ ] **Step 3: Ver que pasa**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: `13 passed`.

- [ ] **Step 4: Commit**

```bash
uv run ruff format src/project/analysis/dashboard_ingesta tests/test_dashboard.py
uv run ruff check src/project/analysis/dashboard_ingesta tests/test_dashboard.py
git add src/project/analysis/dashboard_ingesta/figuras.py tests/test_dashboard.py .gitattributes
git commit -m "feat(dashboard): figuras de la memoria desde la misma prueba que la página" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: La foto de datos

**Files:**
- Create: src/project/analysis/dashboard_ingesta/foto.py
- Create: src/project/analysis/dashboard_ingesta/__main__.py
- Modify: tests/test_dashboard.py (un test)
- Generated: dashboard/datos/ingesta.js, dashboard/figuras/P5.pdf, P7.pdf, P9.pdf, P10.pdf

**Interfaces:**
- Consumes: todo lo de las Tasks 1-3; `medir_volumen.medir(dias=None) -> DataFrame[fuente, dia, payloads, mb, max_kb]`; `medir_fuentes.lectivo() -> {"estado": DataFrame[dia, dow, tramos_congestion, ...], "intensidad": DataFrame[dia, valores_distintos, ...]}`; `medir_fuentes.sql(consulta, f="emt_buses")`; metrics/curar.json (`{fuente: {payloads, dias, filas, errores, duplicados, completados, estado}}`).
- Produces: `leer_curar(ruta: Path) -> dict`, `construir() -> dict` (`{"origen", "capitulos", "paradas"}`), `main() -> None`. Cada parada de la foto: `id, capitulo, apartado, fecha, titulo, texto, prueba, remite: [{"ficha", "fecha", "titulo"}], duracion_s`.

- [ ] **Step 0: La bitácora 052 tiene que existir**

El cotejo de P7 remite a la 052, la corrección de la mediana lectiva de la 031 (34 medido con el 18/09 a medias; 43 con el día entero). Comprueba que `docs/bitacora/` tiene una entrada 052 que lo diga. Si no la tiene, para y pide al usuario que la fiche con `/bitacora`: no la escribas tú.

- [ ] **Step 1: Comprobar que `curar` terminó y firmarlo**

`dvc repro curar` se lanzó el 14/10 en segundo plano.

```bash
uv run dvc status curar          # Expected: "Data and pipelines are up to date." para curar
ls metrics/curar.json data/curated
git status --short               # Expected: dvc.lock y metrics/curar.json modificados/nuevos
```

Si `curar` sigue corriendo, para aquí y espera: el exportador necesita `data/curated` entero. Cuando esté:

```bash
cat metrics/curar.json           # una entrada por fuente, "estado": "reescrito"
git add dvc.lock metrics/curar.json
git commit -m "chore(dvc): curar con el crudo hasta el 12/10 y sus cuentas en metrics/curar.json" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Test que falla**

Añade al final de tests/test_dashboard.py:

```python
def test_sin_las_cuentas_de_curar_el_exportador_dice_que_ejecutar(tmp_path):
    from project.analysis.dashboard_ingesta.foto import leer_curar

    with pytest.raises(FileNotFoundError, match="dvc repro curar"):
        leer_curar(tmp_path / "curar.json")
```

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: 1 failed, `ModuleNotFoundError: No module named 'project.analysis.dashboard_ingesta.foto'`.

- [ ] **Step 3: Implementar**

Crea src/project/analysis/dashboard_ingesta/__main__.py:

```python
from project.analysis.dashboard_ingesta.foto import main

main()
```

Crea src/project/analysis/dashboard_ingesta/foto.py:

```python
"""La foto de datos del dashboard de la defensa, fase 1 (ingesta).

    uv run python -m project.analysis.dashboard_ingesta

Escribe dashboard/datos/ingesta.js (`window.DATOS = {...}`: la página abre como
file://, sin servidor ni red) y las figuras de la memoria en dashboard/figuras/.
Cada cifra sale del dato y se coteja con la ficha que la publicó; si una no
cuadra, no se escribe nada.

No lee etiquetas, data/processed/ ni métricas del modelo: la prueba del ADR-024
no se mira desde aquí. Del 07-19/10 solo cuenta sondeos, como la bitácora 050.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from project.analysis import medir_fuentes, medir_volumen
from project.analysis.dashboard_ingesta import extraer, figuras
from project.analysis.dashboard_ingesta.paradas import (
    CAPITULOS,
    PARADAS,
    cotejar,
    es,
    escribir_foto,
    fecha_parada,
    ficha,
    redactar,
    validar_prueba,
)
from project.analysis.medir_completitud import instantes
from project.config import RAIZ, settings
from project.ingest.sources import SOURCES, read_raw

DESTINO = RAIZ / "dashboard"
INICIO = "2026-08-15"
# La primera captura de docs/05: 15/08 22:15 -> 16/08 08:55, hora local.
PRIMERA_CAPTURA = (
    pd.Timestamp("2026-08-15T20:15Z"),
    pd.Timestamp("2026-08-16T06:55Z"),
)
DIA_GID = "2026-08-16"  # el primer día entero de captura
CAPAS_CAIDAS = ("2026-09-01", "2026-09-20")  # alrededor del hueco de la bitácora 021
VOLUMEN = ("2026-08-15", "2026-09-18")  # las jornadas de la bitácora 033
LECTIVO = ("2026-09-08", "2026-09-18")  # el periodo lectivo medido en la bitácora 031
PRUEBA = ("2026-10-07", "2026-10-19")  # ADR-024
COTEJO_PRUEBA = ("2026-10-07", "2026-10-12")  # lo que contó la bitácora 050
INCIDENTES = [
    {"x": "2026-08-18", "texto": "la captura pasa del portátil a la Pi (035)"},
    {"x": "2026-09-10", "texto": "capas del geoportal caídas (021)"},
    {"x": "2026-10-05", "texto": "falla el disco de la Pi (044)"},
    {"x": "2026-10-06", "texto": "la Pi deja de guardar el GTFS (051)"},
]
FUENTES_P1 = {
    "emt_buses": ("EMT · posición de la flota", "si"),
    "trafico_estado": ("Tráfico · estado por tramo (capa 192)", "si"),
    "trafico_intensidad": ("Tráfico · intensidad por tramo (capa 188)", "si"),
    "valenbisi": ("Valenbisi · estaciones", "parcial"),
    "renfe_cercanias": ("Renfe Cercanías · núcleo de València", "si"),
}


def leer_curar(ruta: Path) -> dict:
    if not ruta.exists():
        raise FileNotFoundError(f"falta {ruta}: ejecuta `uv run dvc repro curar`")
    return json.loads(ruta.read_text(encoding="utf-8"))


def _dia(d: str) -> str:
    """'2026-10-07' -> '07/10'."""
    return f"{d[8:10]}/{d[5:7]}"


def _dias_del_crudo(raw: Path) -> list[str]:
    return sorted(
        p.name.removeprefix("date=") for p in (raw / "source=emt_buses").glob("date=*")
    )


def _serie(x, series, sombras=(), anotaciones=()) -> dict:
    return {
        "tipo": "serie",
        "x": [str(d) for d in x],
        "series": [
            {
                "nombre": nombre,
                "valores": [None if pd.isna(v) else float(v) for v in valores],
            }
            for nombre, valores in series
        ],
        "sombras": list(sombras),
        "anotaciones": list(anotaciones),
    }


def _cadencia(segundos: int) -> str:
    return f"cada {segundos} s" if segundos < 60 else f"cada {segundos // 60} min"


def p1():
    elementos = [
        {"nombre": nombre, "veredicto": v, "detalle": _cadencia(SOURCES[f].period_s)}
        for f, (nombre, v) in FUENTES_P1.items()
    ]
    elementos.append(
        {"nombre": "Metrovalencia · FGV", "veredicto": "no", "detalle": "sin tiempo real"}
    )
    valores = {"candidatas": len(elementos), "capturadas": len(SOURCES)}
    return valores, {"tipo": "lista", "elementos": elementos}


def p2(raw: Path, vol: pd.DataFrame):
    primeros = [
        next(read_raw(sorted((raw / f"source={s}").glob("date=*/*.ndjson.gz"))[0]))[0]
        for s in SOURCES
    ]
    primero = min(primeros).tz_convert(settings.zona_horaria)
    por_fuente = vol.groupby("fuente")["payloads"].sum()
    total = int(por_fuente.sum())
    valores = {"primer_sondeo": f"{primero:%d/%m/%Y a las %H:%M}", "payloads": total}
    prueba = {
        "tipo": "cifra",
        "valor": total,
        "decimales": 0,
        "etiqueta": "payloads crudos guardados",
        "detalle": [{"nombre": f, "valor": es(int(n))} for f, n in por_fuente.items()],
    }
    return valores, prueba


def p3(raw: Path):
    a = extraer.alternancia(raw, *PRIMERA_CAPTURA)
    valores = {
        "horas": (PRIMERA_CAPTURA[1] - PRIMERA_CAPTURA[0]) / pd.Timedelta(hours=1),
        "sondeos": a["sondeos"],
        "alternancias": a["alternancias"],
        "desplazadas": a["desplazadas"],
    }
    return valores, {"tipo": "pares", "registros": a["par"], "resalta": "diferencia"}


def p4(raw: Path):
    g = extraer.gid_por_sondeo(raw, DIA_GID)
    valores = {"pares": g["pares"], "comun": g["con_comun"], "dia": _dia(DIA_GID)}
    prueba = {
        "tipo": "pares",
        "registros": g["par"],
        "resalta": "gid en común con el anterior",
    }
    return valores, prueba


def p5(raw: Path):
    desde, hasta = CAPAS_CAIDAS
    series, hueco = [], None
    for fuente, nombre in [
        ("emt_buses", "EMT · sondeos al día"),
        ("trafico_estado", "capa de estado · sondeos al día"),
        ("renfe_cercanias", "Renfe · sondeos al día"),
    ]:
        n, hs = extraer.completitud(raw, fuente, desde, hasta)
        series.append((nombre, n.values))
        if fuente == "trafico_estado":
            hueco = max(hs, key=lambda h: h[1] - h[0])
    l71 = medir_fuentes.sql(
        "SELECT strftime(CAST(ts_ingest_utc AS DATE), '%Y-%m-%d') AS dia, "
        "count(*) AS n FROM {f} WHERE CAST(linea AS VARCHAR) = '71' GROUP BY 1",
        f="emt_buses",
    ).set_index("dia")["n"]
    series.append(("línea 71 · posiciones al día", l71.reindex(n.index, fill_value=0)))
    ini, fin = hueco
    # Renfe dentro del hueco de las capas: el colector seguía vivo.
    ts = [t for t in instantes(raw, "renfe_cercanias", desde, hasta) if ini <= t <= fin]
    renfe = max(b - a for a, b in zip(ts, ts[1:]))
    valores = {
        "desde": f"{ini:%d/%m %H:%M}",
        "hasta": f"{fin:%d/%m %H:%M}",
        "horas": (fin - ini) / pd.Timedelta(hours=1),
        "renfe_min": renfe / pd.Timedelta(minutes=1),
        "linea": "71",
    }
    sombra = {
        "desde": f"{ini:%Y-%m-%d}",
        "hasta": f"{fin:%Y-%m-%d}",
        "etiqueta": "las capas del geoportal no entregan nada",
    }
    return valores, _serie(n.index, series, [sombra])


def p6(raw: Path, curar: dict):
    b = extraer.bloque_a_medias(raw, _dias_del_crudo(raw))
    valores = {
        "filas_a": b["filas"][0],
        "filas_b": b["filas"][1],
        "completados": curar["emt_buses"]["completados"],
    }
    return valores, {"tipo": "pares", "registros": b["par"], "resalta": "filas"}


def p7():
    medido = medir_fuentes.lectivo()
    est, inten = medido["estado"], medido["intensidad"]
    est["dia"] = est["dia"].astype(str)
    inten["dia"] = inten["dia"].astype(str)
    laborables = est[est["dia"].between(*LECTIVO) & est["dow"].between(1, 5)]
    v188 = inten.loc[inten["dia"] <= LECTIVO[1], "valores_distintos"]
    valores = {
        "tramos": float(laborables["tramos_congestion"].median()),
        "valores": int(v188.iloc[0]) if v188.nunique() == 1 else -1,
    }
    dias = est["dia"].tolist()
    intensidad = inten.set_index("dia")["valores_distintos"].reindex(dias)
    prueba = _serie(
        dias,
        [
            ("capa de estado · tramos congestionados", est["tramos_congestion"]),
            ("capa de intensidad · valores distintos", intensidad),
        ],
        [{"desde": LECTIVO[0], "hasta": dias[-1], "etiqueta": "periodo lectivo"}],
    )
    return valores, prueba


def p8(vol: pd.DataFrame):
    v = vol[vol["dia"].between(*VOLUMEN)]
    r = v.groupby("fuente").agg(payloads=("payloads", "median"), mb=("mb", "median"))
    total, mb = float(r["payloads"].sum()), float(r["mb"].sum())
    valores = {"payloads": total, "por_segundo": total / 86400, "mb": mb}
    prueba = {
        "tipo": "cifra",
        "valor": total / 86400,
        "decimales": 3,
        "etiqueta": "payloads por segundo",
        "detalle": [
            {"nombre": f, "valor": f"{es(x['payloads'])} al día · {es(x['mb'])} MB"}
            for f, x in r.iterrows()
        ],
    }
    return valores, prueba


def p9(raw: Path, hasta: str):
    n, hs = extraer.completitud(raw, "emt_buses", INICIO, hasta)
    valores = {
        "dias": len(n),
        "cortes": len(hs),
        "horas": sum((b - a) / pd.Timedelta(hours=1) for a, b in hs),
    }
    sombras = [
        {
            "desde": f"{a:%Y-%m-%d}",
            "hasta": f"{b:%Y-%m-%d}",
            "etiqueta": f"sin captura de {a:%d/%m %H:%M} a {b:%d/%m %H:%M} UTC",
        }
        for a, b in hs
    ]
    anotaciones = [i for i in INCIDENTES if i["x"] <= hasta]
    serie = _serie(n.index, [("EMT · sondeos al día", n.values)], sombras, anotaciones)
    return valores, serie


def p10(raw: Path, hasta: str):
    posibles = {f: 86400 // SOURCES[f].period_s for f in ("emt_buses", "trafico_estado")}
    emt, hs = extraer.completitud(raw, "emt_buses", INICIO, hasta)
    e192, _ = extraer.completitud(raw, "trafico_estado", INICIO, hasta)
    fin = min(PRUEBA[1], hasta)
    prueba = emt.loc[PRUEBA[0] : fin]
    tocados = {
        f"{d:%Y-%m-%d}"
        for a, b in hs
        for d in pd.date_range(a.normalize(), b.normalize())
    }
    valores = {
        "desde": _dia(PRUEBA[0]),
        "hasta": _dia(fin),
        "pct": 100 * prueba.sum() / (posibles["emt_buses"] * len(prueba)),
        "utiles": sum(d not in tocados for d in prueba.index),
        "dias": len(prueba),
        # El cotejo cuenta su propia ventana, no la serie recortada al último día.
        "sondeos_cotejo": int(extraer.completitud(raw, "emt_buses", *COTEJO_PRUEBA)[0].sum()),
    }
    serie = _serie(
        emt.index,
        [
            ("EMT · % de los sondeos posibles", 100 * emt / posibles["emt_buses"]),
            (
                "capa de estado · % de los sondeos posibles",
                100 * e192 / posibles["trafico_estado"],
            ),
        ],
        [{"desde": PRUEBA[0], "hasta": fin, "etiqueta": "prueba del ADR-024"}],
    )
    return valores, serie


def origen(raw: Path) -> dict:
    def git(*args: str) -> str:
        r = subprocess.run(
            ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True
        )
        return r.stdout.strip()

    dias = _dias_del_crudo(raw)
    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "sucio": bool(git("status", "--porcelain", "--untracked-files=no")),
        "generado": datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        "crudo_desde": dias[0],
        "crudo_hasta": dias[-1],
    }


def construir() -> dict:
    raw = settings.raw_dir
    if not settings.curated_dir.exists():
        raise FileNotFoundError(
            f"falta {settings.curated_dir}: ejecuta `uv run dvc repro curar`"
        )
    curar = leer_curar(RAIZ / "metrics" / "curar.json")
    hasta = extraer.ultimo_dia_completo(raw)
    vol = medir_volumen.medir()
    medido = {
        "P1": p1(),
        "P2": p2(raw, vol),
        "P3": p3(raw),
        "P4": p4(raw),
        "P5": p5(raw),
        "P6": p6(raw, curar),
        "P7": p7(),
        "P8": p8(vol),
        "P9": p9(raw, hasta),
        "P10": p10(raw, hasta),
    }
    informe, paradas = [], []
    for p in PARADAS:
        valores, prueba = medido[p["id"]]
        informe += cotejar(p["id"], valores, p["cotejo"])
        validar_prueba(prueba)
        paradas.append(
            {
                "id": p["id"],
                "capitulo": p["capitulo"],
                "apartado": p["apartado"],
                "fecha": fecha_parada(p),
                "titulo": p["titulo"],
                "texto": redactar(p["texto"], valores),
                "prueba": prueba,
                "remite": [ficha(r) for r in p["remite"]],
                "duracion_s": p.get("duracion_s", 12),
            }
        )
    print("\n  Cotejo con las fichas\n" + "\n".join(informe))
    return {"origen": origen(raw), "capitulos": CAPITULOS, "paradas": paradas}


def main() -> None:
    foto = construir()
    datos = DESTINO / "datos" / "ingesta.js"
    n = escribir_foto(foto, datos)
    for p in foto["paradas"]:
        if p["prueba"]["tipo"] == "serie":
            destino = DESTINO / "figuras" / f"{p['id']}.pdf"
            figuras.figura_serie(p["prueba"], p["titulo"], destino)
    print(f"\n  foto: {n:,} bytes en {datos}\n  figuras en {DESTINO / 'figuras'}\n")
```

- [ ] **Step 4: Ver que el test pasa**

Run: `uv run pytest tests/test_dashboard.py -q`
Expected: `14 passed`.

- [ ] **Step 5: Commit del código antes de generar**

La foto anota el commit del que sale y si el árbol estaba sucio: se commitea el código primero.

```bash
uv run ruff format src/project/analysis/dashboard_ingesta tests/test_dashboard.py
uv run ruff check src/project/analysis/dashboard_ingesta tests/test_dashboard.py
git add src/project/analysis/dashboard_ingesta tests/test_dashboard.py
git commit -m "feat(dashboard): exportador de la foto de la ingesta, cotejada con sus fichas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Generar la foto y leer el cotejo**

Run: `uv run python -m project.analysis.dashboard_ingesta`

Expected: un bloque «Cotejo con las fichas» con todas las líneas en `ok` y, al final, `foto: N bytes` con N < 2.000.000. Valores esperados, medidos el 14/10 sobre el crudo hasta el 12/10:

| cotejo | esperado |
|---|---|
| P3 alternancias / sondeos | 342 / 1.236 (ficha: 338 / 1.224, ±2 %) |
| P4 comun | 0 |
| P5 horas | ≈ 103,74 (ficha: 103,7) |
| P8 payloads / mb | 6.342 / 299,3 (ficha: 6.336 / 297, ±2 %) |
| P10 sondeos_cotejo | 17.119 |
| P6 completados | 1.803 (≥ 1.200) |
| P7 tramos / valores | 43 / 243 (la 031 dio 34 con el 18/09 a medias; corrección en la 052) |

Medido el 14/10 con este mismo código en un worktree desechable: el exportador tarda unos 5 min (lee el crudo entero varias veces).

**Si algún cotejo FALLA, no relajes la tolerancia.** Para, mide con `superpowers:systematic-debugging` qué cuenta la ficha y qué cuenta el extractor, y lleva el hallazgo al usuario: es materia de bitácora, no un ajuste del exportador.

- [ ] **Step 7: Revisar la foto**

```bash
uv run python - <<'EOF'
import json, pathlib
t = pathlib.Path("dashboard/datos/ingesta.js").read_text(encoding="utf-8")
d = json.loads(t.removeprefix("window.DATOS = ").rstrip().removesuffix(";"))
print(d["origen"])
for p in d["paradas"]:
    print(p["id"], p["fecha"], p["prueba"]["tipo"], "|", p["texto"])
EOF
ls -la dashboard/figuras
```

Expected: `"sucio": false`; las diez paradas con fechas no decrecientes (14/08 … 13/10) y textos sin `{` ni huecos vacíos; cuatro PDF (P5, P7, P9, P10). Abre los PDF y comprueba que el hueco del 10-14/09 se ve en P5 y P9.

- [ ] **Step 8: Commit de la foto**

```bash
git add dashboard/datos/ingesta.js dashboard/figuras
git commit -m "feat(dashboard): foto de la ingesta y figuras de la memoria" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: La página

**Files:**
- Create: dashboard/vendor/d3.min.js, dashboard/vendor/gsap.min.js, dashboard/vendor/VERSIONES.txt
- Create: dashboard/index.html, dashboard/estilo.css, dashboard/escena.js

**Interfaces:**
- Consumes: `window.DATOS` de la Task 4: `origen{commit, sucio, generado, crudo_desde, crudo_hasta}`, `capitulos[{n, nombre}]`, `paradas[{id, capitulo, apartado, fecha, titulo, texto, prueba, remite[{ficha, fecha, titulo}], duracion_s}]`; tipos de prueba `lista{elementos[{nombre, veredicto: si|parcial|no, detalle}]}`, `pares{registros[{titulo, campos{}}] ×2, resalta}`, `serie{x[], series[{nombre, valores[]}], sombras[{desde, hasta, etiqueta}], anotaciones[{x, texto}]}`, `cifra{valor, decimales, etiqueta, detalle[{nombre, valor}]}`.
- Produces: la página. Teclas: → / espacio / clic avanzan, ← retrocede, Inicio vuelve a la primera, A activa la reproducción automática, F pantalla completa. URL: `?p=N` abre en la parada N (1-10), `?auto=1` reproduce sola.

- [ ] **Step 1: Librerías fijadas**

```bash
mkdir -p dashboard/vendor
curl -fsSL https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js -o dashboard/vendor/d3.min.js
curl -fsSL https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js -o dashboard/vendor/gsap.min.js
head -c 120 dashboard/vendor/d3.min.js; echo; head -c 160 dashboard/vendor/gsap.min.js; echo
```

Expected: la cabecera de D3 dice `v7.9.0` y la de GSAP `3.12.5`. Después:

```bash
{
  echo "Librerías del dashboard, fijadas y servidas desde aquí: la página abre sin red."
  echo "d3 7.9.0    https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js     (ISC)"
  echo "gsap 3.12.5 https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js (licencia estándar de GSAP, sin coste)"
  echo
  sha256sum dashboard/vendor/d3.min.js dashboard/vendor/gsap.min.js
} > dashboard/vendor/VERSIONES.txt
```

- [ ] **Step 2: index.html**

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camino de la ingesta</title>
<link rel="stylesheet" href="estilo.css">
</head>
<body>
<div id="lienzo">
  <svg id="linea" width="1920" height="230"></svg>
  <div id="paneles"></div>
  <div id="carteles"></div>
  <footer id="pie"></footer>
</div>
<!-- Scripts clásicos, no módulos: los módulos ES y fetch no abren desde file:// -->
<script src="vendor/d3.min.js"></script>
<script src="vendor/gsap.min.js"></script>
<script src="datos/ingesta.js"></script>
<script src="escena.js"></script>
</body>
</html>
```

- [ ] **Step 3: estilo.css**

```css
:root {
  --fondo: #f7f6f2;
  --marco: #e9e7e1;
  --tinta: #1d2329;
  --suave: #6b7178;
  --via: #c9ccd1;
  --acento: #1f5fa8;
  --aviso: #d9822b;
  --tarjeta: #ffffff;
  --si: #2e7d4f;
  --no: #b3261e;
  font-family: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; overflow: hidden; background: var(--marco); color: var(--tinta); }
#lienzo { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; overflow: hidden;
  background: var(--fondo); transform-origin: 0 0; }
#linea { position: absolute; left: 0; top: 0; }
.via { stroke: var(--via); stroke-width: 8; stroke-linecap: round; }
.via-hecha { stroke: var(--acento); stroke-width: 8; stroke-linecap: round; }
.estacion circle { fill: var(--fondo); stroke: var(--tinta); stroke-width: 5; }
.estacion .num { text-anchor: middle; font-size: 20px; font-weight: 700; fill: var(--tinta); }
.estacion .nombre { text-anchor: middle; font-size: 18px; fill: var(--suave); }
.parada circle { fill: var(--fondo); stroke: var(--acento); stroke-width: 4; }
.parada text { text-anchor: middle; font-size: 15px; fill: var(--suave); }
.marcador circle { fill: var(--aviso); stroke: #fff; stroke-width: 4; }
.marcador .fecha { text-anchor: middle; font-size: 22px; font-weight: 600; fill: var(--tinta); }
.panel { position: absolute; left: 120px; top: 250px; width: 1680px; height: 750px; visibility: hidden; }
.panel .apartado { margin: 0; font-size: 20px; color: var(--suave); text-transform: uppercase; letter-spacing: .08em; }
.panel h2 { margin: 8px 0 14px; font-size: 46px; }
.panel .texto { max-width: 1500px; margin: 0 0 26px; font-size: 26px; line-height: 1.45; }
.panel .remite { position: absolute; left: 0; bottom: 0; max-width: 1680px; margin: 0; font-size: 15px;
  color: var(--suave); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cartel { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 64px; font-weight: 700; background: rgba(247, 246, 242, .92); visibility: hidden; }
#pie { position: absolute; right: 24px; bottom: 12px; font-size: 13px; color: var(--suave); }
.aviso { margin: 300px auto; font-size: 32px; text-align: center; }

.lista { list-style: none; margin: 0; padding: 0; font-size: 28px; }
.lista li { display: grid; grid-template-columns: 56px 680px 1fr; padding: 10px 0; border-bottom: 1px solid #e3e1db; }
.lista .marca { font-weight: 700; }
.v-si .marca { color: var(--si); }
.v-parcial .marca { color: var(--aviso); }
.v-no .marca { color: var(--no); }
.lista .detalle { color: var(--suave); }

.pares { display: flex; gap: 48px; }
.registro { width: 780px; padding: 22px 28px; border-radius: 12px; background: var(--tarjeta);
  box-shadow: 0 2px 10px rgba(0, 0, 0, .06); }
.registro h3 { margin: 0 0 12px; font-size: 22px; font-weight: 600; color: var(--suave); }
.fila { display: flex; justify-content: space-between; padding: 8px 10px; border-radius: 6px; font-size: 24px; }
.fila .k { color: var(--suave); }
.fila .v { font-family: Consolas, "Cascadia Mono", monospace; }
.fila.resaltada { background: rgba(217, 130, 43, .22); font-weight: 600; }

.serie .trazo { fill: none; stroke: var(--acento); stroke-width: 3; }
.serie .punto { fill: transparent; }
.serie .punto:hover { fill: var(--acento); }
.serie .sombra { fill: var(--aviso); opacity: .16; }
.serie .rotulo { font-size: 17px; fill: var(--tinta); }
.serie .eje text { font-size: 14px; fill: var(--suave); }
.serie .anot line { stroke: var(--suave); stroke-dasharray: 4 4; }
.serie .anot text { font-size: 15px; fill: var(--tinta); }

.cifra .valor { font-size: 160px; font-weight: 700; line-height: 1; color: var(--acento); }
.cifra .etiqueta { margin: 6px 0 24px; font-size: 30px; color: var(--suave); }
.cifra .detalle { columns: 2; margin: 0; padding: 0; list-style: none; font-size: 22px; }
.cifra .detalle li { display: flex; gap: 18px; padding: 4px 0; }
.cifra .detalle .k { min-width: 220px; color: var(--suave); }
```

- [ ] **Step 4: escena.js**

```js
/* Dashboard de la defensa, fase 1: el camino del proyecto por la ingesta.
   Renderizador genérico: dibuja la línea y los cuatro tipos de prueba que trae
   window.DATOS (lo escribe project.analysis.dashboard_ingesta) y no sabe nada de
   paradas concretas. Una sola línea de tiempo de GSAP con una etiqueta por
   parada: avanzar es tweenTo y retroceder es la misma animación al revés. */
(function () {
  "use strict";
  const D = window.DATOS;
  const lienzo = document.getElementById("lienzo");

  function escalar() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    lienzo.style.transform =
      `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  }
  addEventListener("resize", escalar);
  escalar();

  if (!D) {
    lienzo.innerHTML = '<p class="aviso">Falta <code>datos/ingesta.js</code>.<br>' +
      "Genéralo con <code>uv run python -m project.analysis.dashboard_ingesta</code></p>";
    return;
  }

  const fmtFecha = d3.utcFormat("%d/%m/%Y");
  const PASO = 280, X0 = 160, Y = 120, ANCHO = 1920;

  // --- La línea: estaciones (capítulos) y paradas, en orden -----------------
  const nodos = [];
  D.capitulos.forEach((c) => {
    nodos.push({ tipo: "estacion", c });
    D.paradas.filter((p) => p.capitulo === c.n).forEach((p) => nodos.push({ tipo: "parada", p }));
  });
  nodos.forEach((n, i) => (n.x = X0 + i * PASO));
  const xFin = nodos[nodos.length - 1].x;
  const xDe = (p) => nodos.find((n) => n.p === p).x;
  // La cámara deja el marcador a un tercio de la izquierda sin pasarse de los extremos.
  const camara = (x) => Math.max(Math.min(0, ANCHO / 3 - x), ANCHO - (xFin + X0));

  const mundo = d3.select("#linea").append("g");
  mundo.append("line").attr("class", "via")
    .attr("x1", X0).attr("x2", xFin).attr("y1", Y).attr("y2", Y);
  const hecha = mundo.append("line").attr("class", "via-hecha")
    .attr("x1", X0).attr("x2", X0).attr("y1", Y).attr("y2", Y);
  const est = mundo.selectAll("g.estacion").data(nodos.filter((n) => n.tipo === "estacion"))
    .join("g").attr("class", "estacion").attr("transform", (n) => `translate(${n.x},${Y})`);
  est.append("circle").attr("r", 24);
  est.append("text").attr("class", "num").attr("dy", "0.35em").text((n) => n.c.n);
  est.append("text").attr("class", "nombre").attr("y", 56).text((n) => n.c.nombre);
  const circuloDe = new Map();
  const par = mundo.selectAll("g.parada").data(nodos.filter((n) => n.tipo === "parada"))
    .join("g").attr("class", "parada").attr("transform", (n) => `translate(${n.x},${Y})`);
  par.append("circle").attr("r", 10).each(function (n) { circuloDe.set(n.p, this); });
  par.append("text").attr("y", 40).text((n) => n.p.id);
  const marcador = mundo.append("g").attr("class", "marcador");
  marcador.append("circle").attr("r", 15);
  const fecha = marcador.append("text").attr("class", "fecha").attr("y", -32);

  const estado = { x: X0, cam: 0, t: Date.parse(D.paradas[0].fecha) };
  function pinta() {
    mundo.attr("transform", `translate(${estado.cam},0)`);
    marcador.attr("transform", `translate(${estado.x},${Y})`);
    hecha.attr("x2", estado.x);
    fecha.text(fmtFecha(new Date(estado.t)));
  }
  pinta();

  // --- Las pruebas: cada una devuelve la línea de tiempo de su entrada -------
  function lista(el, pr) {
    const li = d3.select(el).append("ul").attr("class", "lista")
      .selectAll("li").data(pr.elementos).join("li").attr("class", (e) => `v-${e.veredicto}`);
    li.append("span").attr("class", "marca")
      .text((e) => ({ si: "✓", parcial: "!", no: "✕" })[e.veredicto]);
    li.append("span").attr("class", "nombre").text((e) => e.nombre);
    li.append("span").attr("class", "detalle").text((e) => e.detalle);
    return gsap.timeline().from(li.nodes(), { autoAlpha: 0, x: -40, stagger: 0.12, duration: 0.4 });
  }

  function pares(el, pr) {
    const tarjetas = d3.select(el).append("div").attr("class", "pares")
      .selectAll("div").data(pr.registros).join("div").attr("class", "registro");
    tarjetas.append("h3").text((r) => r.titulo);
    const filas = tarjetas.selectAll("div.fila").data((r) => Object.entries(r.campos)).join("div")
      .attr("class", ([k]) => (k === pr.resalta ? "fila resaltada" : "fila"));
    filas.append("span").attr("class", "k").text(([k]) => k);
    filas.append("span").attr("class", "v").text(([, v]) => v);
    return gsap.timeline()
      .from(tarjetas.nodes(), { autoAlpha: 0, y: 30, stagger: 0.25, duration: 0.45 })
      .from(d3.select(el).selectAll(".resaltada").nodes(),
        { backgroundColor: "rgba(217,130,43,0.75)", duration: 0.9 }, ">");
  }

  function serie(el, pr) {
    const W = 1680, n = pr.series.length, H = Math.min(160, 440 / n);
    const M = { l: 330, r: 30, t: 56, b: 34 };
    const fechas = pr.x.map((d) => new Date(d));
    const x = d3.scaleUtc().domain(d3.extent(fechas)).range([M.l, W - M.r]);
    const alto = M.t + H * n;
    const DIA = 864e5;
    const svg = d3.select(el).append("svg").attr("class", "serie")
      .attr("width", W).attr("height", alto + M.b);
    const sombras = svg.selectAll("rect.sombra").data(pr.sombras).join("rect").attr("class", "sombra")
      .attr("x", (s) => x(new Date(s.desde)))
      .attr("width", (s) => Math.max(3, x(new Date(Date.parse(s.hasta) + DIA)) - x(new Date(s.desde))))
      .attr("y", M.t).attr("height", H * n);
    sombras.append("title").text((s) => s.etiqueta);
    const tl = gsap.timeline();
    pr.series.forEach((s, i) => {
      const y0 = M.t + H * i;
      const y = d3.scaleLinear().domain([0, d3.max(s.valores) || 1]).nice()
        .range([y0 + H - 14, y0 + 8]);
      const g = svg.append("g");
      g.append("text").attr("class", "rotulo").attr("x", M.l - 60).attr("y", y0 + H / 2)
        .attr("dy", "0.35em").attr("text-anchor", "end").text(s.nombre);
      g.append("g").attr("class", "eje").attr("transform", `translate(${M.l - 8},0)`)
        .call(d3.axisLeft(y).ticks(3).tickSizeOuter(0));
      const puntos = pr.x.map((d, j) => [fechas[j], s.valores[j], d]);
      const linea = d3.line().defined((v) => v[1] != null).x((v) => x(v[0])).y((v) => y(v[1]));
      const trazo = g.append("path").attr("class", "trazo").attr("d", linea(puntos));
      g.selectAll("circle").data(puntos.filter((v) => v[1] != null)).join("circle")
        .attr("class", "punto").attr("r", 6).attr("cx", (v) => x(v[0])).attr("cy", (v) => y(v[1]))
        .append("title").text((v) => `${v[2]} · ${v[1].toLocaleString("es-ES")}`);
      const L = trazo.node().getTotalLength();
      trazo.attr("stroke-dasharray", L).attr("stroke-dashoffset", L);
      tl.to(trazo.node(), { attr: { "stroke-dashoffset": 0 }, duration: 1.3, ease: "power1.inOut" }, i * 0.2);
    });
    svg.append("g").attr("class", "eje").attr("transform", `translate(0,${alto})`)
      .call(d3.axisBottom(x).ticks(d3.utcWeek.every(1)).tickFormat(d3.utcFormat("%d/%m")));
    const anot = svg.selectAll("g.anot").data(pr.anotaciones).join("g").attr("class", "anot")
      .attr("transform", (a) => `translate(${x(new Date(a.x))},0)`);
    anot.append("line").attr("y1", M.t - 4).attr("y2", alto);
    anot.append("text").attr("y", (a, i) => M.t - 12 - (i % 2) * 22)
      .attr("text-anchor", "middle").text((a) => a.texto);
    return tl.from(sombras.nodes(), { opacity: 0, duration: 0.5 }, 0)
      .from(anot.nodes(), { opacity: 0, stagger: 0.15, duration: 0.4 }, ">-0.4");
  }

  function cifra(el, pr) {
    const c = d3.select(el).append("div").attr("class", "cifra");
    const valor = c.append("div").attr("class", "valor");
    c.append("div").attr("class", "etiqueta").text(pr.etiqueta);
    const li = c.append("ul").attr("class", "detalle").selectAll("li").data(pr.detalle).join("li");
    li.append("span").attr("class", "k").text((d) => d.nombre);
    li.append("span").attr("class", "v").text((d) => d.valor);
    const fmt = (v) => v.toLocaleString("es-ES", {
      minimumFractionDigits: pr.decimales, maximumFractionDigits: pr.decimales, useGrouping: "always" });
    const o = { v: pr.valor };
    valor.text(fmt(pr.valor));
    return gsap.timeline()
      .from(o, { v: 0, duration: 1.2, ease: "power2.out", onUpdate: () => valor.text(fmt(o.v)) })
      .from(li.nodes(), { autoAlpha: 0, y: 12, stagger: 0.08, duration: 0.3 }, "-=0.6");
  }

  const R = { lista, pares, serie, cifra };

  // --- Paneles: todos se construyen al cargar, ocultos ------------------------
  const contenedor = document.getElementById("paneles");
  const paneles = D.paradas.map((p) => {
    const el = d3.select(contenedor).append("section").attr("class", "panel");
    el.append("p").attr("class", "apartado")
      .text(`${p.capitulo} · ${D.capitulos[p.capitulo - 1].nombre} · ${p.apartado}`);
    const h = el.append("h2").text(p.titulo);
    const t = el.append("p").attr("class", "texto").text(p.texto);
    const pr = el.append("div").attr("class", "prueba");
    el.append("p").attr("class", "remite")
      .text(p.remite.map((f) => `${f.ficha}: ${f.titulo}`).join("   ·   "));
    const entrada = gsap.timeline()
      .from([h.node(), t.node()], { autoAlpha: 0, y: 24, stagger: 0.15, duration: 0.45 })
      .add(R[p.prueba.tipo](pr.node(), p.prueba), ">-0.1");
    return { el: el.node(), entrada };
  });

  const carteles = new Map(D.capitulos.map((c) => [c.n,
    d3.select("#carteles").append("div").attr("class", "cartel").text(`${c.n} · ${c.nombre}`).node()]));

  // --- La línea de tiempo maestra ---------------------------------------------
  const tl = gsap.timeline({ paused: true });
  D.paradas.forEach((p, i) => {
    const previa = D.paradas[i - 1];
    if (previa) tl.to(paneles[i - 1].el, { autoAlpha: 0, y: -20, duration: 0.4 });
    tl.to(estado, {
      x: xDe(p), cam: camara(xDe(p)), t: Date.parse(p.fecha),
      duration: previa ? 1.2 : 0.8, ease: "power2.inOut", onUpdate: pinta,
    });
    if (!previa || previa.capitulo !== p.capitulo) {
      const c = carteles.get(p.capitulo);
      tl.to(c, { autoAlpha: 1, duration: 0.3 }, "<0.3").to(c, { autoAlpha: 0, duration: 0.3 }, "+=0.7");
    }
    tl.to(circuloDe.get(p), { attr: { r: 18 }, duration: 0.2, yoyo: true, repeat: 1 });
    tl.set(paneles[i].el, { autoAlpha: 1, y: 0 });
    tl.add(paneles[i].entrada);
    tl.addLabel(`p${i}`);
  });

  // --- Navegación ---------------------------------------------------------------
  const total = D.paradas.length;
  let actual = -1, auto = false, espera = null;
  function programar() {
    clearTimeout(espera);
    if (auto && actual < total - 1)
      espera = setTimeout(() => ir(actual + 1), D.paradas[actual].duracion_s * 1000);
  }
  function ir(j) {
    actual = Math.max(0, Math.min(total - 1, j));
    clearTimeout(espera);
    tl.tweenTo(`p${actual}`, { overwrite: true, onComplete: programar });
  }
  addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " ") ir(actual + 1);
    else if (e.key === "ArrowLeft") ir(actual - 1);
    else if (e.key === "Home") ir(0);
    else if (e.key === "a" || e.key === "A") { auto = !auto; programar(); }
    else if (e.key === "f" || e.key === "F") {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });
  addEventListener("click", () => ir(actual + 1));

  d3.select("#pie").text(
    `foto ${D.origen.commit}${D.origen.sucio ? " (con cambios sin commitear)" : ""} · ` +
    `generada ${D.origen.generado} · crudo ${D.origen.crudo_desde} → ${D.origen.crudo_hasta}`);

  const q = new URLSearchParams(location.search);
  if (q.has("p")) {
    actual = Math.max(0, Math.min(total - 1, Number(q.get("p")) - 1));
    tl.seek(`p${actual}`, false);
  } else {
    ir(0);
  }
  if (q.get("auto") === "1") { auto = true; programar(); }
  console.log(`[dashboard] ${total} paradas, foto ${D.origen.commit}`);
})();
```

- [ ] **Step 5: Verificar con Chrome sin cabeza**

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
# Ruta con forma de Windows: Chrome es nativo y no entiende /tmp de Git Bash.
OUT="C:/Users/oppen/AppData/Local/Temp/dashboard-capturas"; mkdir -p "$OUT"
URL="file:///C:/Users/oppen/Code/TFM/dashboard/index.html"
for i in $(seq 1 10); do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 \
    --virtual-time-budget=5000 --enable-logging=stderr --v=0 \
    --screenshot="$OUT/P$i.png" "$URL?p=$i" 2>&1 | grep -E "dashboard\]|Uncaught|TypeError|ReferenceError" || true
done
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1024,768 \
  --virtual-time-budget=5000 --screenshot="$OUT/P5-4x3.png" "$URL?p=5"
ls "$OUT"
```

Expected: diez veces la línea `[dashboard] 10 paradas, foto <commit>` y ningún `Uncaught`/`TypeError`/`ReferenceError`. Abre cada PNG con la herramienta Read y comprueba:
- la línea arriba con las 6 estaciones, el tramo recorrido en azul hasta la parada y la fecha encima del marcador;
- el apartado, el título, el texto sin `{` y la prueba completa (P1 lista, P2 y P8 cifra, P3/P4/P6 dos tarjetas con el campo resaltado, P5/P7/P9/P10 series con sombras y anotaciones);
- el pie con el commit y sin «con cambios sin commitear»;
- P5-4x3.png: el lienzo entero con bandas arriba y abajo, nada recortado.

Si un texto se sale de su caja o dos anotaciones se pisan, ajusta solo estilo.css o las alturas de `serie` y repite.

- [ ] **Step 6: Sin datos, la página lo dice**

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
OUT="C:/Users/oppen/AppData/Local/Temp/dashboard-capturas"
URL="file:///C:/Users/oppen/Code/TFM/dashboard/index.html"
mv dashboard/datos/ingesta.js "$TEMP/ingesta.js.bak"
"$CHROME" --headless=new --disable-gpu --window-size=1920,1080 --virtual-time-budget=3000 \
  --screenshot="$OUT/sin-datos.png" "$URL"
mv "$TEMP/ingesta.js.bak" dashboard/datos/ingesta.js
git status --short dashboard/datos   # Expected: nada
```

Expected: sin-datos.png enseña «Falta datos/ingesta.js. Genéralo con uv run python -m project.analysis.dashboard_ingesta».

- [ ] **Step 7: Recorrido a mano (lo hace el usuario)**

Pide al usuario que abra dashboard/index.html con doble clic en Chrome y compruebe: → recorre las 10 paradas con el marcador moviéndose y la fecha contando; ← deshace la última transición; pulsar → dos veces seguidas durante una transición no rompe nada; A reproduce sola hasta P10; F entra y sale de pantalla completa; al pasar el ratón por una serie aparece el tooltip con día y valor.

- [ ] **Step 8: Commit**

```bash
git add dashboard/index.html dashboard/estilo.css dashboard/escena.js dashboard/vendor
git commit -m "feat(dashboard): página de la ingesta con D3 y GSAP, sin red ni servidor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Cierre

**Files:**
- Modify: CLAUDE.md (sección Comandos)
- Create: auditoria/resultados/mutantes_<commit>.json (lo escribe `mutar.py`)

- [ ] **Step 1: Documentar el comando**

En CLAUDE.md, en el bloque de la sección «Comandos», tras la línea de `project.analysis.diagnose`, añade:

```bash
uv run python -m project.analysis.dashboard_ingesta  # foto y figuras del dashboard de la defensa
```

- [ ] **Step 2: Suites completas**

```bash
uv run ruff format . && uv run ruff check --fix .
uv run pytest -q
uv run pytest .claude/tests -q
```

Expected: todo en verde; tests/test_dashboard.py con 14 tests.

- [ ] **Step 3: Commit y auditoría de mutantes**

```bash
git add CLAUDE.md
git commit -m "docs: comando del dashboard de la defensa" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
uv run python auditoria/mutar.py --solo 145 146 147 148 149 150 151
```

Expected: los controles 000 `equivalente` y 002 `detectado`, y los mutantes 145-151 `detectado`, cada uno con su detector esperado como caído. Si alguno sale `invalido`, su `buscar` ya no aparece exactamente una vez (lo habrá tocado `ruff format`): corrige el `buscar` en el catálogo, commitea y repite.

```bash
git add auditoria/resultados/mutantes_*.json
git commit -m "test(auditoria): mutantes 145-151 detectados" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Ofrecer lo que va a la bitácora**

No lo escribas sin preguntar. Ofrece al usuario fichar con `/bitacora`:
- la ventana de la primera captura (15/08 22:15 → 16/08 08:55) dura 10 h 40 min, no «12,5 h» como dicen `docs/05` y el docstring de `resolver_convencion`;
- la trampa 002 da 338 alternancias en 1.224 sondeos y el crudo de hoy da 342 en 1.236;
- la bitácora 033 da 6.336 payloads y 297 MB al día, y el crudo de hoy da 6.342 y 299 MB;
- Renfe tiene 244 payloads que no parsean en metrics/curar.json (`errores`), sin explicar;
- cualquier cotejo que no haya salido como en la tabla del paso 6 de la Task 4.

Después, antes de integrar la rama, la skill `pre-merge`.
