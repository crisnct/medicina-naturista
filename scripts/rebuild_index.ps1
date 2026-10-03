param([int]$BatchSize = 64, [string]$Model = '')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelArguments = @()
if ($Model) { $modelArguments = @('--model', $Model) }
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
& (Join-Path $projectRoot '.venv\Scripts\python.exe') `
    (Join-Path $PSScriptRoot 'build_hybrid_index.py') `
    --source (Join-Path $projectRoot 'data\documents') `
    --batch-size $BatchSize `
    @modelArguments
exit $LASTEXITCODE
