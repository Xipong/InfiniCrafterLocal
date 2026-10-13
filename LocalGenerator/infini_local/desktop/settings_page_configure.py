from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk

class ConfigurePageMixin:
    def _build_configure(self, parent):
        server_card = self._card(
            parent,
            "Сервер и поведение крафта",
            "Локальный HTTP helper для tModLoader craft request. 127.0.0.1 — только для себя; 0.0.0.0 — LAN/Radmin.",
            icon="▣",
        )
        self.row(server_card, "Адрес сервера", "INFINI_HOST", hint="127.0.0.1 — только ты; 0.0.0.0 — принимать подключения из Radmin/LAN.")
        self.row(server_card, "Порт сервера", "INFINI_PORT", width=16)
        self.row(server_card, "Ожидание крафта (сек.)", "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS", width=16, hint="240 секунд: если крафт не готов, tModLoader попробует retry.")
        self.row(server_card, "Попыток крафта", "INFINI_CRAFT_HTTP_ATTEMPTS", width=16)
        self.row(server_card, "Ожидание очереди (сек.)", "INFINI_COMBINE_BUSY_WAIT_SECONDS", width=16, hint="Сколько секунд параллельный /combine ждёт текущий craft/cache вместо немедленного busy response. Для обычной игры: 210.")
        restart_bar = ttk.Frame(server_card, padding=(10, 5))
        restart_bar.pack(fill="x")
        self._register_ui_section(restart_bar, advanced=True)
        force_button = self._modern_button(restart_bar, "Принудительный перезапуск…", self.force_restart_server, variant="danger")
        force_button.pack(side="left")
        self._attach_static_help(force_button, "Start/Stop по умолчанию SAFE: busy/unknown server не прерывается. Force требует отдельного подтверждения; чужой root/PID всё равно защищён.")
        ttk.Label(restart_bar, text="Start / Stop: safe; Force прерывает текущий craft только после подтверждения.", style="Hint.TLabel").pack(side="left", padx=10)

        debug_card = self._card(
            parent,
            "Debug: запас атакующих расходников",
            "Consumable weapon и ammo получают выбранный минимум. Зелья и материалы не меняются.\nLLM/prompt и canonical recipe не затрагиваются.",
            icon="⚒",
        )
        self.check_row(debug_card, "Включить минимум для атакующих расходников", "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED", hint="Применяется к delivery-копии fresh/cache-hit результата.")
        self._register_ui_section(debug_card, advanced=True)
        self.row(debug_card, "Минимум за один крафт", "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD", width=16, values=["2", "5", "10", "20", "25", "50", "99", "100", "250", "500", "999"], hint="Если authored craftYield/maxStack ниже, оба поднимаются до выбранного количества.")


    def _build_multiplayer(self, parent):
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
        self.row(radmin_card, "Передача изображений", "INFINI_MP_ASSET_TRANSPORT", values=["native", "http"], hint="native = PNG через Terraria packets; http = PNG через host /get_asset.")
        self.row(radmin_card, "Внешний адрес ассетов", "INFINI_ASSET_PUBLIC_BASE_URL", hint="Нужен только для HTTP: http://26.x.x.x:5055.")
        self.row(radmin_card, "Порт Terraria", "INFINI_TERRARIA_PORT", width=16, hint="Для друзей: Multiplayer → Join via IP → твой Radmin IP → этот порт. Обычно 7777.")
        connect = ttk.Frame(radmin_card, padding=(12, 6), style="CardInner.TFrame")
        connect.pack(fill="x")
        for text, command in [
            ("Определить адрес", self.autofill_radmin_url),
            ("Скопировать инструкцию", self.copy_radmin_friend_guide),
            ("Открыть инструкцию", self.open_mp_connect_page),
        ]:
            self._modern_button(connect, text, command, variant="ghost").pack(side="left", padx=(0, 6))
        self.radmin_info_var = tk.StringVar(value=self._radmin_status_text())
        self._info_panel(radmin_card, self.radmin_info_var, tone="blue")


    def _build_logging(self, parent):
        trace_card = self._card(
            parent,
            "Логирование генерации",
            "Полные sanitized запросы, ответы и диагностика без ротации. GUI показывает последние записи, не удаляя архив.",
            icon="⌘",
            status=("debug", "amber"),
        )
        self.check_row(trace_card, "Полное логирование (без обрезки)", "INFINI_TRACE_PROMPTS", hint="По умолчанию включено. OFF: без дополнительных trace/артефактов/events; остаются краткие фатальные ошибки. Сохранить → перезапустить сервер.")
        self.row(trace_card, "Символов в просмотре", "INFINI_TRACE_MAX_PROMPT_CHARS", width=16)
        self.row(trace_card, "Событий в просмотре", "INFINI_TRACE_EVENTS_TAIL", width=16)
        self.row(
            trace_card,
            "Сообщения в консоли",
            "INFINI_CONSOLE_EVENT_LEVEL",
            values=["warn", "error", "info", "debug", "off"],
            hint="Эхо событий в окно сервера. При полном логировании OFF остаются только краткие фатальные ошибки; off отключает и их эхо.",
        )
    def _build_general(self, parent):
        # Compatibility entry point for embedding clients and legacy contract tests.
        self._build_configure(parent)
        self._build_multiplayer(parent)
        self._build_logging(parent)
