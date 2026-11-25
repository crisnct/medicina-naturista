# Registers (or with -Remove deletes) the logon task that runs the Colibri host agent.
#
# The agent (colibri_host_agent.py) measures RAM/VRAM, runs `coli plan` and starts or stops the
# Colibri server when the app asks; it loads no model itself. The task runs it with the system
# Python's pythonw.exe (no console window) for the current user, without administrator rights.
# The project's .venv Python cannot write under C:\Colibri, the system Python can.
#
#   powershell -ExecutionPolicy Bypass -File src\scripts\colibri_agent_startup.ps1
#   powershell -ExecutionPolicy Bypass -File src\scripts\colibri_agent_startup.ps1 -Remove

[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$Python = "C:\Program Files\Python311\pythonw.exe",
    [string]$AgentArguments = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "medicina-colibri-agent"
$Agent = Join-Path $PSScriptRoot "colibri_host_agent.py"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
if ($Remove) {
    Write-Output "Removed the logon task $TaskName."
    return
}

if (-not (Test-Path $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path $Agent)) { throw "Agent not found: $Agent" }

$action = New-ScheduledTaskAction -Execute $Python -Argument ("`"$Agent`" " + $AgentArguments).Trim()
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# No time limit, a restart if it crashes, and it also runs on battery: the agent is idle almost
# always and only reacts to the app's requests.
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Colibri host agent for medicina-naturista (port 8011)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "Registered and started the logon task $TaskName."
