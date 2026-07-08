from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path, PureWindowsPath

from infini_local.desktop.tk_compat import filedialog, messagebox, tk, ttk
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    FIELD_HELP,
    FIELD_ORDER,
    OPTION_HELP,
    PRESETS,
    PRESET_HELP,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_EXTRA_FLAG_SPECS,
    SDCPP_EXTRA_PROFILES,
    SDCPP_EXTRA_PROFILE_HELP,
    repair_sdcpp_command_template,
)
from infini_local.desktop.settings_env import parse_env, quote_env_value, write_env
from infini_local.desktop.settings_widgets import ScrollFrame, ToolTip
from infini_local.desktop.settings_sdcpp_args import (
    extra_option_names,
    join_extra_for_gui,
    remove_extra_options,
    split_extra_for_gui,
)
from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
    EXAMPLE_PATH,
    APP_TITLE,
    APP_BG,
    APP_PANEL_BG,
    CARD_BG,
    CARD_MUTED_BG,
    HEADER_BG,
    HEADER_BG_2,
    TEXT_FG,
    MUTED_FG,
    SOFT_FG,
    ACCENT_BG,
    ACCENT_HOVER_BG,
    ACCENT_SOFT_BG,
    ACCENT_FG,
    SUCCESS_BG,
    SUCCESS_SOFT_BG,
    SUCCESS_FG,
    DANGER_BG,
    DANGER_SOFT_BG,
    DANGER_FG,
    WARNING_SOFT_BG,
    WARNING_FG,
    BORDER_FG,
    BORDER_DARK_FG,
)


class SettingsGuiImageArgsMixin:
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

    _split_extra_for_gui = staticmethod(split_extra_for_gui)
    _join_extra_for_gui = staticmethod(join_extra_for_gui)
    _extra_option_names = staticmethod(extra_option_names)
    _remove_extra_options = staticmethod(remove_extra_options)


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

__all__ = ["SettingsGuiImageArgsMixin"]
