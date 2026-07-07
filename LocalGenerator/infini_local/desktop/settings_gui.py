from __future__ import annotations

import os
import json
import re
import socket
import subprocess
import shlex
import signal
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path, PureWindowsPath
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    TKINTER_AVAILABLE = True
    TKINTER_IMPORT_ERROR = ""
except Exception as _tkinter_import_error:
    # Headless Python installs on Linux often omit tkinter/_tkinter.  Contract
    # tests import this module for DEFAULTS/FIELD_ORDER/static helpers, so import
    # must degrade to lightweight headless shims instead of blocking the whole pytest run.
    TKINTER_AVAILABLE = False
    TKINTER_IMPORT_ERROR = f"{type(_tkinter_import_error).__name__}: {_tkinter_import_error}"
    class _TkHeadlessBase:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name):
            return self._noop

        def _noop(self, *args, **kwargs):
            return None

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def grid_remove(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        config = configure

        def destroy(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def winfo_children(self, *args, **kwargs):
            return []

        def yview(self, *args, **kwargs):
            return None

        def xview(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

        def see(self, *args, **kwargs):
            return None

        def yview_moveto(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def itemconfigure(self, *args, **kwargs):
            return None

        def bbox(self, *args, **kwargs):
            return (0, 0, 0, 0)

        def after(self, *args, **kwargs):
            return None

        def after_cancel(self, *args, **kwargs):
            return None

    class _TkHeadlessVar:
        def __init__(self, value=""):
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

    class _TkHeadless:
        Widget = _TkHeadlessBase
        Toplevel = _TkHeadlessBase
        Frame = _TkHeadlessBase
        Button = _TkHeadlessBase
        Label = _TkHeadlessBase
        Entry = _TkHeadlessBase
        Text = _TkHeadlessBase
        Canvas = _TkHeadlessBase
        Menu = _TkHeadlessBase
        Message = _TkHeadlessBase
        StringVar = _TkHeadlessVar
        BooleanVar = _TkHeadlessVar
        END = "end"
        LEFT = "left"
        RIGHT = "right"
        BOTH = "both"
        X = "x"
        Y = "y"
        WORD = "word"

        class Tk(_TkHeadlessBase):
            def mainloop(self, *args, **kwargs):
                return None

            def protocol(self, *args, **kwargs):
                return None

            def title(self, *args, **kwargs):
                return None

            def geometry(self, *args, **kwargs):
                return None

            def update(self, *args, **kwargs):
                return None

    class _TtkHeadless:
        Widget = _TkHeadlessBase
        Frame = _TkHeadlessBase
        Label = _TkHeadlessBase
        Button = _TkHeadlessBase
        Entry = _TkHeadlessBase
        Combobox = _TkHeadlessBase
        Checkbutton = _TkHeadlessBase
        Separator = _TkHeadlessBase
        Scrollbar = _TkHeadlessBase
        Notebook = _TkHeadlessBase
        LabelFrame = _TkHeadlessBase
        Style = _TkHeadlessBase

    class _HeadlessDialog:
        def askopenfilename(self, **kwargs):
            return ""

        def askdirectory(self, **kwargs):
            return ""

    class _HeadlessMessageBox:
        def showwarning(self, *args, **kwargs):
            return None

        def showinfo(self, *args, **kwargs):
            return None

        def showerror(self, *args, **kwargs):
            return None

        def askyesno(self, *args, **kwargs):
            return False

    tk = _TkHeadless()
    ttk = _TtkHeadless()
    filedialog = _HeadlessDialog()
    messagebox = _HeadlessMessageBox()

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.env"
EXAMPLE_PATH = ROOT / "config.example.env"
APP_TITLE = "InfiniCrafterLocal Settings GUI v0.4.237"
APP_BG = "#f5f7fb"
APP_PANEL_BG = "#eef4ff"
CARD_BG = "#ffffff"
CARD_MUTED_BG = "#f8fafc"
HEADER_BG = "#081226"
HEADER_BG_2 = "#0f1f3d"
TEXT_FG = "#0f172a"
MUTED_FG = "#64748b"
SOFT_FG = "#94a3b8"
ACCENT_BG = "#2563eb"
ACCENT_HOVER_BG = "#1d4ed8"
ACCENT_SOFT_BG = "#eff6ff"
ACCENT_FG = "#ffffff"
SUCCESS_BG = "#16a34a"
SUCCESS_SOFT_BG = "#dcfce7"
SUCCESS_FG = "#166534"
DANGER_BG = "#dc2626"
DANGER_SOFT_BG = "#fee2e2"
DANGER_FG = "#991b1b"
WARNING_SOFT_BG = "#fef3c7"
WARNING_FG = "#92400e"
BORDER_FG = "#dbe3ef"
BORDER_DARK_FG = "#cbd5e1"


FIELD_ORDER = [
    "INFINI_USE_LLM",
    "INFINI_LLM_RUNTIME_AUTHORING",
    "INFINI_LLM_RUNTIME_PLAN_REQUIRED",
    "INFINI_LLM_RUNTIME_STRICT_VALIDATION",
    "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK",
    "INFINI_GUI_PIPELINE_PRESET",
    "INFINI_LLM_PROVIDER",
    "INFINI_LMSTUDIO_URL",
    "INFINI_LMSTUDIO_MODEL",
    "INFINI_OPENROUTER_API_KEY",
    "INFINI_OPENROUTER_MODEL",
    "INFINI_OPENROUTER_HTTP_REFERER",
    "INFINI_OPENROUTER_APP_TITLE",
    "INFINI_OPENAI_COMPAT_BASE_URL",
    "INFINI_OPENAI_COMPAT_API_KEY",
    "INFINI_OPENAI_COMPAT_MODEL",
    "INFINI_LLM_FALLBACK_PROVIDER",
    "INFINI_LLM_FALLBACK_MODEL",
    "INFINI_LLM_FALLBACK_BASE_URL",
    "INFINI_LLM_FALLBACK_API_KEY",
    "INFINI_LLM_FALLBACK_NETWORK_FAILS",
    "INFINI_LLM_RESPONSE_FORMAT",
    "INFINI_LLM_TEMPERATURE",
    "INFINI_VISUAL_DIRECTOR_TEMPERATURE",
    "INFINI_LLM_MAX_TOKENS",
    "INFINI_LLM_REASONING_MODE",
    "INFINI_LLM_REASONING_MAX_TOKENS",
    "INFINI_LLM_REASONING_EXCLUDE",
    "INFINI_LLM_LOCAL_REASONING_PROMPT",
    "INFINI_IMAGE_BACKEND",
    "INFINI_SDCPP_SERVER_EXE",
    "INFINI_SDCPP_MODEL",
    "INFINI_SDCPP_VAE",
    "INFINI_SDCPP_LLM",
    "INFINI_SDCPP_LORA_DIR",
    "INFINI_SDCPP_LORA_FILE",
    "INFINI_SDCPP_LORA_WEIGHT",
    "INFINI_SDCPP_LORA_PROMPT_TAGS",
    "INFINI_SDCPP_SERVER_URL",
    "INFINI_SDCPP_SERVER_AUTOSTART",
    "INFINI_SDCPP_SERVER_COMMAND_MODE",
    "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE",
    "INFINI_SDCPP_SERVER_EXTRA_ARGS",
    "INFINI_SDCPP_SERVER_SHOW_CONSOLE",
    "INFINI_SDCPP_SERVER_LOG_FILE",
    "INFINI_SDCPP_WIDTH",
    "INFINI_SDCPP_HEIGHT",
    "INFINI_SDCPP_STEPS",
    "INFINI_SDCPP_CFG",
    "INFINI_SDCPP_SAMPLER",
    "INFINI_SDCPP_SEED",
    "INFINI_ZIMAGE_PROMPT_CONTRACT",
    "INFINI_ZIMAGE_POSITIVE_ONLY",
    "INFINI_IMAGE_API_BASE_URL",
    "INFINI_IMAGE_API_KEY",
    "INFINI_IMAGE_API_MODEL",
    "INFINI_IMAGE_API_PATH",
    "INFINI_IMAGE_API_SIZE",
    "INFINI_IMAGE_API_TIMEOUT",
    "INFINI_A1111_URL",
    "INFINI_COMFYUI_URL",
    "INFINI_VISUAL_ASSET_MODE",
    "INFINI_VISUAL_DIRECTOR_LLM",
    "INFINI_VISUAL_DIRECTOR_MAX_TOKENS",
    "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES",
    "INFINI_VISUAL_GENERATE_IMPACT_IMAGES",
    "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES",
    "INFINI_VFX_LLM_DIRECTOR",
    "INFINI_REMOVE_BG",
    "INFINI_BG_REMOVE_MODE",
    "INFINI_BG_COLOR",
    "INFINI_CHROMA_TOLERANCE",
    "INFINI_ALPHA_THRESHOLD",
    "INFINI_SPRITE_KEYER_SPILL_RADIUS",
    "INFINI_SPRITE_KEYER_RESIDUE_STEPS",
    "INFINI_SPRITE_RETRIES",
    "INFINI_SAVE_SPRITE_STAGES",
    "INFINI_PIXEL_POSTERIZE",
    "INFINI_MAX_COLORS",
    "INFINI_SPRITE_PROCESSING_PROFILE",
    "INFINI_SPRITE_MASTER_CANVAS",
    "INFINI_SPRITE_DOWNSCALE_FILTER",
    "INFINI_SPRITE_CHROMA_DEFRINGE",
    "INFINI_SPRITE_PREMULTIPLIED_RESIZE",
    "INFINI_VISUAL_STRICT_AI_AUTHORSHIP",
    "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK",
    "INFINI_HOST",
    "INFINI_PORT",
    "INFINI_ASSET_PUBLIC_BASE_URL",
    "INFINI_TERRARIA_PORT",
    "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS",
    "INFINI_CRAFT_HTTP_ATTEMPTS",
    "INFINI_TRACE_PROMPTS",
    "INFINI_TRACE_MAX_PROMPT_CHARS",
    "INFINI_TRACE_EVENTS_TAIL",
]

SDCPP_DEFAULT_COMMAND_TEMPLATE = "{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-method {sampler} {extra}"

SDCPP_EXTRA_PROFILES = {
    # Official sd.cpp backend syntax allows per-module runtime placement such as
    # diffusion=vulkan0,vae=cpu,te=vulkan0. If --params-backend is omitted,
    # sd.cpp stores parameters on the same backend as that module runtime, so do
    # not duplicate identical backend assignments in normal presets. Keep model,
    # VAE, Qwen/LLM and LoRA paths in dedicated GUI rows; these profiles are only
    # runtime/performance flags.
    "zimage_amd_safe": "-v --backend diffusion=vulkan0,vae=cpu,te=vulkan0 --rng cuda --flow-shift 3",
    "zimage_amd_low_vram": "-v --backend diffusion=vulkan0,vae=cpu,te=cpu --rng cuda --flow-shift 3",
    "zimage_amd_full_gpu": "-v --backend diffusion=vulkan0,vae=vulkan0,te=vulkan0 --rng cuda --flow-shift 3",
    "zimage_amd_disk_params": "-v --backend diffusion=vulkan0,vae=cpu,te=vulkan0 --params-backend te=disk --rng cuda --flow-shift 3",
    "zimage_cpu_compat": "-v --backend cpu --rng cpu --flow-shift 3",
    "compat_offload": "-v --offload-to-cpu --flow-shift 3",
    "basic_verbose": "-v --flow-shift 3",
    "vulkan_te_vae_cpu_dbcache": "-v --backend diffusion=vulkan0,vae=cpu,te=vulkan0 --rng cuda --flow-shift 3 --cache-mode dbcache --cache-option \"threshold=0.08,warmup=2\"",
}

SDCPP_EXTRA_PROFILE_HELP = {
    "zimage_amd_safe": "AMD safe — текущий рекомендуемый профиль под твою связку: Z-Image/diffusion и Qwen/TE на Vulkan GPU, VAE на CPU. Обычно быстрее/стабильнее на RX 6800 XT, если VAE Vulkan тормозит.",
    "zimage_amd_low_vram": "AMD low VRAM — diffusion на Vulkan, VAE и Qwen/TE на CPU. Меньше VRAM-пиков, но condition/Qwen может быть медленнее.",
    "zimage_amd_full_gpu": "AMD full GPU — diffusion, VAE и Qwen/TE на Vulkan. Пробовать, если хватает VRAM и VAE на GPU реально быстрее; при тормозах откатиться на AMD safe.",
    "zimage_amd_disk_params": "Disk params — runtime как AMD safe, но параметры Qwen/TE перечитываются с диска по необходимости. Экономит RAM/VRAM, но может сильно тормозить.",
    "zimage_cpu_compat": "CPU compat — всё на CPU. Очень медленно, зато полезно проверить, что пути/модели/команда живые без Vulkan.",
    "compat_offload": "Compat offload — старый совместимый --offload-to-cpu. Оставлен для сборок/форков, где новые --backend/--params-backend работают странно.",
    "vulkan_te_vae_cpu_dbcache": "DBCache split — AMD safe + dbcache. Эксперимент на ускорение DiT/Z-Image; если артефакты/мыло, отключить cache.",
    "basic_verbose": "Basic — только verbose + flow-shift. Для ручных экспериментов, когда backend-флаги прописываешь сам.",
}


SDCPP_EXTRA_FLAG_SPECS = [
    ("Verbose", "-v", "Показывает подробный лог sd.cpp: backend, загрузку весов, время sampling/decode и причины падений."),
    ("Diffusion FA", "--diffusion-fa", "Flash Attention для diffusion-графа. Может снизить память; поддержка зависит от модели/backend/сборки."),
    ("VAE direct", "--vae-conv-direct", "Direct convolution для VAE. Экспериментальная оптимизация; если decode ломается — убрать."),
    ("Diff direct", "--diffusion-conv-direct", "Direct convolution для diffusion. Эксперимент; оставлять только если сборка/модель реально принимает флаг."),
    ("RNG GPU", "--rng cuda", "Генератор случайности как в webui/GPU RNG. Дефолтный вариант sd.cpp для воспроизводимости с webui-стилем."),
    ("RNG CPU", "--rng cpu", "CPU/ComfyUI-style RNG. Полезно, если хочешь ближе к ComfyUI или стабильнее сравнивать backend'и."),
    ("Flow 2", "--flow-shift 2", "Flow shift 2: сдвиг расписания timestep для Flow/DiT моделей. Чуть меньше смещает шум к поздним шагам: может давать мягче/чище, но иногда слабее детали/контраст."),
    ("Flow 3", "--flow-shift 3", "Flow shift 3: более сильный flow-shift; для Z-Image в sd.cpp обычно рабочий дефолт. Часто контрастнее/резче, но может пережигать или усиливать артефакты."),
    ("LoRA runtime", "--lora-apply-mode at_runtime", "LoRA применяется во время инференса. Лучше совместимость/точность для quantized/GGUF, но может быть медленнее."),
    ("LoRA auto", "--lora-apply-mode auto", "Дать sd.cpp самому выбрать режим LoRA: для quantized весов обычно at_runtime, иначе immediately."),
    ("Cache DBCache", "--cache-mode dbcache --cache-option \"threshold=0.08,warmup=2\"", "DiT/Z-Image cache: может ускорить повторяемые прогонки, но при артефактах/мыле отключить."),
    ("Params disk", "--params-backend disk", "Минимальная RAM/VRAM-резидентность: веса перечитываются с диска по мере нужды. Может быть медленно."),
]


def repair_sdcpp_command_template(template: str) -> tuple[str, bool, str]:
    raw = str(template or "").strip()
    if not raw:
        return SDCPP_DEFAULT_COMMAND_TEMPLATE, True, "empty_template"
    required = ("{exe}", "{model}", "{host}", "{port}", "{width}", "{height}", "{steps}", "{cfg}", "{sampler}", "{extra}")
    lowered = raw.lower()
    preset_bleed = any(x in lowered for x in ("openrouter + local", "lm studio + local", "z-image/sd.cppethod"))
    broken_sampling = "--sampling-method" not in raw and "sampling-m" in raw
    missing_required = any(tok not in raw for tok in required)
    if preset_bleed or broken_sampling or missing_required:
        reasons = []
        if preset_bleed: reasons.append("pipeline preset text leaked into command")
        if broken_sampling: reasons.append("broken --sampling-method flag")
        if missing_required: reasons.append("missing placeholders")
        return SDCPP_DEFAULT_COMMAND_TEMPLATE, True, "; ".join(reasons)
    return raw, False, ""


DEFAULTS = {
    "INFINI_USE_LLM": "1",
    "INFINI_LLM_RUNTIME_AUTHORING": "1",
    "INFINI_LLM_RUNTIME_PLAN_REQUIRED": "1",
    "INFINI_LLM_RUNTIME_STRICT_VALIDATION": "1",
    "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK": "0",
    "INFINI_GUI_PIPELINE_PRESET": "Локалка: LM Studio + local Z-Image/sd.cpp",
    "INFINI_LLM_PROVIDER": "local",
    "INFINI_LMSTUDIO_URL": "http://127.0.0.1:1234",
    "INFINI_LMSTUDIO_MODEL": "auto",
    "INFINI_OPENROUTER_API_KEY": "",
    "INFINI_OPENROUTER_MODEL": "auto",
    "INFINI_OPENROUTER_HTTP_REFERER": "https://github.com/InfiniCrafterLocal",
    "INFINI_OPENROUTER_APP_TITLE": "InfiniCrafterLocal",
    "INFINI_OPENAI_COMPAT_BASE_URL": "",
    "INFINI_OPENAI_COMPAT_API_KEY": "",
    "INFINI_OPENAI_COMPAT_MODEL": "auto",
    "INFINI_LLM_FALLBACK_PROVIDER": "",
    "INFINI_LLM_FALLBACK_MODEL": "",
    "INFINI_LLM_FALLBACK_BASE_URL": "",
    "INFINI_LLM_FALLBACK_API_KEY": "",
    "INFINI_LLM_FALLBACK_NETWORK_FAILS": "2",
    "INFINI_LLM_RESPONSE_FORMAT": "auto",
    "INFINI_LLM_TEMPERATURE": "0.38",
    "INFINI_VISUAL_DIRECTOR_TEMPERATURE": "0.42",
    "INFINI_LLM_MAX_TOKENS": "9000",
    "INFINI_LLM_REASONING_MODE": "off",
    "INFINI_LLM_REASONING_MAX_TOKENS": "1500",
    "INFINI_LLM_REASONING_EXCLUDE": "1",
    "INFINI_LLM_LOCAL_REASONING_PROMPT": "1",
    "INFINI_IMAGE_BACKEND": "sdcpp",
    "INFINI_SDCPP_SERVER_EXE": r"C:\Games\sdcpp\sd-server.exe",
    "INFINI_SDCPP_MODEL": r"C:\Games\sdcpp\models\z-image-turbo-Q6_K.gguf",
    "INFINI_SDCPP_VAE": r"C:\Games\sdcpp\models\ae.safetensors",
    "INFINI_SDCPP_LLM": r"C:\Games\sdcpp\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    "INFINI_SDCPP_LORA_DIR": "",
    "INFINI_SDCPP_LORA_FILE": "",
    "INFINI_SDCPP_LORA_WEIGHT": "0.65",
    "INFINI_SDCPP_LORA_PROMPT_TAGS": "",
    "INFINI_SDCPP_SERVER_URL": "http://127.0.0.1:7861",
    "INFINI_SDCPP_SERVER_AUTOSTART": "1",
    "INFINI_SDCPP_SERVER_COMMAND_MODE": "safe_args",
    "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE": SDCPP_DEFAULT_COMMAND_TEMPLATE,
    "INFINI_SDCPP_SERVER_EXTRA_ARGS": "",
    "INFINI_SDCPP_SERVER_SHOW_CONSOLE": "1" if os.name == "nt" else "0",
    "INFINI_SDCPP_SERVER_LOG_FILE": str(ROOT / "cache" / "sdcpp_server.log"),
    "INFINI_SDCPP_WIDTH": "512",
    "INFINI_SDCPP_HEIGHT": "512",
    "INFINI_SDCPP_STEPS": "8",
    "INFINI_SDCPP_CFG": "1.0",
    "INFINI_SDCPP_SAMPLER": "euler",
    "INFINI_SDCPP_SEED": "-1",
    "INFINI_ZIMAGE_PROMPT_CONTRACT": "auto",
    "INFINI_ZIMAGE_POSITIVE_ONLY": "1",
    "INFINI_IMAGE_API_BASE_URL": "https://api.openai.com/v1",
    "INFINI_IMAGE_API_KEY": "",
    "INFINI_IMAGE_API_MODEL": "gpt-image-1",
    "INFINI_IMAGE_API_PATH": "/images/generations",
    "INFINI_IMAGE_API_SIZE": "512x512",
    "INFINI_IMAGE_API_TIMEOUT": "180",
    "INFINI_A1111_URL": "http://127.0.0.1:7860",
    "INFINI_COMFYUI_URL": "http://127.0.0.1:8188",
    "INFINI_VISUAL_ASSET_MODE": "full",
    "INFINI_VISUAL_DIRECTOR_LLM": "1",
    "INFINI_VISUAL_DIRECTOR_MAX_TOKENS": "",
    "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES": "1",
    "INFINI_VISUAL_GENERATE_IMPACT_IMAGES": "0",
    "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES": "0",
    "INFINI_VFX_LLM_DIRECTOR": "1",
    "INFINI_REMOVE_BG": "1",
    "INFINI_BG_REMOVE_MODE": "sprite_keyer",
    "INFINI_BG_COLOR": "magenta",
    "INFINI_CHROMA_TOLERANCE": "34",
    "INFINI_ALPHA_THRESHOLD": "28",
    "INFINI_SPRITE_KEYER_SPILL_RADIUS": "3",
    "INFINI_SPRITE_KEYER_RESIDUE_STEPS": "8",
    "INFINI_SPRITE_RETRIES": "1",
    "INFINI_SAVE_SPRITE_STAGES": "0",
    "INFINI_PIXEL_POSTERIZE": "1",
    "INFINI_MAX_COLORS": "32",
    "INFINI_SPRITE_PROCESSING_PROFILE": "master_soft",
    "INFINI_SPRITE_MASTER_CANVAS": "256",
    "INFINI_SPRITE_DOWNSCALE_FILTER": "box",
    "INFINI_SPRITE_CHROMA_DEFRINGE": "1",
    "INFINI_SPRITE_PREMULTIPLIED_RESIZE": "1",
    "INFINI_VISUAL_STRICT_AI_AUTHORSHIP": "1",
    "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK": "0",
    "INFINI_HOST": "127.0.0.1",
    "INFINI_PORT": "5055",
    "INFINI_ASSET_PUBLIC_BASE_URL": "",
    "INFINI_TERRARIA_PORT": "7777",
    "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS": "240",
    "INFINI_CRAFT_HTTP_ATTEMPTS": "2",
    "INFINI_TRACE_PROMPTS": "1",
    "INFINI_TRACE_MAX_PROMPT_CHARS": "18000",
    "INFINI_TRACE_EVENTS_TAIL": "120",
}

PRESETS = {
    "Локалка: LM Studio + local Z-Image/sd.cpp": {
        "INFINI_LLM_PROVIDER": "local",
        "INFINI_IMAGE_BACKEND": "sdcpp",
        "INFINI_SDCPP_SERVER_AUTOSTART": "1",
        "INFINI_SDCPP_SERVER_COMMAND_MODE": "safe_args",
        "INFINI_SDCPP_SERVER_EXTRA_ARGS": SDCPP_EXTRA_PROFILES["zimage_amd_safe"],
        "INFINI_SDCPP_STEPS": "8",
        "INFINI_SDCPP_CFG": "1.0",
        "INFINI_SDCPP_SAMPLER": "euler",
    },
    "OpenRouter + local Z-Image/sd.cpp": {
        "INFINI_LLM_PROVIDER": "openrouter",
        "INFINI_IMAGE_BACKEND": "sdcpp",
        "INFINI_SDCPP_SERVER_AUTOSTART": "1",
        "INFINI_SDCPP_SERVER_COMMAND_MODE": "safe_args",
        "INFINI_SDCPP_SERVER_EXTRA_ARGS": SDCPP_EXTRA_PROFILES["zimage_amd_safe"],
        "INFINI_SDCPP_STEPS": "8",
        "INFINI_SDCPP_CFG": "1.0",
        "INFINI_SDCPP_SAMPLER": "euler",
    },
    "OpenRouter + Image API": {
        "INFINI_LLM_PROVIDER": "openrouter",
        "INFINI_IMAGE_BACKEND": "image_api",
        "INFINI_SDCPP_SERVER_AUTOSTART": "0",
    },
    "API LLM only: без картинок": {
        "INFINI_LLM_PROVIDER": "openrouter",
        "INFINI_IMAGE_BACKEND": "off",
        "INFINI_SDCPP_SERVER_AUTOSTART": "0",
    },
}

# Radmin/LAN is intentionally NOT a pipeline preset. It is a network overlay that can be
# applied on top of any LLM/image combination above.


PRESET_HELP = {
    "Локалка: LM Studio + local Z-Image/sd.cpp": "LLM-контракт пишет локальная модель через LM Studio/OpenAI-compatible API. PNG рисует локальный Z-Image через stable-diffusion.cpp. Это основной офлайн-пайплайн.",
    "OpenRouter + local Z-Image/sd.cpp": "Контракт предмета пишет модель с OpenRouter, а картинки всё равно рисуются локально через Z-Image/sd.cpp. Хороший режим, когда локальная LLM тупит, но VRAM хочется оставить под image gen.",
    "OpenRouter + Image API": "И контракт, и изображения уходят во внешние API. Локальный sd.cpp не нужен и его поля в GUI будут неактивны.",
    "API LLM only: без картинок": "LLM пишет только JSON/механику. Генерация PNG выключена; визуальные и sprite-postprocess поля будут неактивны, потому что обрабатывать нечего.",
}

FIELD_HELP = {
    "INFINI_HOST": "На каком интерфейсе слушает server.py. 127.0.0.1 — только этот ПК; 0.0.0.0 — принимать подключения из LAN/Radmin.",
    "INFINI_PORT": "Порт локального генератора. tModLoader-клиент должен ходить именно сюда.",
    "INFINI_ASSET_PUBLIC_BASE_URL": "Публичный адрес, по которому другие игроки смогут скачать готовые PNG/JSON ассеты с host-ПК. Для Radmin обычно http://26.x.x.x:5055.",
    "INFINI_TERRARIA_PORT": "Порт Terraria/tModLoader сервера для подсказки друзьям. По умолчанию Host & Play/server используют 7777, если ты не менял порт.",
    "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS": "Сколько tModLoader ждёт один HTTP-запрос крафта, прежде чем считать попытку зависшей.",
    "INFINI_CRAFT_HTTP_ATTEMPTS": "Сколько попыток клиент сделает при таймауте/сетевом сбое.",
    "INFINI_TRACE_PROMPTS": "Сохраняет промпты, ответы и шаги pipeline в cache/*.ndjson. Полезно для отладки, но может хранить длинные запросы.",
    "INFINI_TRACE_MAX_PROMPT_CHARS": "Максимум символов промпта/ответа в trace, чтобы лог не разрастался бесконечно.",
    "INFINI_TRACE_EVENTS_TAIL": "Сколько последних событий показывать во вкладке Trace.",
    "INFINI_GUI_PIPELINE_PRESET": "Последний применённый pipeline preset. GUI хранит его в config.env, чтобы после перезапуска открывать тот же режим, а не первый пункт списка.",
    "INFINI_SAVE_SPRITE_STAGES": "Сохранять промежуточные PNG-этапы спрайт-пайплайна (raw, bg_removed, master, final bake) в cache/sprites. Нужен для отладки мастер-канваса и обрезки.",
    "INFINI_CHROMA_TOLERANCE": "Допуск для удаления chroma-key фона. Больше = агрессивнее к магенте, но выше риск задеть полезные edge-пиксели. Обычно 30-40.",
    "INFINI_ALPHA_THRESHOLD": "Порог альфы после вырезания фона. Больше = жестче обрезает полупрозрачные края. Обычно 24-32.",

    "INFINI_LLM_PROVIDER": "Кто пишет JSON-контракт предмета: локальная модель, OpenRouter или другой OpenAI-compatible API.",
    "INFINI_LMSTUDIO_URL": "Адрес локального OpenAI-compatible сервера LM Studio/Ollama. Активен только при LLM provider = local.",
    "INFINI_LMSTUDIO_MODEL": "Имя локальной модели. auto обычно достаточно, если endpoint сам выбирает загруженную модель.",
    "INFINI_OPENROUTER_API_KEY": "Ключ OpenRouter. Активен только при LLM provider = openrouter.",
    "INFINI_OPENROUTER_MODEL": "Slug модели OpenRouter. auto оставляет выбор серверной логике/дефолту.",
    "INFINI_OPENROUTER_HTTP_REFERER": "HTTP-Referer для OpenRouter статистики/идентификации приложения.",
    "INFINI_OPENROUTER_APP_TITLE": "Название приложения для OpenRouter.",
    "INFINI_OPENAI_COMPAT_BASE_URL": "Base URL любого другого OpenAI-compatible API. Активен только при provider = openai_compat.",
    "INFINI_OPENAI_COMPAT_API_KEY": "Ключ стороннего OpenAI-compatible API.",
    "INFINI_OPENAI_COMPAT_MODEL": "Имя/slug модели стороннего OpenAI-compatible API.",
    "INFINI_LLM_FALLBACK_PROVIDER": "Опциональный fallback provider. Пусто = использовать тот же провайдер, но другую модель. Полезно, если хочешь primary OpenRouter, а fallback — local/compat.",
    "INFINI_LLM_FALLBACK_MODEL": "Опциональная запасная модель. Если основная модель умерла по бабкам/quota/auth или два раза подряд не достучалась по сети, сервер переключится на эту модель.",
    "INFINI_LLM_FALLBACK_BASE_URL": "Опциональный base URL fallback-маршрута. Пусто = брать URL выбранного fallback provider из основных полей.",
    "INFINI_LLM_FALLBACK_API_KEY": "Опциональный отдельный ключ для fallback-маршрута. Пусто = использовать основной ключ соответствующего provider.",
    "INFINI_LLM_FALLBACK_NETWORK_FAILS": "Сколько сетевых/timeout сбоев подряд терпеть на primary, прежде чем переключаться на fallback. По умолчанию 2.",
    "INFINI_LLM_RESPONSE_FORMAT": "Как просить JSON у модели. auto — безопасный дефолт; strict schema может ломаться на провайдерах без поддержки response_format.",
    "INFINI_LLM_TEMPERATURE": "Температура основного LLM planner: выше = больше вариативности/риска, ниже = стабильнее/однообразнее. Это не Z-Image; картинки регулируются seed/CFG/steps/flow-shift.",
    "INFINI_VISUAL_DIRECTOR_TEMPERATURE": "Температура LLM Visual Director, который пишет visual kit/prompt-ы для Z-Image. Выше = больше художественной вариативности, но больше риск ухода от предмета.",
    "INFINI_LLM_MAX_TOKENS": "Лимит ответа LLM. Для reasoning-моделей нужен запас, иначе модель может не успеть вернуть JSON.",
    "INFINI_LLM_REASONING_MODE": "Управляет reasoning/thinking API у OpenRouter или prompt-only приватной проверкой для локалок.",
    "INFINI_LLM_REASONING_MAX_TOKENS": "Бюджет thinking-токенов. Работает только когда reasoning mode = tokens и провайдер поддерживает reasoning object.",
    "INFINI_LLM_REASONING_EXCLUDE": "Просит провайдера не возвращать reasoning в content. Нужен только для API reasoning, чтобы не ломать JSON-парсер.",
    "INFINI_LLM_LOCAL_REASONING_PROMPT": "Разрешает локальной модели короткую приватную самопроверку через system prompt. Это не API thinking и не вывод chain-of-thought.",

    "INFINI_IMAGE_BACKEND": "Кто рисует PNG: локальный sd.cpp/Z-Image, внешний Image API, A1111, ComfyUI или выключено.",
    "INFINI_SDCPP_SERVER_EXE": "Путь до sd-server.exe из stable-diffusion.cpp. Активен только при image backend = sdcpp.",
    "INFINI_SDCPP_MODEL": "Главная diffusion-модель Z-Image *.gguf.",
    "INFINI_SDCPP_VAE": "AE/VAE файл для Z-Image, обычно ae.safetensors. GUI сам добавит --vae.",
    "INFINI_SDCPP_LLM": "Qwen/LLM файл для Z-Image prompt processing. GUI сам добавит --llm.",
    "INFINI_SDCPP_LORA_DIR": "Скрытое/backcompat поле. В GUI больше не редактируется: папка для --lora-model-dir автоматически выводится из выбранного LoRA file.",
    "INFINI_SDCPP_LORA_FILE": "Конкретный файл LoRA (*.safetensors/*.ckpt/*.pt/*.pth). GUI сам возьмёт родительскую папку для --lora-model-dir и имя файла для <lora:name:weight>.",
    "INFINI_SDCPP_LORA_WEIGHT": "Вес LoRA для кнопки Use selected LoRA. Обычно 0.35-0.8; для sprite style лучше начинать с 0.45-0.65.",
    "INFINI_SDCPP_LORA_PROMPT_TAGS": "Активные LoRA-теги, которые будут добавляться к каждому image prompt. Обычно заполняются кнопкой Use selected LoRA; руками нужно только для нескольких LoRA.",
    "INFINI_SDCPP_SERVER_URL": "URL уже запущенного sd.cpp server. Если autostart=1, GUI/server.py стартует его сам.",
    "INFINI_SDCPP_SERVER_AUTOSTART": "1 — server.py сам поднимет sd.cpp перед генерацией. 0 — считаем, что sd.cpp уже запущен вручную.",
    "INFINI_SDCPP_SERVER_COMMAND_MODE": "safe_args = GUI/server.py собирают argv сами и не дают pipeline preset сломать флаги. template = использовать ручной шаблон команды для нестандартных форков sd.cpp.",
    "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE": "Шаблон команды запуска sd.cpp. В safe_args режиме хранится как reference/fallback; реально используется только command mode = template.",
    "INFINI_SDCPP_SERVER_EXTRA_ARGS": "Только дополнительные флаги sd.cpp: -v, --backend/--params-backend, --offload-to-cpu, cache и т.п. VAE/Qwen лучше задавать отдельными полями.",
    "INFINI_SDCPP_SERVER_SHOW_CONSOLE": "1 — открыть видимое окно sd-server.exe на Windows; 0 — писать stdout/stderr в лог.",
    "INFINI_SDCPP_SERVER_LOG_FILE": "Куда писать лог sd.cpp, если консоль выключена.",
    "INFINI_SDCPP_WIDTH": "Ширина сырого image gen. Для Terraria-иконок обычно 512 достаточно.",
    "INFINI_SDCPP_HEIGHT": "Высота сырого image gen. Обычно квадрат 512x512.",
    "INFINI_SDCPP_STEPS": "Количество шагов генерации. У turbo-моделей обычно мало шагов: 6–12.",
    "INFINI_SDCPP_CFG": "CFG scale. Для Z-Image turbo часто около 1.0.",
    "INFINI_SDCPP_SAMPLER": "Сэмплер sd.cpp. Для текущего Z-Image дефолт euler.",
    "INFINI_SDCPP_SEED": "Seed для sd.cpp. -1 = случайный seed на каждую картинку; положительное число = воспроизводимость для дебага.",
    "INFINI_ZIMAGE_PROMPT_CONTRACT": "auto = включать Z-Image prompt contract при Z-Image модели; 1 = force; 0 = отключить. Обычно auto.",
    "INFINI_ZIMAGE_POSITIVE_ONLY": "1 = для Z-Image держать negative_prompt пустым и всё упаковывать в positive prompt. Обычно включено.",
    "INFINI_IMAGE_API_BASE_URL": "Base URL внешнего Image API. Активно только при image backend = image_api.",
    "INFINI_IMAGE_API_KEY": "Ключ внешнего Image API.",
    "INFINI_IMAGE_API_MODEL": "Модель внешнего Image API.",
    "INFINI_IMAGE_API_PATH": "Путь endpoint генерации изображений, обычно /images/generations.",
    "INFINI_IMAGE_API_SIZE": "Размер сырой картинки от внешнего API до sprite postprocess.",
    "INFINI_IMAGE_API_TIMEOUT": "Сколько ждать внешний Image API.",
    "INFINI_A1111_URL": "URL Automatic1111. Активен только при image backend = a1111.",
    "INFINI_COMFYUI_URL": "URL ComfyUI. Активен только при image backend = comfyui.",

    "INFINI_VISUAL_ASSET_MODE": "Сколько визуальных ассетов генерировать: полный набор, только projectile или вообще отключить визуал.",
    "INFINI_VISUAL_DIRECTOR_LLM": "Разрешает LLM сформировать visual kit/направление для PNG, вместо голой генерации по имени.",
    "INFINI_VISUAL_DIRECTOR_MAX_TOKENS": "Лимит output tokens для шага Visual Director (LLM, который пишет visual kit/prompt'ы для Z-Image). Пусто = наследовать общий Max answer tokens.",
    "INFINI_SPRITE_MASTER_CANVAS": "Промежуточный большой RGBA-canvas (обычно 256), на который спрайт сначала нормализуется после вырезания фона, а уже потом печётся в 32/48/64. Это нужно, чтобы high-res fake pixel-art не деградировал от прямого 512→32 resize.",
    "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES": "Разрешить модели отдельный projectile PNG. Флаг не принуждает генерацию без authored baked_sprite.",
    "INFINI_VISUAL_GENERATE_IMPACT_IMAGES": "Разрешить модели отдельный impact PNG. Обычные удары рисуются VFX/Dust без PNG.",
    "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES": "Разрешить модели отдельные child/field PNG. Искры/поля по умолчанию идут через VFX, не через force-картинки.",
    "INFINI_VFX_LLM_DIRECTOR": "Разрешает LLM описывать VFX-слоты/намерение, но код всё равно валидирует контракт.",
    "INFINI_REMOVE_BG": "Удалять фон у сырой картинки перед запеканием sprite PNG.",
    "INFINI_BG_REMOVE_MODE": "Метод удаления фона. Оставлен только sprite_keyer — рабочий протокол для Terraria/fake pixel-art.",
    "INFINI_BG_COLOR": "Ожидаемый chroma-key/фон. Для Z-Image пайплайна обычно magenta.",
    "INFINI_SPRITE_RETRIES": "Сколько раз ретраить image gen, если техническая валидация PNG не прошла.",
    "INFINI_SPRITE_PROCESSING_PROFILE": "Профиль запекания PNG. Оставлены только: master_soft (новый дефолт), pixel_strict и legacy_nearest.",
    "INFINI_SPRITE_MASTER_CANVAS": "Промежуточный RGBA canvas перед финальным 32/48/64. Используется master-first профилями.",
    "INFINI_SPRITE_DOWNSCALE_FILTER": "Фильтр финального downscale. Игнорируется в pixel_strict/legacy_nearest, потому что там принудительный nearest.",
    "INFINI_SPRITE_PREMULTIPLIED_RESIZE": "Premultiplied RGBA resize, чтобы прозрачный magenta не подтекал в края. Не работает при nearest.",
    "INFINI_SPRITE_CHROMA_DEFRINGE": "Консервативно удаляет magenta/key-остатки на краях альфы.",
    "INFINI_PIXEL_POSTERIZE": "Сжимает видимую часть sprite в ограниченную палитру после resize.",
    "INFINI_MAX_COLORS": "Максимум цветов при posterize. Активно только если Posterize=1.",
    "INFINI_VISUAL_STRICT_AI_AUTHORSHIP": "1 — код не рисует за нейронку, только чистит/валидирует/ретраит. Это основной режим авторства модели.",
    "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK": "Разрешает процедурный запасной PNG, если image gen умер. Должен быть выключен при strict AI authorship.",
}

OPTION_HELP = {
    "INFINI_LLM_PROVIDER": {
        "local": "Локальная LLM через LM Studio/Ollama/OpenAI-compatible endpoint. Активны LM Studio URL/model, OpenRouter/Compat поля блокируются.",
        "openrouter": "LLM-контракт пишет модель с OpenRouter. Активны OpenRouter key/model/referer/title, локальные/compat поля блокируются.",
        "openai_compat": "Любой другой OpenAI-compatible API. Активны compat base URL/key/model.",
    },
    "INFINI_LLM_RESPONSE_FORMAT": {
        "auto": "Дефолт: сервер сам выбирает безопасный формат под провайдера/модель.",
        "json_schema": "Просить строгую JSON schema. Хорошо для совместимых API, но некоторые локалки/провайдеры падают.",
        "json_object": "Просить JSON object без полной schema. Мягче, чем json_schema.",
        "off": "Не отправлять response_format; остаётся только prompt-инструкция вернуть JSON.",
    },
    "INFINI_LLM_REASONING_MODE": {
        "off": "Reasoning выключен. Самый совместимый режим.",
        "auto": "Для OpenRouter отправляет enabled reasoning; для local не шлёт API-поле.",
        "none": "Просит effort=none у reasoning API, если провайдер поддерживает.",
        "minimal": "Минимальный reasoning effort для поддерживаемых API.",
        "low": "Низкий reasoning effort.",
        "medium": "Средний reasoning effort; дороже по токенам, но может лучше держать контракт.",
        "high": "Высокий reasoning effort; может съесть бюджет ответа.",
        "xhigh": "Максимальный effort у провайдеров, где он есть. Риск не успеть вернуть JSON при малом max tokens.",
        "tokens": "Задать отдельный бюджет thinking через Reasoning token budget.",
        "prompt_light": "Не API reasoning: короткая приватная самопроверка в system prompt. Полезно локалкам.",
        "prompt_strong": "Не API reasoning: более сильная приватная проверка в prompt. Может слегка удлинить ответ локалки.",
    },
    "INFINI_IMAGE_BACKEND": {
        "sdcpp": "Локальный stable-diffusion.cpp/Z-Image. Активируются sd.cpp пути, размеры, steps/cfg/sampler и debug-кнопки.",
        "image_api": "Внешний OpenAI-compatible Image API. sd.cpp поля блокируются.",
        "off": "PNG не генерируются. Визуальные и sprite-processing настройки блокируются, потому что обрабатывать нечего.",
        "comfyui": "ComfyUI endpoint. Активен только URL ComfyUI; sd.cpp/Image API поля блокируются.",
        "a1111": "Automatic1111 endpoint. Активен только A1111 URL; sd.cpp/Image API поля блокируются.",
    },
    "INFINI_SDCPP_SERVER_AUTOSTART": {
        "1": "server.py сам запускает sd-server.exe перед генерацией.",
        "0": "sd.cpp должен быть уже запущен руками или отдельным bat-файлом.",
    },
    "INFINI_SDCPP_SERVER_SHOW_CONSOLE": {
        "1": "Показывать отдельное окно sd-server.exe с живым логом.",
        "0": "Не показывать консоль, писать лог в файл.",
    },
    "INFINI_SDCPP_SERVER_COMMAND_MODE": {
        "safe_args": "Рекомендуется: GUI/server.py собирает argv напрямую без shell-template, поэтому пресеты не могут испортить флаги.",
        "template": "Ручной шаблон команды. Использовать только для нестандартного sd.cpp/launcher.",
    },
    "INFINI_ZIMAGE_PROMPT_CONTRACT": {
        "auto": "Рекомендуется: включать Z-Image contract только когда backend похож на Z-Image.",
        "1": "Принудительно включить Z-Image prompt contract.",
        "0": "Отключить contract для нестандартного backend/эксперимента.",
    },
    "INFINI_ZIMAGE_POSITIVE_ONLY": {
        "1": "Рекомендуется для Z-Image Turbo: negative_prompt пустой, все техусловия в positive prompt.",
        "0": "Передавать negative_prompt как обычному SD backend'у.",
    },
    "INFINI_IMAGE_API_SIZE": {
        "512x512": "Быстро и достаточно для Terraria-иконок; потом всё равно запекается в 32/48/64.",
        "768x768": "Больше деталей и дороже/медленнее. Может помочь сложным силуэтам.",
        "1024x1024": "Максимум деталей, но тяжелее и не всегда лучше для маленькой иконки.",
    },
    "INFINI_VISUAL_ASSET_MODE": {
        "full": "Полный визуальный пакет: item + projectile/impact/child/field там, где они нужны.",
        "projectile": "Урезанный режим: item/projectile, без impact и child/field ассетов.",
        "off": "Визуальный asset pipeline выключен.",
    },
    "INFINI_BG_REMOVE_MODE": {
        "sprite_keyer": "Единственный рабочий режим удаления фона: Photoshop-like selection/keying под Terraria/fake pixel-art.",
    },
    "INFINI_BG_COLOR": {
        "magenta": "Классический #ff00ff chroma-key. Лучший дефолт для Z-Image sprite prompt.",
        "transparent": "Ожидать уже прозрачный PNG от backend.",
        "white": "Белый фон; риск снести светлые детали предмета.",
        "black": "Чёрный фон; риск снести тёмные детали предмета.",
    },
    "INFINI_SPRITE_PROCESSING_PROFILE": {
        "master_soft": "Новый дефолт: full-res cleanup → master canvas → мягкий BOX/Lanczos/Bicubic bake. Лучший для Z-Image/fake pixel-art.",
        "pixel_strict": "Master-first, но финальный resize принудительно NEAREST. Жёстче пиксели, хуже для шумного fake pixel-art.",
        "legacy_nearest": "Старый откат: прямой fit_to_canvas nearest без master-first bake. Нужен для сравнения/аварийного rollback.",
    },
    "INFINI_SPRITE_DOWNSCALE_FILTER": {
        "box": "Дефолт для fake pixel-art: усредняет high-res блоки и меньше ловит случайный шум.",
        "lanczos": "Более резкий качественный downscale, может давать ореолы на мелкой 32x32 иконке.",
        "bicubic": "Компромисс между box и lanczos.",
        "nearest": "Жёсткий пиксельный resize. В pixel_strict/legacy используется принудительно.",
    },
    "INFINI_PIXEL_POSTERIZE": {
        "1": "После resize ужать видимую часть в ограниченную палитру.",
        "0": "Оставить цвета как есть после resize.",
    },
    "INFINI_VISUAL_STRICT_AI_AUTHORSHIP": {
        "1": "Код не придумывает арт сам. Только техническая очистка, нормализация, валидация и retry.",
        "0": "Разрешить менее строгий режим; тогда можно включить procedural fallback.",
    },
    "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK": {
        "0": "Не подменять art генератор процедурной заглушкой. Рекомендуется для авторства ИИ.",
        "1": "Разрешить процедурный emergency PNG при провале image backend. Блокируется при strict AI authorship=1.",
    },
}

for _bool_key in [
    "INFINI_VISUAL_DIRECTOR_LLM",
    "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES",
    "INFINI_VISUAL_GENERATE_IMPACT_IMAGES",
    "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES",
    "INFINI_VFX_LLM_DIRECTOR",
    "INFINI_REMOVE_BG",
    "INFINI_SPRITE_PREMULTIPLIED_RESIZE",
    "INFINI_SPRITE_CHROMA_DEFRINGE",
    "INFINI_LLM_REASONING_EXCLUDE",
    "INFINI_LLM_LOCAL_REASONING_PROMPT",
    "INFINI_TRACE_PROMPTS",
]:
    OPTION_HELP.setdefault(_bool_key, {"1": "Включено.", "0": "Выключено."})



def parse_env(path: Path) -> dict[str, str]:
    data = dict(DEFAULTS)
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def quote_env_value(value: str) -> str:
    value = str(value or "")
    if any(ch in value for ch in ['#', '\n', '\r']):
        value = value.replace('"', '\\"')
        return f'"{value}"'
    return value


def write_env(path: Path, data: dict[str, str]) -> None:
    lines = [
        "# InfiniCrafterLocal config.env",
        "# Generated by LocalGenerator/settings_gui.py. Можно править руками, но проще через GUI.",
        "",
        "# ===== LLM =====",
    ]
    sections = {
        "INFINI_IMAGE_BACKEND": "# ===== IMAGE =====",
        "INFINI_VISUAL_ASSET_MODE": "# ===== VISUAL / VFX =====",
        "INFINI_HOST": "# ===== SERVER / MULTIPLAYER =====",
        "INFINI_TRACE_PROMPTS": "# ===== TRACE / DEBUG =====",
    }
    for key in FIELD_ORDER:
        if key in sections:
            lines += ["", sections[key]]
        lines.append(f"{key}={quote_env_value(data.get(key, DEFAULTS.get(key, '')))}")
    unknown = {k: v for k, v in data.items() if k not in FIELD_ORDER}
    if unknown:
        lines += ["", "# ===== UNKNOWN / MANUAL KEYS PRESERVED ====="]
        for key in sorted(unknown):
            lines.append(f"{key}={quote_env_value(unknown[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")




class ToolTip:
    """Small delayed tooltip for Tk/ttk widgets.

    `text` may be a string or a callable returning a string, so disabled-state reasons
    and current combobox values stay fresh while the GUI is open.
    """
    def __init__(self, widget, text, *, delay: int = 450, wraplength: int = 520):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Motion>", self._move, add="+")

    def _resolve_text(self) -> str:
        try:
            value = self.text() if callable(self.text) else self.text
        except Exception as e:
            value = f"Tooltip error: {e}"
        return str(value or "").strip()

    def _schedule(self, event=None):
        self._cancel()
        self._last_event = event
        self._after_id = self.widget.after(self.delay, lambda: self._show(self._last_event))

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self, event=None):
        self._cancel()
        text = self._resolve_text()
        if not text:
            return
        self._hide()
        x = (getattr(event, "x_root", 0) or self.widget.winfo_pointerx()) + 16
        y = (getattr(event, "y_root", 0) or self.widget.winfo_pointery()) + 18
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip,
            text=text,
            justify="left",
            wraplength=self.wraplength,
            padx=9,
            pady=7,
            relief="solid",
            borderwidth=1,
            background="#ffffe8",
        )
        label.pack(ipadx=1)
        self._tip = tip

    def _move(self, event=None):
        # Do not chase the cursor every pixel while visible; that makes tooltips jittery.
        if self._tip is None:
            self._last_event = event

    def _hide(self, event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

class ScrollFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.configure(style="Infini.TFrame")
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, background=APP_BG)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = ttk.Frame(self.canvas, style="Infini.TFrame")
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        if self.winfo_toplevel().focus_get() is not None:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class SettingsGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x760")
        self.minsize(900, 660)
        self._configure_theme()
        self.proc: subprocess.Popen | None = None
        self.data = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
        self.vars: dict[str, tk.StringVar] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.field_widgets: dict[str, list[tk.Widget]] = {}
        self.field_base_hints: dict[str, str] = {}
        self.field_hint_labels: dict[str, ttk.Label] = {}
        self.field_disabled_reasons: dict[str, str] = {}
        self.extra_arg_buttons: list[tk.Widget] = []
        self.sdcpp_debug_buttons: list[tk.Widget] = []
        self.show_secrets = tk.BooleanVar(value=False)
        self.radmin_enabled = tk.BooleanVar(value=(self.data.get("INFINI_HOST") == "0.0.0.0" or bool(self.data.get("INFINI_ASSET_PUBLIC_BASE_URL"))))
        self.status_var = tk.StringVar(value="Готово. Выбери pipeline preset, отдельно включи Radmin/LAN если нужен, нажми Save и Start.")
        self._build_ui()
        self._install_global_edit_shortcuts()
        self._refresh_visibility()

    def _var(self, key: str) -> tk.StringVar:
        v = tk.StringVar(value=self.data.get(key, DEFAULTS.get(key, "")))
        self.vars[key] = v
        return v

    @staticmethod
    def _pipeline_preset_from_config(data: dict[str, str]) -> str:
        saved = str(data.get("INFINI_GUI_PIPELINE_PRESET", "") or "").strip()
        if saved in PRESETS:
            return saved
        provider = str(data.get("INFINI_LLM_PROVIDER", "") or "").strip().lower()
        backend = str(data.get("INFINI_IMAGE_BACKEND", "") or "").strip().lower()
        if provider == "local" and backend == "sdcpp":
            return "Локалка: LM Studio + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "sdcpp":
            return "OpenRouter + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "image_api":
            return "OpenRouter + Image API"
        if provider == "openrouter" and backend in {"off", "none", "disabled", "0"}:
            return "API LLM only: без картинок"

        best_name = list(PRESETS)[0]
        best_score = -1
        for name, preset in PRESETS.items():
            score = sum(1 for key, value in preset.items() if str(data.get(key, "")).strip() == str(value).strip())
            if score > best_score:
                best_name, best_score = name, score
        return best_name


    def _attach_static_help(self, widget, text):
        ToolTip(widget, text)
        widget.bind("<Enter>", lambda _e: self.status_var.set(text() if callable(text) else str(text)), add="+")

    def _register_field_widgets(self, key: str, widgets: list[tk.Widget], hint: str | None = None, hint_label: ttk.Label | None = None):
        self.field_widgets.setdefault(key, []).extend([w for w in widgets if w is not None])
        self.field_base_hints[key] = hint or FIELD_HELP.get(key, "")
        if hint_label is not None:
            self.field_hint_labels[key] = hint_label
        for widget in widgets:
            if widget is None:
                continue
            ToolTip(widget, lambda key=key: self._field_help_text(key))
            widget.bind("<Enter>", lambda _e, key=key: self._show_field_help(key), add="+")

    def _field_help_text(self, key: str) -> str:
        parts: list[str] = []
        reason = self.field_disabled_reasons.get(key, "")
        if reason:
            parts.append("Сейчас неактивно: " + reason)
        base = FIELD_HELP.get(key) or self.field_base_hints.get(key, "")
        if base:
            parts.append(base)
        options = OPTION_HELP.get(key) or {}
        if options:
            cur = self.vars.get(key).get().strip() if key in self.vars else ""
            if cur and cur in options:
                parts.append(f"Текущее значение `{cur}`: {options[cur]}")
            rendered = "\n".join(f"• {value}: {desc}" for value, desc in options.items())
            parts.append("Варианты:\n" + rendered)
        return "\n\n".join(parts)

    def _show_field_help(self, key: str):
        text = self._field_help_text(key)
        if text:
            # Status bar is intentionally short; full text is in hover tooltip.
            first = text.split("\n", 1)[0]
            self.status_var.set(first[:220])

    def _preset_help_text(self) -> str:
        name = self.preset_var.get()
        text = PRESET_HELP.get(name, "")
        changes = PRESETS.get(name, {})
        if changes:
            rendered = "\n".join(f"• {k}={v}" for k, v in changes.items())
            return f"{name}\n\n{text}\n\nЧто изменит Apply pipeline:\n{rendered}"
        return text or name

    def _show_preset_help(self):
        self.status_var.set(PRESET_HELP.get(self.preset_var.get(), "Выбран pipeline preset. Нажми Apply pipeline, чтобы применить."))

    def _set_widget_enabled(self, widget, enabled: bool):
        try:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if enabled else "disabled")
                return
            if isinstance(widget, tk.Text):
                widget.configure(state="normal" if enabled else "disabled")
                return
            if isinstance(widget, ttk.Entry) or isinstance(widget, tk.Entry):
                widget.configure(state="normal" if enabled else "disabled")
                return
            if hasattr(widget, "state"):
                widget.state(["!disabled"] if enabled else ["disabled"])
                return
            widget.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _set_widgets_enabled(self, widgets: list[tk.Widget], enabled: bool):
        for widget in widgets:
            self._set_widget_enabled(widget, enabled)

    def _set_field_enabled(self, key: str, enabled: bool, reason: str = ""):
        self.field_disabled_reasons[key] = "" if enabled else reason
        self._set_widgets_enabled(self.field_widgets.get(key, []), enabled)
        hint_label = self.field_hint_labels.get(key)
        if hint_label is not None:
            base = self.field_base_hints.get(key, "")
            if enabled or not reason:
                hint_label.configure(text="   " + base if base else "")
            else:
                suffix = f"Неактивно: {reason}"
                hint_label.configure(text="   " + (base + "  —  " if base else "") + suffix)

    def _configure_theme(self):
        try:
            self.configure(bg=APP_BG)
            style = ttk.Style(self)
            try:
                # "clam" is old, but it allows ttk colors/padding to be predictable.
                # The visible chrome is drawn mostly with tk.Frame/tk.Button helpers below.
                style.theme_use("clam")
            except (AttributeError, RuntimeError, TypeError):
                pass
            style.configure("Infini.TFrame", background=APP_BG)
            style.configure("Toolbar.TFrame", background=CARD_BG)
            style.configure("Card.TFrame", background=CARD_BG, relief="flat", borderwidth=0)
            style.configure("CardInner.TFrame", background=CARD_BG, relief="flat", borderwidth=0)
            style.configure("MutedCard.TFrame", background=CARD_MUTED_BG, relief="flat", borderwidth=0)
            style.configure("Header.TFrame", background=HEADER_BG)
            style.configure("Header.TLabel", background=HEADER_BG, foreground="#f8fafc", font=("Segoe UI", 20, "bold"))
            style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground="#cbd5e1", font=("Segoe UI", 9))
            style.configure("Section.TLabel", background=CARD_BG, foreground=TEXT_FG, font=("Segoe UI", 11, "bold"))
            style.configure("FieldLabel.TLabel", background=CARD_BG, foreground=TEXT_FG, font=("Segoe UI", 9, "bold"))
            style.configure("FieldLabelMuted.TLabel", background=CARD_MUTED_BG, foreground=TEXT_FG, font=("Segoe UI", 9, "bold"))
            style.configure("Hint.TLabel", background=CARD_BG, foreground=MUTED_FG, font=("Segoe UI", 8))
            style.configure("HintMuted.TLabel", background=CARD_MUTED_BG, foreground=MUTED_FG, font=("Segoe UI", 8))
            style.configure("Status.TLabel", background=CARD_BG, foreground=MUTED_FG, padding=(10, 7))
            style.configure("TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 6, 0, 0))
            style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 9, "bold"), background="#eef2f7", foreground="#475569")
            style.map(
                "TNotebook.Tab",
                background=[("selected", CARD_BG), ("active", "#f8fafc")],
                foreground=[("selected", ACCENT_BG), ("active", TEXT_FG)],
            )
            style.configure("Accent.TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
            style.configure("Ghost.TButton", padding=(10, 6), font=("Segoe UI", 9))
            style.configure("TEntry", padding=(7, 5), fieldbackground="#ffffff", bordercolor=BORDER_DARK_FG, lightcolor=BORDER_DARK_FG, darkcolor=BORDER_DARK_FG)
            style.configure("TCombobox", padding=(7, 5), fieldbackground="#ffffff", bordercolor=BORDER_DARK_FG)
        except (AttributeError, RuntimeError, TypeError):
            # Headless/import smoke tests use no-op ttk shims. Styling is best-effort only.
            pass

    @staticmethod
    def _bg_of(parent, fallback: str = APP_BG) -> str:
        return str(getattr(parent, "_infini_bg", fallback) or fallback)

    @staticmethod
    def _as_tk_color_widget(widget, **kwargs):
        try:
            widget.configure(**kwargs)
        except (AttributeError, RuntimeError, TypeError):
            pass
        return widget

    def _modern_button(self, parent, text: str, command, variant: str = "ghost", width: int | None = None):
        """A small tk.Button skin because ttk buttons remain Windows-95-ish on some tML/dev boxes."""
        palette = {
            "primary": (ACCENT_BG, ACCENT_FG, ACCENT_HOVER_BG, ACCENT_BG),
            "success": (SUCCESS_SOFT_BG, SUCCESS_FG, "#bbf7d0", "#86efac"),
            "danger": (DANGER_SOFT_BG, DANGER_FG, "#fecaca", "#fca5a5"),
            "ghost": (CARD_BG, TEXT_FG, "#f8fafc", BORDER_DARK_FG),
            "soft": (ACCENT_SOFT_BG, ACCENT_BG, "#dbeafe", "#bfdbfe"),
            "dark": ("#152542", "#f8fafc", "#1e3a5f", "#334155"),
        }
        bg, fg, hover, border = palette.get(variant, palette["ghost"])
        try:
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                activebackground=hover,
                activeforeground=fg,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=border,
                highlightcolor=border,
                padx=14,
                pady=7,
                width=width or 0,
                font=("Segoe UI", 9, "bold" if variant in {"primary", "soft"} else "normal"),
                cursor="hand2",
            )
            btn.bind("<Enter>", lambda _e, btn=btn, hover=hover: btn.configure(bg=hover), add="+")
            btn.bind("<Leave>", lambda _e, btn=btn, bg=bg: btn.configure(bg=bg), add="+")
            return btn
        except (AttributeError, RuntimeError, TypeError):
            return ttk.Button(parent, text=text, command=command, style="Accent.TButton" if variant == "primary" else "Ghost.TButton")

    def _chip(self, parent, text: str, tone: str = "neutral"):
        colors = {
            "neutral": ("#f1f5f9", "#334155", BORDER_FG),
            "blue": (ACCENT_SOFT_BG, ACCENT_BG, "#bfdbfe"),
            "green": (SUCCESS_SOFT_BG, SUCCESS_FG, "#bbf7d0"),
            "red": (DANGER_SOFT_BG, DANGER_FG, "#fecaca"),
            "amber": (WARNING_SOFT_BG, WARNING_FG, "#fde68a"),
        }
        bg, fg, border = colors.get(tone, colors["neutral"])
        try:
            label = tk.Label(
                parent,
                text=text,
                bg=bg,
                fg=fg,
                padx=10,
                pady=4,
                font=("Segoe UI", 8, "bold"),
                highlightthickness=1,
                highlightbackground=border,
            )
            label._infini_bg = bg
            return label
        except (AttributeError, RuntimeError, TypeError):
            return ttk.Label(parent, text=text)

    def _card(self, parent, title: str | None = None, subtitle: str = "", icon: str = "", status: tuple[str, str] | None = None):
        try:
            outer = tk.Frame(parent, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER_FG, bd=0)
            outer._infini_bg = CARD_BG
            outer.pack(fill="x", padx=10, pady=(8, 10))
            if title:
                head = tk.Frame(outer, bg=CARD_BG, padx=16, pady=12)
                head._infini_bg = CARD_BG
                head.pack(fill="x")
                left = tk.Frame(head, bg=CARD_BG)
                left._infini_bg = CARD_BG
                left.pack(side="left", fill="x", expand=True)
                title_line = tk.Frame(left, bg=CARD_BG)
                title_line._infini_bg = CARD_BG
                title_line.pack(anchor="w", fill="x")
                if icon:
                    tk.Label(title_line, text=icon, bg=CARD_BG, fg=ACCENT_BG, font=("Segoe UI Symbol", 14, "bold")).pack(side="left", padx=(0, 8))
                tk.Label(title_line, text=title, bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 12, "bold")).pack(side="left")
                if subtitle:
                    tk.Label(left, text=subtitle, bg=CARD_BG, fg=MUTED_FG, font=("Segoe UI", 8), anchor="w", justify="left", wraplength=900).pack(anchor="w", pady=(4, 0))
                if status:
                    chip = self._chip(head, status[0], status[1])
                    chip.pack(side="right", padx=(12, 0))
            body = tk.Frame(outer, bg=CARD_BG, padx=4, pady=0)
            body._infini_bg = CARD_BG
            body.pack(fill="x")
            return body
        except (AttributeError, RuntimeError, TypeError):
            frame = ttk.Frame(parent, padding=(10, 8), style="Card.TFrame")
            frame.pack(fill="x", padx=10, pady=(8, 10))
            if title:
                ttk.Label(frame, text=((icon + "  ") if icon else "") + title, style="Section.TLabel").pack(anchor="w")
            return frame

    def _inline_card(self, parent, bg: str = CARD_MUTED_BG):
        try:
            frame = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER_FG, padx=12, pady=10)
            frame._infini_bg = bg
            frame.pack(fill="x", padx=12, pady=6)
            return frame
        except (AttributeError, RuntimeError, TypeError):
            frame = ttk.Frame(parent, padding=(10, 8), style="MutedCard.TFrame")
            frame.pack(fill="x", padx=12, pady=6)
            return frame

    def _info_panel(self, parent, text: str | tk.StringVar, tone: str = "blue"):
        bg = {"blue": ACCENT_SOFT_BG, "green": SUCCESS_SOFT_BG, "amber": WARNING_SOFT_BG, "red": DANGER_SOFT_BG}.get(tone, ACCENT_SOFT_BG)
        fg = {"blue": "#1e3a8a", "green": SUCCESS_FG, "amber": WARNING_FG, "red": DANGER_FG}.get(tone, "#1e3a8a")
        panel = self._inline_card(parent, bg=bg)
        try:
            tk.Label(panel, text="i", bg="#dbeafe" if tone == "blue" else bg, fg=fg, width=2, font=("Segoe UI", 10, "bold"), highlightthickness=1, highlightbackground="#bfdbfe").pack(side="left", padx=(0, 10), anchor="n")
            label_kwargs = dict(bg=bg, fg=fg, font=("Segoe UI", 8), justify="left", wraplength=980, anchor="w")
            if isinstance(text, tk.StringVar):
                lbl = tk.Label(panel, textvariable=text, **label_kwargs)
            else:
                lbl = tk.Label(panel, text=str(text), **label_kwargs)
            lbl.pack(side="left", fill="x", expand=True)
            return lbl
        except (AttributeError, RuntimeError, TypeError):
            if isinstance(text, tk.StringVar):
                return ttk.Label(panel, textvariable=text)
            return ttk.Label(panel, text=str(text))

    def _build_ui(self):
        shell = ttk.Frame(self, padding=(14, 12), style="Infini.TFrame")
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg=HEADER_BG, padx=18, pady=16, highlightthickness=1, highlightbackground="#102344")
        header._infini_bg = HEADER_BG
        header.pack(fill="x", pady=(0, 12))
        brand = tk.Frame(header, bg=HEADER_BG)
        brand._infini_bg = HEADER_BG
        brand.pack(side="left", fill="x", expand=True)
        logo = tk.Label(brand, text="⚡", bg=HEADER_BG, fg="#38bdf8", font=("Segoe UI Symbol", 28, "bold"))
        logo.pack(side="left", padx=(0, 14))
        header_text = tk.Frame(brand, bg=HEADER_BG)
        header_text._infini_bg = HEADER_BG
        header_text.pack(side="left", fill="x", expand=True)
        tk.Label(header_text, text="InfiniCrafterLocal", bg=HEADER_BG, fg="#f8fafc", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(
            header_text,
            text="Локальный генератор предметов: LLM runtime, картинки, Radmin/LAN и debug-trace в одном месте.",
            bg=HEADER_BG,
            fg="#cbd5e1",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        actions = tk.Frame(header, bg=HEADER_BG)
        actions._infini_bg = HEADER_BG
        actions.pack(side="right")
        for text, command, variant in [
            ("💾  Save", self.save, "primary"),
            ("▶  Start", self.start_server, "dark"),
            ("■  Stop", self.stop_server, "danger"),
            ("♥  Health", self.open_health, "success"),
            ("⚙  config.env", self.open_config, "dark"),
        ]:
            btn = self._modern_button(actions, text, command, variant=variant)
            btn.pack(side="left", padx=4)

        preset_bar = tk.Frame(shell, bg=CARD_BG, padx=16, pady=12, highlightthickness=1, highlightbackground=BORDER_FG)
        preset_bar._infini_bg = CARD_BG
        preset_bar.pack(fill="x", pady=(0, 12))
        tk.Label(preset_bar, text="Pipeline preset", bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 10))
        self.preset_var = tk.StringVar(value=self._pipeline_preset_from_config(self.data))
        preset_combo = ttk.Combobox(preset_bar, textvariable=self.preset_var, values=list(PRESETS), state="readonly", width=54)
        preset_combo.pack(side="left", padx=6, ipady=2)
        preset_combo.bind("<<ComboboxSelected>>", lambda _e: self._show_preset_help(), add="+")
        self._attach_static_help(preset_combo, lambda: self._preset_help_text())
        apply_btn = self._modern_button(preset_bar, "＋  Apply pipeline", self.apply_preset, variant="soft")
        apply_btn.pack(side="left", padx=(10, 16))
        self._attach_static_help(apply_btn, "Применить выбранный pipeline preset. После применения GUI заблокирует поля, которые не участвуют в выбранной связке.")
        self._chip(preset_bar, "runtime guarded", "blue").pack(side="right", padx=(8, 0))
        validate_btn = self._modern_button(preset_bar, "📁  Проверить пути", self.validate_paths, variant="ghost")
        validate_btn.pack(side="right", padx=(8, 0))
        self._attach_static_help(validate_btn, "Проверить активные пути/ключи для текущего provider/backend. Неактивные поля не считаются ошибкой.")
        secrets_btn = ttk.Checkbutton(preset_bar, text="Показать ключи", variable=self.show_secrets, command=self._refresh_secret_entries)
        secrets_btn.pack(side="right", padx=8)
        self._attach_static_help(secrets_btn, "Временно показать API keys вместо звёздочек.")

        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(0, 8))
        self.general_tab = ScrollFrame(self.tabs)
        self.llm_tab = ScrollFrame(self.tabs)
        self.image_tab = ScrollFrame(self.tabs)
        self.visual_tab = ScrollFrame(self.tabs)
        self.trace_tab = ttk.Frame(self.tabs, style="Infini.TFrame")
        self.tabs.add(self.general_tab, text="▣  1. Сервер / крафт")
        self.tabs.add(self.llm_tab, text="◉  2. LLM")
        self.tabs.add(self.image_tab, text="▧  3. Картинки")
        self.tabs.add(self.visual_tab, text="✦  4. VFX / качество")
        self.tabs.add(self.trace_tab, text="⌘  5. Trace / pipeline")

        self._build_general(self.general_tab.inner)
        self._build_llm(self.llm_tab.inner)
        self._build_image(self.image_tab.inner)
        self._build_visual(self.visual_tab.inner)
        self._build_trace(self.trace_tab)

        status_bar = tk.Frame(shell, bg=CARD_BG, padx=12, pady=8, highlightthickness=1, highlightbackground=BORDER_FG)
        status_bar._infini_bg = CARD_BG
        status_bar.pack(fill="x")
        tk.Label(status_bar, text="●", bg=CARD_BG, fg=SUCCESS_BG, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(status_bar, text="Готово", bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12))
        tk.Label(status_bar, textvariable=self.status_var, bg=CARD_BG, fg=MUTED_FG, font=("Segoe UI", 9), anchor="w", justify="left").pack(side="left", fill="x", expand=True)

    def row(self, parent, label, key, width=64, secret=False, browse=None, values=None, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(12, 7), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=26, style=label_style)
        label_widget.pack(side="left")
        var = self._var(key)
        if values:
            widget = ttk.Combobox(frame, textvariable=var, values=values, width=width, state="readonly")
            widget.bind("<<ComboboxSelected>>", lambda _e, key=key: (self._refresh_visibility(), self._show_field_help(key)), add="+")
        else:
            widget = ttk.Entry(frame, textvariable=var, width=width, show="*" if secret and not self.show_secrets.get() else "")
            if secret:
                if not hasattr(self, "secret_entries"):
                    self.secret_entries = []
                self.secret_entries.append(widget)
        widget.pack(side="left", fill="x", expand=True, ipady=2)
        self._enable_edit_menu(widget)
        registered_widgets: list[tk.Widget] = [frame, label_widget, widget]
        if browse == "file":
            btn = self._modern_button(frame, "…", lambda: self.browse_file(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "model":
            btn = self._modern_button(frame, "…", lambda: self.browse_model(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "folder":
            btn = self._modern_button(frame, "…", lambda: self.browse_folder(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "lora_file":
            btn = self._modern_button(frame, "…", self.browse_lora_file, variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        hint_label = None
        base_hint = hint or ""
        if base_hint:
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style)
            hint_label.pack(anchor="w", padx=16, pady=(0, 4))
            registered_widgets.append(hint_label)
        self._register_field_widgets(key, registered_widgets, base_hint, hint_label)
        return frame

    def text_row(self, parent, label, key, height=4, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(12, 7), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=26, style=label_style)
        label_widget.pack(side="left", anchor="n")
        text = tk.Text(frame, width=70, height=height, wrap="word", undo=True, relief="solid", bd=1, highlightthickness=1, highlightbackground=BORDER_DARK_FG, font=("Segoe UI", 9))
        text.insert("1.0", self.data.get(key, DEFAULTS.get(key, "")))
        text.pack(side="left", fill="x", expand=True)
        self.text_widgets[key] = text
        self._enable_edit_menu(text)
        hint_label = None
        base_hint = hint or ""
        registered_widgets: list[tk.Widget] = [frame, label_widget, text]
        if base_hint:
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style)
            hint_label.pack(anchor="w", padx=16, pady=(0, 4))
            registered_widgets.append(hint_label)
        self._register_field_widgets(key, registered_widgets, base_hint, hint_label)
        return frame

    def _enable_edit_menu(self, widget):
        # Right-click paste menu + keyboard shortcuts below. Needed because Tk on Windows
        # can miss Ctrl+V when the keyboard layout is Cyrillic.
        widget.bind("<Button-3>", lambda e: self._show_edit_menu(e), add="+")

    def _install_global_edit_shortcuts(self):
        for cls in ("Entry", "TEntry", "Text", "TCombobox"):
            self.bind_class(cls, "<Control-KeyPress>", self._handle_ctrl_edit_shortcut, add="+")
            self.bind_class(cls, "<Control-Shift-KeyPress-Insert>", lambda e: self._edit_event(e.widget, "paste"), add="+")
            self.bind_class(cls, "<Shift-KeyPress-Insert>", lambda e: self._edit_event(e.widget, "paste"), add="+")

    def _handle_ctrl_edit_shortcut(self, event):
        # keycode handles physical Ctrl+C/V/X/A even under RU layout.
        code = getattr(event, "keycode", 0)
        key = (getattr(event, "keysym", "") or "").lower()
        if code == 86 or key in {"v", "cyrillic_em"}:
            return self._edit_event(event.widget, "paste")
        if code == 67 or key in {"c", "cyrillic_es"}:
            return self._edit_event(event.widget, "copy")
        if code == 88 or key in {"x", "cyrillic_che"}:
            return self._edit_event(event.widget, "cut")
        if code == 65 or key in {"a", "cyrillic_ef"}:
            return self._edit_event(event.widget, "select_all")
        return None

    def _edit_event(self, widget, action):
        try:
            if action == "paste":
                widget.event_generate("<<Paste>>")
            elif action == "copy":
                widget.event_generate("<<Copy>>")
            elif action == "cut":
                widget.event_generate("<<Cut>>")
            elif action == "select_all":
                if isinstance(widget, tk.Text):
                    widget.tag_add("sel", "1.0", "end-1c")
                    widget.mark_set("insert", "end-1c")
                else:
                    widget.selection_range(0, "end")
                    widget.icursor("end")
            return "break"
        except Exception:
            return None

    def _show_edit_menu(self, event):
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Cut", command=lambda: self._edit_event(event.widget, "cut"))
        menu.add_command(label="Copy", command=lambda: self._edit_event(event.widget, "copy"))
        menu.add_command(label="Paste", command=lambda: self._edit_event(event.widget, "paste"))
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: self._edit_event(event.widget, "select_all"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _build_general(self, parent):
        server_card = self._card(
            parent,
            "Сервер и поведение крафта",
            "Локальный HTTP helper для tModLoader craft request. 127.0.0.1 — только для себя; 0.0.0.0 — LAN/Radmin.",
            icon="▣",
            status=("Ready", "green"),
        )
        self.row(server_card, "Host", "INFINI_HOST", hint="127.0.0.1 — только ты; 0.0.0.0 — принимать подключения из Radmin/LAN.")
        self.row(server_card, "Port", "INFINI_PORT", width=16)
        self.row(server_card, "Craft HTTP timeout", "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS", width=16, hint="240 секунд: если крафт не готов, tModLoader попробует retry.")
        self.row(server_card, "Craft attempts", "INFINI_CRAFT_HTTP_ATTEMPTS", width=16)

        radmin_status = ("Local only", "green") if not self.radmin_enabled.get() else ("Radmin/LAN", "blue")
        radmin_card = self._card(
            parent,
            "Radmin / LAN — сетевой оверлей, не отдельный AI-режим",
            "Друзьям не нужен LocalGenerator для уже готовых предметов: они получают финальные JSON/PNG ассеты через мод.",
            icon="⌁",
            status=radmin_status,
        )
        net = ttk.Frame(radmin_card, padding=(12, 7), style="CardInner.TFrame")
        net.pack(fill="x")
        ttk.Checkbutton(net, text="Включить Radmin/LAN sharing поверх выбранного pipeline", variable=self.radmin_enabled, command=self.on_radmin_toggle).pack(side="left")
        self._modern_button(net, "Radmin: включить", self.apply_radmin_overlay, variant="soft").pack(side="left", padx=8)
        self._modern_button(net, "Local only", self.apply_local_overlay, variant="ghost").pack(side="left", padx=4)
        self.row(radmin_card, "Public asset URL", "INFINI_ASSET_PUBLIC_BASE_URL", hint="Для Radmin: http://26.x.x.x:5055. Это настройка поверх LMStudio/OpenRouter/Z-Image/Image API.")
        self.row(radmin_card, "Terraria port", "INFINI_TERRARIA_PORT", width=16, hint="Для друзей: Multiplayer → Join via IP → твой Radmin IP → этот порт. Обычно 7777.")
        connect = ttk.Frame(radmin_card, padding=(12, 6), style="CardInner.TFrame")
        connect.pack(fill="x")
        for text, command in [
            ("🌐  Auto Radmin URL", self.autofill_radmin_url),
            ("⧉  Copy friend guide", self.copy_radmin_friend_guide),
            ("↗  Open MP connect page", self.open_mp_connect_page),
        ]:
            self._modern_button(connect, text, command, variant="ghost").pack(side="left", padx=(0, 6))
        self.radmin_info_var = tk.StringVar(value=self._radmin_status_text())
        self._info_panel(radmin_card, self.radmin_info_var, tone="blue")

        trace_card = self._card(
            parent,
            "Trace / black box recorder",
            "Для отладки генерации: prompt trace, compact events tail и расследование проблемных предметов без изменения gameplay.",
            icon="⌘",
            status=("debug", "amber"),
        )
        self.row(trace_card, "Trace prompts", "INFINI_TRACE_PROMPTS", values=["1", "0"], hint="1 = сохранять LLM/image prompts и ответы в cache/prompt_trace.ndjson. Это debug, не gameplay state.")
        self.row(trace_card, "Trace prompt chars", "INFINI_TRACE_MAX_PROMPT_CHARS", width=16)
        self.row(trace_card, "Trace events tail", "INFINI_TRACE_EVENTS_TAIL", width=16)

    def _build_llm(self, parent):
        ttk.Label(parent, text="LLM: кто пишет контракт предмета", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.row(parent, "LLM provider", "INFINI_LLM_PROVIDER", values=["local", "openrouter", "openai_compat"], hint="OpenRouter может писать контракт, а картинки при этом могут идти локально через Z-Image.")
        self.row(parent, "LM Studio URL", "INFINI_LMSTUDIO_URL")
        self.row(parent, "LM Studio model", "INFINI_LMSTUDIO_MODEL")
        self.row(parent, "OpenRouter API key", "INFINI_OPENROUTER_API_KEY", secret=True)
        self.row(parent, "OpenRouter model", "INFINI_OPENROUTER_MODEL", hint="auto или slug модели с OpenRouter.")
        self.row(parent, "OpenRouter referer", "INFINI_OPENROUTER_HTTP_REFERER")
        self.row(parent, "OpenRouter title", "INFINI_OPENROUTER_APP_TITLE")
        self.row(parent, "Compat base URL", "INFINI_OPENAI_COMPAT_BASE_URL")
        self.row(parent, "Compat API key", "INFINI_OPENAI_COMPAT_API_KEY", secret=True)
        self.row(parent, "Compat model", "INFINI_OPENAI_COMPAT_MODEL")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Fallback LLM (optional)", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.row(parent, "Fallback provider", "INFINI_LLM_FALLBACK_PROVIDER", values=["", "local", "openrouter", "openai_compat"], hint="Пусто = использовать тот же провайдер, что и основной. Нужен только если хочешь при падении уйти на другой pipeline.")
        self.row(parent, "Fallback model", "INFINI_LLM_FALLBACK_MODEL", hint="Пусто = fallback выключен. Если основная модель умерла по бабкам/сети, сервер попробует эту модель.")
        self.row(parent, "Fallback base URL", "INFINI_LLM_FALLBACK_BASE_URL", hint="Пусто = взять base URL от fallback provider по умолчанию/из основных полей.")
        self.row(parent, "Fallback API key", "INFINI_LLM_FALLBACK_API_KEY", secret=True, hint="Пусто = использовать основной ключ выбранного fallback provider.")
        self.row(parent, "Fallback after transport fails", "INFINI_LLM_FALLBACK_NETWORK_FAILS", width=16, hint="Сколько сетевых/timeout падений подряд терпеть на основной модели, прежде чем уходить на fallback. По умолчанию 2.")
        self.row(parent, "Response format", "INFINI_LLM_RESPONSE_FORMAT", values=["auto", "json_schema", "json_object", "off"])
        self.row(parent, "Planner temperature", "INFINI_LLM_TEMPERATURE", width=16, hint="LLM JSON planner temperature. 0.30-0.45: стабильнее; 0.55-0.75: разнообразнее, но выше риск мусора в контракте.")
        self.row(parent, "Visual temp", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", width=16, hint="LLM Visual Director temperature for Z-Image prompts. Это не sd.cpp temperature; влияет на prompt/visual kit, а не на sampler.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Output / reasoning", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.row(parent, "Max answer tokens", "INFINI_LLM_MAX_TOKENS", width=16, hint="Для OpenRouter free/cheap reasoning-моделей обычно 9000-12000, иначе reasoning съедает бюджет и JSON не успевает выйти.")
        self.row(parent, "Reasoning mode", "INFINI_LLM_REASONING_MODE", values=["off", "auto", "none", "minimal", "low", "medium", "high", "xhigh", "tokens", "prompt_light", "prompt_strong"], hint="OpenRouter: auto/effort/tokens через reasoning. Local LM Studio: API reasoning не шлём, prompt_* добавляет только внутренний чек без вывода reasoning.")
        self.row(parent, "Reasoning token budget", "INFINI_LLM_REASONING_MAX_TOKENS", width=16, hint="Используется при mode=tokens; OpenRouter мапит это на max_tokens/thinking_budget там, где модель поддерживает.")
        self.row(parent, "Hide reasoning output", "INFINI_LLM_REASONING_EXCLUDE", values=["1", "0"], hint="1 = reasoning используется, но не возвращается в message.content; меньше ломает JSON-парсер.")
        self.row(parent, "Local prompt reasoning", "INFINI_LLM_LOCAL_REASONING_PROMPT", values=["1", "0"], hint="Для локалок без API reasoning: разрешить короткий внутренний чек в system prompt. Цепочку мыслей выводить всё равно запрещено.")

    def _build_zimage_guide(self, parent):
        box = ttk.LabelFrame(parent, text="Z-Image / stable-diffusion.cpp Vulkan — краткий гайд", padding=(10, 8))
        box.pack(fill="x", padx=10, pady=(6, 10))
        guide = (
            "1) Пути: укажи sd-server.exe, z-image-turbo *.gguf, ae.safetensors и Qwen/LLM *.gguf. "
            "VAE/Qwen/LoRA не надо дублировать в extra args — GUI добавит --vae/--llm/--lora-model-dir сам.\n"
            "2) AMD/Vulkan дефолт: нажми профиль AMD safe. Он держит diffusion+VAE на vulkan0, а text encoder/Qwen на CPU — обычно стабильнее для игры.\n"
            "3) Если VRAM душит/игра фризит: AMD low VRAM. Если нужен максимум скорости и хватает VRAM: AMD full GPU.\n"
            "4) LoRA: выбери LoRA file и нажми Browse + use / Use selected LoRA. Отдельного поля folder нет: папка берётся из файла, а в prompt добавляется <lora:name:weight>.\n"
            "5) steps/cfg/sampler для Z-Image Turbo обычно держи примерно 6-12 / 1.0 / euler. Дальше регулируй prompt/postprocess, а не гоняй 30 шагов.\n"
            "6) safe_args лучше template: меньше риска сломать --sampling-method или случайно вставить текст пресета в команду."
        )
        msg = tk.Message(box, text=guide, width=980, foreground="#444")
        msg.pack(fill="x", anchor="w")
        btns = ttk.Frame(box)
        btns.pack(fill="x", pady=(8, 0))
        docs = [
            ("Открыть sd.cpp GitHub", "https://github.com/leejet/stable-diffusion.cpp"),
            ("Backend docs", "https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/backend.md"),
            ("LoRA docs", "https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/lora.md"),
        ]
        for label, url in docs:
            b = ttk.Button(btns, text=label, command=lambda url=url: webbrowser.open(url))
            b.pack(side="left", padx=2)
            self._attach_static_help(b, url)

    def _build_image(self, parent):
        ttk.Label(parent, text="Image backend: кто рисует PNG", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self._build_zimage_guide(parent)
        self.row(parent, "Image backend", "INFINI_IMAGE_BACKEND", values=["sdcpp", "image_api", "off", "comfyui", "a1111"], hint="sdcpp = локальный Z-Image; image_api = внешний API; off = без PNG.")
        self.row(parent, "sd-server.exe", "INFINI_SDCPP_SERVER_EXE", browse="file")
        self.row(parent, "Z-Image model", "INFINI_SDCPP_MODEL", browse="model", hint="Основной z-image-turbo *.gguf, например Q6_K.")
        self.row(parent, "Z-Image VAE / AE", "INFINI_SDCPP_VAE", browse="model", hint="Обычно ae.safetensors. GUI сам добавит --vae, руками в extra args не надо.")
        self.row(parent, "Z-Image Qwen / LLM", "INFINI_SDCPP_LLM", browse="model", hint="Обычно Qwen3-4B-Instruct-...gguf. GUI сам добавит --llm, руками в extra args не надо.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="LoRA для Z-Image/sd.cpp", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        lora_note = ttk.Label(
            parent,
            text="   LoRA folder скрыт: GUI берёт папку из выбранного LoRA file и сам передаёт её как --lora-model-dir.",
            foreground="#666",
        )
        lora_note.pack(anchor="w", padx=10)
        ToolTip(lora_note, "sd.cpp ищет LoRA по имени из <lora:name:weight> внутри папки --lora-model-dir. Поэтому для обычного GUI-сценария достаточно выбрать конкретный LoRA file.")
        self.row(parent, "LoRA file", "INFINI_SDCPP_LORA_FILE", browse="lora_file", hint="Выбери конкретный *.safetensors/*.ckpt/*.pt/*.pth. GUI сам возьмёт родительскую папку для --lora-model-dir и добавит <lora:имя:weight>.")
        self.row(parent, "LoRA weight", "INFINI_SDCPP_LORA_WEIGHT", width=16, hint="Вес для Use selected LoRA. Начинай с 0.45-0.65; выше сильнее навязывает стиль.")
        self.text_row(parent, "LoRA prompt tags", "INFINI_SDCPP_LORA_PROMPT_TAGS", height=2, hint="Активные LoRA-теги, добавляются к каждому image prompt. Можно несколько: <lora:pixelart:0.65> <lora:terraria_items:0.45>. Если пусто, --lora-model-dir не добавляется.")
        self._build_lora_buttons(parent)
        self.row(parent, "sd.cpp URL", "INFINI_SDCPP_SERVER_URL")
        self.row(parent, "sd.cpp autostart", "INFINI_SDCPP_SERVER_AUTOSTART", values=["1", "0"])
        self.row(parent, "sd.cpp command mode", "INFINI_SDCPP_SERVER_COMMAND_MODE", values=["safe_args", "template"], hint="safe_args = рекомендуемый безопасный запуск без shell/template; template нужен только для нестандартного sd.cpp.")
        self.row(parent, "sd.cpp command", "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE")
        self.text_row(parent, "sd.cpp extra args", "INFINI_SDCPP_SERVER_EXTRA_ARGS", height=4, hint="Только доп. флаги: -v, --diffusion-fa, --offload-to-cpu и т.п. VAE/Qwen лучше задавать полями выше.")
        self._build_sdcpp_extra_buttons(parent)
        self.row(parent, "sd.cpp show console", "INFINI_SDCPP_SERVER_SHOW_CONSOLE", values=["1", "0"], hint="1 = открыть отдельное окно sd-server.exe с живым логом. Полезно для отлова Z-Image крашей.")
        self.row(parent, "sd.cpp log file", "INFINI_SDCPP_SERVER_LOG_FILE", browse="file", hint="Если show console=0, stdout/stderr sd-server пишутся сюда. /sdcpp_debug покажет хвост.")
        self._build_sdcpp_debug_buttons(parent)
        self.row(parent, "sd width", "INFINI_SDCPP_WIDTH", width=16)
        self.row(parent, "sd height", "INFINI_SDCPP_HEIGHT", width=16)
        self.row(parent, "sd steps", "INFINI_SDCPP_STEPS", width=16)
        self.row(parent, "sd cfg", "INFINI_SDCPP_CFG", width=16)
        self.row(parent, "sd sampler", "INFINI_SDCPP_SAMPLER", width=24)
        self.row(parent, "sd seed", "INFINI_SDCPP_SEED", width=16, hint="-1 = случайный seed. Положительное число фиксирует результат для отладки.")
        self.row(parent, "Z-Image contract", "INFINI_ZIMAGE_PROMPT_CONTRACT", values=["auto", "1", "0"], hint="Обычно auto. Это внутренний маркер для Z-Image payload/prompt contract.")
        self.row(parent, "Positive-only prompt", "INFINI_ZIMAGE_POSITIVE_ONLY", values=["1", "0"], hint="Для Z-Image Turbo обычно 1: negative_prompt не используется, все запреты/техусловия в positive prompt.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        self.row(parent, "Image API base", "INFINI_IMAGE_API_BASE_URL")
        self.row(parent, "Image API key", "INFINI_IMAGE_API_KEY", secret=True)
        self.row(parent, "Image API model", "INFINI_IMAGE_API_MODEL")
        self.row(parent, "Image API path", "INFINI_IMAGE_API_PATH")
        self.row(parent, "Image API size", "INFINI_IMAGE_API_SIZE", values=["512x512", "768x768", "1024x1024"])
        self.row(parent, "Image API timeout", "INFINI_IMAGE_API_TIMEOUT", width=16)
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        self.row(parent, "A1111 URL", "INFINI_A1111_URL")
        self.row(parent, "ComfyUI URL", "INFINI_COMFYUI_URL")


    def _build_lora_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        ttk.Label(frame, text="", width=30).pack(side="left")
        specs = [
            ("Use selected LoRA", self.use_selected_lora, "Взять LoRA file, вывести папку из файла и добавить тег <lora:filename:weight> в LoRA prompt tags."),
            ("Browse + use", self.browse_and_use_lora_file, "Выбрать LoRA файл и сразу подключить его: hidden --lora-model-dir + prompt tag."),
            ("Clear LoRA", self.clear_lora_settings, "Очистить LoRA file, prompt tags и скрытый LoRA dir."),
        ]
        for text, command, help_text in specs:
            btn = ttk.Button(frame, text=text, command=command)
            btn.pack(side="left", padx=2)
            self.extra_arg_buttons.append(btn)
            self._attach_static_help(btn, help_text)
        ttk.Label(
            frame,
            text="sd.cpp: GUI сам выводит --lora-model-dir из LoRA file; активная LoRA — через <lora:name:weight> в prompt.",
            foreground="#666",
        ).pack(side="left", padx=8)

    def _get_lora_tags_widget(self):
        return self.text_widgets.get("INFINI_SDCPP_LORA_PROMPT_TAGS")

    def _get_lora_tags(self) -> str:
        widget = self._get_lora_tags_widget()
        if widget is not None:
            return widget.get("1.0", "end-1c").strip()
        return self.data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "")

    def _set_lora_tags(self, value: str):
        widget = self._get_lora_tags_widget()
        if widget is not None:
            widget.delete("1.0", "end")
            widget.insert("1.0", value.strip())
        elif "INFINI_SDCPP_LORA_PROMPT_TAGS" in self.vars:
            self.vars["INFINI_SDCPP_LORA_PROMPT_TAGS"].set(value.strip())

    @staticmethod
    def _lora_tag_from_file(path: str, weight: str) -> str:
        raw = str(path or "").strip()
        stem = (PureWindowsPath(raw).stem if "\\" in raw or ":" in raw else Path(raw).stem).strip()
        weight = str(weight or "0.65").strip() or "0.65"
        if not stem:
            return ""
        return f"<lora:{stem}:{weight}>"

    @staticmethod
    def _lora_dir_from_file(path: str) -> str:
        raw = str(path or "").strip()
        if not raw:
            return ""
        parent = PureWindowsPath(raw).parent if "\\" in raw or ":" in raw else Path(raw).parent
        return "" if str(parent) in {"", "."} else str(parent)

    def _append_lora_tag(self, tag: str):
        tag = " ".join(str(tag or "").split()).strip()
        if not tag:
            return
        cur = self._get_lora_tags()
        if tag not in cur:
            cur = (cur.rstrip() + " " + tag).strip()
        self._set_lora_tags(cur)

    def use_selected_lora(self):
        path = self.vars.get("INFINI_SDCPP_LORA_FILE", tk.StringVar(value="")).get().strip()
        if not path:
            messagebox.showwarning("LoRA", "Сначала выбери LoRA file (*.safetensors/*.ckpt).")
            return
        lora_dir = self._lora_dir_from_file(path)
        if "INFINI_SDCPP_LORA_DIR" in self.vars and lora_dir:
            self.vars["INFINI_SDCPP_LORA_DIR"].set(lora_dir)
        p = Path(path)
        weight = self.vars.get("INFINI_SDCPP_LORA_WEIGHT", tk.StringVar(value="0.65")).get().strip() or "0.65"
        tag = self._lora_tag_from_file(path, weight)
        self._append_lora_tag(tag)
        self.data["INFINI_SDCPP_LORA_DIR"] = lora_dir or str(p.parent)
        self.status_var.set(f"LoRA подключена: hidden --lora-model-dir {lora_dir or p.parent} + {tag}")

    def browse_and_use_lora_file(self):
        if self.browse_lora_file():
            self.use_selected_lora()

    def clear_lora_settings(self):
        if "INFINI_SDCPP_LORA_FILE" in self.vars:
            self.vars["INFINI_SDCPP_LORA_FILE"].set("")
        if "INFINI_SDCPP_LORA_DIR" in self.vars:
            self.vars["INFINI_SDCPP_LORA_DIR"].set("")
        self._set_lora_tags("")
        self.data["INFINI_SDCPP_LORA_DIR"] = ""
        self.status_var.set("LoRA file, prompt tags и скрытый LoRA dir очищены.")

    def _build_sdcpp_extra_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        ttk.Label(frame, text="", width=30).pack(side="left")
        ttk.Label(frame, text="Пресеты:", foreground="#666").pack(side="left", padx=(0, 4))
        preset_specs = [
            ("AMD safe", lambda: self.set_extra_profile("zimage_amd_safe"), SDCPP_EXTRA_PROFILE_HELP["zimage_amd_safe"]),
            ("AMD low VRAM", lambda: self.set_extra_profile("zimage_amd_low_vram"), SDCPP_EXTRA_PROFILE_HELP["zimage_amd_low_vram"]),
            ("AMD full GPU", lambda: self.set_extra_profile("zimage_amd_full_gpu"), SDCPP_EXTRA_PROFILE_HELP["zimage_amd_full_gpu"]),
            ("Disk params", lambda: self.set_extra_profile("zimage_amd_disk_params"), SDCPP_EXTRA_PROFILE_HELP["zimage_amd_disk_params"]),
            ("CPU compat", lambda: self.set_extra_profile("zimage_cpu_compat"), SDCPP_EXTRA_PROFILE_HELP["zimage_cpu_compat"]),
            ("Compat offload", lambda: self.set_extra_profile("compat_offload"), SDCPP_EXTRA_PROFILE_HELP["compat_offload"]),
            ("DBCache split", lambda: self.set_extra_profile("vulkan_te_vae_cpu_dbcache"), SDCPP_EXTRA_PROFILE_HELP["vulkan_te_vae_cpu_dbcache"]),
            ("Basic", lambda: self.set_extra_profile("basic_verbose"), SDCPP_EXTRA_PROFILE_HELP["basic_verbose"]),
        ]
        frame2 = ttk.Frame(parent, padding=(10, 2))
        frame2.pack(fill="x")
        ttk.Label(frame2, text="", width=30).pack(side="left")
        ttk.Label(frame2, text="", foreground="#666").pack(side="left", padx=(0, 4))
        for i, (text, command, help_text) in enumerate(preset_specs):
            target = frame if i < 4 else frame2
            btn = ttk.Button(target, text=text, command=command)
            btn.pack(side="left", padx=2)
            self.extra_arg_buttons.append(btn)
            self._attach_static_help(btn, help_text)

        flag_specs = SDCPP_EXTRA_FLAG_SPECS
        for row_index in range(0, len(flag_specs), 6):
            flag_frame = ttk.Frame(parent, padding=(10, 2))
            flag_frame.pack(fill="x")
            ttk.Label(flag_frame, text="", width=30).pack(side="left")
            ttk.Label(flag_frame, text="Добавить флаг:" if row_index == 0 else "", foreground="#666").pack(side="left", padx=(0, 4))
            for text, fragment, help_text in flag_specs[row_index:row_index + 6]:
                btn = ttk.Button(flag_frame, text=text, command=lambda fragment=fragment: self.append_extra_args(fragment))
                btn.pack(side="left", padx=2)
                self.extra_arg_buttons.append(btn)
                self._attach_static_help(btn, help_text)

        frame4 = ttk.Frame(parent, padding=(10, 2))
        frame4.pack(fill="x")
        ttk.Label(frame4, text="", width=30).pack(side="left")
        for text, command, help_text in [
            ("Repair command", self.repair_command_template, "Вернуть safe_args и безопасный reference command template."),
            ("Clear extra", self.clear_extra_args, "Очистить manual extra args. Пути модели/VAE/Qwen/LoRA не трогает."),
        ]:
            btn = ttk.Button(frame4, text=text, command=command)
            btn.pack(side="left", padx=2)
            self.extra_arg_buttons.append(btn)
            self._attach_static_help(btn, help_text)
        self._build_sdcpp_extra_help(parent)

    def _build_sdcpp_extra_help(self, parent):
        help_box = ttk.LabelFrame(parent, text="Что делают пресеты и флаги sd.cpp", padding=(10, 6))
        help_box.pack(fill="x", padx=10, pady=(4, 8))
        profiles = "\n".join("• " + text for text in SDCPP_EXTRA_PROFILE_HELP.values())
        flags = "\n".join(f"• {name}: {desc}" for name, _fragment, desc in SDCPP_EXTRA_FLAG_SPECS)
        msg = tk.Message(
            help_box,
            text=(
                "Пресеты заменяют всю строку sd.cpp extra args. Кнопки флагов только добавляют фрагмент к текущей строке.\n"
                "Одинаковые backend-строки больше не дублируются: если --params-backend не указан, sd.cpp сам держит параметры на backend соответствующего модуля.\n\n"
                "Flow-shift — параметр Flow/DiT расписания, то есть не качество сам по себе, а сдвиг распределения timesteps/noise. 3 = дефолтный/резкий Z-Image вариант; 2 = более мягкий эксперимент.\n\n"
                "Пресеты:\n" + profiles + "\n\n"
                "Флаги:\n" + flags
            ),
            width=980,
            foreground="#444",
        )
        msg.pack(fill="x", anchor="w")

    def _build_sdcpp_debug_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        ttk.Label(frame, text="", width=30).pack(side="left")
        start_btn = ttk.Button(frame, text="Start / check Z-Image", command=self.open_sdcpp_start)
        start_btn.pack(side="left", padx=2)
        debug_btn = ttk.Button(frame, text="Open sd.cpp debug", command=self.open_sdcpp_debug)
        debug_btn.pack(side="left", padx=2)
        doctor_btn = ttk.Button(frame, text="Visual Doctor", command=self.open_visual_doctor)
        doctor_btn.pack(side="left", padx=2)
        probe_btn = ttk.Button(frame, text="Live sprite probe", command=self.open_visual_doctor_probe)
        probe_btn.pack(side="left", padx=2)
        self.sdcpp_debug_buttons.extend([start_btn, debug_btn, doctor_btn, probe_btn])
        self._attach_static_help(start_btn, "Сохранить config.env и открыть /sdcpp_start: server.py попробует поднять sd.cpp до крафта.")
        self._attach_static_help(debug_btn, "Открыть /sdcpp_debug: команда запуска, активный backend и хвост лога sd.cpp.")
        self._attach_static_help(doctor_btn, "Открыть /visual_doctor: проверка полного пути Z-Image -> postprocess -> asset delivery.")
        self._attach_static_help(probe_btn, "Открыть /visual_doctor.json?probe=1: реальная тестовая генерация item sprite без крафта в игре.")
        ttk.Label(frame, text="/sdcpp_start запускает sd-server; Visual Doctor проверяет Z-Image и обязательный sprite delivery.", foreground="#666").pack(side="left", padx=8)

    def _extra_text(self):
        return self.text_widgets.get("INFINI_SDCPP_SERVER_EXTRA_ARGS")

    def _get_extra_args(self) -> str:
        text = self._extra_text()
        if text is None:
            return self.data.get("INFINI_SDCPP_SERVER_EXTRA_ARGS", "")
        return text.get("1.0", "end-1c").strip()

    def _set_extra_args(self, value: str):
        text = self._extra_text()
        if text is not None:
            text.delete("1.0", "end")
            text.insert("1.0", value.strip())

    def append_extra_arg(self, arg: str):
        self.append_extra_args(arg)

    @staticmethod
    def _split_extra_for_gui(value: str) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        try:
            return shlex.split(raw, posix=True)
        except ValueError:
            return raw.split()

    @staticmethod
    def _join_extra_for_gui(tokens: list[str]) -> str:
        if not tokens:
            return ""
        try:
            return shlex.join(tokens)
        except AttributeError:
            return " ".join(tokens)

    @staticmethod
    def _extra_option_names(tokens: list[str]) -> set[str]:
        value_flags = {"--rng", "--flow-shift", "--lora-apply-mode", "--params-backend", "--cache-mode", "--cache-option", "--backend"}
        names: set[str] = set()
        i = 0
        while i < len(tokens):
            token = str(tokens[i])
            name = token.split("=", 1)[0]
            if name in value_flags:
                names.add(name)
                i += 2 if "=" not in token and i + 1 < len(tokens) else 1
            else:
                i += 1
        return names

    @staticmethod
    def _remove_extra_options(tokens: list[str], names: set[str]) -> list[str]:
        value_flags = {"--rng", "--flow-shift", "--lora-apply-mode", "--params-backend", "--cache-mode", "--cache-option", "--backend"}
        out: list[str] = []
        i = 0
        while i < len(tokens):
            token = str(tokens[i])
            name = token.split("=", 1)[0]
            if name in names:
                i += 2 if name in value_flags and "=" not in token and i + 1 < len(tokens) else 1
                continue
            out.append(token)
            i += 1
        return out

    def append_extra_args(self, fragment: str):
        fragment = str(fragment or "").strip()
        if not fragment:
            return
        cur_tokens = self._split_extra_for_gui(self._get_extra_args())
        frag_tokens = self._split_extra_for_gui(fragment)
        option_names = self._extra_option_names(frag_tokens)
        if option_names:
            cur_tokens = self._remove_extra_options(cur_tokens, option_names)
        for token in frag_tokens:
            if token not in cur_tokens:
                cur_tokens.append(token)
        cur = self._join_extra_for_gui(cur_tokens)
        self._set_extra_args(cur)
        replaced = f"; заменены конфликтующие {', '.join(sorted(option_names))}" if option_names else ""
        self.status_var.set(f"Добавлено в sd.cpp extra args: {fragment}{replaced}")

    def apply_zimage_recommended_extra(self):
        self.set_extra_profile("zimage_amd_safe")

    def set_extra_profile(self, profile: str):
        value = SDCPP_EXTRA_PROFILES.get(profile, "")
        self._set_extra_args(value)
        self.status_var.set(f"sd.cpp extra profile applied: {profile}")

    def repair_command_template(self):
        if "INFINI_SDCPP_SERVER_COMMAND_MODE" in self.vars:
            self.vars["INFINI_SDCPP_SERVER_COMMAND_MODE"].set("safe_args")
        if "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE" in self.vars:
            self.vars["INFINI_SDCPP_SERVER_COMMAND_TEMPLATE"].set(SDCPP_DEFAULT_COMMAND_TEMPLATE)
        self.status_var.set("sd.cpp command repaired: command mode=safe_args, template reset to default reference.")
        self._refresh_visibility()

    def clear_extra_args(self):
        self._set_extra_args("")
        self.status_var.set("sd.cpp extra args cleared. VAE/Qwen/LoRA поля выше не тронуты.")

    def _build_visual(self, parent):
        ttk.Label(parent, text="VFX / качество / авторство", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.row(parent, "Visual asset mode", "INFINI_VISUAL_ASSET_MODE", values=["full", "projectile", "off"])
        self.row(parent, "Visual director LLM", "INFINI_VISUAL_DIRECTOR_LLM", values=["1", "0"])
        self.row(parent, "Visual director max tokens", "INFINI_VISUAL_DIRECTOR_MAX_TOKENS", width=16, hint="Пусто = взять общий Max answer tokens. Если хочешь отдельно ограничить visual-kit шаг, задай число здесь.")
        self.row(parent, "Allow projectile images", "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES", values=["1", "0"])
        self.row(parent, "Allow impact images", "INFINI_VISUAL_GENERATE_IMPACT_IMAGES", values=["1", "0"])
        self.row(parent, "Allow child/field images", "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES", values=["1", "0"])
        self.row(parent, "VFX LLM director", "INFINI_VFX_LLM_DIRECTOR", values=["1", "0"])
        self.row(parent, "Remove BG", "INFINI_REMOVE_BG", values=["1", "0"])
        self.row(parent, "BG remove mode", "INFINI_BG_REMOVE_MODE", values=["sprite_keyer"], hint="Оставлен только sprite_keyer: Photoshop-like Magic Wand от краёв + refine/spill cleanup под Terraria sprites.")
        self.row(parent, "BG color", "INFINI_BG_COLOR", values=["magenta", "transparent", "white", "black"])
        self.row(parent, "Chroma tolerance", "INFINI_CHROMA_TOLERANCE", width=16, hint="Допуск key-color удаления. Если белое/серое уносит — не повышать; обычно 34.")
        self.row(parent, "Alpha threshold", "INFINI_ALPHA_THRESHOLD", width=16, hint="Порог отсечения полупрозрачной альфы. Если края худеют — снизить до 20-24.")
        self.row(parent, "Sprite keyer spill radius", "INFINI_SPRITE_KEYER_SPILL_RADIUS", width=16, hint="sprite_keyer: radius узкой refine-edge зоны для подавления magenta spill. Обычно 3.")
        self.row(parent, "Sprite keyer residue steps", "INFINI_SPRITE_KEYER_RESIDUE_STEPS", width=16, hint="sprite_keyer: сколько шагов проходить по connected magenta/dark-key residue от выбранного фона. Обычно 8.")
        self.row(parent, "Sprite retries", "INFINI_SPRITE_RETRIES", width=16)
        self.row(parent, "Save sprite stages", "INFINI_SAVE_SPRITE_STAGES", values=["1", "0"], hint="1 = сохранять 00_raw / 10_bg_removed_fullres / 20_master_norm / 30_baked_final в cache\\sprites для дебага.")
        self.row(parent, "Sprite processing", "INFINI_SPRITE_PROCESSING_PROFILE", values=["master_soft", "pixel_strict", "legacy_nearest"], hint="master_soft = full-res bg cut/normalize + premultiplied downscale; legacy_nearest = старый прямой resize.")
        self.row(parent, "Master canvas", "INFINI_SPRITE_MASTER_CANVAS", width=16, hint="Большой промежуточный RGBA-canvas перед финальным 32/48/64 bake. Нужен для master-first нормализации: вырезали фон, вписали объект в 256x256, потом уже уменьшили в 32/48/64.")
        self.row(parent, "Downscale filter", "INFINI_SPRITE_DOWNSCALE_FILTER", values=["box", "lanczos", "bicubic", "nearest"], hint="box обычно лучше для fake pixel-art 512→32; nearest оставлен для strict/legacy.")
        self.row(parent, "Premultiplied resize", "INFINI_SPRITE_PREMULTIPLIED_RESIZE", values=["1", "0"], hint="Убирает magenta bleed по краям при resize RGBA.")
        self.row(parent, "Chroma defringe", "INFINI_SPRITE_CHROMA_DEFRINGE", values=["1", "0"], hint="Консервативно удаляет остатки magenta-key только на краях alpha.")
        self.row(parent, "Posterize", "INFINI_PIXEL_POSTERIZE", values=["1", "0"])
        self.row(parent, "Max colors", "INFINI_MAX_COLORS", width=16)
        self.row(parent, "Strict AI authorship", "INFINI_VISUAL_STRICT_AI_AUTHORSHIP", values=["1", "0"], hint="1 = код не рисует за нейронку, только валидирует/ретраит.")
        self.row(parent, "Allow procedural fallback", "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", values=["0", "1"])

    def _build_trace(self, parent):
        outer = ttk.Frame(parent, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Pipeline trace / prompts / sd.cpp", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Чёрный ящик генерации: что отправили ЛЛМ, какие image prompts ушли в backend, что ответил sd.cpp, где отвалился step.",
            foreground="#666",
        ).pack(anchor="w", pady=(2, 8))

        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Refresh trace", command=self.refresh_trace).pack(side="left", padx=2)
        ttk.Button(bar, text="Open /trace", command=self.open_trace_page).pack(side="left", padx=2)
        ttk.Button(bar, text="Open trace.json", command=self.open_trace_json).pack(side="left", padx=2)
        ttk.Button(bar, text="Open cache folder", command=self.open_cache_folder).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear trace", command=self.clear_trace_files).pack(side="left", padx=8)
        self.trace_status_var = tk.StringVar(value="Нажми Refresh trace. Если server.py не запущен, GUI покажет локальные cache/*.ndjson.")
        ttk.Label(bar, textvariable=self.trace_status_var, foreground="#666").pack(side="left", padx=8)

        self.trace_views = ttk.Notebook(outer)
        self.trace_views.pack(fill="both", expand=True)
        self.trace_texts: dict[str, tk.Text] = {}
        for key, title in [
            ("summary", "Сводка"),
            ("prompts", "Промпты"),
            ("pipeline", "Steps"),
            ("events", "Events"),
            ("sdcpp", "sd.cpp"),
            ("failure", "Last failure"),
        ]:
            frame = ttk.Frame(self.trace_views)
            self.trace_views.add(frame, text=title)
            text = tk.Text(frame, wrap="word", undo=False, font=("Consolas", 9), bg="#101828", fg="#e5e7eb", insertbackground="#e5e7eb")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            text.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            self._enable_edit_menu(text)
            self.trace_texts[key] = text

    def _set_trace_text(self, key: str, content: str):
        text = self.trace_texts.get(key)
        if not text:
            return
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", content)
        text.configure(state="normal")

    def _load_local_trace_snapshot(self, reason: str = "") -> dict:
        cache = ROOT / "cache"
        def tail_ndjson(path: Path, limit: int = 120):
            if not path.exists():
                return []
            out = []
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    out.append(obj if isinstance(obj, dict) else {"raw": obj})
                except Exception:
                    out.append({"raw": line})
            return out
        def tail_text(path: Path, max_chars: int = 20000):
            if not path.exists():
                return ""
            return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
        return {
            "ok": False,
            "source": "local_cache_fallback",
            "version": "server unavailable",
            "serverRoot": str(ROOT),
            "cacheDir": str(cache),
            "pipeline": {"note": "server.py не ответил или отвечает другая копия; показан локальный cache", "reason": reason},
            "traceConfig": {"eventsFile": str(cache / "events.ndjson"), "promptTraceFile": str(cache / "prompt_trace.ndjson"), "pipelineTraceFile": str(cache / "pipeline_trace.ndjson")},
            "events": tail_ndjson(cache / "events.ndjson"),
            "promptTrace": tail_ndjson(cache / "prompt_trace.ndjson"),
            "pipelineTrace": tail_ndjson(cache / "pipeline_trace.ndjson"),
            "sdcpp": {"logFile": str(cache / "sdcpp_server.log"), "logTail": tail_text(cache / "sdcpp_server.log")},
            "lastCombineFailure": json.loads((cache / "last_combine_failure.json").read_text(encoding="utf-8")) if (cache / "last_combine_failure.json").exists() else None,
        }

    def _fetch_trace_snapshot(self) -> dict:
        health = self._fetch_health_snapshot(timeout=8)
        if not self._health_matches_this_gui(health):
            raise RuntimeError(self._server_identity_warning(health).replace("\n", " | "))
        url = self._server_base_url() + "/trace.json"
        with urllib.request.urlopen(url, timeout=18) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _pretty(self, value) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(value)

    def _fmt_event_line(self, ev: dict, include_prompts: bool = False) -> str:
        ts = ev.get("ts") or ev.get("createdAt") or ""
        stage = ev.get("stage") or ev.get("level") or ev.get("kind") or "event"
        title = ev.get("title") or ev.get("message") or ""
        head = f"[{ts}] {stage} :: {title}\n"
        payload = {k: v for k, v in ev.items() if k not in {"prompt", "negative", "response"}}
        body = self._pretty(payload)
        if include_prompts:
            if ev.get("prompt"):
                body += "\n\n--- PROMPT ---\n" + str(ev.get("prompt"))
            if ev.get("negative"):
                body += "\n\n--- NEGATIVE ---\n" + str(ev.get("negative"))
            if ev.get("response"):
                body += "\n\n--- RESPONSE ---\n" + str(ev.get("response"))
        return head + body + "\n" + ("═" * 96) + "\n"

    def refresh_trace(self):
        try:
            snap = self._fetch_trace_snapshot()
            self.trace_status_var.set("Trace loaded from server /trace.json")
        except Exception as e:
            reason = str(e)
            snap = self._load_local_trace_snapshot(reason)
            self.trace_status_var.set(f"Server trace unavailable, local cache fallback: {reason}")

        pipeline = snap.get("pipeline") or {}
        trace_cfg = snap.get("traceConfig") or {}
        summary = []
        summary.append("INFICRAFTER TRACE SUMMARY")
        summary.append("═" * 96)
        summary.append(f"version: {snap.get('version')}")
        summary.append(f"cache:   {snap.get('cacheDir')}")
        summary.append("")
        summary.append("PIPELINE")
        summary.append(self._pretty(pipeline))
        summary.append("")
        summary.append("TRACE FILES")
        summary.append(self._pretty(trace_cfg))
        self._set_trace_text("summary", "\n".join(summary))

        prompt_events = snap.get("promptTrace") or []
        self._set_trace_text("prompts", "".join(self._fmt_event_line(ev, include_prompts=True) for ev in reversed(prompt_events)) or "Пока prompt trace пуст.")
        pipe_events = snap.get("pipelineTrace") or []
        self._set_trace_text("pipeline", "".join(self._fmt_event_line(ev) for ev in reversed(pipe_events)) or "Пока pipeline trace пуст.")
        events = snap.get("events") or []
        self._set_trace_text("events", "".join(self._fmt_event_line(ev) for ev in reversed(events)) or "Пока events пуст.")
        self._set_trace_text("sdcpp", self._pretty(snap.get("sdcpp") or {}))
        self._set_trace_text("failure", self._pretty(snap.get("lastCombineFailure")))

    def open_trace_page(self):
        webbrowser.open(self._server_base_url() + "/trace")
        self.status_var.set("Opened /trace. Если server.py не запущен — Start server.")

    def open_trace_json(self):
        webbrowser.open(self._server_base_url() + "/trace.json")
        self.status_var.set("Opened /trace.json.")

    def open_cache_folder(self):
        cache = ROOT / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        os.startfile(cache) if os.name == "nt" else webbrowser.open(cache.as_uri())

    def clear_trace_files(self):
        if messagebox.askyesno("Clear trace", "Очистить events.ndjson / prompt_trace.ndjson / pipeline_trace.ndjson?"):
            try:
                with urllib.request.urlopen(self._server_base_url() + "/trace_clear", timeout=4) as resp:
                    _ = resp.read()
                self.trace_status_var.set("Trace cleared through server.")
            except Exception:
                cache = ROOT / "cache"
                for name in ["events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"]:
                    try:
                        (cache / name).write_text("", encoding="utf-8")
                    except Exception:
                        pass
                self.trace_status_var.set("Trace cleared locally.")
            self.refresh_trace()

    def _refresh_secret_entries(self):
        show = "" if self.show_secrets.get() else "*"
        for entry in getattr(self, "secret_entries", []):
            entry.configure(show=show)

    def _value(self, key: str, default: str = "") -> str:
        if key in self.vars:
            return self.vars[key].get().strip()
        return self.data.get(key, DEFAULTS.get(key, default)).strip()

    def _refresh_visibility(self):
        # Keep fields visible, but block the inactive branch.  This is less confusing
        # than disappearing boxes and prevents editing settings that the current
        # provider/backend/profile will ignore anyway.
        self._refresh_secret_entries()
        for key in list(self.field_widgets):
            self._set_field_enabled(key, True, "")
        self._set_widgets_enabled(self.extra_arg_buttons, True)
        self._set_widgets_enabled(self.sdcpp_debug_buttons, True)

        provider = (self._value("INFINI_LLM_PROVIDER", "local") or "local").lower()
        backend = (self._value("INFINI_IMAGE_BACKEND", "sdcpp") or "sdcpp").lower()
        visual_mode = (self._value("INFINI_VISUAL_ASSET_MODE", "full") or "full").lower()
        sprite_profile = (self._value("INFINI_SPRITE_PROCESSING_PROFILE", "master_soft") or "master_soft").lower()
        reasoning_mode = (self._value("INFINI_LLM_REASONING_MODE", "off") or "off").lower().replace("-", "_")
        remove_bg = self._value("INFINI_REMOVE_BG", "1") == "1"
        bg_mode = (self._value("INFINI_BG_REMOVE_MODE", "sprite_keyer") or "sprite_keyer").lower()
        posterize = self._value("INFINI_PIXEL_POSTERIZE", "1") == "1"
        strict_ai = self._value("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1"

        local_llm = ["INFINI_LMSTUDIO_URL", "INFINI_LMSTUDIO_MODEL"]
        openrouter_llm = [
            "INFINI_OPENROUTER_API_KEY", "INFINI_OPENROUTER_MODEL",
            "INFINI_OPENROUTER_HTTP_REFERER", "INFINI_OPENROUTER_APP_TITLE",
        ]
        compat_llm = ["INFINI_OPENAI_COMPAT_BASE_URL", "INFINI_OPENAI_COMPAT_API_KEY", "INFINI_OPENAI_COMPAT_MODEL"]
        for key in local_llm:
            self._set_field_enabled(key, provider == "local", f"LLM provider сейчас `{provider}`, локальные LM Studio поля не используются.")
        for key in openrouter_llm:
            self._set_field_enabled(key, provider == "openrouter", f"LLM provider сейчас `{provider}`, OpenRouter поля не используются.")
        for key in compat_llm:
            self._set_field_enabled(key, provider == "openai_compat", f"LLM provider сейчас `{provider}`, compat API поля не используются.")

        off_modes = {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}
        prompt_modes = {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}
        api_reasoning_active = provider != "local" and reasoning_mode not in off_modes and reasoning_mode not in prompt_modes
        self._set_field_enabled(
            "INFINI_LLM_REASONING_MAX_TOKENS",
            api_reasoning_active and reasoning_mode in {"tokens", "token_budget", "max_tokens", "budget"},
            "Бюджет токенов работает только при reasoning mode = tokens и не-local provider.",
        )
        self._set_field_enabled(
            "INFINI_LLM_REASONING_EXCLUDE",
            api_reasoning_active,
            "Exclude нужен только когда провайдеру реально отправляется API reasoning object.",
        )
        local_prompt_active = reasoning_mode in prompt_modes or (provider == "local" and reasoning_mode not in off_modes)
        self._set_field_enabled(
            "INFINI_LLM_LOCAL_REASONING_PROMPT",
            local_prompt_active,
            "Prompt-only reasoning используется для local/prompt_* режимов; для обычного API reasoning это поле игнорируется.",
        )

        sdcpp_keys = [
            "INFINI_SDCPP_SERVER_EXE", "INFINI_SDCPP_MODEL", "INFINI_SDCPP_VAE", "INFINI_SDCPP_LLM",
            "INFINI_SDCPP_LORA_FILE", "INFINI_SDCPP_LORA_WEIGHT", "INFINI_SDCPP_LORA_PROMPT_TAGS",
            "INFINI_SDCPP_SERVER_URL", "INFINI_SDCPP_SERVER_AUTOSTART", "INFINI_SDCPP_SERVER_COMMAND_MODE", "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE",
            "INFINI_SDCPP_SERVER_EXTRA_ARGS", "INFINI_SDCPP_SERVER_SHOW_CONSOLE", "INFINI_SDCPP_SERVER_LOG_FILE",
            "INFINI_SDCPP_WIDTH", "INFINI_SDCPP_HEIGHT", "INFINI_SDCPP_STEPS", "INFINI_SDCPP_CFG", "INFINI_SDCPP_SAMPLER",
            "INFINI_SDCPP_SEED", "INFINI_ZIMAGE_PROMPT_CONTRACT", "INFINI_ZIMAGE_POSITIVE_ONLY",
        ]
        image_api_keys = [
            "INFINI_IMAGE_API_BASE_URL", "INFINI_IMAGE_API_KEY", "INFINI_IMAGE_API_MODEL",
            "INFINI_IMAGE_API_PATH", "INFINI_IMAGE_API_SIZE", "INFINI_IMAGE_API_TIMEOUT",
        ]
        for key in sdcpp_keys:
            self._set_field_enabled(key, backend == "sdcpp", f"Image backend сейчас `{backend}`, sd.cpp/Z-Image поля не участвуют.")
        command_mode = (self._value("INFINI_SDCPP_SERVER_COMMAND_MODE", "safe_args") or "safe_args").lower()
        self._set_field_enabled(
            "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE",
            backend == "sdcpp" and command_mode == "template",
            "Command mode = safe_args: server.py собирает argv сам; шаблон не используется и не может сломать --sampling-method.",
        )
        self._set_widgets_enabled(self.extra_arg_buttons, backend == "sdcpp")
        self._set_widgets_enabled(self.sdcpp_debug_buttons, backend == "sdcpp")
        for key in image_api_keys:
            self._set_field_enabled(key, backend == "image_api", f"Image backend сейчас `{backend}`, Image API поля не участвуют.")
        self._set_field_enabled("INFINI_A1111_URL", backend == "a1111", f"Image backend сейчас `{backend}`, A1111 URL не используется.")
        self._set_field_enabled("INFINI_COMFYUI_URL", backend == "comfyui", f"Image backend сейчас `{backend}`, ComfyUI URL не используется.")

        if not self.radmin_enabled.get():
            self._set_field_enabled("INFINI_ASSET_PUBLIC_BASE_URL", False, "Radmin/LAN overlay выключен; внешний URL ассетов не нужен для локальной игры.")
        else:
            self._set_field_enabled("INFINI_ASSET_PUBLIC_BASE_URL", True, "")

        image_active = backend != "off"
        asset_pack_active = image_active and visual_mode in {"full", "all", "projectile", "visualpack", "assetpack"}
        full_asset_pack = image_active and visual_mode in {"full", "all", "visualpack", "assetpack"}
        projectile_asset_pack = image_active and visual_mode in {"full", "all", "projectile", "visualpack", "assetpack"}

        for key in ["INFINI_VISUAL_DIRECTOR_LLM", "INFINI_VFX_LLM_DIRECTOR"]:
            self._set_field_enabled(key, asset_pack_active, "Visual asset mode сейчас off или image backend выключен; director-pass не вызывается.")
        self._set_field_enabled("INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES", projectile_asset_pack, "Projectile asset pack выключен текущим Visual asset mode/backend.")
        self._set_field_enabled("INFINI_VISUAL_GENERATE_IMPACT_IMAGES", full_asset_pack, "Baked impact images доступны только в full visual asset mode; флаг разрешает, но не принуждает.")
        self._set_field_enabled("INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES", full_asset_pack, "Baked child/field images доступны только в full visual asset mode; флаг разрешает, но не принуждает.")

        sprite_processing_active = image_active
        for key in [
            "INFINI_REMOVE_BG", "INFINI_SPRITE_RETRIES", "INFINI_SPRITE_PROCESSING_PROFILE",
            "INFINI_PIXEL_POSTERIZE", "INFINI_VISUAL_STRICT_AI_AUTHORSHIP",
        ]:
            self._set_field_enabled(key, sprite_processing_active, "Image backend = off; PNG не генерируются, sprite postprocess не запускается.")
        self._set_field_enabled("INFINI_BG_REMOVE_MODE", sprite_processing_active and remove_bg, "Remove BG выключен или image backend=off; режим удаления фона не используется.")
        sprite_keyer_active = sprite_processing_active and remove_bg and bg_mode == "sprite_keyer"
        for key in ["INFINI_SPRITE_KEYER_SPILL_RADIUS", "INFINI_SPRITE_KEYER_RESIDUE_STEPS"]:
            self._set_field_enabled(key, sprite_keyer_active, "Поля sprite_keyer активны при BG remove mode = sprite_keyer.")
        self._set_field_enabled("INFINI_BG_COLOR", sprite_processing_active and remove_bg and bg_mode not in {"off", "none", "transparent"}, "Фон не вырезается текущим sprite_keyer-пайплайном, цвет ключа не используется.")
        self._set_field_enabled("INFINI_SPRITE_CHROMA_DEFRINGE", sprite_processing_active and remove_bg, "Defringe используется как безопасная edge-clean стадия после sprite_keyer; сейчас этот этап неактивен.")
        self._set_field_enabled("INFINI_MAX_COLORS", sprite_processing_active and posterize, "Max colors используется только когда Posterize=1 и image backend не off.")

        if sprite_processing_active:
            if sprite_profile in {"legacy", "legacy_nearest"}:
                self._set_field_enabled("INFINI_SPRITE_MASTER_CANVAS", False, "legacy_nearest не использует master canvas: идёт старый прямой fit_to_canvas.")
                self._set_field_enabled("INFINI_SPRITE_DOWNSCALE_FILTER", False, "legacy_nearest принудительно использует NEAREST; фильтр игнорируется.")
                self._set_field_enabled("INFINI_SPRITE_PREMULTIPLIED_RESIZE", False, "legacy_nearest делает прямой NEAREST resize; premultiplied resize не вызывается.")
            elif sprite_profile == "pixel_strict":
                self._set_field_enabled("INFINI_SPRITE_MASTER_CANVAS", True, "")
                self._set_field_enabled("INFINI_SPRITE_DOWNSCALE_FILTER", False, "pixel_strict принудительно использует NEAREST; ручной filter игнорируется.")
                self._set_field_enabled("INFINI_SPRITE_PREMULTIPLIED_RESIZE", False, "pixel_strict использует NEAREST, а premultiplied resize нужен только для мягких alpha-фильтров.")
            else:
                self._set_field_enabled("INFINI_SPRITE_MASTER_CANVAS", True, "")
                self._set_field_enabled("INFINI_SPRITE_DOWNSCALE_FILTER", True, "")
                filter_value = (self._value("INFINI_SPRITE_DOWNSCALE_FILTER", "box") or "box").lower()
                self._set_field_enabled("INFINI_SPRITE_PREMULTIPLIED_RESIZE", filter_value != "nearest", "При downscale filter=nearest premultiplied resize не используется.")

        if strict_ai:
            if "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK" in self.vars:
                self.vars["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"].set("0")
            self._set_field_enabled("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", False, "Strict AI authorship=1: procedural fallback принудительно выключен, чтобы код не авторил картинку за модель.")
        else:
            self._set_field_enabled("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", sprite_processing_active, "Image backend=off; fallback PNG не нужен.")

    def collect(self) -> dict[str, str]:
        data = parse_env(CONFIG_PATH) if CONFIG_PATH.exists() else dict(DEFAULTS)
        data["INFINI_GUI_PIPELINE_PRESET"] = self.preset_var.get().strip() if hasattr(self, "preset_var") else data.get("INFINI_GUI_PIPELINE_PRESET", DEFAULTS.get("INFINI_GUI_PIPELINE_PRESET", ""))
        for key, var in self.vars.items():
            data[key] = var.get().strip()
        for key, widget in self.text_widgets.items():
            raw = widget.get("1.0", "end-1c").strip()
            # config.env is line-based; keep multiline extra args readable in GUI but save them as one command line.
            data[key] = " ".join(raw.split()) if key == "INFINI_SDCPP_SERVER_EXTRA_ARGS" else raw
        repaired_template, repaired, reason = repair_sdcpp_command_template(data.get("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", ""))
        if repaired:
            data["INFINI_SDCPP_SERVER_COMMAND_TEMPLATE"] = repaired_template
            if "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE" in self.vars:
                self.vars["INFINI_SDCPP_SERVER_COMMAND_TEMPLATE"].set(repaired_template)
            if "INFINI_SDCPP_SERVER_COMMAND_MODE" in self.vars:
                self.vars["INFINI_SDCPP_SERVER_COMMAND_MODE"].set("safe_args")
                data["INFINI_SDCPP_SERVER_COMMAND_MODE"] = "safe_args"
            self.status_var.set(f"sd.cpp command template repaired on save: {reason}")
        # Radmin/LAN is an overlay, not a pipeline preset. Apply it last so it can sit
        # on top of local/OpenRouter/image_api/etc.
        if self.radmin_enabled.get():
            data["INFINI_HOST"] = "0.0.0.0"
            if "INFINI_HOST" in self.vars:
                self.vars["INFINI_HOST"].set("0.0.0.0")
        else:
            if data.get("INFINI_HOST") == "0.0.0.0":
                data["INFINI_HOST"] = "127.0.0.1"
                if "INFINI_HOST" in self.vars:
                    self.vars["INFINI_HOST"].set("127.0.0.1")
            if data.get("INFINI_ASSET_PUBLIC_BASE_URL", "").startswith("http://26."):
                data["INFINI_ASSET_PUBLIC_BASE_URL"] = ""
                if "INFINI_ASSET_PUBLIC_BASE_URL" in self.vars:
                    self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].set("")
        lora_file = data.get("INFINI_SDCPP_LORA_FILE", "").strip()
        if lora_file:
            # A concrete LoRA file is the source of truth: stale/default folder values
            # must not point sd.cpp at a different directory.
            p = Path(lora_file)
            lora_dir = self._lora_dir_from_file(lora_file) or str(p.parent)
            if lora_dir:
                data["INFINI_SDCPP_LORA_DIR"] = lora_dir
                if "INFINI_SDCPP_LORA_DIR" in self.vars:
                    self.vars["INFINI_SDCPP_LORA_DIR"].set(lora_dir)
            if not data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "").strip():
                tag = self._lora_tag_from_file(lora_file, data.get("INFINI_SDCPP_LORA_WEIGHT", "0.65"))
                data["INFINI_SDCPP_LORA_PROMPT_TAGS"] = tag
                self._set_lora_tags(tag)
        else:
            # LoRA folder is no longer a visible GUI control. Without a concrete file
            # there is no safe directory to infer, so do not keep stale hidden paths.
            data["INFINI_SDCPP_LORA_DIR"] = ""
        if data.get("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1":
            data["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
            if "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK" in self.vars:
                self.vars["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"].set("0")
        return data

    def save(self):
        data = self.collect()
        write_env(CONFIG_PATH, data)
        self.data = data
        self.status_var.set(f"Saved: {CONFIG_PATH}")

    def apply_preset(self):
        preset_name = self.preset_var.get().strip()
        preset = PRESETS.get(preset_name, {})
        for key, value in preset.items():
            if key in self.vars:
                self.vars[key].set(value)
        self.data["INFINI_GUI_PIPELINE_PRESET"] = preset_name
        self.status_var.set("Pipeline applied. Нажми Save, чтобы сохранить выбранный preset в config.env. Radmin/LAN не менялся.")
        self._refresh_visibility()

    def on_radmin_toggle(self):
        if self.radmin_enabled.get():
            self.apply_radmin_overlay(status_only=False)
        else:
            self.apply_local_overlay(status_only=False)

    def apply_radmin_overlay(self, status_only: bool = True):
        self.radmin_enabled.set(True)
        if "INFINI_HOST" in self.vars:
            self.vars["INFINI_HOST"].set("0.0.0.0")
        if "INFINI_ASSET_PUBLIC_BASE_URL" in self.vars and not self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].get().strip():
            best = self._best_radmin_ip()
            self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].set(f"http://{best}:5055" if best else "http://26.x.x.x:5055")
        self._update_radmin_info()
        self.status_var.set("Radmin/LAN overlay включён: host=0.0.0.0. Друзья получают только готовый item JSON + PNG/JSON ассеты, не LLM/prompts.")
        self._refresh_visibility()

    def apply_local_overlay(self, status_only: bool = True):
        self.radmin_enabled.set(False)
        if "INFINI_HOST" in self.vars:
            self.vars["INFINI_HOST"].set("127.0.0.1")
        if "INFINI_ASSET_PUBLIC_BASE_URL" in self.vars:
            val = self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].get().strip()
            if val.startswith("http://26.") or "26.x.x.x" in val:
                self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].set("")
        self._update_radmin_info()
        self.status_var.set("Local-only overlay: server слушает только 127.0.0.1.")
        self._refresh_visibility()

    @staticmethod
    def _detect_ipv4_candidates() -> list[str]:
        candidates: list[str] = []
        def add(ip: str):
            ip = (ip or "").strip()
            if not ip or ip.startswith("127.") or ip in candidates:
                return
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
                candidates.append(ip)
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                add(info[4][0])
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                add(s.getsockname()[0])
            finally:
                s.close()
        except Exception:
            pass
        if os.name == "nt":
            try:
                out = subprocess.run(["ipconfig"], capture_output=True, text=True, encoding="cp866", errors="ignore", timeout=2).stdout
                for m in re.finditer(r"IPv4[^:\r\n]*:\s*([0-9]+(?:\.[0-9]+){3})", out):
                    add(m.group(1))
            except Exception:
                pass
        return candidates

    def _radmin_ips(self) -> list[str]:
        return [ip for ip in self._detect_ipv4_candidates() if ip.startswith("26.")]

    def _best_radmin_ip(self) -> str:
        ips = self._radmin_ips()
        return ips[0] if ips else ""

    def _radmin_status_text(self) -> str:
        ips = self._radmin_ips()
        lan = self._detect_ipv4_candidates()
        ip_text = ", ".join(ips) if ips else "не найден 26.x.x.x — запусти Radmin VPN и вступи в одну сеть"
        lan_text = ", ".join(lan[:4]) if lan else "нет IPv4"
        url = self.vars.get("INFINI_ASSET_PUBLIC_BASE_URL", tk.StringVar(value=self.data.get("INFINI_ASSET_PUBLIC_BASE_URL", ""))).get().strip() if hasattr(self, "vars") else self.data.get("INFINI_ASSET_PUBLIC_BASE_URL", "")
        terraria_port = self.vars.get("INFINI_TERRARIA_PORT", tk.StringVar(value="7777")).get().strip() if hasattr(self, "vars") else self.data.get("INFINI_TERRARIA_PORT", "7777")
        return (f"Radmin IP: {ip_text}.  Terraria друзьям: Join via IP → <Radmin IP>:{terraria_port}.  "
                f"Asset URL: {url or 'не задан'}.  Друзьям не нужен LocalGenerator для уже готовых предметов; они качают только финальные ассеты.")

    def _update_radmin_info(self):
        if hasattr(self, "radmin_info_var"):
            self.radmin_info_var.set(self._radmin_status_text())

    def autofill_radmin_url(self):
        self.radmin_enabled.set(True)
        if "INFINI_HOST" in self.vars:
            self.vars["INFINI_HOST"].set("0.0.0.0")
        ip = self._best_radmin_ip()
        if not ip:
            self.status_var.set("Radmin IP 26.x.x.x не найден. Проверь, что Radmin VPN запущен и ты в сети.")
            messagebox.showwarning("Radmin", "Не нашёл Radmin IPv4 26.x.x.x. Запусти Radmin VPN / вступи в сеть и нажми ещё раз.")
            self._update_radmin_info()
            return
        port = self.vars.get("INFINI_PORT", tk.StringVar(value="5055")).get().strip() or "5055"
        if "INFINI_ASSET_PUBLIC_BASE_URL" in self.vars:
            self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].set(f"http://{ip}:{port}")
        self._update_radmin_info()
        self.status_var.set(f"Radmin URL выставлен: http://{ip}:{port}. Нажми Save → Start server.")

    def _friend_guide_text(self) -> str:
        ip = self._best_radmin_ip() or "<мой Radmin IP 26.x.x.x>"
        port = self.vars.get("INFINI_TERRARIA_PORT", tk.StringVar(value="7777")).get().strip() or "7777"
        asset_url = self.vars.get("INFINI_ASSET_PUBLIC_BASE_URL", tk.StringVar(value=f"http://{ip}:5055")).get().strip() or f"http://{ip}:5055"
        return ("Как подключиться к моей Terraria / InfiniCrafterLocal:\n"
                "1) Запусти Radmin VPN и зайди в нашу общую сеть.\n"
                f"2) Terraria/tModLoader → Multiplayer → Join via IP → {ip} → Port {port}.\n"
                f"3) Для проверки ассетов открой в браузере: {asset_url}/health\n"
                "4) LocalGenerator/LLM/Z-Image нужен только хосту. Тебе прилетают уже готовые предметы и финальные PNG/JSON ассеты.")

    def copy_radmin_friend_guide(self):
        text = self._friend_guide_text()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Инструкция для друзей скопирована в буфер.")
        messagebox.showinfo("Radmin", text)

    def open_mp_connect_page(self):
        base = self._server_base_url()
        webbrowser.open(base + "/mp_connect")
        self.status_var.set("Открыл /mp_connect. Если хочешь, чтобы это открыл друг — дай ему ссылку с твоим Radmin IP, не 127.0.0.1.")

    def browse_file(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        filename = filedialog.askopenfilename(title="Выбери файл", initialdir=str(Path(initial).parent) if initial else str(ROOT))
        if filename and key in self.vars:
            self.vars[key].set(filename)

    def browse_model(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        filename = filedialog.askopenfilename(title="Выбери model файл", initialdir=str(Path(initial).parent) if initial else str(ROOT), filetypes=[("Model files", "*.gguf *.safetensors *.ckpt *.pt *.pth"), ("All files", "*.*")])
        if filename and key in self.vars:
            self.vars[key].set(filename)

    def browse_lora_file(self) -> bool:
        key = "INFINI_SDCPP_LORA_FILE"
        initial = self.vars[key].get() if key in self.vars else self.data.get("INFINI_SDCPP_LORA_FILE", "")
        initial_dir = str(Path(initial).parent) if initial and Path(initial).suffix else (initial if initial else str(ROOT))
        filename = filedialog.askopenfilename(
            title="Выбери LoRA файл",
            initialdir=initial_dir if Path(initial_dir).exists() else str(ROOT),
            filetypes=[("LoRA files", "*.safetensors *.ckpt *.pt *.pth"), ("All files", "*.*")],
        )
        if filename and key in self.vars:
            self.vars[key].set(filename)
            self.data["INFINI_SDCPP_LORA_DIR"] = str(Path(filename).parent)
            self.status_var.set("LoRA file выбран. Нажми Use selected LoRA, чтобы добавить prompt tag; папка будет взята из файла.")
            return True
        return False

    def browse_folder(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        directory = filedialog.askdirectory(title="Выбери папку", initialdir=initial if initial and Path(initial).exists() else str(ROOT))
        if directory and key in self.vars:
            self.vars[key].set(directory)

    def _server_base_url(self) -> str:
        data = self.collect()
        host = data.get("INFINI_HOST") or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = data.get("INFINI_PORT") or "5055"
        return f"http://{host}:{port}"

    @staticmethod
    def _norm_path_for_compare(value: str | Path) -> str:
        # Compare Windows paths reliably even when tests run on Linux.
        text = str(value or "").strip().replace("\\", "/")
        while "//" in text and not text.startswith("http"):
            text = text.replace("//", "/")
        return text.rstrip("/").lower()

    @staticmethod
    def _parent_path_text(value: str, levels: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        path = PureWindowsPath(text) if (":" in text or "\\" in text) else Path(text)
        for _ in range(levels):
            path = path.parent
        return str(path)

    def _infer_server_root_from_health(self, snap: dict) -> str:
        root = str(snap.get("serverRoot") or "").strip()
        if root:
            return root
        # Backcompat for older builds: infer LocalGenerator root from cache paths.
        asset_sync = snap.get("assetSync") or {}
        sprite_dir = str(asset_sync.get("spriteDir") or "").strip()
        if sprite_dir:
            return self._parent_path_text(sprite_dir, 2)
        world_recipes = str(snap.get("worldRecipesDir") or "").strip()
        if world_recipes:
            return self._parent_path_text(world_recipes, 2)
        return ""

    def _health_matches_this_gui(self, snap: dict) -> bool:
        root = self._infer_server_root_from_health(snap)
        if not root:
            return True
        return self._norm_path_for_compare(root) == self._norm_path_for_compare(ROOT)

    @staticmethod
    def _health_looks_like_infini_helper(snap: dict) -> bool:
        if not isinstance(snap, dict):
            return False
        # Do not kill arbitrary services that happen to answer {"ok": true} on 5055.
        return bool(
            snap.get("serverRoot")
            or snap.get("cacheDir")
            or snap.get("assetSync")
            or snap.get("pipeline")
            or snap.get("sdcpp")
            or str(snap.get("server_version") or "").lower().startswith("infinicrafter")
        )

    def _fetch_health_snapshot(self, timeout: int = 8) -> dict:
        with urllib.request.urlopen(self._server_base_url() + "/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _server_identity_warning(self, snap: dict) -> str:
        root = self._infer_server_root_from_health(snap) or "unknown"
        pid = snap.get("pid") or "unknown"
        return (
            "На этом порту отвечает другая копия InfiniCrafterLocal.\n"
            f"Ответивший server.py: {root}\n"
            f"PID: {pid}\n"
            f"Текущий GUI: {ROOT}\n\n"
            "Start server теперь может прибить старый helper автоматически. "
            "Если порт занят не InfiniCrafterLocal, GUI остановится и покажет предупреждение."
        )

    def _server_port(self) -> int:
        try:
            return int((self.collect().get("INFINI_PORT") or "5055").strip())
        except Exception:
            return 5055

    def _try_http_shutdown_current_server(self, timeout: float = 2.0) -> bool:
        try:
            with urllib.request.urlopen(self._server_base_url() + "/shutdown", timeout=timeout) as resp:
                resp.read()
            return True
        except Exception:
            return False

    def _wait_until_helper_stops(self, timeout: float = 4.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._fetch_health_snapshot(timeout=0.7)
            except Exception:
                return True
            time.sleep(0.2)
        return False

    @staticmethod
    def _pid_command_line(pid: int) -> str:
        if pid <= 0:
            return ""
        if os.name == "nt":
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                return (proc.stdout or "").strip()
            except Exception:
                return ""
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _looks_like_infini_server_command(command_line: str) -> bool:
        text = str(command_line or "").replace("\\", "/").lower()
        if not text:
            return False
        if "sd-server" in text or "stable-diffusion" in text:
            return False
        return (
            "infinicrafterlocal" in text
            or ("localgenerator" in text and "server.py" in text)
            or ("infini_local" in text and "web/server" in text)
        )

    @staticmethod
    def _listening_pids_on_port(port: int) -> list[int]:
        pids: set[int] = set()
        try:
            if os.name == "nt":
                proc = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=4)
                text = proc.stdout or ""
                for line in text.splitlines():
                    cols = line.split()
                    if len(cols) < 5:
                        continue
                    local_addr = cols[1]
                    state = cols[3].upper() if len(cols) >= 5 else ""
                    if state != "LISTENING" or not local_addr.endswith(f":{port}"):
                        continue
                    try:
                        pids.add(int(cols[-1]))
                    except Exception:
                        pass
            else:
                # Best-effort fallback for dev/Linux. Prefer ss, then lsof if present.
                proc = subprocess.run(["bash", "-lc", f"ss -ltnp 'sport = :{port}' 2>/dev/null || true"], capture_output=True, text=True, timeout=4)
                for part in (proc.stdout or "").replace(',', ' ').split():
                    if "pid=" in part:
                        try:
                            pids.add(int(part.split("pid=", 1)[1].split("=", 1)[0].split()[0]))
                        except Exception:
                            pass
        except Exception:
            pass
        return sorted(pid for pid in pids if pid > 0)

    @staticmethod
    def _terminate_pid(pid: int, force: bool = False) -> bool:
        if pid <= 0 or pid == os.getpid():
            return False
        try:
            if os.name == "nt":
                args = ["taskkill", "/PID", str(pid), "/T"]
                if force:
                    args.append("/F")
                subprocess.run(args, capture_output=True, text=True, timeout=5)
            else:
                os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            return True
        except Exception:
            return False

    def _cleanup_old_helper_servers_before_start(self) -> list[str]:
        """Stop stale LocalGenerator helpers on the configured port before starting.

        Users often close the visible console with the window X, leaving another
        python/server.py copy on 5055.  Start server should behave like restart:
        ask the answering helper to shutdown, then kill only processes that look
        like InfiniCrafterLocal helpers.
        """
        actions: list[str] = []
        snap: dict | None = None
        try:
            snap = self._fetch_health_snapshot(timeout=1.2)
        except Exception:
            snap = None

        if snap and snap.get("ok"):
            if not self._health_looks_like_infini_helper(snap):
                actions.append(f"port {self._server_port()} answers /health but not as InfiniCrafterLocal; not killed")
            else:
                root = self._infer_server_root_from_health(snap) or "unknown"
                pid_raw = snap.get("pid")
                actions.append(f"found helper on {self._server_base_url()} pid={pid_raw or 'unknown'} root={root}")
                if self._try_http_shutdown_current_server(timeout=1.5):
                    actions.append("requested /shutdown")
                    if self._wait_until_helper_stops(timeout=4.0):
                        actions.append("old helper stopped gracefully")
                        return actions
                try:
                    pid = int(pid_raw or 0)
                except Exception:
                    pid = 0
                if pid and pid != os.getpid():
                    if self._terminate_pid(pid, force=False):
                        actions.append(f"sent terminate to pid {pid}")
                        if self._wait_until_helper_stops(timeout=2.0):
                            return actions
                    if self._terminate_pid(pid, force=True):
                        actions.append(f"force-killed pid {pid}")
                        self._wait_until_helper_stops(timeout=2.0)
                        return actions

        port = self._server_port()
        for pid in self._listening_pids_on_port(port):
            if pid == os.getpid():
                continue
            cmdline = self._pid_command_line(pid)
            if self._looks_like_infini_server_command(cmdline):
                if self._terminate_pid(pid, force=False):
                    actions.append(f"sent terminate to stale helper pid {pid}")
                    time.sleep(0.3)
                # If it still listens, force-kill.
                if pid in self._listening_pids_on_port(port):
                    if self._terminate_pid(pid, force=True):
                        actions.append(f"force-killed stale helper pid {pid}")
            else:
                actions.append(f"port {port} is used by non-Infini process pid {pid}; not killed")
        self._wait_until_helper_stops(timeout=2.0)
        return actions

    def open_sdcpp_start(self):
        self.save()
        webbrowser.open(self._server_base_url() + "/sdcpp_start")
        self.status_var.set("Opened /sdcpp_start. Если server.py ещё не запущен — сначала нажми Start server.")

    def open_sdcpp_debug(self):
        webbrowser.open(self._server_base_url() + "/sdcpp_debug")
        self.status_var.set("Opened /sdcpp_debug.")

    def open_visual_doctor(self):
        webbrowser.open(self._server_base_url() + "/visual_doctor")
        self.status_var.set("Opened /visual_doctor. Если server.py не запущен — Start server.")

    def open_visual_doctor_probe(self):
        webbrowser.open(self._server_base_url() + "/visual_doctor.json?probe=1&role=item")
        self.status_var.set("Opened live item sprite probe. Это реально дергает Z-Image без крафта.")

    def open_config(self):
        if not CONFIG_PATH.exists():
            self.save()
        os.startfile(CONFIG_PATH) if os.name == "nt" else webbrowser.open(CONFIG_PATH.as_uri())

    def open_health(self):
        webbrowser.open(self._server_base_url() + "/health")

    def validate_paths(self):
        data = self.collect()
        warnings = []
        backend = data.get("INFINI_IMAGE_BACKEND", "")
        if backend == "sdcpp" and data.get("INFINI_SDCPP_SERVER_AUTOSTART") == "1":
            exe = data.get("INFINI_SDCPP_SERVER_EXE", "")
            model = data.get("INFINI_SDCPP_MODEL", "")
            vae = data.get("INFINI_SDCPP_VAE", "")
            llm = data.get("INFINI_SDCPP_LLM", "")
            lora_file = data.get("INFINI_SDCPP_LORA_FILE", "")
            lora_dir = self._lora_dir_from_file(lora_file)
            if exe and not Path(exe).exists():
                warnings.append(f"sd-server.exe не найден: {exe}")
            if model and not Path(model).exists():
                warnings.append(f"Z-Image model не найден: {model}")
            if vae and not Path(vae).exists():
                warnings.append(f"Z-Image VAE/AE не найден: {vae}")
            if llm and not Path(llm).exists():
                warnings.append(f"Z-Image Qwen/LLM не найден: {llm}")
            if lora_file and not Path(lora_file).exists():
                warnings.append(f"LoRA file не найден: {lora_file}")
            if lora_file and lora_dir and not Path(lora_dir).exists():
                warnings.append(f"Папка LoRA, выведенная из файла, не найдена: {lora_dir}")
            if data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "").strip() and not lora_dir:
                warnings.append("LoRA prompt tags заполнены, но LoRA file не выбран — GUI не может вывести --lora-model-dir.")
            if not vae:
                warnings.append("Z-Image VAE/AE пустой: для Z-Image Turbo обычно нужен ae.safetensors.")
            if not llm:
                warnings.append("Z-Image Qwen/LLM пустой: для Z-Image Turbo обычно нужен Qwen3 *.gguf.")
        if data.get("INFINI_LLM_PROVIDER") == "openrouter" and not data.get("INFINI_OPENROUTER_API_KEY"):
            warnings.append("OpenRouter выбран, но API key пустой.")
        if backend == "image_api" and not data.get("INFINI_IMAGE_API_KEY"):
            warnings.append("Image API выбран, но API key пустой.")
        if self.radmin_enabled.get():
            url = data.get("INFINI_ASSET_PUBLIC_BASE_URL", "")
            if not url or "26.x.x.x" in url:
                warnings.append("Radmin/LAN включён, но Public asset URL не заполнен реальным Radmin IP: http://26.xxx.xxx.xxx:5055")
            if data.get("INFINI_HOST") != "0.0.0.0":
                warnings.append("Radmin/LAN включён, но Host не 0.0.0.0 — друзья не достучатся до LocalGenerator asset host.")
        if warnings:
            messagebox.showwarning("Проверка", "\n".join(warnings))
            self.status_var.set("Есть предупреждения по настройкам.")
        else:
            messagebox.showinfo("Проверка", "Критичных проблем в настройках не вижу.")
            self.status_var.set("Проверка прошла без критичных предупреждений.")

    def start_server(self):
        self.save()
        cleanup_actions: list[str] = []
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                cleanup_actions.append("terminated GUI-owned server.py")
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    cleanup_actions.append("force-killed GUI-owned server.py")
            except Exception as e:
                cleanup_actions.append(f"failed to stop GUI-owned server.py: {e}")
            self.proc = None
        cleanup_actions.extend(self._cleanup_old_helper_servers_before_start())
        try:
            snap = self._fetch_health_snapshot(timeout=1.5)
            if snap.get("ok"):
                if self._health_looks_like_infini_helper(snap):
                    warning = self._server_identity_warning(snap)
                else:
                    warning = (
                        f"Порт {self._server_port()} занят другим HTTP-сервисом, не похожим на InfiniCrafterLocal.\n"
                        "GUI не будет убивать чужой процесс автоматически."
                    )
                messagebox.showwarning("Port still busy", warning)
                self.status_var.set(f"Порт {self._server_port()} всё ещё занят; новый server.py не запускаю.")
                return
        except Exception:
            pass
        env = os.environ.copy()
        env.update(self.collect())
        cmd = [sys.executable, str(ROOT / "server.py")]
        try:
            if os.name == "nt":
                self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
            suffix = f" Старые процессы: {'; '.join(cleanup_actions[:3])}" if cleanup_actions else ""
            self.status_var.set("server.py запущен. Health откроется через пару секунд." + suffix)
            threading.Thread(target=self._delayed_health_check, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Start failed", str(e))
            self.status_var.set(f"Start failed: {e}")

    def _delayed_health_check(self):
        time.sleep(2.5)
        url = self._server_base_url() + "/health"
        try:
            snap = self._fetch_health_snapshot(timeout=10)
            if not self._health_matches_this_gui(snap):
                self.status_var.set("Health ответил, но это другая копия server.py на том же порту.")
                return
            self.status_var.set(f"Health OK: {url}")
        except Exception as e:
            self.status_var.set(f"server.py запущен, но health пока не ответил: {e}")

    def stop_server(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status_var.set("Stop signal sent to server.py")
        else:
            self.status_var.set("Нет server.py процесса, запущенного из этого GUI.")

    def on_close(self):
        self.destroy()


def main():
    app = SettingsGui()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
