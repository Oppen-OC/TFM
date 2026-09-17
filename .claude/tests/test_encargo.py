"""Validación mecánica de la maquinaria de encargos (`/encargo` + `CLAUDE.md`).

La lista de dimensiones vive en la sección *Encargos incompletos* de `CLAUDE.md` y
en ningún otro sitio. Es exactamente el tipo de contenido que ya divergió tres
veces con la trampa 002: útil, corto y tentador de copiar. Estas comprobaciones
impiden la copia y la deriva.

Lo que exige juicio (si el comando sigue preguntando lo que importa, si las ocho
dimensiones siguen siendo las que muerden) no se comprueba aquí.

Sin dependencias nuevas: frontmatter `clave: valor` plano, parseado con regex.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CLAUDE_MD = RAIZ / "CLAUDE.md"
ENCARGO = RAIZ / ".claude" / "commands" / "encargo.md"
GRILL_ME = RAIZ / ".claude" / "commands" / "grill-me.md"

SECCION = "## Encargos incompletos"

# Las dimensiones se declaran como `- **clave** — glosa` dentro de la sección.
RE_DIMENSION = re.compile(r"^- \*\*([a-z]+)\*\* — ", re.MULTILINE)
RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
RE_CAMPO = re.compile(r"^([a-z-]+):\s*(.*)$")

DIMENSIONES_ESPERADAS = {
    "dato",
    "alcance",
    "acoplamiento",
    "temporalidad",
    "evidencia",
    "frontera",
    "trampa",
    "entrega",
}


def _seccion_encargos() -> str:
    texto = CLAUDE_MD.read_text(encoding="utf-8")
    assert SECCION in texto, f"CLAUDE.md: falta la sección {SECCION!r}"
    cuerpo = texto.split(SECCION, 1)[1]
    # Hasta el siguiente encabezado de nivel 2, o el final del fichero.
    return re.split(r"^## ", cuerpo, maxsplit=1, flags=re.MULTILINE)[0]


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


def test_claude_md_declara_las_ocho_dimensiones() -> None:
    """La lista es la fuente de verdad: si cambia, este test se cambia a mano."""
    declaradas = set(RE_DIMENSION.findall(_seccion_encargos()))
    assert declaradas == DIMENSIONES_ESPERADAS, (
        "las dimensiones de CLAUDE.md ya no coinciden con las esperadas; "
        f"sobran {declaradas - DIMENSIONES_ESPERADAS}, "
        f"faltan {DIMENSIONES_ESPERADAS - declaradas}"
    )


def test_el_comando_no_copia_la_lista() -> None:
    """Copiada, la lista diverge. El comando la referencia; no la reproduce."""
    copiadas = set(RE_DIMENSION.findall(ENCARGO.read_text(encoding="utf-8")))
    assert not copiadas, (
        "encargo.md reproduce dimensiones de CLAUDE.md como lista propia "
        f"({sorted(copiadas)}); referénciala en lugar de copiarla"
    )


def test_el_comando_apunta_a_la_fuente_de_verdad() -> None:
    """Sin el puntero, quien lea el comando no sabe dónde está la lista."""
    texto = ENCARGO.read_text(encoding="utf-8")
    assert "Encargos incompletos" in texto and "CLAUDE.md" in texto, (
        "encargo.md no cita la sección *Encargos incompletos* de CLAUDE.md"
    )


def test_frontera_declarada_en_los_dos_comandos() -> None:
    """`/encargo` y `/grill-me` se solapan si nadie dice dónde acaba cada uno."""
    assert "/grill-me" in ENCARGO.read_text(encoding="utf-8"), (
        "encargo.md no declara su frontera con /grill-me"
    )
    assert "/encargo" in GRILL_ME.read_text(encoding="utf-8"), (
        "grill-me.md no declara su frontera con /encargo"
    )


def test_frontmatter_de_encargo() -> None:
    campos = _frontmatter(ENCARGO)
    assert campos.get("description"), "encargo.md: `description` vacía o ausente"
    assert campos.get("argument-hint"), "encargo.md: `argument-hint` vacío o ausente"


def test_claude_md_declara_que_la_lista_no_se_duplica() -> None:
    """La regla anti-copia tiene que estar escrita donde se lee la lista."""
    cuerpo = _seccion_encargos()
    assert "solo aquí" in cuerpo, (
        "CLAUDE.md: la sección no dice que la lista vive en un único sitio"
    )
