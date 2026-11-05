from __future__ import annotations

"""Plain Python settings and lifecycle state for the local browser Studio.

Only the control loop mutates this object. I/O workers capture plain inputs and
return results through queues; HTTP workers read published immutable snapshots.
"""

import heapq
import itertools
import os
import time
from pathlib import Path

from infini_local.desktop.settings_env import (
    CUSTOM_PRESET, USER_PRESET_PREFIX, load_user_presets, parse_env, write_env,
)
from infini_local.desktop.settings_schema import DEFAULTS, PRESETS
from infini_local.core.app_paths import CONFIG_PATH, EXAMPLE_PATH
from infini_local.core.config_migration import migrate_config_file, environment_migration_status, explicit_config_keys
from infini_local.core.env_utils import env_str
from infini_local.core.server_endpoint import resolve_server_endpoint
from infini_local.desktop.settings_fields import FIELDS, disabled_reasons
from infini_local.desktop.studio_operations import StudioOperations
from infini_local.desktop.settings_interactions import StudioActions
from infini_local.services.sdcpp_backend import DEFAULT_COMMAND_TEMPLATE, lora_dir_from_file, lora_tag_from_file, repair_command_template


class SettingsController(StudioOperations):
    def __init__(self, config_path=None, *, example_path=None):
        self.config_path = Path(config_path) if config_path is not None else CONFIG_PATH
        self.example_path = Path(example_path) if example_path is not None else EXAMPLE_PATH
        migrate_config_file(self.config_path, environment=os.environ)
        self.values = self.read_saved_settings()
        self.proc = None
        self._gui_closed = False
        self.actions = StudioActions(self)
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
        self.user_presets = {}
        try:
            self.user_presets = load_user_presets(self.config_path.with_name("gui_user_presets.json"))
        except (OSError, ValueError) as exc:
            self.status = f"Пользовательские профили не загружены: {exc}"
        self.preset = self._pipeline_preset_from_config(self.values, self.user_presets)
        self._capture_profile_baseline()
        self._refresh_visibility()

    def read_saved_settings(self):
        from infini_local.desktop.settings_env import parse_env as read_settings
        source = self.config_path if self.config_path.exists() else self.example_path
        values = read_settings(source)
        changes = environment_migration_status()['changes']
        if not changes:
            return values
        explicit = explicit_config_keys(self.config_path)
        # A migrated inherited value must not disappear behind UI defaults on a
        # fresh install. Actual canonical file fields still have precedence.
        for change in changes:
            target = change.get('target', '')
            if target in os.environ and (not self.config_path.exists() or target not in explicit):
                values[target] = env_str(target, strip=False)
        return values

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

    def _refresh_visibility(self):
        if self._value("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1":
            self.values["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
        self.field_disabled_reasons = disabled_reasons(self.values, self.lan_enabled)

    def collect(self, values=None, *, preset=None, lan_enabled=None):
        draft = self.values if values is None else values
        preset = self.preset if preset is None else preset
        lan_enabled = self.lan_enabled if lan_enabled is None else lan_enabled
        data = parse_env(self.config_path) if self.config_path.exists() else dict(DEFAULTS)
        editable_keys = {field["key"] for field in FIELDS}
        # Unknown/manual extension settings are opaque wire values, not widgets.
        data.update({key: value.strip() if key in editable_keys else value
                     for key, value in draft.items()})
        language = data.get("INFINI_LANGUAGE", DEFAULTS["INFINI_LANGUAGE"]).strip().lower()
        if language not in {"ru", "en"}:
            raise ValueError("INFINI_LANGUAGE must be ru or en")
        data["INFINI_LANGUAGE"] = language
        data["INFINI_GUI_PIPELINE_PRESET"] = preset.strip()
        data["INFINI_SDCPP_SERVER_EXTRA_ARGS"] = " ".join(data.get("INFINI_SDCPP_SERVER_EXTRA_ARGS", "").split())
        template, repaired, reason = repair_command_template(data.get("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", ""), DEFAULT_COMMAND_TEMPLATE)
        if repaired:
            data["INFINI_SDCPP_SERVER_COMMAND_TEMPLATE"] = template
            data["INFINI_SDCPP_SERVER_COMMAND_MODE"] = "safe_args"
            self.status = f"sd.cpp command template repaired on save: {reason}"
        transport = "http" if data.get("INFINI_MP_ASSET_TRANSPORT", "native").lower() == "http" else "native"
        data["INFINI_MP_ASSET_TRANSPORT"] = transport
        if lan_enabled and transport == "http":
            data["INFINI_HOST"] = "0.0.0.0"
        else:
            if data.get("INFINI_HOST") == "0.0.0.0":
                data["INFINI_HOST"] = "127.0.0.1"
            if data.get("INFINI_ASSET_PUBLIC_BASE_URL", "").startswith("http://26."):
                data["INFINI_ASSET_PUBLIC_BASE_URL"] = ""
        lora_file = data.get("INFINI_SDCPP_LORA_FILE", "")
        if lora_file:
            data["INFINI_SDCPP_LORA_DIR"] = lora_dir_from_file(lora_file) or str(Path(lora_file).parent)
            if not data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", ""):
                data["INFINI_SDCPP_LORA_PROMPT_TAGS"] = lora_tag_from_file(lora_file, data.get("INFINI_SDCPP_LORA_WEIGHT", "0.25"))
        else:
            data["INFINI_SDCPP_LORA_DIR"] = ""
        if data.get("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1") == "1":
            data["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
        # Only canonicalized launch fields change draft state, never unrelated
        # disk values that were read to preserve extension keys.
        for key in ("INFINI_LANGUAGE", "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", "INFINI_SDCPP_SERVER_COMMAND_MODE",
                    "INFINI_MP_ASSET_TRANSPORT", "INFINI_HOST", "INFINI_ASSET_PUBLIC_BASE_URL",
                    "INFINI_SDCPP_LORA_DIR", "INFINI_SDCPP_LORA_PROMPT_TAGS", "INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"):
            if values is None and key in data:
                self.values[key] = data[key]
        return data

    def save(self):
        data = self.collect()
        data["INFINI_PORT"] = str(resolve_server_endpoint(data).port)
        write_env(self.config_path, data)
        self.values = data
        self.status = f"Saved: {self.config_path}"
        self._update_applied_config_feedback("Saved")

    def apply_preset(self, values=None, *, preset=None, lan_enabled=None):
        draft = dict(self.values if values is None else values)
        label = self.preset if preset is None else preset
        lan = self.lan_enabled if lan_enabled is None else lan_enabled
        is_user = label.startswith(USER_PRESET_PREFIX)
        preset = self.user_presets.get(label[len(USER_PRESET_PREFIX):]) if is_user else PRESETS.get(label)
        if preset is None:
            self.status = "Свои настройки сохранены без изменений. Для применения выбери готовый профиль."
            draft["INFINI_GUI_PIPELINE_PRESET"] = label
            return self._draft_result(draft, lan, commit=values is None)
        resize_choices = {} if is_user else {
            "INFINI_SPRITE_DOWNSCALE_FILTER": {"box", "bilinear", "bicubic", "lanczos"},
            "INFINI_SPRITE_PREMULTIPLIED_RESIZE": {"0", "1"},
        }
        for key, value in preset.items():
            if key in resize_choices and draft.get(key, DEFAULTS.get(key, "")).strip().lower() in resize_choices[key]:
                continue
            draft[key] = value
        if is_user:
            lan = draft.get("INFINI_HOST") == "0.0.0.0"
        draft["INFINI_GUI_PIPELINE_PRESET"] = label
        outcome = self._draft_result(draft, lan, commit=values is None)
        if values is None:
            self.preset = label
            self._capture_profile_baseline()
        self.status = "Профиль применён. Нажми «Сохранить», чтобы записать config.env; работающий сервер применит изменения после перезапуска."
        return outcome

    def _draft_result(self, draft, lan, *, commit=False):
        if draft.get("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", "1").strip() == "1":
            draft["INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK"] = "0"
        if commit:
            self.values = draft
            self.lan_enabled = lan
            self._refresh_visibility()
        return {"values": draft, "lanEnabled": bool(lan)}

    def use_selected_lora(self, values=None, *, lan_enabled=None):
        draft = dict(self.values if values is None else values)
        path = draft.get("INFINI_SDCPP_LORA_FILE", "").strip()
        if not path:
            self.actions.notify("warning", "LoRA", "Сначала выбери LoRA file (*.safetensors/*.ckpt).")
            return {"ok": False, "message": "Сначала выбери файл LoRA."}
        directory = lora_dir_from_file(path) or str(Path(path).parent)
        tag = lora_tag_from_file(path, draft.get("INFINI_SDCPP_LORA_WEIGHT", "0.25").strip())
        tags = draft.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "").strip()
        if tag not in tags:
            tags = (tags.rstrip() + " " + tag).strip()
        draft.update(INFINI_SDCPP_LORA_DIR=directory, INFINI_SDCPP_LORA_PROMPT_TAGS=tags)
        self.status = f"LoRA подключена: --lora-model-dir {directory} + {tag}"
        return self._draft_result(draft, self.lan_enabled if lan_enabled is None else lan_enabled, commit=values is None)

    def clear_lora_settings(self, values=None, *, lan_enabled=None):
        draft = dict(self.values if values is None else values)
        for key in ("INFINI_SDCPP_LORA_FILE", "INFINI_SDCPP_LORA_DIR", "INFINI_SDCPP_LORA_PROMPT_TAGS"):
            draft[key] = ""
        self.status = "LoRA file, prompt tags и LoRA dir очищены."
        return self._draft_result(draft, self.lan_enabled if lan_enabled is None else lan_enabled, commit=values is None)

    def reset_sprite_resize(self, values=None, *, lan_enabled=None):
        draft = dict(self.values if values is None else values)
        for key in ("INFINI_SPRITE_DOWNSCALE_FILTER", "INFINI_SPRITE_PREMULTIPLIED_RESIZE"):
            draft[key] = DEFAULTS[key]
        self.status = "Base resize: BOX, premultiplied RGBA=1. Нажми Save, чтобы сохранить."
        return self._draft_result(draft, self.lan_enabled if lan_enabled is None else lan_enabled, commit=values is None)

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
        # An obsolete or undeclared preset name is not evidence of a pipeline.
        # Keep its actual settings untouched and show them as custom.
        return CUSTOM_PRESET

    def refresh_home(self):
        runtime = self.runtime_status()
        lifecycle = runtime['lifecycle']
        if runtime['busy']:
            code, title, detail = "checking", "Проверяем состояние…", "Перед действием проверяем сервер и текущую генерацию. Интерфейс остаётся доступным."
        elif runtime['reason_code'] == 'action_failed' or lifecycle == 'exited':
            code, title, detail = "attention", "Нужно внимание", "Действие не выполнено. Подробности и исходное сообщение доступны в разделе «Диагностика»."
        elif lifecycle == "stopped":
            code, title, detail = "stopped", "Сервер остановлен", "Можно изменить настройки или запустить генератор снова."
        elif lifecycle == "starting":
            code, title, detail = "starting", "Сервер запускается", "Процесс запущен. Ждём подтверждения соединения; готовность ещё не проверена."
        elif runtime['confirmed']:
            code, title, detail = "responding", "Сервер отвечает", "Получен ответ от сервера этой копии генератора. Полная проверка всех настроек и ключей не выполнялась."
            if runtime['active'] or runtime['waiting']:
                code, title = "generating", "Идёт генерация"
                detail = f"Последний снимок сервера: создаётся {runtime['active']}, в очереди {runtime['waiting']}. Для актуального состояния нажми «Проверить соединение»."
        elif runtime['reason_code'] == 'health_unconfirmed':
            code, title, detail = "unconfirmed", "Соединение не подтверждено", "Сервер недоступен или его принадлежность этой копии не подтверждена. Проверь диагностику; чужие процессы не изменяются."
        else:
            code, title, detail = "unknown", "Состояние ещё не проверено", "Настройки готовы к редактированию. Нажми «Проверить соединение» или запусти сервер."
        self.home_code, self.home_state, self.home_detail = code, title, detail
        config_note = "Изменения настроек применяются после безопасного перезапуска сервера. Ключи скрыты и не копируются в профили."
        if runtime['config_match'] == 'mismatch':
            config_note = "Настройки изменены. Ответ сервера не подтверждает новые значения — нужен безопасный перезапуск."
        elif runtime['config_match'] == 'match':
            config_note = "Проверяемая часть настроек совпадает с сервером. Ключи и дополнительные модели этой проверкой не подтверждаются."
        self.home_config = config_note
