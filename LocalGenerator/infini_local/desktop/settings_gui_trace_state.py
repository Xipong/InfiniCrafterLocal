from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

from infini_local.desktop.tk_compat import messagebox, simpledialog, tk, ttk
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    PRESETS,
    repair_sdcpp_command_template,
)
from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX, parse_env, save_user_preset, write_env
from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
)
from infini_local.storage import trace_tools


class SettingsGuiTraceStateMixin:
    def _current_profile_settings(self):
        data = dict(self.data)
        data.pop("INFINI_GUI_PIPELINE_PRESET", None)
        data.update({key: variable.get() for key, variable in self.vars.items()})
        data.update({key: widget.get("1.0", "end-1c") for key, widget in self.text_widgets.items()})
        return data

    def _capture_profile_baseline(self):
        self._profile_baseline = self._current_profile_settings()
        self._profile_baseline_label = self.preset_var.get()

    def _profile_settings_changed(self, *_args):
        if self.__dict__.get("_profile_edit_guard", False):
            return
        label = self.__dict__.get("_profile_baseline_label", CUSTOM_PRESET)
        if self._current_profile_settings() != self.__dict__.get("_profile_baseline", {}):
            label = CUSTOM_PRESET
        self.preset_var.set(label)

    def _profile_text_changed(self, widget):
        if widget.edit_modified():
            widget.edit_modified(False)
            self._profile_settings_changed()

    def _install_profile_tracking(self):
        self._capture_profile_baseline()
        for variable in self.vars.values():
            variable.trace_add("write", self._profile_settings_changed)
        for widget in self.text_widgets.values():
            widget.edit_modified(False)
            widget.bind("<<Modified>>", lambda _event, item=widget: self._profile_text_changed(item), add="+")

    def save_profile_as(self):
        selected = self.preset_var.get()
        initial = selected[len(USER_PRESET_PREFIX):] if selected.startswith(USER_PRESET_PREFIX) else ""
        name = simpledialog.askstring("Сохранить профиль", "Название профиля:", initialvalue=initial, parent=self)
        if name is None:
            return
        name = name.strip()
        path = CONFIG_PATH.with_name("gui_user_presets.json")
        try:
            self.user_presets = save_user_preset(path, name, self._current_profile_settings())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Профиль не сохранён", str(exc))
            self.status_var.set(f"Профиль не сохранён: {exc}")
            return
        self.preset_combo.configure(values=[CUSTOM_PRESET, *PRESETS, *(USER_PRESET_PREFIX + key for key in self.user_presets)])
        self.preset_var.set(USER_PRESET_PREFIX + name)
        self._capture_profile_baseline()
        self.status_var.set(f"Профиль «{name}» сохранён отдельно. config.env не изменён; ключи и токены в профиль не входят.")

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
        ttk.Button(bar, text="Cancel refresh", command=self.cancel_trace_refresh).pack(side="left", padx=2)
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

    @staticmethod
    def _cache_dir_from_environment(env: dict[str, str]) -> Path:
        # Match env_path() and the GUI launch cwd, including an explicit blank
        # override (Path("") == cwd). Do not expand ~ or reinterpret saved keys.
        cache = Path(env.get("INFINI_CACHE_DIR", str(ROOT / "cache")).strip())
        return (cache if cache.is_absolute() else ROOT / cache).resolve()

    def _effective_cache_dir(self) -> Path:
        env = os.environ.copy()
        env.update(self.collect())
        return self._cache_dir_from_environment(env)

    def _load_local_trace_snapshot(self, reason: str = "", cache: Path | None = None) -> dict:
        cache = cache if cache is not None else self._effective_cache_dir()
        return {
            "ok": False,
            "source": "local_cache_fallback",
            "version": "server unavailable",
            "serverRoot": str(ROOT),
            "cacheDir": str(cache),
            "pipeline": {"note": "server.py не ответил или отвечает другая копия; показан локальный cache", "reason": reason},
            "traceConfig": {"eventsFile": str(cache / "events.ndjson"), "promptTraceFile": str(cache / "prompt_trace.ndjson"), "pipelineTraceFile": str(cache / "pipeline_trace.ndjson")},
            "events": trace_tools.tail_ndjson(cache / "events.ndjson", 120),
            "promptTrace": trace_tools.tail_ndjson(cache / "prompt_trace.ndjson", 120),
            "pipelineTrace": trace_tools.tail_ndjson(cache / "pipeline_trace.ndjson", 120),
            "sdcpp": {
                "logFile": str(cache / "sdcpp_server.log"),
                "logTail": trace_tools.tail_text_file(cache / "sdcpp_server.log", 20000),
            },
            "lastCombineFailure": json.loads((cache / "last_combine_failure.json").read_text(encoding="utf-8")) if (cache / "last_combine_failure.json").exists() else None,
        }

    def _fetch_trace_snapshot(self, base_url: str | None = None) -> dict:
        base_url = base_url if base_url is not None else self._server_base_url()
        health = self._fetch_health_snapshot(timeout=8, base_url=base_url)
        if not self._health_matches_this_gui(health):
            raise RuntimeError("Trace refused: другая копия server.py")
        snap = self._read_gui_json(base_url + "/trace.json", timeout=18, max_bytes=None)
        if not self._health_matches_this_gui(snap) or snap.get("pid") != health.get("pid"):
            raise RuntimeError("Trace refused: server identity changed")
        return snap

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
        # Capture Tk/config on the UI thread before starting any I/O.
        base_url = self._server_base_url()
        cache = self._effective_cache_dir()
        self.trace_status_var.set("Loading trace…")

        def work(cancel):
            try:
                snap = self._fetch_trace_snapshot(base_url=base_url)
                return snap, "Trace loaded from server /trace.json"
            except Exception:
                if cancel.is_set():
                    return None
                reason = "server unavailable or identity mismatch"
                snap = self._load_local_trace_snapshot(reason, cache=cache)
                return snap, f"Local cache fallback: {cache} ({reason})"

        def apply(ok, result):
            if not ok or result is None:
                self.trace_status_var.set("Trace unavailable; local trace could not be read.")
                return
            snap, status = result
            self.trace_status_var.set(status)
            self._render_trace_snapshot(snap)

        self._run_gui_task("trace", work, apply)

    def cancel_trace_refresh(self):
        self._cancel_gui_task("trace")
        self.trace_status_var.set("Trace refresh cancelled; any in-flight read is being retired.")

    def _render_trace_snapshot(self, snap: dict):
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
        cache = self._effective_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        os.startfile(cache) if os.name == "nt" else webbrowser.open(cache.as_uri())
        self.status_var.set(f"Opened launch cache: {cache}")

    def clear_trace_files(self):
        if "trace-clear" in self.__dict__.get("_gui_tasks", {}):
            self.trace_status_var.set("Trace clear already in progress.")
            return
        if not messagebox.askyesno("Clear trace", "Очистить events.ndjson / prompt_trace.ndjson / pipeline_trace.ndjson?"):
            return
        base_url = self._server_base_url()
        cache = self._effective_cache_dir()
        self._cancel_gui_task("trace")
        self.trace_status_var.set("Clearing trace…")

        def work(cancel):
            try:
                health = self._fetch_health_snapshot(timeout=2, base_url=base_url)
            except Exception as exc:
                # HTTP refusals/timeouts are not proof that the selected helper
                # is offline; never truncate its files as a destructive fallback.
                if not self._connection_was_refused(exc):
                    return "Trace clear refused: server liveness/identity unavailable."
                health = None
            if cancel.is_set():
                return None
            if health is not None:
                if health.get("ok") is not True or not self._health_matches_this_gui(health):
                    return "Trace clear refused: unknown/foreign server root."
                projection = health.get("effectiveConfig") or {}
                live_cache = projection.get("cacheDir") if isinstance(projection, dict) else None
                live_cache = live_cache or health.get("cacheDir")
                if not isinstance(live_cache, str) or self._norm_path_for_compare(live_cache) != self._norm_path_for_compare(cache):
                    return "Trace clear refused: live cache differs from launch cache or is unverified. Check applied config / restart."
                reply = self._read_gui_json(base_url + "/trace_clear", timeout=4, max_bytes=64 * 1024)
                cleared = reply.get("cleared")
                expected = {self._norm_path_for_compare(cache / name) for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")}
                acknowledged = set()
                if isinstance(cleared, list):
                    for value in cleared:
                        if isinstance(value, str):
                            path = Path(value)
                            path = (path if path.is_absolute() else ROOT / path).resolve()
                            acknowledged.add(self._norm_path_for_compare(path))
                if reply.get("ok") is not True or not expected.issubset(acknowledged):
                    return "Trace clear unavailable; server did not confirm all selected trace files."
                return "Trace cleared through this server."
            paths = [cache / name for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")]
            # Refuse known linked trace/lock leaves before clearing any file;
            # folder configuration never authorizes mutation of their targets.
            if any(path.is_symlink() or path.with_name(path.name + ".lock").is_symlink() for path in paths):
                return "Trace clear refused: linked trace/lock file outside the selected-file contract."
            for path in paths:
                if cancel.is_set():
                    return None
                trace_tools.clear_ndjson(path)
            return f"Trace cleared locally: {cache}"

        def apply(ok, result):
            self.trace_status_var.set(result if ok and result else "Trace clear unavailable; not confirmed.")
            if ok and result and result.startswith("Trace cleared"):
                self.refresh_trace()

        self._run_gui_task("trace-clear", work, apply)

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
        llm_enabled = self._value("INFINI_USE_LLM", "1") == "1"
        backend = (self._value("INFINI_IMAGE_BACKEND", "sdcpp") or "sdcpp").lower()
        visual_mode = (self._value("INFINI_VISUAL_ASSET_MODE", "full") or "full").lower()
        reasoning_mode = (self._value("INFINI_LLM_REASONING_MODE", "off") or "off").lower().replace("-", "_")
        remove_bg = self._value("INFINI_REMOVE_BG", "1") == "1"
        bg_mode = (self._value("INFINI_BG_REMOVE_MODE", "sprite_keyer") or "sprite_keyer").lower().replace("-", "_")
        transparent_bg = self._value("INFINI_BG_COLOR", "magenta").lower() == "transparent"
        posterize = self._value("INFINI_PIXEL_POSTERIZE", "1") == "1"
        strict_ai = self._value("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1"
        attack_consumable_debug = self._value("INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED", "0") == "1"
        asset_transport = (self._value("INFINI_MP_ASSET_TRANSPORT", "native") or "native").lower()

        local_llm = ["INFINI_LMSTUDIO_URL", "INFINI_LMSTUDIO_MODEL"]
        openrouter_llm = [
            "INFINI_OPENROUTER_API_KEY", "INFINI_OPENROUTER_MODEL", "INFINI_OPENROUTER_PROVIDER",
            "INFINI_OPENROUTER_HTTP_REFERER", "INFINI_OPENROUTER_APP_TITLE",
        ]
        compat_llm = ["INFINI_OPENAI_COMPAT_BASE_URL", "INFINI_OPENAI_COMPAT_API_KEY", "INFINI_OPENAI_COMPAT_MODEL"]
        for key in local_llm:
            self._set_field_enabled(key, provider == "local", f"LLM provider сейчас `{provider}`, локальные LM Studio поля не используются.")
        for key in openrouter_llm:
            self._set_field_enabled(key, provider == "openrouter", f"LLM provider сейчас `{provider}`, OpenRouter поля не используются.")
        for key in compat_llm:
            self._set_field_enabled(key, provider == "openai_compat", f"LLM provider сейчас `{provider}`, compat API поля не используются.")
        self._set_field_enabled("INFINI_CODEX_LLM_MODEL", provider == "openai_codex" and llm_enabled, "Текстовая Codex-модель используется только при LLM provider=openai_codex и Use LLM=1.")
        self._set_field_enabled("INFINI_CODEX_VISUAL_REASONING", provider == "openai_codex" and llm_enabled, "Reasoning Visual Director используется только при текстовом Codex provider.")
        self._set_field_enabled("INFINI_LLM_MAX_TOKENS", provider != "openai_codex", "Codex /responses отвергает max_output_tokens; числовой лимит не отправляется и не ограничивает квоту.")
        if hasattr(self, "codex_reasoning_combo"):
            if provider == "openai_codex":
                self._update_codex_efforts()
            else:
                self.codex_reasoning_combo.configure(values=["off", "auto", "none", "minimal", "low", "medium", "high", "xhigh", "tokens", "prompt_light", "prompt_strong"])
                self.codex_visual_reasoning_combo.configure(values=["inherit", "model_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"])
        for key in ("INFINI_LLM_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE", "INFINI_VISUAL_DIRECTOR_TEMPERATURE"):
            enabled = provider != "openai_codex" and (llm_enabled or key != "INFINI_LLM_REAUTHOR_TEMPERATURE")
            reason = ("Codex /responses не принимает temperature; значение сохраняется для других провайдеров."
                      if provider == "openai_codex" else "Use LLM=0; scoped same-author repair не вызывается.")
            getattr(self, "_set_field_enabled")(key, enabled, reason)

        set_field_enabled = getattr(self, "_set_field_enabled")
        set_field_enabled("INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD", attack_consumable_debug, "Debug minimum выключен; поставь галочку выше, чтобы выбрать batch size.")
        for slot in (2, 3, 4):
            enabled = self._value(f"INFINI_LLM_POOL_{slot}_ENABLED", "0") == "1"
            for suffix in ("PROVIDER", "BASE_URL", "API_KEY", "MODEL", "API_MODE"):
                set_field_enabled(
                    f"INFINI_LLM_POOL_{slot}_{suffix}",
                    enabled,
                    f"LLM {slot} выключен; сначала установи Enabled = 1.",
                )

            set_field_enabled(
                f"INFINI_LLM_POOL_{slot}_OPENROUTER_PROVIDER",
                enabled and self._value(f"INFINI_LLM_POOL_{slot}_PROVIDER", "openai_compat").lower() == "openrouter",
                "Фиксация upstream доступна только для включённого OpenRouter профиля.",
            )
        fallback_provider = (self._value("INFINI_LLM_FALLBACK_PROVIDER", "") or provider).lower()
        set_field_enabled(
            "INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER",
            fallback_provider == "openrouter" and bool(self._value("INFINI_LLM_FALLBACK_MODEL", "")),
            "Нужны fallback model и OpenRouter в качестве fallback provider.",
        )

        off_modes = {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}
        prompt_modes = {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}
        api_reasoning_active = provider != "local" and reasoning_mode not in off_modes and reasoning_mode not in prompt_modes
        self._set_field_enabled(
            "INFINI_LLM_REASONING_MAX_TOKENS",
            api_reasoning_active and provider != "openai_codex" and reasoning_mode in {"tokens", "token_budget", "max_tokens", "budget"},
            "Codex не поддерживает reasoning token budget; у других провайдеров работает при mode=tokens.",
        )
        self._set_field_enabled(
            "INFINI_LLM_REASONING_EXCLUDE",
            api_reasoning_active and provider != "openai_codex",
            "Codex /responses не принимает exclude; другие API могут использовать этот флаг для reasoning output.",
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
        for key in ("INFINI_CODEX_IMAGE_MODEL", "INFINI_CODEX_IMAGE_QUALITY", "INFINI_CODEX_IMAGE_SIZE", "INFINI_CODEX_IMAGE_TIMEOUT"):
            self._set_field_enabled(key, backend == "openai_codex", "Эти поля используются только backend openai_codex.")
        for key in image_api_keys:
            self._set_field_enabled(key, backend == "image_api", f"Image backend сейчас `{backend}`, Image API поля не участвуют.")
        self._set_field_enabled("INFINI_A1111_URL", backend == "a1111", f"Image backend сейчас `{backend}`, A1111 URL не используется.")
        self._set_field_enabled("INFINI_COMFYUI_URL", backend == "comfyui", f"Image backend сейчас `{backend}`, ComfyUI URL не используется.")

        if asset_transport != "http":
            self._set_field_enabled("INFINI_ASSET_PUBLIC_BASE_URL", False, "Asset transport=native; PNG идут через Terraria packets, внешний URL не используется.")
        elif not self.radmin_enabled.get():
            self._set_field_enabled("INFINI_ASSET_PUBLIC_BASE_URL", False, "Radmin/LAN overlay выключен; внешний URL ассетов не нужен для локальной игры.")
        else:
            self._set_field_enabled("INFINI_ASSET_PUBLIC_BASE_URL", True, "")

        image_active = backend != "off"
        asset_pack_active = image_active and visual_mode in {"full", "all", "projectile", "visualpack", "assetpack"}

        for key in ["INFINI_VISUAL_DIRECTOR_LLM", "INFINI_VFX_LLM_DIRECTOR"]:
            self._set_field_enabled(key, asset_pack_active, "Visual asset mode сейчас off или image backend выключен; director-pass не вызывается.")
        self._set_field_enabled("INFINI_IMAGE_MAX_CONCURRENCY", image_active, "Image backend=off; image request gate не участвует.")

        sprite_processing_active = image_active
        for key in [
            "INFINI_REMOVE_BG", "INFINI_SPRITE_RETRIES",
            "INFINI_PIXEL_POSTERIZE", "INFINI_VISUAL_STRICT_AI_AUTHORSHIP",
        ]:
            self._set_field_enabled(key, sprite_processing_active, "Image backend = off; PNG не генерируются, sprite postprocess не запускается.")
        alpha_reason = "Модель запрашивается с alpha; локальный keyer не применяется."
        keyer_reason = alpha_reason if sprite_processing_active else "Image backend=off; sprite postprocess не запускается."
        # Legacy enabled mode aliases still use the same local sprite_keyer.
        sprite_keyer_active = sprite_processing_active and remove_bg and not transparent_bg and bg_mode not in {"off", "none"}
        self._set_field_enabled("INFINI_REMOVE_BG", sprite_processing_active and not transparent_bg, keyer_reason)
        self._set_field_enabled("INFINI_BG_REMOVE_MODE", sprite_keyer_active, keyer_reason)
        for key in ["INFINI_CHROMA_TOLERANCE", "INFINI_SPRITE_KEYER_SPILL_RADIUS",
                    "INFINI_SPRITE_KEYER_RESIDUE_STEPS", "INFINI_SPRITE_CHROMA_DEFRINGE"]:
            self._set_field_enabled(key, sprite_keyer_active, keyer_reason)
        # Keep the background selector available so native-alpha mode is escapable.
        self._set_field_enabled("INFINI_BG_COLOR", sprite_processing_active, "Image backend=off; фон не запрашивается.")
        # Hard-alpha item cleanup still uses this threshold with native alpha.
        self._set_field_enabled("INFINI_ALPHA_THRESHOLD", sprite_processing_active, "Image backend=off; alpha cleanup не запускается.")
        self._set_field_enabled("INFINI_MAX_COLORS", sprite_processing_active and posterize, "Max colors используется только когда Posterize=1 и image backend не off.")

        if sprite_processing_active:
            self._set_field_enabled("INFINI_SPRITE_MASTER_CANVAS", True, "")
            self._set_field_enabled("INFINI_SPRITE_DOWNSCALE_FILTER", True, "")
            self._set_field_enabled("INFINI_SPRITE_PREMULTIPLIED_RESIZE", True, "")

        if strict_ai:
            if "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK" in self.vars:
                self.vars["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"].set("0")
            self._set_field_enabled("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", False, "Strict AI authorship=1: procedural fallback принудительно выключен, чтобы код не авторил картинку за модель.")
        else:
            self._set_field_enabled("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", sprite_processing_active, "Image backend=off; fallback PNG не нужен.")
        if "advanced_var" in self.__dict__:
            self._apply_view_mode()

    def collect(self) -> dict[str, str]:
        data = parse_env(CONFIG_PATH) if CONFIG_PATH.exists() else dict(DEFAULTS)
        data.update(self.__dict__.get("_profile_extra_settings", {}))
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
        # on top of local/OpenRouter/image_api/etc. Native packets do not expose the
        # LocalGenerator HTTP listener; HTTP asset mode requires the LAN/Radmin bind.
        asset_transport = "http" if (data.get("INFINI_MP_ASSET_TRANSPORT") or "native").strip().lower() == "http" else "native"
        data["INFINI_MP_ASSET_TRANSPORT"] = asset_transport
        if "INFINI_MP_ASSET_TRANSPORT" in self.vars:
            self.vars["INFINI_MP_ASSET_TRANSPORT"].set(asset_transport)
        if self.radmin_enabled.get() and asset_transport == "http":
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
                tag = self._lora_tag_from_file(lora_file, data.get("INFINI_SDCPP_LORA_WEIGHT", "0.25"))
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
        if "applied_config_var" in self.__dict__:
            self._update_applied_config_feedback("Saved")

    def apply_preset(self):
        preset_name = self.preset_var.get()
        is_user = preset_name.startswith(USER_PRESET_PREFIX)
        preset = self.__dict__.get("user_presets", {}).get(preset_name[len(USER_PRESET_PREFIX):]) if is_user else PRESETS.get(preset_name)
        if preset is None:
            self.status_var.set("Свои настройки сохранены без изменений. Для применения выбери готовый профиль.")
            return
        resize_choices = {} if is_user else {
            "INFINI_SPRITE_DOWNSCALE_FILTER": {"box", "bilinear", "bicubic", "lanczos"},
            "INFINI_SPRITE_PREMULTIPLIED_RESIZE": {"0", "1"},
        }
        self._profile_edit_guard = True
        try:
            for key, value in preset.items():
                if is_user and key in self.text_widgets:
                    widget = self.text_widgets[key]
                    widget.delete("1.0", "end")
                    widget.insert("1.0", value)
                    widget.edit_modified(False)
                elif key in self.vars:
                    # Pipeline selection does not discard explicit resize preferences.
                    if key in resize_choices and self._value(key).lower() in resize_choices[key]:
                        continue
                    self.vars[key].set(value)
                if is_user:
                    self.data[key] = value
            if is_user:
                self._profile_extra_settings = {key: value for key, value in preset.items()
                    if key not in self.vars and key not in self.text_widgets}
                self.radmin_enabled.set(self._current_profile_settings().get("INFINI_HOST") == "0.0.0.0")
            self.data["INFINI_GUI_PIPELINE_PRESET"] = preset_name
            self._refresh_visibility()
        finally:
            self._profile_edit_guard = False
        if "_profile_baseline" in self.__dict__:
            self._capture_profile_baseline()
        self.status_var.set("Профиль применён. Нажми «Сохранить», чтобы записать config.env; работающий сервер применит изменения после перезапуска.")

    def on_radmin_toggle(self):
        if self.radmin_enabled.get():
            self.apply_radmin_overlay(status_only=False)
        else:
            self.apply_local_overlay(status_only=False)

    def apply_radmin_overlay(self, status_only: bool = True):
        self.radmin_enabled.set(True)
        if "INFINI_HOST" in self.vars:
            self.vars["INFINI_HOST"].set("0.0.0.0" if self._value("INFINI_MP_ASSET_TRANSPORT", "native").lower() == "http" else "127.0.0.1")
        if (self._value("INFINI_MP_ASSET_TRANSPORT", "native").lower() == "http"
                and "INFINI_ASSET_PUBLIC_BASE_URL" in self.vars
                and not self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].get().strip()):
            best = self._best_radmin_ip()
            self.vars["INFINI_ASSET_PUBLIC_BASE_URL"].set(f"http://{best}:5055" if best else "http://26.x.x.x:5055")
        self._update_radmin_info()
        host = self.vars.get("INFINI_HOST", tk.StringVar(value="127.0.0.1")).get().strip()
        self.status_var.set(f"Radmin/LAN overlay включён: host={host}. Друзья получают только готовый item JSON + PNG ассеты, не LLM/prompts.")
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
        transport = self._value("INFINI_MP_ASSET_TRANSPORT", "native").lower()
        terraria_port = self.vars.get("INFINI_TERRARIA_PORT", tk.StringVar(value="7777")).get().strip() if hasattr(self, "vars") else self.data.get("INFINI_TERRARIA_PORT", "7777")
        url_text = (url or "не задан") if transport == "http" else "не нужен (Native)"
        return (f"Radmin IP: {ip_text}.  Terraria друзьям: Join via IP → <Radmin IP>:{terraria_port}.  "
                f"Asset transport: {transport}.  Asset URL: {url_text}.  Друзьям не нужен LLM/image pipeline.")

    def _update_radmin_info(self):
        if hasattr(self, "radmin_info_var"):
            self.radmin_info_var.set(self._radmin_status_text())

    def autofill_radmin_url(self):
        self.radmin_enabled.set(True)
        if "INFINI_MP_ASSET_TRANSPORT" in self.vars:
            self.vars["INFINI_MP_ASSET_TRANSPORT"].set("http")
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
        transport = self._value("INFINI_MP_ASSET_TRANSPORT", "native").lower()
        asset_url = self.vars.get("INFINI_ASSET_PUBLIC_BASE_URL", tk.StringVar(value=f"http://{ip}:5055")).get().strip() or f"http://{ip}:5055"
        asset_step = (f"3) Для проверки HTTP-ассетов открой: {asset_url}/health\n"
                      if transport == "http"
                      else "3) PNG идут через Terraria/tModLoader packets; Public asset URL не нужен.\n")
        return ("Как подключиться к моей Terraria / InfiniCrafterLocal:\n"
                "1) Запусти Radmin VPN и зайди в нашу общую сеть.\n"
                f"2) Terraria/tModLoader → Multiplayer → Join via IP → {ip} → Port {port}.\n"
                f"{asset_step}"
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
