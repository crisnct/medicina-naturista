param(
    [switch]$DryRun,
    # Redundant now that folding is the default, kept so existing commands
    # (".\scripts\clean_documents.ps1 -FoldDiacritics") keep working.
    [switch]$FoldDiacritics,
    [switch]$KeepDiacritics
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$arguments = @((Join-Path $PSScriptRoot 'clean_documents.py'))
if ($DryRun) { $arguments += '--dry-run' }
if ($FoldDiacritics) { $arguments += '--fold-diacritics' }
# Last one wins in argparse, so an explicit -KeepDiacritics overrides
# -FoldDiacritics when both are given.
if ($KeepDiacritics) { $arguments += '--no-fold-diacritics' }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
