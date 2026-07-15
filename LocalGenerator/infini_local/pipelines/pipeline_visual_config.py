from __future__ import annotations

from typing import Any

import os
from pathlib import Path

from infini_local.core.config_bootstrap import APP_VERSION, CACHE_DIR, RECIPE_IDENTITY_VERSION
from infini_local.core.contract_versions import build_contract_versions
from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING as _LLM_RUNTIME_AUTHORING_DEFAULT
from infini_local.services import sdcpp_backend, sdcpp_service
from infini_local.storage.trace_runtime import log_event

# AGENT MAP: canonical visual/image backend env/config and lifecycle state.
# Consumers import this owner directly. No gameplay/runtime authoring logic belongs here.

IMAGE_BACKEND_ALIASES = {
    "stablediffusioncpp": "sdcpp",
    "stable-diffusion.cpp": "sdcpp",
    "stable_diffusion_cpp": "sdcpp",
    "api_image": "image_api",
    "openai_image": "image_api",
    "openai_images": "image_api",
    "openai_compat_image": "image_api",
    "none": "off",
    "disabled": "off",
}
SUPPORTED_IMAGE_BACKENDS = frozenset({"off", "sdcpp", "a1111", "comfyui", "image_api", "procedural"})
IMAGE_BACKEND_RAW = env_str("INFINI_IMAGE_BACKEND", "sdcpp").strip().lower()
IMAGE_BACKEND = IMAGE_BACKEND_ALIASES.get(IMAGE_BACKEND_RAW, IMAGE_BACKEND_RAW)
IMAGE_BACKEND_CONFIG_ERROR = "" if IMAGE_BACKEND in SUPPORTED_IMAGE_BACKENDS else f"unsupported image backend: {IMAGE_BACKEND_RAW or '<empty>'}"
A1111_URL = env_str("INFINI_A1111_URL", "http://127.0.0.1:7860").rstrip("/")
COMFYUI_URL = env_str("INFINI_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
# stable-diffusion.cpp backend. v0.4.19 removes per-image CLI generation entirely.
# Only persistent sd-server/http mode is supported for gameplay. The model must stay hot in memory.
SDCPP_MODEL = env_first(("INFINI_SDCPP_MODEL", "SDCPP_MODEL"), "")
# Z-Image needs separate text encoder/LLM and VAE/AE files in stable-diffusion.cpp.
# Keep them as dedicated fields so users do not have to hand-type fragile extra args.
SDCPP_VAE = env_str("INFINI_SDCPP_VAE", "")
SDCPP_LLM = env_str("INFINI_SDCPP_LLM", "")
SDCPP_LORA_DIR = env_str("INFINI_SDCPP_LORA_DIR", "")
SDCPP_LORA_FILE = env_str("INFINI_SDCPP_LORA_FILE", "")
SDCPP_LORA_WEIGHT = env_str("INFINI_SDCPP_LORA_WEIGHT", "0.25") or "0.25"
SDCPP_LORA_PROMPT_TAGS = env_str("INFINI_SDCPP_LORA_PROMPT_TAGS", "")
if SDCPP_LORA_FILE:
    _lora_path = Path(SDCPP_LORA_FILE)
    # A concrete LoRA file should drive the directory passed to sd.cpp. This avoids
    # stale GUI defaults such as C:\Games\sdcpp\loras pointing at the wrong folder.
    _file_lora_dir = sdcpp_backend.lora_dir_from_file(SDCPP_LORA_FILE)
    if _file_lora_dir:
        SDCPP_LORA_DIR = _file_lora_dir
    if not SDCPP_LORA_PROMPT_TAGS and _lora_path.stem:
        SDCPP_LORA_PROMPT_TAGS = sdcpp_backend.lora_tag_from_file(SDCPP_LORA_FILE, SDCPP_LORA_WEIGHT)
SDCPP_WIDTH = env_int("INFINI_SDCPP_WIDTH", 512, lo=64, hi=2048)
SDCPP_HEIGHT = env_int("INFINI_SDCPP_HEIGHT", SDCPP_WIDTH, lo=64, hi=2048)
SDCPP_STEPS = env_int("INFINI_SDCPP_STEPS", 8, lo=1, hi=150)
SDCPP_CFG = env_float("INFINI_SDCPP_CFG", 1.0, lo=0.0, hi=30.0)
SDCPP_SAMPLER = env_str("INFINI_SDCPP_SAMPLER", "euler")
SDCPP_SEED = env_int("INFINI_SDCPP_SEED", -1)
ZIMAGE_PROMPT_CONTRACT = env_str("INFINI_ZIMAGE_PROMPT_CONTRACT", "auto").lower()  # auto, 1, 0
ZIMAGE_POSITIVE_ONLY = env_bool("INFINI_ZIMAGE_POSITIVE_ONLY", True)
SDCPP_SERVER_URL = env_str("INFINI_SDCPP_SERVER_URL", "http://127.0.0.1:7861").rstrip("/")
SDCPP_SERVER_HOST = env_str("INFINI_SDCPP_SERVER_HOST", "127.0.0.1")
SDCPP_SERVER_PORT = env_int("INFINI_SDCPP_SERVER_PORT", 7861, lo=1, hi=65535)
SDCPP_SERVER_AUTOSTART = env_bool("INFINI_SDCPP_SERVER_AUTOSTART", False)
SDCPP_SERVER_EXE = env_str("INFINI_SDCPP_SERVER_EXE", "")
SDCPP_ROCM_COMPAT_ROOT = env_str("INFINI_SDCPP_ROCM_COMPAT_ROOT", "")
SDCPP_DEFAULT_COMMAND_TEMPLATE = "{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-method {sampler} {extra}"
SDCPP_SERVER_COMMAND_MODE = env_str("INFINI_SDCPP_SERVER_COMMAND_MODE", "safe_args").lower()  # safe_args, template
SDCPP_SERVER_COMMAND_TEMPLATE = env_str("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", "")
SDCPP_SERVER_EXTRA_ARGS = env_str("INFINI_SDCPP_SERVER_EXTRA_ARGS", "")
SDCPP_MODE = "server"
SDCPP_TIMEOUT = env_int("INFINI_SDCPP_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
SDCPP_SERVER_HEALTH_PATHS = [x.strip() for x in env_str("INFINI_SDCPP_SERVER_HEALTH_PATHS", "/,/health,/sdapi/v1/sd-models").split(",") if x.strip()]
SDCPP_SERVER_TXT2IMG_PATHS = [x.strip() for x in env_str("INFINI_SDCPP_SERVER_TXT2IMG_PATHS", "/sdapi/v1/txt2img,/txt2img,/generate").split(",") if x.strip()]
SDCPP_SERVER_PAYLOAD_STYLE = env_str("INFINI_SDCPP_SERVER_PAYLOAD_STYLE", "auto").lower()  # auto, a1111, sdcpp, openai
SDCPP_SERVER_STARTUP_TIMEOUT = env_int("INFINI_SDCPP_SERVER_STARTUP_TIMEOUT", 180)
SDCPP_SERVER_REQUEST_TIMEOUT = env_int("INFINI_SDCPP_SERVER_REQUEST_TIMEOUT", SDCPP_TIMEOUT, lo=1, hi=3600)
# v0.4.49: do not hide sd-server output behind PIPE. Z-Image startup bugs need visible logs,
# and verbose sd.cpp output can otherwise fill the pipe and stall the child process.
SDCPP_SERVER_SHOW_CONSOLE = env_bool("INFINI_SDCPP_SERVER_SHOW_CONSOLE", os.name == "nt")
SDCPP_SERVER_LOG_FILE = env_str("INFINI_SDCPP_SERVER_LOG_FILE", str(CACHE_DIR / "sdcpp_server.log"))
SDCPP_SERVER_STATE = sdcpp_service.SdcppServerState()
def _sdcpp_config() -> sdcpp_backend.SdcppBackendConfig:
    return sdcpp_backend.SdcppBackendConfig(
        default_command_template=SDCPP_DEFAULT_COMMAND_TEMPLATE,
        command_mode=SDCPP_SERVER_COMMAND_MODE,
        server_exe=SDCPP_SERVER_EXE,
        model=SDCPP_MODEL,
        vae=SDCPP_VAE,
        llm=SDCPP_LLM,
        lora_dir=SDCPP_LORA_DIR,
        lora_prompt_tags=SDCPP_LORA_PROMPT_TAGS,
        host=SDCPP_SERVER_HOST,
        port=SDCPP_SERVER_PORT,
        width=SDCPP_WIDTH,
        height=SDCPP_HEIGHT,
        steps=SDCPP_STEPS,
        cfg=SDCPP_CFG,
        sampler=SDCPP_SAMPLER,
        extra_args=SDCPP_SERVER_EXTRA_ARGS,
        server_url=SDCPP_SERVER_URL,
        health_paths=SDCPP_SERVER_HEALTH_PATHS,
        zimage_prompt_contract=ZIMAGE_PROMPT_CONTRACT,
        zimage_positive_only=ZIMAGE_POSITIVE_ONLY,
        rocm_compat_root=SDCPP_ROCM_COMPAT_ROOT,
    )


def cleanup_sdcpp_server_process(reason: str = "cleanup") -> None:
    sdcpp_service.cleanup_server_process(SDCPP_SERVER_STATE, log_event, reason)


COMFYUI_WORKFLOW = env_str("INFINI_COMFYUI_WORKFLOW", "auto")
COMFYUI_WORKFLOW_LORA = env_str("INFINI_COMFYUI_WORKFLOW_LORA", "")
COMFYUI_WORKFLOW_NO_LORA = env_str("INFINI_COMFYUI_WORKFLOW_NO_LORA", "")
COMFYUI_CHECKPOINT = env_str("INFINI_COMFYUI_CHECKPOINT", "")
COMFYUI_LORA_NAME = env_first(("INFINI_COMFYUI_LORA_NAME", "INFINI_PIXEL_LORA_NAME"), "")
COMFYUI_LORA_WEIGHT = env_first(("INFINI_COMFYUI_LORA_WEIGHT", "INFINI_PIXEL_LORA_WEIGHT"), "0.8")
COMFYUI_TRIGGER = env_first(("INFINI_COMFYUI_TRIGGER", "INFINI_PIXEL_TRIGGER"), "")
COMFYUI_WIDTH = env_int("INFINI_COMFYUI_WIDTH", 512)
COMFYUI_HEIGHT = env_int("INFINI_COMFYUI_HEIGHT", COMFYUI_WIDTH, lo=64, hi=2048)
COMFYUI_STEPS = env_int("INFINI_COMFYUI_STEPS", 16)
COMFYUI_CFG = env_float("INFINI_COMFYUI_CFG", 5.5)
COMFYUI_SAMPLER = env_str("INFINI_COMFYUI_SAMPLER", "euler")
COMFYUI_SCHEDULER = env_str("INFINI_COMFYUI_SCHEDULER", "normal")
COMFYUI_DENOISE = env_float("INFINI_COMFYUI_DENOISE", 1.0)
COMFYUI_TIMEOUT = env_int("INFINI_COMFYUI_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
COMFYUI_POLL_INTERVAL = env_float("INFINI_COMFYUI_POLL_INTERVAL", 0.75)
COMFYUI_CLIENT_ID = env_str("INFINI_COMFYUI_CLIENT_ID", "infinicrafterlocal")
IMAGE_API_BASE_URL = env_first(("INFINI_IMAGE_API_BASE_URL", "INFINI_OPENAI_COMPAT_IMAGE_BASE_URL"), "https://api.openai.com/v1").rstrip("/")
IMAGE_API_KEY = env_first(("INFINI_IMAGE_API_KEY", "INFINI_OPENAI_COMPAT_IMAGE_API_KEY", "OPENAI_API_KEY"), "")
IMAGE_API_MODEL = env_first(("INFINI_IMAGE_API_MODEL", "INFINI_OPENAI_COMPAT_IMAGE_MODEL"), "gpt-image-1")
IMAGE_API_PATH = env_str("INFINI_IMAGE_API_PATH", "/images/generations")
IMAGE_API_SIZE = env_first(("INFINI_IMAGE_API_SIZE", "INFINI_OPENAI_COMPAT_IMAGE_SIZE"), "512x512")
IMAGE_API_TIMEOUT = env_int("INFINI_IMAGE_API_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
IMAGE_API_EXTRA_HEADERS_JSON = env_str("INFINI_IMAGE_API_EXTRA_HEADERS_JSON", "")
GENERATE_VARIANTS = env_int("INFINI_IMAGE_VARIANTS", 1)
# Visual asset generation mode. "item" = inventory icon only; "full" = item + projectile + impact briefs.
VISUAL_ASSET_MODE = env_str("INFINI_VISUAL_ASSET_MODE", "full").lower()
VISUAL_GENERATE_CHILD_FIELD_IMAGES = env_bool("INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES", False)
VISUAL_GENERATE_IMPACT_IMAGES = env_bool("INFINI_VISUAL_GENERATE_IMPACT_IMAGES", False)
VISUAL_GENERATE_PROJECTILE_IMAGES = env_bool("INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES", True)
# v0.3.15: light pattern library. Do not dump long VFX docs into Gemma.
# The planner sees only a few retrieved pattern cards, and missing/invalid attackPattern
# is repaired by the same LLM in a tiny second call instead of deterministic guessing.
PATTERN_LIBRARY_CARDS = env_int("INFINI_PATTERN_LIBRARY_CARDS", 4)
PATTERN_REPAIR_ATTEMPTS = env_int("INFINI_PATTERN_REPAIR_ATTEMPTS", 0 if _LLM_RUNTIME_AUTHORING_DEFAULT else 2, lo=0, hi=8)
PATTERN_REPAIR_TIMEOUT = env_int("INFINI_PATTERN_REPAIR_TIMEOUT", 20)
# v0.3.9: merged author-first visual pipeline. Planner writes the toy, visual-director
# builds a role-separated asset pack, generator produces item/projectile/impact/child/field PNGs.
VISUAL_DIRECTOR_LLM = env_bool("INFINI_VISUAL_DIRECTOR_LLM", True)
VISUAL_PIPELINE_PROFILE = env_str("INFINI_VISUAL_PIPELINE_PROFILE", "author_visualpack_v2")


def contract_versions_payload() -> dict[str, Any]:
    return build_contract_versions(
        app_version=APP_VERSION,
        recipe_identity_version=RECIPE_IDENTITY_VERSION,
        runtime_api_version=ENGINE_RUNTIME_API_VERSION,
        visual_pipeline_profile=VISUAL_PIPELINE_PROFILE,
    )
VISUAL_GENERATION_TIMEOUT = env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240)
PROJECTILE_SPRITE_CANVAS = env_int("INFINI_PROJECTILE_SPRITE_CANVAS", 32)
IMPACT_SPRITE_CANVAS = env_int("INFINI_IMPACT_SPRITE_CANVAS", 32)
CHILD_SPRITE_CANVAS = env_int("INFINI_CHILD_SPRITE_CANVAS", 24)
FIELD_SPRITE_CANVAS = env_int("INFINI_FIELD_SPRITE_CANVAS", 32)
# VFX manifest pipeline constants/functions are imported from vfx_manifest.py after config.env is loaded.
# v0.3.9 one-shot sprite alpha pipeline. Default path:
# 1 generated image per asset -> local alpha removal -> crop/fit/downscale ->
# technical validation -> retry only if PNG is technically broken.
# No VLM judge and no fake best-of-N selection by default.
REMOVE_BG = env_bool("INFINI_REMOVE_BG", True)
BG_REMOVE_MODE = env_str("INFINI_BG_REMOVE_MODE", "sprite_keyer").lower()  # primary supported mode: sprite_keyer
BG_COLOR = env_str("INFINI_BG_COLOR", "magenta").lower()
# v0.4.19: visual generation depends on local alpha/crop/validation; raw SD PNGs are not valid Terraria sprites.
REQUIRE_PILLOW = env_bool("INFINI_REQUIRE_PILLOW", True)
CHROMA_TOLERANCE = env_int("INFINI_CHROMA_TOLERANCE", 34)
ALPHA_THRESHOLD = env_int("INFINI_ALPHA_THRESHOLD", 28)
SPRITE_KEYER_SPILL_RADIUS = env_int("INFINI_SPRITE_KEYER_SPILL_RADIUS", 3)
SPRITE_KEYER_RESIDUE_STEPS = env_int("INFINI_SPRITE_KEYER_RESIDUE_STEPS", 8)
SPRITE_PADDING = env_int("INFINI_SPRITE_PADDING", 2)
SAVE_SPRITE_STAGES = env_bool("INFINI_SAVE_SPRITE_STAGES", False)
PIXEL_POSTERIZE = env_bool("INFINI_PIXEL_POSTERIZE", True)
MAX_COLORS = env_int("INFINI_MAX_COLORS", 32)
# v0.4.55 master-first sprite pipeline.  AI still authors the art; code only performs
# technical image processing: full-res key removal, premultiplied resize, canvas fit,
# palette bake.
SPRITE_PROCESSING_PROFILE = "master_soft"
SPRITE_MASTER_CANVAS = env_int("INFINI_SPRITE_MASTER_CANVAS", 256, lo=64, hi=2048)
_sprite_downscale_filter = env_str("INFINI_SPRITE_DOWNSCALE_FILTER", "box").lower()
SPRITE_DOWNSCALE_FILTER = _sprite_downscale_filter if _sprite_downscale_filter in {"box", "bilinear", "bicubic", "lanczos"} else "box"
SPRITE_CHROMA_DEFRINGE = env_bool("INFINI_SPRITE_CHROMA_DEFRINGE", True)
SPRITE_PREMULTIPLIED_RESIZE = env_bool("INFINI_SPRITE_PREMULTIPLIED_RESIZE", True)
DENOISE_STRAY_PIXELS = env_bool("INFINI_DENOISE_STRAY_PIXELS", False)
SPRITE_RETRIES = env_int("INFINI_SPRITE_RETRIES", 2, lo=0, hi=8)
SPRITE_MIN_BBOX_RATIO = env_float("INFINI_SPRITE_MIN_BBOX_RATIO", 0.10)
SPRITE_MAX_BBOX_RATIO = env_float("INFINI_SPRITE_MAX_BBOX_RATIO", 0.92)
SPRITE_ITEM_CORE_ALPHA_THRESHOLD = env_int("INFINI_SPRITE_ITEM_CORE_ALPHA_THRESHOLD", 56)
SPRITE_EFFECT_CORE_ALPHA_THRESHOLD = env_int("INFINI_SPRITE_EFFECT_CORE_ALPHA_THRESHOLD", 40)
ITEM_ICON_TARGET_FILL = env_float("INFINI_ITEM_ICON_TARGET_FILL", 0.91)
PROJECTILE_ICON_TARGET_FILL = env_float("INFINI_PROJECTILE_ICON_TARGET_FILL", 0.84)
IMPACT_ICON_TARGET_FILL = env_float("INFINI_IMPACT_ICON_TARGET_FILL", 0.82)
CHILD_ICON_TARGET_FILL = env_float("INFINI_CHILD_ICON_TARGET_FILL", 0.72)
FIELD_ICON_TARGET_FILL = env_float("INFINI_FIELD_ICON_TARGET_FILL", 0.86)
VISUAL_STRICT_AI_AUTHORSHIP = env_bool("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", True)
VISUAL_ALLOW_PROCEDURAL_FALLBACK = env_bool("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", False)
# Core-loop guard: a freshly generated recipe must not be delivered with a dead/missing item sprite.
# InfiniCrafter's point is authored gameplay + generated visual asset, not a JSON item with a placeholder.
VISUAL_REQUIRE_ITEM_SPRITE = env_bool("INFINI_VISUAL_REQUIRE_ITEM_SPRITE", True)
# Optional hard mode for setups that should only craft through Z-Image/sd.cpp. Keep opt-in so tests and
# non-Z-image development backends can still run deliberately.
VISUAL_REQUIRE_ZIMAGE_BACKEND = env_bool("INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
SPRITE_MIN_OPAQUE_PCT = env_float("INFINI_SPRITE_MIN_OPAQUE_PCT", 0.015)
SPRITE_MAX_OPAQUE_PCT = env_float("INFINI_SPRITE_MAX_OPAQUE_PCT", 0.82)
SPRITE_MAX_EDGE_TOUCH_PCT = env_float("INFINI_SPRITE_MAX_EDGE_TOUCH_PCT", 0.12)
A1111_LORA_NAME = env_str("INFINI_A1111_LORA_NAME", "")
A1111_LORA_WEIGHT = env_str("INFINI_A1111_LORA_WEIGHT", "0.8")
A1111_TRIGGER = env_str("INFINI_A1111_TRIGGER", "")
A1111_WIDTH = env_int("INFINI_A1111_WIDTH", 512, lo=64, hi=2048)
A1111_HEIGHT = env_int("INFINI_A1111_HEIGHT", A1111_WIDTH, lo=64, hi=2048)
A1111_BATCH_SIZE = env_int("INFINI_A1111_BATCH_SIZE", 1, lo=1, hi=16)


__all__ = [
    "IMAGE_BACKEND_RAW",
    "IMAGE_BACKEND",
    "IMAGE_BACKEND_CONFIG_ERROR",
    "SUPPORTED_IMAGE_BACKENDS",
    "A1111_URL",
    "COMFYUI_URL",
    "SDCPP_MODEL",
    "SDCPP_VAE",
    "SDCPP_LLM",
    "SDCPP_LORA_DIR",
    "SDCPP_LORA_FILE",
    "SDCPP_LORA_WEIGHT",
    "SDCPP_LORA_PROMPT_TAGS",
    "SDCPP_WIDTH",
    "SDCPP_HEIGHT",
    "SDCPP_STEPS",
    "SDCPP_CFG",
    "SDCPP_SAMPLER",
    "SDCPP_SEED",
    "ZIMAGE_PROMPT_CONTRACT",
    "ZIMAGE_POSITIVE_ONLY",
    "SDCPP_SERVER_URL",
    "SDCPP_SERVER_HOST",
    "SDCPP_SERVER_PORT",
    "SDCPP_SERVER_AUTOSTART",
    "SDCPP_SERVER_EXE",
    "SDCPP_DEFAULT_COMMAND_TEMPLATE",
    "SDCPP_SERVER_COMMAND_MODE",
    "SDCPP_SERVER_COMMAND_TEMPLATE",
    "SDCPP_SERVER_EXTRA_ARGS",
    "SDCPP_MODE",
    "SDCPP_TIMEOUT",
    "SDCPP_SERVER_HEALTH_PATHS",
    "SDCPP_SERVER_TXT2IMG_PATHS",
    "SDCPP_SERVER_PAYLOAD_STYLE",
    "SDCPP_SERVER_STARTUP_TIMEOUT",
    "SDCPP_SERVER_REQUEST_TIMEOUT",
    "SDCPP_SERVER_SHOW_CONSOLE",
    "SDCPP_SERVER_LOG_FILE",
    "SDCPP_SERVER_STATE",
    "_sdcpp_config",
    "cleanup_sdcpp_server_process",
    "COMFYUI_WORKFLOW",
    "COMFYUI_WORKFLOW_LORA",
    "COMFYUI_WORKFLOW_NO_LORA",
    "COMFYUI_CHECKPOINT",
    "COMFYUI_LORA_NAME",
    "COMFYUI_LORA_WEIGHT",
    "COMFYUI_TRIGGER",
    "COMFYUI_WIDTH",
    "COMFYUI_HEIGHT",
    "COMFYUI_STEPS",
    "COMFYUI_CFG",
    "COMFYUI_SAMPLER",
    "COMFYUI_SCHEDULER",
    "COMFYUI_DENOISE",
    "COMFYUI_TIMEOUT",
    "COMFYUI_POLL_INTERVAL",
    "COMFYUI_CLIENT_ID",
    "IMAGE_API_BASE_URL",
    "IMAGE_API_KEY",
    "IMAGE_API_MODEL",
    "IMAGE_API_PATH",
    "IMAGE_API_SIZE",
    "IMAGE_API_TIMEOUT",
    "IMAGE_API_EXTRA_HEADERS_JSON",
    "GENERATE_VARIANTS",
    "VISUAL_ASSET_MODE",
    "VISUAL_GENERATE_CHILD_FIELD_IMAGES",
    "VISUAL_GENERATE_IMPACT_IMAGES",
    "VISUAL_GENERATE_PROJECTILE_IMAGES",
    "PATTERN_LIBRARY_CARDS",
    "PATTERN_REPAIR_ATTEMPTS",
    "PATTERN_REPAIR_TIMEOUT",
    "VISUAL_DIRECTOR_LLM",
    "VISUAL_PIPELINE_PROFILE",
    "contract_versions_payload",
    "VISUAL_GENERATION_TIMEOUT",
    "PROJECTILE_SPRITE_CANVAS",
    "IMPACT_SPRITE_CANVAS",
    "CHILD_SPRITE_CANVAS",
    "FIELD_SPRITE_CANVAS",
    "REMOVE_BG",
    "BG_REMOVE_MODE",
    "BG_COLOR",
    "REQUIRE_PILLOW",
    "CHROMA_TOLERANCE",
    "ALPHA_THRESHOLD",
    "SPRITE_KEYER_SPILL_RADIUS",
    "SPRITE_KEYER_RESIDUE_STEPS",
    "SPRITE_PADDING",
    "SAVE_SPRITE_STAGES",
    "PIXEL_POSTERIZE",
    "MAX_COLORS",
    "SPRITE_PROCESSING_PROFILE",
    "SPRITE_MASTER_CANVAS",
    "SPRITE_DOWNSCALE_FILTER",
    "SPRITE_CHROMA_DEFRINGE",
    "SPRITE_PREMULTIPLIED_RESIZE",
    "DENOISE_STRAY_PIXELS",
    "SPRITE_RETRIES",
    "SPRITE_MIN_BBOX_RATIO",
    "SPRITE_MAX_BBOX_RATIO",
    "SPRITE_ITEM_CORE_ALPHA_THRESHOLD",
    "SPRITE_EFFECT_CORE_ALPHA_THRESHOLD",
    "ITEM_ICON_TARGET_FILL",
    "PROJECTILE_ICON_TARGET_FILL",
    "IMPACT_ICON_TARGET_FILL",
    "CHILD_ICON_TARGET_FILL",
    "FIELD_ICON_TARGET_FILL",
    "VISUAL_STRICT_AI_AUTHORSHIP",
    "VISUAL_ALLOW_PROCEDURAL_FALLBACK",
    "VISUAL_REQUIRE_ITEM_SPRITE",
    "VISUAL_REQUIRE_ZIMAGE_BACKEND",
    "SPRITE_MIN_OPAQUE_PCT",
    "SPRITE_MAX_OPAQUE_PCT",
    "SPRITE_MAX_EDGE_TOUCH_PCT",
    "A1111_LORA_NAME",
    "A1111_LORA_WEIGHT",
    "A1111_TRIGGER",
    "A1111_WIDTH",
    "A1111_HEIGHT",
    "A1111_BATCH_SIZE",
]
