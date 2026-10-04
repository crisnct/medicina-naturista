param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Query,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$arguments = @('-m', 'backend.ai.search', $Query)
if ($Json) { $arguments += '--json' }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
