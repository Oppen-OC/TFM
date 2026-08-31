"""Validación mecánica del registro de trampas (`.claude/trampas/`).

El registro solo sirve si dice la verdad. Una ficha marcada `cerrada` cuyo test no
existe es peor que no tener ficha: afirma una protección que nadie está dando.

Estas comprobaciones son las que no requieren juicio. Las que sí (duplicación de
contenido fuera del directorio, trampas descritas en `docs/` sin fichar, fichas
estancadas) viven en el comando `/trampas`.

Sin dependencias nuevas: el frontmatter es `clave: valor` plano y se parsea con
regex. `pyyaml` solo está en el entorno como transitiva de mlflow y no se declara
en `pyproject.toml`, así que no nos apoyamos en él.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TRAMPAS = RAIZ / ".claude" / "trampas"
SELFTEST = RAIZ / "demo" / "selftest.py"

CAMPOS = ("id", "titulo", "estado", "capa", "detectada", "test")
ESTADOS = {"vigente", "mitigada", "cerrada"}
CAPAS = {"fuentes", "tracking", "etiquetado", "pipeline", "serving"}

RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
RE_CAMPO = re.compile(r"^([a-z_]+):\s*(.*)$")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# `demo/selftest.py::"nombre del check"` o node id de pytest `tests/x.py::test_y`
RE_TEST_SELFTEST = re.compile(r'^demo/selftest\.py::"(.+)"$')
RE_TEST_PYTEST = re.compile(r"^(tests/[\w/]+\.py)::([\w\[\]-]+)$")


def _fichas() -> list[Path]:
    return sorted(TRAMPAS.glob("[0-9]*.md"))


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


def _checks_de_selftest() -> set[str]:
    """Nombres declarados con check("...") en demo/selftest.py.

    Solo literales: los `check(f"{x}: ...")` dentro de bucles no se pueden
    resolver estáticamente y no deben referenciarse desde una ficha.
    """
    texto = SELFTEST.read_text(encoding="utf-8")
    return set(re.findall(r'\bcheck\(\s*"([^"]+)"', texto))


# Recolectado una vez: si el directorio no existe, todo el módulo debe fallar
# ruidosamente en lugar de pasar en verde por no encontrar nada que validar.
FICHAS = _fichas()


def test_el_registro_existe():
    assert TRAMPAS.is_dir(), f"falta el directorio {TRAMPAS}"
    assert (TRAMPAS / "README.md").is_file(), "falta el índice README.md"
    assert FICHAS, "el registro no tiene ninguna ficha"


@pytest.mark.parametrize("ruta", FICHAS, ids=lambda p: p.stem)
def test_frontmatter_completo_y_valido(ruta: Path):
    fm = _frontmatter(ruta)

    faltan = [c for c in CAMPOS if c not in fm]
    assert not faltan, f"{ruta.name}: faltan campos {faltan}"

    assert fm["estado"] in ESTADOS, f"{ruta.name}: estado {fm['estado']!r} no válido"
    assert fm["capa"] in CAPAS, f"{ruta.name}: capa {fm['capa']!r} no válida"
    assert RE_FECHA.match(fm["detectada"]), (
        f"{ruta.name}: detectada {fm['detectada']!r} no es YYYY-MM-DD"
    )
    assert fm["titulo"], f"{ruta.name}: titulo vacío"

    prefijo = ruta.name.split("-")[0]
    assert fm["id"] == prefijo, (
        f"{ruta.name}: id {fm['id']!r} no coincide con el prefijo del fichero"
    )


def test_ids_correlativos_y_sin_duplicados():
    ids = [_frontmatter(f)["id"] for f in FICHAS]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"
    esperados = [f"{i:03d}" for i in range(1, len(ids) + 1)]
    assert ids == esperados, f"ids con huecos o desordenados: {ids} != {esperados}"


@pytest.mark.parametrize("ruta", FICHAS, ids=lambda p: p.stem)
def test_cerrada_exige_guardia(ruta: Path):
    """La regla dura del registro: sin test que la guarde, una trampa no se cierra."""
    fm = _frontmatter(ruta)
    if fm["estado"] == "cerrada":
        assert fm["test"] != "ninguno", (
            f"{ruta.name}: estado 'cerrada' con test 'ninguno'. "
            "Sin guardia no se cierra: pásala a 'mitigada' o escribe el test."
        )
    else:
        assert fm["test"] == "ninguno", (
            f"{ruta.name}: estado {fm['estado']!r} pero declara test {fm['test']!r}. "
            "Si el test existe y la guarda, pásala a 'cerrada'."
        )


@pytest.mark.parametrize("ruta", FICHAS, ids=lambda p: p.stem)
def test_el_test_citado_existe(ruta: Path):
    """Una ficha que cita un test inexistente afirma una protección que no hay."""
    fm = _frontmatter(ruta)
    ref = fm["test"]
    if ref == "ninguno":
        return

    if m := RE_TEST_SELFTEST.match(ref):
        nombre = m.group(1)
        disponibles = _checks_de_selftest()
        assert nombre in disponibles, (
            f"{ruta.name}: el check {nombre!r} no existe en demo/selftest.py"
        )
        return

    if m := RE_TEST_PYTEST.match(ref):
        fichero = RAIZ / m.group(1)
        assert fichero.is_file(), f"{ruta.name}: {m.group(1)} no existe"
        assert f"def {m.group(2)}" in fichero.read_text(encoding="utf-8"), (
            f"{ruta.name}: {m.group(2)} no está definido en {m.group(1)}"
        )
        return

    pytest.fail(
        f"{ruta.name}: test {ref!r} no tiene formato reconocible. "
        'Usa demo/selftest.py::"<nombre del check>" o tests/<f>.py::<test_x>.'
    )


def test_indice_sincronizado_con_las_fichas():
    """El índice es lo único que se carga siempre: si miente, miente en todas partes."""
    readme = (TRAMPAS / "README.md").read_text(encoding="utf-8")

    filas = {}
    for linea in readme.splitlines():
        m = re.match(
            r"^\|\s*\[(\d+)\]\(([^)]+)\)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|", linea
        )
        if m:
            filas[m.group(1)] = {
                "fichero": m.group(2),
                "estado": m.group(3),
                "capa": m.group(4),
            }

    en_disco = {_frontmatter(f)["id"]: f for f in FICHAS}

    assert set(filas) == set(en_disco), (
        f"índice y directorio no coinciden. "
        f"Solo en el índice: {sorted(set(filas) - set(en_disco))}. "
        f"Solo en disco: {sorted(set(en_disco) - set(filas))}."
    )

    for id_, fila in filas.items():
        ficha = en_disco[id_]
        fm = _frontmatter(ficha)
        assert fila["fichero"] == ficha.name, (
            f"índice {id_}: enlaza a {fila['fichero']}, la ficha es {ficha.name}"
        )
        assert fila["estado"] == fm["estado"], (
            f"índice {id_}: estado {fila['estado']!r} != frontmatter {fm['estado']!r}"
        )
        assert fila["capa"] == fm["capa"], (
            f"índice {id_}: capa {fila['capa']!r} != frontmatter {fm['capa']!r}"
        )


def test_indice_no_engorda():
    """Se carga en cada turno de cada sesión y de cada subagente."""
    lineas = len((TRAMPAS / "README.md").read_text(encoding="utf-8").splitlines())
    assert lineas <= 45, (
        f"el índice tiene {lineas} líneas. Compacta las fichas `cerrada` a media línea."
    )


@pytest.mark.parametrize("ruta", FICHAS, ids=lambda p: p.stem)
def test_secciones_fijas(ruta: Path):
    """Sin 'por qué se vuelve a caer aquí' no era una trampa, era un bug."""
    texto = ruta.read_text(encoding="utf-8").lower()
    for seccion in (
        "## síntoma",
        "## causa",
        "## por qué se vuelve a caer aquí",
        "## guardia",
    ):
        assert seccion in texto, f"{ruta.name}: falta la sección {seccion!r}"
