from __future__ import annotations

"""Declarative browser settings metadata and pure field enablement rules."""

from infini_local.desktop.settings_schema import FIELD_HELP

_BASIC_FIELDS = frozenset({'INFINI_HOST', 'INFINI_PORT', 'INFINI_LLM_PROVIDER', 'INFINI_USE_LLM', 'INFINI_PROMPT_STYLE', 'INFINI_CODEX_LLM_MODEL', 'INFINI_LLM_REASONING_MODE', 'INFINI_LMSTUDIO_URL', 'INFINI_LMSTUDIO_MODEL', 'INFINI_OPENROUTER_API_KEY', 'INFINI_OPENROUTER_MODEL', 'INFINI_OPENROUTER_PROVIDER', 'INFINI_OPENAI_COMPAT_BASE_URL', 'INFINI_OPENAI_COMPAT_API_KEY', 'INFINI_OPENAI_COMPAT_MODEL', 'INFINI_IMAGE_BACKEND', 'INFINI_CODEX_IMAGE_MODEL', 'INFINI_CODEX_IMAGE_QUALITY', 'INFINI_CODEX_IMAGE_SIZE', 'INFINI_SDCPP_SERVER_EXE', 'INFINI_SDCPP_MODEL', 'INFINI_SDCPP_VAE', 'INFINI_SDCPP_LLM', 'INFINI_SDCPP_SERVER_AUTOSTART', 'INFINI_SDCPP_LORA_FILE', 'INFINI_SDCPP_LORA_WEIGHT', 'INFINI_SDCPP_SERVER_URL', 'INFINI_SDCPP_STEPS', 'INFINI_SDCPP_CFG', 'INFINI_SDCPP_SAMPLER', 'INFINI_IMAGE_API_BASE_URL', 'INFINI_IMAGE_API_KEY', 'INFINI_IMAGE_API_MODEL', 'INFINI_IMAGE_API_SIZE', 'INFINI_A1111_URL', 'INFINI_COMFYUI_URL', 'INFINI_BG_COLOR', 'INFINI_REMOVE_BG', 'INFINI_SPRITE_DOWNSCALE_FILTER', 'INFINI_MP_ASSET_TRANSPORT', 'INFINI_TERRARIA_PORT', 'INFINI_ASSET_PUBLIC_BASE_URL', 'INFINI_MULTIDEV_CONCURRENCY', 'INFINI_TRACE_PROMPTS'})


def _field(key, label, page, *, options=(), hint='', secret=False, multiline=False):
    return {'key': key, 'label': label, 'help': hint or FIELD_HELP.get(key, ''),
            'options': list(options), 'secret': secret, 'page': page,
            'advanced': key not in _BASIC_FIELDS and not key.startswith('INFINI_LLM_POOL_'),
            'multiline': multiline}


FIELDS = [
    _field('INFINI_HOST', 'Адрес сервера', 'configure', hint='127.0.0.1 — только ты; 0.0.0.0 — принимать подключения из Radmin/LAN.'),
    _field('INFINI_PORT', 'Порт сервера', 'configure'),
    _field('INFINI_CRAFT_HTTP_TIMEOUT_SECONDS', 'Ожидание крафта (сек.)', 'configure', hint='240 секунд: если крафт не готов, tModLoader попробует retry.'),
    _field('INFINI_CRAFT_HTTP_ATTEMPTS', 'Попыток крафта', 'configure'),
    _field('INFINI_COMBINE_BUSY_WAIT_SECONDS', 'Ожидание очереди (сек.)', 'configure', hint='Сколько секунд параллельный /combine ждёт текущий craft/cache вместо немедленного busy response. Для обычной игры: 210.'),
    _field('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED', 'Включить минимум для атакующих расходников', 'configure', hint='Применяется к delivery-копии fresh/cache-hit результата.', options=['1', '0']),
    _field('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD', 'Минимум за один крафт', 'configure', options=['2', '5', '10', '20', '25', '50', '99', '100', '250', '500', '999'], hint='Если authored craftYield/maxStack ниже, оба поднимаются до выбранного количества.'),
    _field('INFINI_MP_ASSET_TRANSPORT', 'Передача изображений', 'multiplayer', options=['native', 'http'], hint='native = PNG через Terraria packets; http = PNG через host /get_asset.'),
    _field('INFINI_ASSET_PUBLIC_BASE_URL', 'Внешний адрес ассетов', 'multiplayer', hint='Нужен только для HTTP: http://26.x.x.x:5055.'),
    _field('INFINI_TERRARIA_PORT', 'Порт Terraria', 'multiplayer', hint='Для друзей: Multiplayer → Join via IP → твой Radmin IP → этот порт. Обычно 7777.'),
    _field('INFINI_TRACE_PROMPTS', 'Полное логирование (без обрезки)', 'diagnostics', hint='По умолчанию включено. OFF: без дополнительных trace/артефактов/events; остаются краткие фатальные ошибки. Сохранить → перезапустить сервер.', options=['1', '0']),
    _field('INFINI_TRACE_MAX_PROMPT_CHARS', 'Символов в просмотре', 'diagnostics'),
    _field('INFINI_TRACE_EVENTS_TAIL', 'Событий в просмотре', 'diagnostics'),
    _field('INFINI_CONSOLE_EVENT_LEVEL', 'Сообщения в консоли', 'diagnostics', options=['warn', 'error', 'info', 'debug', 'off'], hint='Эхо событий в окно сервера. При полном логировании OFF остаются только краткие фатальные ошибки; off отключает и их эхо.'),
    _field('INFINI_USE_LLM', 'Использовать модель', 'providers', options=['1', '0'], hint='Главный переключатель LLM-авторинга. 0 допустим только для явных debug/dev сценариев.'),
    _field('INFINI_PROMPT_STYLE', 'Стиль промпта', 'providers', options=['Default', 'Terraria Like'], hint='Все режимы генерируют предметы для Terraria. Terraria Like — vanilla-like спрайты, палитра, читаемость и согласованные эффекты; не пресет механик.'),
    _field('INFINI_BALANCE_MODE', 'Balance mode', 'providers', options=['safety', 'normalize', 'report']),
    _field('INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK', 'Deterministic dev fallback', 'providers', options=['0', '1'], hint='Только для разработки: разрешает кодовый fallback, если LLM недоступна. В обычной игре оставлять 0.'),
    _field('INFINI_LLM_PROVIDER', 'Источник текста', 'providers', options=['local', 'openrouter', 'openai_compat', 'openai_codex']),
    _field('INFINI_CODEX_LLM_MODEL', 'Codex text model', 'providers', options=[], hint='Slug редактируемый. Перед генерацией выбери модель; пустое значение не запускает Codex. Ошибка обновления не стирает сохранённый slug.'),
    _field('INFINI_LMSTUDIO_URL', 'LM Studio URL', 'providers'),
    _field('INFINI_LMSTUDIO_MODEL', 'LM Studio model', 'providers'),
    _field('INFINI_OPENROUTER_API_KEY', 'OpenRouter API key', 'providers', secret=True),
    _field('INFINI_OPENROUTER_MODEL', 'OpenRouter model', 'providers', hint='auto или slug модели с OpenRouter.'),
    _field('INFINI_OPENROUTER_PROVIDER', 'OpenRouter provider slug', 'providers', hint='Пусто = auto. Точный slug из OpenRouter фиксирует площадку; при её недоступности нет перехода на другой profile/fallback.'),
    _field('INFINI_OPENROUTER_HTTP_REFERER', 'OpenRouter referer', 'providers'),
    _field('INFINI_OPENROUTER_APP_TITLE', 'OpenRouter title', 'providers'),
    _field('INFINI_OPENAI_COMPAT_BASE_URL', 'Адрес API', 'providers'),
    _field('INFINI_OPENAI_COMPAT_API_KEY', 'Ключ API', 'providers', secret=True),
    _field('INFINI_OPENAI_COMPAT_MODEL', 'Модель API', 'providers'),
    _field('INFINI_LLM_API_MODE', 'LLM 1 API mode', 'providers', options=['auto', 'responses', 'chat_completions'], hint='auto сначала пробует /responses и запоминает поддержку; при отказе тот же self-contained packet идёт через /chat/completions.'),
    _field('INFINI_LLM_FALLBACK_PROVIDER', 'Fallback provider', 'providers', options=['', 'local', 'openrouter', 'openai_compat'], hint='Пусто = использовать тот же провайдер, что и основной. Нужен только если хочешь при падении уйти на другой pipeline.'),
    _field('INFINI_LLM_FALLBACK_MODEL', 'Fallback model', 'providers', hint='Пусто = fallback выключен. Если основная модель умерла по бабкам/сети, сервер попробует эту модель.'),
    _field('INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER', 'OpenRouter provider slug', 'providers', hint='Отдельная фиксация upstream для OpenRouter fallback. Пусто = auto, не наследует основной slug. При фиксации основного профиля переход сюда запрещён.'),
    _field('INFINI_LLM_FALLBACK_BASE_URL', 'Fallback base URL', 'providers', hint='Пусто = взять base URL от fallback provider по умолчанию/из основных полей.'),
    _field('INFINI_LLM_FALLBACK_API_KEY', 'Fallback API key', 'providers', hint='Пусто = использовать основной ключ выбранного fallback provider.', secret=True),
    _field('INFINI_LLM_FALLBACK_NETWORK_FAILS', 'Fallback after transport fails', 'providers', hint='Сколько сетевых/timeout падений подряд терпеть на основной модели, прежде чем уходить на fallback. По умолчанию 2.'),
    _field('INFINI_LLM_RESPONSE_FORMAT', 'Response format', 'providers', options=['auto', 'json_schema', 'json_object', 'off']),
    _field('INFINI_LLM_TEMPERATURE', 'Разнообразие ответа', 'providers', hint='Температура основной LLM, которая пишет gameplay/runtime contract. 0.30-0.45: стабильнее; 0.55-0.75: разнообразнее, но выше риск мусора в контракте. Не относится к fallback-модели.'),
    _field('INFINI_LLM_REAUTHOR_TEMPERATURE', 'Температура исправлений', 'providers', hint='Пусто = 0.12. Обычно 0.0-0.2 для scoped Repair; явно заданный INFINI_LLM_REPAIR_TEMPERATURE имеет приоритет.'),
    _field('INFINI_VISUAL_DIRECTOR_TEMPERATURE', 'Разнообразие образа', 'providers', hint='Температура отдельного LLM Visual Director для image prompts/visual kit. Это не sd.cpp temperature и не fallback; на sampler не влияет.'),
    _field('INFINI_CODEX_VISUAL_REASONING', 'Visual Director effort', 'providers', options=['inherit', 'model_default', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'], hint='Отдельный reasoning текстового Visual Director; inherit = усилие основной LLM, model_default = без effort в запросе; не image-модель.'),
    _field('INFINI_LLM_MAX_TOKENS', 'Бюджет ответа (токены)', 'providers', hint='Другие провайдеры: бюджет ответа. Codex /responses не принимает max_output_tokens: поле не отправляется и не ограничивает квоту; применяются только временные/байтовые ограничения.'),
    _field('INFINI_LLM_REASONING_MODE', 'Рассуждение', 'providers', options=['off', 'auto', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'tokens', 'prompt_light', 'prompt_strong'], hint='Codex: выбери effort текущей модели; другие провайдеры сохраняют свои API/prompt режимы.'),
    _field('INFINI_LLM_REASONING_MAX_TOKENS', 'Reasoning token budget', 'providers', hint='Используется при mode=tokens; OpenRouter мапит это на max_tokens/thinking_budget там, где модель поддерживает.'),
    _field('INFINI_LLM_REASONING_EXCLUDE', 'Hide reasoning output', 'providers', options=['1', '0'], hint='1 = reasoning используется, но не возвращается в message.content; меньше ломает JSON-парсер.'),
    _field('INFINI_LLM_LOCAL_REASONING_PROMPT', 'Local prompt reasoning', 'providers', options=['1', '0'], hint='Для локалок без API reasoning: разрешить короткий внутренний чек в system prompt. Цепочку мыслей выводить всё равно запрещено.'),
    _field('INFINI_MULTIDEV_CONCURRENCY', 'Параллельных окон', 'models', options=['2', '3'], hint='Верхний предел LocalGenerator. Команда в игре может открыть 2 или 3 окна, но не больше этого значения.'),
    _field('INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS', 'Cooldown после ошибки', 'models', hint='Для обычного round-robin/failover. Exact multi-dev lanes за соседней моделью не прячутся.'),
    _field('INFINI_LLM_POOL_2_ENABLED', 'Включена', 'models', options=['0', '1']),
    _field('INFINI_LLM_POOL_3_ENABLED', 'Включена', 'models', options=['0', '1']),
    _field('INFINI_LLM_POOL_4_ENABLED', 'Включена', 'models', options=['0', '1']),
    _field('INFINI_LLM_POOL_2_PROVIDER', 'Провайдер', 'models', options=['local', 'openrouter', 'openai_compat']),
    _field('INFINI_LLM_POOL_3_PROVIDER', 'Провайдер', 'models', options=['local', 'openrouter', 'openai_compat']),
    _field('INFINI_LLM_POOL_4_PROVIDER', 'Провайдер', 'models', options=['local', 'openrouter', 'openai_compat']),
    _field('INFINI_LLM_POOL_2_BASE_URL', 'Base URL', 'models', hint='Можно оставить пустым для стандартного OpenRouter URL или основного LM Studio URL.'),
    _field('INFINI_LLM_POOL_3_BASE_URL', 'Base URL', 'models', hint='Можно оставить пустым для стандартного OpenRouter URL или основного LM Studio URL.'),
    _field('INFINI_LLM_POOL_4_BASE_URL', 'Base URL', 'models', hint='Можно оставить пустым для стандартного OpenRouter URL или основного LM Studio URL.'),
    _field('INFINI_LLM_POOL_2_API_KEY', 'API key', 'models', secret=True),
    _field('INFINI_LLM_POOL_3_API_KEY', 'API key', 'models', secret=True),
    _field('INFINI_LLM_POOL_4_API_KEY', 'API key', 'models', secret=True),
    _field('INFINI_LLM_POOL_2_MODEL', 'Модель', 'models', hint='Для lane 2/3 пустая модель означает честный отказ этого окна и refund.'),
    _field('INFINI_LLM_POOL_3_MODEL', 'Модель', 'models', hint='Для lane 2/3 пустая модель означает честный отказ этого окна и refund.'),
    _field('INFINI_LLM_POOL_4_MODEL', 'Модель', 'models', hint='Для lane 2/3 пустая модель означает честный отказ этого окна и refund.'),
    _field('INFINI_LLM_POOL_2_OPENROUTER_PROVIDER', 'OpenRouter provider slug', 'models', hint='Независимый exact upstream slug для этого профиля; пусто = auto. При фиксации нет provider/profile failover.'),
    _field('INFINI_LLM_POOL_3_OPENROUTER_PROVIDER', 'OpenRouter provider slug', 'models', hint='Независимый exact upstream slug для этого профиля; пусто = auto. При фиксации нет provider/profile failover.'),
    _field('INFINI_LLM_POOL_4_OPENROUTER_PROVIDER', 'OpenRouter provider slug', 'models', hint='Независимый exact upstream slug для этого профиля; пусто = auto. При фиксации нет provider/profile failover.'),
    _field('INFINI_LLM_POOL_2_API_MODE', 'Режим API', 'models', options=['auto', 'responses', 'chat_completions']),
    _field('INFINI_LLM_POOL_3_API_MODE', 'Режим API', 'models', options=['auto', 'responses', 'chat_completions']),
    _field('INFINI_LLM_POOL_4_API_MODE', 'Режим API', 'models', options=['auto', 'responses', 'chat_completions']),
    _field('INFINI_IMAGE_BACKEND', 'Источник картинок', 'images', options=['sdcpp', 'openai_codex', 'image_api', 'off', 'comfyui', 'a1111'], hint='openai_codex = ChatGPT/Codex OAuth по подписке; sdcpp = локальная модель; image_api = отдельный API; off = без PNG.'),
    _field('INFINI_IMAGE_MAX_CONCURRENCY', 'Параллельных запросов', 'images', hint='Один общий GPU/sd-server: 1. Увеличивай только если backend действительно обслуживает параллельные image jobs без OOM/очереди внутри.'),
    _field('INFINI_CODEX_IMAGE_MODEL', 'Codex image model', 'images', options=['gpt-image-2'], hint='gpt-image-2 — встроенная известная модель. Ручное имя сохраняется, но не подтверждает доступ к нему.'),
    _field('INFINI_CODEX_IMAGE_QUALITY', 'Codex quality', 'images', options=['low', 'medium', 'high', 'auto']),
    _field('INFINI_CODEX_IMAGE_SIZE', 'Codex size', 'images', options=['1024x1024', '1536x1024', '1024x1536', 'auto']),
    _field('INFINI_CODEX_IMAGE_TIMEOUT', 'Codex timeout', 'images'),
    _field('INFINI_SDCPP_SERVER_EXE', 'sd-server.exe', 'images'),
    _field('INFINI_SDCPP_ROCM_COMPAT_ROOT', 'ROCm hybrid runtime', 'images', hint='Папка sdcpp-hybrid-gfx1030. ROCm/HIP/rocBLAS env применяется только к дочернему sd-server.exe.'),
    _field('INFINI_SDCPP_MODEL', 'Diffusion model', 'images', hint='FLUX.2 Klein или Z-Image *.gguf.'),
    _field('INFINI_SDCPP_VAE', 'VAE / AE', 'images', hint='Обычно ae.safetensors. GUI сам добавит --vae, руками в extra args не надо.'),
    _field('INFINI_SDCPP_LLM', 'Qwen / LLM', 'images', hint='Text encoder/Qwen *.gguf. GUI сам добавит --llm, руками в extra args не надо.'),
    _field('INFINI_SDCPP_LORA_FILE', 'LoRA file', 'images', hint='Выбери конкретный *.safetensors/*.ckpt/*.pt/*.pth. Имя файла и вес уйдут в структурированное поле lora[]; текстовый тег в модель не попадёт.'),
    _field('INFINI_SDCPP_LORA_WEIGHT', 'LoRA weight', 'images', hint='Для FLUX.2 pixel-art LoRA начинай с 0.20-0.30; 0.45+ заметно меняет форму и может ухудшать identity.'),
    _field('INFINI_SDCPP_LORA_PROMPT_TAGS', 'LoRA prompt tags', 'images', hint='Совместимый ввод <lora:name:weight>. Перед HTTP-вызовом теги удаляются из prompt и переводятся в lora[]; выбранный LoRA file задаёт точное имя файла.', multiline=True),
    _field('INFINI_SDCPP_SERVER_URL', 'sd.cpp URL', 'images'),
    _field('INFINI_SDCPP_SERVER_AUTOSTART', 'sd.cpp autostart', 'images', options=['1', '0']),
    _field('INFINI_SDCPP_SERVER_COMMAND_MODE', 'sd.cpp command mode', 'images', options=['safe_args', 'template'], hint='safe_args = рекомендуемый безопасный запуск без shell/template; template нужен только для нестандартного sd.cpp.'),
    _field('INFINI_SDCPP_SERVER_COMMAND_TEMPLATE', 'sd.cpp command', 'images'),
    _field('INFINI_SDCPP_SERVER_EXTRA_ARGS', 'sd.cpp extra args', 'images', hint='Только доп. флаги: -v, --diffusion-fa, --offload-to-cpu и т.п. VAE/Qwen лучше задавать полями выше.', multiline=True),
    _field('INFINI_SDCPP_SERVER_SHOW_CONSOLE', 'sd.cpp show console', 'images', options=['1', '0'], hint='1 = открыть отдельное окно sd-server.exe с живым логом. Полезно для отлова Z-Image крашей.'),
    _field('INFINI_SDCPP_SERVER_LOG_FILE', 'sd.cpp log file', 'images', hint='Если show console=0, stdout/stderr sd-server пишутся сюда. /sdcpp_debug покажет хвост.'),
    _field('INFINI_SDCPP_WIDTH', 'sd width', 'images'),
    _field('INFINI_SDCPP_HEIGHT', 'sd height', 'images'),
    _field('INFINI_SDCPP_STEPS', 'sd steps', 'images'),
    _field('INFINI_SDCPP_CFG', 'sd cfg', 'images'),
    _field('INFINI_SDCPP_SAMPLER', 'sd sampler', 'images'),
    _field('INFINI_SDCPP_SEED', 'sd seed', 'images', hint='-1 = случайный seed. Положительное число фиксирует результат для отладки.'),
    _field('INFINI_ZIMAGE_PROMPT_CONTRACT', 'Z-Image contract', 'images', options=['auto', '1', '0'], hint='Обычно auto. Это внутренний маркер для Z-Image payload/prompt contract.'),
    _field('INFINI_ZIMAGE_POSITIVE_ONLY', 'Positive-only prompt', 'images', options=['1', '0'], hint='Для Z-Image Turbo обычно 1: negative_prompt не используется, все запреты/техусловия в positive prompt.'),
    _field('INFINI_VISUAL_REQUIRE_ITEM_SPRITE', 'Require item sprite', 'images', options=['1', '0'], hint='1 = не доставлять свежий craft без валидного item PNG. Основной product contract; выключать только для явной диагностики.'),
    _field('INFINI_IMAGE_API_BASE_URL', 'Image API base', 'images'),
    _field('INFINI_IMAGE_API_KEY', 'Image API key', 'images', secret=True),
    _field('INFINI_IMAGE_API_MODEL', 'Image API model', 'images'),
    _field('INFINI_IMAGE_API_PATH', 'Image API path', 'images'),
    _field('INFINI_IMAGE_API_SIZE', 'Image API size', 'images', options=['512x512', '768x768', '1024x1024']),
    _field('INFINI_IMAGE_API_TIMEOUT', 'Image API timeout', 'images'),
    _field('INFINI_A1111_URL', 'A1111 URL', 'images'),
    _field('INFINI_COMFYUI_URL', 'ComfyUI URL', 'images'),
    _field('INFINI_REMOVE_BG', 'Удалять фон', 'sprites', options=['1', '0']),
    _field('INFINI_BG_REMOVE_MODE', 'Способ удаления фона', 'sprites', options=['sprite_keyer'], hint='Оставлен только sprite_keyer: Photoshop-like Magic Wand от краёв + refine/spill cleanup под Terraria sprites.'),
    _field('INFINI_BG_COLOR', 'Фон изображения', 'sprites', options=['magenta', 'transparent', 'white', 'black'], hint='transparent = модель запрашивается с alpha; локальный keyer не применяется. Chroma-цвет используется только при локальном удалении фона.'),
    _field('INFINI_CHROMA_TOLERANCE', 'Допуск цвета фона', 'sprites', hint='Допуск key-color удаления. Если белое/серое уносит — не повышать; обычно 34.'),
    _field('INFINI_ALPHA_THRESHOLD', 'Порог прозрачности', 'sprites', hint='Порог отсечения полупрозрачной альфы. Если края худеют — снизить до 20-24.'),
    _field('INFINI_SPRITE_KEYER_SPILL_RADIUS', 'Радиус очистки края', 'sprites', hint='sprite_keyer: radius узкой refine-edge зоны для подавления magenta spill. Обычно 3.'),
    _field('INFINI_SPRITE_KEYER_RESIDUE_STEPS', 'Проходов очистки', 'sprites', hint='sprite_keyer: сколько шагов проходить по connected magenta/dark-key residue от выбранного фона. Обычно 8.'),
    _field('INFINI_SPRITE_RETRIES', 'Попыток генерации', 'sprites'),
    _field('INFINI_SAVE_SPRITE_STAGES', 'Сохранять этапы PNG', 'sprites', options=['1', '0'], hint='1 = сохранять 00_raw / 10_bg_removed_fullres / 20_master_norm / 30_baked_final в cache\\sprites для дебага.'),
    _field('INFINI_SPRITE_MASTER_CANVAS', 'Промежуточный размер', 'sprites', hint='Большой промежуточный RGBA-canvas перед финальным 32/48/64 bake. Нужен для master-first нормализации: вырезали фон, вписали объект в 256x256, потом уже уменьшили в 32/48/64.'),
    _field('INFINI_SPRITE_DOWNSCALE_FILTER', 'Фильтр уменьшения', 'sprites', options=['box', 'bilinear', 'bicubic', 'lanczos'], hint='box — базовый фильтр; pipeline preset сохраняет выбранный фильтр. Reset BOX вернёт box и premultiplied=1.'),
    _field('INFINI_SPRITE_PREMULTIPLIED_RESIZE', 'Уменьшение с альфой', 'sprites', options=['1', '0'], hint='Убирает magenta bleed по краям при resize RGBA.'),
    _field('INFINI_SPRITE_CHROMA_DEFRINGE', 'Очистка цветного ореола', 'sprites', options=['1', '0'], hint='Консервативно удаляет остатки magenta-key только на краях alpha.'),
    _field('INFINI_PIXEL_POSTERIZE', 'Ограничивать палитру', 'sprites', options=['1', '0']),
    _field('INFINI_MAX_COLORS', 'Количество цветов', 'sprites'),
    _field('INFINI_VISUAL_STRICT_AI_AUTHORSHIP', 'Только авторство модели', 'sprites', options=['1', '0'], hint='1 = код не рисует за нейронку, только валидирует/ретраит.'),
    _field('INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK', 'Программный резерв', 'sprites', options=['0', '1']),
    _field('INFINI_VISUAL_ASSET_MODE', 'Визуальный комплект', 'sprites', options=['full', 'projectile', 'off']),
    _field('INFINI_VISUAL_DIRECTOR_LLM', 'Модель внешнего вида', 'sprites', options=['1', '0']),
    _field('INFINI_VISUAL_DIRECTOR_MAX_TOKENS', 'Бюджет описания образа', 'sprites', hint='Пусто = взять общий Max answer tokens. Если хочешь отдельно ограничить visual-kit шаг, задай число здесь.'),
    _field('INFINI_VFX_LLM_DIRECTOR', 'Модель эффектов', 'sprites', options=['1', '0']),
]


def disabled_reasons(values, lan_enabled=False):
    reasons = {field['key']: '' for field in FIELDS}

    def value(key, default=''):
        return str(values.get(key, default)).strip()

    def set_field_enabled(key, enabled, reason=''):
        reasons[key] = '' if enabled else reason
    provider = (value('INFINI_LLM_PROVIDER', 'local') or 'local').lower()
    llm_enabled = value('INFINI_USE_LLM', '1') == '1'
    backend = (value('INFINI_IMAGE_BACKEND', 'sdcpp') or 'sdcpp').lower()
    visual_mode = (value('INFINI_VISUAL_ASSET_MODE', 'full') or 'full').lower()
    reasoning_mode = (value('INFINI_LLM_REASONING_MODE', 'off') or 'off').lower().replace('-', '_')
    remove_bg = value('INFINI_REMOVE_BG', '1') == '1'
    bg_mode = (value('INFINI_BG_REMOVE_MODE', 'sprite_keyer') or 'sprite_keyer').lower().replace('-', '_')
    transparent_bg = value('INFINI_BG_COLOR', 'magenta').lower() == 'transparent'
    posterize = value('INFINI_PIXEL_POSTERIZE', '1') == '1'
    strict_ai = value('INFINI_VISUAL_STRICT_AI_AUTHORSHIP', '1') == '1'
    attack_consumable_debug = value('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED', '0') == '1'
    asset_transport = (value('INFINI_MP_ASSET_TRANSPORT', 'native') or 'native').lower()
    local_llm = ['INFINI_LMSTUDIO_URL', 'INFINI_LMSTUDIO_MODEL']
    openrouter_llm = ['INFINI_OPENROUTER_API_KEY', 'INFINI_OPENROUTER_MODEL', 'INFINI_OPENROUTER_PROVIDER', 'INFINI_OPENROUTER_HTTP_REFERER', 'INFINI_OPENROUTER_APP_TITLE']
    compat_llm = ['INFINI_OPENAI_COMPAT_BASE_URL', 'INFINI_OPENAI_COMPAT_API_KEY', 'INFINI_OPENAI_COMPAT_MODEL']
    for key in local_llm:
        set_field_enabled(key, provider == 'local', f'LLM provider сейчас `{provider}`, локальные LM Studio поля не используются.')
    for key in openrouter_llm:
        set_field_enabled(key, provider == 'openrouter', f'LLM provider сейчас `{provider}`, OpenRouter поля не используются.')
    for key in compat_llm:
        set_field_enabled(key, provider == 'openai_compat', f'LLM provider сейчас `{provider}`, compat API поля не используются.')
    set_field_enabled('INFINI_CODEX_LLM_MODEL', provider == 'openai_codex' and llm_enabled, 'Текстовая Codex-модель используется только при LLM provider=openai_codex и Use LLM=1.')
    set_field_enabled('INFINI_CODEX_VISUAL_REASONING', provider == 'openai_codex' and llm_enabled, 'Reasoning Visual Director используется только при текстовом Codex provider.')
    set_field_enabled('INFINI_LLM_MAX_TOKENS', provider != 'openai_codex', 'Codex /responses отвергает max_output_tokens; числовой лимит не отправляется и не ограничивает квоту.')
    for key in ('INFINI_LLM_TEMPERATURE', 'INFINI_LLM_REAUTHOR_TEMPERATURE', 'INFINI_VISUAL_DIRECTOR_TEMPERATURE'):
        enabled = provider != 'openai_codex' and (llm_enabled or key != 'INFINI_LLM_REAUTHOR_TEMPERATURE')
        reason = 'Codex /responses не принимает temperature; значение сохраняется для других провайдеров.' if provider == 'openai_codex' else 'Use LLM=0; scoped same-author repair не вызывается.'
        set_field_enabled(key, enabled, reason)
    set_field_enabled('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD', attack_consumable_debug, 'Debug minimum выключен; поставь галочку выше, чтобы выбрать batch size.')
    for slot in (2, 3, 4):
        enabled = value(f'INFINI_LLM_POOL_{slot}_ENABLED', '0') == '1'
        for suffix in ('PROVIDER', 'BASE_URL', 'API_KEY', 'MODEL', 'API_MODE'):
            set_field_enabled(f'INFINI_LLM_POOL_{slot}_{suffix}', enabled, f'LLM {slot} выключен; сначала установи Enabled = 1.')
        set_field_enabled(f'INFINI_LLM_POOL_{slot}_OPENROUTER_PROVIDER', enabled and value(f'INFINI_LLM_POOL_{slot}_PROVIDER', 'openai_compat').lower() == 'openrouter', 'Фиксация upstream доступна только для включённого OpenRouter профиля.')
    fallback_provider = (value('INFINI_LLM_FALLBACK_PROVIDER', '') or provider).lower()
    set_field_enabled('INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER', fallback_provider == 'openrouter' and bool(value('INFINI_LLM_FALLBACK_MODEL', '')), 'Нужны fallback model и OpenRouter в качестве fallback provider.')
    off_modes = {'', 'off', 'false', '0', 'disabled', 'disable', 'none', 'no_reasoning'}
    prompt_modes = {'prompt', 'prompt_light', 'prompt_strong', 'local_prompt', 'local_light', 'local_strong'}
    api_reasoning_active = provider != 'local' and reasoning_mode not in off_modes and (reasoning_mode not in prompt_modes)
    set_field_enabled('INFINI_LLM_REASONING_MAX_TOKENS', api_reasoning_active and provider != 'openai_codex' and (reasoning_mode in {'tokens', 'token_budget', 'max_tokens', 'budget'}), 'Codex не поддерживает reasoning token budget; у других провайдеров работает при mode=tokens.')
    set_field_enabled('INFINI_LLM_REASONING_EXCLUDE', api_reasoning_active and provider != 'openai_codex', 'Codex /responses не принимает exclude; другие API могут использовать этот флаг для reasoning output.')
    local_prompt_active = reasoning_mode in prompt_modes or (provider == 'local' and reasoning_mode not in off_modes)
    set_field_enabled('INFINI_LLM_LOCAL_REASONING_PROMPT', local_prompt_active, 'Prompt-only reasoning используется для local/prompt_* режимов; для обычного API reasoning это поле игнорируется.')
    sdcpp_keys = ['INFINI_SDCPP_SERVER_EXE', 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'INFINI_SDCPP_MODEL', 'INFINI_SDCPP_VAE', 'INFINI_SDCPP_LLM', 'INFINI_SDCPP_LORA_FILE', 'INFINI_SDCPP_LORA_WEIGHT', 'INFINI_SDCPP_LORA_PROMPT_TAGS', 'INFINI_SDCPP_SERVER_URL', 'INFINI_SDCPP_SERVER_AUTOSTART', 'INFINI_SDCPP_SERVER_COMMAND_MODE', 'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE', 'INFINI_SDCPP_SERVER_EXTRA_ARGS', 'INFINI_SDCPP_SERVER_SHOW_CONSOLE', 'INFINI_SDCPP_SERVER_LOG_FILE', 'INFINI_SDCPP_WIDTH', 'INFINI_SDCPP_HEIGHT', 'INFINI_SDCPP_STEPS', 'INFINI_SDCPP_CFG', 'INFINI_SDCPP_SAMPLER', 'INFINI_SDCPP_SEED', 'INFINI_ZIMAGE_PROMPT_CONTRACT', 'INFINI_ZIMAGE_POSITIVE_ONLY']
    image_api_keys = ['INFINI_IMAGE_API_BASE_URL', 'INFINI_IMAGE_API_KEY', 'INFINI_IMAGE_API_MODEL', 'INFINI_IMAGE_API_PATH', 'INFINI_IMAGE_API_SIZE', 'INFINI_IMAGE_API_TIMEOUT']
    for key in sdcpp_keys:
        set_field_enabled(key, backend == 'sdcpp', f'Image backend сейчас `{backend}`, sd.cpp/Z-Image поля не участвуют.')
    command_mode = (value('INFINI_SDCPP_SERVER_COMMAND_MODE', 'safe_args') or 'safe_args').lower()
    set_field_enabled('INFINI_SDCPP_SERVER_COMMAND_TEMPLATE', backend == 'sdcpp' and command_mode == 'template', 'Command mode = safe_args: server.py собирает argv сам; шаблон не используется и не может сломать --sampling-method.')
    for key in ('INFINI_CODEX_IMAGE_MODEL', 'INFINI_CODEX_IMAGE_QUALITY', 'INFINI_CODEX_IMAGE_SIZE', 'INFINI_CODEX_IMAGE_TIMEOUT'):
        set_field_enabled(key, backend == 'openai_codex', 'Эти поля используются только backend openai_codex.')
    for key in image_api_keys:
        set_field_enabled(key, backend == 'image_api', f'Image backend сейчас `{backend}`, Image API поля не участвуют.')
    set_field_enabled('INFINI_A1111_URL', backend == 'a1111', f'Image backend сейчас `{backend}`, A1111 URL не используется.')
    set_field_enabled('INFINI_COMFYUI_URL', backend == 'comfyui', f'Image backend сейчас `{backend}`, ComfyUI URL не используется.')
    if asset_transport != 'http':
        set_field_enabled('INFINI_ASSET_PUBLIC_BASE_URL', False, 'Asset transport=native; PNG идут через Terraria packets, внешний URL не используется.')
    elif not lan_enabled:
        set_field_enabled('INFINI_ASSET_PUBLIC_BASE_URL', False, 'Radmin/LAN overlay выключен; внешний URL ассетов не нужен для локальной игры.')
    else:
        set_field_enabled('INFINI_ASSET_PUBLIC_BASE_URL', True, '')
    image_active = backend != 'off'
    asset_pack_active = image_active and visual_mode in {'full', 'all', 'projectile', 'visualpack', 'assetpack'}
    for key in ['INFINI_VISUAL_DIRECTOR_LLM', 'INFINI_VFX_LLM_DIRECTOR']:
        set_field_enabled(key, asset_pack_active, 'Visual asset mode сейчас off или image backend выключен; director-pass не вызывается.')
    set_field_enabled('INFINI_IMAGE_MAX_CONCURRENCY', image_active, 'Image backend=off; image request gate не участвует.')
    sprite_processing_active = image_active
    for key in ['INFINI_REMOVE_BG', 'INFINI_SPRITE_RETRIES', 'INFINI_PIXEL_POSTERIZE', 'INFINI_VISUAL_STRICT_AI_AUTHORSHIP']:
        set_field_enabled(key, sprite_processing_active, 'Image backend = off; PNG не генерируются, sprite postprocess не запускается.')
    alpha_reason = 'Модель запрашивается с alpha; локальный keyer не применяется.'
    keyer_reason = alpha_reason if sprite_processing_active else 'Image backend=off; sprite postprocess не запускается.'
    sprite_keyer_active = sprite_processing_active and remove_bg and (not transparent_bg) and (bg_mode not in {'off', 'none'})
    set_field_enabled('INFINI_REMOVE_BG', sprite_processing_active and (not transparent_bg), keyer_reason)
    set_field_enabled('INFINI_BG_REMOVE_MODE', sprite_keyer_active, keyer_reason)
    for key in ['INFINI_CHROMA_TOLERANCE', 'INFINI_SPRITE_KEYER_SPILL_RADIUS', 'INFINI_SPRITE_KEYER_RESIDUE_STEPS', 'INFINI_SPRITE_CHROMA_DEFRINGE']:
        set_field_enabled(key, sprite_keyer_active, keyer_reason)
    set_field_enabled('INFINI_BG_COLOR', sprite_processing_active, 'Image backend=off; фон не запрашивается.')
    set_field_enabled('INFINI_ALPHA_THRESHOLD', sprite_processing_active, 'Image backend=off; alpha cleanup не запускается.')
    set_field_enabled('INFINI_MAX_COLORS', sprite_processing_active and posterize, 'Max colors используется только когда Posterize=1 и image backend не off.')
    if sprite_processing_active:
        set_field_enabled('INFINI_SPRITE_MASTER_CANVAS', True, '')
        set_field_enabled('INFINI_SPRITE_DOWNSCALE_FILTER', True, '')
        set_field_enabled('INFINI_SPRITE_PREMULTIPLIED_RESIZE', True, '')
    if strict_ai:
        set_field_enabled('INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK', False, 'Strict AI authorship=1: procedural fallback принудительно выключен, чтобы код не авторил картинку за модель.')
    else:
        set_field_enabled('INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK', sprite_processing_active, 'Image backend=off; fallback PNG не нужен.')
    return reasons
