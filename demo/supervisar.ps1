<#
.SYNOPSIS
    Lanza, supervisa y consulta el colector del TFM en Windows.

.DESCRIPTION
    Tres modos, de menos a más duradero:

      -Modo Detach     el colector sobrevive al cierre del terminal, pero no
                       al reinicio de Windows. Vale para la prueba de 24 h.

      -Modo Tarea      lo registra en el Programador de tareas: arranca solo
                       al iniciar sesión y se reintenta si falla. Es lo que
                       necesitas para capturar durante meses.

      -Modo Estado     muestra el latido. No toca el proceso.
      -Modo Parar      lo detiene.

.EXAMPLE
    .\demo\supervisar.ps1 -Modo Detach
    .\demo\supervisar.ps1 -Modo Estado
    .\demo\supervisar.ps1 -Modo Tarea
    .\demo\supervisar.ps1 -Modo Parar

.NOTES
    Lánzalo desde la raíz del repo. Para el modo Tarea hace falta una consola
    de PowerShell como administrador.
#>
[CmdletBinding()]
param(
    [ValidateSet('Detach', 'Tarea', 'Estado', 'Parar')]
    [string]$Modo = 'Estado',
    [int]$Minutos = 0,
    [string]$NombreTarea = 'TFM-ColectorValencia'
)

$ErrorActionPreference = 'Stop'
$Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Python: primero el entorno activado, luego el .venv del repo, y sólo como
# último recurso el del sistema (que no tendrá las dependencias instaladas).
$Candidatos = @(
    $(if ($env:VIRTUAL_ENV) { Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe' }),
    (Join-Path $Raiz '.venv\Scripts\python.exe'),
    $(if (Get-Command python -ErrorAction SilentlyContinue) { (Get-Command python).Source })
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $Candidatos) {
    Write-Host "No encuentro ningún Python. Crea el entorno con 'uv sync'." -ForegroundColor Red
    exit 1
}
$Python = $Candidatos[0]

# Comprobación temprana: un colector lanzado con el Python equivocado muere en
# silencio en segundo plano y te enteras al día siguiente.
& $Python -c "import httpx, pandas, pyarrow" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ese Python no tiene las dependencias:" -ForegroundColor Red
    Write-Host "  $Python`n"
    Write-Host "Instálalas con:  uv add httpx pandas pyarrow scipy duckdb"
    Write-Host "o activa el entorno:  .\.venv\Scripts\Activate.ps1"
    exit 1
}

$Script  = Join-Path $Raiz 'demo\collect.py'
$LogDir  = Join-Path $Raiz 'data\logs'
$Log     = Join-Path $LogDir 'colector.log'
$PidFile = Join-Path $Raiz 'data\colector.pid'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-ColectorPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $procId = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $procId) { return $null }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($p) { return [int]$procId }
    return $null
}

switch ($Modo) {

    'Detach' {
        if (Get-ColectorPid) {
            Write-Host "Ya hay un colector corriendo (PID $(Get-ColectorPid))." -ForegroundColor Yellow
            Write-Host "Detenlo antes con:  .\demo\supervisar.ps1 -Modo Parar"
            break
        }
        Write-Host "Python : $Python"
        Write-Host "Log    : $Log"
        $proc = Start-Process -FilePath $Python `
            -ArgumentList @($Script, '--minutes', $Minutos, '--log', $Log) `
            -WorkingDirectory $Raiz -WindowStyle Hidden -PassThru
        $proc.Id | Set-Content $PidFile
        Write-Host "`nColector arrancado en segundo plano. PID $($proc.Id)." -ForegroundColor Green
        Write-Host "Ya puedes cerrar este terminal.`n"
        Write-Host "  Ver estado :  .\demo\supervisar.ps1 -Modo Estado"
        Write-Host "  Ver log    :  Get-Content '$Log' -Tail 20 -Wait"
        Write-Host "  Parar      :  .\demo\supervisar.ps1 -Modo Parar"
        Write-Host "`nOJO: esto NO sobrevive a un reinicio de Windows." -ForegroundColor Yellow
        Write-Host "Para capturar durante meses usa:  -Modo Tarea"
    }

    'Tarea' {
        $accion = New-ScheduledTaskAction -Execute $Python `
            -Argument "`"$Script`" --minutes 0 --log `"$Log`"" `
            -WorkingDirectory $Raiz
        $disparador = New-ScheduledTaskTrigger -AtLogOn
        $ajustes = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 2) `
            -ExecutionTimeLimit (New-TimeSpan -Days 0) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $NombreTarea -Action $accion `
            -Trigger $disparador -Settings $ajustes -Force | Out-Null
        Start-ScheduledTask -TaskName $NombreTarea
        Write-Host "Tarea '$NombreTarea' registrada y arrancada." -ForegroundColor Green
        Write-Host "  Arranca sola al iniciar sesión y se reintenta cada 2 min si falla."
        Write-Host "  Quitarla:  Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:`$false"
        Write-Host "`nRevisa ADEMÁS que el equipo no se suspenda:" -ForegroundColor Yellow
        Write-Host "  powercfg /change standby-timeout-ac 0"
        Write-Host "  powercfg /change hibernate-timeout-ac 0"
    }

    'Estado' {
        & $Python $Script --status --out (Join-Path $Raiz 'data')
        $procId = Get-ColectorPid
        if ($procId) { Write-Host "  Proceso suelto vivo: PID $procId" }
        $t = Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
        if ($t) { Write-Host "  Tarea programada '$NombreTarea': $($t.State)" }
    }

    'Parar' {
        $procId = Get-ColectorPid
        if ($procId) {
            Stop-Process -Id $procId -Force
            Remove-Item $PidFile -ErrorAction SilentlyContinue
            Write-Host "Colector detenido (PID $procId)." -ForegroundColor Green
        } else {
            Write-Host "No hay proceso suelto en marcha."
        }
        $t = Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
        if ($t) {
            Stop-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
            Write-Host "Tarea programada detenida (sigue registrada)."
        }
    }
}
