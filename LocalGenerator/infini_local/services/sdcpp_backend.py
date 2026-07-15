from __future__ import annotations

"""stable-diffusion.cpp / Z-Image backend helpers.

This module owns the low-level sd.cpp command and response contracts.  It is kept
side-effect-light on purpose: server.py still owns HTTP routes, environment
bootstrapping, process lifecycle decisions, trace/log callbacks, and generated
asset orchestration.  Tests can import this module directly to validate the
backend contract without importing the full HTTP server.
"""

from dataclasses import dataclass
import base64
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
from typing import Any, Callable
from urllib import request as urlrequest


@dataclass(frozen=True)
class SdcppBackendConfig:
    default_command_template: str
    command_mode: str
    server_exe: str
    model: str
    vae: str
    llm: str
    lora_dir: str
    lora_prompt_tags: str
    host: str
    port: int
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    extra_args: str
    server_url: str
    health_paths: list[str]
    zimage_prompt_contract: str
    zimage_positive_only: bool
    rocm_compat_root: str = ""
    lora_file: str = ""


def server_process_environment(
    cfg: SdcppBackendConfig,
    *,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the isolated environment used only by the hybrid sd.cpp child."""
    env = dict(os.environ if base_env is None else base_env)
    raw_root = str(cfg.rocm_compat_root or "").strip().rstrip("\\/")
    if not raw_root:
        return env
    is_windows_path = len(raw_root) >= 2 and raw_root[1] == ":"
    root = str(PureWindowsPath(raw_root)) if is_windows_path else raw_root
    rocblas = (
        str(PureWindowsPath(root) / "rocblas" / "library")
        if is_windows_path
        else str(Path(root) / "rocblas" / "library")
    )
    env.update({
        "ROCM_COMPAT_ROOT": root,
        "ROCM_PATH": root,
        "HIP_PATH": root,
        "ROCBLAS_TENSILE_LIBPATH": rocblas,
    })
    old_path = str(env.get("PATH") or "")
    separator = ";" if is_windows_path else os.pathsep
    env["PATH"] = root + (separator + old_path if old_path else "")
    return env


def quote_cmd_arg(value: str) -> str:
    """Quote one command argument for Windows shell=True template mode."""
    v = str(value).replace('"', '\\"')
    return f'"{v}"'


def repair_command_template(template: str, default_template: str) -> tuple[str, bool, str]:
    """Return a safe sd.cpp command template.

    The Settings GUI exposes a free-form command template field.  A copied
    pipeline preset name can accidentally land inside a flag name, for example
    `--sampling-mOpenRouter + local Z-Image/sd.cppethod`.  In safe-args mode the
    caller should build argv directly; in template mode this repair only handles
    clearly malformed templates.
    """
    raw = str(template or "").strip()
    if not raw:
        return default_template, True, "empty_template"
    required = ("{exe}", "{model}", "{host}", "{port}", "{width}", "{height}", "{steps}", "{cfg}", "{sampler}", "{extra}")
    lowered = raw.lower()
    preset_bleed = any(x.lower() in lowered for x in ("openrouter + local", "lm studio + local", "z-image/sd.cppethod"))
    broken_sampling = "--sampling-method" not in raw and "sampling-m" in raw
    missing_required = any(tok not in raw for tok in required)
    if preset_bleed or broken_sampling or missing_required:
        reasons: list[str] = []
        if preset_bleed:
            reasons.append("pipeline_preset_text_inside_template")
        if broken_sampling:
            reasons.append("broken_sampling_method_flag")
        if missing_required:
            reasons.append("missing_required_placeholders")
        return default_template, True, "+".join(reasons)
    return raw, False, ""


def command_mode_is_template(command_mode: str) -> bool:
    return str(command_mode or "").strip().lower() in {"template", "raw_template", "custom_template"}


def executable_path_for_subprocess(value: str) -> str:
    """Convert Windows executable drive path for POSIX/WSL subprocess argv mode.

    Only the executable path is normalized.  When WSL launches a Windows .exe,
    that Windows process still expects model/LoRA arguments as Windows paths
    (``C:/...``), not WSL ``/mnt/c/...`` paths.
    Template/shell mode keeps its raw text and is not normalized here.
    """
    raw = str(value or "").strip()
    if not raw or os.name == "nt":
        return raw
    if len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] in {"\\", "/"}:
        drive = raw[0].lower()
        rest = raw[2:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return raw


def base_arg_list(cfg: SdcppBackendConfig) -> list[str]:
    return [
        executable_path_for_subprocess(cfg.server_exe),
        "--diffusion-model", cfg.model,
        "-l", cfg.host,
        "--listen-port", str(cfg.port),
        "-W", str(cfg.width),
        "-H", str(cfg.height),
        "--steps", str(cfg.steps),
        "--cfg-scale", str(cfg.cfg),
        "--sampling-method", str(cfg.sampler),
    ]


def split_extra_args(extra: str) -> list[str]:
    """Split user-provided sd.cpp extra args for subprocess argv mode.

    Even on Windows we use POSIX-like quote handling here because subprocess gets
    an argv list, not a raw cmd.exe line. This strips helper quotes around values
    such as ``--cache-option "threshold=0.08,warmup=2"`` instead of passing the
    literal quote characters to sd.cpp. Dedicated GUI fields should be used for
    Windows paths, so extra args stay mostly flag/value pairs.
    """
    raw = str(extra or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=True)
    except ValueError:
        return raw.split()


def extra_has_flag(extra: str, *flags: str) -> bool:
    """Best-effort flag presence check for user-provided sd.cpp extra args.

    Accepts both ``--flag value`` and ``--flag=value`` spellings so dedicated GUI
    rows do not duplicate VAE/Qwen/LoRA paths when a user already supplied the
    same option manually.
    """
    wanted = {str(flag or "").strip() for flag in flags if str(flag or "").strip()}
    for token in split_extra_args(extra):
        name = str(token).split("=", 1)[0]
        if name in wanted:
            return True
    return False


def lora_is_active(lora_prompt_tags: str) -> bool:
    """LoRA folder is useful only when a prompt tag enables a concrete LoRA."""
    return bool(str(lora_prompt_tags or "").strip())


def effective_extra_args(cfg: SdcppBackendConfig) -> str:
    """Compose sd.cpp extra args from dedicated GUI fields and manual extras."""
    manual = cfg.extra_args or ""
    parts: list[str] = []
    if cfg.vae and not extra_has_flag(manual, "--vae"):
        parts.append(f"--vae {quote_cmd_arg(cfg.vae)}")
    if cfg.llm and not extra_has_flag(manual, "--llm"):
        parts.append(f"--llm {quote_cmd_arg(cfg.llm)}")
    if cfg.lora_dir and lora_is_active(cfg.lora_prompt_tags) and not extra_has_flag(manual, "--lora-model-dir"):
        parts.append(f"--lora-model-dir {quote_cmd_arg(cfg.lora_dir)}")
    if manual:
        parts.append(manual)
    return " ".join(x.strip() for x in parts if x and x.strip()).strip()


def effective_extra_arg_list(cfg: SdcppBackendConfig) -> list[str]:
    args: list[str] = []
    manual = cfg.extra_args or ""
    if cfg.vae and not extra_has_flag(manual, "--vae"):
        args += ["--vae", cfg.vae]
    if cfg.llm and not extra_has_flag(manual, "--llm"):
        args += ["--llm", cfg.llm]
    if cfg.lora_dir and lora_is_active(cfg.lora_prompt_tags) and not extra_has_flag(manual, "--lora-model-dir"):
        args += ["--lora-model-dir", cfg.lora_dir]
    if manual:
        args += split_extra_args(manual)
    return args


def server_is_configured(cfg: SdcppBackendConfig, command_template: str = "") -> bool:
    if command_template:
        return True
    if cfg.server_exe and cfg.model:
        return True
    # External server already running: URL alone is enough.
    return bool(cfg.server_url)


def server_is_alive(server_url: str, health_paths: list[str], timeout: int = 2) -> bool:
    if not server_url:
        return False
    from urllib import error as urlerror
    for path in health_paths:
        try:
            url = server_url.rstrip("/") + (path if path.startswith("/") else "/" + path)
            req = urlrequest.Request(url, headers={"Accept": "application/json,*/*"}, method="GET")
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                if not 200 <= int(getattr(resp, "status", 200)) < 300:
                    continue
                body = resp.read(16384).decode("utf-8", errors="ignore")
                normalized_path = "/" + path.strip("/").lower()
                if normalized_path == "/sdapi/v1/sd-models":
                    try:
                        return isinstance(json.loads(body), list)
                    except (TypeError, ValueError):
                        continue
                signature = body.lower()
                if any(token in signature for token in ("stable-diffusion", "stable diffusion", "sd.cpp", "sdapi", "txt2img")):
                    return True
        except urlerror.HTTPError as e:
            try:
                if 200 <= int(getattr(e, "code", 0)) < 300:
                    continue
            except Exception:
                pass
            continue
        except Exception:
            continue
    return False


def build_server_command(cfg: SdcppBackendConfig, command_template: str = "") -> tuple[list[str] | str, bool]:
    """Build long-lived stable-diffusion.cpp server command."""
    extra = effective_extra_args(cfg)
    if command_mode_is_template(cfg.command_mode):
        template, _repaired, _reason = repair_command_template(command_template, cfg.default_command_template)
        mapping = {
            "exe": quote_cmd_arg(cfg.server_exe),
            "model": quote_cmd_arg(cfg.model),
            "host": cfg.host,
            "port": str(cfg.port),
            "width": str(cfg.width),
            "height": str(cfg.height),
            "steps": str(cfg.steps),
            "cfg": str(cfg.cfg),
            "sampler": str(cfg.sampler),
            "extra": extra,
        }
        return template.format(**mapping), True

    exe = cfg.server_exe
    exe_name = Path(exe).name.lower() if exe else ""
    if "sd-server" in exe_name or exe_name in {"server.exe", "server"}:
        args = base_arg_list(cfg)
    else:
        # Conservative legacy default. If the binary does not support --server,
        # callers can set command mode=template.
        args = [exe, "--server", "-m", cfg.model, "--host", cfg.host, "--port", str(cfg.port)]
    args += effective_extra_arg_list(cfg)
    return args, False


def stringify_cmd(cmd: list[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(quote_cmd_arg(str(x)) if any(c.isspace() for c in str(x)) else str(x) for x in cmd)





def lora_dir_from_file(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    parent = PureWindowsPath(raw).parent if "\\" in raw or ":" in raw else Path(raw).parent
    return "" if str(parent) in {"", "."} else str(parent)

def lora_tag_from_file(path: str, weight: str = "0.25") -> str:
    """Return stable-diffusion-webui/sd.cpp style LoRA prompt tag for a file path.

    sd.cpp discovers LoRA files through ``--lora-model-dir`` and enables a
    concrete LoRA by prompt tag.  The tag name is the file stem, e.g.
    ``C:/loras/terraria_items.safetensors`` -> ``<lora:terraria_items:0.25>``.
    """
    raw = str(path or "").strip()
    stem = (PureWindowsPath(raw).stem if "\\" in raw or ":" in raw else Path(raw).stem).strip()
    w = str(weight or "0.25").strip() or "0.25"
    if not stem:
        return ""
    return f"<lora:{stem}:{w}>"

def _split_lora_prompt_tags(lora_prompt_tags: str) -> list[str]:
    return [part for part in " ".join(str(lora_prompt_tags or "").split()).split(" ") if part]


def append_lora_prompt_tags(prompt: str, lora_prompt_tags: str) -> str:
    """Append global LoRA tags to a prompt once.

    stable-diffusion.cpp uses stable-diffusion-webui-style prompt tags such as
    ``<lora:name:0.7>`` while the LoRA search directory is configured through
    ``--lora-model-dir``.  Tags are appended individually so a retry prompt that
    already contains one configured tag does not receive a duplicate.
    """
    prompt = str(prompt or "")
    missing = [tag for tag in _split_lora_prompt_tags(lora_prompt_tags) if tag not in prompt]
    if not missing:
        return prompt
    return (prompt.rstrip() + " " + " ".join(missing)).strip()


_LORA_PROMPT_TAG_RE = re.compile(r"<lora:([^:>]+):([^>]+)>")


def structured_server_loras(prompt: str, lora_file: str = "") -> tuple[str, list[dict[str, Any]]]:
    """Translate webui prompt tags into sd-server's secure structured API.

    Current sd-server intentionally disables prompt-embedded LoRA parsing for HTTP
    routes. The tags must therefore become the request ``lora`` array while the
    text encoder receives a clean prompt. The selected file supplies the exact
    relative filename expected by the server-side LoRA cache.
    """
    selected_raw = str(lora_file or "").strip()
    selected_path = PureWindowsPath(selected_raw) if "\\" in selected_raw or ":" in selected_raw else Path(selected_raw)
    selected_name = str(selected_path.name) if selected_raw else ""
    selected_stem = str(selected_path.stem) if selected_raw else ""
    entries: list[dict[str, Any]] = []
    for match in _LORA_PROMPT_TAG_RE.finditer(str(prompt or "")):
        name = match.group(1).strip()
        try:
            multiplier = float(match.group(2).strip())
        except ValueError:
            continue
        if not math.isfinite(multiplier):
            continue
        path = selected_name if selected_name and name == selected_stem else name
        entries.append({"path": path, "multiplier": multiplier, "is_high_noise": False})
    clean_prompt = re.sub(r"\s+", " ", _LORA_PROMPT_TAG_RE.sub("", str(prompt or ""))).strip()
    return clean_prompt, entries


def server_payload(
    cfg: SdcppBackendConfig,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    style: str,
    *,
    is_zimage: bool,
    positive_only: bool,
) -> dict[str, Any]:
    """Build txt2img payload for A1111, OpenAI-ish, or sd.cpp-ish wrappers."""
    style = (style or "auto").lower()
    prompt = append_lora_prompt_tags(prompt, cfg.lora_prompt_tags)
    prompt, structured_loras = structured_server_loras(prompt, cfg.lora_file)
    neg = "" if positive_only else (negative or "")
    if style in {"a1111", "auto"}:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": neg,
            "width": width,
            "height": height,
            "steps": cfg.steps,
            "cfg_scale": cfg.cfg,
            "sampler_name": cfg.sampler,
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        if is_zimage:
            payload["zimage_prompt_contract"] = cfg.zimage_prompt_contract
            payload["zimage_positive_only_prompt"] = bool(positive_only)
        if structured_loras:
            payload["lora"] = structured_loras
        return payload
    if style == "openai":
        payload = {"prompt": prompt, "n": 1, "size": f"{width}x{height}", "response_format": "b64_json"}
        if structured_loras:
            payload["lora"] = structured_loras
        return payload
    payload = {
        "prompt": prompt,
        "negative_prompt": neg,
        "negative": neg,
        "width": width,
        "height": height,
        "steps": cfg.steps,
        "sample_steps": cfg.steps,
        "cfg_scale": cfg.cfg,
        "cfg": cfg.cfg,
        "sampler": cfg.sampler,
        "sampling_method": cfg.sampler,
        "seed": seed,
    }
    if is_zimage:
        payload["zimage_prompt_contract"] = cfg.zimage_prompt_contract
        payload["zimage_positive_only_prompt"] = bool(positive_only)
    if structured_loras:
        payload["lora"] = structured_loras
    return payload


def extract_image_from_response(
    raw: bytes,
    ctype: str,
    out_path: Path,
    *,
    fetch_url: Callable[[str, int], bytes] | None = None,
    timeout: int = 240,
) -> bool:
    """Decode an image from common sd.cpp/A1111/OpenAI-compatible responses."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n" or "image/png" in (ctype or ""):
        out_path.write_bytes(raw)
        return True
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return False
    images = obj.get("images") if isinstance(obj, dict) else None
    if isinstance(images, list) and images:
        b64 = str(images[0])
        if "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        out_path.write_bytes(base64.b64decode(b64))
        return True
    data = obj.get("data") if isinstance(obj, dict) else None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                out_path.write_bytes(base64.b64decode(str(first["b64_json"])))
                return True
            if first.get("url") and fetch_url is not None:
                out_path.write_bytes(fetch_url(str(first["url"]), timeout))
                return True
    for key in ["image", "png", "output", "result"]:
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, str) and len(val) > 64:
            try:
                b64 = val.split(",", 1)[1] if val.startswith("data:") and "," in val else val
                out_path.write_bytes(base64.b64decode(b64))
                return True
            except Exception:
                pass
    for key in ["path", "file", "filename", "output_path"]:
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, str):
            p = Path(val)
            if p.exists():
                out_path.write_bytes(p.read_bytes())
                return True
    return False
