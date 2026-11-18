"""El catálogo de mutantes se ata al código solo por texto (issue #11).

Un mutante cuyo `buscar` no aparece exactamente una vez no se aplica: no mide
nada, y la guardia que debía probar se queda sin evidencia. Pasa sin tocar el
catálogo, con que un commit repita o reescriba esa línea en el mismo fichero.
Así se perdieron 4 de 241, el 027 y el 033 sobre el crudo antes del parser.

Vive aquí y no en `tests/` porque `mutar.py` corre `tests/` sobre el código
mutado: un `buscar` sustituido haría caer este test con cada mutante, y todos
saldrían detectados.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("mutar", RAIZ / "auditoria" / "mutar.py")
mutar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mutar)


def test_todo_buscar_del_catalogo_aparece_una_sola_vez():
    catalogo = tomllib.loads(
        (RAIZ / "auditoria" / "catalogo.toml").read_text(encoding="utf-8")
    )["mutante"]
    assert mutar.invalidos(catalogo, RAIZ) == []


def test_un_buscar_repetido_o_ausente_se_detecta(tmp_path):
    # CRLF a propósito: `aplicar` adapta el salto de línea del `buscar` al fichero.
    (tmp_path / "m.py").write_bytes(b"a = 1\r\nb = 2\r\na = 1\r\n")
    catalogo = [
        {"id": "uno", "fichero": "m.py", "buscar": "b = 2\na = 1"},
        {"id": "dos", "fichero": "m.py", "buscar": "a = 1"},
        {"id": "cero", "fichero": "m.py", "buscar": "c = 3"},
    ]
    assert mutar.invalidos(catalogo, tmp_path) == [("dos", 2), ("cero", 0)]
