from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import SPRITE_DIR
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
from infini_local.services.visual_asset_pipeline import sprite_status_from_raw_path, truncate_prompt_at_boundary
from infini_local.storage.trace_runtime import (
    log_event,
    trace_event,
)
from infini_local.pipelines.image_backend_pipeline import (
    generate_a1111,
    generate_comfyui,
    generate_image_api,
    generate_sdcpp,
)
from infini_local.pipelines.sprite_postprocess import (
    build_retry_prompt_from_validation,
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
) -> list[str]:
    """Dispatch one configured backend without silently changing authorship mode."""
    config_error = _backend_configuration_error()
    if config_error:
        raise ImageBackendConfigurationError(config_error)
    with IMAGE_GENERATION_GATE.slot():
        if IMAGE_BACKEND == "a1111":
            return generate_a1111(prompt, negative, asset_id, canvas)
        if IMAGE_BACKEND == "comfyui":
            return generate_comfyui(prompt, negative, asset_id)
        if IMAGE_BACKEND == "sdcpp":
            return generate_sdcpp(prompt, negative, asset_id, canvas)
        if IMAGE_BACKEND == "image_api":
            return generate_image_api(prompt, negative, asset_id, canvas)
        if IMAGE_BACKEND == "procedural":
            if role == "item":
                return [
                    visual_asset_pipeline.generate_procedural_sprite(
                        data,
                        variant=i,
                        sprite_dir=SPRITE_DIR,
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
                    sprite_dir=SPRITE_DIR,
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
    base_prompt = normalize_asset_prompt(data, "item", str(visual.get("imagePrompt") or ""), int(visual.get("preferredCanvasSize") or 32))
    visual["imagePrompt"] = base_prompt
    visual["finalItemPrompt"] = truncate_prompt_at_boundary(base_prompt, 1800)
    if IMAGE_BACKEND == "off":
        visual["spriteStatus"] = "prompt_only"
        return data
    config_error = _backend_configuration_error()
    if config_error:
        visual["spriteStatus"] = "backend_config_error"
        visual["spritePath"] = ""
        visual["spriteRawPath"] = ""
        visual["spriteUrl"] = ""
        data.setdefault("debug", {})["imageBackendConfigError"] = config_error
        trace_event("error", "IMAGE:item", "image backend configuration is invalid", {"backend": IMAGE_BACKEND, "error": config_error})
        return data
    canvas = int(visual.get("preferredCanvasSize") or 32)
    topology, part_count_min, part_count_max = _authored_sprite_topology(data, "item")
    negative = str(visual.get("negativePrompt") or "")
    asset_id = str(data.get("id") or "sprite")
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(SPRITE_RETRIES) + 1)
    last_path = ""
    last_raw_path = ""
    last_score = 0.0
    last_validation: dict[str, Any] | None = None
    for attempt in range(max_attempts):
        attempt_id = asset_id if attempt == 0 else f"{asset_id}_retry{attempt}"
        attempt_prompt = base_prompt if attempt == 0 else build_retry_prompt_from_validation(base_prompt, last_validation or {}, "item", attempt, canvas)
        visual["finalItemPrompt"] = attempt_prompt
        data.setdefault("debug", {})["itemFinalPrompt"] = attempt_prompt
        data["debug"]["itemFinalPromptAttempt"] = attempt
        trace_event("prompt", "IMAGE:item", f"{IMAGE_BACKEND} item prompt attempt {attempt}", {
            "assetId": asset_id, "attemptId": attempt_id, "attempt": attempt, "role": "item",
            "backend": IMAGE_BACKEND, "canvas": canvas, "spriteRetries": SPRITE_RETRIES,
        }, prompt=attempt_prompt, negative=negative)
        try:
            variants = _generate_backend_variants(
                data,
                prompt=attempt_prompt,
                negative=negative,
                asset_id=attempt_id,
                canvas=canvas,
                role="item",
            )
            variants = [p for p in variants if p and Path(p).exists()]
            if not variants:
                attempts.append({"attempt": attempt, "ok": False, "status": "no_raw_image"})
                trace_event("step", "IMAGE:item", "no raw image returned", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND})
                continue
            best, score = pick_best_sprite(variants, "item", canvas)
            raw_best = best
            final_path = postprocess_sprite(
                best, attempt_id, canvas, "item", topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
            )
            validation = validate_processed_sprite(
                final_path, "item", topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
            )
            refit_path = ""
            refit_validation: dict[str, Any] | None = None
            if not validation.get("ok") and not sprite_validation_fatal(validation):
                refit_path = refit_processed_sprite_to_contract(final_path, attempt_id, canvas, "item", validation)
                if refit_path:
                    refit_validation = validate_processed_sprite(
                        refit_path, "item", topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
                    )
                    if refit_validation.get("ok"):
                        data.setdefault("debug", {})["itemSpriteRefit"] = json.dumps({
                            "from": str(Path(final_path).resolve()),
                            "to": str(Path(refit_path).resolve()),
                            "before": validation,
                            "after": refit_validation,
                        }, ensure_ascii=False)
                        final_path = refit_path
                        validation = refit_validation
            technical_score = technical_validation_score(validation)
            attempt_row = {"attempt": attempt, "raw": raw_best, "final": final_path, "score": technical_score, "candidateScore": round(float(score), 3), "validation": validation}
            if refit_path:
                attempt_row["refit"] = {"path": refit_path, "validation": refit_validation}
            attempts.append(attempt_row)
            last_path = final_path
            last_raw_path = raw_best
            last_score = technical_score
            last_validation = validation if isinstance(validation, dict) else None
            if validation.get("ok") or not sprite_validation_fatal(validation):
                if attempt != 0:
                    canonical = SPRITE_DIR / f"{data.get('id', 'sprite')}.png"
                    try:
                        import shutil
                        shutil.copyfile(final_path, canonical)
                        final_path = str(canonical)
                    except Exception as exc:
                        data.setdefault("debug", {})["itemSpriteCanonicalCopyError"] = json.dumps({
                            "from": str(final_path),
                            "to": str(canonical),
                            "error": repr(exc),
                        }, ensure_ascii=False)
                visual["spritePath"] = str(Path(final_path).resolve())
                visual["spriteRawPath"] = str(Path(raw_best).resolve())
                visual["spriteStatus"] = sprite_status_from_raw_path(raw_best, IMAGE_BACKEND, invalid=not bool(validation.get("ok")))
                visual["spriteTechnicalScore"] = round(last_score, 3)
                visual["semanticReviewStatus"] = "not_performed"
                visual.pop("visualJudgeScore", None)
                visual["spriteCandidateScore"] = round(float(score), 3)
                visual["spriteUrl"] = f"/sprite/{Path(final_path).name}"
                attach_visual_soul_from_sprite(data, final_path, validation=validation, score=last_score)
                if not validation.get("ok"):
                    data.setdefault("debug", {})["itemSpriteAcceptedWithWarnings"] = json.dumps(validation, ensure_ascii=False)
                data.setdefault("debug", {})["itemSpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
                trace_event("step", "IMAGE:item", "sprite accepted", {
                    "assetId": asset_id, "attempt": attempt, "raw": str(Path(raw_best).resolve()), "final": str(Path(final_path).resolve()),
                    "score": last_score, "candidateScore": round(float(score), 3), "status": visual.get("spriteStatus", ""), "validation": validation,
                })
                return data
        except Exception as e:
            attempts.append({"attempt": attempt, "ok": False, "error": repr(e)})
            data.setdefault("debug", {})["spriteError"] = repr(e)
            trace_event("error", "IMAGE:item", "sprite generation attempt failed", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND}, error=repr(e))
            log_event("warn", "sprite generation failed", {"attempt": attempt, "error": repr(e), "trace": traceback.format_exc()})
    data.setdefault("debug", {})["itemSpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
    if last_path:
        data.setdefault("debug", {})["itemSpriteInvalidGeneratedDiscarded"] = str(Path(last_path).resolve())
    if VISUAL_ALLOW_PROCEDURAL_FALLBACK and not VISUAL_STRICT_AI_AUTHORSHIP:
        try:
            fallback = visual_asset_pipeline.generate_procedural_asset(data, "item", variant=0, canvas_size=canvas, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)
            final = postprocess_sprite(
                fallback, str(data.get("id", "sprite")), canvas, "item",
                topology=topology, part_count_min=part_count_min, part_count_max=part_count_max,
            )
            visual["spritePath"] = str(Path(final).resolve())
            visual["spriteRawPath"] = str(Path(fallback).resolve())
            visual["spriteStatus"] = "fallback_after_failed_generation"
            visual["spriteTechnicalScore"] = 0.0
            visual["semanticReviewStatus"] = "not_performed"
            visual.pop("visualJudgeScore", None)
            visual["spriteUrl"] = f"/sprite/{Path(final).name}"
            attach_visual_soul_from_sprite(data, final, validation={"ok": True, "source": "procedural_fallback"}, score=0.0)
            return data
        except Exception as e:
            data.setdefault("debug", {})["spriteFallbackError"] = repr(e)
    visual["spriteStatus"] = "failed"
    visual["spritePath"] = ""
    visual["spriteRawPath"] = ""
    visual["spriteUrl"] = ""
    visual["spriteTechnicalScore"] = round(last_score, 3)
    visual["semanticReviewStatus"] = "not_performed"
    visual.pop("visualJudgeScore", None)
    return data

def _validation_reasons(validation: dict[str, Any] | None) -> list[str]:
    if not isinstance(validation, dict):
        return []
    return [str(x) for x in (validation.get("reasons") or [])]

def refit_processed_sprite_to_contract(path: str, asset_id: str, canvas: int, role: str, validation: dict[str, Any] | None) -> str:
    """Local no-regeneration salvage for fit-only sprite failures.

    If image generation produced a good subject but the final fit made the core silhouette
    a few pixels too small, crop the transparent bbox, scale it with the production BOX
    filter, and center it back on the target canvas. Fatal alpha/key failures are not
    repaired here.
    """
    reasons = _validation_reasons(validation)
    if not any("silhouette_too_small" in r or "core_silhouette_too_small" in r or "effect_silhouette_too_small" in r for r in reasons):
        return ""
    if Image is None or not path or not Path(path).exists():
        return ""
    try:
        img = Image.open(path).convert("RGBA")
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
        out_path = SPRITE_DIR / f"{asset_id}_refit.png"
        out.save(out_path)
        return str(out_path)
    except (OSError, ValueError, TypeError, AttributeError):
        return ""

def generate_visual_asset(data: dict[str, Any], role: str, prompt: str, negative: str, asset_id: str, canvas: int) -> tuple[str, str, float, str]:
    """Generate one role-separated visual asset with retry-on-technical-fail.

    v0.3.9: no fake best-of-N judging by default. We generate one image, run local
    alpha/crop/fit validation, and retry only when the PNG is technically broken.
    """
    contract_role = "impact" if role.startswith("impact_") else role
    base_prompt = normalize_asset_prompt(data, contract_role, prompt, canvas)
    negative = str(negative or "")
    data.setdefault("debug", {})[f"{role}FinalPrompt"] = truncate_prompt_at_boundary(base_prompt, 1800)
    data.setdefault("debug", {})[f"{role}AuthoringPolicy"] = "ai_primary_non_procedural"
    if IMAGE_BACKEND == "off":
        return "", "", 0.0, "prompt_only"
    config_error = _backend_configuration_error()
    if config_error:
        data.setdefault("debug", {})["imageBackendConfigError"] = config_error
        trace_event("error", f"IMAGE:{role}", "image backend configuration is invalid", {"backend": IMAGE_BACKEND, "error": config_error})
        return "", "", 0.0, "backend_config_error"
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(SPRITE_RETRIES) + 1)
    last_path = ""
    last_raw_path = ""
    last_score = 0.0
    last_validation: dict[str, Any] | None = None
    topology, part_count_min, part_count_max = _authored_sprite_topology(data, role)
    for attempt in range(max_attempts):
        attempt_id = asset_id if attempt == 0 else f"{asset_id}_retry{attempt}"
        attempt_prompt = base_prompt if attempt == 0 else build_retry_prompt_from_validation(base_prompt, last_validation or {}, contract_role, attempt, canvas)
        data.setdefault("debug", {})[f"{role}FinalPrompt"] = attempt_prompt
        data["debug"][f"{role}FinalPromptAttempt"] = attempt
        trace_event("prompt", f"IMAGE:{role}", f"{IMAGE_BACKEND} {role} prompt attempt {attempt}", {
            "assetId": asset_id, "attemptId": attempt_id, "attempt": attempt, "role": role,
            "backend": IMAGE_BACKEND, "canvas": canvas, "spriteRetries": SPRITE_RETRIES,
        }, prompt=attempt_prompt, negative=negative)
        try:
            variants = _generate_backend_variants(
                data,
                prompt=attempt_prompt,
                negative=negative,
                asset_id=attempt_id,
                canvas=canvas,
                role=contract_role,
            )
            variants = [p for p in variants if p and Path(p).exists()]
            if not variants:
                attempts.append({"attempt": attempt, "ok": False, "status": "no_raw_image"})
                continue
            best, score = pick_best_sprite(variants, contract_role, canvas)
            final_path = postprocess_sprite(
                best, attempt_id, canvas, contract_role, topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
            )
            validation = validate_processed_sprite(
                final_path, contract_role, topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
            )
            refit_path = ""
            refit_validation: dict[str, Any] | None = None
            if not validation.get("ok") and not sprite_validation_fatal(validation):
                refit_path = refit_processed_sprite_to_contract(final_path, attempt_id, canvas, contract_role, validation)
                if refit_path:
                    refit_validation = validate_processed_sprite(
                        refit_path, contract_role, topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
                    )
                    if refit_validation.get("ok"):
                        data.setdefault("debug", {})[f"{role}SpriteRefit"] = json.dumps({
                            "from": str(Path(final_path).resolve()),
                            "to": str(Path(refit_path).resolve()),
                            "before": validation,
                            "after": refit_validation,
                        }, ensure_ascii=False)
                        final_path = refit_path
                        validation = refit_validation
            technical_score = technical_validation_score(validation)
            attempt_row = {"attempt": attempt, "raw": best, "final": final_path, "score": technical_score, "candidateScore": round(float(score), 3), "validation": validation}
            if refit_path:
                attempt_row["refit"] = {"path": refit_path, "validation": refit_validation}
            attempts.append(attempt_row)
            last_path = final_path
            last_raw_path = best
            last_score = technical_score
            last_validation = validation if isinstance(validation, dict) else None
            if validation.get("ok") or not sprite_validation_fatal(validation):
                if attempt != 0:
                    canonical = SPRITE_DIR / f"{asset_id}.png"
                    try:
                        import shutil
                        shutil.copyfile(final_path, canonical)
                        final_path = str(canonical)
                    except Exception as exc:
                        data.setdefault("debug", {})[f"{role}SpriteCanonicalCopyError"] = json.dumps({
                            "from": str(final_path),
                            "to": str(canonical),
                            "error": repr(exc),
                        }, ensure_ascii=False)
                data.setdefault("debug", {})[f"{role}SpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
                data["debug"][f"{role}SpriteTechnicalScore"] = round(last_score, 3)
                data["debug"][f"{role}SpriteCandidateScore"] = round(float(score), 3)
                if not validation.get("ok"):
                    data.setdefault("debug", {})[f"{role}SpriteAcceptedWithWarnings"] = json.dumps(validation, ensure_ascii=False)
                status = sprite_status_from_raw_path(best, IMAGE_BACKEND, invalid=not bool(validation.get("ok")))
                trace_event("step", f"IMAGE:{role}", "sprite accepted", {
                    "assetId": asset_id, "attempt": attempt, "raw": best, "final": str(Path(final_path).resolve()),
                    "score": last_score, "candidateScore": round(float(score), 3), "status": status, "validation": validation,
                })
                return str(Path(final_path).resolve()), f"/sprite/{Path(final_path).name}", last_score, status
        except Exception as e:
            attempts.append({"attempt": attempt, "ok": False, "error": repr(e)})
            data.setdefault("debug", {})[f"{role}SpriteError"] = repr(e)
            trace_event("error", f"IMAGE:{role}", "sprite generation attempt failed", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND}, error=repr(e))
            log_event("warn", f"{role} sprite generation attempt failed", {"attempt": attempt, "error": repr(e), "trace": traceback.format_exc()})
    data.setdefault("debug", {})[f"{role}SpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
    if last_path:
        data.setdefault("debug", {})[f"{role}InvalidGeneratedDiscarded"] = str(Path(last_path).resolve())
        # v0.4.49: strict AI authorship should prefer an imperfect AI-authored sprite
        # over an engine placeholder when the failure is only fit/crop strictness.
        # Fatal technical failures (magenta still present, no alpha, empty sprite) stay failed.
        reasons = []
        try:
            reasons = list((last_validation or {}).get("reasons") or [])
        except Exception:
            reasons = []
        fatal = sprite_validation_fatal(last_validation)
        if not fatal and Path(last_path).exists():
            data.setdefault("debug", {})[f"{role}InvalidGeneratedUsedAsWarn"] = json.dumps({
                "path": str(Path(last_path).resolve()),
                "reasons": reasons,
                "policy": "strict_ai_authorship_keep_imperfect_ai_sprite_not_placeholder",
            }, ensure_ascii=False)
            canonical = SPRITE_DIR / f"{asset_id}.png"
            try:
                import shutil
                if Path(last_path).resolve() != canonical.resolve():
                    shutil.copyfile(last_path, canonical)
                last_path = str(canonical)
            except Exception:
                pass
            return str(Path(last_path).resolve()), f"/sprite/{Path(last_path).name}", round(last_score, 3), "generated_warn_invalid"
    if VISUAL_ALLOW_PROCEDURAL_FALLBACK and not VISUAL_STRICT_AI_AUTHORSHIP:
        try:
            fallback = visual_asset_pipeline.generate_procedural_asset(data, role, variant=0, canvas_size=canvas, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)
            final = postprocess_sprite(
                fallback, asset_id, canvas, role, topology=topology, part_count_min=part_count_min, part_count_max=part_count_max
            )
            return str(Path(final).resolve()), f"/sprite/{Path(final).name}", 0.0, "fallback_after_failed_generation"
        except Exception as e:
            log_event("warn", f"{role} sprite procedural fallback failed", {"error": repr(e)})
    trace_event("error", f"IMAGE:{role}", "sprite generation failed completely", {"assetId": asset_id, "role": role, "backend": IMAGE_BACKEND, "attempts": attempts})
    log_event("warn", f"{role} sprite generation failed completely", {"role": role, "backend": IMAGE_BACKEND, "strictAiAuthorship": VISUAL_STRICT_AI_AUTHORSHIP})
    return "", "", round(last_score, 3), "failed"

def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def maybe_generate_visual_assets(data: dict[str, Any]) -> dict[str, Any]:
    """Generate exactly the assets authored for accepted runtime entities.

    The function never invents projectile/impact/child roles.  Every non-item
    image is keyed by a stable runtime entity ID and an explicit Visual Director
    ``assetMode``.
    """
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
            backend_role = "impact_" + entity_id
            path, url, score, status = generate_visual_asset(
                data,
                backend_role,
                prompt,
                negative,
                str(slot.get("assetId") or f"{data.get('id')}_{entity_id}_impact"),
                canvas,
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
        backend_role = "entity_" + entity_id
        path, url, score, status = generate_visual_asset(
            data,
            backend_role,
            prompt,
            director_negative,
            str(slot.get("assetId") or f"{data.get('id')}_{entity_id}"),
            canvas,
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
