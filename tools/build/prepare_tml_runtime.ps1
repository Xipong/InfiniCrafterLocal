param(
    [string]$TmlRuntime = '',
    [string]$TmlVersion = '',
    [Parameter(Mandatory = $true)][string]$Destination
)

# The official launcher uses its private runtime at the exact framework version
# in tModLoader.runtimeconfig.json, with framework roll-forward disabled.
$ErrorActionPreference = 'Stop'
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null
if ([string]::IsNullOrWhiteSpace($TmlRuntime)) {
    $requestedVersion = $null
    if (-not [Version]::TryParse($TmlVersion, [ref]$requestedVersion)) {
        throw 'Pass an official unpacked -TmlRuntime or an exact resolved -TmlVersion.'
    }
    if ($requestedVersion.Revision -lt 0) { $requestedVersion = [Version]($TmlVersion + '.0') }
    $headers = @{ Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
    if ($env:GITHUB_TOKEN) { $headers.Authorization = "Bearer $env:GITHUB_TOKEN" }
    $releases = Invoke-RestMethod 'https://api.github.com/repos/tModLoader/tModLoader/releases?per_page=100' -Headers $headers
    $matches = @($releases | Where-Object {
        $candidate = $null
        [Version]::TryParse(([string]$_.tag_name -replace '^v', ''), [ref]$candidate) -and $candidate -eq $requestedVersion
    })
    if ($matches.Count -ne 1) { throw "Cannot uniquely locate official tML release $requestedVersion." }
    $asset = @($matches[0].assets | Where-Object name -eq 'tModLoader.zip')
    if ($asset.Count -ne 1) { throw 'Expected one official tModLoader.zip asset.' }
    $releaseArchive = Join-Path $destinationPath 'tModLoader.zip'
    & curl.exe --fail --location --retry 3 --silent --show-error --output $releaseArchive $asset[0].browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'Official tML download failed.' }
    $archiveHash = (Get-FileHash $releaseArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($asset[0].digest -and $asset[0].digest -ne "sha256:$archiveHash") { throw 'Official tML asset digest mismatch.' }
    $TmlRuntime = Join-Path $destinationPath 'tml'
    Expand-Archive -Path $releaseArchive -DestinationPath $TmlRuntime -Force
}
$runtimeRoot = (Resolve-Path $TmlRuntime).Path
$runtimeConfig = Join-Path $runtimeRoot 'tModLoader.runtimeconfig.json'
if (-not (Test-Path $runtimeConfig)) { throw 'Official tModLoader.runtimeconfig.json is missing.' }
$configuration = Get-Content $runtimeConfig -Raw | ConvertFrom-Json
$framework = $configuration.runtimeOptions.framework
$runtimeVersion = [string]$framework.version
if ($framework.name -ne 'Microsoft.NETCore.App' -or $runtimeVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw 'Unexpected official tML runtime framework; do not substitute the build SDK runtime.'
}
$runtimeDirectory = Join-Path $destinationPath 'dotnet'
$runtimeHostPath = Join-Path $runtimeDirectory 'dotnet.exe'
$coreLibrary = Join-Path $runtimeDirectory "shared/Microsoft.NETCore.App/$runtimeVersion/System.Private.CoreLib.dll"
if (-not (Test-Path $runtimeHostPath) -or -not (Test-Path $coreLibrary)) {
    New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
    $bundledRuntime = Join-Path $runtimeRoot "LaunchUtils/dotnet-runtime-$runtimeVersion-win-x64.zip"
    if (Test-Path $bundledRuntime) {
        Expand-Archive -Path $bundledRuntime -DestinationPath $runtimeDirectory -Force
    } else {
        $installer = Join-Path $destinationPath 'dotnet-install.ps1'
        & curl.exe --fail --location --retry 3 --silent --show-error --output $installer 'https://dot.net/v1/dotnet-install.ps1'
        if ($LASTEXITCODE -ne 0) { throw 'Official dotnet-install.ps1 download failed.' }
        $powerShellPath = (Get-Process -Id $PID).Path
        & $powerShellPath -NoProfile -ExecutionPolicy Bypass -File $installer -Runtime dotnet -Version $runtimeVersion -Architecture x64 -InstallDir $runtimeDirectory -NoPath | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Exact tML .NET runtime installation failed: $LASTEXITCODE" }
    }
}
if (-not (Test-Path $runtimeHostPath) -or -not (Test-Path $coreLibrary)) {
    throw 'The exact private tML runtime was not installed.'
}
[pscustomobject]@{
    TmlRuntime = $runtimeRoot
    RuntimeDotnet = $runtimeHostPath
    RuntimeConfig = $runtimeConfig
    RuntimeVersion = $runtimeVersion
}
