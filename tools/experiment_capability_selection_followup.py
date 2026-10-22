"""Controlled offline continuation; no provider requests, feedback or repair."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

from experiment_capability_selection import read, write
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.qa.capability_selection_experiment import build_selector_packet, build_author_variant

CASES = ("wand", "musket", "tool")
ARMS = ("baseline", "groups_full", "groups", "capabilities_full", "capabilities")
REPEATS = (1, 2)
POLICY = "selected_only"


def author_id(arm, case, repeat):
    return hashlib.sha256(f"round2/{arm}/{case}/{repeat}".encode()).hexdigest()[:12]


def prepare(root, previous):
    trials = []
    for case in CASES:
        payload = read(previous / "packets" / "baseline" / f"{case}.json")
        if case == "tool":
            payload["experimentBrief"] += " Input isolation is required: primary must not launch the returning projectile, and alternate must not launch the straight projectile. Held effects must not occupy either active action."
        write(root / "sources" / f"{case}.json", payload)
        for repeat in REPEATS:
            for mode in ("groups", "capabilities"):
                packet = build_selector_packet(payload, mode, policy=POLICY)
                write(root / "selectors" / mode / f"{case}_r{repeat}.json", packet)
            for arm in ARMS:
                trial = {"id": author_id(arm, case, repeat), "arm": arm, "case": case, "repeat": repeat}
                trials.append(trial)
                if arm == "baseline":
                    write(root / "author_packets" / f"{trial['id']}.json", payload)
    write(root / "protocol.json", {
        "schema": "ifc.selection-followup.v1", "documentationPolicy": POLICY,
        "cases": CASES, "repeats": REPEATS, "arms": ARMS, "trials": trials,
        "selection": "4 fresh Luna sessions: one per mode/repeat, each selecting three cases; batch is the independent selector unit",
        "author": "30 fresh GPT-6 Luna high sessions; one packet and one frozen answer each; no validator feedback or repair",
        "controls": "Within each mode/case/repeat, full and reduced share the exact same selector intent and source context",
        "limits": ["no paid provider requests", "no constrained decoding", "no billed reasoning/cache/latency measurement",
                   "two replicates per case/arm, not a reliability estimate", "no game smoke"],
        "secondaryPreservation": "All 73 IDs remain discoverable; index-only cards lack full parameter grammar, so losslessness is NOT guaranteed",
        "trap": "Excluded from comparative pass rate because original conjunction is not executable; retained as a separate catalogue diagnostic",
        "primaryOutcome": "canonical validation AND all preregistered function checks; not validator alone",
        "functionChecks": {
            "wand": ["primary magic damage", "gravity on primary projectile", "on-hit owner healing", "equipped defense and regeneration"],
            "musket": ["fallen-star ammo consumption", "primary damaging gravity projectile", "on-hit reachable damaging homing child"],
            "tool": ["native primary pick action", "primary straight damaging projectile", "alternate returning damaging projectile isolated from primary", "same-group held ore detection and regeneration"],
        },
    })


def assemble(root):
    protocol = read(root / "protocol.json")
    for trial in protocol["trials"]:
        if trial["arm"] == "baseline":
            continue
        arm, case, repeat = trial["arm"], trial["case"], trial["repeat"]
        mode = arm.removesuffix("_full")
        path = root / "selections" / mode / f"{case}_r{repeat}.json"
        if not path.exists():
            continue
        selection = read(path)
        payload = read(root / "sources" / f"{case}.json")
        # Validate original selection before constructing its matched control.
        reduced, audit = build_author_variant(payload, mode, selection, policy=POLICY)
        if arm.endswith("_full"):
            full_choice = {**selection, "fullCatalog": True}
            packet, audit = build_author_variant(payload, mode, full_choice, policy=POLICY)
            assert packet["selectionIntent"] == reduced["selectionIntent"]
            assert packet["parents"] == reduced["parents"]
        else:
            packet = reduced
        write(root / "author_packets" / f"{trial['id']}.json", packet)
        write(root / "audit" / f"{trial['id']}.json", audit)


def functional_checks(document, case):
    """Case rubric on explicit reachable paths; not a general runtime validator.

    Call presence alone is insufficient. Validate exact parameter conditions and
    producer/target links. Canonical admission is scored separately.
    """
    p = document.get("runtimeProgram", {})
    entities = p.get("entities", [])
    body = next((e.get("id") for e in entities if e.get("kind") == "item_body"), None)
    calls = p.get("calls", [])
    bindings = p.get("bindings", [])

    def find(fn, target=None):
        return [c for c in calls if c.get("fn") == fn and (target is None or c.get("target", body) == target)]

    def params(fn, target):
        return [c.get("params", {}) for c in find(fn, target)]

    def roots(input_name):
        return [b.get("action", {}).get("targetId") for b in bindings
                if b.get("input") == input_name and b.get("action", {}).get("kind") == "spawn_entity"]

    def damaging(target, damage_class=None):
        return any(x.get("damage", 0) > 0 and (damage_class is None or x.get("damageClass") == damage_class)
                   for x in params("set_projectile_damage", target))

    def hit_edges(target):
        return [x for x in params("spawn_entity_on_event", target) if x.get("when") == "on_hit"]

    def damaging_child(root, event):
        child = event.get("entity")
        # live_parent selects a combat source, but does not enable child damage.
        # An explicit zero-base child damage capability DOES enable that gate.
        if not find("set_projectile_damage", child) or event.get("damageMultiplier", 0) <= 0:
            return False
        return damaging(root) if event.get("damageBasis") == "live_parent" else damaging(child)

    primary, alternate = roots("primary_use"), roots("alternate_use")
    if case == "wand":
        magic = [r for r in primary if damaging(r, "magic")]
        return {
            "primary_magic_damage": bool(magic),
            "gravity_on_primary": any(find("move_gravity_arc", r) for r in magic),
            "on_hit_owner_healing": any(x.get("when") == "on_hit" and x.get("damageFraction", 0) > 0 and x.get("maxHeal", 0) > 0
                                        for r in magic for x in params("heal_owner_on_event", r)),
            "equipped_defense_regeneration": any(b.get("input") == "equipped" for b in bindings)
                and any(x.get("defensePoints", 0) > 0 and x.get("lifeRegenHpPerSecond", 0) > 0 for x in params("configure_accessory", body)),
        }
    if case == "musket":
        gravity = [r for r in primary if damaging(r) and find("move_gravity_arc", r)]
        return {
            "native_star_ammo": bool(primary) and any(x.get("ammoCategory") == "fallen_star" for x in params("configure_weapon_ammo", body)),
            "primary_gravity_damage": bool(gravity),
            "reachable_hit_homing_child": any(event.get("entity") != root and damaging_child(root, event)
                                               and find("move_slow_homing", event.get("entity"))
                                               for root in gravity for event in hit_edges(root)),
        }
    if case == "tool":
        straight = [r for r in primary if damaging(r) and find("move_straight", r)]
        returning = [r for r in alternate if damaging(r) and find("move_boomerang", r)]
        # Shared body.on_use producers belong to both active input paths.
        def reachable_from(roots):
            reachable = set(roots)
            reachable.update(x.get("entity") for x in params("spawn_entity_on_event", body) if x.get("when") == "on_use")
            while True:
                expanded = reachable | {x.get("entity") for r in reachable for x in params("spawn_entity_on_event", r)}
                expanded |= {x.get("shotEntity") for r in reachable for x in params("target_and_fire", r)}
                expanded.discard(None)
                if expanded == reachable:
                    return reachable
                reachable = expanded
        groups = {x.get("effectGroupId") for x in params("refresh_generated_effect_group_while_held", body)} - {None}
        held = any(x.get("effectGroupId") in groups and x.get("oreSenseEnabled") is True and x.get("lifeRegenHpPerSecond", 0) > 0
                   for x in params("apply_generated_buff_on_use", body))
        occupied = any(b.get("input") in {"primary_use", "alternate_use"}
                       and b.get("action", {}).get("kind") == "apply_item_effects"
                       and b["action"].get("effectGroupId") in groups for b in bindings)
        return {
            "native_primary_pick": bool(primary) and any(x.get("pickPower", 0) > 0 for x in params("configure_tool", body)),
            "primary_straight_damage": bool(straight),
            "isolated_alternate_returner": bool(returning) and not set(returning) & reachable_from(primary) and not set(straight) & reachable_from(alternate),
            "held_ore_regeneration": held and not occupied,
        }
    raise ValueError(case)


def evaluate(root):
    import tiktoken
    encoding = tiktoken.get_encoding("o200k_base")
    tokens = lambda value: len(encoding.encode(json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
    rows = []
    for trial in read(root / "protocol.json")["trials"]:
        row = dict(trial)
        packet_path = root / "author_packets" / f"{trial['id']}.json"
        if not packet_path.exists():
            row["notAssembled"] = True
            rows.append(row)
            continue
        packet = read(packet_path)
        row["authorInputProxy"] = tokens(packet)
        row["packetSha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        if trial["arm"] != "baseline":
            mode = trial["arm"].removesuffix("_full")
            key = f"{trial['case']}_r{trial['repeat']}.json"
            row["selectorInputProxy"] = tokens(read(root / "selectors" / mode / key))
            row["selectorOutputProxy"] = tokens(read(root / "selections" / mode / key))
            row["detailedCapabilities"] = len(packet["runtimeCapabilityContract"]["catalog"]["capabilities"])
        output = root / "outputs" / f"{trial['id']}.json"
        if not output.exists():
            row["notRun"] = True
        else:
            row["outputSha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
            try:
                document = read(output)
                validation = validate_runtime_program(document)
                row.update(valid=validation["ok"], errors=validation.get("errors", []), authorOutputProxy=tokens(document))
                row["functions"] = functional_checks(document, trial["case"])
                detailed = {c["fn"] for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"]}
                row["indexOnlyUsed"] = sorted({c.get("fn", "") for c in document.get("runtimeProgram", {}).get("calls", [])} - detailed)
                row["allFunctions"] = all(row["functions"].values())
                row["acceptedAndPreserved"] = row["valid"] and row["allFunctions"]
                if row["valid"]:
                    compile_runtime_program(document)
                    row["compiled"] = True
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                row.update(evaluationError=f"{type(exc).__name__}: {exc}", acceptedAndPreserved=False)
        rows.append(row)
    write(root / "results.json", {"rows": rows, "tokenizer": "o200k_base proxy, no billed API usage"})
    measure_wire(root, encoding)
    print(json.dumps([{k: v for k, v in row.items() if k not in {"errors", "packetSha256", "outputSha256"}} for row in rows], indent=2))


def measure_wire(root, encoding):
    """Offline schema/layout/hash inspection, never provider cache hit claims."""
    from infini_local.core.llm_prompt_cache import with_instruction_segments
    from infini_local.pipelines.author_item_contract import author_item_provider_response_schema
    from infini_local.pipelines.llm_provider_wire import _prompt_cache_identity

    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    tokens = lambda value: encoding.encode(encode(value))
    owner = Path(__file__).resolve().parents[1] / "LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py"
    # Read literal canonical system/boundary without importing the API pipeline.
    literals = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(owner.read_text()).body
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"_AUTHOR_SYSTEM", "_AUTHOR_CACHE_PREFIX_KEYS"}}
    schema = author_item_provider_response_schema()
    response_format = {"type": "json_schema", "json_schema": {"name": "infini_low_level_runtime_author", "strict": True, "schema": schema}}
    rows = []
    trials = read(root / "protocol.json")["trials"]
    for arm in ARMS:
        sequences, keys, content_sizes = [], [], []
        for trial in (t for t in trials if t["arm"] == arm):
            path = root / "author_packets" / f"{trial['id']}.json"
            if not path.exists():
                continue
            packet = read(path)
            request = {"messages": [{"role": "system", "content": literals["_AUTHOR_SYSTEM"]},
                                    {"role": "user", "content": encode(packet)}], "response_format": response_format}
            request = with_instruction_segments(request, packet, literals["_AUTHOR_CACHE_PREFIX_KEYS"])
            keys.append(_prompt_cache_identity(request, "gpt-6-luna"))
            sequences.append(tokens(packet))
            content_sizes.append(sum(len(encoding.encode(m["content"])) for m in request["messages"]) + len(tokens(response_format)))
        if not sequences:
            continue
        prefix = next((i for i, values in enumerate(zip(*sequences)) if len(set(values)) != 1), min(map(len, sequences)))
        rows.append({"arm": arm, "commonAuthorPrefixProxy": prefix, "distinctDerivedCacheKeys": len(set(keys)),
                     "messageContentPlusResponseFormatMeanProxy": sum(content_sizes) / len(content_sizes), "cacheKeys": keys})
    write(root / "wire_measurement.json", {
        "fullProviderSchemaTokensProxy": len(tokens(schema)), "rows": rows,
        "note": "Canonical ordinary-provider instruction split and content-derived cache routing hint. Counts message contents plus response_format serialization separately, without outer JSON escaping. Environment system suffix/options and provider framing excluded. No actual schema accounting, constrained decoding or cache hits measured.",
        "schemaIncludedInAuthorTrials": False,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "assemble", "evaluate"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if args.previous is None:
            parser.error("prepare requires --previous")
        prepare(args.root, args.previous)
    elif args.action == "assemble":
        assemble(args.root)
    else:
        evaluate(args.root)


if __name__ == "__main__":
    main()
