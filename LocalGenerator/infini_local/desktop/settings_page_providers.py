from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk

class ProvidersPageMixin:
    def _build_llm(self, parent):
        primary = self._card(parent, "Модель и стиль", "Выбери источник контракта предмета. Codex работает через аккаунт, остальные провайдеры сохраняют свои поля.", icon="◉")
        self.row(primary, "Использовать модель", "INFINI_USE_LLM", values=["1", "0"], hint="Главный переключатель LLM-авторинга. 0 допустим только для явных debug/dev сценариев.")
        self.row(primary, "Стиль промпта", "INFINI_PROMPT_STYLE", width=20, values=["Default", "Terraria Like"], hint="Все режимы генерируют предметы для Terraria. Terraria Like — vanilla-like спрайты, палитра, читаемость и согласованные эффекты; не пресет механик.")
        self.row(primary, "Balance mode", "INFINI_BALANCE_MODE", values=["safety", "normalize", "report"])
        self.row(primary, "Deterministic dev fallback", "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK", values=["0", "1"], hint="Только для разработки: разрешает кодовый fallback, если LLM недоступна. В обычной игре оставлять 0.")
        self.row(primary, "Источник текста", "INFINI_LLM_PROVIDER", values=["local", "openrouter", "openai_compat", "openai_codex"])

        codex_card = self._card(parent, "ChatGPT / Codex", "Только текст: модели и поддерживаемые reasoning efforts из live-каталога аккаунта. Запрос не генерирует контент.", icon="✦", status=("OAuth", "blue"))
        self._register_ui_section(codex_card, "INFINI_LLM_PROVIDER", ("openai_codex",))
        model_row = self.row(codex_card, "Codex text model", "INFINI_CODEX_LLM_MODEL", values=[self.data.get("INFINI_CODEX_LLM_MODEL") or ""], editable=True, hint="Slug редактируемый. Перед генерацией выбери модель; пустое значение не запускает Codex. Ошибка обновления не стирает сохранённый slug.")
        self.codex_model_combo = next(w for w in model_row.winfo_children() if isinstance(w, ttk.Combobox))
        self.codex_model_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_codex_efforts(), add="+")
        self.vars["INFINI_CODEX_LLM_MODEL"].trace_add("write", lambda *_: self._update_codex_efforts())
        buttons = ttk.Frame(codex_card, style="CardInner.TFrame")
        buttons.pack(fill="x", padx=10, pady=4)
        for text, action in (("Обновить текстовые модели", self.refresh_codex_text_catalog), ("Войти", self.codex_login), ("Сессия", self.codex_status), ("Выйти", self.codex_logout)):
            self._modern_button(buttons, text, action, variant="soft" if text.startswith("Обновить") else "ghost").pack(side="left", padx=(0, 6))
        self.codex_catalog_var = tk.StringVar(value="Текстовый каталог ещё не загружен. Войди в Codex и обнови модели.")
        self._info_panel(codex_card, self.codex_catalog_var)

        other = self._card(parent, "Подключение к модели", "Показаны настройки выбранного источника. Остальные значения сохранены.", icon="⌁")
        self._register_ui_section(other, "INFINI_LLM_PROVIDER", ("local", "openrouter", "openai_compat"))
        self.row(other, "LM Studio URL", "INFINI_LMSTUDIO_URL")
        self.row(other, "LM Studio model", "INFINI_LMSTUDIO_MODEL")
        self.row(other, "OpenRouter API key", "INFINI_OPENROUTER_API_KEY", secret=True)
        self.row(other, "OpenRouter model", "INFINI_OPENROUTER_MODEL", hint="auto или slug модели с OpenRouter.")
        self.row(other, "OpenRouter provider slug", "INFINI_OPENROUTER_PROVIDER", hint="Пусто = auto. Точный slug из OpenRouter фиксирует площадку; при её недоступности нет перехода на другой profile/fallback.")
        self.row(other, "OpenRouter referer", "INFINI_OPENROUTER_HTTP_REFERER")
        self.row(other, "OpenRouter title", "INFINI_OPENROUTER_APP_TITLE")
        self.row(other, "Адрес API", "INFINI_OPENAI_COMPAT_BASE_URL")
        self.row(other, "Ключ API", "INFINI_OPENAI_COMPAT_API_KEY", secret=True)
        self.row(other, "Модель API", "INFINI_OPENAI_COMPAT_MODEL")
        self.row(other, "LLM 1 API mode", "INFINI_LLM_API_MODE", values=["auto", "responses", "chat_completions"], hint="auto сначала пробует /responses и запоминает поддержку; при отказе тот же self-contained packet идёт через /chat/completions.")
        fallback = self._card(parent, "Резервная модель", "Необязательный резерв для локальных/API провайдеров.", icon="↳")
        self._register_ui_section(fallback, advanced=True)
        self.row(fallback, "Fallback provider", "INFINI_LLM_FALLBACK_PROVIDER", values=["", "local", "openrouter", "openai_compat"], hint="Пусто = использовать тот же провайдер, что и основной. Нужен только если хочешь при падении уйти на другой pipeline.")
        self.row(fallback, "Fallback model", "INFINI_LLM_FALLBACK_MODEL", hint="Пусто = fallback выключен. Если основная модель умерла по бабкам/сети, сервер попробует эту модель.")
        self.row(fallback, "OpenRouter provider slug", "INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER", hint="Отдельная фиксация upstream для OpenRouter fallback. Пусто = auto, не наследует основной slug. При фиксации основного профиля переход сюда запрещён.")
        self.row(fallback, "Fallback base URL", "INFINI_LLM_FALLBACK_BASE_URL", hint="Пусто = взять base URL от fallback provider по умолчанию/из основных полей.")
        self.row(fallback, "Fallback API key", "INFINI_LLM_FALLBACK_API_KEY", secret=True, hint="Пусто = использовать основной ключ выбранного fallback provider.")
        self.row(fallback, "Fallback after transport fails", "INFINI_LLM_FALLBACK_NETWORK_FAILS", width=16, hint="Сколько сетевых/timeout падений подряд терпеть на основной модели, прежде чем уходить на fallback. По умолчанию 2.")
        controls = self._card(parent, "Генерация и рассуждение", "Gameplay Author и текстовый Visual Director. PNG-качество на вкладке «Картинки».", icon="◇")
        self.row(controls, "Response format", "INFINI_LLM_RESPONSE_FORMAT", values=["auto", "json_schema", "json_object", "off"])
        self.row(controls, "Разнообразие ответа", "INFINI_LLM_TEMPERATURE", width=16, hint="Температура основной LLM, которая пишет gameplay/runtime contract. 0.30-0.45: стабильнее; 0.55-0.75: разнообразнее, но выше риск мусора в контракте. Не относится к fallback-модели.")
        self.row(controls, "Температура исправлений", "INFINI_LLM_REAUTHOR_TEMPERATURE", width=16, hint="Пусто = 0.12. Обычно 0.0-0.2 для scoped Repair; явно заданный INFINI_LLM_REPAIR_TEMPERATURE имеет приоритет.")
        self.row(controls, "Разнообразие образа", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", width=16, hint="Температура отдельного LLM Visual Director для image prompts/visual kit. Это не sd.cpp temperature и не fallback; на sampler не влияет.")
        visual_row = self.row(controls, "Visual Director effort", "INFINI_CODEX_VISUAL_REASONING", values=["inherit", "model_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"], hint="Отдельный reasoning текстового Visual Director; inherit = усилие основной LLM, model_default = без effort в запросе; не image-модель.")
        self.codex_visual_reasoning_combo = next(w for w in visual_row.winfo_children() if isinstance(w, ttk.Combobox))
        self.row(controls, "Бюджет ответа (токены)", "INFINI_LLM_MAX_TOKENS", width=16, hint="Другие провайдеры: бюджет ответа. Codex /responses не принимает max_output_tokens: поле не отправляется и не ограничивает квоту; применяются только временные/байтовые ограничения.")
        reasoning_row = self.row(controls, "Рассуждение", "INFINI_LLM_REASONING_MODE", values=["off", "auto", "none", "minimal", "low", "medium", "high", "xhigh", "tokens", "prompt_light", "prompt_strong"], hint="Codex: выбери effort текущей модели; другие провайдеры сохраняют свои API/prompt режимы.")
        self.codex_reasoning_combo = next(w for w in reasoning_row.winfo_children() if isinstance(w, ttk.Combobox))
        self.row(controls, "Reasoning token budget", "INFINI_LLM_REASONING_MAX_TOKENS", width=16, hint="Используется при mode=tokens; OpenRouter мапит это на max_tokens/thinking_budget там, где модель поддерживает.")
        self.row(controls, "Hide reasoning output", "INFINI_LLM_REASONING_EXCLUDE", values=["1", "0"], hint="1 = reasoning используется, но не возвращается в message.content; меньше ломает JSON-парсер.")
        self.row(controls, "Local prompt reasoning", "INFINI_LLM_LOCAL_REASONING_PROMPT", values=["1", "0"], hint="Для локалок без API reasoning: разрешить короткий внутренний чек в system prompt. Цепочку мыслей выводить всё равно запрещено.")

    def _build_multidev(self, parent):
        hero = self._card(
            parent,
            "Multi-dev крафт — 2–3 независимых окна",
            "В игре: /multidevcraft 2, /multidevcraft 3 или /multidevcraft off. Каждое окно имеет свои A/B-слоты, requestId, прогресс и exact LLM profile.",
            icon="▦",
            status=("admin-команда", "amber"),
        )
        self._info_panel(
            hero,
            "Lane 1 → LLM 1, lane 2 → LLM 2, lane 3 → LLM 3. Multi-dev не прыгает на соседнюю модель: неактивный или пустой profile честно роняет только своё окно и возвращает его ингредиенты.",
            tone="amber",
        )
        self.row(hero, "Параллельных окон", "INFINI_MULTIDEV_CONCURRENCY", width=16, values=["2", "3"], hint="Верхний предел LocalGenerator. Команда в игре может открыть 2 или 3 окна, но не больше этого значения.")
        self.row(hero, "Cooldown после ошибки", "INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS", width=16, hint="Для обычного round-robin/failover. Exact multi-dev lanes за соседней моделью не прячутся.")

        lane1 = self._card(
            parent,
            "Окно 1 · LLM 1",
            "Основной provider/model на вкладке LLM. В multi-dev режиме первое окно закрепляется за llm_1.",
            icon="①",
            status=("основная", "blue"),
        )
        self._info_panel(lane1, "Настрой Источник текста, base URL/API key и model на вкладке 2. LLM.", tone="blue")

        for slot in (2, 3, 4):
            prefix = f"INFINI_LLM_POOL_{slot}"
            if slot <= 3:
                title = f"Окно {slot} · LLM {slot}"
                subtitle = f"Отдельное игровое окно #{slot}; exact profile llm_{slot}, без model hop."
                status = ("крафт-окно", "green")
            else:
                title = "LLM 4 · обычный pool reserve"
                subtitle = "Не создаёт четвёртое окно; остаётся доступным обычному item-level round-robin/failover."
                status = ("резерв", "neutral")
            card = self._card(parent, title, subtitle, icon=str(slot), status=status)
            self.row(card, "Включена", f"{prefix}_ENABLED", values=["0", "1"])
            self.row(card, "Провайдер", f"{prefix}_PROVIDER", values=["local", "openrouter", "openai_compat"])
            self.row(card, "Base URL", f"{prefix}_BASE_URL", hint="Можно оставить пустым для стандартного OpenRouter URL или основного LM Studio URL.")
            self.row(card, "API key", f"{prefix}_API_KEY", secret=True)
            self.row(card, "Модель", f"{prefix}_MODEL", hint="Для lane 2/3 пустая модель означает честный отказ этого окна и refund.")
            self.row(card, "OpenRouter provider slug", f"{prefix}_OPENROUTER_PROVIDER", hint="Независимый exact upstream slug для этого профиля; пусто = auto. При фиксации нет provider/profile failover.")
            self.row(card, "Режим API", f"{prefix}_API_MODE", values=["auto", "responses", "chat_completions"])
