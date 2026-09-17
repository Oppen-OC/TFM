"""Validación mecánica de la maquinaria de exámenes (`/examen` + `.claude/examenes/`).

El examen es un instrumento de medida, y el instrumento también miente (trampa
004). Dos fallos lo matan sin dar la cara: que la clave acabe escrita dentro del
propio examen —se lee, y el 100 % deja de significar nada— y que el comando
duplique las reglas del README hasta que las dos copias divergen.

Lo que exige juicio (si las preguntas discriminan de verdad, si la corrección es
dura con `a-medias`, si un concepto está bien delimitado) no se comprueba aquí.

Sin dependencias nuevas: frontmatter `clave: valor` plano, parseado con regex.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
EXAMENES = RAIZ / ".claude" / "examenes"
README = EXAMENES / "README.md"
DEBILIDADES = EXAMENES / "debilidades.md"
COMANDO = RAIZ / ".claude" / "commands" / "examen.md"

CAMPOS = ("id", "tema", "fecha", "fuentes", "estado", "ronda", "nota")
ESTADOS = {"en-blanco", "contestado", "corregido", "cerrado"}
VEREDICTOS = {"correcta", "a-medias", "fallada", "—"}
COLUMNAS_DEBILIDADES = (
    "concepto",
    "tema",
    "fallos",
    "aciertos limpios",
    "último",
    "estado",
)

RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
# Guion incluido: el comando usa `argument-hint`, que es justo lo que se comprueba.
RE_CAMPO = re.compile(r"^([a-z_-]+):\s*(.*)$")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_PREGUNTA = re.compile(r"^## P(\d+) · ", re.MULTILINE)
RE_CONCEPTO = re.compile(r"^<!-- concepto: ([a-z0-9-]+) -->$", re.MULTILINE)
RE_VEREDICTO = re.compile(r"^\*\*Veredicto:\*\* (.+)$", re.MULTILINE)
# Fila del índice de trampas o de bitácora: `| [008](008-slug.md) | ...`.
RE_FILA_INDICE = re.compile(r"^\|\s*\[\d{3}\]\(\d{3}-", re.MULTILINE)
# Cualquier forma de escribir la clave dentro del examen.
RE_CLAVE = re.compile(r"\*\*(Clave|Solución|Respuesta correcta|Corrección)\b")


def _examenes() -> list[Path]:
    return sorted(EXAMENES.glob("[0-9]*.md"))


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


def _bloques(ruta: Path) -> list[str]:
    """Trocea el examen en bloques de pregunta, descartando el preámbulo."""
    texto = ruta.read_text(encoding="utf-8")
    return re.split(r"^## P\d+ · ", texto, flags=re.MULTILINE)[1:]


EXAMENES_FICHEROS = _examenes()


# --- El registro existe y está bien formado -------------------------------


def test_el_directorio_y_sus_dos_ficheros_fijos_existen() -> None:
    """Sin README no hay fuente de verdad; sin debilidades.md no hay estado."""
    assert EXAMENES.is_dir(), "falta el directorio .claude/examenes/"
    assert README.is_file(), "falta .claude/examenes/README.md"
    assert DEBILIDADES.is_file(), "falta .claude/examenes/debilidades.md"


def test_el_readme_documenta_todos_los_campos_del_frontmatter() -> None:
    """Un campo que se usa y no se documenta se rellena distinto cada vez."""
    texto = README.read_text(encoding="utf-8")
    faltan = [c for c in CAMPOS if f"{c}:" not in texto]
    assert not faltan, f"README.md no documenta los campos {faltan}"


def test_el_readme_declara_la_regla_de_que_se_pregunta() -> None:
    """Es la regla que el comando aplica sin copiarla: tiene que estar aquí."""
    texto = README.read_text(encoding="utf-8")
    assert "Qué se pregunta y qué no" in texto, (
        "README.md no declara la sección *Qué se pregunta y qué no*"
    )
    assert "grep" in texto, (
        "README.md no declara el filtro de que una respuesta encontrable con "
        "`grep` no es pregunta"
    )


def test_el_readme_prohibe_la_clave_dentro_del_examen() -> None:
    """Si la regla no está donde se lee el formato, se olvidará."""
    texto = README.read_text(encoding="utf-8")
    assert "La clave no se escribe nunca en el fichero" in texto, (
        "README.md no prohíbe escribir la clave dentro del examen"
    )


# --- El comando referencia, no copia --------------------------------------


def test_frontmatter_del_comando() -> None:
    campos = _frontmatter(COMANDO)
    assert campos.get("description"), "examen.md: `description` vacía o ausente"
    assert campos.get("argument-hint"), "examen.md: `argument-hint` vacío o ausente"


def test_el_comando_apunta_a_la_fuente_de_verdad() -> None:
    texto = COMANDO.read_text(encoding="utf-8")
    assert ".claude/examenes/README.md" in texto, (
        "examen.md no cita .claude/examenes/README.md"
    )
    assert "Qué se pregunta y qué no" in texto, (
        "examen.md no apunta a la sección que define qué se pregunta"
    )


def test_el_comando_no_copia_el_formato_ni_la_rubrica() -> None:
    """Copiados, formato y rúbrica divergen. Ya pasó tres veces con la 002."""
    texto = COMANDO.read_text(encoding="utf-8")
    assert "```yaml" not in texto, (
        "examen.md reproduce el bloque de frontmatter del README; referéncialo"
    )
    en_tabla = [v for v in ("a-medias", "correcta") if f"| `{v}` |" in texto]
    assert not en_tabla, (
        f"examen.md reproduce la tabla de rúbrica del README ({en_tabla})"
    )


def test_el_comando_no_copia_los_indices_de_los_otros_registros() -> None:
    texto = COMANDO.read_text(encoding="utf-8")
    assert not RE_FILA_INDICE.search(texto), (
        "examen.md reproduce filas del índice de trampas o de bitácora; cita ids"
    )


def test_frontera_declarada_con_los_otros_dos_comandos() -> None:
    """Tres comandos que interrogan se solapan si nadie dice dónde acaba cada uno."""
    texto = COMANDO.read_text(encoding="utf-8")
    for otro in ("/grill-me", "/encargo"):
        assert otro in texto, f"examen.md no declara su frontera con {otro}"


@pytest.mark.parametrize("comando", ["encargo.md", "grill-me.md"])
def test_los_otros_comandos_apuntan_de_vuelta(comando: str) -> None:
    """Sin la línea recíproca, /examen es indescubrible desde donde se necesita."""
    ruta = RAIZ / ".claude" / "commands" / comando
    assert "/examen" in ruta.read_text(encoding="utf-8"), (
        f"{comando} no menciona /examen"
    )


# --- Los exámenes escritos ------------------------------------------------


@pytest.mark.parametrize("ruta", EXAMENES_FICHEROS, ids=lambda p: p.name)
def test_frontmatter_completo_y_valido(ruta: Path) -> None:
    campos = _frontmatter(ruta)
    faltan = [c for c in CAMPOS if c not in campos]
    assert not faltan, f"{ruta.name}: faltan campos {faltan}"
    assert campos["id"] == ruta.name[:3], (
        f"{ruta.name}: `id` {campos['id']!r} no coincide con el nombre del fichero"
    )
    assert RE_FECHA.match(campos["fecha"]), (
        f"{ruta.name}: `fecha` no es YYYY-MM-DD: {campos['fecha']!r}"
    )
    assert campos["estado"] in ESTADOS, (
        f"{ruta.name}: `estado` {campos['estado']!r} fuera de {sorted(ESTADOS)}"
    )
    assert campos["ronda"] in {"1", "2"}, (
        f"{ruta.name}: `ronda` {campos['ronda']!r} — no hay ronda 3"
    )
    assert campos["fuentes"], f"{ruta.name}: `fuentes` vacío; la clave sale de ahí"


def test_ids_correlativos_sin_huecos() -> None:
    ids = [int(p.name[:3]) for p in EXAMENES_FICHEROS]
    assert ids == list(range(1, len(ids) + 1)), f"ids no correlativos desde 001: {ids}"


@pytest.mark.parametrize("ruta", EXAMENES_FICHEROS, ids=lambda p: p.name)
def test_cada_bloque_tiene_concepto_respuesta_y_veredicto(ruta: Path) -> None:
    bloques = _bloques(ruta)
    assert bloques, f"{ruta.name}: sin ninguna pregunta `## PN · …`"
    for i, bloque in enumerate(bloques, start=1):
        assert RE_CONCEPTO.search(bloque), (
            f"{ruta.name} P{i}: sin `<!-- concepto: kebab-case -->`"
        )
        assert "**Respuesta:**" in bloque, (
            f"{ruta.name} P{i}: sin hueco `**Respuesta:**`"
        )
        m = RE_VEREDICTO.search(bloque)
        assert m, f"{ruta.name} P{i}: sin línea `**Veredicto:**`"
        assert m.group(1).strip() in VEREDICTOS, (
            f"{ruta.name} P{i}: veredicto {m.group(1)!r} fuera de {sorted(VEREDICTOS)}"
        )


@pytest.mark.parametrize("ruta", EXAMENES_FICHEROS, ids=lambda p: p.name)
def test_ninguna_pregunta_se_numera_dos_veces(ruta: Path) -> None:
    numeros = RE_PREGUNTA.findall(ruta.read_text(encoding="utf-8"))
    assert len(numeros) == len(set(numeros)), (
        f"{ruta.name}: números de pregunta repetidos"
    )


@pytest.mark.parametrize("ruta", EXAMENES_FICHEROS, ids=lambda p: p.name)
def test_el_examen_no_lleva_la_clave_dentro(ruta: Path) -> None:
    """La guardia principal: clave escrita ⇒ se lee ⇒ el 100 % no mide nada."""
    m = RE_CLAVE.search(ruta.read_text(encoding="utf-8"))
    assert not m, (
        f"{ruta.name}: contiene {m.group(0)!r}; la clave no se escribe en el examen"
    )


# --- El registro de debilidades -------------------------------------------


def _filas_debilidades() -> list[list[str]]:
    filas = []
    for linea in DEBILIDADES.read_text(encoding="utf-8").splitlines():
        if not linea.startswith("|"):
            continue
        celdas = [c.strip() for c in linea.strip("|").split("|")]
        if celdas[0] in {"concepto", ""} or set(celdas[0]) <= {"-", ":"}:
            continue
        filas.append(celdas)
    return filas


def test_cabecera_de_debilidades() -> None:
    lineas = DEBILIDADES.read_text(encoding="utf-8").splitlines()
    cabeceras = [ln for ln in lineas if ln.startswith("| concepto")]
    assert cabeceras, "debilidades.md: sin fila de cabecera de la tabla"
    columnas = tuple(c.strip() for c in cabeceras[0].strip("|").split("|"))
    assert columnas == COLUMNAS_DEBILIDADES, (
        f"debilidades.md: columnas {columnas} ≠ {COLUMNAS_DEBILIDADES}"
    )


def test_ningun_concepto_del_registro_es_huerfano() -> None:
    """Un concepto que no salió de ningún examen no lo puso la corrección."""
    en_examenes = {
        c
        for p in EXAMENES_FICHEROS
        for c in RE_CONCEPTO.findall(p.read_text(encoding="utf-8"))
    }
    huerfanos = [f[0] for f in _filas_debilidades() if f[0] not in en_examenes]
    assert not huerfanos, (
        f"debilidades.md registra conceptos que no aparecen en ningún examen: {huerfanos}"
    )


def test_estados_del_registro_validos() -> None:
    invalidos = [
        (f[0], f[5]) for f in _filas_debilidades() if f[5] not in {"flojo", "dominado"}
    ]
    assert not invalidos, (
        f"debilidades.md: estados fuera de flojo|dominado: {invalidos}"
    )
