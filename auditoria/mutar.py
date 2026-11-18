"""Runner de la auditoría por mutación dirigida.

    uv run python auditoria/mutar.py                  # catálogo entero
    uv run python auditoria/mutar.py --solo 000 001   # algunos mutantes

Para cada mutante de `catalogo.toml`:

  1. lo aplica sobre un `git worktree` desechable creado desde HEAD,
  2. corre la suite de `tests/` contra el código mutado,
  3. si ningún test cae, corre sus sondas (`sondas.py`) con y sin mutante,
  4. restaura el fichero y pasa al siguiente.

El árbol de trabajo principal no se toca. Se exige `src/` y `tests/` limpios
respecto a HEAD: la auditoría habla de un commit, no de lo que haya en disco.

El worktree no tiene `.venv` propio. Se reutiliza el intérprete que ejecuta este
script, con `PYTHONPATH` apuntando a `<worktree>/src`, que precede al `.pth` del
paquete editable. El control de arranque comprueba que `import project` resuelve
al worktree: si no lo hiciera, se estarían probando los tests contra el código
sin mutar y todo saldría "no detectado".

Controles antes del catálogo:
  - suite de referencia sin mutar: todo `passed` o `xfailed`,
  - mutante nulo (`control = "nulo"`): ningún test cae y las sondas coinciden,
  - mutante positivo (`control = "positivo"`): lo detecta su detector.
Si un control falla, el runner se detiene y no clasifica nada más.

Antes de todo, cada `buscar` debe aparecer exactamente una vez en su fichero; si
no, sale con código 4 sin ejecutar nada (issue #11).

Salida: `auditoria/resultados/mutantes_<hash>.json`, con `completo: false` si la
ejecución se cortó, y una tabla por stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
TIMEOUT_SUITE_S = 900


def git(*args: str, cwd: Path = RAIZ) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def guardia_de_ficha(trampa: str) -> str | None:
    """El node id que la ficha de la trampa cita como guardia."""
    for ficha in (RAIZ / ".claude" / "trampas").glob(f"{trampa}-*.md"):
        m = re.search(r"^test:\s*(\S+)", ficha.read_text(encoding="utf-8"), re.M)
        if m and m.group(1) != "ninguno":
            return m.group(1)
    return None


def _sin_parametros(nodeid: str) -> str:
    return nodeid.split("[", 1)[0]


def correr_suite(wt: Path, env: dict) -> dict[str, str]:
    """node id -> passed | failed | error | skipped | xfailed | xpassed."""
    xml = wt / "_junit.xml"
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={xml}",
                "-o",
                "junit_family=xunit1",
            ],
            cwd=wt,
            env=env,
            # La salida no se usa: el resultado sale del junit. Leerla en la
            # codificación local (cp1252) podía cascar con la UTF-8 del hijo.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SUITE_S,
        )
    except subprocess.TimeoutExpired:
        return {"__timeout__": "failed"}
    resultado: dict[str, str] = {}
    if not xml.exists():
        return {"__sin_junit__": "failed"}
    for caso in ET.parse(xml).iter("testcase"):
        clase = caso.get("classname", "")
        nodeid = f"{clase.replace('.', '/')}.py::{caso.get('name')}"
        estado = "passed"
        for hijo in caso:
            if hijo.tag == "failure":
                estado = (
                    "xpassed" if "XPASS" in (hijo.get("message") or "") else "failed"
                )
            elif hijo.tag == "error":
                estado = "error"
            elif hijo.tag == "skipped":
                tipo = hijo.get("type", "")
                estado = "xfailed" if "xfail" in tipo else "skipped"
        resultado[nodeid] = estado
    xml.unlink()
    return resultado


def correr_sondas(wt: Path, env: dict, nombres: list[str]) -> dict[str, str]:
    if not nombres:
        return {}
    r = subprocess.run(
        [sys.executable, str(wt / "auditoria" / "sondas.py"), *nombres],
        cwd=wt,
        env=env,
        capture_output=True,
        encoding="utf-8",  # la del hijo, por PYTHONIOENCODING
        timeout=TIMEOUT_SUITE_S,
    )
    salida = dict(
        linea.split("=", 1) for linea in r.stdout.splitlines() if "=" in linea
    )
    for n in nombres:
        salida.setdefault(n, f"SIN_SALIDA:{r.returncode}")
    return salida


def _saltos(texto: str, s: str) -> str:
    """`s` con el salto de línea de `texto`: el catálogo usa \\n, el fichero quizá CRLF."""
    return s.replace("\n", "\r\n" if "\r\n" in texto else "\n")


def invalidos(catalogo: list[dict], raiz: Path) -> list[tuple[str, int]]:
    """(id, apariciones) de los mutantes cuyo `buscar` no sale exactamente una vez.

    El catálogo se ata al código solo por texto: basta un commit que repita o
    reescriba la línea para que el mutante deje de aplicarse (issue #11). Un
    fichero que ya no existe cuenta como cero apariciones.
    """
    malos = []
    for m in catalogo:
        ruta = raiz / m["fichero"]
        texto = ruta.read_bytes().decode("utf-8") if ruta.exists() else ""
        n = texto.count(_saltos(texto, m["buscar"]))
        if n != 1:
            malos.append((m["id"], n))
    return malos


def aplicar(wt: Path, m: dict) -> tuple[Path, bytes]:
    """Aplica el mutante. Devuelve (fichero, bytes originales).

    `main` ya ha comprobado con `invalidos` que el `buscar` sale una sola vez.
    """
    ruta = wt / m["fichero"]
    original = ruta.read_bytes()
    texto = original.decode("utf-8")
    mutado = texto.replace(_saltos(texto, m["buscar"]), _saltos(texto, m["reemplazar"]))
    ruta.write_bytes(mutado.encode("utf-8"))
    return ruta, original


def clasificar(
    m: dict,
    base: dict[str, str],
    mut: dict[str, str],
    sondas_base: dict[str, str],
    sondas_mut: dict[str, str],
) -> dict:
    caidos = sorted(
        n
        for n, e in mut.items()
        if e in ("failed", "error", "xpassed")
        and base.get(n) in ("passed", "xfailed", None)
    )
    caidos_sin_param = sorted({_sin_parametros(n) for n in caidos})
    esperados = m.get("detector", [])
    guardia = guardia_de_ficha(m["trampa"]) if m.get("trampa") else None

    if caidos:
        veredicto = "detectado"
    elif any(
        sondas_mut.get(k) != v
        for k, v in sondas_base.items()
        if k in m.get("sondas", [])
    ):
        veredicto = "hueco"
    else:
        veredicto = "equivalente"

    return {
        "id": m["id"],
        "nombre": m["nombre"],
        "capa": m["capa"],
        "trampa": m.get("trampa"),
        "veredicto": veredicto,
        "caidos": caidos_sin_param,
        "n_caidos": len(caidos),
        "esperados": esperados,
        "esperado_cae": all(e in caidos_sin_param for e in esperados)
        if esperados
        else None,
        "guardia_ficha": guardia,
        "guardia_ficha_cae": (guardia in caidos_sin_param) if guardia else None,
        "sondas": {
            k: [sondas_base.get(k), sondas_mut.get(k)] for k in m.get("sondas", [])
        },
    }


def main(solo: list[str] | None) -> int:
    # Redirigido a fichero o tubería, stdout en Windows es cp1252 y no tiene la
    # «τ» de algunos nombres: el print abortaba a mitad (issue #3).
    sys.stdout.reconfigure(encoding="utf-8")
    # Solo cuentan los ficheros con seguimiento: uno nuevo sin commitear no está
    # en el worktree y no puede alterar lo que se audita.
    sucio = git("status", "--porcelain", "--untracked-files=no", "--", "src", "tests")
    if sucio:
        print(
            "src/ o tests/ tienen cambios sin commitear: la auditoría habla de un commit."
        )
        print(sucio)
        return 2
    rev = git("rev-parse", "--short", "HEAD")
    catalogo = tomllib.loads((AQUI / "catalogo.toml").read_text(encoding="utf-8"))[
        "mutante"
    ]
    if solo:
        # Un id mal escrito dejaría solo los controles, en verde.
        if desconocidos := set(solo) - {m["id"] for m in catalogo}:
            print(f"--solo con ids que no están en el catálogo: {sorted(desconocidos)}")
            return 4
        catalogo = [m for m in catalogo if m["id"] in solo or m.get("control")]
    # Un mutante que no se aplica no mide nada: saltárselo y salir con 0 haría
    # pasar por auditada una guardia sin evidencia (issue #11).
    malos = invalidos(catalogo, RAIZ)
    if malos:
        print("MUTANTES INVÁLIDOS: su buscar no aparece una sola vez en HEAD.")
        for id_, n in malos:
            print(f"  {id_}: {n} apariciones")
        return 4

    wt = Path(tempfile.mkdtemp(prefix="tfm-mutar-"))
    shutil.rmtree(wt)
    git("worktree", "add", "--detach", str(wt), "HEAD")
    # El catálogo y las sondas se usan en su versión actual aunque no estén en HEAD.
    shutil.copytree(
        AQUI,
        wt / "auditoria",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("resultados", "__pycache__"),
    )
    env = {**os.environ, "PYTHONPATH": str(wt / "src"), "PYTHONIOENCODING": "utf-8"}
    resultados: list[dict] = []
    completo = False
    t0 = time.time()
    try:
        donde = subprocess.run(
            [sys.executable, "-c", "import project; print(project.__file__)"],
            cwd=wt,
            env=env,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not Path(donde).resolve().is_relative_to(wt.resolve()):
            print(
                f"CONTROL FALLIDO: `import project` resuelve a {donde}, no al worktree."
            )
            return 3
        print(f"  worktree {wt} @ {rev}; project -> {donde}")

        base = correr_suite(wt, env)
        malos = {n: e for n, e in base.items() if e not in ("passed", "xfailed")}
        print(f"  referencia: {len(base)} tests, fuera de passed/xfailed: {len(malos)}")
        if malos or not base:
            print(f"CONTROL FALLIDO: la suite sin mutar no está verde: {malos}")
            return 3
        nombres_sondas = sorted({s for m in catalogo for s in m.get("sondas", [])})
        sondas_base = correr_sondas(wt, env, nombres_sondas)
        print(f"  sondas de referencia: {sondas_base}")
        if any(v.startswith(("EXCEPCION", "SIN_SALIDA")) for v in sondas_base.values()):
            print("CONTROL FALLIDO: una sonda revienta sin mutar.")
            return 3

        orden = sorted(catalogo, key=lambda m: (m.get("control") is None, m["id"]))
        for m in orden:
            t = time.time()
            ruta, original = aplicar(wt, m)
            try:
                mut = correr_suite(wt, env)
                cayo = any(e in ("failed", "error", "xpassed") for e in mut.values())
                # Las sondas solo se necesitan si nada cae, y en los controles.
                sm = (
                    correr_sondas(wt, env, m.get("sondas", []))
                    if (not cayo or m.get("control"))
                    else {}
                )
            finally:
                ruta.write_bytes(original)
            r = clasificar(m, base, mut, sondas_base, sm)
            r["segundos"] = round(time.time() - t, 1)
            resultados.append(r)
            print(
                f"  {r['id']} {r['veredicto']:<12} {r.get('n_caidos', 0):>3} caídos  "
                f"{r['segundos']:>6}s  {m['nombre']}",
                flush=True,
            )

            if m.get("control") == "nulo" and r["veredicto"] != "equivalente":
                print("CONTROL FALLIDO: el mutante nulo cambia algo.")
                return 3
            if m.get("control") == "positivo" and not r.get("esperado_cae"):
                print("CONTROL FALLIDO: el mutante positivo no lo detecta su detector.")
                return 3
        completo = True
    finally:
        git("worktree", "remove", "--force", str(wt))
        destino = AQUI / "resultados" / f"mutantes_{rev}.json"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(
            json.dumps(
                {
                    "rev": rev,
                    # False si se cortó: un control fallido o una excepción
                    # dejan aquí solo los mutantes que dio tiempo a correr.
                    "completo": completo,
                    # La auditoría entera es `solo: null`; con ids, un subconjunto.
                    "solo": solo or None,
                    "segundos": round(time.time() - t0),
                    "mutantes": resultados,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n  resultados -> {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--solo", nargs="*", default=None)
    raise SystemExit(main(p.parse_args().solo))
