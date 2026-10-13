"""Primary Operate surface: actions first, honest state, compact workflow summary."""
from __future__ import annotations

import re

from infini_local.desktop.tk_compat import tk
from infini_local.desktop.settings_gui_theme import (
    APP_BG, CARD_BG, CARD_MUTED_BG, TEXT_FG, MUTED_FG, ACCENT_BG, ACCENT_SOFT_BG, BORDER_FG,
)


class OperatePageMixin:
    def _build_operate(self, parent):
        self.home_state_var = tk.StringVar(value="Состояние ещё не проверено")
        self.home_detail_var = tk.StringVar(value="Проверь соединение, чтобы увидеть состояние генератора.")
        self.home_pipeline_var = tk.StringVar(value="")
        self.home_config_var = tk.StringVar(value="")
        self.home_notice_var = tk.StringVar(value="Готово к настройке")
        self.home_model_vars = [tk.StringVar(value="") for _ in range(3)]

        title = self._surface(parent, bg=APP_BG, pady=12)
        title.pack(fill="x", padx=4)
        self._label(title, "Рабочее место", size=24, bold=True).pack(anchor="w")
        self._label(title, "Настрой генерацию. Запусти сервер. Создавай предметы в игре.", fg=MUTED_FG).pack(anchor="w", pady=(5, 16))

        station = self._surface(parent, padx=22, pady=20, highlightthickness=1, highlightbackground=BORDER_FG)
        station.pack(fill="x", padx=4, pady=(0, 14))
        top = self._surface(station)
        top.pack(fill="x")
        stamp = tk.Canvas(top, width=58, height=58, bg=CARD_BG, highlightthickness=0)
        stamp.pack(side="left", padx=(0, 16))
        stamp.create_polygon(29, 3, 54, 17, 54, 42, 29, 56, 4, 42, 4, 17, outline=ACCENT_BG, fill=CARD_BG, width=2)
        stamp.create_line(16, 23, 42, 23, 34, 31, 24, 31, 20, 39, 38, 39, fill=ACCENT_BG, width=3)
        state = self._surface(top)
        state.pack(side="left", fill="x", expand=True)
        self._label(state, "ГЕНЕРАТОР", size=9, fg=ACCENT_BG, bold=True).pack(anchor="w")
        self._label(state, textvariable=self.home_state_var, size=18, bold=True).pack(anchor="w", pady=(4, 0))
        self._label(station, textvariable=self.home_detail_var, fg=MUTED_FG, wraplength=770, justify="left").pack(fill="x", pady=(14, 18))
        actions = self._surface(station)
        actions.pack(fill="x")
        self.operate_actions = {}
        for key, label, callback, variant in (
            ("start", "Запустить сервер", self.start_server, "primary"),
            ("stop", "Остановить", self.stop_server, "ghost"),
            ("health", "Проверить соединение", self._delayed_health_check, "ghost"),
        ):
            button = self._modern_button(actions, label, callback, variant)
            button.pack(side="left", padx=(0, 8))
            self.operate_actions[key] = button
        self._label(station, "Запуск сохраняет настройки. Занятая генерация защищена от случайного перезапуска.", size=9, fg=MUTED_FG, wraplength=780, justify="left").pack(anchor="w", pady=(12, 0))

        flow = self._surface(parent, bg=APP_BG)
        flow.pack(fill="x", padx=4, pady=(4, 8))
        self._label(flow, "ТВОЯ СБОРКА", fg=MUTED_FG, size=9, bold=True).pack(anchor="w", pady=(0, 10))
        # One vertical process rail; not a gallery of marketing tiles.
        for number, title, route, variable in zip(
            ("01", "02", "03"), ("Идея и свойства", "Изображение", "Готовый спрайт"),
            ("providers", "images", "sprites"), self.home_model_vars,
        ):
            line = self._surface(flow, bg=CARD_MUTED_BG, padx=14, pady=10)
            line.pack(fill="x", pady=(0, 2))
            self._label(line, number, size=13, fg=ACCENT_BG, bold=True, width=4).pack(side="left")
            body = self._surface(line, bg=CARD_MUTED_BG)
            body.pack(side="left", fill="x", expand=True)
            self._label(body, title, bold=True).pack(anchor="w")
            self._label(body, textvariable=variable, fg=MUTED_FG, size=9).pack(anchor="w", pady=(3, 0))
            self._modern_button(line, "Настроить", lambda key=route: self.navigate(key)).pack(side="right")

        bottom = self._surface(parent, bg=APP_BG, pady=10)
        bottom.pack(fill="x", padx=4)
        self._label(bottom, textvariable=self.home_config_var, fg=MUTED_FG, size=9, wraplength=800, justify="left").pack(anchor="w")
        self._label(bottom, "После запуска открой Terraria с модом InfiniCrafterLocal. Крафт выполняется в игре.", fg=MUTED_FG, size=9, wraplength=800, justify="left").pack(anchor="w", pady=(8, 0))
        self._refresh_operate_summary()

    def _refresh_operate_summary(self, *_args):
        if "home_state_var" not in self.__dict__:
            return
        def value(key, default=""):
            var = self.vars.get(key)
            return var.get().strip() if var is not None else str(self.data.get(key, default)).strip()
        provider = value("INFINI_LLM_PROVIDER", "local")
        backend = value("INFINI_IMAGE_BACKEND", "sdcpp")
        providers = {"local": "LM Studio · локальная модель", "openrouter": "OpenRouter", "openai_compat": "Совместимый API", "openai_codex": "ChatGPT / Codex"}
        engines = {"sdcpp": "sd.cpp · локальная модель", "openai_codex": "ChatGPT · генерация изображений", "image_api": "Внешний API изображений", "off": "Изображения выключены", "comfyui": "ComfyUI", "a1111": "Automatic1111"}
        self.home_model_vars[0].set(providers.get(provider, "Другой источник текста"))
        self.home_model_vars[1].set(engines.get(backend, "Другой источник изображений"))
        self.home_model_vars[2].set("Без обработки: изображения выключены" if backend == "off" else
            ("Прозрачный фон" if value("INFINI_BG_COLOR") == "transparent" else "Удаление фона") + " · уменьшение " + value("INFINI_SPRITE_DOWNSCALE_FILTER", "box"))
        self.home_pipeline_var.set(providers.get(provider, "Другой источник текста") + " / " + engines.get(backend, "Другой источник изображений"))
        raw = self.status_var.get().lower()
        applied = self.__dict__.get("applied_config_var")
        applied_text = applied.get().lower() if applied is not None else ""
        busy = "server-action" in self.__dict__.get("_gui_tasks", {}) or "checking" in raw or "checking" in applied_text
        ack = self.__dict__.get("_applied_config_ack")
        if busy:
            title, detail = "Проверяем состояние…", "Перед действием проверяем сервер и текущую генерацию. Интерфейс остаётся доступным."
        elif any(word in raw for word in ("refused", "failed", "unavailable", "ошиб", "не удалось")):
            title, detail = "Нужно внимание", "Действие не выполнено. Подробности и исходное сообщение доступны в разделе «Диагностика»."
        elif "unconfirmed" in applied_text:
            title, detail = "Соединение не подтверждено", "Сервер недоступен или его принадлежность этой копии не подтверждена. Проверь диагностику; чужие процессы не изменяются."
        elif "stopped" in raw:
            title, detail = "Сервер остановлен", "Можно изменить настройки или запустить генератор снова."
        elif ack:
            title, detail = "Сервер отвечает", "Получен ответ от сервера этой копии генератора. Полная проверка всех настроек и ключей не выполнялась."
        elif "запущен" in raw:
            title, detail = "Сервер запускается", "Процесс запущен. Ждём подтверждения соединения; готовность ещё не проверена."
        else:
            title, detail = "Состояние ещё не проверено", "Настройки готовы к редактированию. Нажми «Проверить соединение» или запусти сервер."
        activity = self.__dict__.get("activity_var")
        snapshot = re.match(r"Backend last health snapshot: active=(\d+), waiting=(\d+), accepting=(True|False)", activity.get()) if activity is not None else None
        if ack and snapshot and not busy and title == "Сервер отвечает":
            active, waiting = int(snapshot[1]), int(snapshot[2])
            if active or waiting:
                title = "Идёт генерация"
                detail = f"Последний снимок сервера: создаётся {active}, в очереди {waiting}. Для актуального состояния нажми «Проверить соединение»."
        self.home_state_var.set(title)
        self.home_detail_var.set(detail)
        self.home_notice_var.set("Настройки сохранены" if raw.startswith("saved:") else title)
        config_note = "Изменения настроек применяются после безопасного перезапуска сервера. Ключи скрыты и не копируются в профили."
        if "restart" in applied_text or "differs" in applied_text:
            config_note = "Настройки изменены. Ответ сервера не подтверждает новые значения — нужен безопасный перезапуск."
        elif "matches" in applied_text:
            config_note = "Проверяемая часть настроек совпадает с сервером. Ключи и дополнительные модели этой проверкой не подтверждаются."
        self.home_config_var.set(config_note)
