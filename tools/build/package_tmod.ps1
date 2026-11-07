# Use the official tML BuildMod command, not a renamed DLL or a custom packer.
# https://github.com/tModLoader/tModLoader/blob/stable/patches/tModLoader/Terraria/release_extras/tMLMod.targets
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$project = Join-Path $root 'mod/InfiniCrafterLocal'
$output = Join-Path $root 'artifacts/package'
New-Item -ItemType Directory -Force $output | Out-Null
# Assemble the private interpreter, pinned wheels and Studio/generator resources.
# The smoke uses that interpreter, an isolated data directory and real HTTP;
# it neither opens a browser nor contacts a model provider.
& python (Join-Path $PSScriptRoot 'build_studio_bundle.py')
if ($LASTEXITCODE -ne 0) { throw 'Studio runtime bundle or its startup smoke failed.' }
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
$runtimeExecution = & (Join-Path $PSScriptRoot 'prepare_tml_runtime.ps1') -TmlRuntime $runtime -Destination (Join-Path $work 'exact-runtime')
# Build source projections on the release target with the same actual native
# dependency bytes. A pack produced on another OS/runtime is never presumed to
# match this deployment; the runtime also verifies every dependency before use.
$nativeReferences = @($assets.packageFolders.PSObject.Properties.Name | ForEach-Object {
    $candidate = Join-Path $_ ($tml[0].Value.path + '/lib/net8.0')
    if (Test-Path (Join-Path $candidate 'tModLoader.dll')) { $candidate }
})
if ($nativeReferences.Count -ne 1) { throw 'Could not uniquely locate tModLoader references for source pack generation.' }
if ((Get-FileHash (Join-Path $nativeReferences[0] 'tModLoader.dll') -Algorithm SHA256).Hash -ne
    (Get-FileHash (Join-Path $runtime 'tModLoader.dll') -Algorithm SHA256).Hash) {
    throw 'Source pack build references differ from the official release runtime.'
}
$sourcePack = Join-Path $project 'Data/native-source-pack.zip'
$sourcePackBootstrap = Join-Path $work 'native-source-pack-harness'
& python (Join-Path $root 'tools/generate/build_native_source_pack.py') --build --tml-references $nativeReferences[0] --external-deps $env:INFINI_TML_DEPS_SRC --harness-output $sourcePackBootstrap --output $sourcePack --runtime-dotnet $runtimeExecution.RuntimeDotnet --runtimeconfig $runtimeExecution.RuntimeConfig --target-rid win-x64 2>&1 | Tee-Object (Join-Path $output 'native-source-pack-build.log')
if ($LASTEXITCODE -ne 0) { throw 'Complete native source pack generation failed.' }
& python (Join-Path $root 'tools/generate/build_native_source_pack.py') --check --output $sourcePack --tml-references $nativeReferences[0]
if ($LASTEXITCODE -ne 0) { throw 'Native source pack input or payload verification failed.' }
# Keep the full identity/gap build receipt as release evidence, outside the mod.
Move-Item ($sourcePack + '.report.json') (Join-Path $output 'native-source-pack-build.json') -Force
Copy-Item (Join-Path $sourcePackBootstrap 'native-target-staging.json') (Join-Path $output 'native-target-staging.json') -Force
# Release optimization, same resolved references as the compilation/native gate.
& dotnet build (Join-Path $project 'InfiniCrafterLocal.csproj') -c Release --no-restore -warnaserror /p:TmlBuildMod=false
if ($LASTEXITCODE -ne 0) { throw 'Release assembly build failed.' }
$dll = Join-Path $project 'bin/Release/net8.0/InfiniCrafterLocal.dll'
if (!(Test-Path $dll)) { throw 'Release DLL missing.' }
$save = Join-Path $work 'save'
Push-Location $runtime
try {
    & $runtimeExecution.RuntimeDotnet exec --runtimeconfig $runtimeExecution.RuntimeConfig --roll-forward Disable tModLoader.dll -server -build $project -eac $dll -tmlsavedirectory $save 2>&1 | Tee-Object (Join-Path $output 'packaging.log')
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
    nativeSourcePackSha256 = (Get-FileHash $sourcePack -Algorithm SHA256).Hash.ToLowerInvariant()
    nativeSourcePackBuild = (Get-Content (Join-Path $output 'native-source-pack-build.json') -Raw | ConvertFrom-Json | Select-Object schema, status, projectionSha256, nativeAssemblySha256, decompilerAssemblySha256, collectorAssemblySha256, runtimeVersion, collectorLaunch, projectileCount, itemCount, capturedIdentities, packSha256, packBytes)
    studioManifest = (Get-Content (Join-Path $project 'Studio/manifest.json') -Raw | ConvertFrom-Json)
    studioRuntimeSmoke = 'passed: embedded interpreter imports, HTTP frontend and managed shutdown'
    runtimeSmoke = 'notRun: packaging does not launch the game'
} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $output 'build-provenance.json') -Encoding utf8
# Verify the actual serialized receipt, not just the in-memory manifest.
$written = Get-Content (Join-Path $output 'build-provenance.json') -Raw | ConvertFrom-Json
$expectedStudio = Get-Content (Join-Path $project 'Studio/manifest.json') -Raw | ConvertFrom-Json
if (($written.studioManifest | ConvertTo-Json -Depth 8 -Compress) -cne ($expectedStudio | ConvertTo-Json -Depth 8 -Compress)) {
    throw 'Serialized Studio provenance differs from the packaged manifest.'
}
