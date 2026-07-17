param(
    [switch]$RequireBuild,
    [switch]$RequireRuntimeSelfTest,
    [switch]$SkipBuild,
    [string]$Project,
    [string]$ExternalDepsRoot,
    [string]$RuntimeSelfTestReport,
    [string]$Report
)
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Art = Join-Path $Root "artifacts\validation"
$StatusFile = Join-Path $Art "status.tsv"
if (-not $Project) { $Project = Join-Path $Root "ModSources\InfiniCrafterLocal\InfiniCrafterLocal.csproj" }
if (-not $ExternalDepsRoot) { $ExternalDepsRoot = $env:INFINI_TML_DEPS_SRC }
if (-not $RuntimeSelfTestReport) { $RuntimeSelfTestReport = $env:INFINI_AGENT_SELFTEST_REPORT }
if (-not $Report) { $Report = Join-Path $Art "validation_report.json" }
New-Item -ItemType Directory -Force -Path $Art | Out-Null
Set-Content -Path $StatusFile -Value ""
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "LocalGenerator"
$env:PYTHONUTF8 = "1"
$Python = if ($env:INFINI_PYTHON) { $env:INFINI_PYTHON } else { (Get-Command python).Source }
$MissingFullDeps = & $Python -c "import importlib.util; deps={'pytest':'pytest','pydantic':'pydantic','pydantic_core':'pydantic_core','Pillow':'PIL','Hypothesis':'hypothesis'}; print(','.join(label for label,name in deps.items() if importlib.util.find_spec(name) is None))"
if ($MissingFullDeps) {
    Write-Host "[UNAVAILABLE] full release dependencies are missing: $MissingFullDeps"
    Write-Host "[HINT] $Python tools/validate_sandbox.py"
    exit 2
}

function Add-Status([string]$Name, [string]$Status, [string]$Code, [double]$Duration, [string]$Log) {
    Add-Content -Path $StatusFile -Value "$Name`t$Status`t$Code`t$Duration`t$Log"
    Write-Host "[$($Status.ToUpper())] $Name ($Duration s)"
}
function Run-Step([string]$Name, [string]$Command, [string[]]$Arguments, [string]$WorkingDirectory = $Root) {
    $Log = Join-Path $Art "$Name.log"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments *> $Log
        $Code = $LASTEXITCODE
    } finally { Pop-Location }
    $sw.Stop()
    $Status = if ($Code -eq 0) { "passed" } else { "failed" }
    Add-Status $Name $Status "$Code" ([Math]::Round($sw.Elapsed.TotalSeconds, 3)) ($Log.Substring($Root.Length + 1).Replace('\','/'))
}
function Add-Unavailable([string]$Name, [string]$Reason) {
    $Log = Join-Path $Art "$Name.log"
    Set-Content -Path $Log -Value $Reason
    Add-Status $Name "unavailable" "" 0 ($Log.Substring($Root.Length + 1).Replace('\','/'))
}

Run-Step "pytest" $Python @("tools/run_pytest_shards.py", "--shards", "4", "--timeout-seconds", "60", "--json-out", "artifacts/validation/pytest_shards.json")
Run-Step "compileall" $Python @("-m", "compileall", "-q", "LocalGenerator/infini_local", "tools")
Run-Step "schema_check" $Python @("tools/export_contract_schemas.py", "--check")
Run-Step "config_registry" $Python @("tools/config_registry.py", "--check")
Run-Step "contract_parity" $Python @("tools/contract_parity.py", "--quiet", "--out", "artifacts/validation/contract_parity_report.json")
Run-Step "delivery_contract" $Python @("tools/check_delivery_contract.py", "--quiet", "--out", "artifacts/validation/delivery_contract_report.json")
Run-Step "mutation_gate" $Python @("tools/mutation_contract_gate.py")
Run-Step "semantic_runtime_diff" $Python @("tools/semantic_runtime_diff.py")
Run-Step "runtime_impact" $Python @("tools/runtime_impact_report.py", "--out", "artifacts/validation/runtime_impact_report.json")
Run-Step "csharp_contracts" $Python @("tools/check_csharp_contracts.py")
Run-Step "project_hygiene" $Python @("tools/check_project_hygiene.py")
Run-Step "planner_prompt" $Python @("tools/check_planner_prompt_usability.py")
& $Python -c "import ruff" *> $null
if ($LASTEXITCODE -eq 0) { Run-Step "ruff" $Python @("-m", "ruff", "check", "LocalGenerator/infini_local", "tools") }
elseif (Get-Command ruff -ErrorAction SilentlyContinue) { Run-Step "ruff" "ruff" @("check", "LocalGenerator/infini_local", "tools") }
else { Add-Unavailable "ruff" "ruff is not installed for the selected Python or on PATH" }
& $Python -c "import pyright" *> $null
if ($LASTEXITCODE -eq 0) { Run-Step "pyright" $Python @("tools/run_pyright.py", "--pythonpath", $Python) }
elseif (Get-Command pyright -ErrorAction SilentlyContinue) { Run-Step "pyright" $Python @("tools/run_pyright.py", "--pythonpath", $Python, "--pyright-command", (Get-Command pyright).Source) }
else { Add-Unavailable "pyright" "pyright is not installed for the selected Python or on PATH" }
if ($SkipBuild) { Add-Unavailable "tml_build" "build explicitly skipped" }
elseif (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { Add-Unavailable "tml_build" "dotnet is not available" }
elseif (-not (Test-Path $Project)) { Add-Unavailable "tml_build" "project not found: $Project" }
else {
    $BuildArgs = @("build", $Project, "-c", "Debug", "--nologo", "-v:minimal", "-warnaserror")
    if ($ExternalDepsRoot) { $BuildArgs += "/p:InfiniExternalDepsRoot=$ExternalDepsRoot" }
    Run-Step "tml_build" "dotnet" $BuildArgs
}
if ($RuntimeSelfTestReport -and (Test-Path $RuntimeSelfTestReport)) {
    Run-Step "tml_runtime_selftest" $Python @("tools/check_tml_selftest_report.py", $RuntimeSelfTestReport)
} else {
    Add-Unavailable "tml_runtime_selftest" "real tModLoader runtime self-test report is unavailable; run tML with INFINI_AGENT_SELFTEST=1"
}
$RenderArgs = @("tools/render_validation_report.py", "--status-file", $StatusFile, "--out", $Report)
if ($RequireBuild) { $RenderArgs += "--require-build" }
if ($RequireRuntimeSelfTest) { $RenderArgs += "--require-runtime-selftest" }
& $Python @RenderArgs
exit $LASTEXITCODE
