param(
    [switch]$DryRun,
    [switch]$FoldDiacritics
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$arguments = @((Join-Path $PSScriptRoot 'clean_documents.py'))
if ($DryRun) { $arguments += '--dry-run' }
if ($FoldDiacritics) { $arguments += '--fold-diacritics' }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
