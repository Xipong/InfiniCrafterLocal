"""Historical finalContract runtimePlan replay + impact selector.

Load a dump-backed corpus of accepted executable runtimePlans, select cases by
changed engine functions, and replay production compile/final projection.

No LLM, no HTTP, no image backend. Mechanical accepted-wire replay only.
Does not duplicate semantic validation — production compile path owns that.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring.final_projection import (
    compile_runtime_plan_to_final_result,
)
from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
    NORMALIZED_ROOT_FUNCTION_NAME,
    NORMALIZED_ROOT_REQUIRED_PARAM_NAMES,
    engine_function_catalog,
    engine_function_contract_surface,
    engine_function_form_impacts,
    engine_function_impact_names,
    normalized_root_required_authored_param_names,
)

CORPUS_SCHEMA = "infini.runtime-contract-replay-corpus.v1"
CONTRACT_FINGERPRINT_SCHEMA = "infini.runtime-contract-fingerprints.v2"
DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "runtime_contract_history"
    / "corpus.json"
)

# Presentation / free-text fields stripped from historical dumps.
PROSE_RUNTIME_PLAN_KEYS = frozenset(
    {
        "visualIntent",
        "sourceReading",
        "sourceRolePreservation",
        "balanceIntent",
        "runtimeStateIntent",
    }
)


def canonical_json(value: Any) -> str:
    """Deterministic JSON for fingerprints and dedupe keys."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strip_python_docstrings(tree: ast.AST) -> ast.AST:
    """Drop non-executable docstrings before implementation fingerprinting."""

    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            del body[0]
    return tree


_VERSION_NEUTRAL_EMPTY_AST_FIELDS = frozenset({"type_params"})


def _stable_ast_payload(value: Any) -> Any:
    """Serialize executable AST semantics without Python-minor dump drift.

    ``ast.dump`` includes every field known by the running interpreter. Python
    3.12 added empty ``type_params`` fields to several nodes, so identical source
    produced different committed fingerprints under 3.11/3.12/3.13. Preserve
    meaningful non-empty metadata, but omit version-added empty fields and encode
    the remaining tree explicitly.
    """

    if isinstance(value, ast.AST):
        fields: list[list[Any]] = []
        for field_name in value._fields:
            field_value = getattr(value, field_name, None)
            if (
                field_name in _VERSION_NEUTRAL_EMPTY_AST_FIELDS
                and field_value in (None, [])
            ):
                continue
            fields.append([field_name, _stable_ast_payload(field_value)])
        return {"node": type(value).__name__, "fields": fields}
    if isinstance(value, (list, tuple)):
        return [_stable_ast_payload(item) for item in value]
    return value


def _semantic_python_source_fingerprint(source: str) -> str:
    """Hash executable Python structure, not whitespace/comments/docstrings.

    The replay selector must react to implementation changes without turning a
    formatter or documentation edit into a global regression run. Stable AST
    payloads keep names, constants, control flow, decorators and imports while
    ignoring source layout, comments and Python-minor-only empty metadata.
    """

    tree = ast.parse(textwrap.dedent(source))
    normalized = _strip_python_docstrings(tree)
    payload = canonical_json(_stable_ast_payload(normalized))
    return _sha256_bytes(payload.encode("utf-8"))


def _semantic_python_file_fingerprint(path: Path) -> str:
    return _semantic_python_source_fingerprint(path.read_text(encoding="utf-8"))


def _semantic_python_module_functions_fingerprint(path: Path) -> str:
    """Hash every module-level function while excluding registry data declarations."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    function_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    function_module = ast.Module(body=function_nodes, type_ignores=[])
    normalized = _strip_python_docstrings(function_module)
    payload = canonical_json(_stable_ast_payload(normalized))
    return _sha256_bytes(payload.encode("utf-8"))


def _runtime_implementation_fingerprints() -> dict[str, str]:
    """Fingerprint executable owners that registry-only diffs cannot represent.

    Contract declarations remain form-local through ``functions`` below.  These
    hashes cover executable structure that consumes the declarations.  A mixed
    patch that changes one form *and* compiler/lowering/provenance code must therefore
    run the whole corpus instead of hiding the implementation change behind a one-case
    selector.  Formatting, comments and docstrings do not invalidate replay locality.
    """

    project_root = Path(__file__).resolve().parents[3]
    core_root = project_root / "LocalGenerator/infini_local/core"
    runtime_authoring_root = core_root / "runtime_authoring"

    # Discover the complete runtime-authoring implementation package so adding a
    # new consumer cannot silently bypass mixed-change replay.  Registry data rows
    # remain form-local; all registry function bodies are fingerprinted separately.
    owners: dict[str, Path] = {
        f"runtime_authoring/{path.stem}": path
        for path in sorted(runtime_authoring_root.glob("*.py"))
        if path.stem not in {"__init__", "function_contract_registry"}
    }
    owners.update(
        {
            f"core/{path.stem}": path
            for path in sorted(core_root.glob("runtime_*.py"))
        }
    )
    for name in ("boundary_models", "sound_catalog", "vfx_composition_primitives"):
        owners[f"core/{name}"] = core_root / f"{name}.py"
    owners.update(
        {
            "historical_replay": Path(__file__).resolve(),
            "historical_replay_gate": project_root / "tools/check_runtime_contract_replay.py",
        }
    )

    fingerprints = {
        name: _semantic_python_file_fingerprint(path)
        for name, path in sorted(owners.items())
    }

    registry_path = runtime_authoring_root / "function_contract_registry.py"
    fingerprints["runtime_authoring/function_contract_registry_functions"] = (
        _semantic_python_module_functions_fingerprint(registry_path)
    )
    return dict(sorted(fingerprints.items()))


def runtime_contract_fingerprint_manifest() -> dict[str, Any]:
    """Compact derived fingerprints for function-level impact selection.

    This is deliberately not another contract owner: every byte is projected from
    ``function_contract_registry`` plus semantic AST fingerprints of executable
    consumers.  The committed file lets a dirty-tree inner loop compare against
    ``git show HEAD:<file>`` without freezing generated provider-schema snapshots or
    reacting to formatting-only edits.
    """

    surface = engine_function_contract_surface()
    catalog = engine_function_catalog()
    functions: dict[str, Any] = {}
    for fn in sorted(surface):
        row = surface[fn]
        params = row.get("params") if isinstance(row.get("params"), Mapping) else {}
        lowerers = row.get("lowerers") if isinstance(row.get("lowerers"), list) else []
        meta = {
            "meaning": (catalog.get(fn) or {}).get("meaning"),
            "rootExecutor": row.get("rootExecutor"),
            "requiresRootExecutor": row.get("requiresRootExecutor"),
            "paramOrder": row.get("paramOrder"),
            "repairGroups": row.get("repairGroups"),
            "normalizedOnlyParams": row.get("normalizedOnlyParams"),
            "lowererTargets": [
                lowerer.get("targetFunction")
                for lowerer in lowerers
                if isinstance(lowerer, Mapping)
            ],
            "functionBindings": [
                {
                    "targetFunction": lowerer.get("targetFunction"),
                    "binding": binding,
                }
                for lowerer in lowerers
                if isinstance(lowerer, Mapping)
                for binding in (lowerer.get("bindings") or [])
                if isinstance(binding, Mapping)
                and binding.get("sourcePath") == "$function"
            ],
        }
        forms: dict[str, str] = {}
        for param_name in sorted(str(name) for name in params):
            param = params.get(param_name)
            if not isinstance(param, Mapping):
                continue
            bindings = [
                {
                    "targetFunction": lowerer.get("targetFunction"),
                    "binding": binding,
                }
                for lowerer in lowerers
                if isinstance(lowerer, Mapping)
                for binding in (lowerer.get("bindings") or [])
                if isinstance(binding, Mapping)
                and binding.get("sourcePath") == param_name
            ]
            forms[param_name] = _sha256_json(
                {"param": param, "lowererBindings": bindings}
            )
            nested_rows = param.get("nestedWirePaths")
            if isinstance(nested_rows, list):
                for nested in nested_rows:
                    if not isinstance(nested, Mapping) or not nested.get("path"):
                        continue
                    path = f"{param_name}.{nested['path']}"
                    nested_bindings = [
                        {
                            "targetFunction": lowerer.get("targetFunction"),
                            "binding": binding,
                        }
                        for lowerer in lowerers
                        if isinstance(lowerer, Mapping)
                        for binding in (lowerer.get("bindings") or [])
                        if isinstance(binding, Mapping)
                        and binding.get("sourcePath") == path
                    ]
                    forms[path] = _sha256_json(
                        {
                            "parentValueKind": param.get("valueKind"),
                            "parentObjectModel": param.get("objectModel"),
                            "nested": nested,
                            "lowererBindings": nested_bindings,
                        }
                    )
        functions[fn] = {
            "metaFingerprint": _sha256_json(meta),
            "formFingerprints": forms,
        }
    payload = {
        "schema": CONTRACT_FINGERPRINT_SCHEMA,
        "functions": functions,
        "implementationFingerprints": _runtime_implementation_fingerprints(),
    }
    payload["registryFingerprint"] = _sha256_json(payload)
    return payload


def diff_runtime_contract_fingerprints(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Return exact changed functions/forms or request a conservative full replay."""

    if (
        baseline.get("schema") != CONTRACT_FINGERPRINT_SCHEMA
        or current.get("schema") != CONTRACT_FINGERPRINT_SCHEMA
    ):
        return {
            "fullReplay": True,
            "changedFunctions": [],
            "changedForms": [],
            "changedImplementations": [],
            "reason": "missing_or_incompatible_fingerprint_schema",
        }
    old_functions = baseline.get("functions")
    new_functions = current.get("functions")
    if not isinstance(old_functions, Mapping) or not isinstance(new_functions, Mapping):
        return {
            "fullReplay": True,
            "changedFunctions": [],
            "changedForms": [],
            "changedImplementations": [],
            "reason": "invalid_fingerprint_function_map",
        }

    old_implementations = baseline.get("implementationFingerprints")
    new_implementations = current.get("implementationFingerprints")
    if not isinstance(old_implementations, Mapping) or not isinstance(new_implementations, Mapping):
        return {
            "fullReplay": True,
            "changedFunctions": [],
            "changedForms": [],
            "changedImplementations": [],
            "reason": "invalid_implementation_fingerprint_map",
        }
    changed_implementations = sorted(
        str(name)
        for name in set(old_implementations) | set(new_implementations)
        if old_implementations.get(name) != new_implementations.get(name)
    )
    if changed_implementations:
        return {
            "fullReplay": True,
            "changedFunctions": [],
            "changedForms": [],
            "changedImplementations": changed_implementations,
            "reason": "runtime_implementation_changed",
        }

    changed_functions: set[str] = set()
    changed_forms: set[str] = set()
    removed_functions = set(old_functions) - set(new_functions)
    if removed_functions:
        return {
            "fullReplay": True,
            "changedFunctions": [],
            "changedForms": [],
            "changedImplementations": [],
            "reason": f"removed_functions:{sorted(removed_functions)}",
        }

    for fn in sorted(set(old_functions) | set(new_functions)):
        old = old_functions.get(fn)
        new = new_functions.get(fn)
        if not isinstance(new, Mapping):
            return {
                "fullReplay": True,
                "changedFunctions": [],
                "changedForms": [],
                "changedImplementations": [],
                "reason": f"invalid_current_function_fingerprint:{fn}",
            }
        if not isinstance(old, Mapping):
            changed_functions.add(str(fn))
            continue
        if old.get("metaFingerprint") != new.get("metaFingerprint"):
            changed_functions.add(str(fn))
            continue
        old_forms = old.get("formFingerprints")
        new_forms = new.get("formFingerprints")
        if not isinstance(old_forms, Mapping) or not isinstance(new_forms, Mapping):
            changed_functions.add(str(fn))
            continue
        if set(old_forms) - set(new_forms):
            # A removed form cannot be selected through the current registry graph.
            changed_functions.add(str(fn))
            continue
        for path in sorted(set(old_forms) | set(new_forms)):
            if old_forms.get(path) != new_forms.get(path):
                changed_forms.add(f"{fn}:{path}")

    changed_forms = {
        form
        for form in changed_forms
        if form.split(":", 1)[0] not in changed_functions
    }
    return {
        "fullReplay": False,
        "changedFunctions": sorted(changed_functions),
        "changedForms": sorted(changed_forms),
        "changedImplementations": [],
        "reason": "contract_diff" if changed_functions or changed_forms else "no_contract_diff",
    }


def _safe_token(value: object) -> str:
    raw = str(value or "").strip().lower()
    token = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("._-")
    return token or "unknown"


def _normalize_function_name(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def default_corpus_path() -> Path:
    return DEFAULT_CORPUS_PATH


def load_corpus(path: str | Path | None = None) -> dict[str, Any]:
    """Load the committed historical replay corpus."""
    corpus_path = Path(path) if path is not None else DEFAULT_CORPUS_PATH
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("corpus root must be an object")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("corpus.cases must be a list")
    return payload


def deterministic_contract_witness_candidates() -> list[dict[str, Any]]:
    """Small executable witnesses for registry functions absent from old Live dumps.

    The historical corpus is evidence from real accepted generations, but the 21–23
    July dumps predate preservation of typed Author identities.  These nine plans are
    deliberately boring mechanical witnesses: they contain no item names or prose and
    exist only so every canonical function has at least one fail-closed compile path.

    Keep them minimal.  They are test inputs, not a second gameplay-policy owner.
    """

    def call(call_id: str, fn: str, **params: Any) -> dict[str, Any]:
        return {"callId": call_id, "fn": fn, "params": params}

    def root_witness_params(fn: str, **overrides: Any) -> dict[str, Any]:
        """Fill every required source form from the registry, then apply valid examples."""

        spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[fn]
        by_name = {param.name: param for param in spec.params}
        params = {
            name: copy.deepcopy(by_name[name].example_value)
            for name in normalized_root_required_authored_param_names(fn)
        }
        params.update(overrides)
        return params

    weapon_stats = call(
        "stats",
        "set_item_stats",
        resultKind="weapon",
        damageClass="ranged",
        damage=10,
        maxStack=1,
        craftYield=1,
        consumable=False,
        useTimeTicks=20,
        useAnimationTicks=20,
    )
    magic_stats = copy.deepcopy(weapon_stats)
    magic_stats["params"]["damageClass"] = "magic"
    summon_stats = copy.deepcopy(weapon_stats)
    summon_stats["params"]["damageClass"] = "summon"
    melee_stats = copy.deepcopy(weapon_stats)
    melee_stats["params"]["damageClass"] = "melee"
    tool_stats = call(
        "stats",
        "set_item_stats",
        resultKind="tool",
        damageClass="melee",
        damage=5,
        maxStack=1,
        craftYield=1,
        consumable=False,
        useTimeTicks=20,
        useAnimationTicks=20,
    )

    rows: list[tuple[str, str, list[dict[str, Any]]]] = [
        (
            "perform_melee_attack",
            "weapon",
            [
                melee_stats,
                call(
                    "root",
                    "perform_melee_attack",
                    **root_witness_params(
                        "perform_melee_attack",
                        family="broadsword",
                        speed=8,
                        rangeTiles=8,
                        lifetimeTicks=60,
                        shotCount=1,
                        spreadRadians=0,
                        pierce=1,
                        useTimeTicks=20,
                        useAnimationTicks=20,
                    ),
                ),
            ],
        ),
        (
            "fire_ranged_weapon",
            "weapon",
            [
                weapon_stats,
                call(
                    "root",
                    "fire_ranged_weapon",
                    **root_witness_params(
                        "fire_ranged_weapon",
                        family="bow",
                        ammoFor="arrow",
                        projectileFamily="arrow",
                        movement="straight",
                        speed=10,
                        rangeTiles=40,
                        lifetimeTicks=120,
                        shotCount=1,
                        spreadRadians=0,
                        pierce=1,
                        useTimeTicks=20,
                        useAnimationTicks=20,
                    ),
                ),
            ],
        ),
        (
            "cast_magic_weapon",
            "weapon",
            [
                magic_stats,
                call(
                    "root",
                    "cast_magic_weapon",
                    **root_witness_params(
                        "cast_magic_weapon",
                        family="staff",
                        projectileFamily="magic_bolt",
                        movement="straight",
                        speed=10,
                        rangeTiles=40,
                        lifetimeTicks=120,
                        shotCount=1,
                        spreadRadians=0,
                        pierce=1,
                        useTimeTicks=20,
                        useAnimationTicks=20,
                    ),
                ),
            ],
        ),
        (
            "deploy_sentry",
            "weapon",
            [
                summon_stats,
                call(
                    "root",
                    "deploy_sentry",
                    **root_witness_params(
                        "deploy_sentry",
                        placement="grounded",
                        attackIntervalTicks=40,
                        targetRangeTiles=28,
                        helperLifetimeTicks=600,
                        shotCount=1,
                        speed=10,
                        spreadRadians=0,
                        pierce=1,
                        movement="straight",
                        projectileShape="sentry body",
                        secondaryProjectileShape="sentry bolt",
                        secondaryLifetimeTicks=60,
                        useTimeTicks=20,
                        useAnimationTicks=20,
                    ),
                ),
            ],
        ),
        (
            "spawn_temporary_helper_projectile",
            "weapon",
            [
                summon_stats,
                call(
                    "root",
                    "spawn_temporary_helper_projectile",
                    **root_witness_params(
                        "spawn_temporary_helper_projectile",
                        family="drone",
                        movement="orbit",
                        speed=8,
                        rangeTiles=20,
                        lifetimeTicks=600,
                        shotCount=1,
                        spreadRadians=0,
                        pierce=1,
                        projectileShape="helper drone",
                        useTimeTicks=20,
                        useAnimationTicks=20,
                    ),
                ),
            ],
        ),
        (
            "ammo_behavior",
            "ammo",
            [
                call(
                    "stats",
                    "set_item_stats",
                    resultKind="ammo",
                    damageClass="ranged",
                    damage=7,
                    maxStack=999,
                    craftYield=50,
                    consumable=True,
                    ammoFor="arrow",
                ),
                call("ammo", "ammo_behavior", ammoFor="arrow"),
            ],
        ),
        (
            "emit_light",
            "tool",
            [
                tool_stats,
                call("tool", "tool_capability", pickPower=35),
                call("light", "emit_light", strength=0.4, color="gold", durationTicks=60),
            ],
        ),
        (
            "leave_trail_or_field",
            "weapon",
            [
                weapon_stats,
                call(
                    "root",
                    "shoot_projectile",
                    **root_witness_params(
                        "shoot_projectile",
                        runtimeFamily="shoot",
                        delivery="shoot",
                        weaponFamily="gun",
                        projectileFamily="bullet",
                        movement="straight",
                        speed=10,
                        rangeTiles=40,
                        lifetimeTicks=120,
                        shotCount=1,
                        spreadRadians=0,
                        pierce=1,
                    ),
                ),
                call(
                    "trail",
                    "leave_trail_or_field",
                    trailLength=6,
                    fieldLifetimeTicks=80,
                    fieldRadiusTiles=3.5,
                    tickRate=9,
                    visualOnly=True,
                ),
            ],
        ),
        (
            "use_condition",
            "tool",
            [
                tool_stats,
                call("tool", "tool_capability", pickPower=35),
                call("condition", "use_condition", mode="mana_above", minMana=40),
            ],
        ),
    ]

    candidates: list[dict[str, Any]] = []
    for target, result_kind, calls in rows:
        runtime_plan = {
            "resultKind": result_kind,
            "engineCalls": copy.deepcopy(calls),
        }
        functions = sorted(functions_from_runtime_plan(runtime_plan))
        authored_functions = list(functions)
        authored_forms = sorted(
            f"{fn}:{path}"
            for fn, path in authored_function_forms_from_runtime_plan(
                runtime_plan,
                assume_current_is_authored=True,
            )
        )
        plan_key = canonical_json(
            {
                "runtimePlan": runtime_plan,
                "authoredFunctions": authored_functions,
                "authoredForms": authored_forms,
            }
        )
        candidates.append(
            {
                "caseId": make_case_id(
                    "deterministic-contract-witness-v1", target, plan_key
                ),
                "sourceRun": "deterministic-contract-witness-v1",
                "case": target,
                "category": result_kind,
                "resultKind": result_kind,
                "functions": functions,
                "authoredFunctions": authored_functions,
                "authoredForms": authored_forms,
                "runtimePlan": runtime_plan,
                "_planKey": plan_key,
                "_shapes": call_shapes_from_plan(runtime_plan),
            }
        )
    return candidates


def functions_from_runtime_plan(runtime_plan: Mapping[str, Any] | None) -> frozenset[str]:
    """Return the engine function set from an executable runtimePlan."""
    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[str] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = _normalize_function_name(call.get("fn"))
        if fn:
            out.add(fn)
    return frozenset(out)


def normalized_functions_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[str]:
    """Return actual compiler-IR functions after production normalization."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    from infini_local.core.runtime_authoring.normalize import (  # local: avoid import cycle
        normalize_runtime_plan_inplace,
    )

    data = {"runtimePlan": copy.deepcopy(dict(runtime_plan))}
    normalize_runtime_plan_inplace(data)
    normalized = data.get("runtimePlan")
    return functions_from_runtime_plan(normalized if isinstance(normalized, Mapping) else {})


def normalized_function_forms_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[tuple[str, str]]:
    """Return exact function/param forms after production normalization."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    from infini_local.core.runtime_authoring.normalize import (  # local: avoid import cycle
        normalize_runtime_plan_inplace,
    )

    data = {"runtimePlan": copy.deepcopy(dict(runtime_plan))}
    normalize_runtime_plan_inplace(data)
    normalized = data.get("runtimePlan")
    return function_forms_from_runtime_plan(
        normalized if isinstance(normalized, Mapping) else {}
    )


def authored_functions_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[str]:
    """Recover typed Author function provenance when a dump preserved it."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[str] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        authored = _normalize_function_name(
            call.get("_authoredFn") or call.get("_rawFn") or call.get("authoredFn")
        )
        if authored:
            out.add(authored)
    return frozenset(out)


def authored_function_forms_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
    *,
    assume_current_is_authored: bool = False,
) -> frozenset[tuple[str, str]]:
    """Recover exact typed Author forms from production provenance metadata.

    A normalized call may expose ``fn=shoot_projectile`` while retaining the real
    source contract in ``_authoredFn``/``_authoredParams``.  Replay selection must
    consume that canonical metadata rather than reconstructing source aliases from
    the lowered target.  Synthetic raw typed witnesses may opt in to treating the
    current call as authored; historical dumps do not guess when metadata is absent.
    """

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[tuple[str, str]] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        current_fn = _normalize_function_name(call.get("fn"))
        authored_fn = _normalize_function_name(
            call.get("_authoredFn")
            or call.get("_rawFn")
            or call.get("authoredFn")
            or (current_fn if assume_current_is_authored else "")
        )
        if not authored_fn:
            continue
        out.add((authored_fn, "$function"))
        authored_params = call.get("_authoredParams")
        if not isinstance(authored_params, Mapping):
            authored_params = call.get("params") if authored_fn == current_fn else None
        if isinstance(authored_params, Mapping):
            out.update(
                (authored_fn, path) for path in _iter_param_paths(authored_params)
            )
    return frozenset(out)


def _iter_param_paths(params: Mapping[str, Any]) -> frozenset[str]:
    """Return top-level and nested object paths present in one call."""

    out: set[str] = set()
    pending: list[tuple[str, Any]] = [
        (str(key), value) for key, value in params.items() if not str(key).startswith("_")
    ]
    while pending:
        path, value = pending.pop(0)
        out.add(path)
        if isinstance(value, Mapping):
            pending[0:0] = [
                (f"{path}.{child}", child_value)
                for child, child_value in value.items()
                if not str(child).startswith("_")
            ]
    return frozenset(out)


def function_forms_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[tuple[str, str]]:
    """Return normalized function identity and exact present parameter forms."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[tuple[str, str]] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = _normalize_function_name(call.get("fn"))
        if not fn:
            continue
        out.add((fn, "$function"))
        params = call.get("params")
        if isinstance(params, Mapping):
            out.update((fn, path) for path in _iter_param_paths(params))
    return frozenset(out)


def case_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """Function inventory for one corpus case (authoritative: engineCalls)."""
    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    from_plan = functions_from_runtime_plan(plan if isinstance(plan, Mapping) else {})
    listed = case.get("functions")
    if isinstance(listed, list) and listed:
        listed_set = frozenset(str(fn).strip() for fn in listed if str(fn).strip())
        if listed_set != from_plan:
            # Prefer executable calls; listed field is a cache that must match.
            return from_plan
        return listed_set
    return from_plan


def case_authored_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """Typed Author function inventory, if retained by the corpus builder."""

    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    from_plan = authored_functions_from_runtime_plan(plan if isinstance(plan, Mapping) else {})
    listed = case.get("authoredFunctions")
    listed_set = (
        frozenset(_normalize_function_name(fn) for fn in listed if _normalize_function_name(fn))
        if isinstance(listed, list)
        else frozenset()
    )
    return from_plan or listed_set


def case_authored_form_set(case: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    """Typed Author forms retained by runtime metadata or the corpus sidecar."""

    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    from_plan = authored_function_forms_from_runtime_plan(
        plan if isinstance(plan, Mapping) else {}
    )
    listed = case.get("authoredForms")
    listed_set: set[tuple[str, str]] = set()
    if isinstance(listed, list):
        for raw in listed:
            token = str(raw or "").strip()
            if ":" not in token:
                continue
            raw_fn, raw_path = token.split(":", 1)
            fn = _normalize_function_name(raw_fn)
            path = raw_path.strip()
            if fn and path:
                listed_set.add((fn, path))
    return from_plan or frozenset(listed_set)


def case_impact_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """Stored, normalized, and authored function identities represented by a case."""

    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    return (
        case_function_set(case)
        | normalized_functions_from_runtime_plan(plan)
        | case_authored_function_set(case)
    )


def corpus_function_set(corpus: Mapping[str, Any]) -> frozenset[str]:
    """Union of all engine functions present in the corpus."""
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        return frozenset()
    out: set[str] = set()
    for case in cases:
        if isinstance(case, Mapping):
            out |= set(case_function_set(case))
    return frozenset(out)


def select_cases_by_changed_functions(
    corpus: Mapping[str, Any],
    changed_functions: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Select corpus cases impacted by changed engine functions.

    - empty / None changed set → all cases (full regression)
    - a provenance-aware corpus selects specialized typed lowerers by exact
      ``authoredFunctions`` identity
    - a legacy corpus without authored provenance conservatively maps a typed
      lowerer to its canonical normalized executor
    - unknown or uncovered functions raise instead of returning false-green empty
      selections
    - each case appears at most once; order is deterministic by caseId
    """
    cases_raw = corpus.get("cases")
    cases: list[dict[str, Any]] = [
        dict(case) for case in cases_raw if isinstance(case, Mapping)
    ] if isinstance(cases_raw, list) else []

    if changed_functions is None:
        selected = cases
    else:
        changed = {
            _normalize_function_name(fn)
            for fn in changed_functions
            if _normalize_function_name(fn)
        }
        if not changed:
            selected = cases
        else:
            unknown = sorted(fn for fn in changed if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME)
            if unknown:
                raise ValueError(f"unknown changed engine functions: {unknown}")

            coverage = corpus.get("coverage")
            coverage = coverage if isinstance(coverage, Mapping) else {}
            authored_inventory_available = bool(
                coverage.get("authoredFunctionInventoryAvailable")
            )
            selected_by_id: dict[str, dict[str, Any]] = {}
            uncovered: list[str] = []
            for fn in sorted(changed):
                spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[fn]
                if spec.lowerers and authored_inventory_available:
                    # New corpora retain exact typed Author identity.  Falling back
                    # to every normalized shoot_projectile case here would hide a
                    # missing typed-family fixture behind unrelated executor cases.
                    matches = [
                        case for case in cases
                        if fn in case_authored_function_set(case)
                    ]
                else:
                    impacted = engine_function_impact_names(fn)
                    matches = [
                        case for case in cases
                        if case_impact_function_set(case).intersection(impacted)
                    ]
                if not matches:
                    uncovered.append(fn)
                    continue
                for case in matches:
                    case_id = str(case.get("caseId") or "")
                    selected_by_id[case_id] = case

            if uncovered:
                raise ValueError(
                    "historical replay corpus has no coverage for changed engine functions: "
                    f"{uncovered}"
                )
            selected = list(selected_by_id.values())

    selected.sort(key=lambda case: str(case.get("caseId") or ""))
    return selected


def select_cases_by_changed_forms(
    corpus: Mapping[str, Any],
    changed_forms: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Select exact ``function:param.path`` impacts and fail closed on gaps.

    Typed source forms are lowered through ``engine_function_form_impacts``.  Legacy
    corpus rows therefore remain selectable without a hand-written source/target map.
    Empty/None forms mean full replay, matching the changed-function selector.
    """

    cases_raw = corpus.get("cases")
    cases: list[dict[str, Any]] = [
        dict(case) for case in cases_raw if isinstance(case, Mapping)
    ] if isinstance(cases_raw, list) else []
    if changed_forms is None:
        return sorted(cases, key=lambda case: str(case.get("caseId") or ""))

    raw_forms = [str(form or "").strip() for form in changed_forms if str(form or "").strip()]
    if not raw_forms:
        return sorted(cases, key=lambda case: str(case.get("caseId") or ""))

    case_forms = {
        str(case.get("caseId") or ""): function_forms_from_runtime_plan(
            case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
        )
        for case in cases
    }
    authored_case_forms = {
        str(case.get("caseId") or ""): case_authored_form_set(case)
        for case in cases
    }
    normalized_case_forms = {
        str(case.get("caseId") or ""): normalized_function_forms_from_runtime_plan(
            case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
        )
        for case in cases
    }
    coverage = corpus.get("coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    authored_inventory_available = bool(
        coverage.get("authoredFunctionInventoryAvailable")
    )
    selected_by_id: dict[str, dict[str, Any]] = {}
    uncovered: list[str] = []
    for raw_form in sorted(set(raw_forms)):
        if ":" not in raw_form:
            raise ValueError(
                f"changed form must use 'function:param.path' syntax: {raw_form!r}"
            )
        raw_fn, raw_path = raw_form.split(":", 1)
        fn = _normalize_function_name(raw_fn)
        path = raw_path.strip()
        if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME:
            raise ValueError(f"unknown changed engine function in form: {fn!r}")
        spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[fn]
        impacts = engine_function_form_impacts(fn, path)
        if not impacts:
            raise ValueError(f"unknown or unbound changed engine form: {fn}:{path}")
        if spec.lowerers and authored_inventory_available:
            # Provenance-aware witnesses retain the exact typed source form.  Do
            # not broaden a deploy_sentry field change to every historical
            # shoot_projectile row merely because both lower to one executor.
            matches = [
                case
                for case in cases
                if fn in case_authored_function_set(case)
                and (fn, path)
                in authored_case_forms[str(case.get("caseId") or "")]
            ]
        else:
            matches = [
                case
                for case in cases
                if (
                    case_forms[str(case.get("caseId") or "")]
                    | normalized_case_forms[str(case.get("caseId") or "")]
                ).intersection(impacts)
            ]
        if not matches:
            uncovered.append(f"{fn}:{path}")
            continue
        for case in matches:
            selected_by_id[str(case.get("caseId") or "")] = case

    if uncovered:
        raise ValueError(
            "historical replay corpus has no coverage for changed engine forms: "
            f"{uncovered}"
        )
    return sorted(selected_by_id.values(), key=lambda case: str(case.get("caseId") or ""))


def stable_final_sections_fingerprint(compile_result: Mapping[str, Any]) -> str:
    """Stable fingerprint of compiler-owned final sections (+ identity)."""
    payload = {
        "identity": compile_result.get("identity"),
        "finalSections": compile_result.get("finalSections"),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


def compile_input_from_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Build the minimal production compile input from a corpus case."""
    plan = case.get("runtimePlan")
    if not isinstance(plan, Mapping):
        raise ValueError("case.runtimePlan must be an object")
    runtime_plan = copy.deepcopy(dict(plan))
    # Defensive strip if an older dump leaked prose keys.
    for key in PROSE_RUNTIME_PLAN_KEYS:
        runtime_plan.pop(key, None)
    category = case.get("category") or case.get("resultKind") or runtime_plan.get("resultKind")
    data: dict[str, Any] = {
        "category": category,
        "runtimePlan": runtime_plan,
    }
    return data


def replay_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Replay one historical case through production final projection compile.

    Uses compile_runtime_plan_to_final_result (production path). No network.
    """
    case_id = str(case.get("caseId") or _safe_token(case.get("case")))
    report: dict[str, Any] = {
        "caseId": case_id,
        "ok": False,
        "error": None,
        "fingerprint": None,
        "expectedFingerprint": case.get("expectedFinalSectionsFingerprint"),
        "result": None,
        "functions": sorted(case_function_set(case)),
    }
    try:
        data = compile_input_from_case(case)
        result = compile_runtime_plan_to_final_result(data)
        if not isinstance(result, dict):
            raise TypeError("compile_runtime_plan_to_final_result returned non-object")
        rejected = result.get("rejectedEngineCalls") or []
        if rejected:
            raise ValueError(f"production compiler returned rejected engine calls: {rejected}")
        receipts = result.get("finalWireReceipts") or []
        dropped = [
            row
            for row in receipts
            if isinstance(row, Mapping) and str(row.get("status") or "") == "dropped"
        ]
        if dropped:
            raise ValueError(f"production compiler returned dropped final-wire receipts: {dropped}")
        validation = result.get("validation")
        if isinstance(validation, Mapping) and validation.get("ok") is False:
            raise ValueError(f"production compiler validation failed: {dict(validation)}")
        fingerprint = stable_final_sections_fingerprint(result)
        report["fingerprint"] = fingerprint
        report["result"] = {
            "schema": result.get("schema"),
            "identity": copy.deepcopy(result.get("identity")),
            "finalSections": copy.deepcopy(result.get("finalSections")),
            "rejectedEngineCalls": copy.deepcopy(result.get("rejectedEngineCalls") or []),
            "finalWireReceipts": copy.deepcopy(result.get("finalWireReceipts") or []),
            "validation": copy.deepcopy(result.get("validation") or {}),
        }
        expected = case.get("expectedFinalSectionsFingerprint")
        if expected and fingerprint != expected:
            report["error"] = (
                f"fingerprint mismatch: got {fingerprint}, expected {expected}"
            )
            report["ok"] = False
        else:
            report["ok"] = True
    except Exception as exc:  # surface compile crashes as failed reports
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["ok"] = False
    return report


def replay_cases(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Replay many cases; preserves input order."""
    return [replay_case(case) for case in cases]


def executable_runtime_plan_from_dump(runtime_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Strip prose and internal keys; keep engineCalls + structural resultKind."""
    calls_out: list[dict[str, Any]] = []
    raw_calls = runtime_plan.get("engineCalls")
    if isinstance(raw_calls, list):
        for raw in raw_calls:
            if not isinstance(raw, Mapping):
                continue
            fn = str(raw.get("fn") or "").strip()
            if not fn:
                continue
            params_in = raw.get("params") if isinstance(raw.get("params"), Mapping) else {}
            params = {
                str(key): copy.deepcopy(value)
                for key, value in dict(params_in or {}).items()
                if not str(key).startswith("_")
            }
            call_id = str(raw.get("callId") or "").strip()
            if not call_id:
                continue
            calls_out.append({"callId": call_id, "fn": fn, "params": params})
    plan: dict[str, Any] = {
        "resultKind": runtime_plan.get("resultKind"),
        "engineCalls": calls_out,
    }
    # Optional structural (non-prose) metadata.
    flags = runtime_plan.get("anomalyFlags")
    if isinstance(flags, list) and flags:
        plan["anomalyFlags"] = copy.deepcopy(flags)
    return plan


def call_shapes_from_plan(runtime_plan: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    """Accepted call-shapes: (fn, sorted param keys)."""
    shapes: list[tuple[str, tuple[str, ...]]] = []
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return shapes
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = str(call.get("fn") or "").strip()
        if not fn:
            continue
        params = call.get("params") if isinstance(call.get("params"), Mapping) else {}
        shapes.append((fn, tuple(sorted(str(k) for k in dict(params or {}).keys()))))
    return shapes


def make_case_id(source_run: str, case_name: str, plan_key: str) -> str:
    short = hashlib.sha256(plan_key.encode("utf-8")).hexdigest()[:10]
    base = f"{_safe_token(source_run)}__{_safe_token(case_name)}"
    return f"{base}__{short}"


__all__ = [
    "CONTRACT_FINGERPRINT_SCHEMA",
    "CORPUS_SCHEMA",
    "DEFAULT_CORPUS_PATH",
    "PROSE_RUNTIME_PLAN_KEYS",
    "call_shapes_from_plan",
    "canonical_json",
    "case_authored_function_set",
    "case_function_set",
    "case_impact_function_set",
    "compile_input_from_case",
    "corpus_function_set",
    "default_corpus_path",
    "deterministic_contract_witness_candidates",
    "diff_runtime_contract_fingerprints",
    "executable_runtime_plan_from_dump",
    "authored_functions_from_runtime_plan",
    "authored_function_forms_from_runtime_plan",
    "case_authored_form_set",
    "functions_from_runtime_plan",
    "function_forms_from_runtime_plan",
    "load_corpus",
    "make_case_id",
    "normalized_functions_from_runtime_plan",
    "replay_case",
    "replay_cases",
    "runtime_contract_fingerprint_manifest",
    "select_cases_by_changed_functions",
    "select_cases_by_changed_forms",
    "stable_final_sections_fingerprint",
]
