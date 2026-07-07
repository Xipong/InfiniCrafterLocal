#!/usr/bin/env python3
# Local helper for InfiniCrafterLocal debug BAT launchers.
# Uses only Python stdlib and local 127.0.0.1 HTTP endpoints.

from __future__ import annotations

import json
import sys
import uuid
import urllib.request
import urllib.error
from pathlib import Path


def _print_json_or_text(raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    try:
        obj = json.loads(text)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        print(text)


def request_json(method: str, url: str, payload: dict | None = None, timeout: int = 30) -> None:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _print_json_or_text(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}")
        try:
            _print_json_or_text(exc.read())
        except Exception:
            pass
        raise SystemExit(1)
    except Exception as exc:
        print(f"Request failed: {exc}")
        print("Make sure InfiniCrafterLocal server is running and the port is correct.")
        raise SystemExit(1)


def vfx_probe_matrix() -> None:
    payload = {
        "patterns": ["thrown_simple", "slash_holdout", "beam_slash", "field_trap"],
        "intents": [
            "large bright burst with motes",
            "clean physical small flash",
            "slow smoky residue field",
            "goo splat bubbles",
        ],
    }
    request_json("POST", "http://127.0.0.1:5055/debug/vfx_probe_matrix", payload)


def vfx_bake_preview() -> None:
    payload = {
        "pattern": "slash_holdout",
        "vfxIntent": "large baked slash burst with motes",
        "projectile": "debug projectile blade",
        "impact": "debug impact flash",
        "child": "debug child mote",
        "recipeKey": "preview-" + str(uuid.uuid4()),
        "returnManifest": False,
    }
    request_json("POST", "http://127.0.0.1:5055/debug/vfx_bake_preview", payload)


def vfx_timeline() -> None:
    request_json(
        "GET",
        "http://127.0.0.1:5055/debug/vfx_timeline?pattern=slash_holdout&recipeId=lod_high_layered_slash_88&returnManifest=0",
    )


def vfx_budget_audit() -> None:
    request_json("GET", "http://127.0.0.1:5055/debug/vfx_budget_audit")


def vfx_stack() -> None:
    payload = {
        "pattern": "slash_holdout",
        "forceRecipeId": "foundation_slash_light_sound_stack_81",
        "returnManifest": True,
    }
    request_json("POST", "http://127.0.0.1:5055/debug/vfx_stack", payload)


def vfx_lanes() -> None:
    # This imports the local server module directly, matching the old intent of 32_PREVIEW_VFX_LANES.bat.
    # Run from LocalGenerator root.
    try:
        from infini_local.web.vfx_debug_routes import VfxDebugRoutes

        routes = VfxDebugRoutes(
            app_version="debug",
            normalize_world_id_from_payload=lambda payload: "debug",
            read_world_recipe_cache=lambda *args, **kwargs: None,
            write_world_recipe_cache=lambda *args, **kwargs: None,
            final_normalize=lambda data: data,
        )
        result = routes.composer({
            "pattern": "slash_holdout",
            "forceRecipeId": "reference_layered_slash_crescent_100",
            "returnManifest": True,
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"Local import/debug call failed: {exc}")
        raise SystemExit(1)


def vfx_procedural() -> None:
    payload = {
        "attack": {
            "enabled": True,
            "pattern": "slash_holdout",
            "powerBudget": 1.45,
            "projectileSpritePrompt": "bright crescent blade",
            "impactSpritePrompt": "wide starburst impact",
        },
        "visualKit": {
            "vfxIntent": "layered slash with side streaks and impact flash",
        },
    }
    request_json("POST", "http://127.0.0.1:5055/debug/vfx_procedural", payload)


COMMANDS = {
    "vfx_probe_matrix": vfx_probe_matrix,
    "vfx_bake_preview": vfx_bake_preview,
    "vfx_timeline": vfx_timeline,
    "vfx_budget_audit": vfx_budget_audit,
    "vfx_stack": vfx_stack,
    "vfx_lanes": vfx_lanes,
    "vfx_procedural": vfx_procedural,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print("Usage: python tools/local_debug_calls.py <command>")
        print("Commands:")
        for name in sorted(COMMANDS):
            print("  " + name)
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
