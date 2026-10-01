from __future__ import annotations

import hashlib
import json
import os
import tempfile
import traceback
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from infini_local.storage.world_recipe_runtime import safe_file_part
from infini_local.core.config_bootstrap import SPRITE_DIR, WORLD_RECIPES_DIR
from infini_local.core.runtime_authoring.capability_registry import VISUAL_ROLE_BY_ENTITY_KIND
from infini_local.core.image_dependencies import (
    Image,
    ImageDraw,
)
from infini_local.pipelines.pipeline_visual_config import (
    GENERATE_VARIANTS,
    IMAGE_BACKEND,
    IMAGE_BACKEND_CONFIG_ERROR,
    IMAGE_GENERATION_GATE,
    SPRITE_RETRIES,
    VISUAL_ALLOW_PROCEDURAL_FALLBACK,
    VISUAL_ASSET_MODE,
    VISUAL_STRICT_AI_AUTHORSHIP,
)
from infini_local.services import visual_asset_pipeline
from infini_local.services.codex_auth import CodexError
from infini_local.services.visual_asset_pipeline import ImageOutputIOError, load_image_input, save_image_output, sprite_status_from_raw_path, truncate_prompt_at_boundary
from infini_local.storage.trace_runtime import (
    log_event,
    trace_event,
)
from infini_local.pipelines.image_backend_pipeline import (
    generate_a1111,
    generate_comfyui,
    generate_image_api,
    generate_openai_codex,
    generate_sdcpp,
)
from infini_local.pipelines.sprite_postprocess import (
    build_retry_prompt_from_validation,
    cleanup_alpha,
    pick_best_sprite,
    postprocess_sprite,
    sprite_validation_fatal,
    technical_validation_score,
    validate_processed_sprite,
)
from infini_local.pipelines.visual_asset_manifest import write_visual_manifest
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt
from infini_local.pipelines.visual_soul import attach_visual_soul_from_sprite


# AGENT MAP: image backend calls/retry/refit for item and role-separated visual assets.
# This module mutates only visual/attack asset paths/status/debug fields after prompts
# and plans are already authored.


class ImageBackendConfigurationError(RuntimeError):
    """Selected image backend cannot produce an authored sprite in this configuration."""


def _authored_sprite_topology(data: dict[str, Any], role: str) -> tuple[str, int, int]:
    """Return only topology explicitly authored by Visual Director.

    Runtime entities do not infer sprite topology from gameplay, names, categories,
    or movement controllers.  A visual row may optionally declare a technical
    topology in its own visual payload; absent values remain absent.
    """
    if (role or "item").lower() == "item":
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    else:
        entity_id = role.removeprefix("entity_").removeprefix("entity:")
        runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
        entity = next((row for row in runtime.get("entities") or [] if isinstance(row, dict) and str(row.get("id") or "") == entity_id), {})
        visual = entity.get("visual") if isinstance(entity, dict) and isinstance(entity.get("visual"), dict) else {}
    topology = str(visual.get("topology") or "").strip().lower()
    minimum = visual.get("partCountMin")
    maximum = visual.get("partCountMax")
    return topology, int(minimum) if isinstance(minimum, int) else 0, int(maximum) if isinstance(maximum, int) else 0

def _backend_configuration_error() -> str:
    if IMAGE_BACKEND_CONFIG_ERROR:
        return IMAGE_BACKEND_CONFIG_ERROR
    if IMAGE_BACKEND == "procedural" and (VISUAL_STRICT_AI_AUTHORSHIP or not VISUAL_ALLOW_PROCEDURAL_FALLBACK):
        return "procedural backend requires strict AI authorship=0 and explicit procedural fallback=1"
    return ""


def _generate_backend_variants(
    data: dict[str, Any],
    *,
    prompt: str,
    negative: str,
    asset_id: str,
    canvas: int,
    role: str,
    output_dir: Path | None = None,
) -> list[str]:
    """Dispatch one configured backend without silently changing authorship mode."""
    config_error = _backend_configuration_error()
    if config_error:
        raise ImageBackendConfigurationError(config_error)
    with IMAGE_GENERATION_GATE.slot():
        if IMAGE_BACKEND == "a1111":
            return generate_a1111(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if IMAGE_BACKEND == "comfyui":
            return generate_comfyui(prompt, negative, asset_id, output_dir=output_dir)
        if IMAGE_BACKEND == "sdcpp":
            return generate_sdcpp(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if IMAGE_BACKEND == "openai_codex":
            return generate_openai_codex(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if IMAGE_BACKEND == "image_api":
            return generate_image_api(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if IMAGE_BACKEND == "procedural":
            if role == "item":
                return [
                    visual_asset_pipeline.generate_procedural_sprite(
                        data,
                        variant=i,
                        sprite_dir=output_dir if output_dir is not None else SPRITE_DIR,
                        image_cls=Image,
                        image_draw_cls=ImageDraw,
                    )
                    for i in range(max(1, GENERATE_VARIANTS))
                ]
            return [
                visual_asset_pipeline.generate_procedural_asset(
                    data,
                    role,
                    variant=0,
                    canvas_size=canvas,
                    sprite_dir=output_dir if output_dir is not None else SPRITE_DIR,
                    image_cls=Image,
                    image_draw_cls=ImageDraw,
                )
            ]
        if IMAGE_BACKEND == "off":
            return []
        raise ImageBackendConfigurationError(f"unsupported image backend: {IMAGE_BACKEND}")


def maybe_generate_sprite(data: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    visual.setdefault("authoringPolicy", "ai_primary_non_procedural")
    canvas = int(visual.get("preferredCanvasSize") or 32)
    prompt = normalize_asset_prompt(data, "item", str(visual.get("imagePrompt") or ""), canvas)
    visual["imagePrompt"] = prompt
    topology, minimum, maximum = _authored_sprite_topology(data, "item")
    request = _ImageRequest(
        logical_asset_id=str(data.get("id") or "sprite"), audit_role="item", processing_role="item",
        prompt=prompt, negative=str(visual.get("negativePrompt") or ""), canvas=canvas,
        topology=topology, part_count_min=minimum, part_count_max=maximum,
        policy=_PublicationPolicy.ITEM, publication_identity=_legacy_publication_identity(data, "item", "", str(data.get("id") or "sprite")),
    )
    result = _execute_image_request(data, request)
    visual["finalItemPrompt"] = result.final_prompt
    visual["spriteStatus"] = result.status
    if result.status == "prompt_only":
        return data
    visual.update(spritePath=result.public_path, spriteUrl=result.url, spriteRawPath=result.raw_path if result.public_path else "")
    if result.status == "backend_config_error":
        return data
    visual["spriteTechnicalScore"] = round(result.technical_score, 3)
    visual["semanticReviewStatus"] = "not_performed"
    visual.pop("visualJudgeScore", None)
    if result.public_path:
        if result.status != "fallback_after_failed_generation":
            visual["spriteCandidateScore"] = result.candidate_score
        validation = result.validation if result.status != "fallback_after_failed_generation" else {"ok": True, "source": "procedural_fallback"}
        try:
            attach_visual_soul_from_sprite(data, result.public_path, validation=validation, score=result.technical_score)
        except OSError as exc:
            # The PNG is committed, but a failed local projection must not leave
            # a usable DTO or cause another model call. Keep private receipts.
            failed = replace(result, public_path="", raw_path="", status="failed", error=repr(exc), failure_phase="projection")
            _finish_image_request(data, request, failed, [*result.attempts, {"attempt": result.final_prompt_attempt, "ok": False, "error": repr(exc), "phase": "projection"}])
            visual.update(spritePath="", spriteUrl="", spriteRawPath="", spriteStatus="failed")
    return data


def _validation_reasons(validation: dict[str, Any] | None) -> list[str]:
    if not isinstance(validation, dict):
        return []
    return [str(x) for x in (validation.get("reasons") or [])]

def refit_processed_sprite_to_contract(path: str, asset_id: str, canvas: int, role: str, validation: dict[str, Any] | None, *, output_dir: Path | None = None) -> str:
    """Local no-regeneration salvage for fit-only sprite failures.

    If image generation produced a good subject but the final fit made the core silhouette
    a few pixels too small, crop the transparent bbox, scale it with the production BOX
    filter, and center it back on the target canvas. Fatal alpha/key failures are not
    repaired here.
    """
    if role == "vfx_strip":
        return ""
    reasons = _validation_reasons(validation)
    if not any("silhouette_too_small" in r or "core_silhouette_too_small" in r or "effect_silhouette_too_small" in r for r in reasons):
        return ""
    if Image is None or not path or not Path(path).exists():
        return ""
    try:
        img = load_image_input(path, Image)
        stats = validation.get("stats") if isinstance(validation, dict) and isinstance(validation.get("stats"), dict) else {}
        bbox_stats = validation.get("bboxStats") if isinstance(validation, dict) and isinstance(validation.get("bboxStats"), dict) else {}
        bbox = bbox_stats.get("core_bbox") or bbox_stats.get("effect_bbox") or stats.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            bbox = img.getbbox()
        if not bbox:
            return ""
        left, top, right, bottom = [int(round(float(x))) for x in bbox]
        left = max(0, min(img.width - 1, left)); top = max(0, min(img.height - 1, top))
        right = max(left + 1, min(img.width, right)); bottom = max(top + 1, min(img.height, bottom))
        crop = img.crop((left, top, right, bottom))
        spec = bbox_stats.get("spec") if isinstance(bbox_stats.get("spec"), dict) else {}
        margin = int(spec.get("marginPx") or (2 if canvas >= 48 else 1))
        target = int(spec.get("targetLongAxisPx") or round(canvas * (0.84 if role == "projectile" else 0.88)))
        target = max(1, min(canvas - margin * 2, target))
        long_axis = max(crop.width, crop.height)
        if long_axis <= 0:
            return ""
        scale = target / float(long_axis)
        max_scale = min((canvas - 2 * margin) / max(1, crop.width), (canvas - 2 * margin) / max(1, crop.height))
        scale = max(1.0, min(scale, max_scale))
        if scale <= 1.01:
            return ""
        new_w = max(1, min(canvas - 2 * margin, int(round(crop.width * scale))))
        new_h = max(1, min(canvas - 2 * margin, int(round(crop.height * scale))))
        resampling = getattr(getattr(Image, "Resampling", Image), "BOX", 4)
        resized = crop.resize((new_w, new_h), resampling)
        out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        out.alpha_composite(resized, ((canvas - new_w) // 2, (canvas - new_h) // 2))
        out = cleanup_alpha(out, role)
        out_path = (output_dir if output_dir is not None else SPRITE_DIR) / f"{safe_file_part(asset_id, 'sprite')}_refit.png"
        save_image_output(out, out_path)
        return str(out_path)
    except ImageOutputIOError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        return ""

def _publish_image_png(identity: bytes, path: str, *, prefix: str = "infini_asset_png_") -> str:
    """Commit final bytes atomically; AssetSync still owns integrity descriptors."""
    raw = Path(path).read_bytes()
    name = prefix + hashlib.sha256(identity + b"\0" + raw).hexdigest() + ".png"
    SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    destination = SPRITE_DIR / name
    fd, temporary = tempfile.mkstemp(prefix="." + name + ".", suffix=".part", dir=SPRITE_DIR)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination.resolve())


def _publish_vfx_png(data: dict[str, Any], asset_id: str, path: str) -> str:
    """Keep the accepted VFX exact recipe/asset + NUL + bytes identity."""
    manifest = data["vfxManifest"]
    recipe_id = manifest["recipeId"] if "recipeId" in manifest else data["id"]
    identity = json.dumps([recipe_id, asset_id], ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    return _publish_image_png(identity, path, prefix="infini_vfx_png_")


class _PublicationPolicy(Enum):
    ITEM = "item"
    LEGACY_ASSET = "legacy_asset"
    REQUIRED_VFX = "required_vfx"


@dataclass(frozen=True)
class _ImageRequest:
    logical_asset_id: str
    audit_role: str
    processing_role: str
    prompt: str
    negative: str
    canvas: int
    topology: str
    part_count_min: int
    part_count_max: int
    policy: _PublicationPolicy
    publication_identity: bytes


@dataclass(frozen=True)
class _ImageResult:
    public_path: str = ""
    raw_path: str = ""
    status: str = "failed"
    technical_score: float = 0.0
    candidate_score: float = 0.0
    final_prompt: str = ""
    final_prompt_attempt: int = 0
    validation: dict[str, Any] | None = None
    refit: dict[str, Any] | None = None
    attempts: tuple[dict[str, Any], ...] = ()
    error: str = ""
    failure_phase: str = ""
    private_dir: str = ""
    discarded_path: str = ""
    late_warning: bool = False

    @property
    def url(self) -> str:
        return f"/sprite/{Path(self.public_path).name}" if self.public_path else ""


def _legacy_publication_identity(data: dict[str, Any], role: str, entity_id: str, asset_id: str) -> bytes:
    # Structured exact identities cannot alias role/entity concatenations.
    return json.dumps([data.get("id"), role, entity_id, asset_id], ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _new_image_workspace() -> Path:
    """Retain invocation-owned diagnostics outside both PNG-serving roots.

    These are cache diagnostics, not temporary public assets. Retention is explicit
    in each result receipt; no invocation deletes another invocation's evidence.
    """
    root = SPRITE_DIR.parent / "image-diagnostics"
    serving_roots = (SPRITE_DIR.resolve(), WORLD_RECIPES_DIR.resolve())
    if any(root.resolve().is_relative_to(serving) for serving in serving_roots):
        root = Path(tempfile.gettempdir()) / "infini-image-diagnostics"
    if any(root.resolve().is_relative_to(serving) for serving in serving_roots):
        raise OSError("private image diagnostics must be outside PNG-serving roots")
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="image-", dir=root))


def _finish_image_request(data: dict[str, Any], request: _ImageRequest, result: _ImageResult,
                          attempts: list[dict[str, Any]]) -> _ImageResult:
    result = replace(result, attempts=tuple(attempts))
    debug = data.setdefault("debug", {})
    prefix = "item" if request.policy is _PublicationPolicy.ITEM else request.audit_role
    debug[prefix + "FinalPrompt"] = result.final_prompt
    debug[prefix + "FinalPromptAttempt"] = result.final_prompt_attempt
    debug[prefix + "SpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
    if result.private_dir:
        debug[prefix + "SpriteDiagnostics"] = json.dumps({
            "retention": "retained_private", "directory": result.private_dir,
        }, ensure_ascii=False)
    if result.error:
        debug["spriteError" if request.policy is _PublicationPolicy.ITEM else prefix + "SpriteError"] = result.error
    if result.failure_phase:
        debug[prefix + "SpriteFailurePhase"] = result.failure_phase
    else:
        debug.pop(prefix + "SpriteFailurePhase", None)
    if result.refit:
        debug[prefix + "SpriteRefit"] = json.dumps(result.refit, ensure_ascii=False)
    if result.discarded_path:
        key = "itemSpriteInvalidGeneratedDiscarded" if request.policy is _PublicationPolicy.ITEM else prefix + "InvalidGeneratedDiscarded"
        debug[key] = result.discarded_path
    if result.late_warning:
        debug[prefix + "InvalidGeneratedUsedAsWarn"] = json.dumps({
            "path": result.public_path, "reasons": _validation_reasons(result.validation),
            "policy": "strict_ai_authorship_keep_imperfect_ai_sprite_not_placeholder",
        }, ensure_ascii=False)
    if result.public_path:
        if request.policy is not _PublicationPolicy.ITEM:
            debug[prefix + "SpriteTechnicalScore"] = round(result.technical_score, 3)
            debug[prefix + "SpriteCandidateScore"] = result.candidate_score
        if result.validation and not result.validation.get("ok") and not result.late_warning:
            debug[prefix + "SpriteAcceptedWithWarnings"] = json.dumps(result.validation, ensure_ascii=False)
    return result


def _execute_image_request(data: dict[str, Any], request: _ImageRequest) -> _ImageResult:
    """The sole budget → generate → process → validate/refit → commit lifecycle."""
    result = _ImageResult(final_prompt=truncate_prompt_at_boundary(request.prompt, 1800))
    attempts: list[dict[str, Any]] = []
    if IMAGE_BACKEND == "off":
        return replace(result, status="prompt_only")
    config_error = _backend_configuration_error()
    if config_error:
        data.setdefault("debug", {})["imageBackendConfigError"] = config_error
        trace_event("error", f"IMAGE:{request.audit_role}", "image backend configuration is invalid", {"backend": IMAGE_BACKEND, "error": config_error})
        return replace(result, status="backend_config_error", failure_phase="configuration", error=config_error)
    try:
        workspace = _new_image_workspace()
    except OSError as exc:
        result = replace(result, failure_phase="processing", error=repr(exc))
        return _finish_image_request(data, request, result, attempts)
    result = replace(result, private_dir=str(workspace.resolve()))
    required_vfx = request.policy is _PublicationPolicy.REQUIRED_VFX
    # This accepted nonce/digest is ALSO a workflow input. Never replace it with a
    # stable VFX plan ID or apply it to legacy roles just to isolate filenames.
    nonce = uuid.uuid4().hex if required_vfx else ""
    validation_kwargs: dict[str, Any] = dict(topology=request.topology, part_count_min=request.part_count_min, part_count_max=request.part_count_max)
    if required_vfx:
        validation_kwargs["expected_canvas"] = request.canvas
    process_kwargs: dict[str, Any] = dict(topology=request.topology, part_count_min=request.part_count_min, part_count_max=request.part_count_max)
    last_path = ""
    terminal = False
    for attempt in range(max(1, int(SPRITE_RETRIES) + 1)):
        if nonce:
            identity = f"{request.logical_asset_id}\0{nonce}\0{attempt}".encode("utf-8")
            attempt_id = "infini_vfx_job_" + hashlib.sha256(identity).hexdigest()
        else:
            attempt_id = request.logical_asset_id if attempt == 0 else f"{request.logical_asset_id}_retry{attempt}"
        prompt = request.prompt if attempt == 0 else build_retry_prompt_from_validation(request.prompt, result.validation or {}, request.processing_role, attempt, request.canvas)
        result = replace(result, final_prompt=prompt, final_prompt_attempt=attempt)
        trace_event("prompt", f"IMAGE:{request.audit_role}", f"{IMAGE_BACKEND} {request.audit_role} prompt attempt {attempt}", {
            "assetId": request.logical_asset_id, "attemptId": attempt_id, "attempt": attempt, "role": request.audit_role,
            "backend": IMAGE_BACKEND, "canvas": request.canvas, "spriteRetries": SPRITE_RETRIES,
        }, prompt=prompt, negative=request.negative)
        phase = "processing"
        try:
            output_dir = workspace / f"attempt-{attempt}"
            output_dir.mkdir()
            phase = "backend"
            variants = _generate_backend_variants(data, prompt=prompt, negative=request.negative,
                asset_id=attempt_id, canvas=request.canvas, role=request.processing_role, output_dir=output_dir)
            variants = [path for path in variants if path and Path(path).exists()]
            if not variants:
                attempts.append({"attempt": attempt, "ok": False, "status": "no_raw_image"})
                if request.policy is _PublicationPolicy.ITEM:
                    trace_event("step", "IMAGE:item", "no raw image returned", {"assetId": request.logical_asset_id, "attempt": attempt, "backend": IMAGE_BACKEND})
                continue
            phase = "selection"
            best, score = pick_best_sprite(variants, request.processing_role, request.canvas)
            phase = "processing"
            final = postprocess_sprite(best, attempt_id, request.canvas, request.processing_role, output_dir=output_dir, **process_kwargs)
            phase = "validation"
            validation = validate_processed_sprite(final, request.processing_role, **validation_kwargs)
            refit_path = ""
            refit_validation = None
            if request.processing_role != "vfx_strip" and not validation.get("ok") and not sprite_validation_fatal(validation):
                phase = "processing"
                refit_path = refit_processed_sprite_to_contract(final, attempt_id, request.canvas, request.processing_role, validation, output_dir=output_dir)
                if refit_path:
                    phase = "validation"
                    refit_validation = validate_processed_sprite(refit_path, request.processing_role, **validation_kwargs)
                    if refit_validation.get("ok"):
                        result = replace(result, refit={"from": str(Path(final).resolve()), "to": str(Path(refit_path).resolve()), "before": validation, "after": refit_validation})
                        final, validation = refit_path, refit_validation
            row = {"attempt": attempt, "raw": best, "final": final, "score": technical_validation_score(validation),
                   "candidateScore": round(float(score), 3), "validation": validation}
            if refit_path:
                row["refit"] = {"path": refit_path, "validation": refit_validation}
            attempts.append(row)
            last_path = final
            result = replace(result, raw_path=str(Path(best).resolve()), technical_score=row["score"], candidate_score=row["candidateScore"], validation=validation)
            if validation.get("ok") or not sprite_validation_fatal(validation):
                if required_vfx and sprite_status_from_raw_path(best, IMAGE_BACKEND) not in {"generated", "generated_warn_invalid"}:
                    row["status"] = "rejected_non_authored_fallback"
                    result = replace(result, technical_score=0.0)
                    continue
                phase = "publication"
                published = (_publish_vfx_png(data, request.audit_role.removeprefix("vfx:"), final) if required_vfx
                             else _publish_image_png(request.publication_identity, final))
                status = sprite_status_from_raw_path(best, IMAGE_BACKEND, invalid=not bool(validation.get("ok")))
                phase = "projection"
                trace_event("step", f"IMAGE:{request.audit_role}", "sprite accepted", {
                    "assetId": request.logical_asset_id, "attempt": attempt, "raw": best, "final": published,
                    "score": result.technical_score, "candidateScore": result.candidate_score, "status": status, "validation": validation,
                })
                result = replace(result, public_path=published, status=status, failure_phase="")
                return _finish_image_request(data, request, result, attempts)
        except Exception as exc:
            attempts.append({"attempt": attempt, "ok": False, "error": repr(exc), "phase": phase})
            result = replace(result, public_path="", status="failed", error=repr(exc), failure_phase=phase)
            trace_event("error", f"IMAGE:{request.audit_role}", "sprite generation attempt failed", {"assetId": request.logical_asset_id, "attempt": attempt, "backend": IMAGE_BACKEND}, error=repr(exc))
            log_event("warn", f"{request.audit_role} sprite generation attempt failed", {"attempt": attempt, "error": repr(exc), "trace": traceback.format_exc()})
            if (isinstance(exc, (CodexError, ImageOutputIOError)) or phase == "publication"
                    or (isinstance(exc, OSError) and phase in {"processing", "projection"})):
                terminal = True
                break
    if last_path:
        result = replace(result, discarded_path=str(Path(last_path).resolve()))
        # Separate legacy compatibility recovery after a projection-tail fault;
        # it never turns a local commit failure or VFX failure into a usable PNG.
        if not terminal and request.policy is _PublicationPolicy.LEGACY_ASSET and not sprite_validation_fatal(result.validation) and Path(last_path).exists():
            try:
                published = _publish_image_png(request.publication_identity, last_path)
                result = replace(result, public_path=published, status="generated_warn_invalid", failure_phase="", late_warning=True)
                return _finish_image_request(data, request, result, attempts)
            except OSError as exc:
                terminal = True
                result = replace(result, error=repr(exc), failure_phase="publication")
    if not terminal and not required_vfx and IMAGE_BACKEND != "openai_codex" and VISUAL_ALLOW_PROCEDURAL_FALLBACK and not VISUAL_STRICT_AI_AUTHORSHIP:
        phase = "processing"
        try:
            output_dir = workspace / "fallback"
            output_dir.mkdir()
            fallback = visual_asset_pipeline.generate_procedural_asset(data, request.audit_role, variant=0,
                canvas_size=request.canvas, sprite_dir=output_dir, image_cls=Image, image_draw_cls=ImageDraw)
            final = postprocess_sprite(fallback, request.logical_asset_id, request.canvas, request.audit_role, output_dir=output_dir, **process_kwargs)
            phase = "publication"
            published = _publish_image_png(request.publication_identity, final)
            result = replace(result, public_path=published, raw_path=str(Path(fallback).resolve()), status="fallback_after_failed_generation", technical_score=0.0, failure_phase="")
            return _finish_image_request(data, request, result, attempts)
        except Exception as exc:
            result = replace(result, error=repr(exc), failure_phase=phase)
            if request.policy is _PublicationPolicy.ITEM:
                data.setdefault("debug", {})["spriteFallbackError"] = repr(exc)
            log_event("warn", f"{request.audit_role} sprite procedural fallback failed", {"error": repr(exc)})
    if required_vfx:
        result = replace(result, technical_score=0.0)
    trace_event("error", f"IMAGE:{request.audit_role}", "sprite generation failed completely", {"assetId": request.logical_asset_id, "role": request.audit_role, "backend": IMAGE_BACKEND, "attempts": attempts})
    return _finish_image_request(data, request, result, attempts)


def generate_visual_asset(data: dict[str, Any], role: str, prompt: str, negative: str, asset_id: str, canvas: int, *, entity_id: str = "", processing_role: str = "", publication_entity_id: str = "") -> tuple[str, str, float, str]:
    """Adapt one authored role into the common image-attempt lifecycle."""
    contract_role = processing_role or ("impact" if role.startswith("impact_") else role)
    base_prompt = normalize_asset_prompt(data, contract_role, prompt, canvas)
    debug = data.setdefault("debug", {})
    debug[f"{role}FinalPrompt"] = truncate_prompt_at_boundary(base_prompt, 1800)
    debug[f"{role}AuthoringPolicy"] = "ai_primary_non_procedural"
    topology, minimum, maximum = _authored_sprite_topology(data, "entity:" + entity_id if entity_id else role)
    policy = _PublicationPolicy.REQUIRED_VFX if contract_role in {"vfx_cutout", "vfx_strip"} else _PublicationPolicy.LEGACY_ASSET
    request = _ImageRequest(logical_asset_id=asset_id, audit_role=role, processing_role=contract_role,
        prompt=base_prompt, negative=str(negative or ""), canvas=canvas, topology=topology,
        part_count_min=minimum, part_count_max=maximum, policy=policy,
        publication_identity=_legacy_publication_identity(data, role, publication_entity_id or entity_id, asset_id))
    result = _execute_image_request(data, request)
    return result.public_path, result.url, round(result.technical_score, 3), result.status


def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def maybe_generate_visual_assets(data: dict[str, Any]) -> dict[str, Any]:
    """Generate exactly the assets authored for accepted runtime entities.

    The function never invents projectile/impact/child roles.  Every non-item
    image is keyed by a stable runtime entity ID and an explicit Visual Director
    ``assetMode``.
    """
    # Validate declared requests/references before any image job, including item.
    # Rebuild the ordinary plan after item hydration to retain legacy projections.
    build_visual_asset_plan(data)
    data = maybe_generate_sprite(data)
    visual = data.setdefault("visual", {})
    item_path = str(visual.get("spritePath") or "")
    item_url = str(visual.get("spriteUrl") or "")
    item_status = str(visual.get("spriteStatus") or "")
    item_score = float(visual.get("spriteTechnicalScore") or 0.0)

    plan = build_visual_asset_plan(data)
    by_id = {str(row.get("id") or ""): row for row in _runtime_entities(data)}
    raw_kit = data.get("visualKit")
    visual_kit: dict[str, Any] = raw_kit if isinstance(raw_kit, dict) else {}
    raw_item_kit = visual_kit.get("item")
    item_kit: dict[str, Any] = raw_item_kit if isinstance(raw_item_kit, dict) else {}
    director_negative = str(item_kit.get("negativePrompt") or "").strip()

    for slot in plan:
        if not isinstance(slot, dict):
            continue
        role = str(slot.get("role") or "")
        if role.startswith("vfx:"):
            asset = next(row for row in data["vfxManifest"]["assets"] if row["id"] == slot["vfxAssetId"])
            path, url, score, status = generate_visual_asset(
                data, role, slot["prompt"], slot["negativePrompt"], slot["assetId"], slot["canvas"],
                processing_role=slot["processingRole"],
            )
            asset.update(spritePath=path, spriteUrl=url, spriteStatus=status, spriteTechnicalScore=score)
            slot.update(path=path, url=url, status=status, technicalScore=score)
            continue
        if role == "equip_overlay":
            prompt = str(slot.get("prompt") or visual.get("equipOverlayPrompt") or "")
            canvas = int(slot.get("canvas") or 48)
            path, url, score, status = generate_visual_asset(
                data,
                "equip_overlay",
                prompt,
                director_negative,
                str(slot.get("assetId") or f"{data.get('id')}_equip_overlay"),
                canvas,
            )
            final_prompt = str(data.get("debug", {}).get("equip_overlayFinalPrompt") or "")
            if final_prompt:
                slot["prompt"] = final_prompt
                visual["equipOverlayPrompt"] = final_prompt
            usable = bool(path) and status not in {"failed", "prompt_only", "placeholder", "backend_config_error"}
            visual.update({
                "equipOverlayStatus": status,
                "equipOverlayPath": path if usable else "",
                "equipOverlayUrl": url if usable else "",
                "equipOverlayTechnicalScore": score if usable else 0.0,
            })
            slot.update({
                "status": status,
                "path": path if usable else "",
                "url": url if usable else "",
                "technicalScore": score if usable else 0.0,
            })
            continue
        if role.startswith("impact:"):
            entity_id = str(slot.get("entityId") or "")
            entity = by_id.get(entity_id)
            if not isinstance(entity, dict):
                slot.update({"status": "invalid_missing_entity", "path": "", "url": "", "technicalScore": 0.0})
                continue
            entity_visual = entity.setdefault("visual", {})
            prompt = str(slot.get("prompt") or "")
            negative = str(slot.get("negativePrompt") or "")
            canvas = int(slot.get("canvas") or 32)
            backend_role = "impact"
            path, url, score, status = generate_visual_asset(
                data,
                backend_role,
                prompt,
                negative,
                str(slot.get("assetId") or f"{data.get('id')}_{entity_id}_impact"),
                canvas,
                publication_entity_id=entity_id,
            )
            final_prompt = str(data.get("debug", {}).get(f"{backend_role}FinalPrompt") or "")
            entity_visual["impactPrompt"] = final_prompt or prompt
            entity_visual["impactNegativePrompt"] = negative
            if final_prompt:
                slot["prompt"] = final_prompt
            usable = bool(path) and status not in {"failed", "prompt_only", "placeholder", "backend_config_error"}
            entity_visual.update({
                "impactSpriteStatus": status,
                "impactSpritePath": path if usable else "",
                "impactSpriteUrl": url if usable else "",
                "impactSpriteTechnicalScore": score if usable else 0.0,
            })
            slot.update({
                "status": status,
                "path": path if usable else "",
                "url": url if usable else "",
                "technicalScore": score if usable else 0.0,
            })
            continue
        entity_id = str(slot.get("entityId") or "")
        entity = by_id.get(entity_id)
        if not isinstance(entity, dict):
            slot.update({"status": "invalid_missing_entity", "path": "", "url": "", "technicalScore": 0.0})
            continue
        entity_visual = entity.setdefault("visual", {})
        mode = str(slot.get("assetMode") or "").strip().lower()
        if entity.get("kind") == "item_body":
            slot.update({"status": item_status, "path": item_path, "url": item_url, "technicalScore": item_score})
            entity_visual.update({"assetMode": "baked_sprite", "spriteStatus": item_status, "spritePath": item_path, "spriteUrl": item_url, "spriteTechnicalScore": item_score})
            continue
        if mode == "reuse_item_icon":
            status = item_status if item_path else "required_item_icon_missing"
            entity_visual.update({"spriteStatus": status, "spritePath": item_path, "spriteUrl": item_url, "spriteTechnicalScore": item_score})
            slot.update({"status": status, "path": item_path, "url": item_url, "technicalScore": item_score})
            continue
        if mode in {"runtime_geometry", "no_asset"}:
            entity_visual.update({"spriteStatus": "not_required", "spritePath": "", "spriteUrl": "", "spriteTechnicalScore": 0.0})
            slot.update({"status": "not_required", "path": "", "url": "", "technicalScore": 0.0})
            continue
        if mode != "baked_sprite":
            entity_visual.update({"spriteStatus": "invalid_or_missing_authored_asset_mode", "spritePath": "", "spriteUrl": "", "spriteTechnicalScore": 0.0})
            slot.update({"status": "invalid_or_missing_authored_asset_mode", "path": "", "url": "", "technicalScore": 0.0})
            continue
        if VISUAL_ASSET_MODE not in {"full", "projectile", "all", "visualpack", "assetpack"}:
            entity_visual["spriteStatus"] = "skipped_disabled_by_settings"
            slot["status"] = "skipped_disabled_by_settings"
            continue
        prompt = str(slot.get("prompt") or entity_visual.get("prompt") or "")
        canvas = int(slot.get("canvas") or 32)
        expected_role = VISUAL_ROLE_BY_ENTITY_KIND.get(str(slot.get("entityKind") or ""))
        declared_role = str(slot.get("visualRole") or "")
        if not expected_role or (declared_role and declared_role != expected_role):
            entity_visual["spriteStatus"] = "invalid_runtime_visual_role"
            slot.update(status="invalid_runtime_visual_role", path="", url="", technicalScore=0.0)
            continue
        # Exact registry projection, not a name/prose router. The namespace keeps
        # runtime pose independent of the legacy +X projectile processing path.
        backend_role = "runtime:" + expected_role
        path, url, score, status = generate_visual_asset(
            data,
            backend_role,
            prompt,
            director_negative,
            str(slot.get("assetId") or f"{data.get('id')}_{entity_id}"),
            canvas,
            entity_id=entity_id,
        )
        final_prompt = str(data.get("debug", {}).get(f"{backend_role}FinalPrompt") or "")
        if final_prompt:
            slot["prompt"] = final_prompt
        usable = bool(path) and status not in {"failed", "prompt_only", "placeholder", "backend_config_error"}
        entity_visual.update({
            "spriteStatus": status,
            "spritePath": path if usable else "",
            "spriteUrl": url if usable else "",
            "spriteTechnicalScore": score if usable else 0.0,
        })
        slot.update({
            "status": status,
            "path": path if usable else "",
            "url": url if usable else "",
            "technicalScore": score if usable else 0.0,
        })

    data.setdefault("debug", {})["visualAssetPlan"] = json.dumps(plan, ensure_ascii=False)
    write_visual_manifest(data, plan)
    return data


__all__ = [
    "ImageBackendConfigurationError",
    "_backend_configuration_error",
    "_generate_backend_variants",
    "maybe_generate_sprite",
    "_validation_reasons",
    "refit_processed_sprite_to_contract",
    "generate_visual_asset",
    "maybe_generate_visual_assets",
]
