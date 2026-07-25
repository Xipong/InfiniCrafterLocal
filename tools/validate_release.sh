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

# Keep every release step on one dependency-complete interpreter. The Python
# dispatcher supplies sys.executable; direct shell callers may activate a venv
# or set INFINI_PYTHON explicitly.
if [[ -n "${INFINI_PYTHON:-}" ]]; then
  PYTHON_BIN="$INFINI_PYTHON"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[FAIL] no Python interpreter is available"
  exit 2
fi
if [[ "$PYTHON_BIN" != */* ]]; then PYTHON_BIN="$(command -v "$PYTHON_BIN" || true)"; fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then echo "[FAIL] invalid Python interpreter: ${INFINI_PYTHON:-<empty>}"; exit 2; fi

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

MISSING_FULL_DEPS="$("$PYTHON_BIN" -c 'import importlib.util; deps={"pytest":"pytest","pydantic":"pydantic","pydantic_core":"pydantic_core","Pillow":"PIL","Hypothesis":"hypothesis"}; print(",".join(label for label,name in deps.items() if importlib.util.find_spec(name) is None))')"
if [[ -n "$MISSING_FULL_DEPS" ]]; then
  echo "[UNAVAILABLE] full release dependencies are missing: $MISSING_FULL_DEPS"
  echo "[HINT] $PYTHON_BIN tools/validate_sandbox.py"
  exit 2
fi

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

run_step pytest "$PYTHON_BIN" tools/run_pytest_shards.py --shards 4 --timeout-seconds 60 --json-out artifacts/validation/pytest_shards.json
run_step compileall "$PYTHON_BIN" -m compileall -q LocalGenerator/infini_local tools
run_step schema_check "$PYTHON_BIN" tools/export_contract_schemas.py --check
run_step targeted_repair "$PYTHON_BIN" tools/audit_targeted_repair.py --check
run_step terraria_standardization "$PYTHON_BIN" tools/audit_terraria_standardization.py --check
run_step config_registry "$PYTHON_BIN" tools/config_registry.py --check
run_step contract_parity "$PYTHON_BIN" tools/contract_parity.py --quiet --out artifacts/validation/contract_parity_report.json
run_step delivery_contract "$PYTHON_BIN" tools/check_delivery_contract.py --quiet --out artifacts/validation/delivery_contract_report.json
run_step mutation_gate "$PYTHON_BIN" tools/mutation_contract_gate.py
run_step semantic_runtime_diff "$PYTHON_BIN" tools/semantic_runtime_diff.py
run_step runtime_impact "$PYTHON_BIN" tools/runtime_impact_report.py --out artifacts/validation/runtime_impact_report.json
run_step csharp_contracts "$PYTHON_BIN" tools/check_csharp_contracts.py
run_step project_hygiene "$PYTHON_BIN" tools/check_project_hygiene.py
run_step planner_prompt "$PYTHON_BIN" tools/check_planner_prompt_usability.py

if "$PYTHON_BIN" -c 'import ruff' >/dev/null 2>&1; then
  run_step ruff "$PYTHON_BIN" -m ruff check LocalGenerator/infini_local tools
elif command -v ruff >/dev/null 2>&1; then
  run_step ruff "$(command -v ruff)" check LocalGenerator/infini_local tools
else
  record_unavailable ruff "ruff is not installed for the selected Python or on PATH"
fi
if "$PYTHON_BIN" -c 'import pyright' >/dev/null 2>&1; then
  run_step pyright "$PYTHON_BIN" tools/run_pyright.py --pythonpath "$PYTHON_BIN"
elif command -v pyright >/dev/null 2>&1; then
  run_step pyright "$PYTHON_BIN" tools/run_pyright.py --pythonpath "$PYTHON_BIN" --pyright-command "$(command -v pyright)"
else
  record_unavailable pyright "pyright is not installed for the selected Python or on PATH"
fi

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
  run_step tml_runtime_selftest "$PYTHON_BIN" tools/check_tml_selftest_report.py "$RUNTIME_SELFTEST_REPORT"
else
  record_unavailable tml_runtime_selftest "real tModLoader runtime self-test report is unavailable; run tML with INFINI_AGENT_SELFTEST=1"
fi

render=("$PYTHON_BIN" tools/render_validation_report.py --status-file "$STATUS" --out "$REPORT")
if [[ $REQUIRE_BUILD -eq 1 ]]; then render+=(--require-build); fi
if [[ $REQUIRE_RUNTIME_SELFTEST -eq 1 ]]; then render+=(--require-runtime-selftest); fi
"${render[@]}"
exit $?
