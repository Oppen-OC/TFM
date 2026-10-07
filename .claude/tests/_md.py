"""Frontmatter `clave: valor` plano de los registros del andamiaje.

Regex y no YAML, a propósito: YAML leería `id: 001` como el entero 1 y una
fecha como `date`, y los tests comparan texto. Cada registro pasa su propio
patrón de clave (unos admiten guion, otros no).
"""

from __future__ import annotations

import re
from pathlib import Path

RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def frontmatter(ruta: Path, campo: re.Pattern[str]) -> dict[str, str]:
    m = RE_FRONTMATTER.match(ruta.read_text(encoding="utf-8"))
    assert m, f"{ruta.name}: sin frontmatter delimitado por ---"
    campos: dict[str, str] = {}
    for linea in m.group(1).splitlines():
        if not linea.strip():
            continue
        c = campo.match(linea)
        assert c, f"{ruta.name}: línea de frontmatter no es `clave: valor`: {linea!r}"
        campos[c.group(1)] = c.group(2).strip()
    return campos
