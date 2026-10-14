from __future__ import annotations

from pathlib import Path, PureWindowsPath

from infini_local.desktop.settings_widgets import write_text_value
from infini_local.desktop.tk_compat import messagebox, tk, ttk
from infini_local.desktop.settings_interactions import notify
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_EXTRA_FLAG_SPECS,
    SDCPP_EXTRA_PROFILES,
    SDCPP_EXTRA_PROFILE_HELP,
)
from infini_local.desktop.settings_sdcpp_args import (
    extra_option_names,
    join_extra_for_gui,
    remove_extra_options,
    split_extra_for_gui,
)


class SettingsGuiImageArgsMixin:
    def _build_lora_buttons(self, parent):
        from infini_local.desktop.settings_page_images import ImagesPageMixin
        return ImagesPageMixin._build_lora_buttons(self, parent)

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
            write_text_value(widget, value.strip())
        elif "INFINI_SDCPP_LORA_PROMPT_TAGS" in self.vars:
            self.vars["INFINI_SDCPP_LORA_PROMPT_TAGS"].set(value.strip())

    @staticmethod
    def _lora_tag_from_file(path: str, weight: str) -> str:
        raw = str(path or "").strip()
        stem = (PureWindowsPath(raw).stem if "\\" in raw or ":" in raw else Path(raw).stem).strip()
        weight = str(weight or "0.25").strip() or "0.25"
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
        variable = self.vars.get("INFINI_SDCPP_LORA_FILE")
        path = variable.get().strip() if variable is not None else ""
        if not path:
            notify(self, "warning", "LoRA", "Сначала выбери LoRA file (*.safetensors/*.ckpt).")
            return {"ok": False, "message": "Сначала выбери файл LoRA."}
        lora_dir = self._lora_dir_from_file(path)
        if "INFINI_SDCPP_LORA_DIR" in self.vars and lora_dir:
            self.vars["INFINI_SDCPP_LORA_DIR"].set(lora_dir)
        p = Path(path)
        weight_var = self.vars.get("INFINI_SDCPP_LORA_WEIGHT")
        weight = (weight_var.get().strip() if weight_var is not None else "") or "0.25"
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
        from infini_local.desktop.settings_page_images import ImagesPageMixin
        return ImagesPageMixin._build_sdcpp_extra_buttons(self, parent)

    def _build_sdcpp_extra_help(self, parent):
        from infini_local.desktop.settings_page_images import ImagesPageMixin
        return ImagesPageMixin._build_sdcpp_extra_help(self, parent)

    def _build_sdcpp_debug_buttons(self, parent):
        from infini_local.desktop.settings_page_images import ImagesPageMixin
        return ImagesPageMixin._build_sdcpp_debug_buttons(self, parent)

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
            write_text_value(text, value.strip())

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

    def reset_sprite_resize(self):
        for key in ("INFINI_SPRITE_DOWNSCALE_FILTER", "INFINI_SPRITE_PREMULTIPLIED_RESIZE"):
            self.vars[key].set(DEFAULTS[key])
        self.status_var.set("Base resize: BOX, premultiplied RGBA=1. Нажми Save, чтобы сохранить.")
        self._refresh_visibility()


__all__ = ["SettingsGuiImageArgsMixin"]
