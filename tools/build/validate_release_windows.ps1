param(
    [switch]$RequireBuild,
    [switch]$RequireRuntimeSelfTest,
    [switch]$SkipBuild,
    [string]$Project,
    [string]$ExternalDepsRoot,
    [string]$RuntimeSelfTestReport,
    [string]$Report,
    [string]$Group = "full"
)
$Python = if ($env:INFINI_PYTHON) { $env:INFINI_PYTHON } else { (Get-Command python).Source }
$Arguments = @((Join-Path $PSScriptRoot "../validate_release.py"), "--group", $Group)
if ($RequireBuild) { $Arguments += "--require-build" }
if ($RequireRuntimeSelfTest) { $Arguments += "--require-runtime-selftest" }
if ($SkipBuild) { $Arguments += "--skip-build" }
if ($Project) { $Arguments += @("--project", $Project) }
if ($ExternalDepsRoot) { $Arguments += @("--external-deps-root", $ExternalDepsRoot) }
if ($RuntimeSelfTestReport) { $Arguments += @("--runtime-selftest-report", $RuntimeSelfTestReport) }
if ($Report) { $Arguments += @("--report", $Report) }
& $Python @Arguments
exit $LASTEXITCODE
