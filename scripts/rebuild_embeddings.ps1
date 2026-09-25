param([int]$BatchSize = 64)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
& (Join-Path $projectRoot '.venv\Scripts\python.exe') `
    (Join-Path $PSScriptRoot 'build_medical_embeddings.py') `
    --source (Join-Path $projectRoot 'data\documents') `
    --output (Join-Path $projectRoot 'data') `
    --batch-size $BatchSize
exit $LASTEXITCODE
