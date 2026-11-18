<#
.SYNOPSIS
    Registra a tarefa agendada diária do Robô RevTributaria no Agendador de Tarefas do Windows.
.DESCRIPTION
    Executa diariamente às 02:00: catálogo oficial + sincronização bases oficiais + Vigia Noturno + Validador de NCMs.
#>
param(
    [string]$Horario = "02:00",
    [string]$NomeTarefa = "RevTributaria_Robo_Diario"
)

$RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = (Get-Command python -ErrorAction Stop).Source
$LogDir = Join-Path $RepoDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "robo_diario.log"

$Cmd = "`"$PythonExe`" -m src.automation.sync_job --db `"$RepoDir\revtributaria.db`" --uf-origem SP >> `"$LogFile`" 2>&1"
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $Cmd" -WorkingDirectory $RepoDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $Horario
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $NomeTarefa -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "Tarefa '$NomeTarefa' agendada diariamente às $Horario. Log: $LogFile"
