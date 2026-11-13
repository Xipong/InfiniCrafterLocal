"""Native composite parent handoff acceptance; no generation or network calls.

Run from repo root with PYTHONPATH=generator:tests/generator. This expects a
real Dragon+Cell Prepare export; it does not certify gameplay or missing profiles.
Repair uses an empty scope solely to exercise its independent parent handoff."""

import argparse
import copy
import json
from pathlib import Path

from infini_local.core import llm_config
from infini_local.pipelines.author.request import build_initial_author_request, build_gameplay_repair_dossier
from prompt_packet_helpers import request_dossier, expand_native_source_references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="Native Prepare StardustDragonStaff + StardustCellStaff JSON")
    args = parser.parse_args()
    p = json.loads(args.packet.read_text())
    report = []
    for mode in ("json_object", "json_schema"):
        llm_config.LLM_RESPONSE_FORMAT_MODE = mode
        before = copy.deepcopy(p)
        request, *_ = build_initial_author_request(p["itemA"], p["itemB"], "composite-native-audit", model_name="offline")
        dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
        repair = expand_native_source_references(build_gameplay_repair_dossier({}, p["itemA"], p["itemB"], failure_report={"errors": []}))
        assert repair["parents"]["a"]["packet"]["raw"] == dossier["parents"]["A"]["packet"]["raw"], "repair parent context diverges"
        raw = dossier["parents"]["A"]["packet"]["raw"]
        mechanics = raw["mechanics"]
        dispatch = mechanics["itemRules"]["nativeItemDispatchReference"]
        original = p["itemA"]["nativeItemDispatchReference"]

        def mechanical(value):
            if isinstance(value, dict):
                return {k: mechanical(v) for k, v in value.items() if k not in {"sourceMethodSha256", "sourceModuleVersionId"}}
            if isinstance(value, list):
                return [mechanical(v) for v in value]
            return value

        assert mechanical(dispatch) == mechanical(original), "item construction/extension facts changed in actual Author"
        code = "\n".join(r["code"] for r in mechanics["source"])
        original_follower = next(
            (r["code"] for r in p["itemA"]["directProjectileRaw"]["mechanicsSource"]["records"] if "GetByUUID" in r.get("code", "")),
            None,
        )
        assert original_follower is not None, "native capture lost follower branch"
        assert any(r.get("code") == original_follower for r in mechanics["source"]), "complete follower method changed"
        for fact in ("GetByUUID", "localAI[0]", "localAI[1]"):
            assert fact in code, fact
        construction = "\n".join(r["code"] for x in dispatch["roots"] for r in x["records"])
        for fact in ("projToShoot + 1", "projToShoot + 2", "projToShoot + 3", "else if"):
            assert fact in construction, fact
        assert p == before, "source packet mutated"
        report.append(
            dict(
                mode=mode,
                itemDispatchMechanicalFieldsExact=True,
                followerSourceRetained=True,
                repairParentExact=True,
                parentChars=len(json.dumps(raw, ensure_ascii=False, separators=(",", ":"))),
                profileTypes=[x["defaults"].get("type") for x in mechanics["projectiles"]],
            )
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
