from __future__ import annotations

"""Generate real GeneratedItemData for golden runtime cases via combine().

Uses LLM replay fixtures so generation is deterministic and offline-friendly.
Sprites are not required (image backend off). This proves the full Python
authoring → repair → gameplay/attack → final_normalize path for each case.
"""

import argparse
import json
import os
import shutil
import sys
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "agent_reports" / "runtime_proof_items"


def _configure_env(cache_dir: Path, replay_dir: Path) -> None:
    os.environ["INFINI_USE_LLM"] = "1"
    os.environ["INFINI_LLM_RUNTIME_AUTHORING"] = "1"
    os.environ["INFINI_LLM_RUNTIME_PLAN_REQUIRED"] = "1"
    os.environ["INFINI_LLM_RUNTIME_STRICT_VALIDATION"] = "0"
    os.environ["INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK"] = "0"
    os.environ["INFINI_IMAGE_BACKEND"] = "off"
    os.environ["INFINI_VISUAL_REQUIRE_ITEM_SPRITE"] = "0"
    os.environ["INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND"] = "0"
    os.environ["INFINI_VISUAL_STRICT_AI_AUTHORSHIP"] = "0"
    os.environ["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "1"
    os.environ["INFINI_VISUAL_DIRECTOR_LLM"] = "0"
    os.environ["INFINI_VFX_LLM_DIRECTOR"] = "0"
    os.environ["INFINI_CACHE_DIR"] = str(cache_dir)
    os.environ["INFINI_LLM_REPLAY_RAW"] = str(replay_dir)
    # Avoid accidental network if replay misses a stage.
    os.environ.setdefault("INFINI_LLM_PROVIDER", "openai_compat")


def _parent(name: str = "Wooden Sword", *, damage: int = 10, damage_class: str = "melee", **extra: Any) -> dict[str, Any]:
    item = {
        "name": name,
        "internalName": name.replace(" ", "").replace("'", ""),
        "sourceMod": "Terraria",
        "fullName": "Terraria/" + name.replace(" ", "").replace("'", ""),
        "damage": damage,
        "damageClass": damage_class,
        "useStyle": 1,
        "useTime": 20,
        "useAnimation": 20,
        "rare": 1,
        "value": 100,
        "maxStack": 1,
        "shoot": 0,
        "shootSpeed": 0.0,
        "tags": [],
    }
    item.update(extra)
    return item


def _author_plan(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("caseId") or "case")
    inp = deepcopy(case.get("input") or {})
    runtime_plan = inp.get("runtimePlan") if isinstance(inp.get("runtimePlan"), dict) else {"engineCalls": []}
    category = str(inp.get("category") or "weapon")
    plan = {
        "name": f"Golden {case_id.replace('_', ' ').title()}",
        "tooltip": str(case.get("description") or case_id),
        "category": category,
        "concept": {
            "fantasy": str(case.get("description") or case_id),
            "mergeLogic": "Golden runtime proof case: authored engineCalls are the executable intent.",
            "weirdTwist": "Deterministic golden-case authoring for runtime proof.",
        },
        "runtimePlan": runtime_plan,
        "visual": {
            "itemPrompt": f"terraria-style item sprite for {case_id}",
            "projectilePrompt": f"terraria-style projectile for {case_id}",
        },
        "debug": {"planner": "llm", "goldenCaseId": case_id},
    }
    return plan


def _write_replay(replay_dir: Path, plan: dict[str, Any]) -> None:
    if replay_dir.exists():
        shutil.rmtree(replay_dir)
    replay_dir.mkdir(parents=True, exist_ok=True)
    planner = json.dumps(plan, ensure_ascii=False, indent=2)
    (replay_dir / "planner.txt").write_text(planner, encoding="utf-8")
    (replay_dir / "default.txt").write_text("{}", encoding="utf-8")
    (replay_dir / "vfx_director.txt").write_text(
        json.dumps({"visualKit": {"itemSpritePrompt": plan["visual"]["itemPrompt"], "projectileSpritePrompt": plan["visual"]["projectilePrompt"], "negativePrompt": ""}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (replay_dir / "author_repair.txt").write_text(planner, encoding="utf-8")
    (replay_dir / "genome_repair.txt").write_text("{}", encoding="utf-8")
    (replay_dir / "name_repair.txt").write_text(json.dumps({"name": plan["name"]}, ensure_ascii=False), encoding="utf-8")
    (replay_dir / "llm.txt").write_text("{}", encoding="utf-8")


def _compact(item: dict[str, Any], case_id: str, mismatches: list[str], error: str | None) -> dict[str, Any]:
    gp = item.get("gameplay") if isinstance(item.get("gameplay"), dict) else {}
    at = item.get("attack") if isinstance(item.get("attack"), dict) else {}
    return {
        "caseId": case_id,
        "ok": not mismatches and not error,
        "error": error,
        "mismatches": mismatches,
        "name": item.get("name"),
        "category": item.get("category"),
        "gameplay": {
            k: gp.get(k)
            for k in (
                "kind",
                "damage",
                "damageClass",
                "useTime",
                "manaCost",
                "pickPower",
                "axePower",
                "miningSpeedScale",
                "runtimeLightStrength",
                "runtimeLightColorName",
                "mobilityMode",
                "mobilityRangeTiles",
                "mobilityCooldownTicks",
                "mobilitySafeTileOnly",
                "maxStack",
            )
            if k in gp
        },
        "attack": {
            k: at.get(k)
            for k in (
                "enabled",
                "runtimeFamily",
                "delivery",
                "movement",
                "effect",
                "onHit",
                "weaponFamily",
                "runtimePlanAuthored",
                "speed",
            )
            if k in at
        },
        "accessory": item.get("accessory") if isinstance(item.get("accessory"), dict) else {},
        "armor": item.get("armor") if isinstance(item.get("armor"), dict) else {},
        "spriteStatus": ((item.get("visual") or {}) if isinstance(item.get("visual"), dict) else {}).get("spriteStatus"),
    }


def generate(out_dir: Path) -> dict[str, Any]:
    cache_dir = out_dir / "_cache"
    replay_root = out_dir / "_replay"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Env must be set before importing pipeline modules.
    _configure_env(cache_dir, replay_root / "bootstrap")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from infini_local.pipelines.combine_pipeline import combine
    from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
    from infini_local.qa.runtime_proof import _mismatches_for_gameplay_expect

    rows: list[dict[str, Any]] = []
    for case in GOLDEN_RUNTIME_CASES:
        case_id = str(case.get("caseId") or "case")
        case_replay = replay_root / case_id
        plan = _author_plan(case)
        _write_replay(case_replay, plan)
        os.environ["INFINI_LLM_REPLAY_RAW"] = str(case_replay)

        payload = {
            "itemA": _parent(),
            "itemB": _parent(name="Iron Broadsword", damage=12),
            "worldId": f"qa_runtime_items_{case_id}",
            "worldName": "RuntimeProof",
            "recipeIdentityVersion": "qa_runtime_items_v1",
        }
        error: str | None = None
        item: dict[str, Any] = {}
        mismatches: list[str] = []
        try:
            item = combine(payload)
            report = {
                "item": {
                    "category": item.get("category"),
                    "gameplay": item.get("gameplay") or {},
                    "attack": item.get("attack") or {},
                    "accessory": item.get("accessory") or {},
                    "armor": item.get("armor") or {},
                },
                "error": None,
            }
            mismatches = _mismatches_for_gameplay_expect(report, case.get("expectGameplay") or {})
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            mismatches = [error]
            traceback.print_exc()

        full_path = out_dir / f"{case_id}.full.json"
        full_path.write_text(json.dumps(item or {"error": error}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        row = _compact(item, case_id, mismatches, error)
        row["fullPath"] = str(full_path)
        rows.append(row)
        print(json.dumps({"caseId": case_id, "ok": row["ok"], "mismatches": mismatches[:4], "error": error}, ensure_ascii=False))

    failed = [r for r in rows if not r["ok"]]
    summary = {
        "ok": not failed,
        "caseCount": len(rows),
        "failedCount": len(failed),
        "cases": rows,
        "note": "Full Python combine generation from golden authored runtimePlans via LLM replay; image backend off.",
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["summaryPath"] = str(summary_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate real GeneratedItemData for golden runtime cases.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    summary = generate(args.out)
    print(json.dumps({k: summary[k] for k in ("ok", "caseCount", "failedCount", "summaryPath")}, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
