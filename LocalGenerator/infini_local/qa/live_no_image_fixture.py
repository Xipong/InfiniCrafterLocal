from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
from types import FunctionType
from typing import Any, Callable
import zlib

from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan


def write_no_image_fixture_png(path: Path, *, size: int = 32) -> Path:
    """Write a deterministic technical PNG without calling an image backend."""

    if size < 1 or size > 256:
        raise ValueError("fixture PNG size must be within 1..256")
    path.parent.mkdir(parents=True, exist_ok=True)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            if (x // 4 + y // 4) % 2:
                rows.extend((255, 0, 255, 255))
            else:
                rows.extend((24, 24, 24, 255))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + chunk(b"IEND", b"")
    )
    return path


def hydrate_no_image_fixture_assets(data: dict[str, Any], fixture_path: Path) -> dict[str, Any]:
    """Hydrate final-delivery paths with a QA-only PNG after backend interception.

    This function never changes an authored asset mode and never calls or mocks an
    image generator. It gives the production delivery gate a real file to inspect
    while the no-image campaign separately proves that every backend is blocked.
    """

    fixture = str(fixture_path.resolve())
    visual = data.setdefault("visual", {})
    visual.update({
        "spriteStatus": "qa_no_image_fixture",
        "spritePath": fixture,
        "spriteRawPath": fixture,
        "spriteUrl": "",
    })
    raw_program = data.get("runtimeProgram")
    program: dict[str, Any] = raw_program if isinstance(raw_program, dict) else {}
    asset_plan = build_visual_asset_plan(data)
    required_impact_entity_ids = {
        str(slot.get("entityId") or "")
        for slot in asset_plan
        if str(slot.get("role") or "").startswith("impact:")
    }
    equipment_overlay_required = any(
        str(slot.get("role") or "") == "equip_overlay"
        for slot in asset_plan
    )
    attack = data.setdefault("attack", {})
    for entity in program.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_visual = entity.setdefault("visual", {})
        if entity.get("kind") == "item_body":
            # Match visual_sprite_generation's exact item-body projection: the
            # top-level inventory icon is also its canonical runtime sprite.
            entity_visual.update({
                "assetMode": "baked_sprite",
                "spriteStatus": "qa_no_image_fixture",
                "spritePath": fixture,
                "spriteUrl": "",
                "spriteTechnicalScore": 1.0,
            })
        if entity.get("kind") != "item_body":
            mode = str(entity_visual.get("assetMode") or "")
            if mode == "baked_sprite":
                entity_visual.update({
                    "spriteStatus": "qa_no_image_fixture",
                    "spritePath": fixture,
                    "spriteUrl": "",
                })
            elif mode == "reuse_item_icon":
                entity_visual.update({
                    "spriteStatus": "reused_item_icon",
                    "spritePath": fixture,
                    "spriteUrl": "",
                })
            elif mode in {"runtime_geometry", "no_asset"}:
                entity_visual.update({
                    "spriteStatus": "not_required",
                    "spritePath": "",
                    "spriteUrl": "",
                })
            role = str(entity.get("visualRole") or "")
            if role in {"projectile", "impact", "child", "field"}:
                attack[f"{role}SpriteStatus"] = str(entity_visual.get("spriteStatus") or "")
                attack[f"{role}SpritePath"] = str(entity_visual.get("spritePath") or "")
                attack[f"{role}SpriteUrl"] = ""
        if str(entity.get("id") or "") in required_impact_entity_ids:
            entity_visual.update({
                "impactSpriteStatus": "qa_no_image_fixture",
                "impactSpritePath": fixture,
                "impactSpriteUrl": "",
                "impactSpriteTechnicalScore": 1.0,
            })
    if equipment_overlay_required:
        visual.update({
            "equipOverlayStatus": "qa_no_image_fixture",
            "equipOverlayPath": fixture,
            "equipOverlayUrl": "",
            "equipOverlayTechnicalScore": 1.0,
            "equipOverlayScore": 1.0,
        })
    data.setdefault("debug", {})["noImageQaFixturePath"] = fixture
    return data


def _verify_no_image_fixture_identity(
    fixture: Path, selected_fixture: Path, fixture_sha: str,
) -> None:
    """Bind one QA observation to exact bytes and canonical serving selection."""
    from infini_local.pipelines import visual_delivery_gate as gate

    try:
        paths = {fixture, selected_fixture}
        snapshots = {path: gate._file_snapshot(path) for path in paths}
        selected = gate._resolved_asset_path(str(fixture))
        unchanged = selected is not None and selected.resolve() == selected_fixture
        unchanged = unchanged and all(
            hashlib.sha256(path.read_bytes()).hexdigest() == fixture_sha for path in paths
        )
        selected_after = gate._resolved_asset_path(str(fixture))
        unchanged = unchanged and selected_after is not None and selected_after.resolve() == selected_fixture
        unchanged = unchanged and all(gate._file_snapshot(path) == snapshots[path] for path in paths)
    except (OSError, ValueError):
        unchanged = False
    if not unchanged:
        raise gate.VisualDeliveryBlocked("qa_fixture_identity_changed: synthetic QA fixture bytes or serving selection changed")


def observe_no_image_readiness(
    data: dict[str, Any], fixture_path: Path,
    readiness_check: Callable[[dict[str, Any]], Any],
) -> tuple[dict[str, Any], Any]:
    """Consume a private execution control inside its exact-byte QA proof."""
    control = synthetic_no_image_execution_control(data, fixture_path)
    binding = control.get("debug", {}).get("noImageExecutionControl", {}).get("fixture")
    if binding is None:
        return control, readiness_check(control)
    fixture = Path(binding["path"])
    selected = Path(binding["selectedServingPath"])
    _verify_no_image_fixture_identity(fixture, selected, binding["sha256"])
    try:
        result = readiness_check(control)
    finally:
        # A fresh canonical assessment can accept another complete PNG, or a
        # cached/wrapped consumer can replace it after its own assessment.
        _verify_no_image_fixture_identity(fixture, selected, binding["sha256"])
    return control, result


def synthetic_no_image_execution_control(
    data: dict[str, Any], fixture_path: Path,
) -> dict[str, Any]:
    """Observe a private copy through the real image metadata projector.

    Only this harness-owned technical fixture can supply synthetic completed
    execution results. The original QA labels/evidence are never rewritten.
    Clone the projector's globals rather than patching its module: concurrent
    crafts and production callers must not see these backend substitutions.
    """
    from infini_local.core.vfx_manifest import vfx_png_dependencies
    from infini_local.pipelines import visual_delivery_gate as gate
    from infini_local.pipelines import visual_sprite_generation as sprites
    from infini_local.services.asset_sync_service import is_complete_png_file

    control = copy.deepcopy(data)
    evidence: dict[str, Any] = {
        "kind": "synthetic_no_image_execution_control",
        "synthetic": True,
        "realImageGeneration": False,
        "owners": [],
    }
    control.setdefault("debug", {})["noImageExecutionControl"] = evidence
    # Keep every canonical owner/path/roster refusal. Only the explicitly QA
    # execution-status seam can be bridged, never other readiness failures.
    baseline = gate.visual_delivery_report(data, check_backend_config=False)
    if any(row["code"] != "required_vfx_texture_not_ready" for row in baseline["problems"]):
        return control
    fixture = fixture_path.resolve()
    selected_fixture = gate._resolved_asset_path(str(fixture))
    if selected_fixture is None:
        return control
    selected_fixture = selected_fixture.resolve()
    try:
        snapshots = {path: gate._file_snapshot(path) for path in {fixture, selected_fixture}}
        if not is_complete_png_file(selected_fixture):
            return control
        fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if any(gate._file_snapshot(path) != snapshot for path, snapshot in snapshots.items()):
            raise gate.VisualDeliveryBlocked("qa_fixture_identity_changed: synthetic QA fixture changed during authentication")
        _verify_no_image_fixture_identity(fixture, selected_fixture, fixture_sha)
    except OSError:
        return control

    entities = {row["id"]: row for row in data.get("runtimeProgram", {}).get("entities", [])}
    for dependency in vfx_png_dependencies(data)["dependencies"]:
        if dependency["spriteStatus"] != "qa_no_image_fixture":
            # The projector mirrors item-body/reuse execution metadata; do not
            # let that projection erase a pending/non-QA selected producer.
            return control
        selected = gate._resolved_asset_path(dependency["spritePath"])
        if selected is None or selected.resolve() != selected_fixture.resolve():
            return control

    def execution_result(role: str, owner: dict[str, Any], prefix: str) -> tuple[str, str, float, str]:
        path = str(owner.get(prefix + "Path") or "")
        status = str(owner.get(prefix + "Status") or "")
        selected = gate._resolved_asset_path(path)
        if status == "qa_no_image_fixture" and selected is not None and selected.resolve() == selected_fixture.resolve():
            evidence["owners"].append({
                "role": role, "statusBefore": status,
                "selectedServingPath": str(selected.resolve()), "sha256": fixture_sha,
                "completePng": True,
            })
            return path, "", 1.0, "generated"
        return path, str(owner.get(prefix + "Url") or ""), float(owner.get(prefix + "TechnicalScore") or 0.0), status

    def synthetic_item(item: dict[str, Any]) -> dict[str, Any]:
        path, url, score, status = execution_result("item", data.get("visual", {}), "sprite")
        item.setdefault("visual", {}).update(
            spritePath=path, spriteUrl=url, spriteTechnicalScore=score, spriteStatus=status,
        )
        return item

    def synthetic_asset(_item: dict[str, Any], role: str, *_args: Any, **kwargs: Any) -> tuple[str, str, float, str]:
        entity_id = kwargs.get("entity_id") or kwargs.get("publication_entity_id")
        if entity_id:
            prefix = "impactSprite" if role == "impact" else "sprite"
            owner = entities.get(entity_id, {}).get("visual", {})
            return execution_result(("impact:" if prefix == "impactSprite" else "entity:") + entity_id, owner, prefix)
        if role == "equip_overlay":
            return execution_result(role, data.get("visual", {}), "equipOverlay")
        # Requested VFX ingredients are not supplied by this ordinary fixture.
        return "", "", 0.0, "pending"

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("image backend reached by synthetic no-image observer")

    projector = sprites.maybe_generate_visual_assets
    isolated_globals = dict(projector.__globals__)
    isolated_globals.update(
        maybe_generate_sprite=synthetic_item,
        generate_visual_asset=synthetic_asset,
        _generate_backend_variants=forbidden,
        write_visual_manifest=lambda *_args, **_kwargs: None,
        VISUAL_ASSET_MODE="full",
    )
    isolated_projector = FunctionType(projector.__code__, isolated_globals, projector.__name__, projector.__defaults__, projector.__closure__)
    evidence["fixture"] = {
        "path": str(fixture), "selectedServingPath": str(selected_fixture), "sha256": fixture_sha,
    }
    _verify_no_image_fixture_identity(fixture, selected_fixture, fixture_sha)
    projected = isolated_projector(control)
    _verify_no_image_fixture_identity(fixture, selected_fixture, fixture_sha)
    return projected


__all__ = ["hydrate_no_image_fixture_assets", "write_no_image_fixture_png", "synthetic_no_image_execution_control", "observe_no_image_readiness"]
