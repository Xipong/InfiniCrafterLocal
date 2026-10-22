# Use the official tML BuildMod command, not a renamed DLL or a custom packer.
# https://github.com/tModLoader/tModLoader/blob/stable/patches/tModLoader/Terraria/release_extras/tMLMod.targets
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$project = Join-Path $root 'ModSources/InfiniCrafterLocal'
$output = Join-Path $root 'artifacts/package'
New-Item -ItemType Directory -Force $output | Out-Null
$assets = Get-Content (Join-Path $project 'obj/project.assets.json') -Raw | ConvertFrom-Json
$tml = @($assets.libraries.PSObject.Properties | Where-Object { $_.Name -like 'tModLoader/*' })
if ($tml.Count -ne 1) { throw 'Expected exactly one resolved tML version.' }
$version = $tml[0].Name.Split('/')[1]
if ($version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') { throw "Unexpected tML version: $version" }
$resolvedVersion = [Version]$version
if ($resolvedVersion.Revision -lt 0) { $version += '.0' }
$resolvedVersion = [Version]$version
$headers = @{ Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
if ($env:GITHUB_TOKEN) { $headers.Authorization = "Bearer $env:GITHUB_TOKEN" }
# GitHub tag months may be zero-padded; NuGet normalizes version segments.
$releases = Invoke-RestMethod 'https://api.github.com/repos/tModLoader/tModLoader/releases?per_page=100' -Headers $headers
$matches = @($releases | Where-Object {
    $candidate = $null
    [Version]::TryParse(([string]$_.tag_name -replace '^v', ''), [ref]$candidate) -and $candidate -eq $resolvedVersion
})
if ($matches.Count -ne 1) { throw "Cannot uniquely locate official tML release $version." }
$release = $matches[0]
$asset = @($release.assets | Where-Object name -eq 'tModLoader.zip')
if ($asset.Count -ne 1) { throw 'Official release does not contain exactly one tModLoader.zip.' }
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('infinicrafter-package-' + [Guid]::NewGuid())
New-Item -ItemType Directory $work | Out-Null
$zip = Join-Path $work 'tModLoader.zip'
& curl.exe --fail --location --retry 3 --silent --show-error --output $zip $asset[0].browser_download_url
if ($LASTEXITCODE -ne 0) { throw 'Official tML download failed.' }
$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($asset[0].digest -and $asset[0].digest -ne "sha256:$zipHash") { throw 'Official tML asset digest mismatch.' }
$runtime = Join-Path $work 'runtime'
Expand-Archive $zip $runtime
# Release optimization, same resolved references as the compilation/native gate.
& dotnet build (Join-Path $project 'InfiniCrafterLocal.csproj') -c Release --no-restore -warnaserror /p:TmlBuildMod=false
if ($LASTEXITCODE -ne 0) { throw 'Release assembly build failed.' }
$dll = Join-Path $project 'bin/Release/net8.0/InfiniCrafterLocal.dll'
if (!(Test-Path $dll)) { throw 'Release DLL missing.' }
$save = Join-Path $work 'save'
Push-Location $runtime
try {
    & dotnet tModLoader.dll -server -build $project -eac $dll -tmlsavedirectory $save 2>&1 | Tee-Object (Join-Path $output 'packaging.log')
    if ($LASTEXITCODE -ne 0) { throw "Official tML packager failed ($LASTEXITCODE)." }
}
finally { Pop-Location }
$tmod = Join-Path $save 'Mods/InfiniCrafterLocal.tmod'
if (!(Test-Path $tmod)) { throw 'Official packager did not produce the expected .tmod.' }
Copy-Item $tmod $output
$tmod = Join-Path $output 'InfiniCrafterLocal.tmod'
& python (Join-Path $PSScriptRoot 'verify_tmod_package.py') $tmod --source $project --assembly $dll --tml-version $version --report (Join-Path $output 'package-verification.json')
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed.' }
@{
    sourceCommit = (& git -C $root rev-parse HEAD)
    tmlVersion = $version
    tmlReleaseUrl = $release.html_url
    tmlAssetSha256 = $zipHash
    tmlAssetDigest = $asset[0].digest
    assemblySha256 = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    particleLibrarySha256 = (Get-FileHash (Join-Path $env:INFINI_TML_DEPS_SRC 'ParticleLibrary/ParticleLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    luminanceSha256 = (Get-FileHash (Join-Path $env:INFINI_TML_DEPS_SRC 'Luminance/bin/Debug/net8.0/Luminance.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    packageSha256 = (Get-FileHash $tmod -Algorithm SHA256).Hash.ToLowerInvariant()
    runtimeSmoke = 'notRun: packaging does not launch the game'
} | ConvertTo-Json | Set-Content (Join-Path $output 'build-provenance.json') -Encoding utf8
