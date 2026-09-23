param([int]$BatchSize = 64)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
& (Join-Path $root '.venv\Scripts\python.exe') `
    (Join-Path $root 'build_medical_embeddings.py') `
    --source (Join-Path $root 'documents') `
    --output $root `
    --batch-size $BatchSize
exit $LASTEXITCODE
