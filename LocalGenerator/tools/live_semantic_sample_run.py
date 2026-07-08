from __future__ import annotations

"""Small live LLM sample for semantic/runtime intent QA (no sprites).

Runs a few combine crafts with real LLM, image backend off, and writes:
- full item JSON
- compact semantic audit rows (family/onHit/promises/diversity signals)
"""

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "agent_reports" / "live_semantic_sample"


def load_config_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip().rstrip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def parent(**kw: Any) -> dict[str, Any]:
    base = {
        "name": "Wooden Sword",
        "internalName": "WoodenSword",
        "sourceMod": "Terraria",
        "fullName": "Terraria/WoodenSword",
        "damage": 10,
        "damageClass": "melee",
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
    base.update(kw)
    if "internalName" not in kw:
        base["internalName"] = str(base["name"]).replace(" ", "").replace("'", "")
        base["fullName"] = "Terraria/" + base["internalName"]
    return base


PAIRS: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    (
        "melee_star",
        parent(name="Wooden Sword", damage=10, damageClass="melee"),
        parent(name="Fallen Star", damage=0, damageClass="none", value=500, maxStack=99, consumable=True),
    ),
    (
        "ranged_torch",
        parent(name="Wooden Bow", damage=4, damageClass="ranged", useAmmo=1, shoot=1, shootSpeed=6.6),
        parent(name="Torch", damage=0, damageClass="none", createTile=4, consumable=True, maxStack=999),
    ),
    (
        "magic_gel",
        parent(name="Wand of Sparking", damage=8, damageClass="magic", mana=2, shoot=14, shootSpeed=7),
        parent(name="Gel", damage=0, damageClass="none", maxStack=999, consumable=True),
    ),
    (
        "accessory_boot",
        parent(name="Hermes Boots", damage=0, damageClass="none", accessory=True),
        parent(name="Aglet", damage=0, damageClass="none", accessory=True),
    ),
    (
        "tool_mirror",
        parent(name="Copper Pickaxe", damage=4, damageClass="melee", pick=35),
        parent(name="Magic Mirror", damage=0, damageClass="none", useStyle=4, useTime=90),
    ),
    (
        "boomerang_ice",
        parent(name="Wooden Boomerang", damage=7, damageClass="melee", shoot=52, shootSpeed=6.5, useStyle=1),
        parent(name="Ice Block", damage=0, damageClass="none", createTile=161, consumable=True, maxStack=999),
    ),
    (
        "spear_rope",
        parent(name="Spear", damage=8, damageClass="melee", shoot=49, shootSpeed=3.7, useStyle=5),
        parent(name="Rope", damage=0, damageClass="none", createTile=213, consumable=True, maxStack=999),
    ),
    (
        "summon_flower",
        parent(name="Slime Staff", damage=8, damageClass="summon", mana=10, shoot=266, shootSpeed=10),
        parent(name="Daybloom", damage=0, damageClass="none", maxStack=99, consumable=True),
    ),
    (
        "yoyo_glow",
        parent(name="Rally", damage=14, damageClass="melee", shoot=216, shootSpeed=16, channel=True),
        parent(name="Shine Potion", damage=0, damageClass="none", consumable=True, healLife=0, maxStack=30),
    ),
    (
        "gun_sand",
        parent(name="Minishark", damage=6, damageClass="ranged", useAmmo=14, shoot=14, shootSpeed=7, useTime=8, autoReuse=True),
        parent(name="Sand Block", damage=0, damageClass="none", createTile=53, consumable=True, maxStack=999),
    ),
]


def compact(case_id: str, item: dict[str, Any], error: str | None, ms: int) -> dict[str, Any]:
    gp = item.get("gameplay") if isinstance(item.get("gameplay"), dict) else {}
    at = item.get("attack") if isinstance(item.get("attack"), dict) else {}
    rp = item.get("runtimePlan") if isinstance(item.get("runtimePlan"), dict) else {}
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn") or "") for c in calls if isinstance(c, dict)]
    arch = item.get("runtimeArchetype") if isinstance(item.get("runtimeArchetype"), dict) else {}
    contract = item.get("runtimeContract") if isinstance(item.get("runtimeContract"), dict) else {}
    debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
    promise = {}
    try:
        promise = json.loads(str(debug.get("runtimePromiseTruth") or "{}"))
    except Exception:
        promise = {}
    return {
        "caseId": case_id,
        "ok": error is None and bool(item),
        "error": error,
        "ms": ms,
        "name": item.get("name"),
        "category": item.get("category"),
        "kind": gp.get("kind"),
        "damage": gp.get("damage"),
        "damageClass": gp.get("damageClass"),
        "useTime": gp.get("useTime"),
        "runtimeFamily": at.get("runtimeFamily"),
        "delivery": at.get("delivery"),
        "movement": at.get("movement"),
        "onHit": at.get("onHit"),
        "effect": at.get("effect"),
        "engineFns": fns,
        "runtimeArchetypeFamily": arch.get("family"),
        "executionStatus": contract.get("executionStatus"),
        "unsupportedPromises": list(item.get("unsupportedPromises") or [])[:12],
        "promiseClaims": [
            {"kind": c.get("kind"), "status": c.get("status"), "source": c.get("source")}
            for c in (promise.get("claims") or [])[:12]
            if isinstance(c, dict)
        ],
        "planner": debug.get("planner"),
        "model": debug.get("model"),
    }


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cache = out / "_cache"
    cache.mkdir()

    load_config_env(ROOT / "config.env")
    os.environ["INFINI_USE_LLM"] = "1"
    os.environ["INFINI_IMAGE_BACKEND"] = "off"
    os.environ["INFINI_VISUAL_REQUIRE_ITEM_SPRITE"] = "0"
    os.environ["INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND"] = "0"
    os.environ["INFINI_VISUAL_DIRECTOR_LLM"] = "0"
    os.environ["INFINI_VFX_LLM_DIRECTOR"] = "0"
    os.environ["INFINI_CACHE_DIR"] = str(cache)
    # Ensure no replay hijacks live sample.
    os.environ.pop("INFINI_LLM_REPLAY_RAW", None)

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from infini_local.pipelines.combine_pipeline import combine

    rows: list[dict[str, Any]] = []
    for case_id, a, b in PAIRS:
        t0 = time.time()
        item: dict[str, Any] = {}
        error = None
        try:
            item = combine(
                {
                    "itemA": a,
                    "itemB": b,
                    "worldId": f"live_semantic_{case_id}",
                    "worldName": "LiveSemanticSample",
                    "recipeIdentityVersion": "live_semantic_v1",
                }
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        ms = int((time.time() - t0) * 1000)
        (out / f"{case_id}.full.json").write_text(
            json.dumps(item or {"error": error}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        row = compact(case_id, item, error, ms)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    from collections import Counter

    families = Counter(str(r.get("runtimeFamily") or "") for r in rows if r.get("ok"))
    movements = Counter(str(r.get("movement") or "") for r in rows if r.get("ok"))
    onhits = Counter(str(r.get("onHit") or "") for r in rows if r.get("ok"))
    unsupported = Counter()
    for r in rows:
        for u in r.get("unsupportedPromises") or []:
            unsupported[str(u)] += 1

    summary = {
        "ok": all(r.get("ok") for r in rows),
        "caseCount": len(rows),
        "failedCount": sum(1 for r in rows if not r.get("ok")),
        "cases": rows,
        "diversity": {
            "runtimeFamily": dict(families),
            "movement": dict(movements),
            "onHit": dict(onhits),
            "unsupportedPromises": dict(unsupported),
        },
        "note": "Live LLM semantic sample with image backend off. Not Terraria gameplay proof.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "failedCount": summary["failedCount"], "diversity": summary["diversity"]}, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
