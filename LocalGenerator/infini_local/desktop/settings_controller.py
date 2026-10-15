from __future__ import annotations

"""Plain Python settings and lifecycle state for the local browser Studio.

Only the control loop mutates this object. I/O workers capture plain inputs and
return results through queues; HTTP workers read published immutable snapshots.
"""

import heapq
import itertools
import re
import time
from pathlib import Path, PureWindowsPath

from infini_local.desktop.settings_env import (
    CUSTOM_PRESET, USER_PRESET_PREFIX, load_user_presets, parse_env, write_env,
)
from infini_local.desktop.settings_schema import DEFAULTS, PRESETS, repair_sdcpp_command_template
from infini_local.desktop.settings_paths import CONFIG_PATH, EXAMPLE_PATH
from infini_local.desktop.settings_fields import FIELDS, disabled_reasons
from infini_local.desktop.studio_operations import StudioOperations
from infini_local.desktop.settings_interactions import notify


class SettingsController(StudioOperations):
    def __init__(self, config_path=None, *, example_path=None):
        self.config_path = Path(config_path) if config_path is not None else CONFIG_PATH
        self.example_path = Path(example_path) if example_path is not None else EXAMPLE_PATH
        self.values = parse_env(self.config_path if self.config_path.exists() else self.example_path)
        self.proc = None
        self._gui_closed = False
        self._gui_tasks = {}
        self._applied_config_ack = None
        self._server_lifecycle = "unknown"
        self._health_after_id = None
        self._scheduled = []
        self._scheduled_ids = set()
        self._schedule_sequence = itertools.count()
        self.lan_enabled = self.values.get("INFINI_HOST") == "0.0.0.0" or bool(self.values.get("INFINI_ASSET_PUBLIC_BASE_URL"))
        self.status = "Готово. Выбери профиль генерации, сохрани настройки и запусти сервер."
        self.activity = "Backend activity not checked."
        self.applied_config = "Runtime config not checked (partial non-secret projection; pools/secrets unverified)."
        self.trace_status = "Нажми Refresh trace. Если сервер не запущен, Studio покажет локальные cache/*.ndjson."
        self.trace = dict.fromkeys(("summary", "prompts", "pipeline", "events", "sdcpp", "failure"), "")
        self.codex_catalog = "Текстовый каталог ещё не загружен. Войди в Codex и обнови модели."
        self.codex_image_account = "Image-доступ не проверен."
        self._codex_text_models = {}
        self.codex_models = [self._value("INFINI_CODEX_LLM_MODEL")] if self._value("INFINI_CODEX_LLM_MODEL") else []
        self.codex_efforts = ["off", "none", "minimal", "low", "medium", "high", "xhigh"]
        self.codex_visual_efforts = ["inherit", "model_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"]
        self.user_presets = {}
        try:
            self.user_presets = load_user_presets(self.config_path.with_name("gui_user_presets.json"))
        except (OSError, ValueError) as exc:
            self.status = f"Пользовательские профили не загружены: {exc}"
        self.preset = self._pipeline_preset_from_config(self.values, self.user_presets)
        self._capture_profile_baseline()
        self._refresh_visibility()

    def after(self, milliseconds, callback):
        """Schedule control-loop work without a GUI toolkit or timer thread."""
        identifier = next(self._schedule_sequence)
        heapq.heappush(self._scheduled, (time.monotonic() + milliseconds / 1000, identifier, callback))
        self._scheduled_ids.add(identifier)
        return identifier

    def after_cancel(self, identifier):
        self._scheduled_ids.discard(identifier)

    def cancel_scheduled(self):
        self._scheduled.clear()
        self._scheduled_ids.clear()

    def pump(self):
        # Bound each pass so repeated callbacks cannot starve HTTP commands.
        for _ in range(64):
            if self._gui_closed or not self._scheduled or self._scheduled[0][0] > time.monotonic():
                return
            _, identifier, callback = heapq.heappop(self._scheduled)
            if identifier in self._scheduled_ids:
                self._scheduled_ids.remove(identifier)
                callback()

    def _value(self, key, default=""):
        return self.values.get(key, DEFAULTS.get(key, default)).strip()

    def _current_profile_settings(self):
        return {key: value for key, value in self.values.items() if key != "INFINI_GUI_PIPELINE_PRESET"}

    def _capture_profile_baseline(self):
        self._profile_baseline = self._current_profile_settings()
        self._profile_baseline_label = self.preset

    def update_values(self, values, *, lan_enabled=None):
        self.values.update(values)
        if "INFINI_GUI_PIPELINE_PRESET" in values:
            self.preset = values["INFINI_GUI_PIPELINE_PRESET"]
        elif self._current_profile_settings() != self._profile_baseline:
            self.preset = CUSTOM_PRESET
        else:
            self.preset = self._profile_baseline_label
        if lan_enabled is not None:
            self.lan_enabled = bool(lan_enabled)
        self._refresh_visibility()
        self._update_applied_config_feedback()
        if "INFINI_CODEX_LLM_MODEL" in values:
            self._update_codex_efforts()

    def _refresh_visibility(self):
        if self._value("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1":
            self.values["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
        self.field_disabled_reasons = disabled_reasons(self.values, self.lan_enabled)

    def collect(self):
        data = parse_env(self.config_path) if self.config_path.exists() else dict(DEFAULTS)
        editable_keys = {field["key"] for field in FIELDS}
        # Unknown/manual extension settings are opaque wire values, not widgets.
        data.update({key: value.strip() if key in editable_keys else value
                     for key, value in self.values.items()})
        data["INFINI_GUI_PIPELINE_PRESET"] = self.preset.strip()
        data["INFINI_SDCPP_SERVER_EXTRA_ARGS"] = " ".join(data.get("INFINI_SDCPP_SERVER_EXTRA_ARGS", "").split())
        template, repaired, reason = repair_sdcpp_command_template(data.get("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", ""))
        if repaired:
            data["INFINI_SDCPP_SERVER_COMMAND_TEMPLATE"] = template
            data["INFINI_SDCPP_SERVER_COMMAND_MODE"] = "safe_args"
            self.status = f"sd.cpp command template repaired on save: {reason}"
        transport = "http" if data.get("INFINI_MP_ASSET_TRANSPORT", "native").lower() == "http" else "native"
        data["INFINI_MP_ASSET_TRANSPORT"] = transport
        if self.lan_enabled and transport == "http":
            data["INFINI_HOST"] = "0.0.0.0"
        else:
            if data.get("INFINI_HOST") == "0.0.0.0":
                data["INFINI_HOST"] = "127.0.0.1"
            if data.get("INFINI_ASSET_PUBLIC_BASE_URL", "").startswith("http://26."):
                data["INFINI_ASSET_PUBLIC_BASE_URL"] = ""
        lora_file = data.get("INFINI_SDCPP_LORA_FILE", "")
        if lora_file:
            data["INFINI_SDCPP_LORA_DIR"] = self._lora_dir_from_file(lora_file) or str(Path(lora_file).parent)
            if not data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", ""):
                data["INFINI_SDCPP_LORA_PROMPT_TAGS"] = self._lora_tag_from_file(lora_file, data.get("INFINI_SDCPP_LORA_WEIGHT", "0.25"))
        else:
            data["INFINI_SDCPP_LORA_DIR"] = ""
        if data.get("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1":
            data["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
        # Only canonicalized launch fields change draft state, never unrelated
        # disk values that were read to preserve extension keys.
        for key in ("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", "INFINI_SDCPP_SERVER_COMMAND_MODE",
                    "INFINI_MP_ASSET_TRANSPORT", "INFINI_HOST", "INFINI_ASSET_PUBLIC_BASE_URL",
                    "INFINI_SDCPP_LORA_DIR", "INFINI_SDCPP_LORA_PROMPT_TAGS", "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"):
            if key in data:
                self.values[key] = data[key]
        return data

    def save(self):
        data = self.collect()
        write_env(self.config_path, data)
        self.values = data
        self.status = f"Saved: {self.config_path}"
        self._update_applied_config_feedback("Saved")

    def apply_preset(self):
        is_user = self.preset.startswith(USER_PRESET_PREFIX)
        preset = self.user_presets.get(self.preset[len(USER_PRESET_PREFIX):]) if is_user else PRESETS.get(self.preset)
        if preset is None:
            self.status = "Свои настройки сохранены без изменений. Для применения выбери готовый профиль."
            return
        resize_choices = {} if is_user else {
            "INFINI_SPRITE_DOWNSCALE_FILTER": {"box", "bilinear", "bicubic", "lanczos"},
            "INFINI_SPRITE_PREMULTIPLIED_RESIZE": {"0", "1"},
        }
        for key, value in preset.items():
            if key in resize_choices and self._value(key).lower() in resize_choices[key]:
                continue
            self.values[key] = value
        if is_user:
            self.lan_enabled = self.values.get("INFINI_HOST") == "0.0.0.0"
        self.values["INFINI_GUI_PIPELINE_PRESET"] = self.preset
        self._refresh_visibility()
        self._capture_profile_baseline()
        self.status = "Профиль применён. Нажми «Сохранить», чтобы записать config.env; работающий сервер применит изменения после перезапуска."

    @staticmethod
    def _lora_tag_from_file(path, weight):
        raw = str(path or "").strip()
        stem = (PureWindowsPath(raw).stem if "\\" in raw or ":" in raw else Path(raw).stem).strip()
        return f"<lora:{stem}:{str(weight or '0.25').strip() or '0.25'}>" if stem else ""

    @staticmethod
    def _lora_dir_from_file(path):
        raw = str(path or "").strip()
        if not raw:
            return ""
        parent = PureWindowsPath(raw).parent if "\\" in raw or ":" in raw else Path(raw).parent
        return "" if str(parent) in {"", "."} else str(parent)

    def use_selected_lora(self):
        path = self._value("INFINI_SDCPP_LORA_FILE")
        if not path:
            notify(self, "warning", "LoRA", "Сначала выбери LoRA file (*.safetensors/*.ckpt).")
            return {"ok": False, "message": "Сначала выбери файл LoRA."}
        directory = self._lora_dir_from_file(path) or str(Path(path).parent)
        tag = self._lora_tag_from_file(path, self._value("INFINI_SDCPP_LORA_WEIGHT", "0.25"))
        tags = self._value("INFINI_SDCPP_LORA_PROMPT_TAGS")
        if tag not in tags:
            tags = (tags.rstrip() + " " + tag).strip()
        self.values.update(INFINI_SDCPP_LORA_DIR=directory, INFINI_SDCPP_LORA_PROMPT_TAGS=tags)
        self.status = f"LoRA подключена: --lora-model-dir {directory} + {tag}"

    def clear_lora_settings(self):
        for key in ("INFINI_SDCPP_LORA_FILE", "INFINI_SDCPP_LORA_DIR", "INFINI_SDCPP_LORA_PROMPT_TAGS"):
            self.values[key] = ""
        self.status = "LoRA file, prompt tags и LoRA dir очищены."

    def reset_sprite_resize(self):
        for key in ("INFINI_SPRITE_DOWNSCALE_FILTER", "INFINI_SPRITE_PREMULTIPLIED_RESIZE"):
            self.values[key] = DEFAULTS[key]
        self.status = "Base resize: BOX, premultiplied RGBA=1. Нажми Save, чтобы сохранить."
        self._refresh_visibility()

    @staticmethod
    def _pipeline_preset_from_config(data: dict[str, str], user_presets: dict[str, dict[str, str]] | None = None) -> str:
        saved = str(data.get("INFINI_GUI_PIPELINE_PRESET", "") or "").strip()
        if saved == CUSTOM_PRESET:
            return CUSTOM_PRESET
        if saved.startswith(USER_PRESET_PREFIX):
            preset = (user_presets or {}).get(saved[len(USER_PRESET_PREFIX):])
            return saved if preset is not None and all(data.get(key, DEFAULTS.get(key, "")) == value for key, value in preset.items()) else CUSTOM_PRESET
        if saved in PRESETS:
            saved_preset = PRESETS[saved]
            if all(
                str(data.get(key, DEFAULTS.get(key, ""))).strip() == str(value).strip()
                for key, value in saved_preset.items()
            ):
                return saved
        provider = str(data.get("INFINI_LLM_PROVIDER", "") or "").strip().lower()
        backend = str(data.get("INFINI_IMAGE_BACKEND", "") or "").strip().lower()
        extra_args = str(data.get("INFINI_SDCPP_SERVER_EXTRA_ARGS", "") or "").strip().lower()
        steps = str(data.get("INFINI_SDCPP_STEPS", "") or "").strip()
        if (
            provider == "openai_compat"
            and backend == "sdcpp"
            and "diffusion=rocm0,vae=vulkan0,te=rocm0" in extra_args
            and steps == "4"
        ):
            return "OpenAI-compatible + FLUX.2 Klein 4B hybrid"
        if provider == "local" and backend == "sdcpp":
            return "Локалка: LM Studio + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "sdcpp":
            return "OpenRouter + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "image_api":
            return "OpenRouter + Image API"
        if provider == "openrouter" and backend in {"off", "none", "disabled", "0"}:
            return "API LLM only: без картинок"

        # Shared sprite controls do not establish provider/backend identity.
        # Never present a nearest-score preset as the user's active pipeline.
        return CUSTOM_PRESET

    def refresh_home(self):
        raw = self.status.lower()
        applied = self.applied_config
        applied_text = applied.lower() if applied is not None else ""
        busy = "server-action" in self.__dict__.get("_gui_tasks", {}) or "checking" in raw or "checking" in applied_text
        ack = self.__dict__.get("_applied_config_ack")
        lifecycle = self.__dict__.get("_server_lifecycle", "unknown")
        if busy:
            title, detail = "Проверяем состояние…", "Перед действием проверяем сервер и текущую генерацию. Интерфейс остаётся доступным."
        elif any(word in raw for word in ("refused", "failed", "unavailable", "unconfirmed", "not stopped", "ошиб", "не удалось")):
            title, detail = "Нужно внимание", "Действие не выполнено. Подробности и исходное сообщение доступны в разделе «Диагностика»."
        elif lifecycle == "stopped":
            title, detail = "Сервер остановлен", "Можно изменить настройки или запустить генератор снова."
        elif lifecycle == "starting":
            title, detail = "Сервер запускается", "Процесс запущен. Ждём подтверждения соединения; готовность ещё не проверена."
        elif ack:
            title, detail = "Сервер отвечает", "Получен ответ от сервера этой копии генератора. Полная проверка всех настроек и ключей не выполнялась."
        elif "unconfirmed" in applied_text:
            title, detail = "Соединение не подтверждено", "Сервер недоступен или его принадлежность этой копии не подтверждена. Проверь диагностику; чужие процессы не изменяются."
        else:
            title, detail = "Состояние ещё не проверено", "Настройки готовы к редактированию. Нажми «Проверить соединение» или запусти сервер."
        activity = self.activity
        snapshot = re.match(r"Backend last health snapshot: active=(\d+), waiting=(\d+), accepting=(True|False)", activity) if activity is not None else None
        if ack and snapshot and not busy and title == "Сервер отвечает":
            active, waiting = int(snapshot[1]), int(snapshot[2])
            if active or waiting:
                title = "Идёт генерация"
                detail = f"Последний снимок сервера: создаётся {active}, в очереди {waiting}. Для актуального состояния нажми «Проверить соединение»."
        self.home_state = title
        self.home_detail = detail
        config_note = "Изменения настроек применяются после безопасного перезапуска сервера. Ключи скрыты и не копируются в профили."
        if "restart" in applied_text or "differs" in applied_text:
            config_note = "Настройки изменены. Ответ сервера не подтверждает новые значения — нужен безопасный перезапуск."
        elif "matches" in applied_text:
            config_note = "Проверяемая часть настроек совпадает с сервером. Ключи и дополнительные модели этой проверкой не подтверждаются."
        self.home_config = config_note
