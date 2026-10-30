param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Query,
    [switch]$Json,
    [ValidateSet("ro", "en")]
    [string]$Language = "ro"
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$arguments = @('-m', 'backend.ai.search', $Query, '--language', $Language)
if ($Json) { $arguments += '--json' }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
