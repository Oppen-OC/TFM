"""Validación mecánica de la bitácora de hallazgos (`docs/bitacora/`).

La bitácora existe para que la memoria del TFM se escriba con cifras rastreables
en vez de con recuerdos. Una entrada sin comando que la reproduzca, o con una
sección "Para la memoria" vacía, no cumple ninguna de las dos cosas y además
aparenta cumplirlas.

Solo entra aquí lo inequívoco. Lo que exige juicio —si la cifra sigue saliendo,
si una entrada `abierto` está estancada, si hay hallazgos en `docs/` sin fichar—
vive en el comando `/bitacora`.

Sin dependencias nuevas: el frontmatter es `clave: valor` plano y se parsea con
regex, igual que en `test_trampas.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BITACORA = RAIZ / "docs" / "bitacora"
TRAMPAS = RAIZ / ".claude" / "trampas"

CAMPOS = (
    "id",
    "titulo",
    "fecha",
    "tipo",
    "capa",
    "capitulo",
    "impacto",
    "estado",
    "evidencia",
    "trampa",
)
TIPOS = {"medicion", "anomalia", "limitacion", "descarte", "tecnica"}
CAPAS = {"fuentes", "tracking", "etiquetado", "pipeline", "serving"}
CAPITULOS = {"calidad-dato", "metodologia", "resultados", "limitaciones"}
IMPACTOS = {"alto", "medio", "bajo"}
ESTADOS = {"abierto", "mitigado", "resuelto", "aceptado"}

SECCIONES = (
    "## qué se observó",
    "## cómo se midió",
    "## por qué importa",
    "## qué se hizo / qué queda abierto",
    "## para la memoria",
)

RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
RE_CAMPO = re.compile(r"^([a-z_]+):\s*(.*)$")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_FILA = re.compile(
    r"^\|\s*\[(\d+)\]\(([^)]+)\)\s*\|\s*([\d-]+)\s*\|\s*(\w+)\s*\|\s*([\w-]+)\s*\|"
)


def _entradas() -> list[Path]:
    return sorted(BITACORA.glob("[0-9]*.md"))


def _frontmatter(ruta: Path) -> dict[str, str]:
    m = RE_FRONTMATTER.match(ruta.read_text(encoding="utf-8"))
    assert m, f"{ruta.name}: sin frontmatter delimitado por ---"
    campos: dict[str, str] = {}
    for linea in m.group(1).splitlines():
        if not linea.strip():
            continue
        c = RE_CAMPO.match(linea)
        assert c, f"{ruta.name}: línea de frontmatter no es `clave: valor`: {linea!r}"
        campos[c.group(1)] = c.group(2).strip()
    return campos


def _seccion(ruta: Path, titulo: str) -> str:
    """Texto de una sección, del encabezado al siguiente `## ` o al final."""
    texto = ruta.read_text(encoding="utf-8")
    partes = re.split(r"^## ", texto, flags=re.MULTILINE)
    for p in partes[1:]:
        if p.lower().startswith(titulo.removeprefix("## ")):
            return p
    return ""


# Recolectado una vez: si el directorio no existe, el módulo debe fallar
# ruidosamente en lugar de pasar en verde por no encontrar nada que validar.
ENTRADAS = _entradas()


def test_el_registro_existe():
    assert BITACORA.is_dir(), f"falta el directorio {BITACORA}"
    assert (BITACORA / "README.md").is_file(), "falta el índice README.md"
    assert ENTRADAS, "la bitácora no tiene ninguna entrada"


@pytest.mark.parametrize("ruta", ENTRADAS, ids=lambda p: p.stem)
def test_frontmatter_completo_y_valido(ruta: Path):
    fm = _frontmatter(ruta)

    faltan = [c for c in CAMPOS if c not in fm]
    assert not faltan, f"{ruta.name}: faltan campos {faltan}"

    assert fm["tipo"] in TIPOS, f"{ruta.name}: tipo {fm['tipo']!r} no válido"
    assert fm["capa"] in CAPAS, f"{ruta.name}: capa {fm['capa']!r} no válida"
    assert fm["capitulo"] in CAPITULOS, (
        f"{ruta.name}: capitulo {fm['capitulo']!r} no válido"
    )
    assert fm["impacto"] in IMPACTOS, (
        f"{ruta.name}: impacto {fm['impacto']!r} no válido"
    )
    assert fm["estado"] in ESTADOS, f"{ruta.name}: estado {fm['estado']!r} no válido"
    assert RE_FECHA.match(fm["fecha"]), (
        f"{ruta.name}: fecha {fm['fecha']!r} no es YYYY-MM-DD"
    )
    assert fm["titulo"], f"{ruta.name}: titulo vacío"

    prefijo = ruta.name.split("-")[0]
    assert fm["id"] == prefijo, (
        f"{ruta.name}: id {fm['id']!r} no coincide con el prefijo del fichero"
    )


def test_ids_correlativos_y_sin_duplicados():
    ids = [_frontmatter(f)["id"] for f in ENTRADAS]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"
    esperados = [f"{i:03d}" for i in range(1, len(ids) + 1)]
    assert ids == esperados, f"ids con huecos o desordenados: {ids} != {esperados}"


@pytest.mark.parametrize("ruta", ENTRADAS, ids=lambda p: p.stem)
def test_secciones_fijas(ruta: Path):
    texto = ruta.read_text(encoding="utf-8").lower()
    for seccion in SECCIONES:
        assert seccion in texto, f"{ruta.name}: falta la sección {seccion!r}"


@pytest.mark.parametrize("ruta", ENTRADAS, ids=lambda p: p.stem)
def test_la_cifra_es_rastreable(ruta: Path):
    """Sin evidencia la entrada es una anécdota con decimales.

    O trae un comando reejecutable en `Cómo se midió`, o dice explícitamente que
    no se ha podido reproducir — y entonces sigue `abierto`.
    """
    fm = _frontmatter(ruta)
    assert fm["evidencia"] and fm["evidencia"] != "ninguna", (
        f"{ruta.name}: `evidencia` vacía. Cita el comando, el fichero:línea o el commit."
    )

    medicion = _seccion(ruta, "## cómo se midió")
    if "no reproducido" in medicion.lower():
        assert fm["estado"] == "abierto", (
            f"{ruta.name}: dice 'no reproducido' pero su estado es {fm['estado']!r}. "
            "Una cifra sin reproducir no se da por mitigada ni por resuelta."
        )
    else:
        assert "```" in medicion, (
            f"{ruta.name}: 'Cómo se midió' no trae bloque de comando ni declara "
            "'no reproducido'."
        )


@pytest.mark.parametrize("ruta", ENTRADAS, ids=lambda p: p.stem)
def test_hay_parrafo_para_la_memoria(ruta: Path):
    """Es la sección que hace que la bitácora ahorre trabajo en febrero."""
    cuerpo = _seccion(ruta, "## para la memoria")
    citado = [ln for ln in cuerpo.splitlines() if ln.startswith(">")]
    assert sum(len(ln) for ln in citado) >= 300, (
        f"{ruta.name}: 'Para la memoria' está vacía o es un apunte. Debe traer el "
        "párrafo redactado, en cita (`>`), listo para pegar en el capítulo."
    )


@pytest.mark.parametrize("ruta", ENTRADAS, ids=lambda p: p.stem)
def test_la_trampa_referenciada_existe(ruta: Path):
    ref = _frontmatter(ruta)["trampa"]
    if ref in ("—", "-", "ninguna"):
        return
    fichas = list(TRAMPAS.glob(f"{ref}-*.md"))
    assert fichas, f"{ruta.name}: cita la trampa {ref!r} y no hay ficha con ese id"


def test_indice_sincronizado_con_las_entradas():
    readme = (BITACORA / "README.md").read_text(encoding="utf-8")

    filas = {
        m.group(1): {
            "fichero": m.group(2),
            "fecha": m.group(3),
            "tipo": m.group(4),
            "capitulo": m.group(5),
        }
        for m in (RE_FILA.match(ln) for ln in readme.splitlines())
        if m
    }
    en_disco = {_frontmatter(f)["id"]: f for f in ENTRADAS}

    assert set(filas) == set(en_disco), (
        f"índice y directorio no coinciden. "
        f"Solo en el índice: {sorted(set(filas) - set(en_disco))}. "
        f"Solo en disco: {sorted(set(en_disco) - set(filas))}."
    )

    for id_, fila in filas.items():
        entrada = en_disco[id_]
        fm = _frontmatter(entrada)
        assert fila["fichero"] == entrada.name, (
            f"índice {id_}: enlaza a {fila['fichero']}, la entrada es {entrada.name}"
        )
        for campo in ("fecha", "tipo", "capitulo"):
            assert fila[campo] == fm[campo], (
                f"índice {id_}: {campo} {fila[campo]!r} != frontmatter {fm[campo]!r}"
            )
