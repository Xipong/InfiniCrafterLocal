/* Infinicraft Studio. Same-origin bridge; drafts stay in memory, Save writes local config. */
'use strict';
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const routes = {
    operate: ['Рабочий стол', '', 'Генератор', 'Запуск, состояние и настройки генератора предметов для Terraria.'],
    configure: ['Конфигурация', '', 'Конфигурация', 'Один профиль объединяет механику, изображение и обработку спрайта.'],
    providers: ['Идея и механика', '', 'Текстовая модель', 'Источник модели, параметры ответа и генерация механики предмета.'],
    images: ['Изображения', '', 'Изображения', 'Источник изображений и параметры исходного рисунка.'],
    sprites: ['Спрайты и цвет', '', 'Спрайты и цвет', 'Прозрачность, чистые края и читаемый силуэт в Terraria.'],
    models: ['Модели и LoRA', '', 'Модели и LoRA', 'Локальные модели, текстовый энкодер и художественные адаптеры.'],
    multiplayer: ['Совместная игра', '', 'Совместная игра', 'Соединение с генератором и доставка изображений другим игрокам.'],
    diagnostics: ['Диагностика', '', 'Диагностика', 'Состояние соединения, события и реальные этапы генерации.']
  };
  const names = {
    INFINI_USE_LLM:'Авторство нейросети', INFINI_PROMPT_STYLE:'Художественное направление', INFINI_BALANCE_MODE:'Баланс предметов', INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK:'Технический запасной генератор', INFINI_GUI_PIPELINE_PRESET:'Профиль настроек', INFINI_LLM_PROVIDER:'Источник идей и механики', INFINI_CODEX_LLM_MODEL:'Текстовая модель Codex', INFINI_LMSTUDIO_URL:'Адрес LM Studio', INFINI_LMSTUDIO_MODEL:'Локальная текстовая модель', INFINI_OPENROUTER_API_KEY:'Ключ OpenRouter', INFINI_OPENROUTER_MODEL:'Модель OpenRouter', INFINI_OPENROUTER_PROVIDER:'Площадка OpenRouter', INFINI_OPENROUTER_HTTP_REFERER:'Источник запросов', INFINI_OPENROUTER_APP_TITLE:'Имя приложения в OpenRouter', INFINI_OPENAI_COMPAT_BASE_URL:'Адрес совместимого API', INFINI_OPENAI_COMPAT_API_KEY:'Ключ совместимого API', INFINI_OPENAI_COMPAT_MODEL:'Модель совместимого API', INFINI_LLM_API_MODE:'Формат запроса к модели', INFINI_LLM_RESPONSE_FORMAT:'Формат ответа', INFINI_LLM_TEMPERATURE:'Вариативность идеи', INFINI_LLM_REAUTHOR_TEMPERATURE:'Вариативность исправления', INFINI_VISUAL_DIRECTOR_TEMPERATURE:'Вариативность арт-директора', INFINI_LLM_MAX_TOKENS:'Лимит ответа, токены', INFINI_LLM_TIMEOUT:'Ожидание LLM-стадии, секунды', INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS:'Лимит VFX, токены', INFINI_VFX_LLM_DIRECTOR_TIMEOUT:'Ожидание VFX, секунды', INFINI_LLM_REASONING_MODE:'Глубина рассуждения', INFINI_LLM_REASONING_MAX_TOKENS:'Бюджет рассуждения, токены', INFINI_LLM_REASONING_EXCLUDE:'Не возвращать рассуждение в ответ', INFINI_LLM_LOCAL_REASONING_PROMPT:'Приватная самопроверка', INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS:'Пауза после сбоя, секунды', INFINI_LLM_FALLBACK_PROVIDER:'Запасной источник', INFINI_LLM_FALLBACK_MODEL:'Запасная модель', INFINI_LLM_FALLBACK_BASE_URL:'Адрес запасного API', INFINI_LLM_FALLBACK_API_KEY:'Ключ запасного API', INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER:'Запасная площадка OpenRouter', INFINI_LLM_FALLBACK_NETWORK_FAILS:'Сетевых сбоев до переключения',
    INFINI_IMAGE_BACKEND:'Источник изображений', INFINI_IMAGE_MAX_CONCURRENCY:'Параллельных изображений', INFINI_SDCPP_SERVER_EXE:'Программа sd.cpp', INFINI_SDCPP_ROCM_COMPAT_ROOT:'Папка совместимости ROCm', INFINI_SDCPP_MODEL:'Диффузионная модель', INFINI_SDCPP_VAE:'Модель VAE / AE', INFINI_SDCPP_LLM:'Текстовый энкодер', INFINI_SDCPP_LORA_DIR:'Папка LoRA', INFINI_SDCPP_LORA_FILE:'Файл LoRA', INFINI_SDCPP_LORA_WEIGHT:'Сила LoRA', INFINI_SDCPP_LORA_PROMPT_TAGS:'Теги LoRA', INFINI_SDCPP_SERVER_URL:'Адрес sd.cpp', INFINI_SDCPP_SERVER_AUTOSTART:'Способ запуска sd.cpp', INFINI_SDCPP_SERVER_COMMAND_MODE:'Способ запуска sd.cpp', INFINI_SDCPP_SERVER_COMMAND_TEMPLATE:'Шаблон команды запуска', INFINI_SDCPP_SERVER_EXTRA_ARGS:'Дополнительные аргументы', INFINI_SDCPP_SERVER_SHOW_CONSOLE:'Показывать консоль sd.cpp', INFINI_SDCPP_SERVER_LOG_FILE:'Файл журнала sd.cpp', INFINI_SDCPP_WIDTH:'Ширина исходника, px', INFINI_SDCPP_HEIGHT:'Высота исходника, px', INFINI_SDCPP_STEPS:'Шаги генерации', INFINI_SDCPP_CFG:'Влияние промпта / CFG', INFINI_SDCPP_SAMPLER:'Сэмплер', INFINI_SDCPP_SEED:'Seed изображения', INFINI_ZIMAGE_PROMPT_CONTRACT:'Правила промпта Z-Image', INFINI_ZIMAGE_POSITIVE_ONLY:'Только позитивный промпт', INFINI_CODEX_IMAGE_MODEL:'Модель изображений Codex', INFINI_CODEX_IMAGE_QUALITY:'Качество изображения', INFINI_CODEX_IMAGE_SIZE:'Размер изображения', INFINI_CODEX_IMAGE_TIMEOUT:'Ожидание Codex, секунды', INFINI_CODEX_VISUAL_REASONING:'Рассуждение арт-директора Codex', INFINI_IMAGE_API_BASE_URL:'Адрес API изображений', INFINI_IMAGE_API_KEY:'Ключ API изображений', INFINI_IMAGE_API_MODEL:'Модель изображений API', INFINI_IMAGE_API_PATH:'Путь API генерации', INFINI_IMAGE_API_SIZE:'Размер исходного изображения', INFINI_IMAGE_API_TIMEOUT:'Ожидание API, секунды', INFINI_A1111_URL:'Адрес Automatic1111', INFINI_COMFYUI_URL:'Адрес ComfyUI',
    INFINI_VISUAL_ASSET_MODE:'Состав визуальных ассетов', INFINI_VISUAL_DIRECTOR_LLM:'Нейросетевой арт-директор', INFINI_VISUAL_DIRECTOR_MAX_TOKENS:'Лимит арт-директора, токены', INFINI_VFX_LLM_DIRECTOR:'Нейросетевые визуальные эффекты', INFINI_REMOVE_BG:'Удалять фон', INFINI_BG_REMOVE_MODE:'Метод удаления фона', INFINI_BG_COLOR:'Фон исходного рисунка', INFINI_CHROMA_TOLERANCE:'Допуск цвета фона', INFINI_ALPHA_THRESHOLD:'Порог прозрачности', INFINI_SPRITE_KEYER_SPILL_RADIUS:'Радиус очистки краёв', INFINI_SPRITE_KEYER_RESIDUE_STEPS:'Шаги очистки остаточного цвета', INFINI_SPRITE_RETRIES:'Повторы при дефекте спрайта', INFINI_SAVE_SPRITE_STAGES:'Сохранять промежуточные спрайты', INFINI_PIXEL_POSTERIZE:'Ограничивать палитру', INFINI_MAX_COLORS:'Количество цветов', INFINI_SPRITE_MASTER_CANVAS:'Промежуточный холст, px', INFINI_SPRITE_DOWNSCALE_FILTER:'Фильтр уменьшения', INFINI_SPRITE_CHROMA_DEFRINGE:'Очищать цветные ореолы', INFINI_SPRITE_PREMULTIPLIED_RESIZE:'Учитывать прозрачность при resize', INFINI_VISUAL_STRICT_AI_AUTHORSHIP:'Строгое авторство модели', INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK:'Запасное процедурное изображение', INFINI_VISUAL_REQUIRE_ITEM_SPRITE:'Требовать спрайт предмета',
    INFINI_HOST:'Интерфейс генератора', INFINI_PORT:'Порт генератора', INFINI_MP_ASSET_TRANSPORT:'Доставка спрайтов друзьям', INFINI_ASSET_PUBLIC_BASE_URL:'Публичный адрес ассетов', INFINI_TERRARIA_PORT:'Порт Terraria', INFINI_CRAFT_HTTP_TIMEOUT_SECONDS:'Ожидание крафта, секунды', INFINI_CRAFT_HTTP_ATTEMPTS:'Попытки соединения', INFINI_COMBINE_BUSY_WAIT_SECONDS:'Ожидание очереди, секунды', INFINI_MULTIDEV_CONCURRENCY:'Параллельные окна разработчика', INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED:'Отладочная выдача расходников', INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD:'Минимальная выдача расходников', INFINI_TRACE_PROMPTS:'Записывать промпты и этапы', INFINI_TRACE_MAX_PROMPT_CHARS:'Лимит предпросмотра, символы', INFINI_TRACE_EVENTS_TAIL:'Событий в журнале', INFINI_CONSOLE_EVENT_LEVEL:'Подробность консоли'
  };
  const shortHelp = {
    INFINI_LLM_PROVIDER:'Кто придумывает свойства и пишет механику предмета.', INFINI_LMSTUDIO_URL:'Локальный OpenAI-compatible сервер. Обычно порт 1234.', INFINI_LMSTUDIO_MODEL:'Точное имя модели или auto — выбор на стороне сервера.', INFINI_OPENROUTER_API_KEY:'При сохранении ключ записывается в локальный config.env. В профили не копируется.', INFINI_OPENAI_COMPAT_API_KEY:'Не API-ключ Codex. Только для выбранного совместимого сервиса.', INFINI_PROMPT_STYLE:'Меняет художественное направление, а не модель или механику.', INFINI_LLM_REASONING_MODE:'Дополнительная самопроверка. Доступность зависит от модели.', INFINI_IMAGE_BACKEND:'Локальный движок, подписка или внешний API.', INFINI_SDCPP_SERVER_URL:'Адрес локального сервера изображений, не этой студии.', INFINI_SDCPP_SERVER_AUTOSTART:'Внешний — только URL. Управляемый — программа и файлы моделей на этом ПК.', INFINI_SDCPP_SERVER_EXE:'Путь к sd-server.exe на этом компьютере.', INFINI_SDCPP_MODEL:'Файл основной FLUX / Z-Image модели, обычно GGUF.', INFINI_SDCPP_LLM:'Текстовый энкодер, совместимый с основной моделью.', INFINI_SDCPP_VAE:'Декодер, совместимый с основной моделью.', INFINI_SDCPP_LORA_FILE:'Выбери существующий файл художественного адаптера.', INFINI_SDCPP_LORA_WEIGHT:'Для pixel-art адаптера начни с 0.20–0.30.', INFINI_BG_COLOR:'Прозрачный — native alpha. Другие цвета — chroma-key.', INFINI_SPRITE_DOWNSCALE_FILTER:'BOX — базовый фильтр. Сброс также включит premultiplied resize.', INFINI_HOST:'127.0.0.1 — этот ПК; 0.0.0.0 — принимать подключения из сети.', INFINI_MP_ASSET_TRANSPORT:'Внутри Terraria — без отдельного публичного HTTP-адреса.', INFINI_TRACE_PROMPTS:'Полный локальный журнал растёт до ручной очистки.'
  };
  const optionNames = {
    INFINI_LLM_PROVIDER:{local:'LM Studio · локально',openrouter:'OpenRouter',openai_compat:'Совместимый API',openai_codex:'ChatGPT / Codex'},
    INFINI_IMAGE_BACKEND:{sdcpp:'sd.cpp · локально',openai_codex:'ChatGPT / Codex',image_api:'Внешний Image API',off:'Без изображений',comfyui:'ComfyUI',a1111:'Automatic1111'},
    INFINI_PROMPT_STYLE:{Default:'Свободное направление', 'Terraria Like':'В духе Terraria'},
    INFINI_BALANCE_MODE:{safety:'Авторский баланс + защита',normalize:'Мягкая нормализация',report:'Только рекомендации'},
    INFINI_BG_COLOR:{transparent:'Прозрачный · native alpha',magenta:'Магента · chroma-key',green:'Зелёный · chroma-key',white:'Белый',black:'Чёрный'},
    INFINI_MP_ASSET_TRANSPORT:{native:'Внутри Terraria · рекомендуется',http:'По HTTP с хост-компьютера'},
    INFINI_SDCPP_SERVER_COMMAND_MODE:{safe_args:'Автоматически · рекомендуется',template:'Ручной шаблон'},
    INFINI_SPRITE_DOWNSCALE_FILTER:{box:'BOX · базовый',bilinear:'Bilinear',bicubic:'Bicubic',lanczos:'Lanczos'},
    INFINI_CODEX_IMAGE_QUALITY:{low:'Быстро / low',medium:'Стандарт / medium',high:'Детально / high',auto:'Автоматически'},
    INFINI_LLM_REASONING_MODE:{off:'Не задавать общий effort',auto:'Автоматически',prompt_light:'Короткая самопроверка',prompt_strong:'Подробная самопроверка',tokens:'Отдельный бюджет токенов'}
  };
  const modelKeys = new Set(['INFINI_SDCPP_MODEL','INFINI_SDCPP_VAE','INFINI_SDCPP_LLM']);
  const materialKeys = new Set([...modelKeys,'INFINI_SDCPP_LORA_DIR','INFINI_SDCPP_LORA_FILE','INFINI_SDCPP_LORA_WEIGHT','INFINI_SDCPP_LORA_PROMPT_TAGS','INFINI_SDCPP_SERVER_EXE','INFINI_SDCPP_ROCM_COMPAT_ROOT']);
  const basicKeys = new Set(Object.keys(shortHelp).concat(['INFINI_USE_LLM','INFINI_LLM_TEMPERATURE','INFINI_LLM_MAX_TOKENS','INFINI_OPENROUTER_MODEL','INFINI_OPENROUTER_PROVIDER','INFINI_OPENAI_COMPAT_BASE_URL','INFINI_OPENAI_COMPAT_MODEL','INFINI_CODEX_LLM_MODEL','INFINI_SDCPP_STEPS','INFINI_SDCPP_CFG','INFINI_SDCPP_SAMPLER','INFINI_SDCPP_WIDTH','INFINI_SDCPP_HEIGHT','INFINI_CODEX_IMAGE_MODEL','INFINI_CODEX_IMAGE_SIZE','INFINI_CODEX_IMAGE_QUALITY','INFINI_IMAGE_API_BASE_URL','INFINI_IMAGE_API_KEY','INFINI_IMAGE_API_MODEL','INFINI_IMAGE_API_SIZE','INFINI_A1111_URL','INFINI_COMFYUI_URL','INFINI_REMOVE_BG','INFINI_PIXEL_POSTERIZE','INFINI_MAX_COLORS','INFINI_SPRITE_MASTER_CANVAS','INFINI_PORT','INFINI_TERRARIA_PORT','INFINI_ASSET_PUBLIC_BASE_URL']));
  const state = {remote:null, draft:{}, baseline:{}, fields:[], dirty:new Set(), edits:{}, editClock:0, lan:false, baselineLan:false, lanEdit:0, page:'operate', connected:false, pending:null, submission:null, posting:false, pollTimer:null, fetching:false, filter:'', searchIndex:0, searchMatches:[], traceTab:'summary', openDetails:new Set(), helpFields:new Set(), shutdown:false, seenNotifications:new Set(), notifications:[], picker:null};
  const token = window.INFINI_BOOTSTRAP?.token || '';
  // Keep the launcher's bootstrap query for authenticated refresh. Never render or log it.
  function label(field) {
    if (names[field.key]) return names[field.key];
    const pool = field.key.match(/^INFINI_LLM_POOL_([234])_(.+)$/);
    if (pool) return `${{ENABLED:'Использовать модель',PROVIDER:'Источник',BASE_URL:'Адрес API',API_KEY:'Ключ API',MODEL:'Модель',OPENROUTER_PROVIDER:'Площадка OpenRouter',API_MODE:'Формат запроса'}[pool[2]] || pool[2]} · линия ${pool[1]}`;
    return field.label || field.key.replace(/^INFINI_/,'').replaceAll('_',' ');
  }
  function pageFor(key, suggested='configure') {
    if (materialKeys.has(key)) return 'models';
    if (/^INFINI_(HOST|PORT|MP_|ASSET_PUBLIC|TERRARIA_PORT|CRAFT_HTTP|COMBINE_BUSY|MULTIDEV)/.test(key)) return 'multiplayer';
    if (/^INFINI_(TRACE_|CONSOLE_|DEBUG_|ALLOW_DETERMINISTIC)/.test(key)) return 'diagnostics';
    if (/^INFINI_(LLM_|LMSTUDIO_|OPENROUTER_|OPENAI_COMPAT_|USE_LLM|PROMPT_STYLE|BALANCE_MODE|CODEX_LLM|CODEX_VISUAL|VISUAL_DIRECTOR_TEMPERATURE)/.test(key)) return 'providers';
    if (/^INFINI_(IMAGE_|SDCPP_|ZIMAGE_|CODEX_IMAGE|A1111_|COMFYUI_)/.test(key)) return 'images';
    if (/^INFINI_(VISUAL_|VFX_|SPRITE_|REMOVE_BG|BG_|CHROMA_|ALPHA_|SAVE_SPRITE|PIXEL_|MAX_COLORS)/.test(key)) return 'sprites';
    return ({trace:'diagnostics',diagnostics:'diagnostics',network:'multiplayer',sdcpp:'images'}[suggested]) || (routes[suggested] ? suggested : 'configure');
  }
  // Match credential words, not numeric budgets such as MAX_TOKENS.
  const isCredentialKey = key => /(?:^|_)(?:API_KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?)(?:_|$)/i.test(key);
  function makeFields(remote) {
    const map = new Map((remote.fields || []).map(field => [field.key,{...field}]));
    Object.keys({...remote.defaults,...remote.values}).filter(key => key.startsWith('INFINI_')).forEach(key => {
      if (!map.has(key)) map.set(key,{key,label:names[key],help:remote.fieldHelp?.[key] || '',options:[],secret:isCredentialKey(key),advanced:!basicKeys.has(key),synthetic:true});
    });
    return [...map.values()].map(field => ({...field,secret:field.secret || isCredentialKey(field.key),route:pageFor(field.key,field.page)}));
  }
  function value(key, fallback='') { return state.draft[key] ?? fallback; }
  function recomputeDirty() {
    state.dirty = new Set(Object.keys(state.draft).filter(key => state.draft[key] !== (state.baseline[key] ?? '')));
    $('#save-tray').hidden = !state.dirty.size && state.lan === state.baselineLan;
    const total = state.dirty.size + Number(state.lan !== state.baselineLan);
    $('#dirty-label').textContent = `${total} ${total === 1 ? 'изменение' : total < 5 ? 'изменения' : 'изменений'} в настройках`;
    const conflict=$('#draft-conflict');
    if(conflict) conflict.hidden=!(state.remote?.savedRevision && state.savedRevision && state.remote.savedRevision !== state.savedRevision && total);
    updateActionButtons();
  }
  function inactiveReason(field) {
    const key = field.key, provider = value('INFINI_LLM_PROVIDER','local'), backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    const pool=key.match(/^INFINI_LLM_POOL_([234])_(.+)$/);
    if(pool && pool[2] !== 'ENABLED' && value(`INFINI_LLM_POOL_${pool[1]}_ENABLED`) !== '1') return 'Дополнительная линия выключена';
    if (pool && pool[2] === 'OPENROUTER_PROVIDER' && value(`INFINI_LLM_POOL_${pool[1]}_PROVIDER`) !== 'openrouter') return 'Для линии OpenRouter';
    if (['INFINI_LLM_TEMPERATURE','INFINI_LLM_REAUTHOR_TEMPERATURE','INFINI_VISUAL_DIRECTOR_TEMPERATURE','INFINI_LLM_MAX_TOKENS','INFINI_LLM_REASONING_MAX_TOKENS','INFINI_LLM_REASONING_EXCLUDE'].includes(key) && provider === 'openai_codex') return 'Codex не принимает этот параметр';
    if (key === 'INFINI_CODEX_VISUAL_REASONING' && provider !== 'openai_codex') return 'Для текстового Codex';
    if (key === 'INFINI_LLM_REASONING_MAX_TOKENS' && (provider === 'local' || !['tokens','token_budget','max_tokens','budget'].includes(value('INFINI_LLM_REASONING_MODE')))) return 'Для API с режимом бюджета токенов';
    if (key === 'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD' && value('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED') !== '1') return 'Отладочная выдача выключена';
    if (['INFINI_REMOVE_BG','INFINI_BG_REMOVE_MODE','INFINI_CHROMA_TOLERANCE','INFINI_SPRITE_KEYER_SPILL_RADIUS','INFINI_SPRITE_KEYER_RESIDUE_STEPS','INFINI_SPRITE_CHROMA_DEFRINGE'].includes(key) && value('INFINI_BG_COLOR') === 'transparent') return 'Нативная прозрачность: локальный keyer не используется';
    if (['INFINI_BG_REMOVE_MODE','INFINI_CHROMA_TOLERANCE','INFINI_SPRITE_KEYER_SPILL_RADIUS','INFINI_SPRITE_KEYER_RESIDUE_STEPS','INFINI_SPRITE_CHROMA_DEFRINGE'].includes(key) && value('INFINI_REMOVE_BG') === '0') return 'Удаление фона выключено';
    if (/^INFINI_LMSTUDIO_/.test(key) && provider !== 'local') return 'Для локального источника текста';
    if (/^INFINI_OPENROUTER_/.test(key) && provider !== 'openrouter') return 'Для источника OpenRouter';
    if (/^INFINI_OPENAI_COMPAT_/.test(key) && provider !== 'openai_compat') return 'Для совместимого API';
    if (/^INFINI_CODEX_LLM_/.test(key) && provider !== 'openai_codex') return 'Для ChatGPT / Codex';
    if (/^INFINI_(SDCPP_|ZIMAGE_)/.test(key) && backend !== 'sdcpp') return 'Для локального sd.cpp';
    if (['INFINI_SDCPP_SERVER_EXE','INFINI_SDCPP_ROCM_COMPAT_ROOT','INFINI_SDCPP_MODEL','INFINI_SDCPP_VAE','INFINI_SDCPP_LLM','INFINI_SDCPP_SERVER_COMMAND_MODE','INFINI_SDCPP_SERVER_COMMAND_TEMPLATE','INFINI_SDCPP_SERVER_EXTRA_ARGS','INFINI_SDCPP_SERVER_SHOW_CONSOLE','INFINI_SDCPP_SERVER_LOG_FILE'].includes(key) && value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1') return 'Для управляемого запуска sd.cpp';
    if (/^INFINI_CODEX_IMAGE_/.test(key) && backend !== 'openai_codex') return 'Для изображений ChatGPT / Codex';
    if (/^INFINI_IMAGE_API_/.test(key) && backend !== 'image_api') return 'Для внешнего Image API';
    if (key === 'INFINI_A1111_URL' && backend !== 'a1111') return 'Для Automatic1111';
    if (key === 'INFINI_COMFYUI_URL' && backend !== 'comfyui') return 'Для ComfyUI';
    if (field.route === 'sprites' && backend === 'off') return 'Изображения выключены';
    if (key === 'INFINI_MAX_COLORS' && value('INFINI_PIXEL_POSTERIZE') !== '1') return 'Палитра не ограничена';
    if (key === 'INFINI_ASSET_PUBLIC_BASE_URL' && value('INFINI_MP_ASSET_TRANSPORT') !== 'http') return 'Доставка идёт внутри Terraria';
    if (key === 'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE' && value('INFINI_SDCPP_SERVER_COMMAND_MODE') !== 'template') return 'Запуск использует автоматический argv';
    // Native metadata describes the controller values, not unsaved browser edits.
    if (field.disabled && !state.dirty.size && state.lan === state.baselineLan && Object.entries(state.remote?.values || {}).every(([name,val])=>value(name) === val)) return field.disabled;
    return '';
  }
  async function api(path, payload) {
    if (!token) throw new Error('Открой студию через локальный запускатор. Токен сессии не получен.');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(),12000);
    try {
      const response = await fetch(path,{method:payload ? 'POST':'GET',cache:'no-store',credentials:'same-origin',headers:{'X-Infini-Token':token,...(payload ? {'Content-Type':'application/json'}:{})},body:payload ? JSON.stringify(payload):undefined,signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(response.status === 403 ? 'Сессия недоступна. Открой студию заново через запускатор.' : data.error || `Ошибка локального соединения (${response.status})`);
      return data;
    } finally {clearTimeout(timer);}
  }
  function setConnection(connected, message='') {
    state.connected = connected;
    const connection = $('#connection');
    connection.className = `connection is-${connected ? 'online':'offline'}`;
    connection.innerHTML = `<span class="status-dot"></span><span>${connected ? 'Студия на связи':'Нет связи'}</span>`;
    $('#connection-banner').hidden = connected || state.shutdown;
    if (!connected && !state.shutdown) $('#connection-banner').innerHTML = `<span>${esc(message)} Изменения остаются в этой вкладке.</span><button data-ui="retry">Повторить</button>`;
    updateActionButtons();
  }
  function acceptSnapshot(remote) {
    if (!remote.values || !Array.isArray(remote.fields)) return false;
    const first = !state.remote;
    const previousFields = JSON.stringify(state.fields.map(f => [f.key,f.options]));
    const previousPresets = JSON.stringify([state.remote?.presets,state.remote?.userPresets]);
    state.fields = makeFields(remote);
    const saved = {...remote.defaults,...(remote.savedValues || remote.values)};
    const wasDirty=state.dirty.size || state.lan !== state.baselineLan;
    if (first) {
      // Browser drafts belong to this tab. A controller may hold another tab's
      // prepared profile; only persisted values initialize a fresh tab.
      state.draft={...saved};state.lan=!!remote.savedLanEnabled;
    } else {
      Object.entries(saved).forEach(([key,val])=>{
        const submission=state.pending || state.submission;
        const protectedKeys=submission?.dirtyKeys || Object.keys(submission?.sent || {});
        if(!state.dirty.has(key) && !protectedKeys.includes(key)) state.draft[key]=val;
      });
      if(state.lan === state.baselineLan && !state.pending && !state.submission) state.lan=!!remote.savedLanEnabled;
    }
    if(first || !wasDirty && !state.pending && !state.submission && !state.posting) {
      state.savedRevision=remote.savedRevision;state.revisionValues={...saved};
    }
    state.baseline = saved; state.baselineLan = !!remote.savedLanEnabled;
    state.remote = remote;
    const pending = state.pending;
    const receipt = pending && ((remote.actionResults || []).find(result => result.id === pending.id) || (remote.lastAction?.id === pending.id ? remote.lastAction : null));
    if (pending && receipt && receipt.status !== 'running') {
      state.suppressToast=(remote.notifications || []).some(notice=>notice.actionId === pending.id || notice.message === receipt.message);
      if (receipt.ok && receipt.status !== 'cancelled') {
        const transforming = ['applyPreset','browse','clearLora','useLora','resetSprite','savePreset'].includes(pending.action);
        if (transforming) Object.entries({...remote.defaults,...(receipt.values || remote.values)}).forEach(([key,val]) => {
          if ((state.edits[key] || 0) <= pending.clock) state.draft[key] = val;
        });
        const defaultsDecision = ['acceptDefaults','declineDefaults'].includes(pending.action);
        if (defaultsDecision) {
          if (pending.action === 'acceptDefaults') {
            if(receipt.savedRevision) {state.savedRevision=receipt.savedRevision;state.revisionValues={...remote.defaults,...receipt.savedValues};}
            Object.entries(pending.sent).forEach(([key,val])=>{if((state.edits[key] || 0) <= pending.clock) state.draft[key]=(receipt.savedValues || saved)[key] ?? val;});
          }
          if ($('#utility-dialog').dataset.kind === 'defaults') $('#utility-dialog').close();
          toast(pending.action === 'acceptDefaults' ? 'Записаны только показанные рекомендации. Остальной черновик не сохранён.' : 'Рекомендации отклонены. config.env не изменён.');
        }
        if (transforming && (state.lanEdit || 0) <= pending.clock) state.lan = !!(receipt.lanEnabled ?? pending.lan);
        // A handled callback is not proof of a disk write or a running generator.
        if (pending.action === 'start' && !receipt.status) state.startSubmission = pending;
        if (['save','start','forceRestart'].includes(pending.action) && (receipt.status === 'succeeded' || /^saved:/i.test(remote.status || ''))) {
          state.savedRevision=receipt.savedRevision || state.savedRevision;state.revisionValues={...remote.defaults,...(receipt.savedValues || saved)};
          Object.entries(pending.sent).forEach(([key,val]) => {
            if ((state.edits[key] || 0) <= pending.clock) state.draft[key] = (receipt.savedValues || saved)[key] ?? val;
          });
          if ((state.lanEdit || 0) <= pending.clock) state.lan = receipt.savedValues ? receipt.savedValues.INFINI_HOST === '0.0.0.0' || !!receipt.savedValues.INFINI_ASSET_PUBLIC_BASE_URL : state.baselineLan;
          toast(pending.action !== 'save' ? (receipt.message || 'Процесс генератора запущен. Проверь соединение, чтобы подтвердить готовность.') : 'Настройки записаны в config.env.');
        } else if (pending.action === 'savePreset') toast('Профиль сохранён отдельно. config.env не изменён.');
        else if (transforming) toast('Изменения подготовлены. Сохрани конфигурацию, чтобы записать их на диск.');
        else if (pending.action !== 'exitStudio' && !defaultsDecision) toast(({start:'Запуск передан генератору. Его состояние — на рабочем столе.',stop:'Безопасная остановка завершена.',health:'Проверка соединения завершена. Состояние — на рабочем столе.',validate:'Проверка путей завершена.',trace:'Журнал обновлён. Источник и статус показаны над записями.',codexLogin:'Результат входа показан в статусе аккаунта.',codexStatus:'Статус аккаунта обновлён.',codexCatalog:'Каталог моделей обновлён.',codexPing:'Проверка аккаунта завершена.',codexLogout:'Выход из аккаунта обработан.',cancelTrace:'Обновление журнала отменено.',openConfig:'Сохранённая конфигурация открыта для просмотра.',openCache:'Открываем папку кеша.',clearTrace:'Очистка журнала завершена.'})[pending.action] || 'Действие обработано.');
      } else {
        const message = receipt.message || 'Действие не выполнено. Изменения сохранены в этой вкладке.';
        if (['acceptDefaults','declineDefaults'].includes(pending.action)) defaultsError(message);
        toast(message,true);
      }
      state.suppressToast=false;state.pending = null; clearTimeout(pending.timer);
      if(receipt.ok && ['applyPreset','savePreset'].includes(pending.action)) state.presetChoice=null;
      if (pending.action === 'exitStudio' && receipt.ok && receipt.status === 'succeeded') {
        state.shutdown=true;clearTimeout(state.pollTimer);$('#utility-dialog').close();
        $('#connection').innerHTML='<span class="status-dot"></span><span>Студия закрыта</span>';
        $('#workspace').innerHTML='<div class="initial-loading"><h1>Студия закрыта</h1><p>Закрыта только студия. Генератор не остановлен этим действием.<br>Эту вкладку можно закрыть.</p></div>';
        updateActionButtons();return true;
      }
      if (receipt.result?.kind === 'document') showDocument(receipt.result);
      if (receipt.result?.kind === 'guide' && receipt.result.url?.startsWith('/guide?')) utility(receipt.result.title || 'Инструкция', `<p class="dialog-copy">Интерактивное руководство открывается в отдельной вкладке.</p><a class="button button-primary" href="${esc(receipt.result.url)}" target="_blank" rel="noopener">Открыть руководство ↗</a>`);
      if (['applyPreset','browse','clearLora','useLora','resetSprite','savePreset'].includes(pending.action)) render();
    }
    if (state.startSubmission && !remote.busy?.includes('server-action')) {
      // The guarded start saves only after its activity/identity check succeeds.
      if (/server\.py запущен|^saved:/i.test(remote.status || '')) {
        Object.entries(state.startSubmission.sent).forEach(([key,val]) => {
          if ((state.edits[key] || 0) <= state.startSubmission.clock) state.draft[key] = saved[key] ?? val;
        });
        if ((state.lanEdit || 0) <= state.startSubmission.clock) state.lan = state.baselineLan;
      }
      state.startSubmission = null;
    }
    for (const notice of remote.notifications || []) {
      if (state.seenNotifications.has(notice.id)) continue;
      state.seenNotifications.add(notice.id);
      toast([notice.title,notice.message].filter(Boolean).join(' · '), notice.level !== 'info');
    }
    recomputeDirty();
    if (state.page === 'configure' && $('#preset-select') && document.activeElement !== $('#preset-select')) $('#preset-select').value = state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    if (first || previousFields !== JSON.stringify(state.fields.map(f => [f.key,f.options])) || previousPresets !== JSON.stringify([remote.presets,remote.userPresets])) render();
    else if (state.page === 'operate') renderOperate();
    else if (state.page === 'diagnostics') updateDiagnostics();
    syncInputs();
    if ($('#account-status')) $('#account-status').textContent = [remote.account?.status, remote.account?.[state.page === 'providers' ? 'catalog':'images']].filter(Boolean).join('\n') || 'Статус аккаунта ещё не запрошен.';
    $('#version').textContent = `Версия ${remote.version || 'α'}`;
    if($('#defaults-summary')) $('#defaults-summary').textContent=defaultsSummary();
    return true;
  }
  async function poll() {
    clearTimeout(state.pollTimer);
    if (state.fetching || state.shutdown) return;
    state.fetching = true;
    try {
      const remote = await api('/api/state');
      if (acceptSnapshot(remote)) {if(!state.shutdown) setConnection(true);}
      else setConnection(false,'Мастерская ещё загружается.');
    } catch (error) {
      setConnection(false,error.name === 'AbortError' ? 'Локальный сервер не ответил вовремя.' : error.message);
      if (!state.remote) {
        $('.initial-loading h1').innerHTML = 'Не удалось подключиться';
        $('.initial-loading p').textContent = 'Проверь, что локальный запускатор студии остаётся открытым.';
        $('.loading-line').hidden = true; $('.initial-loading button').hidden = false;
      }
    } finally {
      state.fetching = false;
      if (!state.shutdown) state.pollTimer = setTimeout(poll,document.hidden ? 4000 : state.pending ? 450 : 1400);
    }
  }
  const editableValues = () => Object.fromEntries(Object.entries(state.draft).filter(([key,val]) => key.startsWith('INFINI_') && typeof val === 'string'));
  async function action(name, extra={}) {
    if (name === 'cancelTrace' && state.pending?.action === 'trace' && state.connected && !state.posting) {
      state.posting=true;updateActionButtons();
      try {await api('/api/action',{action:name,values:{},extra:{}});poll();}
      catch(error) {toast(error.message,true);}
      finally {state.posting=false;updateActionButtons();}
      return;
    }
    if(state.pending?.action === name || state.submission?.action === name) return;
    if (!state.connected || state.pending || state.posting) {toast('Дождись ответа текущего действия или восстанови соединение.',true);return;}
    state.posting = true;
    const defaultsDecision = ['acceptDefaults','declineDefaults'].includes(name);
    const sent = defaultsDecision ? (name === 'acceptDefaults' ? Object.fromEntries((state.defaultsPreview?.changes || []).map(row => [row.key,row.recommended])) : {}) : editableValues();
    const clock = state.editClock, sentLan = state.lan, dirtyKeys=[...state.dirty];
    // Protect the submission from the first byte sent, not only after its id arrives.
    state.submission = {action:name,sent,clock,lan:sentLan,dirtyKeys};
    updateActionButtons();
    try {
      const queued = await api('/api/action',{action:name,values:defaultsDecision ? {} : sent,extra:defaultsDecision ? {revision:extra.revision} : {lanEnabled:sentLan,...(['save','start','forceRestart'].includes(name) ? {savedRevision:state.savedRevision} : {}),...extra}});
      if (!queued.ok || !queued.id) throw new Error('Локальный сервер не подтвердил очередь действия.');
      const pending = {id:queued.id,action:name,sent,clock,lan:sentLan,dirtyKeys,timer:null};
      state.pending = pending;
      state.submission = null;
      pending.timer = setTimeout(() => {
        if (state.pending?.id !== queued.id) return;
        // Keep the pending submission protected after a timeout: an action may still finish.
        toast('Подтверждение задерживается. Изменения защищены; действие может ещё завершиться.',true);
      },name === 'browse' ? 180000 : 30000);
      poll();
    } catch (error) {if (defaultsDecision) defaultsError(error.message); toast(error.message,true);}
    finally {state.submission = null; state.posting = false; updateActionButtons();}
  }
  function updateActionButtons() {
    const locked = !state.connected || state.pending || state.posting || state.shutdown;
    $$('[data-action], [data-browse], [data-submit-action]').forEach(button => {button.disabled = !!locked;});
    const pendingAction=state.pending?.action || state.submission?.action;
    const progressLabels={save:'Сохраняем…',start:'Проверяем и запускаем…',health:'Проверяем соединение…',validate:'Проверяем пути…',trace:'Читаем журнал…',codexStatus:'Проверяем аккаунт…',codexCatalog:'Обновляем модели…',codexLogin:'Ожидаем вход…',codexPing:'Проверяем аккаунт…'};
    $$('[data-action]').forEach(button=>{
      if(button.dataset.action === pendingAction && progressLabels[pendingAction]) {
        if(!button.dataset.idleHtml) button.dataset.idleHtml=button.innerHTML;
        button.innerHTML=`${icon('refresh')}${progressLabels[pendingAction]}`;button.setAttribute('aria-busy','true');
      } else if(button.dataset.idleHtml) {button.innerHTML=button.dataset.idleHtml;delete button.dataset.idleHtml;button.removeAttribute('aria-busy');}
    });
    const serverBusy = state.remote?.busy?.includes('server-action');
    $$('[data-action="start"], [data-action="stop"]').forEach(button => {button.disabled = !!(locked || serverBusy);});
    $$('[data-ui="apply-preset"], [data-ui="save-preset"], [data-ui="stop"], [data-ui="reset-sprite"], [data-ui="clear-lora"], [data-ui="clear-trace"], [data-ui="force-restart"]').forEach(button => {button.disabled = !!locked;});
    $$('[data-ui="stop"], [data-ui="force-restart"]').forEach(button=>{button.disabled=!!(locked || serverBusy);});
    $$('[data-ui="defaults-update"], [data-ui="defaults-refresh"]').forEach(button=>{button.disabled=!!locked;});
    if ($('#utility-dialog').dataset.kind === 'defaults') $$('[data-ui="close-dialog"]', $('#utility-dialog')).forEach(button=>{button.disabled=!!(state.pending || state.posting);});
    $$('[data-action="cancelTrace"]').forEach(button=>{button.disabled=!state.connected || state.posting || state.shutdown || !(state.remote?.busy?.includes('trace') || state.pending?.action === 'trace') || !!(state.pending && state.pending.action !== 'trace');});
    const save = $('[data-action="save"]', $('#save-tray'));
    if (save) save.innerHTML = `${icon((state.pending || state.submission)?.action === 'save' ? 'refresh':'save')}${(state.pending || state.submission)?.action === 'save' ? 'Сохраняем…':'Сохранить'}`;
  }
  function toast(message,error=false) {
    if(state.suppressToast) return;
    state.notifications.push({message,error});
    if(state.notifications.length > 100) state.notifications.shift();
    if($('#notice-count')) $('#notice-count').textContent=String(state.notifications.length);
    if ($('#utility-dialog').open) {
      let feedback=$('#utility-feedback');
      if(!feedback) {feedback=document.createElement('p');feedback.id='utility-feedback';feedback.className='dialog-feedback';feedback.setAttribute('role','status');$('#utility-body').append(feedback);}
      feedback.textContent=message;feedback.classList.toggle('is-error',error);
    }
    const div = document.createElement('div'); div.setAttribute('role',error ? 'alert':'status'); div.className = `toast${error ? ' error':''}`;
    div.innerHTML = `${icon(error ? 'alert':'check')}<span class="toast-copy">${esc(message)}</span><button aria-label="Закрыть уведомление">×</button>`;
    div.querySelector('button').onclick = () => div.remove(); $('#toasts').replaceChildren(div);
    if (!error) setTimeout(() => div.remove(),9000);
  }
  function heading(page) {
    const [,eyebrow,title,subtitle] = routes[page];
    return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${page === 'operate' ? '' : `<div class="heading-note">${state.dirty.size ? 'ЧЕРНОВИК / НЕ СОХРАНЁН':'ЛОКАЛЬНАЯ КОНФИГУРАЦИЯ'}<strong>${page === 'configure' ? state.fields.length : state.fields.filter(field => field.route === page).length} параметров</strong></div>`}</div>`;
  }
  function providerSummary() {
    const provider = value('INFINI_LLM_PROVIDER','local');
    if (value('INFINI_USE_LLM') === '0') return {name:'Авторство модели выключено',detail:'Технический режим · не обычная генерация'};
    const modelKey = {local:'INFINI_LMSTUDIO_MODEL',openrouter:'INFINI_OPENROUTER_MODEL',openai_compat:'INFINI_OPENAI_COMPAT_MODEL',openai_codex:'INFINI_CODEX_LLM_MODEL'}[provider];
    const model = value(modelKey);
    return {name:optionNames.INFINI_LLM_PROVIDER[provider] || provider,detail:!model || model === 'auto' ? 'Модель выбирает источник':model};
  }
  function imageSummary() {
    const backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    const modelKey = {sdcpp:'INFINI_SDCPP_MODEL',image_api:'INFINI_IMAGE_API_MODEL',openai_codex:'INFINI_CODEX_IMAGE_MODEL'}[backend];
    const model = value(modelKey).split(/[\\/]/).pop();
    if (backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1') return {name:'sd.cpp · внешний сервер',detail:value('INFINI_SDCPP_SERVER_URL') || 'Укажи адрес сервера изображений'};
    return {name:optionNames.INFINI_IMAGE_BACKEND[backend] || backend,detail:backend === 'off' ? 'Создаётся только механика':model || 'Модель ещё не указана'};
  }
  function nextStep() {
    const provider = value('INFINI_LLM_PROVIDER','local'), backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    if (provider === 'openrouter' && !value('INFINI_OPENROUTER_API_KEY')) return {n:'01',title:'Укажи ключ OpenRouter',description:'OpenRouter выбран, но ключ ещё не указан. Подключи модель, которая будет придумывать механику.',route:'providers',link:'Подключить OpenRouter'};
    if (provider === 'openai_compat' && !value('INFINI_OPENAI_COMPAT_BASE_URL')) return {n:'01',title:'Укажи адрес модели',description:'Совместимому API нужен адрес сервера. Ключ и имя модели настраиваются там же.',route:'providers',link:'Настроить источник'};
    if (backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' && (!value('INFINI_SDCPP_MODEL') || !value('INFINI_SDCPP_SERVER_EXE'))) return {n:'02',title:'Укажи файлы sd.cpp',description:'Для локальных изображений нужны программа sd.cpp и файл модели на этом компьютере.',route:'models',link:'Выбрать модель'};
    if (state.dirty.size || state.lan !== state.baselineLan) return {n:'→',title:'Сохрани настройки',description:'Есть несохранённые настройки. Запиши конфигурацию перед запуском.',route:'configure',link:'Открыть конфигурацию'};
    if (/Сервер отвечает|Идёт генерация/.test(state.remote?.home?.state || '')) return {n:'→',title:'Крафт в Terraria',description:'Открой игру с модом InfiniCrafterLocal. Новые предметы создаются в игре, не в этой студии.',route:'help',link:'Как начать крафт'};
    return {n:'→',title:'Проверка соединения',description:'Проверь соединение или запусти генератор. Выбранные настройки ещё не подтверждают готовность моделей.',route:'diagnostics',link:'Проверить настройку'};
  }
  function homeActivity() {
    const raw = state.remote.activity || '';
    if (/остановлен|не проверено|подтверждено/.test(state.remote.home?.state || '')) return `<div class="activity-empty">${icon('pulse')}<div><h3>Пока без актуального снимка</h3><p>Проверь соединение после запуска. Последний ответ сервера не означает, что он работает сейчас.</p></div></div>`;
    const snapshot = raw.match(/active=(\d+), waiting=(\d+), accepting=(True|False)/);
    if (snapshot) {
      const active = Number(snapshot[1]), waiting = Number(snapshot[2]);
      return `<div class="activity-empty">${icon('pulse')}<div><h3>${active ? `Создаётся предметов: ${active}` : 'Активных запросов нет'}</h3><p>${waiting ? `В очереди: ${waiting}. ` : ''}${snapshot[3] === 'True' ? 'Генератор принимает новые запросы.':'Приём новых запросов закрыт.'}<br>Последняя проверка соединения; не поток в реальном времени.</p></div></div>`;
    }
    return `<div class="activity-empty">${icon('pulse')}<div><h3>Пока без подтверждённых запросов</h3><p>Проверь соединение, чтобы получить состояние генератора. Здесь отображается последний ответ сервера.</p></div></div>`;
  }
  function renderOperate() {
    if (!state.remote || state.page !== 'operate') return;
    const home = state.remote.home || {}, provider = providerSummary(), image = imageSummary(), next = nextStep();
    const busy = state.remote.busy?.includes('server-action'), running = /Сервер отвечает|Идёт генерация/.test(home.state || '');
    const title = busy ? 'Проверяем состояние…':home.state || 'Состояние не проверено';
    const tag = busy ? 'ПРОВЕРКА':running ? 'СЕРВЕР ОТВЕЧАЕТ':/внимание|подтверждено/.test(title) ? 'НУЖНА ПРОВЕРКА':'ОЖИДАНИЕ';
    const detail = title === 'Сервер отвечает' ? 'Генератор этой копии отвечает. Можно продолжить крафт в Terraria.' : title === 'Состояние ещё не проверено' ? 'Запусти генератор или проверь соединение.' : home.detail || 'Настрой источники и проверь соединение перед созданием предметов.';
    const config = state.dirty.size ? 'Есть несохранённые изменения. Сводка показывает черновик.' : /restart|mismatch|differs/i.test(state.remote.appliedConfig || '') ? 'Конфигурация изменена — нужен безопасный перезапуск.' : /matches/i.test(state.remote.appliedConfig || '') ? 'Часть параметров совпадает с сервером на последней проверке. Ключи и дополнительные модели не проверены.' : 'Конфигурация сервера ещё не подтверждена. Проверка соединения не запускает генерацию.';
    const signature = JSON.stringify([home,provider,image,next,config,busy,running,state.dirty.size,state.remote.activity,value('INFINI_HOST'),value('INFINI_PORT')]);
    if (state.operateSignature === signature && $('.station')) {updateActionButtons();return;}
    state.operateSignature = signature;
    const focused = document.activeElement;
    const focusIdentity = focused?.closest('#workspace') ? ['data-action','data-ui','href'].map(name => [name,focused.getAttribute(name)]).find(([,val]) => val) : null;
    $('#workspace').innerHTML = `${heading('operate')}
      <div class="operate-grid"><section class="station" aria-labelledby="generator-title"><div class="station-top"><span class="serial">Состояние генератора</span><span class="state-tag"><span class="status-dot"></span>${tag}</span></div><h2 id="generator-title">${esc(title)}</h2><p class="station-detail">${esc(detail)}</p><div class="endpoint">${icon('network')}<span>Сохранено: ${esc(state.remote.savedValues?.INFINI_HOST || '127.0.0.1')}:${esc(state.remote.savedValues?.INFINI_PORT || '5055')}</span></div><div class="station-buttons"><button class="button button-primary" data-action="start">${icon('play')}${running ? 'Перезапустить безопасно':'Запустить генератор'}</button><button class="button" data-action="health" aria-label="Проверить сохранённый или запущенный генератор">${icon('refresh')}Проверить</button><button class="button button-small" data-ui="stop" title="Безопасно остановить генератор">${icon('stop')}Стоп</button></div><p class="station-caption">Запуск сохраняет настройки. Проверка использует сохранённый адрес или сервер, запущенный этой студией. Новые адреса сначала сохрани.</p></section>
      <section class="pipeline" aria-labelledby="pipeline-title"><div class="section-heading"><h2 id="pipeline-title">Выбранные источники</h2><span class="meta">${state.dirty.size ? 'ЧЕРНОВИК':'КОНФИГУРАЦИЯ'}</span></div><ol class="pipeline-list">${[
        ['01','Идея и механика',provider.name,provider.detail,'providers'],
        ['02','Изображение',image.name,image.detail,'images'],
        ['03','Готовый спрайт',value('INFINI_IMAGE_BACKEND') === 'off' ? 'Без обработки':value('INFINI_BG_COLOR') === 'transparent' ? 'Прозрачный фон':'Чистый фон',value('INFINI_IMAGE_BACKEND') === 'off' ? 'Изображения выключены':`${value('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()} / ${value('INFINI_PIXEL_POSTERIZE') === '1' ? `${value('INFINI_MAX_COLORS')} цвета`:'свободная палитра'}`,'sprites']
      ].map(([number,title,name,detail,route]) => `<li><a class="pipeline-step" href="#${route}"><span class="step-number">${number}</span><div><div class="step-title">${title}</div><div class="step-name">${esc(name)}</div><div class="step-desc">${esc(detail)}</div></div><span class="step-arrow">${icon('arrow')}</span></a></li>`).join('')}</ol><p class="pipeline-note">Настройки сборки — не подтверждение готовности моделей.</p></section></div>
      <div class="operate-lower"><section><div class="activity-header"><h2>Последние события</h2><a class="text-button" href="#diagnostics">Открыть журнал ${icon('arrow')}</a></div><div class="activity-sheet">${homeActivity()}</div></section><section class="next-step"><div><span class="eyebrow">СЛЕДУЮЩИЙ ШАГ</span><h2>${esc(next.title)}</h2><p>${esc(next.description)}</p></div>${next.route === 'help' ? `<a href="#operate" data-ui="help">${next.link}${icon('arrow')}</a>` : `<a href="#${next.route}">${next.link}${icon('arrow')}</a>`}</section></div>
      <div class="config-strip">${icon('sliders')}<p>${esc(config)}</p></div>`;
    updateActionButtons();
    if (focusIdentity) $$('[data-action],[data-ui],a', $('#workspace')).find(element => element.getAttribute(focusIdentity[0]) === focusIdentity[1])?.focus({preventScroll:true});
  }
  function browseType(field) {
    if (field.key === 'INFINI_SDCPP_LORA_FILE') return 'lora';
    if (modelKeys.has(field.key)) return 'model';
    if (/_(DIR|ROOT)$/.test(field.key)) return 'folder';
    if (/(SERVER_EXE|LOG_FILE)$/.test(field.key)) return 'file';
    return '';
  }
  function derivedField(key) {
    if(key === 'INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK' && value('INFINI_VISUAL_STRICT_AI_AUTHORSHIP','1') === '1') return {value:'0 · Выключено',note:'Строгое авторство модели принудительно выключает процедурную подмену.'};
    if(key === 'INFINI_SDCPP_LORA_DIR') {
      const file=value('INFINI_SDCPP_LORA_FILE').trim(), slash=Math.max(file.lastIndexOf('/'),file.lastIndexOf('\\'));
      const dir=!file ? 'Не задано' : slash < 0 ? '.' : slash === 0 ? file[0] : slash === 2 && file[1] === ':' ? file.slice(0,3) : file.slice(0,slash);
      return {value:dir,note:'Вычисляется из выбранного файла LoRA при сохранении. Без файла папка очищается.'};
    }
    if(key === 'INFINI_HOST' && state.lan && value('INFINI_MP_ASSET_TRANSPORT') === 'http') return {value:'0.0.0.0',note:'LAN с HTTP требует сетевой интерфейс. Изменить режим можно переключателем LAN выше.'};
    return null;
  }
  function fieldHTML(field,forceDetails=false) {
    const key = field.key, id = `field-${key}`, val = value(key), options = field.options || [], inactive = inactiveReason(field);
    const isBool = options.length === 2 && options.includes('1') && options.includes('0') && ['0','1'].includes(val);
    const derived=derivedField(key), browse = derived ? '' : browseType(field), help = forceDetails || state.helpFields.has(key), title = label(field);
    let control;
    if (derived) control=`<output id="${id}" data-derived="${key}" tabindex="0" aria-describedby="help-${key}">${esc(derived.value)}</output><span class="field-note">${esc(derived.note)}</span>`;
    else if (field.secret) control = `<input id="${id}" data-field="${key}" type="password" value="${esc(val)}" autocomplete="off" spellcheck="false" data-secret="true" aria-describedby="help-${key}"><button class="reveal" data-reveal="${key}" type="button" aria-label="Показать ключ" aria-pressed="false">${icon('eye')}</button>`;
    else if (key === 'INFINI_SDCPP_SERVER_AUTOSTART') control = `<select id="${id}" data-field="${key}" aria-describedby="help-${key}"><option value="0" ${val === '0' ? 'selected':''}>Внешний · уже запущен</option><option value="1" ${val === '1' ? 'selected':''}>Управляемый · запускать здесь</option>${!['0','1'].includes(val) ? `<option selected value="${esc(val)}">${esc(val)}</option>`:''}</select>`;
    else if (isBool) control = `<label class="toggle-control"><input id="${id}" type="checkbox" data-field="${esc(key)}" ${val === '1' ? 'checked':''} aria-describedby="help-${key}"><span class="toggle-track"></span><span class="toggle-label">${val === '1' ? 'Включено':'Выключено'}</span></label>`;
    else if (field.multiline || /COMMAND_TEMPLATE|EXTRA_ARGS/.test(key)) control = `<textarea id="${id}" data-field="${key}" spellcheck="false" aria-describedby="help-${key}">${esc(val)}</textarea>`;
    else if (options.length && !/_MODEL$/.test(key)) {
      const available = [...new Set([...(options.includes(val) ? []:[val]),...options])];
      control = `<select id="${id}" data-field="${key}" aria-describedby="help-${key}">${available.map(option => `<option value="${esc(option)}" ${option === val ? 'selected':''}>${esc(optionNames[key]?.[option] || option || 'Не задано')}</option>`).join('')}</select>`;
    } else {
      control = `<input id="${id}" data-field="${key}" type="${field.secret ? 'password':'text'}" value="${esc(val)}" autocomplete="off" spellcheck="false" ${field.secret ? 'data-secret="true"':''} ${options.length ? `list="options-${key}"`:''} aria-describedby="help-${key}">${options.length ? `<datalist id="options-${key}">${options.map(option => `<option value="${esc(option)}"></option>`).join('')}</datalist>`:''}`;
      if (field.secret) control += `<button class="reveal" data-reveal="${key}" type="button" aria-label="Показать ключ" aria-pressed="false">${icon('eye')}</button>`;
      if (browse && !field.synthetic) control += `<button class="browse" data-browse="${key}" data-browse-type="${browse}" type="button" title="Выбрать на этом компьютере" aria-label="Выбрать файл: ${esc(title)}">${icon('folder')}</button>`;
    }
    return `<div class="field-row${state.dirty.has(key) ? ' is-dirty':''}" data-field-row="${key}"><div class="field-copy"><div class="field-label-line"><label for="${id}">${esc(title)}</label><button class="field-help-toggle" data-help-field="${key}" type="button" aria-label="Подробности: ${esc(title)}" aria-expanded="${help}">?</button></div><div class="field-key${help ? '':' hidden-key'}">${key}</div><p class="field-help" id="help-${key}">${esc(help ? field.help || shortHelp[key] || 'Параметр локального генератора. Значение сохраняется без преобразования.' : shortHelp[key] || '')}</p></div><div class="field-control${field.secret || browse ? ' has-extra':''}">${control}${inactive && !derived ? `<span class="field-note">${esc(inactive)} · значение сохранится</span>`:''}</div></div>`;
  }
  function disclosure(id,title,fields,reason='',force=false) {
    if (!fields.length) return '';
    const open = state.openDetails.has(id) || force;
    return `<details class="advanced" data-details="${id}" ${open ? 'open':''}><summary>${esc(title)}<span class="meta">${fields.length}</span></summary>${reason ? `<p class="details-note">${esc(reason)}</p>`:''}<div class="section-fields">${fields.map(field => fieldHTML(field,force)).join('')}</div></details>`;
  }
  function fieldGroups(fields,force=false) {
    if (!fields.length) return '<div class="empty-search">В этом разделе ничего не найдено. Попробуй другое слово.</div>';
    if (force) return `<div class="section-fields">${fields.map(field => fieldHTML(field,true)).join('')}</div>`;
    const active = fields.filter(field => !inactiveReason(field)), inactive = fields.filter(field => inactiveReason(field));
    const loRAKeys = new Set(['INFINI_SDCPP_LORA_DIR','INFINI_SDCPP_LORA_FILE','INFINI_SDCPP_LORA_WEIGHT','INFINI_SDCPP_LORA_PROMPT_TAGS']);
    const primary = active.filter(field => !loRAKeys.has(field.key) && (basicKeys.has(field.key)));
    const ordering = state.page === 'images' ? ['INFINI_IMAGE_BACKEND','INFINI_SDCPP_SERVER_AUTOSTART','INFINI_SDCPP_SERVER_URL'] : [];
    primary.sort((a,b) => (ordering.includes(a.key) ? ordering.indexOf(a.key) : 100) - (ordering.includes(b.key) ? ordering.indexOf(b.key) : 100));
    const advanced = active.filter(field => !primary.includes(field));
    const pools = [2,3,4].map(number => advanced.filter(field => field.key.startsWith(`INFINI_LLM_POOL_${number}_`)));
    const poolKeys = pools.flat().map(field => field.key);
    return `<div class="section-fields">${primary.map(field => fieldHTML(field)).join('')}</div>${pools.map((group,index) => disclosure(`pool-${index+2}` ,`Дополнительная линия ${index+2}`,group,'Каждая линия имеет собственный источник, адрес и модель.')).join('')}${disclosure(`${state.page}-lora`,'Художественный адаптер · LoRA',advanced.filter(field => loRAKeys.has(field.key)),'Необязательный адаптер. Файлы и настройки сохраняются при отключении.')}${disclosure(`${state.page}-advanced`,'Тонкая настройка',advanced.filter(field => !poolKeys.includes(field.key) && !loRAKeys.has(field.key)),'Параметры для ручной настройки. Все текущие значения сохраняются.')}${disclosure(`${state.page}-inactive`,'Другие источники и неактивные параметры',inactive,'Не используются выбранным источником. Доступны для редактирования; переключение не стирает значения.')}`;
  }
  function aside() {
    return `<aside class="settings-aside"><h2>Сохранение</h2><p>Изменения остаются в этой вкладке до сохранения. Для работающего генератора нужен безопасный перезапуск.</p><button class="button button-primary" data-action="save">${icon('save')}Сохранить настройки</button><button class="button" data-action="validate">${icon('check')}Проверить пути</button><a class="button" href="#operate">К рабочему столу ${icon('arrow')}</a><div class="aside-meta"><strong>Локальный файл</strong>${esc(state.remote.configPath || 'config.env')}<br><button class="text-button" data-action="openConfig">Открыть файл ${icon('arrow')}</button></div></aside>`;
  }
  function defaultsSummary() {
    const offer=state.remote?.defaultsUpdate,count=offer?.changes?.length || 0;
    if(!count) return 'Новых рекомендаций нет. Текущие настройки можно менять вручную.';
    if(offer.dismissed) return `Рекомендации ${offer.version || ''} отложены. Можно вернуться к ним в любое время.`;
    const unit=count % 10 === 1 && count % 100 !== 11 ? 'параметр' : [2,3,4].includes(count % 10) && ![12,13,14].includes(count % 100) ? 'параметра':'параметров';
    return `Рекомендации ${offer.version || ''}: ${count} ${unit} для сравнения. Это необязательные значения; твои собственные настройки допустимы.`;
  }
  function renderConfigure() {
    const counts = route => state.fields.filter(field => field.route === route).length;
    const selected = state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    const presetEntries = [...Object.keys(state.remote.presets || {}),...Object.keys(state.remote.userPresets || {}).map(name => `Мой: ${name}`)];
    const full = state.fields;
    $('#workspace').innerHTML = `${heading('configure')}<div class="settings-layout"><div class="settings-main"><section class="preset-sheet"><h2>Рекомендованные настройки</h2><p id="defaults-summary">${esc(defaultsSummary())}</p><button class="button" data-ui="defaults-update">Проверить рекомендации</button></section><section class="preset-sheet"><h2>Профиль настроек</h2><p>Начни с готового сочетания моделей или сохрани собственное. Профиль меняет настройки, но не подменяет текущие ключи.</p><div class="preset-selector"><select id="preset-select" aria-label="Профиль настроек"><option value="">Выбери профиль…</option>${presetEntries.map(name => `<option value="${esc(name)}" ${name === selected ? 'selected':''}>${esc(name)}</option>`).join('')}</select><button class="button" data-ui="apply-preset">Применить ${icon('arrow')}</button></div><button class="text-button" data-ui="save-preset" style="margin-top:12px">Сохранить текущие настройки как профиль ${icon('save')}</button></section><div class="section-heading"><h2>Разделы настроек</h2><span class="meta">${state.fields.length} ПАРАМЕТРОВ</span></div><div class="configure-index">${[
      ['01','providers','Автор и механика','Источник текста, направление и вариативность.'],['02','images','Источник изображения','Локальный движок, подписка или API.'],['03','sprites','Спрайт и цвет','Прозрачность, края, холст и палитра.'],['04','models','Модели и LoRA','Файлы моделей и художественные адаптеры.'],['05','multiplayer','Соединение с игрой','Адрес генератора и совместный крафт.'],['06','diagnostics','Диагностика','Журнал, события и технические параметры.']
    ].map(([n,route,title,description]) => `<a class="index-row" href="#${route}"><span class="index-number">${n}</span><div><h3>${title}</h3><p>${description}</p></div><span class="index-tail"><span>${counts(route)}</span>${icon('arrow')}</span></a>`).join('')}</div>${disclosure('all-settings','Все параметры одним списком',full,'Полный доступ ко всем настройкам, включая параметры других источников и служебные поля. Значения не скрываются при смене профиля.')}<p class="settings-path">${esc(state.remote.configPath)}</p></div>${aside()}</div>`;
  }
  function pageExtras(page) {
    if (page === 'providers' && value('INFINI_LLM_PROVIDER') === 'openai_codex' || page === 'images' && value('INFINI_IMAGE_BACKEND') === 'openai_codex') return `<div class="notice">Codex использует вход по подписке, не API-ключ. Модель текста и модель изображения настраиваются независимо.</div><div class="page-actions"><button class="button" data-action="codexLogin">Войти в Codex ${icon('arrow')}</button><button class="button" data-action="codexStatus">Статус аккаунта</button><button class="button" data-action="codexLogout">Выйти</button>${page === 'providers' ? '<button class="button" data-action="codexCatalog">Обновить модели</button>' : '<button class="button" data-action="codexPing">Проверить аккаунт</button>'}</div><div class="account-status-panel"><p><span id="account-status">${esc([state.remote.account?.status,state.remote.account?.[page === 'providers' ? 'catalog':'images']].filter(Boolean).join('\n') || 'Статус аккаунта ещё не запрошен.')}</span><br>Обновление каталога не запускает крафт. У изображений нет отдельного API списка моделей.</p></div>`;
    if (page === 'images' && value('INFINI_IMAGE_BACKEND') === 'sdcpp') return `<div class="notice">${value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? 'Управляемый запуск: генератор поднимет sd.cpp. Программа и веса — в разделе «Модели и LoRA».' : 'Внешний запуск: sd.cpp уже работает отдельно. Здесь достаточно его URL; файлы моделей выбираются на стороне sd.cpp.'}<br><a class="text-button" href="#models">${value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? 'Открыть модели':'LoRA и дополнительные материалы'} ${icon('arrow')}</a></div>`;
    if (page === 'sprites') return `${value('INFINI_IMAGE_BACKEND') === 'off' ? '<div class="notice">Изображения сейчас выключены. Параметры обработки доступны ниже и сохранятся до включения изображений.</div>':''}<div class="page-actions"><button class="button" data-ui="reset-sprite">${icon('refresh')}Вернуть базовый BOX</button><button class="button" data-action="openCache" title="Открыть папку кеша на компьютере генератора">${icon('folder')}Кеш в файловом менеджере</button></div>`;
    if (page === 'models') return `${value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? '<div class="notice">Локальные модели нужны только для sd.cpp. Для текущего источника настрой модель в разделе «Изображения».</div>' : value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1' ? '<div class="notice">Внешний sd.cpp выбирает основные модели при собственном запуске. Для запуска из студии включи управляемый режим в разделе «Изображения».</div>' : ''}<a class="text-button" href="#images">К источнику изображений ${icon('arrow')}</a><div class="page-actions"><button class="button" data-action="useLora">Применить выбранную LoRA</button><button class="button" data-ui="clear-lora">Отключить LoRA</button><button class="button" data-action="validate">${icon('check')}Проверить пути</button></div>`;
    if (page === 'multiplayer') return `<div class="notice">Эта студия работает только на текущем компьютере. Доступ друзей настраивается для генератора, а не для веб-интерфейса.</div><div class="field-row"><div class="field-copy"><label for="lan-enabled">Режим LAN / Radmin</label><p class="field-help">Сетевая надстройка над текущим профилем. Адреса ниже не меняют модель.</p></div><div class="field-control"><label class="toggle-control"><input id="lan-enabled" type="checkbox" data-lan ${state.lan ? 'checked':''}><span class="toggle-track"></span><span class="toggle-label">${state.lan ? 'Включено':'Выключено'}</span></label></div></div>`;
    return '';
  }
  function renderSettings(page) {
    let fields = state.fields.filter(field => field.route === page);
    if (state.filter) fields = fields.filter(field => matches(field,state.filter));
    $('#workspace').innerHTML = `${heading(page)}<div class="settings-layout"><div class="settings-main">${pageExtras(page)}${page === 'diagnostics' ? diagnosticsMarkup():''}<div class="settings-toolbar"><label class="inline-search">${icon('search')}<input id="page-search" placeholder="Найти в этом разделе…" value="${esc(state.filter)}" autocomplete="off" aria-label="Поиск в разделе"></label><span class="field-counter">${fields.length} параметров</span></div><section class="field-section">${page === 'diagnostics' && !state.filter ? disclosure('diagnostic-settings','Параметры журнала и отладки',fields,'Настройки записи; сам журнал показан выше.') : fieldGroups(fields,!!state.filter)}</section></div>${aside()}</div>`;
    if (page === 'diagnostics') updateDiagnostics();
  }
  function diagnosticsMarkup() {
    const tabs = {summary:'Сводка',events:'События',prompts:'Промпты',pipeline:'Этапы',sdcpp:'sd.cpp',failure:'Ошибка'};
    return `<details class="advanced"><summary>Аварийное управление</summary><p class="details-note">Обычный запуск защищает активный крафт. Здесь доступен принудительный перезапуск только после подтверждения.</p><div class="page-actions" style="padding:0 16px"><button class="button button-danger" data-ui="force-restart">Принудительный перезапуск…</button></div></details><section><div class="section-heading"><h2>Локальный журнал</h2></div><p class="dialog-copy">Соединение, журнал, очистка и папка кеша используют сохранённую конфигурацию или сервер, запущенный этой студией. Для новых адресов сначала сохрани настройки.</p><div class="page-actions"><button class="button" data-action="health">${icon('pulse')}Соединение</button><button class="button" data-action="trace">${icon('refresh')}Обновить журнал</button><button class="button" data-action="openCache" title="Открыть папку кеша на компьютере генератора">${icon('folder')}Открыть папку кеша</button><button class="button" data-action="cancelTrace">Отменить обновление</button><button class="button button-danger" data-ui="clear-trace">Очистить…</button></div><div class="diagnostic-status"><span class="eyebrow">ИСХОДНЫЙ СТАТУС ГЕНЕРАТОРА</span><p id="diagnostic-status"></p></div><p id="trace-status" class="trace-status" role="status"></p><div class="trace-tabs" role="tablist" aria-label="Разделы журнала">${Object.entries(tabs).map(([key,name]) => `<button id="tab-${key}" role="tab" aria-controls="trace-view" aria-selected="${key === state.traceTab}" tabindex="${key === state.traceTab ? '0':'-1'}" class="${key === state.traceTab ? 'active':''}" data-trace-tab="${key}">${name}</button>`).join('')}</div><div id="trace-view" class="trace-view" role="tabpanel" aria-labelledby="tab-${state.traceTab}" tabindex="0"></div></section>`;
  }
  function updateDiagnostics() {
    if (!$('#diagnostic-status')) return;
    $('#diagnostic-status').textContent = [state.remote.status,state.remote.appliedConfig,state.remote.activity].filter(Boolean).join('\n\n');
    $('#trace-status').textContent = state.remote.traceStatus || 'Журнал ещё не запрошен.';
    const raw = state.remote.trace?.[state.traceTab] ?? (state.traceTab === 'failure' ? state.remote.trace?.last_failure : null);
    const view = $('#trace-view');
    if (!raw || typeof raw === 'string' && !raw.trim()) {view.classList.add('is-empty');view.innerHTML = '<h3>Пока нет записей.</h3><span>Обнови журнал. Записи появятся после реального крафта.</span>';}
    else {view.classList.remove('is-empty');view.textContent = typeof raw === 'string' ? raw : JSON.stringify(raw,null,2);}
  }
  function render() {
    if (!state.remote || state.shutdown) return;
    state.openDetails = new Set([...state.openDetails,...$$('details[open]').map(detail => detail.dataset.details)]);
    if (state.page === 'operate') renderOperate();
    else if (state.page === 'configure') renderConfigure();
    else renderSettings(state.page);
    $$('details[data-details]').forEach(detail => detail.addEventListener('toggle',() => detail.open ? state.openDetails.add(detail.dataset.details):state.openDetails.delete(detail.dataset.details)));
    updateActionButtons();
  }
  function syncInputs() {
    $$('[data-field]').forEach(input => {
      if (document.activeElement === input) return;
      const val = value(input.dataset.field);
      if (input.type === 'checkbox') input.checked = val === '1'; else if (input.value !== val) input.value = val;
      input.closest('.field-row')?.classList.toggle('is-dirty',state.dirty.has(input.dataset.field));
      if (input.type === 'checkbox' && input.parentElement.querySelector('.toggle-label')) input.parentElement.querySelector('.toggle-label').textContent = input.checked ? 'Включено':'Выключено';
    });
  }
  function setMenu(open, restoreFocus=true) {
    const rail = $('.rail'), menu = $('.mobile-menu');
    open = !!open && innerWidth <= 720;
    rail.classList.toggle('is-open',open);
    menu.setAttribute('aria-expanded',String(open));
    $('#navigation-backdrop').hidden = !open;
    $('.main-shell').inert = open;
    $('#save-tray').inert = open;
    document.body.classList.toggle('menu-open',open);
    if (open) {
      rail.setAttribute('role','dialog'); rail.setAttribute('aria-modal','true');
      $('.nav-link.active',rail)?.focus({preventScroll:true});
    } else {
      rail.removeAttribute('role'); rail.removeAttribute('aria-modal');
      if (restoreFocus && rail.contains(document.activeElement)) menu.focus({preventScroll:true});
    }
  }
  function navigate() {
    const target = location.hash.slice(1).split('?')[0];
    state.page = routes[target] ? target : 'operate'; state.filter = '';
    $$('.nav-link').forEach(link => {link.classList.toggle('active',link.dataset.route === state.page); if (link.dataset.route === state.page) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');});
    $('#crumb').textContent = routes[state.page][0];document.title = `${routes[state.page][0]} — Infinicraft`;
    const fromMenu = $('.rail').classList.contains('is-open');
    setMenu(false,false);
    render();if (fromMenu) $('#workspace').focus({preventScroll:true});
    if(state.focusKey) {const key=state.focusKey;state.focusKey=null;focusFieldRow(key);} else window.scrollTo({top:0,behavior:'instant'});
  }
  function matches(field,query) {
    const haystack = `${label(field)} ${field.key} ${field.help || ''} ${routes[field.route][0]}`.toLocaleLowerCase();
    return query.toLocaleLowerCase().trim().split(/\s+/).every(part => haystack.includes(part));
  }
  function showSearch() {setMenu(false);$('#search-dialog').showModal();$('#global-search').value='';state.searchIndex=0;renderSearch();$('#global-search').focus();}
  function renderSearch() {
    const query = $('#global-search').value;
    state.searchMatches = state.fields.filter(field => matches(field,query));
    state.searchIndex = Math.min(state.searchIndex,Math.max(0,state.searchMatches.length-1));
    $('#search-results').innerHTML = state.searchMatches.length ? state.searchMatches.map((field,index) => `<button class="search-result ${index === state.searchIndex ? 'selected':''}" data-search-key="${field.key}" id="search-hit-${index}"><span><strong>${esc(label(field))}</strong><small>${field.key}</small></span><span>${esc(routes[field.route][0])}</span></button>`).join('') : '<div class="empty-search">Ничего не найдено. Ищи по названию или ключу INFINI_.</div>';
  }
  function focusField(key) {
    const field = state.fields.find(field => field.key === key);if (!field) return;
    $('#search-dialog').close();state.filter = '';state.helpFields.add(key);
    state.focusKey=key;
    // hashchange owns the single route render; a second render would erase focus.
    if(location.hash.slice(1) !== field.route) location.hash=field.route;else navigate();
  }
  function focusFieldRow(key) {
    requestAnimationFrame(() => {
      const row = $(`[data-field-row="${key}"]`);
      if (!row) return;
      let parent = row.parentElement;
      while(parent) {if(parent.tagName === 'DETAILS') {parent.open = true;state.openDetails.add(parent.dataset.details);}parent=parent.parentElement;}
      row.classList.add('field-highlight');
      row.querySelector('[data-field],[data-derived]')?.focus({preventScroll:true});
      const top = row.getBoundingClientRect().top + window.scrollY - 94;
      window.scrollTo({top:Math.max(0,top),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant':'smooth'});
    });
  }
  function utility(title,body) {setMenu(false);$('#utility-dialog').dataset.kind='';$('#utility-title').textContent=title;$('#utility-body').innerHTML=body;$('#utility-dialog').showModal();updateActionButtons();}
  function showSaveConflict() {
    const disk={...state.remote.defaults,...state.remote.savedValues};
    const changed=Object.keys(disk).filter(key=>disk[key] !== state.revisionValues?.[key]);
    const display=(key,val)=>isCredentialKey(key) ? (val ? '••••••••':'Не задано') : val || 'Не задано';
    utility('Конфигурация изменилась на диске', `<p class="dialog-copy">Другой процесс или вкладка сохранили настройки после начала твоего черновика. Проверь изменения ниже. Твои правки останутся в этой вкладке; сохранение потребует отдельного нажатия.</p><div class="confirm-list">${changed.map(key=>`<div><span>${esc(names[key] || key)}<small>На диске: ${esc(display(key,disk[key]))}</small></span><span>Черновик: ${esc(display(key,value(key)))}</span></div>`).join('')}</div><div class="dialog-actions"><button class="button" data-ui="close-dialog">Вернуться</button><button class="button button-primary" id="reconcile-draft">Продолжить с моими правками</button></div>`);
    const revision=state.remote.savedRevision;
    $('#reconcile-draft').onclick=()=>{const edits=Object.fromEntries([...state.dirty].map(key=>[key,state.draft[key]]));state.draft={...disk,...edits};state.baseline={...disk};state.savedRevision=revision;state.revisionValues={...disk};$('#utility-dialog').close();recomputeDirty();render();toast('Черновик сохранён в этой вкладке. Проверь его и нажми «Сохранить», когда будешь готов.');};
  }
  function showDocument(result) {
    utility(result.title || 'Локальный документ', `<p class="dialog-copy">${esc(result.path || '')}</p><pre class="document-view">${esc(result.content || '')}</pre><div class="dialog-actions"><button class="button" data-ui="close-dialog">Закрыть</button></div>`);
  }
  async function showFilePicker(key,kind='file') {
    state.picker={key,kind,request:0};
    utility('Выбрать на компьютере генератора', `<p class="dialog-copy">${esc(names[key] || key)}. Выбор изменит только черновик; файлы не загружаются и не изменяются.</p><form id="file-location"><label class="dialog-field-label" for="file-path">Папка или полный путь</label><div class="file-location"><input class="dialog-input" id="file-path" autocomplete="off" spellcheck="false"><button class="button" type="submit">Открыть</button></div></form><p id="file-error" role="alert" class="defaults-error" hidden></p><div id="file-entries" class="file-entries" aria-live="polite"></div><p id="file-selection" class="dialog-copy" aria-live="polite"></p><div class="dialog-actions"><button class="button" data-ui="close-dialog">Отмена</button><button class="button button-primary" id="file-select" disabled>${kind === 'folder' ? 'Выбрать папку':'Выбрать файл'}</button></div>`);
    $('#utility-dialog').dataset.kind='files';
    $('#file-location').onsubmit=event=>{event.preventDefault();loadFiles($('#file-path').value);};
    $('#file-select').onclick=()=>selectFile(state.picker?.selection);
    await loadFiles(value(key));
  }
  function selectFile(path) {
    if (!path || !state.picker) return;
    const key=state.picker.key;
    state.draft[key]=path;state.edits[key]=++state.editClock;
    state.picker=null;$('#utility-dialog').close();recomputeDirty();render();
    toast('Путь выбран. Сохрани настройки, чтобы записать его в config.env.');
  }
  async function loadFiles(path) {
    const picker=state.picker;if (!picker) return;
    const request=++picker.request;
    $('#file-select').disabled=true;$('#file-error').hidden=true;
    $('#file-entries').textContent='Читаем папку…';
    try {
      const listing=await api(`/api/files?path=${encodeURIComponent(path)}&kind=${encodeURIComponent(picker.kind)}`);
      if(state.picker !== picker || picker.request !== request || !$('#utility-dialog').open || $('#utility-dialog').dataset.kind !== 'files') return;
      $('#file-path').value=listing.path;
      if(listing.warning) {$('#file-error').hidden=false;$('#file-error').textContent=listing.warning;}
      picker.selection=picker.kind === 'folder' ? listing.path : listing.selected?.path || (listing.entries || []).find(entry=>!entry.directory && entry.path === path)?.path || null;
      $('#file-select').disabled=!picker.selection;
      $('#file-selection').textContent=picker.selection ? `Выбрано: ${picker.selection}` : 'Выбери файл из списка или открой полный путь.';
      const entries=listing.entries || [];
      $('#file-entries').innerHTML=`${listing.parent ? '<button class="file-entry" data-file-parent>↑ На уровень выше</button>':''}${entries.map((entry,index)=>`<button class="file-entry" data-file-index="${index}">${icon(entry.directory ? 'folder':'text')}<span>${esc(entry.name)}</span>${entry.directory ? icon('arrow'):''}</button>`).join('')}${!entries.length ? '<p class="dialog-copy">Подходящих файлов здесь нет.</p>':''}${listing.truncated ? '<p class="dialog-copy">Показана часть папки. Укажи более точный путь.</p>':''}`;
      $('[data-file-parent]')?.addEventListener('click',()=>loadFiles(listing.parent));
      $$('[data-file-index]').forEach(button=>button.onclick=()=>{
        const entry=entries[Number(button.dataset.fileIndex)];
        if(entry.directory) {loadFiles(entry.path);return;}
        picker.selection=entry.path;$('#file-select').disabled=false;$('#file-selection').textContent=`Выбрано: ${entry.path}`;
        $$('[data-file-index]').forEach(row=>row.classList.toggle('selected',row === button));
      });
    } catch(error) {
      if(state.picker !== picker || picker.request !== request || $('#utility-dialog').dataset.kind !== 'files') return;
      $('#file-error').hidden=false;$('#file-error').textContent=error.message;
      $('#file-entries').textContent='Проверь путь и попробуй снова.';
    }
  }
  function defaultsError(message) {
    if ($('#defaults-error')) {$('#defaults-error').textContent=message;$('#defaults-error').hidden=false;}
  }
  function showDefaultsUpdate() {
    const offer = state.remote?.defaultsUpdate;
    state.defaultsPreview = offer ? {...offer,changes:(offer.changes || []).map(row=>({...row}))} : null;
    const changes = state.defaultsPreview?.changes || [];
    utility(`Рекомендации ${offer?.version || ''}`,`<p class="dialog-copy">Необязательные рекомендации для сравнения с сохранённым config.env. Личные настройки могут отличаться; применять рекомендации не обязательно. Будут записаны только перечисленные изменения. Несохранённые настройки, ключи, источники моделей и пути остаются без изменений. Работающий генератор применит изменения после безопасного перезапуска.</p><div id="defaults-changes" class="defaults-changes">${changes.length ? changes.map(row=>`<div data-defaults-key="${esc(row.key)}"><code>${esc(row.key)}</code><p class="defaults-values"><span>${esc(row.current || "Пусто (off)")}</span> → <strong>${esc(row.recommended)}</strong></p><p>${esc(row.reason)}</p></div>`).join('') : 'Обновлений рекомендованных значений нет.'}</div><p id="defaults-error" class="defaults-error" role="alert" hidden></p><div class="dialog-actions"><button class="button" data-ui="close-dialog">Позже</button><button class="button" id="defaults-refresh" data-ui="defaults-refresh">Обновить список</button>${changes.length ? '<button class="button" id="defaults-decline" data-submit-action>Оставить текущие</button><button class="button button-primary" id="defaults-accept" data-submit-action>Применить рекомендации</button>' : ''}</div>`);
    $('#utility-dialog').dataset.kind='defaults';
    const decide = name => action(name,{revision:state.defaultsPreview.revision});
    if ($('#defaults-accept')) $('#defaults-accept').onclick=()=>decide('acceptDefaults');
    if ($('#defaults-decline')) $('#defaults-decline').onclick=()=>decide('declineDefaults');
  }
  async function refreshDefaultsUpdate() {
    if (state.pending || state.posting) return;
    try {const remote=await api('/api/state');if(acceptSnapshot(remote)) showDefaultsUpdate();}
    catch(error) {defaultsError(error.message);}
  }
  function confirm(title,description,actionName,extra={},labelText='Подтвердить') {
    utility(title,`<p class="dialog-copy">${esc(description)}</p><div class="dialog-actions"><button class="button" data-ui="close-dialog">Отмена</button><button class="button ${actionName === 'stop' || actionName === 'clearTrace' ? 'button-danger':'button-primary'}" id="confirm-submit" data-submit-action>${esc(labelText)}</button></div>`);
    $('#confirm-submit').onclick=() => {$('#utility-dialog').close();action(actionName,extra);};
  }
  function showHelp() {
    utility('Как начать крафт',`<p class="dialog-copy">Студия настраивает генератор. Сам крафт происходит в Terraria с модом InfiniCrafterLocal.</p>${[
      ['01','Выбери автора','Подключи локальную текстовую модель или API. Автор отвечает за свойства и механику.'],['02','Настрой изображение','Выбери источник рисунка. Для sd.cpp укажи существующие файлы моделей; для API — адрес и ключ.'],['03','Запусти генератор','Сохрани настройки и запусти генератор. «Проверить» показывает реальное соединение, не готовность всех моделей.'],['04','Продолжи в игре','Открой Terraria с модом. Предметы создаются через игровой крафт. Студия не запускает пробную платную генерацию.']
    ].map(([n,title,text]) => `<div class="help-step"><span>${n}</span><div><h3>${title}</h3><p>${text}</p></div></div>`).join('')}<div class="dialog-actions"><a class="button" href="/guide?token=${encodeURIComponent(token)}#/docs/user/START_RU.md" target="_blank" rel="noopener">Локальная инструкция ↗</a><button class="button button-primary" data-ui="close-dialog">К работе ${icon('arrow')}</button></div>`);
  }
  function showPresetPreview() {
    const name = $('#preset-select').value;
    if (!name) {toast('Сначала выбери профиль.',true);return;}
    const source = name.startsWith('Мой: ') ? state.remote.userPresets[name.slice(5)] : state.remote.presets[name];
    const preset = source?.settings || source?.values || source;
    if (!preset || typeof preset !== 'object') {toast('Профиль не найден в локальной конфигурации.',true);return;}
    const changes = Object.entries(preset).filter(([key,val]) => key.startsWith('INFINI_') && !isCredentialKey(key) && String(val) !== value(key));
    utility('Применить сборку?',`<p class="dialog-copy">${esc(name)}<br>Текущие ключи остаются. Изменения будут подготовлены, но ещё не записаны в config.env.</p><div class="confirm-list">${changes.length ? changes.map(([key,val]) => `<div><span>${esc(names[key] || key)}</span><span>${esc(val)}</span></div>`).join(''):'Значения профиля уже совпадают с текущими.'}</div><div class="dialog-actions"><button class="button" data-ui="close-dialog">Отмена</button><button class="button button-primary" id="confirm-submit" data-submit-action>Применить ${icon('arrow')}</button></div>`);
    $('#confirm-submit').onclick=() => {$('#utility-dialog').close();action('applyPreset',{name});};
  }
  function showSavePreset() {
    utility('Сохранить профиль',`<p class="dialog-copy">Именованный профиль сохраняется отдельно. Ключи и токены в него не входят; config.env не меняется.</p><label class="dialog-field-label" for="new-preset-name">Название профиля</label><input class="dialog-input" id="new-preset-name" placeholder="Локальная модель" maxlength="80" autocomplete="off"><div class="dialog-actions"><button class="button" data-ui="close-dialog">Отмена</button><button class="button button-primary" id="confirm-submit" data-submit-action>Сохранить профиль</button></div>`);
    const submit=() => {
      const name=$('#new-preset-name').value.trim();
      if (!name) {$('#new-preset-name').focus();return;}
      if (Object.hasOwn(state.remote.userPresets || {},name)) {
        $('#utility-dialog').close();
        confirm('Заменить существующий профиль?',`Профиль «${name}» уже существует. Сохраним текущую сборку вместо него; config.env не изменится.`,'savePreset',{name},'Заменить профиль');
        return;
      }
      $('#utility-dialog').close();action('savePreset',{name});
    };
    $('#confirm-submit').onclick=submit;$('#new-preset-name').onkeydown=event => {if(event.key === 'Enter') submit();};$('#new-preset-name').focus();
  }
  document.addEventListener('input',event => {
    const target=event.target;
    if (target.matches('[data-field]')) {
      const key=target.dataset.field;state.draft[key]=target.type === 'checkbox' ? target.checked ? '1':'0':target.value;
      state.edits[key]=++state.editClock;recomputeDirty();target.closest('.field-row').classList.toggle('is-dirty',state.dirty.has(key));
      $$('[data-derived]').forEach(output=>{const derived=derivedField(output.dataset.derived);if(derived) output.textContent=derived.value;});
      if(target.type === 'checkbox') target.parentElement.querySelector('.toggle-label').textContent=target.checked ? 'Включено':'Выключено';
      if(target.tagName === 'SELECT' || target.type === 'checkbox') {const selection=key;render();$(`[data-field="${selection}"]`)?.focus({preventScroll:true});}
    }
    if(target.matches('[data-lan]')) {state.lan=target.checked;state.lanEdit=++state.editClock;target.parentElement.querySelector('.toggle-label').textContent=target.checked?'Включено':'Выключено';recomputeDirty();render();$('#lan-enabled')?.focus({preventScroll:true});}
    if(target.id === 'file-path' && state.picker) {state.picker.request++;state.picker.selection=null;$('#file-select').disabled=true;$('#file-selection').textContent='Нажми «Открыть», чтобы проверить новый путь.';$$('[data-file-index]').forEach(row=>row.classList.remove('selected'));}
    if(target.id === 'preset-select') state.presetChoice=target.value;
    if(target.id === 'global-search') {state.searchIndex=0;renderSearch();}
    if(target.id === 'page-search') {const start=target.selectionStart;state.filter=target.value;render();$('#page-search').focus({preventScroll:true});$('#page-search').setSelectionRange(start,start);}
  });
  document.addEventListener('click',event => {
    const navigation = event.target.closest('.rail a[href^="#"]');
    if (navigation && $('.rail').classList.contains('is-open') && navigation.hash === location.hash) {
      setMenu(false,false); $('#workspace').focus({preventScroll:true});
    }
    const button=event.target.closest('button,[data-ui],[data-search-key]');if(!button) return;
    if (button.tagName === 'A' && button.dataset.ui) event.preventDefault();
    if(button.dataset.action) {action(button.dataset.action);return;}
    if(button.dataset.browse) {showFilePicker(button.dataset.browse,button.dataset.browseType);return;}
    if(button.dataset.reveal) {const input=$(`[data-field="${button.dataset.reveal}"]`);input.type=input.type === 'password'?'text':'password';button.setAttribute('aria-pressed',String(input.type === 'text'));button.setAttribute('aria-label',input.type === 'text'?'Скрыть ключ':'Показать ключ');return;}
    if(button.dataset.helpField) {event.preventDefault();const key=button.dataset.helpField;state.helpFields.has(key)?state.helpFields.delete(key):state.helpFields.add(key);const y=window.scrollY;render();window.scrollTo(0,y);$(`[data-help-field="${key}"]`)?.focus({preventScroll:true});return;}
    if(button.dataset.searchKey) {focusField(button.dataset.searchKey);return;}
    if(button.dataset.traceTab) {state.traceTab=button.dataset.traceTab;$$('[data-trace-tab]').forEach(tab => {tab.classList.toggle('active',tab === button);tab.setAttribute('aria-selected',String(tab === button));tab.tabIndex=tab === button?0:-1;});$('#trace-view').setAttribute('aria-labelledby',button.id);updateDiagnostics();return;}
    switch(button.dataset.ui) {
      case 'defaults-update':showDefaultsUpdate();break;
      case 'defaults-refresh':refreshDefaultsUpdate();break;
      case 'search':showSearch();break;
      case 'review-conflict':showSaveConflict();break;
      case 'notifications':utility('Уведомления',state.notifications.length ? `<div class="notification-history">${[...state.notifications].reverse().map(notice=>`<article class="notification-entry${notice.error ? ' is-error':''}"><span>${icon(notice.error ? 'alert':'check')}</span><p>${esc(notice.message)}</p></article>`).join('')}</div>` : '<p class="dialog-copy">Уведомлений пока нет.</p>');break;
      case 'retry':poll();break;
      case 'close-dialog':if (button.closest('dialog')?.dataset.kind !== 'defaults' || !(state.pending || state.posting)) button.closest('dialog')?.close();break;
      case 'menu':setMenu(!$('.rail').classList.contains('is-open'));break;
      case 'close-menu':setMenu(false);break;
      case 'help':showHelp();break;
      case 'force-restart':confirm('Прервать крафт и перезапустить?','Активный и ожидающий крафт будет прерван. Это не подтверждает возврат материалов в игре. Используй только если безопасный перезапуск недоступен.','forceRestart',{confirm:true},'Прервать и перезапустить');break;
      case 'stop':confirm('Остановить генератор?','Проверим активный крафт перед остановкой собственного запущенного сервера. Черновик адреса не меняет цель; чужие процессы не изменяются.','stop',{},'Остановить безопасно');break;
      case 'exit':confirm('Закрыть студию?','Закроется только локальный интерфейс. Это действие не останавливает генератор. Несохранённые изменения в этой вкладке будут потеряны.','exitStudio',{},'Закрыть студию');break;
      case 'clear-trace':confirm('Очистить локальный журнал?','Будут удалены диагностические записи сохранённой конфигурации. Черновик пути не меняет цель. Готовые игровые предметы и рецепты не меняются. Это действие нельзя отменить.','clearTrace',{confirm:true},'Очистить журнал');break;
      case 'clear-lora':confirm('Отключить адаптер?','Сбросим настройки LoRA. Сам файл на диске не удаляется.','clearLora',{},'Отключить LoRA');break;
      case 'reset-sprite':confirm('Вернуть базовый resize?','Фильтр станет BOX, premultiplied resize будет включён. Остальные параметры спрайта остаются.','resetSprite',{},'Вернуть BOX');break;
      case 'apply-preset':showPresetPreview();break;
      case 'save-preset':showSavePreset();break;
      case 'discard':{
        if(state.pending || state.posting) {toast('Дождись подтверждения перед отменой.',true);break;}
        utility('Отменить изменения?', '<p class="dialog-copy">Все несохранённые изменения в этой вкладке будут заменены значениями из config.env.</p><div class="dialog-actions"><button class="button" data-ui="close-dialog">Продолжить редактирование</button><button class="button button-danger" id="confirm-submit">Отменить изменения</button></div>');
        $('#confirm-submit').onclick=()=>{state.draft={...state.remote.defaults,...state.remote.savedValues};state.baseline={...state.draft};state.lan=state.baselineLan=!!state.remote.savedLanEnabled;state.savedRevision=state.remote.savedRevision;state.revisionValues={...state.draft};state.presetChoice=null;state.editClock++;Object.keys(state.draft).forEach(key=>state.edits[key]=state.editClock);state.lanEdit=state.editClock;recomputeDirty();$('#utility-dialog').close();render();};break;
      }
    }
  });
  document.addEventListener('keydown',event => {
    if((event.ctrlKey || event.metaKey) && event.code === 'KeyK') {event.preventDefault();if(!$('#utility-dialog').open) showSearch();}
    if((event.ctrlKey || event.metaKey) && event.code === 'KeyS') {event.preventDefault();if(state.remote && !state.shutdown) action('save');}
    if($('#search-dialog').open && event.target.id === 'global-search' && ['ArrowDown','ArrowUp','Enter'].includes(event.key)) {
      event.preventDefault();
      if(event.key === 'Enter') {if(state.searchMatches[state.searchIndex]) focusField(state.searchMatches[state.searchIndex].key);}
      else {state.searchIndex=Math.max(0,Math.min(state.searchMatches.length-1,state.searchIndex+(event.key === 'ArrowDown'?1:-1)));$$('.search-result').forEach((result,index)=>result.classList.toggle('selected',index === state.searchIndex));const result=$(`#search-hit-${state.searchIndex}`);if(result) {const panel=$('#search-results');if(result.offsetTop < panel.scrollTop) panel.scrollTop=result.offsetTop;else if(result.offsetTop+result.offsetHeight>panel.scrollTop+panel.clientHeight) panel.scrollTop=result.offsetTop+result.offsetHeight-panel.clientHeight;}}
    }
    if(event.target.matches('[data-trace-tab]') && ['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();const tabs=$$('[data-trace-tab]'),index=tabs.indexOf(event.target);const next=event.key === 'Home'?0:event.key === 'End'?tabs.length-1:(index+(event.key === 'ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();
    }
    if(event.key === 'Escape') setMenu(false);
    if(event.key === 'Tab' && $('.rail').classList.contains('is-open') && !document.querySelector('dialog[open]')) {
      const items = $$('a[href],button:not(:disabled)', $('.rail')), first=items[0], last=items.at(-1);
      if(event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
    }
  });
  $$('dialog').forEach(dialog => {
    dialog.addEventListener('cancel',event=>{if(dialog.dataset.kind === 'defaults' && (state.pending || state.posting)) event.preventDefault();});
    dialog.addEventListener('click',event => {if(event.target === dialog && !(dialog.dataset.kind === 'defaults' && (state.pending || state.posting))) {const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom) dialog.close();}});
  });
  window.addEventListener('hashchange',navigate);
  window.addEventListener('resize',() => {if(innerWidth > 720) setMenu(false,false);});
  document.addEventListener('visibilitychange',() => {if(!document.hidden) poll();});
  window.addEventListener('beforeunload',event => {if(!state.shutdown && (state.dirty.size || state.lan !== state.baselineLan)) {event.preventDefault();event.returnValue='';}});
  navigate();poll();
})();
