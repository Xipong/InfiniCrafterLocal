"""Manual scoring counterexample; run from repo root with LocalGenerator:tools on PYTHONPATH."""
import copy
import json
from pathlib import Path
from experiment_capability_selection_followup import functional_checks
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.compiler import compile_runtime_program

source = Path("docs/development/experiments/capability_selection_2026-10-22/followup/outputs/7cab69cba728.json")
doc = json.loads(source.read_text())
program = doc["runtimeProgram"]
program["entities"].append({"id": "extra_shared_returner", "kind": "child_projectile"})
for call in list(program["calls"]):
    if call.get("target") == "returning_marker":
        cloned = copy.deepcopy(call)
        cloned.update(id="extra_" + cloned["id"], target="extra_shared_returner")
        program["calls"].append(cloned)
program["calls"].append({
    "id": "extra_shared_on_use", "fn": "spawn_entity_on_event", "target": "pick_body",
    "params": {"when": "on_use", "entity": "extra_shared_returner", "count": 1,
               "spreadRadians": 0, "damageBasis": "authored_child",
               "knockbackBasis": "authored_child", "damageMultiplier": 1, "delaySeconds": 0},
})
validation = validate_runtime_program(doc)
assert validation["ok"], validation
compile_runtime_program(doc)
checks = functional_checks(doc, "tool")
assert all(checks.values()), checks
print(json.dumps({"valid": validation["ok"], "compiled": True, "checks": checks}, indent=2))
# Semantic violation: shared body.on_use also starts a boomerang on primary use.
# No frozen Author output is modified, and this is not a successful model trial.
