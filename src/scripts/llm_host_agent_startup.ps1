# Registers (or with -Remove deletes) the logon task that runs the LLM host agent.
#
# The agent (llm_host_agent.py) measures RAM/VRAM, runs `coli plan` and starts or stops the
# Colibri server, stops, starts or unloads the host Ollama, and starts, pauses or stops the
# knowledge build (scripts.build_knowledge, in the repository's .venv), when the app or the
# orchestrator asks; it loads no model itself. The task runs it with the system
# Python's pythonw.exe (no console window) for the current user, without administrator rights.
# The project's .venv Python cannot write under C:\Colibri, the system Python can.
#
#   powershell -ExecutionPolicy Bypass -File src\scripts\llm_host_agent_startup.ps1
#   powershell -ExecutionPolicy Bypass -File src\scripts\llm_host_agent_startup.ps1 -Remove

[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$Python = "C:\Program Files\Python311\pythonw.exe",
    [string]$AgentArguments = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "medicina-llm-host-agent"
$Agent = Join-Path $PSScriptRoot "llm_host_agent.py"

# medicina-colibri-agent is this task's former name; its agent would keep port 8011.
foreach ($name in @($TaskName, "medicina-colibri-agent")) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
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
    -Description "LLM host agent for medicina-naturista (port 8011)" | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "Registered and started the logon task $TaskName."
