#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ART="$ROOT/artifacts/validation"
STATUS="$ART/status.tsv"
REPORT="$ART/validation_report.json"
REQUIRE_BUILD=0
REQUIRE_RUNTIME_SELFTEST=0
SKIP_BUILD=0
RUNTIME_SELFTEST_REPORT="${INFINI_AGENT_SELFTEST_REPORT:-}"
PROJECT="$ROOT/ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj"
EXTERNAL_DEPS_ROOT="${INFINI_TML_DEPS_SRC:-}"

while (($#)); do
  case "$1" in
    --require-build) REQUIRE_BUILD=1 ;;
    --require-runtime-selftest) REQUIRE_RUNTIME_SELFTEST=1 ;;
    --runtime-selftest-report) shift; RUNTIME_SELFTEST_REPORT="$1" ;;
    --skip-build) SKIP_BUILD=1 ;;
    --project) shift; PROJECT="$1" ;;
    --external-deps-root) shift; EXTERNAL_DEPS_ROOT="$1" ;;
    --report) shift; REPORT="$1" ;;
    *) echo "[FAIL] unknown argument: $1"; exit 2 ;;
  esac
  shift
done

mkdir -p "$ART"
: > "$STATUS"
cd "$ROOT"
export PYTHONPATH="$ROOT/LocalGenerator"
export PYTHONUTF8=1

record_unavailable() {
  local name="$1"
  local reason="$2"
  local log="$ART/$name.log"
  printf '%s\n' "$reason" > "$log"
  printf '%s\tunavailable\t\t0\t%s\n' "$name" "${log#$ROOT/}" >> "$STATUS"
  echo "[UNAVAILABLE] $name: $reason"
}

run_step() {
  local name="$1"; shift
  local log="$ART/$name.log"
  local start end code status
  start=$(date +%s)
  "$@" > "$log" 2>&1
  code=$?
  end=$(date +%s)
  if [[ $code -eq 0 ]]; then status=passed; else status=failed; fi
  local duration=$((end - start))
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$status" "$code" "$duration" "${log#$ROOT/}" >> "$STATUS"
  echo "[${status^^}] $name (${duration}s)"
}

run_step pytest python tools/run_pytest_shards.py --shards 4 --json-out artifacts/validation/pytest_shards.json
run_step compileall python -m compileall -q LocalGenerator/infini_local tools
run_step schema_check python tools/export_contract_schemas.py --check
run_step config_registry python tools/config_registry.py --check
run_step contract_parity python tools/contract_parity.py --quiet --out artifacts/validation/contract_parity_report.json
run_step delivery_contract python tools/check_delivery_contract.py --quiet --out artifacts/validation/delivery_contract_report.json
run_step mutation_gate python tools/mutation_contract_gate.py
run_step semantic_runtime_diff python tools/semantic_runtime_diff.py
run_step runtime_impact python tools/runtime_impact_report.py --out artifacts/validation/runtime_impact_report.json
run_step csharp_contracts python tools/check_csharp_contracts.py
run_step project_hygiene python tools/check_project_hygiene.py
run_step planner_prompt python tools/check_planner_prompt_usability.py

if command -v ruff >/dev/null 2>&1; then run_step ruff ruff check LocalGenerator/infini_local tools; else record_unavailable ruff "ruff is not installed"; fi
if command -v pyright >/dev/null 2>&1; then run_step pyright pyright; else record_unavailable pyright "pyright is not installed"; fi

if [[ $SKIP_BUILD -eq 1 ]]; then
  record_unavailable tml_build "build explicitly skipped"
elif ! command -v dotnet >/dev/null 2>&1; then
  record_unavailable tml_build "dotnet is not available in this environment"
elif [[ ! -f "$PROJECT" ]]; then
  record_unavailable tml_build "project not found: $PROJECT"
else
  build=(dotnet build "$PROJECT" -c Debug --nologo -v:minimal -warnaserror)
  if [[ -n "$EXTERNAL_DEPS_ROOT" ]]; then build+=("/p:InfiniExternalDepsRoot=$EXTERNAL_DEPS_ROOT"); fi
  run_step tml_build "${build[@]}"
fi

if [[ -n "$RUNTIME_SELFTEST_REPORT" && -f "$RUNTIME_SELFTEST_REPORT" ]]; then
  run_step tml_runtime_selftest python tools/check_tml_selftest_report.py "$RUNTIME_SELFTEST_REPORT"
else
  record_unavailable tml_runtime_selftest "real tModLoader runtime self-test report is unavailable; run tML with INFINI_AGENT_SELFTEST=1"
fi

render=(python tools/render_validation_report.py --status-file "$STATUS" --out "$REPORT")
if [[ $REQUIRE_BUILD -eq 1 ]]; then render+=(--require-build); fi
if [[ $REQUIRE_RUNTIME_SELFTEST -eq 1 ]]; then render+=(--require-runtime-selftest); fi
"${render[@]}"
exit $?
