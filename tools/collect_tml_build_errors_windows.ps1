param(
    [string]$Log = "",
    [string]$Mod = "InfiniCrafterLocal",
    [string]$OutDir = "build_logs"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($Log)) {
    $doc = [Environment]::GetFolderPath("MyDocuments")
    $candidates = @(
        (Join-Path $doc "My Games\Terraria\tModLoader\Logs\client.log"),
        (Join-Path $doc "My Games\Terraria\tModLoader\Logs\Launch.log"),
        (Join-Path $doc "My Games\Terraria\tModLoader\client.log")
    ) | Where-Object { Test-Path $_ }
    if ($candidates.Count -eq 0) {
        Write-Host "[FAIL] tModLoader client.log не найден автоматически. Передай -Log путь к client.log."
        exit 2
    }
    $Log = $candidates[0]
}

$ResolvedLog = (Resolve-Path $Log).Path
$LogPathDir = Join-Path $Root $OutDir
New-Item -ItemType Directory -Force -Path $LogPathDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SummaryPath = Join-Path $LogPathDir "tml_errors_$Stamp.txt"

Write-Host "[parse] $ResolvedLog"
python (Join-Path $Root "tools/parse_tml_build_log.py") "$ResolvedLog" --mod "$Mod" *>&1 | Tee-Object -FilePath $SummaryPath
$Code = $LASTEXITCODE
Write-Host "[summary] $SummaryPath"
exit $Code
