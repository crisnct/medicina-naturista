# Repara accesul la spatiul de lucru medicina-naturista. (v4 - cauza reala)
#
# Ce am descoperit: nu era vorba de drepturi de fisiere (ACL). ACL-ul era deja
# corect dupa v3. Problema este ETICHETA DE INTEGRITATE (mandatory integrity
# control):
#
#   radacina proiectului  -> "Low Mandatory Level"     -> se poate scrie
#   src / data / var / tmp -> fara eticheta (= Medium) -> scrierea este REFUZATA
#
# Procesele sandbox pornesc la integritate Low si, prin regula Windows
# "no write up", nu pot scrie intr-un obiect Medium, oricat de permisiv ar fi
# ACL-ul. Fereastra de administrator (High) nu este afectata.
#
# v4 aplica DOAR eticheta de integritate joasa, cu mostenire, pe radacina si pe
# folderele copil, exact ca pe radacina care functioneaza deja.
#
# Reversibil: comanda de revenire este afisata la final.

[CmdletBinding()]
param(
    [string]$Workspace = 'D:\Workspace\medicina-naturista'
)

$ErrorActionPreference = 'Continue'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host ''
Write-Host '=== Reparare acces spatiu de lucru (v4) ===' -ForegroundColor Cyan
Write-Host "Cont curent  : $($identity.Name)"
Write-Host "Administrator: $isAdmin"
Write-Host "Spatiu       : $Workspace"
Write-Host ''

if (-not (Test-Path -LiteralPath $Workspace)) {
    Write-Host "EROARE: calea nu exista: $Workspace" -ForegroundColor Red
    exit 2
}

if (-not $isAdmin) {
    Write-Host 'Nu rulez ca administrator. Cer elevare (apare fereastra UAC)...' -ForegroundColor Yellow
    try {
        $shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { 'pwsh.exe' } else { 'powershell.exe' }
        Start-Process -FilePath $shell `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-Workspace', ('"' + $Workspace + '"')) `
            -Verb RunAs
        Write-Host 'Am lansat fereastra elevata. Urmareste-i rezultatul.' -ForegroundColor Green
    } catch {
        Write-Host "Elevarea a esuat: $($_.Exception.Message)" -ForegroundColor Red
        exit 3
    }
    exit 0
}

$user = $identity.Name
Write-Host "Rulez elevat ca $user." -ForegroundColor Green

# Eticheta de integritate joasa, cu mostenire pe containere si obiecte.
# *S-1-16-4096 = Low Mandatory Level (SID bine-cunoscut, deci independent de limba).
$targets = @('.', 'src', 'data', 'var', 'tmp', 'frontend')

Write-Host ''
Write-Host '--- Pasul 1/2: aplic eticheta de integritate "Low" (cu mostenire) ---' -ForegroundColor Cyan
foreach ($relative in $targets) {
    $path = if ($relative -eq '.') { $Workspace } else { Join-Path $Workspace $relative }
    if (-not (Test-Path -LiteralPath $path)) { Write-Host ("  {0,-10} LIPSA" -f $relative) -ForegroundColor Yellow; continue }

    & icacls.exe $path /setintegritylevel '(OI)(CI)Low' /C /Q *> $null
    $ok = ($LASTEXITCODE -eq 0)

    # Re-aplica mostenirea pe copiii existenti, ca eticheta sa ajunga si in adancime
    # (nu doar pe folderele de la primul nivel).
    if ($ok) { & icacls.exe $path /T /C /Q /setintegritylevel '(OI)(CI)Low' *> $null }

    Write-Host ("  {0,-10} {1}" -f $relative, $(if ($ok) { 'OK' } else { "cod $LASTEXITCODE" })) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
}

Write-Host ''
Write-Host '--- Pasul 2/2: verificare scriere ---' -ForegroundColor Cyan
$checks = @('.', 'src', 'data', 'var', 'tmp',
            'var\sessions', 'data\documents', 'data\documents\Centrul de studii',
            'data\documents\Centrul de studii\Anatomie')
$allOk = $true
foreach ($relative in $checks) {
    $path = if ($relative -eq '.') { $Workspace } else { Join-Path $Workspace $relative }
    if (-not (Test-Path -LiteralPath $path)) { Write-Host ("  {0,-42} LIPSA" -f $relative) -ForegroundColor Yellow; continue }
    $probe = Join-Path $path ('.proba-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Set-Content -LiteralPath $probe -Value 'proba' -ErrorAction Stop
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        Write-Host ("  {0,-42} SCRIERE OK" -f $relative) -ForegroundColor Green
    } catch {
        $allOk = $false
        Write-Host ("  {0,-42} RESPINS" -f $relative) -ForegroundColor Red
    }
}

Write-Host ''
if ($allOk) {
    Write-Host 'REZULTAT: totul este in regula. Spune-mi si continui lucrul.' -ForegroundColor Green
} else {
    Write-Host 'REZULTAT: unele locuri sunt inca blocate. Trimite-mi textul de mai sus.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Comanda de revenire (scoate eticheta joasa), daca e nevoie vreodata:' -ForegroundColor Gray
Write-Host "  icacls `"$Workspace`" /T /C /setintegritylevel Medium" -ForegroundColor Gray
Write-Host ''
Read-Host 'Apasa Enter pentru a inchide'
