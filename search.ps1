param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Query,
    [int]$Limit = 10,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$arguments = @(
    (Join-Path $root 'search_medical_embeddings.py'),
    $Query,
    '--index', (Join-Path $root 'embedings'),
    '--limit', $Limit.ToString()
)
if ($Json) { $arguments += '--json' }
& (Join-Path $root '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
