from __future__ import annotations

import webbrowser
from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_widgets import ToolTip
from infini_local.desktop.settings_schema import SDCPP_EXTRA_FLAG_SPECS, SDCPP_EXTRA_PROFILE_HELP
from infini_local.desktop.settings_gui_theme import CARD_BG, MUTED_FG

class ImagesPageMixin:
    def _build_zimage_guide(self, parent):
        box = ttk.LabelFrame(parent, text="FLUX.2 / Z-Image / stable-diffusion.cpp — краткий гайд", padding=(10, 8))
        box.pack(fill="x", padx=10, pady=(6, 10))
        self._register_ui_section(box, "INFINI_IMAGE_BACKEND", ("sdcpp",), advanced=True)
        guide = (
            "1) Пути: укажи sd-server.exe, diffusion *.gguf, ae.safetensors и Qwen/LLM *.gguf. "
            "VAE/Qwen/LoRA не надо дублировать в extra args — GUI добавит --vae/--llm/--lora-model-dir сам.\n"
            "2) Текущий FLUX.2 Klein 4B preset: нажми FLUX hybrid. Diffusion+TE работают через ROCm, VAE через Vulkan, TE weights лежат в CPU RAM.\n"
            "3) Для Z-Image нажми AMD safe: runtime diffusion/VAE/TE на Vulkan, параметры Qwen/TE в RAM. Если VRAM душит/игра фризит: AMD low VRAM; для максимума скорости при достаточной VRAM: AMD full GPU.\n"
            "4) LoRA: выбери LoRA file и нажми Browse + use / Use selected LoRA. Отдельного поля folder нет: папка берётся из файла, а в prompt добавляется <lora:name:weight>.\n"
            "5) FLUX.2 Klein preset использует 4 / 1.0 / euler; Z-Image Turbo обычно 6-12 / 1.0 / euler.\n"
            "6) safe_args лучше template: меньше риска сломать --sampling-method или случайно вставить текст пресета в команду."
        )
        msg = tk.Message(box, text=guide, width=900, foreground=MUTED_FG, background=CARD_BG)
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
        root = parent
        choice = self._card(root, "Источник изображения", "PNG-движок выбирается независимо от текстового LLM и Visual Director.", icon="▧")
        self.row(choice, "Источник картинок", "INFINI_IMAGE_BACKEND", values=["sdcpp", "openai_codex", "image_api", "off", "comfyui", "a1111"], hint="openai_codex = ChatGPT/Codex OAuth по подписке; sdcpp = локальная модель; image_api = отдельный API; off = без PNG.")
        self.row(choice, "Параллельных запросов", "INFINI_IMAGE_MAX_CONCURRENCY", width=8, hint="Один общий GPU/sd-server: 1. Увеличивай только если backend действительно обслуживает параллельные image jobs без OOM/очереди внутри.")
        codex = self._card(root, "ChatGPT · изображения", "Встроенная известная image-модель — не список моделей аккаунта.", icon="✦", status=("известная модель", "amber"))
        self._register_ui_section(codex, "INFINI_IMAGE_BACKEND", ("openai_codex",))
        model_row = self.row(codex, "Codex image model", "INFINI_CODEX_IMAGE_MODEL", values=[self.data.get("INFINI_CODEX_IMAGE_MODEL") or "gpt-image-2", "gpt-image-2"], editable=True, hint="gpt-image-2 — встроенная известная модель. Ручное имя сохраняется, но не подтверждает доступ к нему.")
        self._modern_button(model_row, "Пинг · read-only", self.ping_codex_image_account).pack(side="right", padx=(8, 0))
        self.row(codex, "Codex quality", "INFINI_CODEX_IMAGE_QUALITY", values=["low", "medium", "high", "auto"])
        self.row(codex, "Codex size", "INFINI_CODEX_IMAGE_SIZE", values=["1024x1024", "1536x1024", "1024x1536", "auto"])
        self.row(codex, "Codex timeout", "INFINI_CODEX_IMAGE_TIMEOUT", width=16)
        self._info_panel(codex, "Качество и размер влияют на время генерации и расход квоты подписки. high/большой PNG может стоить дороже по лимитам; точных цен и остатка квоты этот UI не получает. Reasoning Visual Director — на вкладке LLM, не параметр image engine.", tone="blue")
        self._info_panel(codex, "Нет live-каталога image-моделей. gpt-image-2 — известная встроенная модель, не подтверждение доступности на этом аккаунте. Пинг рядом с моделью читает текстовый endpoint, а не image-права/квоту.", tone="amber")
        auth_actions = ttk.Frame(codex, style="CardInner.TFrame")
        auth_actions.pack(fill="x", padx=10, pady=4)
        for label, command in (("Войти", self.codex_login), ("Выйти", self.codex_logout)):
            self._modern_button(auth_actions, label, command).pack(side="left", padx=(0, 6))
        self.codex_image_account_var = tk.StringVar(value="Если есть сохранённая сессия, аккаунт проверяется при открытии вкладки; image-доступ не подтверждён.")
        self._info_panel(codex, self.codex_image_account_var)
        parent = self._card(root, "Локальный sd.cpp", "FLUX.2 / Z-Image: пути, LoRA, запуск и sampler.", icon="▦")
        self._register_ui_section(parent, "INFINI_IMAGE_BACKEND", ("sdcpp",))
        self.row(parent, "sd-server.exe", "INFINI_SDCPP_SERVER_EXE", browse="file")
        self.row(parent, "ROCm hybrid runtime", "INFINI_SDCPP_ROCM_COMPAT_ROOT", browse="folder", hint="Папка sdcpp-hybrid-gfx1030. ROCm/HIP/rocBLAS env применяется только к дочернему sd-server.exe.")
        self.row(parent, "Diffusion model", "INFINI_SDCPP_MODEL", browse="model", hint="FLUX.2 Klein или Z-Image *.gguf.")
        self.row(parent, "VAE / AE", "INFINI_SDCPP_VAE", browse="model", hint="Обычно ae.safetensors. GUI сам добавит --vae, руками в extra args не надо.")
        self.row(parent, "Qwen / LLM", "INFINI_SDCPP_LLM", browse="model", hint="Text encoder/Qwen *.gguf. GUI сам добавит --llm, руками в extra args не надо.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="LoRA для Z-Image/sd.cpp", font=(self.__dict__.get("ui_font_family", "Segoe UI"), 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        lora_note = ttk.Label(
            parent,
            text="   LoRA folder скрыт: GUI берёт папку из LoRA file, запускает sd.cpp с --lora-model-dir и передаёт LoRA через структурированный HTTP payload.",
            foreground=MUTED_FG, wraplength=790, justify="left",
        )
        lora_note.pack(anchor="w", padx=10)
        ToolTip(lora_note, "HTTP server sd.cpp намеренно не исполняет <lora:...> из текста prompt. InfiniCrafter преобразует выбранный файл и вес в безопасное поле lora[] запроса.")
        self.row(parent, "LoRA file", "INFINI_SDCPP_LORA_FILE", browse="lora_file", hint="Выбери конкретный *.safetensors/*.ckpt/*.pt/*.pth. Имя файла и вес уйдут в структурированное поле lora[]; текстовый тег в модель не попадёт.")
        self.row(parent, "LoRA weight", "INFINI_SDCPP_LORA_WEIGHT", width=16, hint="Для FLUX.2 pixel-art LoRA начинай с 0.20-0.30; 0.45+ заметно меняет форму и может ухудшать identity.")
        self.text_row(parent, "LoRA prompt tags", "INFINI_SDCPP_LORA_PROMPT_TAGS", height=2, hint="Совместимый ввод <lora:name:weight>. Перед HTTP-вызовом теги удаляются из prompt и переводятся в lora[]; выбранный LoRA file задаёт точное имя файла.")
        self._build_lora_buttons(parent)
        self.row(parent, "sd.cpp URL", "INFINI_SDCPP_SERVER_URL")
        self.row(parent, "sd.cpp autostart", "INFINI_SDCPP_SERVER_AUTOSTART", values=["1", "0"])
        self.row(parent, "sd.cpp command mode", "INFINI_SDCPP_SERVER_COMMAND_MODE", values=["safe_args", "template"], hint="safe_args = рекомендуемый безопасный запуск без shell/template; template нужен только для нестандартного sd.cpp.")
        self.row(parent, "sd.cpp command", "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE")
        self.text_row(parent, "sd.cpp extra args", "INFINI_SDCPP_SERVER_EXTRA_ARGS", height=4, hint="Только доп. флаги: -v, --diffusion-fa, --offload-to-cpu и т.п. VAE/Qwen лучше задавать полями выше.")
        advanced_tools = ttk.Frame(parent, style="CardInner.TFrame")
        advanced_tools.pack(fill="x")
        self._register_ui_section(advanced_tools, advanced=True)
        self._build_sdcpp_extra_buttons(advanced_tools)
        self.row(parent, "sd.cpp show console", "INFINI_SDCPP_SERVER_SHOW_CONSOLE", values=["1", "0"], hint="1 = открыть отдельное окно sd-server.exe с живым логом. Полезно для отлова Z-Image крашей.")
        self.row(parent, "sd.cpp log file", "INFINI_SDCPP_SERVER_LOG_FILE", browse="file", hint="Если show console=0, stdout/stderr sd-server пишутся сюда. /sdcpp_debug покажет хвост.")
        diagnostics_tools = ttk.Frame(parent, style="CardInner.TFrame")
        diagnostics_tools.pack(fill="x")
        self._register_ui_section(diagnostics_tools, advanced=True)
        self._build_sdcpp_debug_buttons(diagnostics_tools)
        self.row(parent, "sd width", "INFINI_SDCPP_WIDTH", width=16)
        self.row(parent, "sd height", "INFINI_SDCPP_HEIGHT", width=16)
        self.row(parent, "sd steps", "INFINI_SDCPP_STEPS", width=16)
        self.row(parent, "sd cfg", "INFINI_SDCPP_CFG", width=16)
        self.row(parent, "sd sampler", "INFINI_SDCPP_SAMPLER", width=24)
        self.row(parent, "sd seed", "INFINI_SDCPP_SEED", width=16, hint="-1 = случайный seed. Положительное число фиксирует результат для отладки.")
        self.row(parent, "Z-Image contract", "INFINI_ZIMAGE_PROMPT_CONTRACT", values=["auto", "1", "0"], hint="Обычно auto. Это внутренний маркер для Z-Image payload/prompt contract.")
        self.row(parent, "Positive-only prompt", "INFINI_ZIMAGE_POSITIVE_ONLY", values=["1", "0"], hint="Для Z-Image Turbo обычно 1: negative_prompt не используется, все запреты/техусловия в positive prompt.")
        self.row(parent, "Require item sprite", "INFINI_VISUAL_REQUIRE_ITEM_SPRITE", values=["1", "0"], hint="1 = не доставлять свежий craft без валидного item PNG. Основной product contract; выключать только для явной диагностики.")
        self._build_zimage_guide(root)
        parent = self._card(root, "Внешний API изображений", "Отдельный API key и endpoint; не относится к Codex-подписке.", icon="↗")
        self._register_ui_section(parent, "INFINI_IMAGE_BACKEND", ("image_api",))
        self.row(parent, "Image API base", "INFINI_IMAGE_API_BASE_URL")
        self.row(parent, "Image API key", "INFINI_IMAGE_API_KEY", secret=True)
        self.row(parent, "Image API model", "INFINI_IMAGE_API_MODEL")
        self.row(parent, "Image API path", "INFINI_IMAGE_API_PATH")
        self.row(parent, "Image API size", "INFINI_IMAGE_API_SIZE", values=["512x512", "768x768", "1024x1024"])
        self.row(parent, "Image API timeout", "INFINI_IMAGE_API_TIMEOUT", width=16)
        parent = self._card(root, "Automatic1111 / ComfyUI", "Альтернативные локальные серверы изображений.", icon="⌁")
        self._register_ui_section(parent, "INFINI_IMAGE_BACKEND", ("a1111", "comfyui"))
        self.row(parent, "A1111 URL", "INFINI_A1111_URL")
        self.row(parent, "ComfyUI URL", "INFINI_COMFYUI_URL")

    def _build_lora_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        specs = [
            ("Применить LoRA", self.use_selected_lora, "Взять LoRA file, вывести папку из файла и подготовить безопасный структурированный lora[] payload с выбранным весом."),
            ("Выбрать и применить", self.browse_and_use_lora_file, "Выбрать LoRA файл и сразу подключить его: hidden --lora-model-dir + структурированный HTTP payload."),
            ("Очистить LoRA", self.clear_lora_settings, "Очистить LoRA file, prompt tags и скрытый LoRA dir."),
        ]
        for text, command, help_text in specs:
            btn = ttk.Button(frame, text=text, command=command)
            btn.pack(side="left", padx=2)
            self.extra_arg_buttons.append(btn)
            self._attach_static_help(btn, help_text)
        ttk.Label(
            parent,
            text="sd.cpp: GUI сам выводит --lora-model-dir из LoRA file; активная LoRA передаётся через структурированный HTTP payload.",
            foreground="#a39c93",
        ).pack(anchor="w", padx=8, pady=6)

    def _build_sdcpp_extra_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        ttk.Label(frame, text="Пресеты:", foreground="#a39c93").pack(side="left", padx=(0, 4))
        preset_specs = [
            ("FLUX hybrid", lambda: self.set_extra_profile("flux2_klein4b_rx6800xt_hybrid"), SDCPP_EXTRA_PROFILE_HELP["flux2_klein4b_rx6800xt_hybrid"]),
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
        ttk.Label(frame2, text="", foreground="#a39c93").pack(side="left", padx=(0, 4))
        for i, (text, command, help_text) in enumerate(preset_specs):
            target = frame if i < 4 else frame2
            btn = ttk.Button(target, text=text, command=command)
            btn.pack(side="left", padx=2)
            self.extra_arg_buttons.append(btn)
            self._attach_static_help(btn, help_text)

        flag_specs = SDCPP_EXTRA_FLAG_SPECS
        for row_index in range(0, len(flag_specs), 3):
            flag_frame = ttk.Frame(parent, padding=(10, 2))
            flag_frame.pack(fill="x")
            ttk.Label(flag_frame, text="Добавить флаг:" if row_index == 0 else "", foreground="#a39c93").pack(side="left", padx=(0, 4))
            for text, fragment, help_text in flag_specs[row_index:row_index + 3]:
                btn = ttk.Button(flag_frame, text=text, command=lambda fragment=fragment: self.append_extra_args(fragment))
                btn.pack(side="left", padx=2)
                self.extra_arg_buttons.append(btn)
                self._attach_static_help(btn, help_text)

        frame4 = ttk.Frame(parent, padding=(10, 2))
        frame4.pack(fill="x")
        for text, command, help_text in [
            ("Восстановить запуск", self.repair_command_template, "Вернуть safe_args и безопасный reference command template."),
            ("Очистить аргументы", self.clear_extra_args, "Очистить manual extra args. Пути модели/VAE/Qwen/LoRA не трогает."),
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
            width=810,
            foreground="#a39c93",
        )
        msg.pack(fill="x", anchor="w")

    def _build_sdcpp_debug_buttons(self, parent):
        frame = ttk.Frame(parent, padding=(10, 2))
        frame.pack(fill="x")
        start_btn = ttk.Button(frame, text="Запустить sd.cpp", command=self.open_sdcpp_start)
        start_btn.pack(side="left", padx=2)
        debug_btn = ttk.Button(frame, text="Журнал sd.cpp", command=self.open_sdcpp_debug)
        debug_btn.pack(side="left", padx=2)
        doctor_btn = ttk.Button(frame, text="Visual Doctor", command=self.open_visual_doctor)
        doctor_btn.pack(side="left", padx=2)
        probe_btn = ttk.Button(frame, text="Тестовая генерация…", command=self.open_visual_doctor_probe)
        probe_btn.pack(side="left", padx=2)
        self.sdcpp_debug_buttons.extend([start_btn, debug_btn, doctor_btn, probe_btn])
        self._attach_static_help(start_btn, "Сохранить config.env и открыть /sdcpp_start: server.py попробует поднять sd.cpp до крафта.")
        self._attach_static_help(debug_btn, "Открыть /sdcpp_debug: команда запуска, активный backend и хвост лога sd.cpp.")
        self._attach_static_help(doctor_btn, "Открыть /visual_doctor: проверка полного пути FLUX/Z-Image -> postprocess -> asset delivery.")
        self._attach_static_help(probe_btn, "Открыть /visual_doctor.json?probe=1: реальная тестовая генерация item sprite без крафта в игре.")
        ttk.Label(parent, text="/sdcpp_start запускает sd-server; Visual Doctor проверяет Image Gen и обязательный sprite delivery.", foreground="#a39c93").pack(anchor="w", padx=8, pady=6)
