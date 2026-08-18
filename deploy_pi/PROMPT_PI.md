# Prompt de traspaso para la sesión de Claude en la Raspberry Pi

Copia y pega esto tal cual en la sesión que tienes abierta en la Pi, **después**
de haber hecho `git push` desde Windows.

---

```
Voy a instalar en esta Raspberry Pi el colector de datos de mi TFM (máster de
Big Data). Captura datos abiertos de movilidad de València cada 30 s y tiene que
correr sin parar durante meses.

Contexto: clona https://github.com/Oppen-OC/TFM.git rama develop en ~/TFM y lee
antes de tocar nada:
  - deploy_pi/PASOS.md          -> el procedimiento paso a paso
  - deploy_pi/README.md         -> por qué el servicio está configurado así
  - CLAUDE.md                   -> reglas del repo y trampas de los datos
  - docs/00_tema_y_alcance.md   -> qué es el proyecto y en qué punto está

Objetivo:
  1. Clonar el repo.
  2. Preparar la memoria USB externa que acabo de conectar y montarla de forma
     permanente en /srv/tfm-data. Hay un script con guardas:
     deploy_pi/preparar_disco.sh
  3. Instalar el colector como servicio systemd:
     sudo env DATOS=/srv/tfm-data bash deploy_pi/instalar.sh
  4. Verificar que captura: systemctl status tfm-colector, y luego
     /opt/tfm/.venv/bin/python /opt/tfm/demo/collect.py --status --out /srv/tfm-data
     Debe decir VIVO y con filas subiendo en las cinco fuentes.

REGLAS:
  - El paso de formatear BORRA un disco entero. Ejecuta primero
    `sudo bash deploy_pi/preparar_disco.sh` SIN argumentos, enséñame la lista de
    discos y PÁRATE. Yo te confirmo cuál es antes de que formatees nada.
  - Los datos NO pueden ir a la tarjeta SD: esta Pi sirve el DNS de casa con
    Pi-hole y una captura continua de meses la desgasta.
  - El colector no debe competir con Pi-hole. El fichero .service ya trae
    Nice, IOSchedulingClass=idle y MemoryMax; no lo relajes.
  - Comprueba que `timedatectl` dice synchronized: yes. El parseo de timestamps
    depende de que el reloj esté bien.
  - Comprueba que `dpkg --print-architecture` dice arm64. En armhf las
    dependencias dan problemas.

Cuando termine la instalación, dime cuánto ocupa /srv/tfm-data y qué cadencia
real está consiguiendo cada fuente.
```

---

## Después, desde Windows

Traer lo ya capturado en el portátil, para no perderlo:

```powershell
.\demo\supervisar.ps1 -Modo Parar
scp -r C:\Users\oppen\Code\TFM\data\raw <usuario>@<ip>:/srv/tfm-data/
```

Y en la Pi, reconstruir `curated/` con el parser actual:

```bash
cd /opt/tfm && sudo -u $USER .venv/bin/python demo/reprocesar.py --data /srv/tfm-data
```
