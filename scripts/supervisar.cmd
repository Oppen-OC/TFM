@echo off
REM Envoltorio para poder lanzar el supervisor desde cmd.exe.
REM
REM En cmd, escribir  .\scripts\supervisar.ps1  NO ejecuta el script: abre el
REM archivo con el programa asociado a .ps1 (normalmente VS Code o el Bloc de
REM notas). Este .cmd invoca PowerShell explícitamente.
REM
REM Uso:
REM   scripts\supervisar.cmd -Modo Detach
REM   scripts\supervisar.cmd -Modo Estado
REM   scripts\supervisar.cmd -Modo Parar
REM   scripts\supervisar.cmd -Modo Tarea      (requiere consola de administrador)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0supervisar.ps1" %*
