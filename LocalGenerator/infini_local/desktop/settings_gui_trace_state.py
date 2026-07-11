from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

from infini_local.desktop.tk_compat import messagebox, tk, ttk
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    PRESETS,
    repair_sdcpp_command_template,
)
from infini_local.desktop.settings_env import parse_env, write_env
from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
)


class SettingsGuiTraceStateMixin:
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
            "INFINI_SDCPP_SERVER_EXE", "INFINI_SDCPP_ROCM_COMPAT_ROOT", "INFINI_SDCPP_MODEL", "INFINI_SDCPP_VAE", "INFINI_SDCPP_LLM",
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

__all__ = ["SettingsGuiTraceStateMixin"]
