from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import random
import re
import shlex
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first, env_path
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode


def http_binary_get(url: str, timeout: int = 30) -> bytes:
    req = urlrequest.Request(url, headers={"Accept": "image/png,*/*"}, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def json_deep_replace(obj: Any, mapping: dict[str, Any]) -> Any:
    """Replace {{PLACEHOLDER}} tokens in a ComfyUI workflow while preserving numeric types.
    If a string is exactly one placeholder, return the mapped value as-is. Otherwise,
    replace placeholders inside the string with their string form.
    """
    if isinstance(obj, dict):
        return {k: json_deep_replace(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_deep_replace(v, mapping) for v in obj]
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped in mapping:
            return mapping[stripped]
        out = obj
        for key, value in mapping.items():
            out = out.replace(key, str(value))
        return out
    return obj

def resolve_comfyui_workflow_path() -> Path | None:
    """Pick a ComfyUI workflow template.
    - explicit INFINI_COMFYUI_WORKFLOW path wins;
    - auto selects LoRA template when a LoRA name is configured, otherwise no-LoRA template.
    """
    candidates: list[str] = []
    explicit = (COMFYUI_WORKFLOW or "auto").strip()
    if explicit and explicit.lower() not in {"auto", "default"}:
        candidates.append(explicit)
    if COMFYUI_LORA_NAME:
        if COMFYUI_WORKFLOW_LORA:
            candidates.append(COMFYUI_WORKFLOW_LORA)
        candidates.append(str(ROOT / "workflows" / "SD15_Pixel_RGBA_LowVRAM_LoRA.json"))
    else:
        if COMFYUI_WORKFLOW_NO_LORA:
            candidates.append(COMFYUI_WORKFLOW_NO_LORA)
        candidates.append(str(ROOT / "workflows" / "SD15_Pixel_RGBA_LowVRAM_NoLoRA.json"))
    candidates.append(str(ROOT / "workflows" / "SD15_Pixel_RGBA_LowVRAM_NoLoRA.json"))
    for c in candidates:
        p = Path(c)
        if not p.is_absolute():
            p = ROOT / p
        if p.exists():
            return p
    return None

def comfyui_mapping(prompt: str, negative: str, sprite_id: str, seed: int | None = None) -> dict[str, Any]:
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    pos = str(prompt or "")
    if COMFYUI_TRIGGER and COMFYUI_TRIGGER not in pos:
        pos = (COMFYUI_TRIGGER + ", " + pos).strip(", ")
    return {
        "{{PROMPT}}": pos,
        "{{NEGATIVE_PROMPT}}": negative or asset_negative_prompt("item"),
        "{{SPRITE_ID}}": safe_file_part(sprite_id, "sprite", 96),
        "{{WIDTH}}": int(COMFYUI_WIDTH),
        "{{HEIGHT}}": int(COMFYUI_HEIGHT),
        "{{STEPS}}": int(COMFYUI_STEPS),
        "{{CFG}}": float(COMFYUI_CFG),
        "{{SAMPLER}}": COMFYUI_SAMPLER,
        "{{SCHEDULER}}": COMFYUI_SCHEDULER,
        "{{DENOISE}}": float(COMFYUI_DENOISE),
        "{{SEED}}": int(seed),
        "{{CHECKPOINT}}": COMFYUI_CHECKPOINT or "model.safetensors",
        "{{LORA_NAME}}": COMFYUI_LORA_NAME or "pixel_lora.safetensors",
        "{{LORA_WEIGHT}}": float(COMFYUI_LORA_WEIGHT or 0.8),
    }

def poll_comfyui_history(prompt_id: str, timeout: int | None = None) -> dict[str, Any]:
    timeout = int(timeout or COMFYUI_TIMEOUT)
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            hist = http_get_json(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            if isinstance(hist, dict):
                last = hist
                entry = hist.get(prompt_id) if prompt_id in hist else hist
                outputs = entry.get("outputs") if isinstance(entry, dict) else None
                if outputs:
                    return hist
        except Exception as e:
            last = {"error": repr(e)}
        time.sleep(max(0.1, COMFYUI_POLL_INTERVAL))
    raise TimeoutError(f"ComfyUI prompt {prompt_id} did not finish within {timeout}s; last={last}")

def extract_comfyui_images(history: dict[str, Any], prompt_id: str) -> list[dict[str, Any]]:
    entry = history.get(prompt_id) if isinstance(history, dict) and prompt_id in history else history
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    images: list[dict[str, Any]] = []
    for node_id, out in (outputs or {}).items():
        for img in (out or {}).get("images", []) or []:
            if isinstance(img, dict) and img.get("filename"):
                item = dict(img)
                item["nodeId"] = node_id
                images.append(item)
    return images

def fetch_comfyui_image(image_meta: dict[str, Any], out_path: Path) -> str:
    query = urlencode({
        "filename": image_meta.get("filename", ""),
        "subfolder": image_meta.get("subfolder", ""),
        "type": image_meta.get("type", "output"),
    })
    data = http_binary_get(f"{COMFYUI_URL}/view?{query}", timeout=60)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return str(out_path)

def sdcpp_repair_command_template(template: str) -> tuple[str, bool, str]:
    return sdcpp_backend.repair_command_template(template, SDCPP_DEFAULT_COMMAND_TEMPLATE)

def sdcpp_command_mode_is_template() -> bool:
    return sdcpp_backend.command_mode_is_template(SDCPP_SERVER_COMMAND_MODE)

def sdcpp_base_arg_list() -> list[str]:
    return sdcpp_backend.base_arg_list(_sdcpp_config())

def quote_cmd_arg(value: str) -> str:
    return sdcpp_backend.quote_cmd_arg(value)

def _extra_has_flag(extra: str, *flags: str) -> bool:
    return sdcpp_backend.extra_has_flag(extra, *flags)

def sdcpp_effective_extra_args() -> str:
    return sdcpp_backend.effective_extra_args(_sdcpp_config())

def sdcpp_effective_extra_arg_list() -> list[str]:
    return sdcpp_backend.effective_extra_arg_list(_sdcpp_config())

def sdcpp_server_is_configured() -> bool:
    return sdcpp_backend.server_is_configured(_sdcpp_config(), SDCPP_SERVER_COMMAND_TEMPLATE)

def http_json_get(url: str, timeout: int = 5) -> Any:
    req = urlrequest.Request(url, headers={"Accept": "application/json,*/*"}, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if "json" in ctype:
            return json.loads(raw.decode("utf-8"))
        return raw

def sdcpp_server_is_alive() -> bool:
    return sdcpp_backend.server_is_alive(SDCPP_SERVER_URL, SDCPP_SERVER_HEALTH_PATHS, timeout=2)

def build_sdcpp_server_command() -> tuple[list[str] | str, bool]:
    return sdcpp_backend.build_server_command(_sdcpp_config(), SDCPP_SERVER_COMMAND_TEMPLATE)

def _stringify_cmd(cmd: list[str] | str) -> str:
    return sdcpp_backend.stringify_cmd(cmd)

def sdcpp_debug_snapshot(include_log_tail: bool = True) -> dict[str, Any]:
    snap = sdcpp_service.debug_snapshot(
        state=SDCPP_SERVER_STATE,
        app_version=APP_VERSION,
        server_url=SDCPP_SERVER_URL,
        server_autostart=SDCPP_SERVER_AUTOSTART,
        show_console=SDCPP_SERVER_SHOW_CONSOLE,
        server_exe=SDCPP_SERVER_EXE,
        model=SDCPP_MODEL,
        vae=SDCPP_VAE,
        llm=SDCPP_LLM,
        lora_dir=_effective_sdcpp_lora_dir(),
        lora_prompt_tags=_effective_sdcpp_lora_prompt_tags(),
        lora_file=SDCPP_LORA_FILE,
        lora_weight=SDCPP_LORA_WEIGHT,
        command_mode=SDCPP_SERVER_COMMAND_MODE,
        command_template=SDCPP_SERVER_COMMAND_TEMPLATE,
        template_repair=sdcpp_repair_command_template(SDCPP_SERVER_COMMAND_TEMPLATE),
        manual_extra_args=SDCPP_SERVER_EXTRA_ARGS,
        effective_extra_args=sdcpp_effective_extra_args(),
        command=SDCPP_SERVER_STATE.last_command or _stringify_cmd(build_sdcpp_server_command()[0]),
        server_log_file=SDCPP_SERVER_LOG_FILE,
        server_is_alive=sdcpp_server_is_alive(),
        server_is_configured=sdcpp_server_is_configured(),
        tail_text_file=_tail_text_file,
        include_log_tail=include_log_tail,
    )
    return snap

def ensure_sdcpp_server() -> bool:
    ok = sdcpp_service.ensure_server(
        state=SDCPP_SERVER_STATE,
        root=ROOT,
        cache_dir=CACHE_DIR,
        server_url=SDCPP_SERVER_URL,
        server_autostart=SDCPP_SERVER_AUTOSTART,
        startup_timeout=SDCPP_SERVER_STARTUP_TIMEOUT,
        show_console=SDCPP_SERVER_SHOW_CONSOLE,
        server_log_file=SDCPP_SERVER_LOG_FILE,
        server_is_alive=sdcpp_server_is_alive,
        build_command=build_sdcpp_server_command,
        stringify_cmd=_stringify_cmd,
        cleanup_process=cleanup_sdcpp_server_process,
        log_event=log_event,
        tail_text_file=_tail_text_file,
    )
    return ok

def sdcpp_server_payload(prompt: str, negative: str, width: int, height: int, seed: int, style: str) -> dict[str, Any]:
    return sdcpp_backend.server_payload(
        _sdcpp_config(),
        prompt,
        negative,
        width,
        height,
        seed,
        style,
        is_zimage=image_backend_is_zimage(),
        positive_only=zimage_positive_only_enabled(),
    )

def extract_image_from_server_response(raw: bytes, ctype: str, out_path: Path) -> bool:
    return sdcpp_backend.extract_image_from_response(
        raw,
        ctype,
        out_path,
        fetch_url=http_binary_get,
        timeout=SDCPP_SERVER_REQUEST_TIMEOUT,
    )

def generate_sdcpp_server(prompt: str, negative: str, sprite_id: str, preferred_canvas: int = 32) -> list[str]:
    if not ensure_sdcpp_server():
        log_event("warn", "stable-diffusion.cpp server is not available; image asset generation will fail/retry", {"serverUrl": SDCPP_SERVER_URL, "autostart": SDCPP_SERVER_AUTOSTART})
        return []
    out: list[str] = []
    variants = max(1, int(GENERATE_VARIANTS))
    width = env_int("INFINI_SDCPP_WIDTH", SDCPP_WIDTH, lo=64, hi=2048)
    height = env_int("INFINI_SDCPP_HEIGHT", SDCPP_HEIGHT, lo=64, hi=2048)
    prompt = str(prompt or "")
    paths = SDCPP_SERVER_TXT2IMG_PATHS or ["/sdapi/v1/txt2img"]
    styles = [SDCPP_SERVER_PAYLOAD_STYLE] if SDCPP_SERVER_PAYLOAD_STYLE != "auto" else ["a1111", "sdcpp", "openai"]
    for i in range(variants):
        seed = SDCPP_SEED if SDCPP_SEED >= 0 else random.randint(1, 2**31 - 1)
        out_path = SPRITE_DIR / f"{safe_file_part(sprite_id, 'sprite')}_raw_sdcpp_server_{i}.png"
        ok = False
        last_err = ""
        for path in paths:
            url = SDCPP_SERVER_URL + (path if path.startswith("/") else "/" + path)
            for style in styles:
                payload = sdcpp_server_payload(prompt, negative or asset_negative_prompt("item"), width, height, seed, style)
                trace_event("step", "SDCPP:txt2img", "trying sd.cpp txt2img endpoint", {
                    "spriteId": sprite_id, "url": url, "style": style, "seed": seed, "width": width, "height": height,
                    "payloadKeys": sorted(payload.keys()),
                })
                try:
                    req = urlrequest.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json,image/png,*/*"}, method="POST")
                    t0 = time.time()
                    with urlrequest.urlopen(req, timeout=SDCPP_SERVER_REQUEST_TIMEOUT) as resp:
                        raw = resp.read()
                        ctype = resp.headers.get("Content-Type", "")
                    if extract_image_from_server_response(raw, ctype, out_path) and out_path.exists():
                        out.append(str(out_path))
                        trace_event("step", "SDCPP:txt2img", "sd.cpp image generated", {"spriteId": sprite_id, "path": str(out_path), "ms": int((time.time() - t0) * 1000), "url": url, "style": style, "seed": seed, "contentType": ctype})
                        log_event("info", "stable-diffusion.cpp server image generated", {"spriteId": sprite_id, "path": str(out_path), "ms": int((time.time() - t0) * 1000), "url": url, "style": style, "seed": seed})
                        ok = True
                        break
                    last_err = f"no image in response from {url} style={style} contentType={ctype} bodyPrefix={raw[:200]!r}"
                except Exception as e:
                    last_err = repr(e)
            if ok:
                break
        if not ok:
            trace_event("error", "SDCPP:txt2img", "sd.cpp generation failed", {"spriteId": sprite_id, "error": last_err, "paths": paths, "styles": styles})
            log_event("warn", "stable-diffusion.cpp server generation failed", {"spriteId": sprite_id, "error": last_err, "paths": paths})
    return out

def image_api_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json,image/png,*/*"}
    if IMAGE_API_KEY:
        headers["Authorization"] = "Bearer " + IMAGE_API_KEY
    if IMAGE_API_EXTRA_HEADERS_JSON:
        try:
            extra = json.loads(IMAGE_API_EXTRA_HEADERS_JSON)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if isinstance(k, str) and k.strip() and v is not None:
                        headers[k.strip()] = str(v)
        except Exception as e:
            log_event("warn", "invalid INFINI_IMAGE_API_EXTRA_HEADERS_JSON", {"error": repr(e)})
    return headers

def image_api_url() -> str:
    path = IMAGE_API_PATH or "/images/generations"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return IMAGE_API_BASE_URL.rstrip("/") + (path if path.startswith("/") else "/" + path)

def extract_image_from_api_response(raw: bytes, ctype: str, out_path: Path, timeout: int) -> bool:
    if raw[:8] == b"\x89PNG\r\n\x1a\n" or "image/png" in (ctype or ""):
        out_path.write_bytes(raw)
        return True
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return False

    # OpenAI Images API shape: {data:[{b64_json:"..."}]} or {data:[{url:"..."}]}
    data = obj.get("data") if isinstance(obj, dict) else None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            b64 = first.get("b64_json") or first.get("image_base64") or first.get("base64")
            if b64:
                val = str(b64)
                if val.startswith("data:") and "," in val:
                    val = val.split(",", 1)[1]
                out_path.write_bytes(base64.b64decode(val))
                return True
            url = first.get("url") or first.get("image_url")
            if url:
                out_path.write_bytes(http_binary_get(str(url), timeout=timeout))
                return True

    # Some OpenAI-compatible gateways use {images:[...]} or {image:"..."}.
    images = obj.get("images") if isinstance(obj, dict) else None
    if isinstance(images, list) and images:
        val = images[0]
        if isinstance(val, dict):
            val = val.get("b64_json") or val.get("url") or val.get("image")
        if isinstance(val, str):
            if val.startswith("http://") or val.startswith("https://"):
                out_path.write_bytes(http_binary_get(val, timeout=timeout))
                return True
            if val.startswith("data:") and "," in val:
                val = val.split(",", 1)[1]
            out_path.write_bytes(base64.b64decode(val))
            return True

    for key in ["b64_json", "image_base64", "base64", "image", "png", "output", "result"]:
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, str) and len(val) > 64:
            if val.startswith("http://") or val.startswith("https://"):
                out_path.write_bytes(http_binary_get(val, timeout=timeout))
                return True
            if val.startswith("data:") and "," in val:
                val = val.split(",", 1)[1]
            out_path.write_bytes(base64.b64decode(val))
            return True
    return False

def generate_image_api(prompt: str, negative: str, sprite_id: str, preferred_canvas: int = 32) -> list[str]:
    """Generate sprite through an OpenAI-compatible image API.

    This is intentionally independent from INFINI_LLM_PROVIDER: OpenRouter (or any
    LLM API) can author the item contract while this backend creates PNGs.
    """
    if not IMAGE_API_BASE_URL:
        log_event("warn", "image API backend has no base URL", {"backend": IMAGE_BACKEND})
        return []
    if not IMAGE_API_KEY:
        log_event("warn", "image API backend has no API key", {"backend": IMAGE_BACKEND, "baseUrl": IMAGE_API_BASE_URL})
        return []
    variants = max(1, int(GENERATE_VARIANTS))
    out: list[str] = []
    url = image_api_url()
    size = IMAGE_API_SIZE or "512x512"
    full_prompt = str(prompt or "")
    if negative:
        full_prompt = full_prompt + ", avoid: " + str(negative)[:700]
    for i in range(variants):
        payload = {
            "model": IMAGE_API_MODEL,
            "prompt": full_prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }
        out_path = SPRITE_DIR / f"{safe_file_part(sprite_id, 'sprite')}_raw_image_api_{i}.png"
        try:
            req = urlrequest.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=image_api_headers(), method="POST")
            t0 = time.time()
            with urlrequest.urlopen(req, timeout=IMAGE_API_TIMEOUT) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
            if extract_image_from_api_response(raw, ctype, out_path, IMAGE_API_TIMEOUT) and out_path.exists():
                out.append(str(out_path))
                log_event("info", "image API generated sprite", {"spriteId": sprite_id, "model": IMAGE_API_MODEL, "url": url, "ms": int((time.time()-t0)*1000), "path": str(out_path)})
                continue
            log_event("warn", "image API response had no usable image", {"spriteId": sprite_id, "contentType": ctype, "bodyPrefix": raw[:300].decode("utf-8", "replace")})
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:2000]
            except Exception:
                pass
            # Some gateways reject response_format. Retry once without it.
            if e.code in {400, 404, 422}:
                try:
                    retry = dict(payload)
                    retry.pop("response_format", None)
                    req = urlrequest.Request(url, data=json.dumps(retry, ensure_ascii=False).encode("utf-8"), headers=image_api_headers(), method="POST")
                    with urlrequest.urlopen(req, timeout=IMAGE_API_TIMEOUT) as resp:
                        raw = resp.read()
                        ctype = resp.headers.get("Content-Type", "")
                    if extract_image_from_api_response(raw, ctype, out_path, IMAGE_API_TIMEOUT) and out_path.exists():
                        out.append(str(out_path))
                        continue
                except Exception as e2:
                    log_event("warn", "image API retry without response_format failed", {"spriteId": sprite_id, "error": repr(e2)})
            log_event("warn", "image API HTTP error", {"spriteId": sprite_id, "status": e.code, "body": body})
        except Exception as e:
            log_event("warn", "image API generation failed", {"spriteId": sprite_id, "error": repr(e)})
    return out

def generate_sdcpp(prompt: str, negative: str, sprite_id: str, preferred_canvas: int = 32) -> list[str]:
    """Generate image through persistent stable-diffusion.cpp server only.

    v0.4.19 intentionally removed CLI/subprocess-per-image mode because it reloads
    model weights on every sprite and makes gameplay crafting unusably slow.
    """
    out = generate_sdcpp_server(prompt, negative, sprite_id, preferred_canvas)
    if out:
        return out
    log_event("warn", "stable-diffusion.cpp server unavailable; image asset will fail/retry instead of procedural authoring", {"serverUrl": SDCPP_SERVER_URL, "autostart": SDCPP_SERVER_AUTOSTART})
    return []

def append_a1111_lora(prompt: str) -> str:
    parts = [str(prompt or '').strip()]
    if A1111_TRIGGER:
        parts.append(A1111_TRIGGER)
    if A1111_LORA_NAME:
        weight = A1111_LORA_WEIGHT or '0.8'
        parts.append(f"<lora:{A1111_LORA_NAME}:{weight}>")
    return ", ".join(p for p in parts if p)

def generate_a1111(prompt: str, negative: str, sprite_id: str, preferred_canvas: int = 32) -> list[str]:
    # Low-VRAM safe by default: sequential requests, batch size 1, no hires fix.
    width = env_int("INFINI_A1111_WIDTH", A1111_WIDTH, lo=64, hi=2048)
    height = env_int("INFINI_A1111_HEIGHT", A1111_HEIGHT, lo=64, hi=2048)
    variants = max(1, int(GENERATE_VARIANTS))
    batch_size = env_int("INFINI_A1111_BATCH_SIZE", A1111_BATCH_SIZE, lo=1, hi=16)
    batch_size = min(batch_size, variants)
    out: list[str] = []
    prompt = append_a1111_lora(prompt)
    negative = negative or asset_negative_prompt("item")
    remaining = variants
    request_i = 0
    while remaining > 0:
        this_batch = min(batch_size, remaining)
        payload = {
            "prompt": prompt,
            "negative_prompt": negative,
            "steps": env_int("INFINI_A1111_STEPS", 16),
            "cfg_scale": env_float("INFINI_A1111_CFG", 5.5),
            "width": width,
            "height": height,
            "batch_size": this_batch,
            "n_iter": 1,
            "sampler_name": env_str("INFINI_A1111_SAMPLER", "Euler a"),
            "enable_hr": False,
            "do_not_save_samples": True,
            "do_not_save_grid": True,
        }
        raw = http_json(f"{A1111_URL}/sdapi/v1/txt2img", payload, timeout=VISUAL_GENERATION_TIMEOUT)
        for j, b64 in enumerate(raw.get("images", [])):
            data = base64.b64decode(b64.split(",")[-1])
            p = SPRITE_DIR / f"{sprite_id}_raw_a1111_{request_i}_{j}.png"
            p.write_bytes(data)
            out.append(str(p))
        remaining -= this_batch
        request_i += 1
    log_event("info", "a1111 images generated", {"spriteId": sprite_id, "count": len(out), "width": width, "height": height, "variants": variants, "batchSize": batch_size, "removeBg": REMOVE_BG,
                        "requirePillow": REQUIRE_PILLOW,
                        "pillowAvailable": Image is not None, "bgMode": BG_REMOVE_MODE})
    return out

def generate_comfyui(prompt: str, negative: str, sprite_id: str) -> list[str]:
    """Run a real ComfyUI workflow and download its output PNGs.

    Contract:
    - workflow JSON may contain placeholders like {{PROMPT}}, {{SPRITE_ID}}, {{WIDTH}};
    - SaveImage should produce at least one image;
    - local postprocess still owns alpha/crop/downscale, so workflow can be raw SD1.5.
    """
    workflow_path = resolve_comfyui_workflow_path()
    if not workflow_path:
        log_event("warn", "ComfyUI selected but no workflow template was found; using procedural fallback", {"workflow": COMFYUI_WORKFLOW})
        return [visual_asset_pipeline.generate_procedural_sprite({"id": sprite_id, "name": prompt, "tags": [], "visual": {"preferredCanvasSize": 32}}, variant=0, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)]
    workflow = json.loads(workflow_path.read_text(encoding="utf-8-sig"))
    seed = random.randint(1, 2**31 - 1)
    workflow = json_deep_replace(workflow, comfyui_mapping(prompt, negative, sprite_id, seed))
    payload = {"prompt": workflow, "client_id": COMFYUI_CLIENT_ID}
    queued = http_json(f"{COMFYUI_URL}/prompt", payload, timeout=30)
    prompt_id = str(queued.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id: {queued}")
    log_event("info", "ComfyUI prompt queued", {"promptId": prompt_id, "spriteId": sprite_id, "workflow": str(workflow_path), "seed": seed, "width": COMFYUI_WIDTH, "height": COMFYUI_HEIGHT, "steps": COMFYUI_STEPS, "cfg": COMFYUI_CFG, "lora": COMFYUI_LORA_NAME})
    history = poll_comfyui_history(prompt_id, COMFYUI_TIMEOUT)
    metas = extract_comfyui_images(history, prompt_id)
    out: list[str] = []
    for i, meta in enumerate(metas):
        p = SPRITE_DIR / f"{safe_file_part(sprite_id, 'sprite')}_raw_comfy_{i}.png"
        try:
            out.append(fetch_comfyui_image(meta, p))
        except Exception as e:
            log_event("warn", "ComfyUI image fetch failed", {"spriteId": sprite_id, "meta": meta, "error": repr(e)})
    log_event("info", "ComfyUI images downloaded", {"spriteId": sprite_id, "count": len(out), "promptId": prompt_id, "removeBg": REMOVE_BG,
                        "requirePillow": REQUIRE_PILLOW,
                        "pillowAvailable": Image is not None, "bgMode": BG_REMOVE_MODE})
    return out

# =============================================================================
# Explicit pipeline dependencies
# =============================================================================
from infini_local.pipelines.pipeline_support import (
    Image,
    ImageDraw,
    A1111_BATCH_SIZE,
    A1111_HEIGHT,
    A1111_LORA_NAME,
    A1111_LORA_WEIGHT,
    A1111_TRIGGER,
    A1111_URL,
    A1111_WIDTH,
    APP_VERSION,
    BG_REMOVE_MODE,
    CACHE_DIR,
    COMFYUI_CFG,
    COMFYUI_CHECKPOINT,
    COMFYUI_CLIENT_ID,
    COMFYUI_DENOISE,
    COMFYUI_HEIGHT,
    COMFYUI_LORA_NAME,
    COMFYUI_LORA_WEIGHT,
    COMFYUI_POLL_INTERVAL,
    COMFYUI_SAMPLER,
    COMFYUI_SCHEDULER,
    COMFYUI_STEPS,
    COMFYUI_TIMEOUT,
    COMFYUI_TRIGGER,
    COMFYUI_URL,
    COMFYUI_WIDTH,
    COMFYUI_WORKFLOW,
    COMFYUI_WORKFLOW_LORA,
    COMFYUI_WORKFLOW_NO_LORA,
    GENERATE_VARIANTS,
    IMAGE_API_BASE_URL,
    IMAGE_API_EXTRA_HEADERS_JSON,
    IMAGE_API_KEY,
    IMAGE_API_MODEL,
    IMAGE_API_PATH,
    IMAGE_API_SIZE,
    IMAGE_API_TIMEOUT,
    IMAGE_BACKEND,
    REMOVE_BG,
    REQUIRE_PILLOW,
    ROOT,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_HEIGHT,
    SDCPP_LLM,
    SDCPP_LORA_DIR,
    SDCPP_LORA_FILE,
    SDCPP_LORA_PROMPT_TAGS,
    SDCPP_LORA_WEIGHT,
    SDCPP_MODEL,
    SDCPP_SEED,
    SDCPP_SERVER_AUTOSTART,
    SDCPP_SERVER_COMMAND_MODE,
    SDCPP_SERVER_COMMAND_TEMPLATE,
    SDCPP_SERVER_EXE,
    SDCPP_SERVER_EXTRA_ARGS,
    SDCPP_SERVER_HOST,
    SDCPP_SERVER_PORT,
    SDCPP_STEPS,
    SDCPP_CFG,
    SDCPP_SAMPLER,
    ZIMAGE_PROMPT_CONTRACT,
    ZIMAGE_POSITIVE_ONLY,
    SDCPP_SERVER_HEALTH_PATHS,
    SDCPP_SERVER_LOG_FILE,
    SDCPP_SERVER_PAYLOAD_STYLE,
    SDCPP_SERVER_REQUEST_TIMEOUT,
    SDCPP_SERVER_SHOW_CONSOLE,
    SDCPP_SERVER_STARTUP_TIMEOUT,
    SDCPP_SERVER_STATE,
    SDCPP_SERVER_TXT2IMG_PATHS,
    SDCPP_SERVER_URL,
    SDCPP_VAE,
    SDCPP_WIDTH,
    SPRITE_DIR,
    VISUAL_GENERATION_TIMEOUT,
    _sdcpp_config,
    _tail_text_file,
    cleanup_sdcpp_server_process,
    log_event,
    safe_file_part,
    sdcpp_backend,
    sdcpp_service,
    trace_event,
    visual_asset_pipeline,
)

from infini_local.pipelines.llm_authoring_pipeline import (
    http_get_json,
    http_json,
)

from infini_local.pipelines.visual_generation_pipeline import (
    asset_negative_prompt,
    image_backend_is_zimage,
    zimage_positive_only_enabled,
)


# Local config reader: image backend owns sd.cpp command construction now.
def _effective_sdcpp_lora_prompt_tags() -> str:
    tags = str(SDCPP_LORA_PROMPT_TAGS or "").strip()
    if tags:
        return tags
    return sdcpp_backend.lora_tag_from_file(SDCPP_LORA_FILE, SDCPP_LORA_WEIGHT)


def _effective_sdcpp_lora_dir() -> str:
    return str(SDCPP_LORA_DIR or "").strip() or sdcpp_backend.lora_dir_from_file(SDCPP_LORA_FILE)


def _sdcpp_config() -> sdcpp_backend.SdcppBackendConfig:
    return sdcpp_backend.SdcppBackendConfig(
        default_command_template=SDCPP_DEFAULT_COMMAND_TEMPLATE,
        command_mode=SDCPP_SERVER_COMMAND_MODE,
        server_exe=SDCPP_SERVER_EXE,
        model=SDCPP_MODEL,
        vae=SDCPP_VAE,
        llm=SDCPP_LLM,
        lora_dir=_effective_sdcpp_lora_dir(),
        lora_prompt_tags=_effective_sdcpp_lora_prompt_tags(),
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
    )
