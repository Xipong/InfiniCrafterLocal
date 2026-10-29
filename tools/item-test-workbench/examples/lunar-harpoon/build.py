#!/usr/bin/env python3
"""Rebuild this assistant-authored demo through existing canonical owners, without an API."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "LocalGenerator"))
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines.visual_generation_pipeline import _validate_kit, _apply_kit
from infini_local.pipelines.visual_sprite_generation import _runtime_publication_identity
from infini_local.core.vfx_manifest import validate_vfx_director_output, _compile_manifest, validate_vfx_manifest_wire
from infini_local.storage.world_storage import sanitize_recipe_for_delivery

ASSET_SHA256 = "8e9bd54774fc16081d709d82c37cabd9c5b994c2d02dad0e3cf5ca5dd9018463"
def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
def write(path: Path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
def require(report):
    if not report.get("ok"):
        raise ValueError(json.dumps(report, indent=2))
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=HERE / "assets" / "infini_asset_png_4a753935d470fa15fe74d5b8b4e87f63a8ef56060e8844a89b30e766fa0c8c2e.png", help="Exact published assistant imagegen PNG (default: bundled original demo art)")
    parser.add_argument("--player-assets", required=True, type=Path, help="Fetched vanilla source PNG root with --include-dummy")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    asset = args.asset.resolve(strict=True)
    raw = asset.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ASSET_SHA256:
        raise ValueError("This demo's measured grip/forward axis require its exact supplied PNG")
    source = read(HERE / "author-source.json")
    identity = _runtime_publication_identity(source, "item", "", source["id"])
    expected = "infini_asset_png_" + hashlib.sha256(identity + b"\0" + raw).hexdigest() + ".png"
    if asset.name != expected:
        raise ValueError("Expected exact canonical publication basename: " + expected)
    args.out.mkdir(parents=True, exist_ok=False)
    write(args.out / "author-validation.json", require(validate_runtime_program(source)))
    data = compile_runtime_program(source)
    write(args.out / "compiler-audit.json", require(audit_compiler_receipts(data["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=data)))
    write(args.out / "compiled-gameplay.json", data)
    visual = read(HERE / "visual-author-source.json")
    kit, errors = _validate_kit(visual, ["item", "harpoon"], "item", accepted_data=data)
    if errors:
        raise ValueError(json.dumps(errors, indent=2))
    data = _apply_kit(data, kit)
    # External imagegen delivery only: no mechanics, axes or artwork are inferred here.
    data["visual"].update(spritePath=str(asset), spriteUrl="", spriteStatus="generated", spriteTechnicalScore=0)
    for entity in data["runtimeProgram"]["entities"]:
        entity["visual"].update(spritePath=str(asset), spriteUrl="", spriteStatus="generated", spriteTechnicalScore=0)
    vfx = read(HERE / "vfx-author-source.json")
    write(args.out / "vfx-author-validation.json", require(validate_vfx_director_output(vfx, data)))
    data["vfxManifest"] = _compile_manifest(data, vfx, data["id"])
    require(validate_vfx_manifest_wire(data))
    final = sanitize_recipe_for_delivery(data)
    write(args.out / "final-wire-validation.json", require(validate_runtime_wire(final)))
    write(args.out / "item.json", final)
    scenario = read(HERE / "scenario.json")
    scenario["nativeRender"]["artworkFiles"] = [str(asset)]
    scenario["nativeRender"]["playerAssetRoot"] = str(args.player_assets.resolve())
    scenario["nativeRender"]["dummyAssetRoot"] = str(args.player_assets.resolve())
    write(args.out / "scenario.json", scenario)
    write(args.out / "build-receipt.json", {"authorship": "assistant-authored Author/Visual/VFX source; actual imagegen artwork", "llmApiUsed": False, "gameplayWireHandEdited": False, "assetByteSha256": ASSET_SHA256, "technicalScoreNotAssessed": True, "authorSha256": hashlib.sha256((HERE / "author-source.json").read_bytes()).hexdigest(), "itemSha256": hashlib.sha256((args.out / "item.json").read_bytes()).hexdigest()})
    print(args.out / "item.json")
if __name__ == "__main__":
    main()
