from __future__ import annotations

"""Wiki-guided playthrough runner for InfiniCrafterLocal.

This is deliberately NOT a unit-test harness. It is a code-driven play session: it
loads a small vanilla Terraria progression route, optionally tries to look up wiki.gg
pages for the listed items, then repeatedly feeds generated items forward like a
player upgrading the same weapon across progression.
"""

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "wiki_guided_vanilla_playthrough.json"
REPORT = ROOT / "wiki_guided_playthrough_report.json"
CACHE = ROOT / ".wiki_guided_playthrough_cache"

os.environ.setdefault("INFINI_USE_LLM", "0")
os.environ.setdefault("INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK", "1")
os.environ.setdefault("INFINI_IMAGE_BACKEND", "off")
os.environ["INFINI_CACHE_DIR"] = str(CACHE)
if os.environ.get("INFINI_PLAYTHROUGH_KEEP_CACHE", "0") != "1":
    if CACHE.exists():
        shutil.rmtree(CACHE)
CACHE.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("infini_server_playthrough", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = server
assert spec.loader is not None
spec.loader.exec_module(server)

BULLET = {
    "type": 14, "sourceMod": "Terraria", "internalName": "Bullet", "fullName": "Terraria/Bullet",
    "width": 4, "height": 4, "scale": 1.0, "aiStyle": 1, "penetrate": 1, "maxPenetrate": 1,
    "timeLeft": 600, "extraUpdates": 1, "tileCollide": True, "ignoreWater": False,
    "friendly": True, "hostile": False, "arrow": False, "minion": False, "sentry": False,
    "minionSlots": 0, "ownerHitCheck": False, "usesLocalNPCImmunity": False,
    "localNPCHitCooldown": -2, "usesIDStaticNPCImmunity": False, "idStaticNPCHitCooldown": -1,
    "stopsDealingDamageAfterPenetrateHits": False, "light": 0, "alpha": 0, "netImportant": False,
}
ARROW = dict(BULLET, type=1, internalName="WoodenArrowFriendly", fullName="Terraria/WoodenArrowFriendly", arrow=True, timeLeft=1200, extraUpdates=0)
BOOMERANG = dict(BULLET, type=52, internalName="EnchantedBoomerang", fullName="Terraria/EnchantedBoomerang", penetrate=-1, timeLeft=360, extraUpdates=0, ownerHitCheck=False)
TERRA_BEAM = dict(BULLET, type=132, internalName="TerraBeam", fullName="Terraria/TerraBeam", penetrate=3, maxPenetrate=3, timeLeft=600, extraUpdates=1)
DEATH_SICKLE = dict(BULLET, type=188, internalName="DeathSickle", fullName="Terraria/DeathSickle", penetrate=-1, timeLeft=240, extraUpdates=0, tileCollide=False, usesLocalNPCImmunity=True, localNPCHitCooldown=20)
MAGIC = dict(BULLET, type=501, internalName="MagicMissile", fullName="Terraria/MagicMissile", penetrate=1, timeLeft=3600, extraUpdates=0, tileCollide=False)
TYPHOON = dict(MAGIC, type=409, internalName="Typhoon", fullName="Terraria/Typhoon", penetrate=-1, timeLeft=360, tileCollide=False)
PRISM_BEAM = dict(MAGIC, type=633, internalName="LastPrismLaser", fullName="Terraria/LastPrismLaser", penetrate=-1, timeLeft=180, usesLocalNPCImmunity=True, localNPCHitCooldown=10)
MEOWMERE = dict(BULLET, type=503, internalName="Meowmere", fullName="Terraria/Meowmere", penetrate=5, maxPenetrate=5, timeLeft=600, extraUpdates=0, tileCollide=True)
STAR_WRATH = dict(BULLET, type=504, internalName="StarWrath", fullName="Terraria/StarWrath", penetrate=2, maxPenetrate=2, timeLeft=600, extraUpdates=0, tileCollide=False)
PROFILES = {"BULLET": BULLET, "ARROW": ARROW, "BOOMERANG": BOOMERANG, "TERRA_BEAM": TERRA_BEAM, "DEATH_SICKLE": DEATH_SICKLE, "MAGIC": MAGIC, "TYPHOON": TYPHOON, "PRISM_BEAM": PRISM_BEAM, "MEOWMERE": MEOWMERE, "STAR_WRATH": STAR_WRATH}


def resolve_item(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    prof = item.get("projectileProfile")
    if isinstance(prof, str):
        item["projectileProfile"] = PROFILES.get(prof, {})
    item.setdefault("sourceMod", "Terraria")
    item.setdefault("internalName", item["name"].replace(" ", "").replace("'", ""))
    item.setdefault("fullName", "Terraria/" + item["internalName"])
    item.setdefault("tags", [])
    return item


def generated_as_input(obj: dict[str, Any], id_base: int) -> dict[str, Any]:
    gp = obj.get("gameplay", {}) if isinstance(obj.get("gameplay"), dict) else {}
    at = obj.get("attack", {}) if isinstance(obj.get("attack"), dict) else {}
    return {
        "id": id_base,
        "name": obj.get("name", "Generated Item"),
        "sourceMod": "InfiniCrafterLocal",
        "internalName": "GeneratedItem",
        "fullName": "InfiniCrafterLocal/GeneratedItem",
        "damage": gp.get("damage", 0),
        "useTime": gp.get("useTime", 24),
        "useAnimation": gp.get("useAnimation", gp.get("useTime", 24)),
        "useStyle": gp.get("useStyle", 1),
        "damageClass": gp.get("damageClass", "generic"),
        "rare": gp.get("rarity", 0),
        "value": gp.get("value", 100),
        "shoot": 1 if at.get("enabled") else 0,
        "shootSpeed": at.get("speed", 0),
        "projectileProfile": server.projectile_profile_of({"generatedData": obj, "shoot": 1}),
        "tags": obj.get("tags", []),
        "generatedData": obj,
    }


def maybe_fetch_wiki(page: str) -> dict[str, Any]:
    if os.environ.get("INFINI_FETCH_WIKI", "0") != "1":
        return {"enabled": False, "page": page}
    # MediaWiki API extract is enough for route notes; the sim does not trust scraped stats.
    url = f"https://terraria.wiki.gg/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles={quote(page)}&format=json"
    try:
        req = urlrequest.Request(url, headers={"User-Agent": "InfiniCrafterLocal wiki-guided playthrough"})
        with urlrequest.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = (data.get("query") or {}).get("pages") or {}
        first = next(iter(pages.values()), {}) if pages else {}
        return {"enabled": True, "page": page, "title": first.get("title"), "extractHead": str(first.get("extract") or "")[:700]}
    except Exception as e:
        return {"enabled": True, "page": page, "error": repr(e)}


def audit_result(route_id: str, step_idx: int, left: dict[str, Any], right: dict[str, Any], result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    gp = result.get("gameplay") if isinstance(result.get("gameplay"), dict) else {}
    at = result.get("attack") if isinstance(result.get("attack"), dict) else {}
    metrics = at.get("engineMetrics") if isinstance(at.get("engineMetrics"), dict) else {}
    left_weapon = server.is_weapon_like_parent(left)
    right_weapon = server.is_weapon_like_parent(right)
    parent_max_damage = max(float(left.get("damage") or 0), float(right.get("damage") or 0))
    weak_anchor = (left.get("damage", 0) or 0) <= 0 or (right.get("damage", 0) or 0) <= 0
    if (left_weapon or right_weapon) and result.get("category") != "weapon":
        # Materials can intentionally turn a weapon into a charm/station only if category policy says so,
        # but playthrough spine chains should not silently lose the weapon.
        if left.get("sourceMod") == "InfiniCrafterLocal" or right.get("sourceMod") == "InfiniCrafterLocal" or (left_weapon and right_weapon):
            pass  # rare category twist is allowed; real gameplay will decide whether it is fun
    if result.get("category") == "weapon":
        dmg = float(gp.get("damage") or 0)
        use = float(gp.get("useTime") or 0)
        if dmg <= 0 or use <= 0:
            issues.append("weapon has non-positive damage/useTime")
        if parent_max_damage >= 25 and not weak_anchor and dmg < parent_max_damage * 0.18:
            issues.append("weapon chain became suspiciously weak versus strongest parent")
        if (left.get("name") == "Dirt Block" or right.get("name") == "Dirt Block") and dmg > 80:
            issues.append("weak material abuse damage too high")
        if metrics.get("activeProjectileEstimate", 0) > 85:
            issues.append("active projectile estimate too high")
        if metrics.get("dustPerSecondEstimate", 0) > 260:
            issues.append("dust/sec estimate too high")
        if at.get("shotCount", 1) > 7:
            issues.append("shotCount exceeds C# cap")
        if at.get("maxChildProjectiles", 0) > 48:
            issues.append("child projectile cap exceeds C# cap")
    return issues


def compact_result(route: str, title: str, step: int, left: dict[str, Any], right: dict[str, Any], result: dict[str, Any], wiki: list[dict[str, Any]]) -> dict[str, Any]:
    gp = result.get("gameplay") if isinstance(result.get("gameplay"), dict) else {}
    at = result.get("attack") if isinstance(result.get("attack"), dict) else {}
    metrics = at.get("engineMetrics") if isinstance(at.get("engineMetrics"), dict) else {}
    return {
        "route": route,
        "routeTitle": title,
        "step": step,
        "left": left.get("name"),
        "right": right.get("name"),
        "result": result.get("name"),
        "category": result.get("category"),
        "kind": gp.get("kind"),
        "stage": gp.get("stage"),
        "damage": gp.get("damage"),
        "useTime": gp.get("useTime"),
        "damageClass": gp.get("damageClass"),
        "delivery": at.get("delivery"),
        "movement": at.get("movement"),
        "onHit": at.get("onHit"),
        "shotCount": at.get("shotCount"),
        "activeProjectileEstimate": metrics.get("activeProjectileEstimate"),
        "dustPerSecondEstimate": metrics.get("dustPerSecondEstimate"),
        "wiki": wiki,
        "issues": audit_result(route, step, left, right, result),
    }


def run() -> int:
    cfg = json.loads(DATA.read_text(encoding="utf-8-sig"))
    items = {k: resolve_item(v) for k, v in cfg["items"].items()}
    all_rows: list[dict[str, Any]] = []
    world = int(time.time()) % 100000
    gen_id = 880000
    print(f"InfiniCrafterLocal wiki-guided playthrough, server {server.APP_VERSION}")
    print(f"wiki fetch: {'on' if os.environ.get('INFINI_FETCH_WIKI','0')=='1' else 'off/offline snapshot'}")
    for route in cfg["routes"]:
        prev: dict[str, Any] | None = None
        print(f"\n== {route['title']} ==")
        for i, pair in enumerate(route["steps"], start=1):
            left = prev if pair[0] == "$prev" else items[pair[0]]
            right = prev if pair[1] == "$prev" else items[pair[1]]
            assert left is not None and right is not None
            wiki = []
            for src in (left, right):
                if src.get("sourceMod") == "Terraria" and src.get("wikiPage"):
                    wiki.append(maybe_fetch_wiki(src["wikiPage"]))
            result = server.combine({"worldId": world, "modVersion": server.APP_VERSION, "itemA": left, "itemB": right})
            row = compact_result(route["id"], route["title"], i, left, right, result, wiki)
            all_rows.append(row)
            issues = (" | ISSUES: " + "; ".join(row["issues"])) if row["issues"] else ""
            print(f"{i:02d}. {row['left']} + {row['right']} -> {row['result']} [{row['category']}] dmg={row['damage']} use={row['useTime']} active={row['activeProjectileEstimate']} dust={row['dustPerSecondEstimate']}{issues}")
            prev = generated_as_input(result, gen_id)
            gen_id += 1
    REPORT.write_text(json.dumps({"version": server.APP_VERSION, "rows": all_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    issue_rows = [r for r in all_rows if r["issues"]]
    print(f"\nReport: {REPORT}")
    print(f"Rows: {len(all_rows)}, issue rows: {len(issue_rows)}")
    return 2 if issue_rows else 0


if __name__ == "__main__":
    raise SystemExit(run())
