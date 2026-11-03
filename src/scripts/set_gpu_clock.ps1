#Requires -Version 5.1
#Requires -RunAsAdministrator

<#
.SYNOPSIS
Seteaza limita superioara a frecventei GPU 0 sau restabileste setarile implicite.
.EXAMPLE
.\src\scripts\set_gpu_clock.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$nvidiaSmi = Get-Command nvidia-smi.exe -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $nvidiaSmi) {
    throw 'nvidia-smi.exe nu a fost gasit in PATH. Verifica instalarea driverului NVIDIA.'
}

while ($true) {
    Write-Host ''
    Write-Host 'GPU 0 - frecventa grafica'
    Write-Host 'Introdu o frecventa intre 1072 si 2145 MHz pentru limita superioara.'
    Write-Host 'Limita inferioara ramane 210 MHz.'
    Write-Host 'D = revenire la setarile implicite | Q = iesire'
    $choice = (Read-Host 'Frecventa (MHz) / D / Q').Trim()

    if ($choice -ieq 'Q') {
        break
    }

    if ($choice -ieq 'D') {
        $smiArguments = @('-i', '0', '-rgc')
    }
    else {
        $frequency = 0
        if (-not [int]::TryParse($choice, [ref]$frequency) -or
            $frequency -lt 1072 -or $frequency -gt 2145) {
            Write-Host 'Valoare invalida. Introdu un numar intreg intre 1072 si 2145, D sau Q.'
            continue
        }

        $smiArguments = @('-i', '0', '-lgc', "210,$frequency")
    }

    Write-Host "Execut: nvidia-smi $($smiArguments -join ' ')"
    & $nvidiaSmi.Source @smiArguments
    $smiExitCode = $LASTEXITCODE
    if ($smiExitCode -ne 0) {
        Write-Warning "Comanda NVIDIA a esuat (cod $smiExitCode). Verifica mesajul de mai sus."
        continue
    }

    if ($choice -ieq 'D') {
        Write-Host 'Setarile implicite ale frecventei GPU au fost restabilite.'
    }
    else {
        Write-Host "Intervalul frecventei GPU a fost setat la 210-$frequency MHz."
    }
}
