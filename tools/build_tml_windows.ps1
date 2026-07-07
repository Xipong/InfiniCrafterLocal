param(
    [string]$Project = "",
    [string]$Configuration = "Debug",
    [string]$LogDir = "build_logs",
    [string]$InfiniExternalDepsRoot = "",
    [string]$InfiniParticleLibraryDll = "",
    [string]$InfiniLuminanceDll = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Exit code conventions:
#   0  = build succeeded, parser found no errors
#   1  = parser found errors (build may have succeeded or failed)
#   2  = environment / script error (dotnet missing, no csproj, etc.)
#   77 = SKIP: build environment is intentionally incomplete
#        (classic tModLoader.targets missing, or SDK external mod DLL refs missing).
#        CI should treat this as a soft-pass. If dotnet actually starts and fails,
#        the real dotnet/parser exit code is returned instead.

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] dotnet not found in PATH"
    exit 2
}

if ([string]::IsNullOrWhiteSpace($Project)) {
    $candidates = Get-ChildItem -Path (Join-Path $Root "ModSources") -Filter "*.csproj" -Recurse -ErrorAction SilentlyContinue
    if ($candidates.Count -eq 1) {
        $Project = $candidates[0].FullName
    } elseif ($candidates.Count -gt 1) {
        Write-Host "[FAIL] multiple .csproj found; pass -Project explicitly:"
        $candidates | ForEach-Object { Write-Host "  $($_.FullName)" }
        exit 2
    } else {
        Write-Host "[FAIL] no .csproj found under ModSources/."
        exit 2
    }
}

$ResolvedProject = (Resolve-Path $Project).Path
$ProjectDir = Split-Path -Parent $ResolvedProject
$ProjectXml = Get-Content $ResolvedProject -Raw -ErrorAction Stop
$UsesTomatSdk = $ProjectXml -match "Tomat\.Terraria\.ModLoader\.Sdk"

$BuildArgs = @("build", $ResolvedProject, "-c", $Configuration, "--nologo", "-v:minimal")

if ($UsesTomatSdk) {
    Write-Host "[ok] Tomat.Terraria.ModLoader.Sdk project detected; classic tModLoader.targets pre-check is not required."

    if ([string]::IsNullOrWhiteSpace($InfiniExternalDepsRoot) -and -not [string]::IsNullOrWhiteSpace($env:INFINI_TML_DEPS_SRC)) {
        $InfiniExternalDepsRoot = $env:INFINI_TML_DEPS_SRC
    }
    if ([string]::IsNullOrWhiteSpace($InfiniExternalDepsRoot)) {
        $CandidateDepsRoots = @(
            (Join-Path $Root "..\..\..\tmp\tml-deps-src"),
            (Join-Path $ProjectDir "..\..\..\..\..\tmp\tml-deps-src")
        )
        foreach ($CandidateDepsRoot in $CandidateDepsRoots) {
            if (Test-Path $CandidateDepsRoot) {
                $InfiniExternalDepsRoot = (Resolve-Path $CandidateDepsRoot).Path
                break
            }
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($InfiniExternalDepsRoot)) {
        $BuildArgs += "/p:InfiniExternalDepsRoot=$InfiniExternalDepsRoot"
    }

    if ([string]::IsNullOrWhiteSpace($InfiniParticleLibraryDll) -and -not [string]::IsNullOrWhiteSpace($InfiniExternalDepsRoot)) {
        $InfiniParticleLibraryDll = Join-Path $InfiniExternalDepsRoot "ParticleLibrary\ParticleLibrary.dll"
    }
    if ([string]::IsNullOrWhiteSpace($InfiniLuminanceDll) -and -not [string]::IsNullOrWhiteSpace($InfiniExternalDepsRoot)) {
        $InfiniLuminanceDll = Join-Path $InfiniExternalDepsRoot "Luminance\bin\Debug\net8.0\Luminance.dll"
    }
    if (-not [string]::IsNullOrWhiteSpace($InfiniParticleLibraryDll)) {
        $BuildArgs += "/p:InfiniParticleLibraryDll=$InfiniParticleLibraryDll"
    }
    if (-not [string]::IsNullOrWhiteSpace($InfiniLuminanceDll)) {
        $BuildArgs += "/p:InfiniLuminanceDll=$InfiniLuminanceDll"
    }

    if ([string]::IsNullOrWhiteSpace($InfiniParticleLibraryDll) -or -not (Test-Path $InfiniParticleLibraryDll) -or
        [string]::IsNullOrWhiteSpace($InfiniLuminanceDll) -or -not (Test-Path $InfiniLuminanceDll)) {
        Write-Host "[SKIP] external mod reference DLLs not found for Tomat SDK build."
        Write-Host "[SKIP] Set -InfiniExternalDepsRoot, -InfiniParticleLibraryDll/-InfiniLuminanceDll, or INFINI_TML_DEPS_SRC."
        Write-Host "[SKIP] Required: ParticleLibrary.dll and Luminance.dll. Exit code 77 = intentional skip, not a C# failure."
        exit 77
    }
} else {
    # Classic ModSources project: <Import Project="..\tModLoader.targets" /> must resolve.
    $TargetsPath = Join-Path (Split-Path -Parent $ProjectDir) "tModLoader.targets"
    if (-not (Test-Path $TargetsPath)) {
        Write-Host "[SKIP] tModLoader.targets not found at: $TargetsPath"
        Write-Host "[SKIP] This machine does not have a classic tModLoader dev environment installed."
        Write-Host "[SKIP] Real dotnet/tML build is skipped. C# static contracts still run separately."
        Write-Host "[SKIP] Exit code 77 = intentional skip, not a build failure."
        exit 77
    }
    Write-Host "[ok] tModLoader.targets found at: $TargetsPath"
}

$LogPathDir = Join-Path $Root $LogDir
New-Item -ItemType Directory -Force -Path $LogPathDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogPathDir "tml_build_$Stamp.log"

Write-Host "[run] dotnet $($BuildArgs -join ' ')"
& dotnet @BuildArgs *>&1 | Tee-Object -FilePath $LogPath
$BuildCode = $LASTEXITCODE
Write-Host "[log] $LogPath"

# Run parser regardless of build code: it summarises errors/warnings compactly.
$PythonExe = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
& $PythonExe (Join-Path $Root "tools/parse_tml_build_log.py") "$LogPath"
$ParseCode = $LASTEXITCODE

if ($BuildCode -ne 0) {
    Write-Host "[FAIL] dotnet build exited with code $BuildCode"
    exit $BuildCode
}
if ($ParseCode -ne 0) {
    Write-Host "[FAIL] build log parser found errors (code $ParseCode)"
    exit $ParseCode
}
Write-Host "[ok] dotnet build succeeded and log parser found no errors"
exit 0
