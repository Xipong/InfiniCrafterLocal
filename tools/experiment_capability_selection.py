"""Offline packet builder/evaluator. Never sends API requests or changes craft.

prepare takes the user's stage_requests.zip, assemble consumes first-pass selector
JSONs, evaluate validates frozen Author outputs without repair. See the experiment
report for subagent instructions and the limits of this small stress-test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalGenerator"))

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload, source_wire_units_for_llm
from infini_local.qa.capability_selection_experiment import build_author_variant, build_selector_packet, MODES


CASES = {
    "wand": ("r_644814a304c6e125cfe85592", "Stress-test design brief, not extra observed parent facts: keep a primary magic ember projectile with gravity and on-hit owner healing; also make the item wearable as an accessory granting positive defense and life regeneration. Preserve both active and equipped functions. Do not claim defense merely from holding it."),
    "trap": ("r_8a8e8749e7f31b3b501f7d54", "Stress-test design brief: primary use controls a tethered hovering trap which periodically fires separate straight-moving damaging darts at nearby enemies. Alternate use places the native gray pressure plate from parent A, using its exact native tile/style. Keep the placed plate and active projectile trap as separate functions; do not claim the placed plate is a shooting turret."),
    "musket": ("r_c5e9826181107dedc5319164", "Stress-test design brief: consume fallen-star ammunition for the primary shot. The main projectile follows a gravity arc; its on-hit event spawns a separate slowly homing child star. Keep both movements on their respective entities and preserve actual ammunition consumption. The weapon itself is not a vanilla ammunition item."),
    "tool": (None, "Synthetic stress-test brief: create a real native mining tool with positive pick power. Primary use mines with the item and also spawns a straight damaging projectile, without claiming that the projectile mines. Alternate use fires a boomerang-like returning projectile. While held, refresh a generated effect group providing ore detection and modest life regeneration. Keep all four functions. Defense while held is not requested. Parents below are deliberately empty synthetic context, not observed game facts; choose bounded authored values."),
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(archive, root):
    contexts = {}
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if name.startswith("stage_requests/") and name.endswith(".json"):
                row = json.loads(source.read(name))
                if row.get("stage") == "gameplay_author":
                    contexts[row["recipeKey"]] = json.loads(next(m["content"] for m in row["messages"] if m["role"] == "user"))
    for case, (key, brief) in CASES.items():
        payload = build_llm_author_payload({}, {}, key or "synthetic_tool")
        if key:
            original = contexts[key]
            for field in ("parents", "balanceCorridor"):
                payload[field] = original[field]
            payload["sourceWireUnits"] = source_wire_units_for_llm([p["packet"] for p in payload["parents"].values()])
        payload["experimentBrief"] = brief
        write(root / "packets" / "baseline" / f"{case}.json", payload)
        for mode in MODES:
            write(root / "selectors" / mode / f"{case}.json", build_selector_packet(payload, mode))
    write(root / "manifest.json", {"cases": CASES, "archive": Path(archive).name, "providerCalls": 0})


def assemble(root):
    for mode in MODES:
        for case in CASES:
            payload = read(root / "packets" / "baseline" / f"{case}.json")
            selection = read(root / "selections" / mode / f"{case}.json")
            packet, audit = build_author_variant(payload, mode, selection)
            write(root / "packets" / mode / f"{case}.json", packet)
            write(root / "audit" / mode / f"{case}.json", audit)


def evaluate(root):
    import tiktoken  # Optional measurement dependency; no provider/tokenizer claim.
    encoding = tiktoken.get_encoding("o200k_base")

    def tokens(value):
        return len(encoding.encode(json.dumps(value, ensure_ascii=False, separators=(",", ":"))))

    rows = []
    for mode in ("baseline", *MODES):
        for case in CASES:
            packet = read(root / "packets" / mode / f"{case}.json")
            row = {"mode": mode, "case": case, "authorPayloadTokensProxy": tokens(packet)}
            if mode != "baseline":
                audit = read(root / "audit" / mode / f"{case}.json")
                row.update(selectorPacketTokensProxy=tokens(read(root / "selectors" / mode / f"{case}.json")),
                           selectorOutputTokensProxy=tokens(read(root / "selections" / mode / f"{case}.json")),
                           detailedCapabilities=len(audit["detailedIds"]), indexOnlyIds=audit["indexOnlyIds"],
                           fullCatalog=audit["explicitFullCatalog"])
            output = root / "outputs" / mode / f"{case}.json"
            if output.exists():
                try:
                    document = read(output)
                except (ValueError, UnicodeError) as exc:
                    row.update(valid=False, parseError=str(exc))
                else:
                    report = validate_runtime_program(document)
                    row.update(valid=report["ok"], errors=report.get("errors", []), authorOutputTokensProxy=tokens(document))
                    calls = document.get("runtimeProgram", {}).get("calls", [])
                    row["capabilitiesUsed"] = sorted({c.get("fn", "") for c in calls})
                    if report["ok"]:
                        compiled = compile_runtime_program(document)
                        write(root / "compiled" / mode / f"{case}.json", compiled)
                        row["compiled"] = True
            else:
                row["notRun"] = True
            rows.append(row)
    prefix_rows = []
    for mode in ("baseline", *MODES):
        for stage in (("packets",) if mode == "baseline" else ("packets", "selectors")):
            encoded = [encoding.encode(json.dumps(read(root / stage / mode / f"{case}.json"),
                       ensure_ascii=False, separators=(",", ":"))) for case in CASES]
            common = next((i for i, values in enumerate(zip(*encoded)) if len(set(values)) != 1), min(map(len, encoded)))
            prefix_rows.append({"mode": mode, "stage": stage, "sharedPrefixTokensProxy": common})
    write(root / "results.json", {
        "tokenizer": "o200k_base proxy; JSON compact serialization, not billed API usage",
        "limits": ["subagent first attempts, not provider requests", "no schema-constrained decoding",
                   "no repairs", "no billed or reasoning-token usage", "no measured cache hits",
                   "no Terraria smoke run", "one trial per case per arm"],
        "rows": rows, "commonPrefixes": prefix_rows,
    })
    print(json.dumps([{k: v for k, v in r.items() if k not in {"errors", "indexOnlyIds", "capabilitiesUsed"}} for r in rows], ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "assemble", "evaluate"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if args.archive is None:
            parser.error("prepare requires --archive")
        prepare(args.archive, args.root)
    elif args.action == "assemble":
        assemble(args.root)
    else:
        evaluate(args.root)


if __name__ == "__main__":
    main()
