"""Image processing orchestration and artifact I/O."""

from __future__ import annotations

import traceback
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None

from infini_local.core.item_identity_tools import safe_file_part
from infini_local.core.config_bootstrap import SPRITE_DIR
from infini_local.services.visual_asset_pipeline import ImageOutputIOError, load_image_input, save_image_output
from infini_local.core.images.config import (
    BG_REMOVE_MODE,
    REMOVE_BG,
    REQUIRE_PILLOW,
    SAVE_SPRITE_STAGES,
    SPRITE_CHROMA_DEFRINGE,
    SPRITE_DOWNSCALE_FILTER,
    SPRITE_MASTER_CANVAS,
    SPRITE_PREMULTIPLIED_RESIZE,
    SPRITE_PROCESSING_PROFILE,
)
from infini_local.storage.trace_runtime import log_event
from infini_local.pipelines.images.geometry import (
    sprite_bbox_stats,
)
from infini_local.pipelines.images import keyer
from infini_local.pipelines.images.keyer import (
    apply_background_removal,
    estimate_sprite_key_profile,
    remove_nested_poster_card_background,
    remove_key_colored_holes,
    scrub_transparent_rgb,
)
from infini_local.core.images.contracts import (
    SPRITE_MIN_TRANSPARENT_PCT,
    final_sprite_canvas,
    sprite_contract_for,
    sprite_uses_soft_alpha,
    uses_key_background,
)


from infini_local.pipelines.images.pixels import (
    bake_sprite_from_master,
    canonicalize_projectile_forward_axis,
    cleanup_alpha,
    defringe_chroma_edges,
    denoise_alpha_singletons,
    prepare_sprite_master,
    resize_rgba_premultiplied,
    sprite_resample_filter,
)
from infini_local.pipelines.images.validation import alpha_stats, edge_touch_ratio, sprite_validation_fatal, validate_processed_sprite


class RawSpriteBackgroundError(ValueError):
    """Provider pixels violate the requested background-removal contract."""


def _exterior_clear_fraction(img: Any) -> float:
    """Real clear pixels connected to the raw frame, not interior cutouts."""
    width, height = img.size
    mask = Image.new("L", (width + 2, height + 2), 0)
    mask.paste(img.getchannel("A").point(lambda alpha: 255 if alpha else 0), (1, 1))
    ImageDraw.floodfill(mask, (0, 0), 1)
    padding = (width + 2) * (height + 2) - width * height
    return (mask.histogram()[1] - padding) / max(1, width * height)


@dataclass(frozen=True)
class PreparedKeyer:
    """One selected candidate's untouched keyer output; never a global cache."""
    source_sha256: str
    source_pixels_sha256: str
    settings: tuple[Any, ...]
    pixels: Any


@dataclass(frozen=True)
class SpriteSelection:
    path: str
    score: float
    prepared: PreparedKeyer | None = None


def _source_sha256(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        # Hashing is reuse admission, not a new reason to reject decoded artwork.
        return None


def _pixels_sha256(image: Any) -> str:
    return hashlib.sha256(str((image.mode, image.size)).encode() + image.tobytes()).hexdigest()


def _keyer_settings(role: str) -> tuple[Any, ...]:
    keyed = uses_key_background()
    return (role, sprite_uses_soft_alpha(role), keyed, keyer.BG_REMOVE_MODE,
            keyer.ALPHA_THRESHOLD, keyer.CHROMA_TOLERANCE,
            keyer.SPRITE_KEYER_RESIDUE_STEPS, keyer.SPRITE_KEYER_SPILL_RADIUS,
            keyer.chroma_rgb() if keyed else None)


def pick_best_sprite(paths: list[str], role: str = "item", canvas: int = 32) -> SpriteSelection:
    if Image is None:
        return SpriteSelection(paths[0], 0.5)
    best = paths[0]
    best_score = -9999.0
    best_prepared = None
    spec = sprite_contract_for(role, canvas)
    target_fill = float(spec["targetFill"])
    for p in paths:
        try:
            source_hash = _source_sha256(p)
            img = load_image_input(p, Image)
            pixels_hash = _pixels_sha256(img)
            settings = _keyer_settings(role)
            keyed = apply_background_removal(img, preserve_alpha=sprite_uses_soft_alpha(role))
            # Candidate scoring has a different cleanup order than final baking.
            # Retain only the common keyer step, before either pipeline mutates it.
            prepared = (PreparedKeyer(source_hash, pixels_hash, settings, keyed)
                        if source_hash is not None and source_hash == _source_sha256(p)
                        and settings == _keyer_settings(role) else None)
            img = cleanup_alpha(keyed.copy(), role)
            if not sprite_uses_soft_alpha(role):
                img = denoise_alpha_singletons(img)
            s = sprite_bbox_stats(img, role, canvas)
            if not s.get("effect_bbox"):
                score = -999.0
            else:
                core_fill = float(s.get("core_fill") or 0.0)
                effect_fill = float(s.get("effect_fill") or 0.0)
                cx, cy = s.get("core_center_norm") or (0.5, 0.5)
                center_penalty = abs(cx - 0.5) + abs(cy - 0.5) if role in {"item", "equip_overlay"} else 0.0
                edge_ratio = edge_touch_ratio(img.getchannel("A"))
                fill_penalty = abs(core_fill - target_fill) * 2.1
                effect_penalty = max(0.0, effect_fill - 0.98) * 1.2
                edge_penalty = max(0.0, edge_ratio - float(spec.get("maxEdgeTouch") or 0.1)) * 3.0
                score = 1.0 - fill_penalty - effect_penalty - center_penalty - edge_penalty
            if score > best_score:
                best_score = score
                best = p
                best_prepared = prepared
        except ImageOutputIOError:
            raise
        except Exception:
            continue
    return SpriteSelection(best, round(max(0.0, min(1.0, best_score)), 3), best_prepared)


def save_stage(img: Any, sprite_id: str, stage: str, *, output_dir: Path | None = None) -> str:
    if not SAVE_SPRITE_STAGES or Image is None:
        return ""
    try:
        p = (output_dir if output_dir is not None else SPRITE_DIR) / f"{safe_file_part(sprite_id, 'sprite')}_stage_{stage}.png"
        save_image_output(img, p)
        return str(p)
    except ImageOutputIOError:
        raise
    except Exception:
        return ""


def _minimal_delivery_bake(source: Any, final_size: int) -> Any:
    """Emergency technical resize of already decoded artwork, never a new design.

    Only a source with real transparency is eligible. Retain the full authored
    frame and aspect ratio (projectile direction and authored offsets included),
    pad transparently, and use the normal premultiplied-alpha final filter.
    The caller still validates the actual PNG before making it public.
    """
    source = source.convert("RGBA")
    if source.width <= 0 or source.height <= 0 or source.getchannel("A").getextrema()[0] >= 255:
        raise ValueError("minimal bake needs decoded artwork with existing transparency")
    scale = min(final_size / source.width, final_size / source.height)
    width = max(1, min(final_size, round(source.width * scale)))
    height = max(1, min(final_size, round(source.height * scale)))
    pixels = resize_rgba_premultiplied(source, (width, height), sprite_resample_filter("final"))
    baked = Image.new("RGBA", (final_size, final_size), (0, 0, 0, 0))
    baked.alpha_composite(pixels, ((final_size - width) // 2, (final_size - height) // 2))
    return scrub_transparent_rgb(baked)


def postprocess_sprite(
    path: str,
    sprite_id: str,
    target_size: int = 32,
    role: str = "unknown",
    *,
    topology: str = "",
    part_count_min: int = 0,
    part_count_max: int = 0,
    output_dir: Path | None = None,
    master_output: Path | None = None,
    prepared: PreparedKeyer | None = None,
) -> str:
    """Process an authored image through the selected technical role contract.

    Recoverable legacy processing errors use a minimal alpha-safe final bake;
    never return raw provider paths. Required VFX ingredients remain strict.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for sprite postprocess/validation")
    target_size = final_sprite_canvas(target_size)
    decoded = False
    background_verified = False
    raw = bg_removed = master = None
    keyed = uses_key_background()
    key_profile = None
    try:
        raw = load_image_input(path, Image)
        decoded = True
        # A canvas fit adds transparent padding. It must not manufacture evidence
        # that a fully opaque provider background satisfied native-alpha delivery.
        # Full-frame UV strips are not fitted/padded; their final alpha gate owns
        # that contract. Chroma transports intentionally start opaque.
        if not uses_key_background() and role != "vfx_strip" and raw.getchannel("A").getextrema()[0] == 255:
            raise RawSpriteBackgroundError(
                "native_alpha_raw_background_opaque: provider must return real transparency, not a painted background"
            )
        save_stage(raw, sprite_id, "00_raw", output_dir=output_dir)

        # Master-first pipeline: all destructive technical work happens before the
        # final downscale.  This does not change semantics; it only removes the
        # requested key background, normalizes the canvas and bakes a clean PNG.
        key_profile = estimate_sprite_key_profile(raw) if keyed else None
        reuse_keyer = (prepared is not None
                       and prepared.source_sha256 == _source_sha256(path)
                       and prepared.source_pixels_sha256 == _pixels_sha256(raw)
                       and prepared.settings == _keyer_settings(role))
        bg_removed = (prepared.pixels.copy() if reuse_keyer
                      else apply_background_removal(raw, preserve_alpha=sprite_uses_soft_alpha(role)))
        # Single supported background-removal protocol: sprite_keyer.  The following
        # steps are technical cleanup only, not an alternate semantic/image mode.
        # Layer 2 removes key-colored pockets that are enclosed by the generated object
        # and therefore unreachable by contiguous border flood-fill.
        if keyed:
            bg_removed = remove_key_colored_holes(bg_removed, key_profile)
        bg_removed = defringe_chroma_edges(bg_removed)
        bg_removed = cleanup_alpha(bg_removed, role)
        # The same clear-background bound as final delivery must be met BEFORE
        # fitting adds transparent padding. Incidental interior key-colored pixels
        # do not establish that an opaque painted matte was removed. Full-frame UV
        # strips are never fitted; their existing final alpha contract remains owner.
        if role != "vfx_strip" and _exterior_clear_fraction(bg_removed) < SPRITE_MIN_TRANSPARENT_PCT:
            raise RawSpriteBackgroundError(
                "raw_background_not_removed: insufficient exterior transparency before canvas fitting; "
                "provider must supply genuine alpha or the requested removable key background"
            )
        background_verified = True
        # Layer 3 removes AI-drawn white/pink poster cards inside the requested key.
        # This keeps retry pressure low and prevents opaque square sprites from reaching the game.
        if keyed and role in {"item", "equip_overlay"}:
            bg_removed = remove_nested_poster_card_background(bg_removed, role)
        bg_removed = cleanup_alpha(bg_removed, role)
        if role in {"item", "equip_overlay"}:
            bg_removed = denoise_alpha_singletons(bg_removed)
        bg_removed = scrub_transparent_rgb(bg_removed)
        save_stage(bg_removed, sprite_id, "10_sprite_keyer_fullres", output_dir=output_dir)
        if role == "vfx_strip":
            # Full-frame UVs are authored data. Only key/alpha cleanup and uniform
            # full-frame resize are allowed; never crop, rotate, center or refit.
            forward_axis = {"rotated": False, "flipped": False}
            master = bg_removed
        else:
            bg_removed, forward_axis = canonicalize_projectile_forward_axis(bg_removed, role)
            if forward_axis.get("rotated") or forward_axis.get("flipped"):
                save_stage(bg_removed, sprite_id, "15_projectile_forward_axis", output_dir=output_dir)
            master = prepare_sprite_master(bg_removed, sprite_id, target_size, role)
        if key_profile is not None:
            master.info["infini.chroma-key"] = json.dumps({"schema": "infini.sampled-chroma-key.v1", **key_profile}, sort_keys=True)
        save_stage(master, sprite_id, "20_master_norm", output_dir=output_dir)
        if master_output is not None:
            save_image_output(master, master_output)
        final = bake_sprite_from_master(master, target_size, role)
        if key_profile is not None:
            final.info["infini.chroma-key"] = json.dumps({"schema": "infini.sampled-chroma-key.v1", **key_profile}, sort_keys=True)
        save_stage(final, sprite_id, "30_baked_final", output_dir=output_dir)

        out = (output_dir if output_dir is not None else SPRITE_DIR) / f"{safe_file_part(sprite_id, 'sprite')}.png"
        save_image_output(final, out)
        stats = alpha_stats(final)
        validation = validate_processed_sprite(
            str(out),
            role,
            topology=topology,
            part_count_min=part_count_min,
            part_count_max=part_count_max,
        )
        log_event(
            "info",
            "sprite postprocessed",
            {
                "spriteId": sprite_id,
                "source": str(path),
                "out": str(out),
                "targetSize": target_size,
                "removeBg": REMOVE_BG,
                "processingProfile": SPRITE_PROCESSING_PROFILE,
                "masterCanvas": SPRITE_MASTER_CANVAS,
                "downscaleFilter": SPRITE_DOWNSCALE_FILTER,
                "premultipliedResize": SPRITE_PREMULTIPLIED_RESIZE,
                "chromaDefringe": SPRITE_CHROMA_DEFRINGE,
                "requirePillow": REQUIRE_PILLOW,
                "pillowAvailable": Image is not None,
                "bgMode": BG_REMOVE_MODE,
                "alpha": stats,
                "projectileForwardAxis": forward_axis,
                "validation": validation,
            },
        )
        return str(out)
    except (ImageOutputIOError, RawSpriteBackgroundError):
        raise
    except Exception as e:
        if decoded and isinstance(e, OSError):
            raise ImageOutputIOError("sprite processing filesystem operation failed") from e
        log_event("warn", "postprocess failed", {"path": path, "error": repr(e), "trace": traceback.format_exc()})
        if role in {"vfx_cutout", "vfx_strip"}:
            raise RuntimeError("required VFX ingredient postprocess failed") from e

        # For ordinary item/entity/overlay/impact PNGs, rescue the latest usable
        # pixel stage rather than publishing the full-size provider source or
        # paying for a new image model attempt after one technical failure.
        # A failed keyer cannot silently publish an opaque raw background.
        stage = "master" if master is not None else "alpha" if bg_removed is not None else "raw"
        candidate = master if master is not None else bg_removed if bg_removed is not None else raw
        # A recoverable processing exception can occur before the normal guard.
        # Rescue must not use fitting/padding to manufacture exterior alpha.
        if (candidate is not None and decoded and not background_verified
                and _exterior_clear_fraction(candidate) < SPRITE_MIN_TRANSPARENT_PCT):
            raise RawSpriteBackgroundError(
                "raw_background_not_removed: insufficient exterior transparency before rescue fitting"
            ) from e
        try:
            if candidate is None or not decoded:
                raise ValueError("no decoded sprite available to recover")
            recovered = _minimal_delivery_bake(candidate, target_size)
            if keyed and key_profile is not None:
                recovered.info["infini.chroma-key"] = json.dumps({"schema": "infini.sampled-chroma-key.v1", **key_profile}, sort_keys=True)
            out = (output_dir if output_dir is not None else SPRITE_DIR) / f"{safe_file_part(sprite_id, 'sprite')}.png"
            save_image_output(recovered, out)
            validation = validate_processed_sprite(
                str(out),
                role,
                expected_canvas=target_size,
                topology=topology,
                part_count_min=part_count_min,
                part_count_max=part_count_max,
            )
            if sprite_validation_fatal(validation):
                raise ValueError(f"minimal bake does not meet sprite contract: {validation.get('reasons')}")
            log_event(
                "warn",
                "sprite recovered by minimal final downscale",
                {
                    "spriteId": sprite_id,
                    "sourceStage": stage,
                    "targetSize": target_size,
                    "out": str(out),
                    "originalError": repr(e),
                    "validation": validation,
                },
            )
            return str(out)
        except ImageOutputIOError:
            raise
        except OSError as io_error:
            raise ImageOutputIOError("minimal sprite bake filesystem operation failed") from io_error
        except Exception as recovery_error:
            log_event(
                "warn",
                "minimal sprite downscale unavailable",
                {
                    "spriteId": sprite_id,
                    "sourceStage": stage,
                    "originalError": repr(e),
                    "recoveryError": repr(recovery_error),
                },
            )
            raise RuntimeError("sprite postprocess could not produce a usable final PNG") from recovery_error
