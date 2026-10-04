$ErrorActionPreference = 'Stop'
$namesFile = 'D:\Workspace\medicina-naturista\src\scripts\conditions_work\FOLK_names_01.txt'
$names = Get-Content -LiteralPath $namesFile -Encoding UTF8
$valid = @{}
foreach ($n in $names) { $valid[$n.Trim()] = $true }

# Doar termeni populari reali, atestati, pentru boli care EXISTA in lista primita.
$pairs = @(
  'Abces|buboi'
  'Adeziviune peritoneala|lipituri'
  'Alcoolism|betie'
  'Alopecie|chelie'
  'Anafilaxie|soc'
  'Anemie|galbeaza'
)

$lines = New-Object System.Collections.Generic.List[string]
foreach ($x in $pairs) {
  $c = ($x -split '\|')[0]
  if (-not $valid.ContainsKey($c)) { Write-Host ("LIPSA IN LISTA: " + $c); continue }
  $lines.Add($x)
}

$out = 'D:\Workspace\medicina-naturista\src\scripts\conditions_work\FOLK_01.txt'
[System.IO.File]::WriteAllLines($out, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ('LINII SCRISE: ' + $lines.Count)
Write-Host ('BOLI ACOPERITE: ' + (($lines | ForEach-Object { ($_ -split '\|')[0] } | Sort-Object -Unique).Count))
$pop = $lines | ForEach-Object { ($_ -split '\|')[1] }
Write-Host ('TERMENI UNICI: ' + ($pop | Sort-Object -Unique).Count + '/' + $pop.Count)
Write-Host '--- continut ---'
$lines | ForEach-Object { Write-Host $_ }
