"""Detecta deriva entre la documentación y el código.

La memoria del proyecto ya ha mentido tres veces sobre lo mismo: `CLAUDE.md`,
`docs/00` y los prompts de los agentes describían la trampa horaria como un desfase
fijo cuando la fuente alterna de convención entre sondeos. Nadie lo vio porque
nada lo comprobaba.

Estas comprobaciones son deliberadamente **estrechas**. Un verificador ambicioso
("¿todo lo que dice la doc es verdad?") produce sobre todo falsos positivos, y un
test con ruido se acaba ignorando, que es peor que no tenerlo. Aquí solo entran
afirmaciones cuya falsedad es inequívoca.

Lo que exige juicio — comportamiento descrito que el código contradice, decisiones
de `docs/07` que el código ya no respeta — vive en el comando `/sincronizar`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOCS = sorted((RAIZ / "docs").glob("*.md"))
# Las fichas de trampas citan funciones y ficheros igual que la documentación, y
# rotan igual: la 002 apunta a `resolver_convencion()`.
TRAMPAS = sorted((RAIZ / ".claude" / "trampas").glob("*.md"))
MEMORIA = [RAIZ / "CLAUDE.md", *DOCS, *TRAMPAS]

# Rutas: separador Y extensión de fichero del repo. Ambas condiciones son
# necesarias, medido sobre esta documentación:
#   - sin extensión entran identificadores de capa ArcGIS (`OPENDATA/Trafico/192`),
#     directorios relativos a otra raíz (`api/`, `services/`), referencias
#     abreviadas (`docs/00`) y slugs de GitHub. Siete falsos positivos, cero
#     hallazgos reales.
#   - sin separador entra cualquier nombre suelto en prosa (`main.py`).
EXTENSIONES = ("py", "yaml", "yml", "toml", "json", "md", "sh", "cfg", "txt")
RE_RUTA = re.compile(r"`((?:[\w.-]+/)+[\w.-]+\.(?:" + "|".join(EXTENSIONES) + r"))`")
RE_FUNCION = re.compile(r"`(\w+)\(\)`")
RE_UV_MODULO = re.compile(r"uv run python -m ([\w.]+)")

# Rutas que la documentación cita como destino futuro, no como hecho presente.
FUTURAS = {"src/project/ingest/"}


def _texto(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _sin_bloques_de_codigo(texto: str) -> str:
    """Los ejemplos de bloque pueden citar cosas que no existen a propósito."""
    return re.sub(r"```.*?```", "", texto, flags=re.DOTALL)


@pytest.mark.parametrize("doc", MEMORIA, ids=lambda p: p.name)
def test_las_rutas_citadas_existen(doc: Path):
    faltan = []
    for ruta in set(RE_RUTA.findall(_texto(doc))):
        if ruta in FUTURAS or ruta.startswith(("http", "data/", "models/")):
            # data/ y models/ los produce el pipeline y los versiona DVC: que no
            # estén en el árbol es lo normal, no deriva.
            continue
        # Tres raíces legítimas: el repo, el directorio del documento
        # (`../CLAUDE.md` desde docs/) y el paquete — la sección de arquitectura
        # nombra los módulos relativos a `src/project/`, igual que el diagrama.
        raices = (RAIZ, doc.parent, RAIZ / "src" / "project")
        if not any((r / ruta).exists() for r in raices):
            faltan.append(ruta)
    assert not faltan, f"{doc.name} cita rutas que no existen: {sorted(faltan)}"


@pytest.mark.parametrize("doc", MEMORIA, ids=lambda p: p.name)
def test_las_funciones_citadas_existen(doc: Path):
    """`resolver_convencion()` es la razón de este test: si se renombra, la ficha
    002 y tres documentos pasan a apuntar a nada sin que nadie se entere."""
    fuentes = " ".join(
        _texto(p)
        for p in [*(RAIZ / "demo").glob("*.py"), *(RAIZ / "src").rglob("*.py")]
    )
    faltan = [
        f
        for f in set(RE_FUNCION.findall(_sin_bloques_de_codigo(_texto(doc))))
        if f"def {f}(" not in fuentes
    ]
    assert not faltan, f"{doc.name} cita funciones que no existen: {sorted(faltan)}"


def test_los_stages_de_dvc_son_los_documentados():
    dvc = _texto(RAIZ / "dvc.yaml")
    declarados = set(re.findall(r"^  (\w+):$", dvc, re.MULTILINE))
    documentados = {"prepare", "features", "train", "evaluate"}
    assert declarados == documentados, (
        f"dvc.yaml declara {sorted(declarados)}, la documentación describe "
        f"{sorted(documentados)}. Actualiza CLAUDE.md o dvc.yaml."
    )


def test_cada_stage_tiene_su_clave_de_params():
    """`params:` de un stage debe existir en params.yaml o DVC no lo reejecuta."""
    dvc = _texto(RAIZ / "dvc.yaml")
    params = _texto(RAIZ / "params.yaml")
    claves = set(re.findall(r"^      - (\w+)$", dvc, re.MULTILINE))
    faltan = [c for c in claves if not re.search(rf"^{c}:$", params, re.MULTILINE)]
    assert not faltan, f"dvc.yaml referencia params inexistentes: {sorted(faltan)}"


def test_los_modulos_de_los_stages_existen_o_estan_declarados_vacios():
    """Un stage puede apuntar a un módulo aún sin escribir — eso es legítimo — pero
    el fichero tiene que existir, o `dvc repro` falla con ImportError en vez de con
    un error útil."""
    faltan = []
    for modulo in RE_UV_MODULO.findall(_texto(RAIZ / "dvc.yaml")):
        destino = RAIZ / "src" / Path(*modulo.split(".")).with_suffix(".py")
        if not destino.exists():
            faltan.append(modulo)
    assert not faltan, f"dvc.yaml invoca módulos que no existen: {sorted(faltan)}"


def test_las_dependencias_pendientes_lo_siguen_estando():
    """CLAUDE.md lista deps 'todavía por añadir'. Cuando se añaden, la lista miente."""
    m = re.search(
        r"Dependencias todavía por añadir: (.+?)\.\n",
        _texto(RAIZ / "CLAUDE.md"),
        re.DOTALL,
    )
    if not m:
        pytest.skip("CLAUDE.md ya no declara dependencias pendientes")
    pendientes = set(re.findall(r"`([\w-]+)`", m.group(1)))
    pyproject = _texto(RAIZ / "pyproject.toml")
    ya_estan = [d for d in pendientes if re.search(rf'"{d}[>=~\[",]', pyproject)]
    assert not ya_estan, (
        f"CLAUDE.md dice que faltan {sorted(ya_estan)}, pero ya están en "
        "pyproject.toml. Quítalas de la lista."
    )


def test_no_se_afirma_que_un_fichero_vacio_cubre_algo():
    """La deriva encontrada el 31/08/2026: CLAUDE.md decía que
    `tests/test_features.py` cubría las transformaciones, y tenía 0 líneas."""
    problemas = []
    for doc in MEMORIA:
        for linea in _sin_bloques_de_codigo(_texto(doc)).splitlines():
            for ruta in RE_RUTA.findall(linea):
                destino = RAIZ / ruta
                if not destino.is_file() or destino.stat().st_size > 0:
                    continue
                if re.search(
                    r"\b(está vacío|se escribirá|por escribir|pendiente)", linea
                ):
                    continue
                if re.search(
                    r"\b(cubre|valida|verifica|implementa|contiene|mantiene)\b", linea
                ):
                    problemas.append(
                        f"{doc.name}: {ruta} está vacío — {linea.strip()[:70]}"
                    )
    assert not problemas, "afirmaciones sobre ficheros vacíos:\n  " + "\n  ".join(
        problemas
    )
