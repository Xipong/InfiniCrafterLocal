/* Infinicraft Studio. Same-origin bridge; drafts stay in memory, Save writes local config. */
'use strict';
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const i18n = window.InfiniI18n;
  const t = (message, ...args) => i18n.t(message, ...args);
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const routes = {
    operate: ['Рабочий стол', '', 'Генератор предметов', 'Запуск, выбранные модели и состояние крафта в Terraria.'],
    configure: ['Конфигурация', '', 'Конфигурация', 'Текущие настройки, сохранённые профили и рекомендации.'],
    providers: ['Текст и механика', '', 'Текст и механика', 'Модель, которая описывает предмет и создаёт его игровую механику.'],
    images: ['Изображения', '', 'Изображения', 'Источник рисунка, размер исходника и параметры генерации.'],
    sprites: ['Спрайты и цвет', '', 'Спрайты и цвет', 'Обработка изображения: прозрачность, уменьшение и палитра.'],
    models: ['Модели и LoRA', '', 'Модели и LoRA', 'Программа sd.cpp, локальные веса и художественный адаптер.'],
    multiplayer: ['Совместная игра', '', 'Совместная игра', 'Адрес генератора, подключение Terraria и доставка спрайтов.'],
    diagnostics: ['Диагностика', '', 'Диагностика', 'Проверка соединения и журнал последних запросов крафта.']
  };
  const names = {
    INFINI_LANGUAGE:'Язык интерфейса и предметов',
    INFINI_USE_LLM:'Генерация механики моделью', INFINI_PROMPT_STYLE:'Художественное направление', INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK:'Технический запасной генератор', INFINI_GUI_PIPELINE_PRESET:'Профиль настроек', INFINI_LLM_PROVIDER:'Источник текста и механики', INFINI_CODEX_LLM_MODEL:'Текстовая модель Codex', INFINI_LMSTUDIO_URL:'Адрес LM Studio', INFINI_LMSTUDIO_MODEL:'Локальная текстовая модель', INFINI_OPENROUTER_API_KEY:'Ключ OpenRouter', INFINI_OPENROUTER_MODEL:'Модель OpenRouter', INFINI_OPENROUTER_PROVIDER:'Площадка OpenRouter', INFINI_OPENROUTER_HTTP_REFERER:'Источник запросов', INFINI_OPENROUTER_APP_TITLE:'Имя приложения в OpenRouter', INFINI_OPENAI_COMPAT_BASE_URL:'Адрес совместимого API', INFINI_OPENAI_COMPAT_API_KEY:'Ключ совместимого API', INFINI_OPENAI_COMPAT_MODEL:'Модель совместимого API', INFINI_LLM_API_MODE:'Формат запроса к модели', INFINI_LLM_RESPONSE_FORMAT:'Формат ответа', INFINI_LLM_TEMPERATURE:'Вариативность идеи', INFINI_LLM_REAUTHOR_TEMPERATURE:'Вариативность исправления', INFINI_VISUAL_DIRECTOR_TEMPERATURE:'Вариативность арт-директора', INFINI_LLM_MAX_TOKENS:'Лимит ответа, токены', INFINI_LLM_TIMEOUT:'Ожидание LLM-стадии, секунды', INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS:'Лимит VFX, токены', INFINI_VFX_LLM_DIRECTOR_TIMEOUT:'Ожидание VFX, секунды', INFINI_LLM_REASONING_MODE:'Глубина рассуждения', INFINI_LLM_REASONING_MAX_TOKENS:'Бюджет рассуждения, токены', INFINI_LLM_REASONING_EXCLUDE:'Не возвращать рассуждение в ответ', INFINI_LLM_LOCAL_REASONING_PROMPT:'Приватная самопроверка', INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS:'Пауза после сбоя, секунды', INFINI_LLM_FALLBACK_PROVIDER:'Запасной источник', INFINI_LLM_FALLBACK_MODEL:'Запасная модель', INFINI_LLM_FALLBACK_BASE_URL:'Адрес запасного API', INFINI_LLM_FALLBACK_API_KEY:'Ключ запасного API', INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER:'Запасная площадка OpenRouter', INFINI_LLM_FALLBACK_NETWORK_FAILS:'Сетевых сбоев до переключения',
    INFINI_IMAGE_BACKEND:'Источник изображений', INFINI_IMAGE_PARALLEL:'Параллельная генерация изображений', INFINI_IMAGE_MAX_CONCURRENCY:'Параллельных изображений', INFINI_SDCPP_SERVER_EXE:'Программа sd.cpp', INFINI_SDCPP_ROCM_COMPAT_ROOT:'Папка совместимости ROCm', INFINI_SDCPP_MODEL:'Диффузионная модель', INFINI_SDCPP_VAE:'Модель VAE / AE', INFINI_SDCPP_LLM:'Текстовый энкодер', INFINI_SDCPP_LORA_DIR:'Папка LoRA', INFINI_SDCPP_LORA_FILE:'Файл LoRA', INFINI_SDCPP_LORA_WEIGHT:'Сила LoRA', INFINI_SDCPP_LORA_PROMPT_TAGS:'Теги LoRA', INFINI_SDCPP_SERVER_URL:'Адрес sd.cpp', INFINI_SDCPP_SERVER_AUTOSTART:'Способ запуска sd.cpp', INFINI_SDCPP_SERVER_COMMAND_MODE:'Способ запуска sd.cpp', INFINI_SDCPP_SERVER_COMMAND_TEMPLATE:'Шаблон команды запуска', INFINI_SDCPP_SERVER_EXTRA_ARGS:'Дополнительные аргументы', INFINI_SDCPP_SERVER_SHOW_CONSOLE:'Показывать консоль sd.cpp', INFINI_SDCPP_SERVER_LOG_FILE:'Файл журнала sd.cpp', INFINI_SDCPP_WIDTH:'Ширина исходника, px', INFINI_SDCPP_HEIGHT:'Высота исходника, px', INFINI_SDCPP_STEPS:'Шаги генерации', INFINI_SDCPP_CFG:'Влияние промпта / CFG', INFINI_SDCPP_SAMPLER:'Сэмплер', INFINI_SDCPP_SEED:'Seed изображения', INFINI_ZIMAGE_PROMPT_CONTRACT:'Правила промпта Z-Image', INFINI_ZIMAGE_POSITIVE_ONLY:'Только позитивный промпт', INFINI_CODEX_IMAGE_MODEL:'Модель изображений Codex', INFINI_CODEX_IMAGE_QUALITY:'Качество изображения', INFINI_CODEX_IMAGE_SIZE:'Размер изображения', INFINI_CODEX_IMAGE_TIMEOUT:'Ожидание Codex, секунды', INFINI_CODEX_VISUAL_REASONING:'Рассуждение арт-директора Codex', INFINI_IMAGE_API_BASE_URL:'Адрес API изображений', INFINI_IMAGE_API_KEY:'Ключ API изображений', INFINI_IMAGE_API_MODEL:'Модель изображений API', INFINI_IMAGE_API_PATH:'Путь API генерации', INFINI_IMAGE_API_SIZE:'Размер исходного изображения', INFINI_IMAGE_API_TIMEOUT:'Ожидание API, секунды', INFINI_A1111_URL:'Адрес Automatic1111', INFINI_COMFYUI_URL:'Адрес ComfyUI',
    INFINI_VISUAL_ASSET_MODE:'Состав визуальных ассетов', INFINI_VISUAL_DIRECTOR_LLM:'Нейросетевой арт-директор', INFINI_VISUAL_DIRECTOR_MAX_TOKENS:'Лимит арт-директора, токены', INFINI_VFX_LLM_DIRECTOR:'Нейросетевые визуальные эффекты', INFINI_REMOVE_BG:'Удалять фон', INFINI_BG_REMOVE_MODE:'Метод удаления фона', INFINI_BG_COLOR:'Фон исходного рисунка', INFINI_CHROMA_TOLERANCE:'Допуск цвета фона', INFINI_ALPHA_THRESHOLD:'Порог прозрачности', INFINI_SPRITE_KEYER_SPILL_RADIUS:'Радиус очистки краёв', INFINI_SPRITE_KEYER_RESIDUE_STEPS:'Шаги очистки остаточного цвета', INFINI_SPRITE_RETRIES:'Повторы при дефекте спрайта', INFINI_SAVE_SPRITE_STAGES:'Сохранять промежуточные спрайты', INFINI_PIXEL_POSTERIZE:'Ограничивать палитру', INFINI_MAX_COLORS:'Количество цветов', INFINI_SPRITE_MASTER_CANVAS:'Промежуточный холст, px', INFINI_SPRITE_DOWNSCALE_FILTER:'Фильтр уменьшения', INFINI_SPRITE_CHROMA_DEFRINGE:'Очищать цветные ореолы', INFINI_SPRITE_PREMULTIPLIED_RESIZE:'Учитывать прозрачность при resize', INFINI_VISUAL_STRICT_AI_AUTHORSHIP:'Строгое авторство модели', INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK:'Запасное процедурное изображение', INFINI_VISUAL_REQUIRE_ITEM_SPRITE:'Требовать спрайт предмета',
    INFINI_HOST:'Интерфейс генератора', INFINI_PORT:'Порт генератора', INFINI_MP_ASSET_TRANSPORT:'Доставка спрайтов друзьям', INFINI_ASSET_PUBLIC_BASE_URL:'Публичный адрес ассетов', INFINI_TERRARIA_PORT:'Порт Terraria', INFINI_CRAFT_HTTP_TIMEOUT_SECONDS:'Ожидание крафта, секунды', INFINI_CRAFT_HTTP_ATTEMPTS:'Попытки соединения', INFINI_COMBINE_BUSY_WAIT_SECONDS:'Ожидание очереди, секунды', INFINI_MULTIDEV_CONCURRENCY:'Параллельные окна разработчика', INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED:'Отладочная выдача расходников', INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD:'Минимальная выдача расходников', INFINI_TRACE_PROMPTS:'Записывать промпты и этапы', INFINI_TRACE_MAX_PROMPT_CHARS:'Лимит предпросмотра, символы', INFINI_TRACE_EVENTS_TAIL:'Событий в журнале', INFINI_CONSOLE_EVENT_LEVEL:'Подробность консоли'
  };
  const shortHelp = {
    INFINI_IMAGE_PARALLEL:'Для облака: изображения одновременно с VFX Designer. Выключи при нехватке видеопамяти локальной модели. Если сохранён лимит 1, изображения идут по одному — поставь 2–4 ниже. Сохранить → перезапустить сервер.',
    INFINI_IMAGE_MAX_CONCURRENCY:'1–4 одновременных изображения, по умолчанию 4. Выключенная галочка всегда ограничивает запросы одним.',
    INFINI_LLM_PROVIDER:'Кто придумывает свойства и пишет механику предмета.', INFINI_LMSTUDIO_URL:'Локальный OpenAI-compatible сервер. Обычно порт 1234.', INFINI_LMSTUDIO_MODEL:'Точное имя модели или auto — выбор на стороне сервера.', INFINI_OPENROUTER_API_KEY:'При сохранении ключ записывается в локальный config.env. В профили не копируется.', INFINI_OPENAI_COMPAT_API_KEY:'Не API-ключ Codex. Только для выбранного совместимого сервиса.', INFINI_PROMPT_STYLE:'Меняет художественное направление, а не модель или механику.', INFINI_LLM_REASONING_MODE:'Дополнительная самопроверка. Доступность зависит от модели.', INFINI_IMAGE_BACKEND:'Локальный движок, подписка или внешний API.', INFINI_SDCPP_SERVER_URL:'Адрес локального сервера изображений, не этой студии.', INFINI_SDCPP_SERVER_AUTOSTART:'Внешний — только URL. Управляемый — программа и файлы моделей на этом ПК.', INFINI_SDCPP_SERVER_EXE:'Путь к sd-server.exe на этом компьютере.', INFINI_SDCPP_MODEL:'Файл основной FLUX / Z-Image модели, обычно GGUF.', INFINI_SDCPP_LLM:'Текстовый энкодер, совместимый с основной моделью.', INFINI_SDCPP_VAE:'Декодер, совместимый с основной моделью.', INFINI_SDCPP_LORA_FILE:'Выбери существующий файл художественного адаптера.', INFINI_SDCPP_LORA_WEIGHT:'Для pixel-art адаптера начни с 0.20–0.30.', INFINI_BG_COLOR:'Прозрачный — native alpha. Другие цвета — chroma-key.', INFINI_SPRITE_DOWNSCALE_FILTER:'BOX — базовый фильтр. Сброс также включит premultiplied resize.', INFINI_HOST:'127.0.0.1 — этот ПК; 0.0.0.0 — принимать подключения из сети.', INFINI_MP_ASSET_TRANSPORT:'Внутри Terraria — без отдельного публичного HTTP-адреса.', INFINI_TRACE_PROMPTS:'Полный локальный журнал растёт до ручной очистки.'
  };
  const optionNames = {
    INFINI_LANGUAGE:{ru:'Русский',en:'English'},
    INFINI_LLM_PROVIDER:{local:'LM Studio · локально',openrouter:'OpenRouter',openai_compat:'Совместимый API',openai_codex:'ChatGPT / Codex'},
    INFINI_IMAGE_BACKEND:{sdcpp:'sd.cpp · локально',openai_codex:'ChatGPT / Codex',image_api:'Внешний Image API',off:'Без изображений',comfyui:'ComfyUI',a1111:'Automatic1111'},
    INFINI_PROMPT_STYLE:{Default:'Свободное направление', 'Terraria Like':'В духе Terraria'},
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
    if (names[field.key]) return t(names[field.key]);
    const pool = field.key.match(/^INFINI_LLM_POOL_([234])_(.+)$/);
    if (pool) return t("{0} · линия {1}", {ENABLED:t('Использовать модель'),PROVIDER:t('Источник'),BASE_URL:t('Адрес API'),API_KEY:t('Ключ API'),MODEL:t('Модель'),OPENROUTER_PROVIDER:t('Площадка OpenRouter'),API_MODE:t('Формат запроса')}[pool[2]] || pool[2], pool[1]);
    return t(field.label) || field.key.replace(/^INFINI_/,'').replaceAll('_',' ');
  }
  function pageFor(key, suggested='configure') {
    if (materialKeys.has(key)) return 'models';
    if (/^INFINI_(HOST|PORT|MP_|ASSET_PUBLIC|TERRARIA_PORT|CRAFT_HTTP|COMBINE_BUSY|MULTIDEV)/.test(key)) return 'multiplayer';
    if (/^INFINI_(TRACE_|CONSOLE_|DEBUG_|ALLOW_DETERMINISTIC)/.test(key)) return 'diagnostics';
    if (/^INFINI_(LLM_|LMSTUDIO_|OPENROUTER_|OPENAI_COMPAT_|USE_LLM|PROMPT_STYLE|CODEX_LLM|CODEX_VISUAL|VISUAL_DIRECTOR_TEMPERATURE)/.test(key)) return 'providers';
    if (/^INFINI_(IMAGE_|SDCPP_|ZIMAGE_|CODEX_IMAGE|A1111_|COMFYUI_)/.test(key)) return 'images';
    if (/^INFINI_(VISUAL_|VFX_|SPRITE_|REMOVE_BG|BG_|CHROMA_|ALPHA_|SAVE_SPRITE|PIXEL_|MAX_COLORS)/.test(key)) return 'sprites';
    return ({trace:'diagnostics',diagnostics:'diagnostics',network:'multiplayer',sdcpp:'images'}[suggested]) || (routes[suggested] ? suggested : 'configure');
  }
  // Match credential words, not numeric budgets such as MAX_TOKENS.
  const isCredentialKey = key => /(?:^|_)(?:API_KEY|TOKEN|PASSWORD|SECRET|CREDENTIALS?)(?:_|$)/i.test(key);
  function makeFields(remote) {
    const map = new Map((remote.fields || []).map(field => [field.key,{...field}]));
    Object.keys({...remote.defaults,...(remote.savedValues || remote.values),...state.draft}).filter(key => key.startsWith('INFINI_')).forEach(key => {
      if (!map.has(key)) map.set(key,{key,label:names[key],help:remote.fieldHelp?.[key] || '',options:[],secret:isCredentialKey(key),advanced:!basicKeys.has(key),synthetic:true});
    });
    return [...map.values()].map(field => {
      let options=field.options;
      if(value('INFINI_LLM_PROVIDER') === 'openai_codex' && ['INFINI_LLM_REASONING_MODE','INFINI_CODEX_VISUAL_REASONING'].includes(field.key)) {
        const model=remote.account?.textModels?.[value('INFINI_CODEX_LLM_MODEL')];
        // Metadata belongs to the selected browser draft, never another tab's model.
        options=model ? [...(field.key === 'INFINI_LLM_REASONING_MODE' ? ['off']:['inherit','model_default']),...model.efforts] : [];
      }
      return {...field,options,secret:field.secret || isCredentialKey(field.key),route:pageFor(field.key,field.page)};
    });
  }
  function syncLanguage() {
    const language=value('INFINI_LANGUAGE','ru');
    if(!i18n.setLanguage(language)) return false;
    i18n.localize(document);
    $('#language-select').value=language;
    $('#crumb').textContent=t(routes[state.page][0]);
    document.title=`${t(routes[state.page][0])} — Infinicraft`;
    state.operateSignature=null;
    if(state.remote) $('#version').textContent=t('Версия {0}',state.remote.version || 'α');
    setConnection(state.connected,state.connectionMessage || '');
    return true;
  }
  function value(key, fallback='') {
    const current=state.draft[key] ?? fallback;
    return key === 'INFINI_LANGUAGE' ? String(current).trim().toLowerCase() : current;
  }
  function draftStatusText() { return state.dirty.size || state.lan !== state.baselineLan ? t('Черновик / Не сохранён') : t('Локальная конфигурация'); }
  function recomputeDirty() {
    syncLanguage();
    state.dirty = new Set(Object.keys(state.draft).filter(key => state.draft[key] !== (state.baseline[key] ?? '')));
    $('#save-tray').hidden = !state.dirty.size && state.lan === state.baselineLan;
    const total = state.dirty.size + Number(state.lan !== state.baselineLan);
    $('#dirty-label').textContent = t("{0} {1} в настройках", total, total === 1 ? t('изменение') : total < 5 ? t('изменения') : t('изменений'));
    $$('[data-draft-status]').forEach(element => element.textContent=draftStatusText());
    $$('[data-dirty-count]').forEach(element => element.textContent=total ? t("{0} несохранённых изменений", total) : t('Изменений нет'));
    $$('.save-panel').forEach(element => element.classList.toggle('is-dirty',!!total));
    const conflict=$('#draft-conflict');
    if(conflict) conflict.hidden=!(state.remote?.savedRevision && state.savedRevision && state.remote.savedRevision !== state.savedRevision && total);
    updateActionButtons();
  }
  function inactiveReason(field) {
    const key = field.key, provider = value('INFINI_LLM_PROVIDER','local'), backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    const pool=key.match(/^INFINI_LLM_POOL_([234])_(.+)$/);
    if(pool && pool[2] !== 'ENABLED' && value(`INFINI_LLM_POOL_${pool[1]}_ENABLED`) !== '1') return t('Дополнительная линия выключена');
    if (pool && pool[2] === 'OPENROUTER_PROVIDER' && value(`INFINI_LLM_POOL_${pool[1]}_PROVIDER`) !== 'openrouter') return t('Для линии OpenRouter');
    if (['INFINI_LLM_TEMPERATURE','INFINI_LLM_REAUTHOR_TEMPERATURE','INFINI_VISUAL_DIRECTOR_TEMPERATURE','INFINI_LLM_MAX_TOKENS','INFINI_LLM_REASONING_MAX_TOKENS','INFINI_LLM_REASONING_EXCLUDE'].includes(key) && provider === 'openai_codex') return t('Codex не принимает этот параметр');
    if (key === 'INFINI_CODEX_VISUAL_REASONING' && provider !== 'openai_codex') return t('Для текстового Codex');
    const reasoning = value('INFINI_LLM_REASONING_MODE','off').toLowerCase().replaceAll('-','_');
    const reasoningOff = ['', 'off', 'false', '0', 'disabled', 'disable', 'none', 'no_reasoning'].includes(reasoning);
    const promptReasoning = ['prompt','prompt_light','prompt_strong','local_prompt','local_light','local_strong'].includes(reasoning);
    if (key === 'INFINI_LLM_REASONING_EXCLUDE' && (provider === 'local' || reasoningOff || promptReasoning)) return t('Для API reasoning, не prompt-only режима');
    if (key === 'INFINI_LLM_REASONING_MAX_TOKENS' && (provider === 'local' || !['tokens','token_budget','max_tokens','budget'].includes(reasoning))) return t('Для API с режимом бюджета токенов');
    if (key === 'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD' && value('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED') !== '1') return t('Отладочная выдача выключена');
    if (['INFINI_IMAGE_PARALLEL','INFINI_IMAGE_MAX_CONCURRENCY'].includes(key) && backend === 'off') return t('Изображения выключены');
    if (key === 'INFINI_IMAGE_MAX_CONCURRENCY' && value('INFINI_IMAGE_PARALLEL') === '0') return t('Параллельная генерация выключена: запросы идут по одному');
    if (['INFINI_VISUAL_DIRECTOR_LLM','INFINI_VFX_LLM_DIRECTOR'].includes(key) && !['full','all','projectile','visualpack','assetpack'].includes(value('INFINI_VISUAL_ASSET_MODE'))) return t('Дополнительные визуальные ассеты выключены');
    if (['INFINI_CODEX_LLM_MODEL','INFINI_CODEX_VISUAL_REASONING'].includes(key) && value('INFINI_USE_LLM') === '0') return t('Текстовая генерация выключена');
    if (['INFINI_REMOVE_BG','INFINI_BG_REMOVE_MODE','INFINI_CHROMA_TOLERANCE','INFINI_SPRITE_KEYER_SPILL_RADIUS','INFINI_SPRITE_KEYER_RESIDUE_STEPS','INFINI_SPRITE_CHROMA_DEFRINGE'].includes(key) && value('INFINI_BG_COLOR') === 'transparent') return t('Нативная прозрачность: локальный keyer не используется');
    if (['INFINI_BG_REMOVE_MODE','INFINI_CHROMA_TOLERANCE','INFINI_SPRITE_KEYER_SPILL_RADIUS','INFINI_SPRITE_KEYER_RESIDUE_STEPS','INFINI_SPRITE_CHROMA_DEFRINGE'].includes(key) && value('INFINI_REMOVE_BG') === '0') return t('Удаление фона выключено');
    if (/^INFINI_LMSTUDIO_/.test(key) && provider !== 'local') return t('Для локального источника текста');
    if (/^INFINI_OPENROUTER_/.test(key) && provider !== 'openrouter') return t('Для источника OpenRouter');
    if (/^INFINI_OPENAI_COMPAT_/.test(key) && provider !== 'openai_compat') return t('Для совместимого API');
    if (/^INFINI_CODEX_LLM_/.test(key) && provider !== 'openai_codex') return t('Для ChatGPT / Codex');
    if (/^INFINI_(SDCPP_|ZIMAGE_)/.test(key) && backend !== 'sdcpp') return t('Для локального sd.cpp');
    if (['INFINI_SDCPP_SERVER_EXE','INFINI_SDCPP_ROCM_COMPAT_ROOT','INFINI_SDCPP_MODEL','INFINI_SDCPP_VAE','INFINI_SDCPP_LLM','INFINI_SDCPP_SERVER_COMMAND_MODE','INFINI_SDCPP_SERVER_COMMAND_TEMPLATE','INFINI_SDCPP_SERVER_EXTRA_ARGS','INFINI_SDCPP_SERVER_SHOW_CONSOLE','INFINI_SDCPP_SERVER_LOG_FILE'].includes(key) && value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1') return t('Для управляемого запуска sd.cpp');
    if (/^INFINI_CODEX_IMAGE_/.test(key) && backend !== 'openai_codex') return t('Для изображений ChatGPT / Codex');
    if (/^INFINI_IMAGE_API_/.test(key) && backend !== 'image_api') return t('Для внешнего Image API');
    if (key === 'INFINI_A1111_URL' && backend !== 'a1111') return t('Для Automatic1111');
    if (key === 'INFINI_COMFYUI_URL' && backend !== 'comfyui') return t('Для ComfyUI');
    if (field.route === 'sprites' && backend === 'off') return t('Изображения выключены');
    if (key === 'INFINI_MAX_COLORS' && value('INFINI_PIXEL_POSTERIZE') !== '1') return t('Палитра не ограничена');
    if (key === 'INFINI_ASSET_PUBLIC_BASE_URL' && value('INFINI_MP_ASSET_TRANSPORT') !== 'http') return t('Доставка идёт внутри Terraria');
    if (key === 'INFINI_ASSET_PUBLIC_BASE_URL' && !state.lan) return t('Режим LAN / Radmin выключен');
    if (key === 'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE' && value('INFINI_SDCPP_SERVER_COMMAND_MODE') !== 'template') return t('Запуск использует автоматический argv');
    // Native metadata describes the controller values, not unsaved browser edits.
    if (field.disabled && !state.dirty.size && state.lan === state.baselineLan && Object.entries(state.remote?.values || {}).every(([name,val])=>value(name) === val)) return t(field.disabled);
    return '';
  }
  function maybeLoadCatalog() {
    if(state.remote?.account?.authenticated === false) state.catalogAutoRequested=false;
    if(state.page !== 'providers' || value('INFINI_LLM_PROVIDER') !== 'openai_codex' || state.remote?.account?.authenticated !== true || !state.connected || state.pending || state.posting || state.shutdown || state.catalogAutoRequested) return;
    state.catalogAutoRequested=true;
    // Reuse an already loaded account catalog; one failed attempt stays manual-retryable.
    if(!Object.keys(state.remote.account.textModels || {}).length) return action('codexCatalog');
  }
  function accountText(page) {
    const account=state.remote?.account || {};
    let detail=account[page === 'providers' ? 'catalog':'images'];
    if(page === 'providers' && /^(Текстовая модель аккаунта:|Сохранённый reasoning|Ручной slug вне текущего каталога:)/.test(detail || '')) detail=t("В последнем каталоге аккаунта: {0} моделей. Image-доступ не проверен.", Object.keys(account.textModels || {}).length);
    const lines=[account.status,detail].filter(Boolean).map(text => t(text));
    if(page === 'providers' && value('INFINI_LLM_PROVIDER') === 'openai_codex') {
      const slug=value('INFINI_CODEX_LLM_MODEL'),model=account.textModels?.[slug];
      if(model) {
        lines.push(t("Для выбранной модели {0} в последнем каталоге: {1}. По умолчанию: {2}.", slug, model.efforts.join(', ') || t('effort не заявлен'), model.defaultEffort || t('не указан')));
        const reasoning=value('INFINI_LLM_REASONING_MODE'),visual=value('INFINI_CODEX_VISUAL_REASONING');
        if(!['off',...model.efforts].includes(reasoning) || !['inherit','model_default',...model.efforts].includes(visual)) lines.push(t('Выбранный effort не поддерживается этой моделью. Значения сохранены; выбери поддерживаемый вариант.'));
      } else lines.push(slug ? t('Выбранный slug ещё не подтверждён каталогом. Effort можно ввести вручную; значение не подменяется.') : t('Выбери текстовую модель. Каталог не выбирает её автоматически.'));
    }
    return lines.join('\n') || t('Статус аккаунта ещё не запрошен.');
  }
  async function api(path, payload) {
    if (!token) throw new Error(t('Открой студию через локальный запускатор. Токен сессии не получен.'));
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(),12000);
    try {
      const response = await fetch(path,{method:payload ? 'POST':'GET',cache:'no-store',credentials:'same-origin',headers:{'X-Infini-Token':token,...(payload ? {'Content-Type':'application/json'}:{})},body:payload ? JSON.stringify(payload):undefined,signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(response.status === 403 ? t('Сессия недоступна. Открой студию заново через запускатор.') : t(data.error) || t("Ошибка локального соединения ({0})", response.status));
      return data;
    } finally {clearTimeout(timer);}
  }
  function setConnection(connected, message='') {
    state.connected = connected;
    state.connectionMessage=message;
    const connection = $('#connection');
    connection.className = `connection is-${connected ? 'online':'offline'}`;
    connection.innerHTML = `<span class="status-dot"></span><span>${connected ? t('Студия на связи'):t('Нет связи')}</span>`;
    $('#connection-banner').hidden = connected || state.shutdown;
    if (!connected && !state.shutdown) $('#connection-banner').innerHTML = `<span>${esc(t(message))} ${t("Изменения остаются в этой вкладке.")}</span><button data-ui="retry">${t("Повторить")}</button>`;
    updateActionButtons();
  }
  function reconcilePersistedValues(pending,receipt,defaults={}) {
    const saved=receipt.savedValues;
    state.savedRevision=receipt.savedRevision || state.savedRevision;
    state.revisionValues={...defaults,...saved};
    Object.entries(pending.sent).forEach(([key,val])=>{if((state.edits[key] || 0) <= pending.clock) state.draft[key]=saved[key] ?? val;});
    if(pending.action !== 'acceptDefaults' && (state.lanEdit || 0) <= pending.clock) state.lan=saved.INFINI_HOST === '0.0.0.0' || !!saved.INFINI_ASSET_PUBLIC_BASE_URL;
  }
  function acceptSnapshot(remote) {
    if (!remote.values || !Array.isArray(remote.fields)) return false;
    const first = !state.remote;
    const presentation=()=>JSON.stringify(state.fields.map(field=>[field.key,inactiveReason(field),!!derivedField(field.key)]));
    const previousPresentation=presentation();
    let needsRender=false, finished=null;
    const previousFields = JSON.stringify(state.fields.map(f => [f.key,f.options]));
    const previousPresets = JSON.stringify([state.remote?.presets,state.remote?.userPresets]);
    const saved = {...remote.defaults,...(remote.savedValues || remote.values)};
    const wasDirty=state.dirty.size || state.lan !== state.baselineLan;
    if (first) {
      // Browser drafts belong to this tab. A controller may hold another tab's
      // prepared profile; only persisted values initialize a fresh tab.
      state.draft={...saved};state.lan=!!remote.savedLanEnabled;
    } else {
      const submission=state.pending || state.submission;
      const protectedKeys=submission?.dirtyKeys || Object.keys(submission?.sent || {});
      // A clean key deleted on disk is not a new local edit to write back.
      for(const key of Object.keys(state.baseline)) {
        if(!Object.hasOwn(saved,key) && !state.dirty.has(key) && !protectedKeys.includes(key)) {delete state.draft[key];delete state.edits[key];}
      }
      Object.entries(saved).forEach(([key,val])=>{
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
      // A process launch can fail after a successful disk write. Reconcile that
      // confirmed write independently, while keeping the action visibly failed.
      if(receipt.savedValues && receipt.savedRevision && ['save','start','forceRestart','acceptDefaults'].includes(pending.action)) reconcilePersistedValues(pending,receipt,remote.defaults);
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
          toast(pending.action === 'acceptDefaults' ? t('Записаны только показанные рекомендации. Остальной черновик не сохранён.') : t('Рекомендации отклонены. config.env не изменён.'));
        }
        if (transforming && (state.lanEdit || 0) <= pending.clock) state.lan = !!(receipt.lanEnabled ?? pending.lan);
        // A handled callback is not proof of a disk write or a running generator.
        if (['save','start','forceRestart'].includes(pending.action) && (receipt.status === 'succeeded' || /^saved:/i.test(remote.status || ''))) {
          if(!receipt.savedValues || !receipt.savedRevision) {
            reconcilePersistedValues(pending,{...receipt,savedValues:receipt.savedValues || saved},remote.defaults);
            if((state.lanEdit || 0) <= pending.clock && !receipt.savedValues) state.lan=state.baselineLan;
          }
          toast(pending.action !== 'save' ? (receipt.message || t('Процесс генератора запущен. Проверь соединение, чтобы подтвердить готовность.')) : t('Настройки записаны в config.env.'));
        } else if (pending.action === 'savePreset') toast(t('Профиль сохранён отдельно. config.env не изменён.'));
        else if (transforming) toast(t('Изменения подготовлены. Сохрани конфигурацию, чтобы записать их на диск.'));
        else if (pending.action !== 'exitStudio' && !defaultsDecision) toast(({start:t('Запуск передан генератору. Его состояние — на рабочем столе.'),stop:t('Безопасная остановка завершена.'),health:t('Проверка соединения завершена. Состояние — на рабочем столе.'),validate:t('Проверка путей завершена.'),trace:t('Журнал обновлён. Источник и статус показаны над записями.'),codexLogin:t('Результат входа показан в статусе аккаунта.'),codexStatus:t('Статус аккаунта обновлён.'),codexCatalog:t('Каталог моделей обновлён.'),codexPing:t('Проверка аккаунта завершена.'),codexLogout:t('Выход из аккаунта обработан.'),cancelTrace:t('Обновление журнала отменено.'),openConfig:t('Сохранённая конфигурация открыта для просмотра.'),openCache:t('Открываем папку кеша.'),clearTrace:t('Очистка журнала завершена.')})[pending.action] || t('Действие обработано.'));
      } else {
        const message = receipt.message || t('Действие не выполнено. Изменения сохранены в этой вкладке.');
        if (['acceptDefaults','declineDefaults'].includes(pending.action)) defaultsError(message);
        toast(message,true);
      }
      state.suppressToast=false;state.pending = null; clearTimeout(pending.timer);finished=pending;
      if(receipt.ok && ['applyPreset','savePreset'].includes(pending.action)) state.presetChoice=null;
      if (pending.action === 'exitStudio' && receipt.ok && receipt.status === 'succeeded') {
        state.shutdown=true;clearTimeout(state.pollTimer);$('#utility-dialog').close();
        $('#connection').innerHTML=`<span class="status-dot"></span><span>${t("Студия закрыта")}</span>`;
        const closeMessage=remote.managed ? t('Студия закрыта. Запущенный ею генератор завершает работу.') : t('Закрыта только студия. Генератор не остановлен этим действием.');
        $('#workspace').innerHTML=`<div class="initial-loading"><h1>${t("Студия закрыта")}</h1><p>${closeMessage}<br>${t("Эту вкладку можно закрыть.")}</p></div>`;
        updateActionButtons();return true;
      }
      if (receipt.result?.kind === 'document') showDocument(receipt.result);
      if (receipt.result?.kind === 'guide' && receipt.result.url?.startsWith('/guide?')) utility(receipt.result.title || t('Инструкция'), `<p class="dialog-copy">${t("Интерактивное руководство открывается в отдельной вкладке.")}</p><a class="button button-primary" href="${esc(receipt.result.url)}" target="_blank" rel="noopener">${t("Открыть руководство ↗")}</a>`);
      if (['applyPreset','browse','clearLora','useLora','resetSprite','savePreset'].includes(pending.action)) needsRender=true;
    }
    for (const notice of remote.notifications || []) {
      if (state.seenNotifications.has(notice.id)) continue;
      state.seenNotifications.add(notice.id);
      toast([notice.title,notice.message].filter(Boolean).map(text => t(text)).join(' · '), notice.level !== 'info');
    }
    state.fields=makeFields(remote);
    needsRender=syncLanguage() || needsRender;
    recomputeDirty();
    if (state.page === 'configure' && $('#preset-select') && document.activeElement !== $('#preset-select')) $('#preset-select').value = state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    if (first || needsRender || previousPresentation !== presentation() || previousFields !== JSON.stringify(state.fields.map(f => [f.key,f.options])) || previousPresets !== JSON.stringify([remote.presets,remote.userPresets])) renderPreservingFocus();
    else if (state.page === 'operate') renderOperate();
    else if (state.page === 'diagnostics') updateDiagnostics();
    syncInputs();
    if ($('#account-status')) $('#account-status').textContent=accountText(state.page);
    $$('[data-account-auth]').forEach(element=>element.textContent=remote.account?.authenticated ? t('Вход выполнен'):t('Требуется вход'));
    $('#version').textContent = t("Версия {0}", remote.version || 'α');
    if($('#defaults-summary')) $('#defaults-summary').textContent=defaultsSummary();
    restoreActionFocus(finished);
    return true;
  }
  async function poll() {
    clearTimeout(state.pollTimer);
    if (state.fetching || state.shutdown) return;
    state.fetching = true;
    try {
      const remote = await api('/api/state');
      if (acceptSnapshot(remote)) {if(!state.shutdown) {setConnection(true);maybeLoadCatalog();}}
      else setConnection(false,t('Мастерская ещё загружается.'));
    } catch (error) {
      setConnection(false,error.name === 'AbortError' ? t('Локальный сервер не ответил вовремя.') : error.message);
      if (!state.remote) {
        $('.initial-loading h1').innerHTML = t('Не удалось подключиться');
        $('.initial-loading p').textContent = t('Проверь, что локальный запускатор студии остаётся открытым.');
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
    if (!state.connected || state.pending || state.posting) {toast(t('Дождись ответа текущего действия или восстанови соединение.'),true);return;}
    if(name === 'codexCatalog') state.catalogAutoRequested=true;
    const active=document.activeElement;
    const focus=active?.dataset?.action === name ? {element:active,action:name,page:state.page,region:active.closest('#save-tray') ? '#save-tray':'#workspace'} : null;
    state.posting = true;
    const defaultsDecision = ['acceptDefaults','declineDefaults'].includes(name);
    const sent = defaultsDecision ? (name === 'acceptDefaults' ? Object.fromEntries((state.defaultsPreview?.changes || []).map(row => [row.key,row.recommended])) : {}) : editableValues();
    const clock = state.editClock, sentLan = state.lan, dirtyKeys=[...state.dirty];
    // Protect the submission from the first byte sent, not only after its id arrives.
    state.submission = {action:name,sent,clock,lan:sentLan,dirtyKeys,focus};
    updateActionButtons();
    try {
      const queued = await api('/api/action',{action:name,values:defaultsDecision ? {} : sent,extra:defaultsDecision ? {revision:extra.revision} : {lanEnabled:sentLan,...(['save','start','forceRestart'].includes(name) ? {savedRevision:state.savedRevision} : {}),...extra}});
      if (!queued.ok || !queued.id) throw new Error(t('Локальный сервер не подтвердил очередь действия.'));
      const pending = {id:queued.id,action:name,sent,clock,lan:sentLan,dirtyKeys,focus,timer:null};
      state.pending = pending;
      state.submission = null;
      pending.timer = setTimeout(() => {
        if (state.pending?.id !== queued.id) return;
        // Keep the pending submission protected after a timeout: an action may still finish.
        toast(t('Подтверждение задерживается. Изменения защищены; действие может ещё завершиться.'),true);
      },name === 'browse' ? 180000 : 30000);
      poll();
    } catch (error) {if (defaultsDecision) defaultsError(error.message); toast(error.message,true);}
    finally {state.submission = null; state.posting = false; updateActionButtons();if(!state.pending) restoreActionFocus({focus});}
  }
  function restoreActionFocus(finished) {
    const focus=finished?.focus;
    // Disabling the initiating button drops focus to body. Restore only that
    // abandoned focus, never a newer field, dialog, or navigation choice.
    if(!focus || focus.page !== state.page || document.activeElement !== document.body || document.querySelector('dialog[open]')) return;
    const candidates=focus.element.isConnected ? [focus.element] : $$('[data-action]',$(focus.region));
    candidates.find(button=>button.dataset.action === focus.action && !button.disabled && button.getClientRects().length)?.focus({preventScroll:true});
  }
  function updateActionButtons() {
    $('#language-select').disabled=!state.remote || state.shutdown;
    const exitHint=state.remote?.managed ? t('Закрыть студию и запущенный ею генератор') : t('Закрыть только студию, не генератор');
    $$('[data-ui="exit"]').forEach(button=>button.title=exitHint);
    const locked = !state.connected || state.pending || state.posting || state.shutdown;
    $$('[data-action], [data-browse], [data-submit-action]').forEach(button => {button.disabled = !!locked;});
    const pendingAction=state.pending?.action || state.submission?.action;
    const progressLabels={save:t('Сохраняем…'),start:t('Проверяем и запускаем…'),health:t('Проверяем соединение…'),validate:t('Проверяем пути…'),trace:t('Читаем журнал…'),codexStatus:t('Проверяем аккаунт…'),codexCatalog:t('Обновляем модели…'),codexLogin:t('Ожидаем вход…'),codexPing:t('Проверяем аккаунт…')};
    $$('[data-action]').forEach(button=>{
      if(button.dataset.action === pendingAction && progressLabels[pendingAction]) {
        // Keep the busy icon mounted across polls so its feedback stays smooth.
        if(!button.dataset.idleHtml) {
          button.dataset.idleHtml=button.innerHTML;
          button.innerHTML=`${icon('refresh')}<span data-progress-label></span>`;
        }
        button.querySelector('[data-progress-label]').textContent=progressLabels[pendingAction];
        button.setAttribute('aria-busy','true');
      } else if(button.dataset.idleHtml) {button.innerHTML=button.dataset.idleHtml;delete button.dataset.idleHtml;i18n.localize(button);button.removeAttribute('aria-busy');}
    });
    const serverBusy = state.remote?.busy?.includes('server-action');
    $$('[data-action="start"], [data-action="stop"]').forEach(button => {button.disabled = !!(locked || serverBusy);});
    $$('[data-ui="apply-preset"], [data-ui="save-preset"], [data-ui="stop"], [data-ui="reset-sprite"], [data-ui="clear-lora"], [data-ui="clear-trace"], [data-ui="force-restart"]').forEach(button => {button.disabled = !!locked;});
    $$('[data-ui="stop"], [data-ui="force-restart"]').forEach(button=>{button.disabled=!!(locked || serverBusy);});
    $$('[data-ui="defaults-update"], [data-ui="defaults-refresh"]').forEach(button=>{button.disabled=!!locked;});
    $$('[data-action="useLora"]').forEach(button=>{button.disabled=!!locked || !value('INFINI_SDCPP_LORA_FILE').trim();});
    if ($('#utility-dialog').dataset.kind === 'defaults') $$('[data-ui="close-dialog"]', $('#utility-dialog')).forEach(button=>{button.disabled=!!(state.pending || state.posting);});
    $$('[data-action="cancelTrace"]').forEach(button=>{button.disabled=!state.connected || state.posting || state.shutdown || !(state.remote?.busy?.includes('trace') || state.pending?.action === 'trace') || !!(state.pending && state.pending.action !== 'trace');});
  }
  function toast(message,error=false) {
    if(state.suppressToast) return;
    message=t(message);
    state.notifications.push({message,error});
    if(state.notifications.length > 100) state.notifications.shift();
    if($('#notice-count')) $('#notice-count').textContent=String(state.notifications.length);
    if ($('#utility-dialog').open) {
      let feedback=$('#utility-feedback');
      if(!feedback) {feedback=document.createElement('p');feedback.id='utility-feedback';feedback.className='dialog-feedback';feedback.setAttribute('role','status');$('#utility-body').append(feedback);}
      feedback.textContent=message;feedback.classList.toggle('is-error',error);
    }
    const div = document.createElement('div'); div.setAttribute('role',error ? 'alert':'status'); div.className = `toast${error ? ' error':''}`;
    div.innerHTML = `${icon(error ? 'alert':'check')}<span class="toast-copy">${esc(message)}</span><button aria-label="${t("Закрыть уведомление")}">×</button>`;
    div.querySelector('button').onclick = () => div.remove(); $('#toasts').replaceChildren(div);
    if (!error) setTimeout(() => div.remove(),9000);
  }
  function heading(page) {
    const [,,title,subtitle] = routes[page].map(text => t(text));
    return `<div class="page-heading${page === 'operate' ? ' operate-heading':''}"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-note"><span class="draft-indicator" aria-hidden="true"></span><span data-draft-status>${draftStatusText()}</span></div></div>`;
  }
  function basename(path) { return String(path || '').split(/[\\/]/).pop() || ''; }
  function chosen(key,fallback=t('Не задано')) { return String(value(key) || fallback); }
  function addressLabel(address,fallback=t('Адрес не задан')) {
    if (!address) return fallback;
    try { const url=new URL(address);return `${url.hostname}${url.port ? `:${url.port}`:''}${url.pathname === '/' ? '' : url.pathname}`; }
    catch { return t('Проверь формат адреса'); }
  }
  function providerSummary() {
    const provider = value('INFINI_LLM_PROVIDER','local');
    if (value('INFINI_USE_LLM') === '0') return {name:t('Текстовая модель выключена'),detail:t('Технический режим')};
    const modelKey = {local:'INFINI_LMSTUDIO_MODEL',openrouter:'INFINI_OPENROUTER_MODEL',openai_compat:'INFINI_OPENAI_COMPAT_MODEL',openai_codex:'INFINI_CODEX_LLM_MODEL'}[provider];
    const model = value(modelKey).trim();
    return {name:t(optionNames.INFINI_LLM_PROVIDER[provider]) || provider,detail:!model ? provider === 'local' ? t('auto · выбор на сервере'):t('Модель не выбрана') : model === 'auto' && provider === 'local' ? t('auto · выбор на сервере'):model};
  }
  function imageSummary() {
    const backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    const modelKey = {sdcpp:'INFINI_SDCPP_MODEL',image_api:'INFINI_IMAGE_API_MODEL',openai_codex:'INFINI_CODEX_IMAGE_MODEL'}[backend];
    const model = backend === 'sdcpp' ? basename(value(modelKey)):value(modelKey).trim();
    if (backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1') return {name:t('sd.cpp · внешний сервер'),detail:addressLabel(value('INFINI_SDCPP_SERVER_URL'))};
    if (backend === 'a1111' || backend === 'comfyui') return {name:t(optionNames.INFINI_IMAGE_BACKEND[backend]),detail:addressLabel(value(backend === 'a1111' ? 'INFINI_A1111_URL':'INFINI_COMFYUI_URL'))};
    return {name:t(optionNames.INFINI_IMAGE_BACKEND[backend]) || backend,detail:backend === 'off' ? t('Генерация рисунка отключена'):model || t('Модель не указана')};
  }
  function sourceSize() {
    const backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    if (backend === 'off') return t('Отключено');
    if (backend === 'sdcpp') return `${chosen('INFINI_SDCPP_WIDTH','—')} × ${chosen('INFINI_SDCPP_HEIGHT','—')}`;
    if (backend === 'openai_codex') return chosen('INFINI_CODEX_IMAGE_SIZE','auto');
    if (backend === 'image_api') return chosen('INFINI_IMAGE_API_SIZE',t('На стороне API'));
    return t('На стороне источника');
  }
  function spriteSummary() {
    const off=value('INFINI_IMAGE_BACKEND') === 'off',transparent=value('INFINI_BG_COLOR') === 'transparent';
    const background=transparent ? 'Native alpha' : value('INFINI_REMOVE_BG') === '0' ? t('Фон сохраняется'):'Chroma key';
    const colors=value('INFINI_PIXEL_POSTERIZE') === '1' ? t("До {0} цветов", chosen('INFINI_MAX_COLORS','—')):t('Без ограничения цветов');
    return {name:off ? t('Обработка отключена'):t("{0} · холст {1} px", chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase(), chosen('INFINI_SPRITE_MASTER_CANVAS','—')),detail:off ? t('Изображения выключены'):`${background} · ${colors.toLocaleLowerCase()}`,background,colors};
  }
  function healthSummary() {
    const home=state.remote?.home || {},raw=state.remote?.activity || '';
    const match=/Сервер отвечает|Идёт генерация/.test(home.state || '') && !state.remote?.busy?.includes('server-action') ? raw.match(/active=(\d+), waiting=(\d+), accepting=(True|False)/) : null;
    return {known:!!match,acceptingRequests:match ? match[3] === 'True' : null,active:match ? match[1]:'—',waiting:match ? match[2]:'—',accepting:match ? match[3] === 'True' ? t('Открыт'):t('Закрыт'):'—'};
  }
  function configStatus() {
    if (state.dirty.size || state.lan !== state.baselineLan) return {title:t('Есть несохранённые изменения'),detail:t('Сводки настроек показывают черновик этой вкладки.'),tone:'draft'};
    const applied=state.remote?.appliedConfig || '';
    if (/restart|mismatch|differs/i.test(applied)) return {title:t('Нужен безопасный перезапуск'),detail:t('Последняя проверка обнаружила расхождение настроек с генератором.'),tone:'attention'};
    if (/matches/i.test(applied)) return {title:t('Проверенные параметры совпадают'),detail:t('По последней проверке. Ключи и дополнительные модели не проверены.'),tone:'saved'};
    return {title:t('Настройки сервера не сверены'),detail:t('Проверка соединения сравнит доступные параметры с сохранённым файлом.'),tone:'unknown'};
  }
  function nextStep() {
    if (state.dirty.size || state.lan !== state.baselineLan) return {title:t('Сохрани изменения'),description:t('Черновик ещё не записан в config.env.'),route:'configure',link:t('Открыть конфигурацию')};
    if(configStatus().tone === 'attention') return {title:t('Примени сохранённые настройки'),description:t('Используй безопасный перезапуск в панели генератора.'),route:'diagnostics',link:t('Посмотреть состояние')};
    if(healthSummary().acceptingRequests === false) return {title:t('Приём запросов закрыт'),description:t('Посмотри состояние генератора перед следующим крафтом.'),route:'diagnostics',link:t('Открыть диагностику')};
    if (/Сервер отвечает|Идёт генерация/.test(state.remote?.home?.state || '')) return {title:t('Можно вернуться в Terraria'),description:t('Новые предметы создаются в игре с модом InfiniCrafterLocal.'),route:'help',link:t('Как начать крафт')};
    return {title:t('Проверь соединение'),description:t('Получи состояние сохранённого или запущенного этой студией генератора.'),route:'diagnostics',link:t('Открыть диагностику')};
  }
  function configurationGaps() {
    const gaps=[],provider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp'),textEnabled=value('INFINI_USE_LLM') !== '0';
    if(value('INFINI_USE_LLM') === '0') gaps.push({title:t('Текстовая модель выключена'),detail:t('Включить генерацию игровой механики'),key:'INFINI_USE_LLM'});
    if(textEnabled && provider === 'local' && !value('INFINI_LMSTUDIO_URL').trim()) gaps.push({title:t('Не указан адрес LM Studio'),detail:t('Добавить адрес текстового сервера'),key:'INFINI_LMSTUDIO_URL'});
    if(textEnabled && provider === 'openrouter' && !value('INFINI_OPENROUTER_API_KEY').trim()) gaps.push({title:t('Нет ключа OpenRouter'),detail:t('Подключить выбранный источник'),key:'INFINI_OPENROUTER_API_KEY'});
    if(textEnabled && provider === 'openai_compat' && !value('INFINI_OPENAI_COMPAT_BASE_URL').trim()) gaps.push({title:t('Не указан адрес API'),detail:t('Настроить источник текста'),key:'INFINI_OPENAI_COMPAT_BASE_URL'});
    if(textEnabled && provider === 'openai_codex' && !value('INFINI_CODEX_LLM_MODEL').trim()) gaps.push({title:t('Не выбрана текстовая модель'),detail:t('Указать модель Codex'),key:'INFINI_CODEX_LLM_MODEL'});
    if((textEnabled && provider === 'openai_codex' || backend === 'openai_codex') && !state.remote?.account?.authenticated) gaps.push({title:t('Нужен вход в Codex'),detail:t('Открыть настройки аккаунта'),key:textEnabled && provider === 'openai_codex' ? 'INFINI_CODEX_LLM_MODEL':'INFINI_CODEX_IMAGE_MODEL'});
    if(backend === 'sdcpp') {
      if(value('INFINI_SDCPP_SERVER_AUTOSTART') === '1') {
        if(!value('INFINI_SDCPP_SERVER_EXE')) gaps.push({title:t('Не выбрана программа sd.cpp'),detail:t('Указать путь к sd-server'),key:'INFINI_SDCPP_SERVER_EXE'});
        if(!value('INFINI_SDCPP_MODEL')) gaps.push({title:t('Не выбрана модель изображения'),detail:t('Указать файл локальных весов'),key:'INFINI_SDCPP_MODEL'});
      } else if(!value('INFINI_SDCPP_SERVER_URL')) gaps.push({title:t('Не указан адрес sd.cpp'),detail:t('Подключить внешний сервер изображений'),key:'INFINI_SDCPP_SERVER_URL'});
    }
    if(backend === 'image_api' && !value('INFINI_IMAGE_API_BASE_URL')) gaps.push({title:t('Не указан адрес Image API'),detail:t('Настроить источник изображений'),key:'INFINI_IMAGE_API_BASE_URL'});
    return gaps;
  }
  function flowCards() {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary();
    const textProvider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    const textMeta=textProvider === 'openai_codex' ? `Effort: ${chosen('INFINI_LLM_REASONING_MODE','off')}` : t("{0} токенов · t {1}", chosen('INFINI_LLM_MAX_TOKENS','—'), chosen('INFINI_LLM_TEMPERATURE','—'));
    const imageMeta=backend === 'sdcpp' ? t("{0} px · {1} шага", sourceSize(), chosen('INFINI_SDCPP_STEPS','—')) : backend === 'off' ? t('Изображения выключены'):sourceSize();
    return `<ol class="pipeline-list">${[
      ['01',t('Текст и механика'),provider.name,provider.detail,textMeta,'providers','text'],
      ['02',t('Исходное изображение'),image.name,image.detail,imageMeta,'images','image'],
      ['03',t('Обработка спрайта'),sprite.name,sprite.detail,value('INFINI_IMAGE_BACKEND') === 'off' ? t('Настройки сохранены'):t("Фон: {0}", t(optionNames.INFINI_BG_COLOR[value('INFINI_BG_COLOR')]) || chosen('INFINI_BG_COLOR')),'sprites','pixel']
    ].map(([number,title,name,detail,meta,route,glyph]) => `<li><a class="pipeline-step flow-card" href="#${route}" data-flow-card><div class="flow-card-top"><span class="flow-index">${number}</span><span class="flow-title">${icon(glyph)}${title}</span><span class="step-arrow">${icon('arrow')}</span></div><h3>${esc(name)}</h3><p class="flow-detail">${esc(detail)}</p><div class="flow-card-meta">${esc(meta)}</div></a></li>`).join('')}</ol>`;
  }
  function homeActivity() {
    const health=healthSummary();
    return `<div class="server-readout">${[[t('Активных крафтов'),health.active],[t('В очереди'),health.waiting],[t('Приём запросов'),health.accepting]].map(([label,val])=>`<div><span>${label}</span><strong>${val}</strong></div>`).join('')}</div><p class="readout-note">${health.known ? t('Последний ответ генератора. Обновляется при проверке соединения.'):t('Состояние очереди появится после проверки соединения.')}</p>`;
  }
  function serviceConnections() {
    const provider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    const textSource=providerSummary(),imageSource=imageSummary();
    const textAddress=provider === 'local' ? addressLabel(value('INFINI_LMSTUDIO_URL')) : provider === 'openai_compat' ? addressLabel(value('INFINI_OPENAI_COMPAT_BASE_URL')) : provider === 'openai_codex' ? state.remote.account?.authenticated ? t('Вход выполнен'):t('Нужен вход') : value('INFINI_OPENROUTER_API_KEY').trim() ? t('Ключ указан'):t('Ключ не указан');
    const imageAddress=backend === 'sdcpp' ? addressLabel(value('INFINI_SDCPP_SERVER_URL')) : backend === 'image_api' ? addressLabel(value('INFINI_IMAGE_API_BASE_URL')) : imageSource.detail;
    return `<div class="service-list"><a href="#providers" class="service-item"><span class="service-icon">${icon('text')}</span><div><strong>${esc(textSource.name)}</strong><span>${esc(textAddress)}</span><small>${provider === 'local' ? t('Запускается отдельно'):t('Внешний сервис')}</small></div>${icon('arrow')}</a><a href="#images" class="service-item"><span class="service-icon">${icon('image')}</span><div><strong>${esc(imageSource.name)}</strong><span>${esc(imageAddress)}</span><small>${backend === 'sdcpp' ? value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? t('Запускает генератор'):t('Запускается отдельно') : backend === 'off' ? t('Запросы изображений отключены'):t('Внешний сервис')}</small></div>${icon('arrow')}</a></div>`;
  }
  function renderOperate() {
    if (!state.remote || state.page !== 'operate') return;
    const home=state.remote.home || {},next=nextStep(),gaps=configurationGaps(),config=configStatus(),health=healthSummary();
    const busy=state.remote.busy?.includes('server-action'),running=/Сервер отвечает|Идёт генерация/.test(home.state || '');
    const title=busy ? t('Проверяем состояние…'):home.state || t('Состояние не проверено');
    const stationState=busy ? 'busy':running ? 'running':/внимание|подтверждено/.test(title) ? 'attention':'idle';
    const detail=title === 'Идёт генерация' && health.known ? t('Последний снимок сервера: создаётся {0}, в очереди {1}. Для актуального состояния нажми «Проверить соединение».',health.active,health.waiting) : title === 'Сервер отвечает' ? t('Генератор отвечает. Новые предметы создаются в Terraria.') : title === 'Состояние ещё не проверено' ? t('Запусти генератор или проверь уже работающий сервер.') : home.detail || t('Запусти генератор или проверь соединение.');
    const endpoint=`${state.remote.savedValues?.INFINI_HOST || '127.0.0.1'}:${state.remote.savedValues?.INFINI_PORT || '5055'}`;
    const hasTrace=Object.values(state.remote.trace || {}).some(raw=>typeof raw === 'string' && raw.trim());
    const signature=JSON.stringify([home,state.draft,state.lan,state.dirty.size,config,busy,state.remote.activity,state.remote.account?.authenticated,endpoint,hasTrace]);
    if(state.operateSignature === signature && $('.station')) {updateActionButtons();return;}
    state.operateSignature=signature;
    const focused=document.activeElement;
    const focusIdentity=focused?.closest('#workspace') ? ['id','data-action','data-ui','data-search-key','href'].map(name=>[name,focused.getAttribute(name)]).find(([,val])=>val) : null;
    $('#workspace').innerHTML=`${heading('operate')}
      <div class="dashboard-top"><section class="station" data-state="${stationState}" aria-labelledby="generator-title">
        <div class="station-top"><span class="serial">${icon('pulse')}${t("Сервер генерации")}</span><span class="state-tag"><span class="status-dot"></span>${busy ? t('Проверка'):running ? t('На связи'):t('Не подтверждён')}</span></div>
        <div class="station-content"><h2 id="generator-title">${esc(t(title))}</h2><p class="station-detail">${esc(t(detail))}</p></div>
        <div class="endpoint">${icon('network')}<span>${esc(endpoint)}</span><small>${t("сохранённый адрес")}</small></div>
        ${homeActivity()}
        <div class="station-controls"><div class="station-buttons"><button class="button button-primary" data-action="start">${icon('play')}${running ? t('Безопасно перезапустить'):t('Запустить генератор')}<span class="start-arrow" aria-hidden="true">↗</span></button><button class="button" data-action="health" aria-label="${t("Проверить сохранённый или запущенный генератор")}">${icon('refresh')}${t("Проверить")}</button><button class="button button-small" data-ui="stop" title="${t("Безопасно остановить генератор")}">${icon('stop')}${t("Стоп")}</button></div><p class="station-caption">${t("Запуск сохранит текущие настройки. Активный крафт защищён безопасным перезапуском.")}</p></div>
      </section><section class="setup-card${gaps.length ? ' has-gaps':''}" aria-labelledby="setup-title"><div class="section-kicker">${icon(gaps.length ? 'alert':'sliders')}${t("Перед крафтом")}</div>${gaps.length ? `<h2 id="setup-title">${t("Проверь настройки")}</h2><p>${t("В текущей конфигурации есть пункты, требующие внимания.")}</p><div class="setup-list">${gaps.slice(0,3).map(gap=>`<button class="setup-item" data-search-key="${gap.key}"><span><strong>${gap.title}</strong><small>${gap.detail}</small></span>${icon('arrow')}</button>`).join('')}</div>` : `<h2 id="setup-title">${t("Сервисы генерации")}</h2>${serviceConnections()}`}
        <div class="setup-foot">${gaps.length ? t("{0}Показаны настройки этой вкладки.", icon('help')):next.route === 'help' ? `<button class="text-button" data-ui="help">${next.link}${icon('arrow')}</button>`:`<a class="text-button" href="#${next.route}">${next.link}${icon('arrow')}</a>`}</div>
      </section></div>
      <section class="pipeline" aria-labelledby="pipeline-title"><div class="section-heading"><h2 id="pipeline-title">${t("Конфигурация крафта")}</h2><a class="text-button" href="#configure">${t("Профили и все настройки")} ${icon('arrow')}</a></div>${flowCards()}<div class="pipeline-foot"><span class="profile-chip">${icon('sliders')}${esc(presetLabel(value('INFINI_GUI_PIPELINE_PRESET')))}</span><span>${state.dirty.size || state.lan !== state.baselineLan ? t('Показан черновик'):t('Показаны сохранённые настройки')}</span></div></section>
      <div class="dashboard-bottom"><a href="#multiplayer" class="utility-card" data-flow-card><span class="utility-icon">${icon('network')}</span><div><h2>${t("Соединение с игрой")}</h2><p>${state.lan ? 'LAN / Radmin':t('Этот компьютер')} · ${value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? t('Спрайты по HTTP'):t('Спрайты внутри Terraria')}</p></div>${icon('arrow')}</a><a href="#diagnostics" class="utility-card" data-flow-card><span class="utility-icon">${icon('pulse')}</span><div><h2>${t("Журнал генерации")}</h2><p>${Object.values(state.remote.trace || {}).some(raw=>typeof raw === 'string' && raw.trim()) ? t('Есть загруженные записи'):t('Промпты, этапы и ошибки последнего крафта')}</p></div>${icon('arrow')}</a></div>
      <div class="config-strip" data-config-tone="${config.tone}">${icon('sliders')}<p><strong>${config.title}.</strong> ${config.detail}</p></div>`;
    updateActionButtons();
    document.dispatchEvent(new Event('studio:render'));
    if(focusIdentity) $$('[data-action],[data-ui],[data-search-key],a', $('#workspace')).find(element=>element.getAttribute(focusIdentity[0]) === focusIdentity[1])?.focus({preventScroll:true});
  }
  function browseType(field) {
    if (field.key === 'INFINI_SDCPP_LORA_FILE') return 'lora';
    if (modelKeys.has(field.key)) return 'model';
    if (/_(DIR|ROOT)$/.test(field.key)) return 'folder';
    if (/(SERVER_EXE|LOG_FILE)$/.test(field.key)) return 'file';
    return '';
  }
  function derivedField(key) {
    if(key === 'INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK' && value('INFINI_VISUAL_STRICT_AI_AUTHORSHIP','1') === '1') return {value:t('0 · Выключено'),note:t('Строгое авторство модели принудительно выключает процедурную подмену.')};
    if(key === 'INFINI_SDCPP_LORA_DIR') {
      const file=value('INFINI_SDCPP_LORA_FILE').trim(), slash=Math.max(file.lastIndexOf('/'),file.lastIndexOf('\\'));
      const dir=!file ? t('Не задано') : slash < 0 ? '.' : slash === 0 ? file[0] : slash === 2 && file[1] === ':' ? file.slice(0,3) : file.slice(0,slash);
      return {value:dir,note:t('Вычисляется из выбранного файла LoRA при сохранении. Без файла папка очищается.')};
    }
    if(key === 'INFINI_HOST' && state.lan && value('INFINI_MP_ASSET_TRANSPORT') === 'http') return {value:'0.0.0.0',note:t('LAN с HTTP требует сетевой интерфейс. Изменить режим можно переключателем LAN выше.')};
    return null;
  }
  function fieldHTML(field,forceDetails=false) {
    const key = field.key, id = `field-${key}`, val = value(key), options = field.options || [], inactive = inactiveReason(field);
    const isBool = options.length === 2 && options.includes('1') && options.includes('0') && ['0','1'].includes(val);
    const derived=derivedField(key), browse = derived ? '' : browseType(field), help = forceDetails || state.helpFields.has(key), title = label(field);
    let control;
    if (derived) control=`<output id="${id}" data-derived="${key}" tabindex="0" aria-describedby="help-${key}">${esc(derived.value)}</output><span class="field-note">${esc(derived.note)}</span>`;
    else if (field.secret) control = `<input id="${id}" data-field="${key}" type="password" value="${esc(val)}" autocomplete="off" spellcheck="false" data-secret="true" aria-describedby="help-${key}"><button class="reveal" data-reveal="${key}" type="button" aria-label="${t("Показать ключ")}" aria-pressed="false">${icon('eye')}</button>`;
    else if (key === 'INFINI_SDCPP_SERVER_AUTOSTART') control = `<select id="${id}" data-field="${key}" aria-describedby="help-${key}"><option value="0" ${val === '0' ? 'selected':''}>${t("Внешний · уже запущен")}</option><option value="1" ${val === '1' ? 'selected':''}>${t("Управляемый · запускать здесь")}</option>${!['0','1'].includes(val) ? `<option selected value="${esc(val)}">${esc(val)}</option>`:''}</select>`;
    else if (isBool) control = `<label class="toggle-control"><input id="${id}" type="checkbox" data-field="${esc(key)}" ${val === '1' ? 'checked':''} aria-describedby="help-${key}"><span class="toggle-track"></span><span class="toggle-label">${val === '1' ? t('Включено'):t('Выключено')}</span></label>`;
    else if (field.multiline || /COMMAND_TEMPLATE|EXTRA_ARGS/.test(key)) control = `<textarea id="${id}" data-field="${key}" spellcheck="false" aria-describedby="help-${key}">${esc(val)}</textarea>`;
    else if (options.length && !/_MODEL$/.test(key)) {
      const available = [...new Set([...(options.includes(val) ? []:[val]),...options])];
      control = `<select id="${id}" data-field="${key}" aria-describedby="help-${key}">${available.map(option => `<option value="${esc(option)}" ${option === val ? 'selected':''}>${esc(t(optionNames[key]?.[option]) || option || t('Не задано'))}</option>`).join('')}</select>`;
    } else {
      control = `<input id="${id}" data-field="${key}" type="${field.secret ? 'password':'text'}" value="${esc(val)}" autocomplete="off" spellcheck="false" ${field.secret ? 'data-secret="true"':''} ${options.length ? `list="options-${key}"`:''} aria-describedby="help-${key}">${options.length ? `<datalist id="options-${key}">${options.map(option => `<option value="${esc(option)}"></option>`).join('')}</datalist>`:''}`;
      if (field.secret) control += `<button class="reveal" data-reveal="${key}" type="button" aria-label="${t("Показать ключ")}" aria-pressed="false">${icon('eye')}</button>`;
      if (browse && !field.synthetic) control += `<button class="browse" data-browse="${key}" data-browse-type="${browse}" type="button" title="${t("Выбрать на этом компьютере")}" aria-label="${t("Выбрать файл:")} ${esc(title)}">${icon('folder')}</button>`;
    }
    if (key === 'INFINI_SDCPP_SERVER_EXE') control += `<span class="field-note"><a class="text-button" href="https://github.com/leejet/stable-diffusion.cpp/releases/latest" target="_blank" rel="noopener noreferrer" title="${t('Официальные сборки sd.cpp на GitHub')}">${t('Скачать sd.cpp')} ${icon('arrow')}</a></span>`;
    return `<div class="field-row${state.dirty.has(key) ? ' is-dirty':''}" data-field-row="${key}"><div class="field-copy"><div class="field-label-line"><label for="${id}">${esc(title)}</label><button class="field-help-toggle" data-help-field="${key}" type="button" aria-label="${t("Подробности:")} ${esc(title)}" aria-expanded="${help}">?</button></div><div class="field-key${help ? '':' hidden-key'}">${key}</div><p class="field-help" id="help-${key}">${esc(t(help ? field.help || shortHelp[key] || t('Параметр локального генератора. Значение сохраняется без преобразования.') : shortHelp[key] || ''))}</p>${browse && !field.secret ? `<span class="field-file" data-file-basename="${key}" title="${esc(val)}" ${val.trim() ? '':'hidden'}>${esc(basename(val))}</span>`:''}</div><div class="field-control${field.secret || browse ? ' has-extra':''}">${control}${inactive && !derived ? `<span class="field-note" data-inactive-source>${esc(inactive)}</span>`:''}</div></div>`;
  }
  function disclosure(id,title,fields,reason='',force=false) {
    if (!fields.length) return '';
    const open = state.openDetails.has(id) || force;
    return `<details class="advanced" data-details="${id}" ${open ? 'open':''}><summary>${esc(title)}<span class="meta">${fields.length}</span></summary>${reason ? `<p class="details-note">${esc(reason)}</p>`:''}<div class="section-fields">${fields.map(field => fieldHTML(field,force)).join('')}</div></details>`;
  }
  const sectionDefinitions = {
    providers:[
      ['source','Источник и модель','Откуда генератор получает игровую механику.',['INFINI_USE_LLM','INFINI_LLM_PROVIDER','INFINI_LMSTUDIO_URL','INFINI_LMSTUDIO_MODEL','INFINI_OPENROUTER_API_KEY','INFINI_OPENROUTER_MODEL','INFINI_OPENROUTER_PROVIDER','INFINI_OPENAI_COMPAT_BASE_URL','INFINI_OPENAI_COMPAT_API_KEY','INFINI_OPENAI_COMPAT_MODEL','INFINI_CODEX_LLM_MODEL']],
      ['response','Ответ модели','Рассуждение, лимиты и художественное направление.',['INFINI_LLM_REASONING_MODE','INFINI_LLM_TEMPERATURE','INFINI_LLM_MAX_TOKENS','INFINI_LLM_TIMEOUT','INFINI_PROMPT_STYLE']]
    ],
    images:[
      ['source','Источник и подключение','Выбранный движок и способ его запуска.',['INFINI_IMAGE_BACKEND','INFINI_SDCPP_SERVER_AUTOSTART','INFINI_SDCPP_SERVER_URL','INFINI_CODEX_IMAGE_MODEL','INFINI_IMAGE_API_BASE_URL','INFINI_IMAGE_API_KEY','INFINI_IMAGE_API_MODEL','INFINI_IMAGE_API_PATH','INFINI_A1111_URL','INFINI_COMFYUI_URL']],
      ['image','Исходное изображение','Размер рисунка до обработки в спрайт.',['INFINI_SDCPP_WIDTH','INFINI_SDCPP_HEIGHT','INFINI_SDCPP_STEPS','INFINI_SDCPP_CFG','INFINI_SDCPP_SAMPLER','INFINI_SDCPP_SEED','INFINI_CODEX_IMAGE_SIZE','INFINI_CODEX_IMAGE_QUALITY','INFINI_IMAGE_API_SIZE']],
      ['queue','Очередь и ожидание','Нагрузка на источник изображений.',['INFINI_IMAGE_PARALLEL','INFINI_IMAGE_MAX_CONCURRENCY','INFINI_CODEX_IMAGE_TIMEOUT','INFINI_IMAGE_API_TIMEOUT']]
    ],
    sprites:[
      ['background','Фон и прозрачность','Как фон исходника превращается в прозрачность.',['INFINI_BG_COLOR','INFINI_REMOVE_BG','INFINI_BG_REMOVE_MODE','INFINI_CHROMA_TOLERANCE','INFINI_ALPHA_THRESHOLD']],
      ['resize','Размер и уменьшение','Промежуточный холст и фильтр обработки.',['INFINI_SPRITE_MASTER_CANVAS','INFINI_SPRITE_DOWNSCALE_FILTER','INFINI_SPRITE_PREMULTIPLIED_RESIZE']],
      ['palette','Палитра','Ограничение количества цветов готового изображения.',['INFINI_PIXEL_POSTERIZE','INFINI_MAX_COLORS']],
      ['assets','Состав визуальных ассетов','Спрайт предмета и дополнительные визуальные эффекты.',['INFINI_VISUAL_ASSET_MODE','INFINI_VISUAL_DIRECTOR_LLM','INFINI_VFX_LLM_DIRECTOR']]
    ],
    models:[
      ['runtime','Программа sd.cpp','Используется при управляемом запуске.',['INFINI_SDCPP_SERVER_EXE','INFINI_SDCPP_ROCM_COMPAT_ROOT']],
      ['weights','Основные модели','Диффузионная модель, декодер и текстовый энкодер.',['INFINI_SDCPP_MODEL','INFINI_SDCPP_VAE','INFINI_SDCPP_LLM']],
      ['lora','Художественный адаптер · LoRA','Необязательный адаптер для выбранной модели.',['INFINI_SDCPP_LORA_FILE','INFINI_SDCPP_LORA_WEIGHT','INFINI_SDCPP_LORA_PROMPT_TAGS','INFINI_SDCPP_LORA_DIR']]
    ],
    multiplayer:[
      ['connection','Адрес генератора','Интерфейс и порт, к которому обращается мод.',['INFINI_HOST','INFINI_PORT']],
      ['delivery','Доставка спрайтов','Как другие игроки получают изображения предметов.',['INFINI_MP_ASSET_TRANSPORT','INFINI_ASSET_PUBLIC_BASE_URL']],
      ['terraria','Сервер Terraria','Порт игрового сервера.',['INFINI_TERRARIA_PORT']],
      ['requests','Запросы крафта','Время ожидания, повторные попытки и очередь.',['INFINI_CRAFT_HTTP_TIMEOUT_SECONDS','INFINI_CRAFT_HTTP_ATTEMPTS','INFINI_COMBINE_BUSY_WAIT_SECONDS']]
    ]
  };
  function pageSections(page,fields) {
    return (sectionDefinitions[page] || []).map(([id,title,description,keys])=>({id,title:t(title),description:t(description),fields:keys.map(key=>fields.find(field=>field.key === key)).filter(field=>field && (page === 'models' || !inactiveReason(field)))})).filter(section=>section.fields.length);
  }
  function fieldGroups(fields,force=false) {
    if(!fields.length) return `<div class="empty-search">${t("В этом разделе ничего не найдено. Попробуй другое слово.")}</div>`;
    if(force) return `<div class="section-fields search-field-results">${fields.map(field=>fieldHTML(field,true)).join('')}</div>`;
    const sections=pageSections(state.page,fields),used=new Set(sections.flatMap(section=>section.fields.map(field=>field.key)));
    const remaining=fields.filter(field=>!used.has(field.key));
    const active=remaining.filter(field=>!inactiveReason(field)),inactive=remaining.filter(field=>inactiveReason(field));
    const pools=[2,3,4].map(number=>active.filter(field=>field.key.startsWith(`INFINI_LLM_POOL_${number}_`)));
    const fallback=active.filter(field=>field.key.startsWith('INFINI_LLM_FALLBACK_'));
    const advanced=active.filter(field=>!pools.flat().includes(field) && !fallback.includes(field));
    return sections.map((section,index)=>`<section class="parameter-section" data-inactive-section="${state.page === 'models' && section.fields.every(field=>inactiveReason(field))}" aria-labelledby="section-${state.page}-${section.id}"><header class="parameter-heading"><span class="section-number">${String(index+1).padStart(2,'0')}</span><div><h2 id="section-${state.page}-${section.id}" tabindex="-1">${section.title}</h2><p>${section.description}${state.page === 'models' && section.fields.every(field=>inactiveReason(field)) ? `<span class="section-inactive-label">${t("Сохранено · не используется в текущем режиме")}</span>`:''}</p></div></header><div class="section-fields">${section.fields.map(field=>fieldHTML(field)).join('')}</div>${state.page === 'models' && section.id === 'lora' ? `<div class="section-actions"><button class="button" data-action="useLora">${t("Применить выбранную LoRA")} ${icon('arrow')}</button><button class="text-button" data-ui="clear-lora">${t("Отключить LoRA")}</button><p>${t("Отключение сбросит настройки адаптера. Файл на диске останется.")}</p></div>`:''}</section>`).join('')+
      pools.map((group,index)=>disclosure(`pool-${index+2}`,t("Дополнительная линия {0} · {1}", index+2, value(`INFINI_LLM_POOL_${index+2}_ENABLED`) === '1' ? t('включена'):t('выключена')),group,t('Собственный источник, адрес и модель для дополнительной линии.'))).join('')+
      disclosure(`${state.page}-fallback`,t('Резервный источник'),fallback,t('Используется при настроенных условиях переключения.'))+
      disclosure(`${state.page}-advanced`,t('Тонкая настройка'),advanced,t('Дополнительные параметры текущего источника.'))+
      disclosure(`${state.page}-inactive`,t('Другие источники и неактивные параметры'),inactive,t('Значения доступны для редактирования. Причина неактивности указана у каждого поля.'));
  }
  function summaryMetric(label,val,detail,glyph,extra='') {
    return `<div class="summary-metric${extra}"><span class="summary-label">${icon(glyph)}${esc(label)}</span><strong>${esc(val)}</strong><p>${esc(detail)}</p></div>`;
  }
  function pageOverview(page) {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary(),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    let metrics='';
    if(page === 'providers') {
      const count=[2,3,4].filter(n=>value(`INFINI_LLM_POOL_${n}_ENABLED`) === '1').length;
      metrics=summaryMetric(provider.name,provider.detail,value('INFINI_USE_LLM') === '0' ? t('Текстовая генерация выключена'):t('Выбранная текстовая модель'),'text',' summary-primary')+
        summaryMetric(t('Рассуждение'),t(optionNames.INFINI_LLM_REASONING_MODE[value('INFINI_LLM_REASONING_MODE')]) || chosen('INFINI_LLM_REASONING_MODE'),t("Ожидание стадии: {0} с", chosen('INFINI_LLM_TIMEOUT','—')),'sliders')+
        summaryMetric(t('Дополнительные линии'),count ? t("Включено: {0}", count):t('Выключены'),count ? t('Собственные источники и модели'):t('Настроена только основная линия'),'stack');
    } else if(page === 'images') {
      metrics=summaryMetric(t('Источник изображения'),image.name,image.detail,'image',' summary-primary')+
        summaryMetric(t('Размер исходника'),sourceSize(),backend === 'off' ? t('Генерация рисунка отключена'):t('До удаления фона и уменьшения'),'expand')+
        summaryMetric(backend === 'sdcpp' ? t('Параметры sd.cpp'):t('Качество и очередь'),backend === 'sdcpp' ? t("{0} шага", chosen('INFINI_SDCPP_STEPS','—')) : backend === 'openai_codex' ? t(optionNames.INFINI_CODEX_IMAGE_QUALITY[value('INFINI_CODEX_IMAGE_QUALITY')]) || chosen('INFINI_CODEX_IMAGE_QUALITY') : backend === 'off' ? t('Отключено'):value('INFINI_IMAGE_PARALLEL') === '0' ? t('Последовательно'):t("{0} параллельно", chosen('INFINI_IMAGE_MAX_CONCURRENCY','—')),backend === 'sdcpp' ? `CFG ${chosen('INFINI_SDCPP_CFG','—')} · ${chosen('INFINI_SDCPP_SAMPLER')}`:backend === 'off' ? t('Настройки обработки сохранены'):t("Лимит изображений: {0}", value('INFINI_IMAGE_PARALLEL') === '0' ? '1':chosen('INFINI_IMAGE_MAX_CONCURRENCY','—')),'sliders');
    } else if(page === 'sprites') {
      metrics=backend === 'off' ? summaryMetric(t('Обработка изображения'),t('Не используется'),t('Источник изображений выключен'),'image',' summary-primary')+summaryMetric(t('Промежуточный холст'),t('Не используется'),t("Сохранено: {0} px · {1}", chosen('INFINI_SPRITE_MASTER_CANVAS','—'), chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()),'pixel')+summaryMetric(t('Палитра'),t('Не используется'),t("Сохранено: {0}", sprite.colors.toLocaleLowerCase()),'sliders') :
        summaryMetric(t('Фон исходника'),sprite.background,t(optionNames.INFINI_BG_COLOR[value('INFINI_BG_COLOR')]) || chosen('INFINI_BG_COLOR'),'image',' summary-primary')+
        summaryMetric(t('Промежуточный холст'),`${chosen('INFINI_SPRITE_MASTER_CANVAS','—')} px`,`${chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()} · ${value('INFINI_SPRITE_PREMULTIPLIED_RESIZE') === '1' ? t('с учётом прозрачности'):t('обычное уменьшение')}`,'pixel')+
        summaryMetric(t('Палитра'),sprite.colors,value('INFINI_PIXEL_POSTERIZE') === '1' ? t('Постеризация включена'):t('Исходные цвета сохраняются'),'sliders');
    } else if(page === 'models') {
      const managed=backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') === '1',lora=basename(value('INFINI_SDCPP_LORA_FILE'));
      metrics=summaryMetric(t('Управление моделями'),managed ? t('Из этой студии'):backend === 'sdcpp' ? t('Внешний sd.cpp'):t('Другой источник'),managed ? basename(value('INFINI_SDCPP_MODEL')) || t('Основная модель не указана'):backend === 'sdcpp' ? t('Основные веса выбирает сервер'):image.name,'stack',' summary-primary')+
        summaryMetric(t('Адаптер LoRA'),backend !== 'sdcpp' ? t('Не используется'):lora || t('Не выбран'),backend !== 'sdcpp' ? lora ? t("Сохранено: {0}", lora):t('sd.cpp не используется') : lora ? t("Сила: {0}", chosen('INFINI_SDCPP_LORA_WEIGHT','—')):t('Без художественного адаптера'),'sliders')+
        summaryMetric(t('Сервер изображений'),backend === 'sdcpp' ? addressLabel(value('INFINI_SDCPP_SERVER_URL')):image.name,t('Выбор источника — в разделе «Изображения»'),'network');
    } else if(page === 'multiplayer') {
      const host=derivedField('INFINI_HOST')?.value || chosen('INFINI_HOST','127.0.0.1');
      metrics=summaryMetric(state.lan ? t('Режим LAN / Radmin'):t('Интерфейс генератора'),`${host}:${chosen('INFINI_PORT','5055')}`,t('Адрес из текущих настроек'),'network',' summary-primary')+
        summaryMetric(t('Доставка спрайтов'),value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? t('По HTTP'):t('Внутри Terraria'),value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? state.lan ? addressLabel(value('INFINI_ASSET_PUBLIC_BASE_URL'),t('Публичный адрес не задан')):t('Публичный адрес не используется: LAN выключен'):t('Без отдельного HTTP-адреса для ассетов'),'image')+
        summaryMetric(t('Порт Terraria'),chosen('INFINI_TERRARIA_PORT','7777'),t('Порт игрового сервера'),'work');
    } else if(page === 'diagnostics') {
      const health=healthSummary(),config=configStatus();
      metrics=summaryMetric(t('Генератор'),t(state.remote.home?.state) || t('Не проверен'),t("{0}:{1} · сохранённый адрес", state.remote.savedValues?.INFINI_HOST || '127.0.0.1', state.remote.savedValues?.INFINI_PORT || '5055'),'pulse',' summary-primary')+
        summaryMetric(t('Последняя проверка'),health.known ? t("{0} активных · {1} в очереди", health.active, health.waiting):t('Нет данных'),health.known ? t("Приём запросов: {0}", health.accepting.toLocaleLowerCase()):t('Нажми «Проверить соединение»'),'refresh')+
        summaryMetric(t('Конфигурация'),config.title,config.detail,'sliders');
    }
    return metrics ? `<div class="page-summary${page === 'sprites' ? ' sprite-summary':''}">${metrics}</div>`:'';
  }
  function updatePageOverview() {
    if(state.page === 'configure') updateConfigureSummary();
    $$('[data-file-basename]').forEach(element=>{const path=value(element.dataset.fileBasename);element.textContent=basename(path);element.title=path;element.hidden=!path.trim();});
    const overview=$('#page-overview');
    if(!overview) return;
    const markup=pageOverview(state.page);
    if(overview._studioSignature !== markup) {overview.innerHTML=markup;overview._studioSignature=markup;}
  }
  function aside(page=state.page) {
    const sections=state.filter ? []:pageSections(page,state.fields.filter(field=>field.route === page));
    const related={configure:['operate',t('Проверить генератор')],providers:['images',t('Источник изображения')],images:['models',t('Файлы моделей и LoRA')],sprites:['images',t('Параметры исходника')],models:['images',t('Способ запуска sd.cpp')],multiplayer:['diagnostics',t('Проверить соединение')],diagnostics:['multiplayer',t('Настроить адрес')]}[page];
    const total=state.dirty.size+Number(state.lan !== state.baselineLan);
    return `<aside class="settings-aside">${sections.length ? `<nav class="section-nav" aria-label="${t("Разделы этой страницы")}"><h2>${t("На этой странице")}</h2>${sections.map((section,index)=>`<button data-section-link="section-${page}-${section.id}"><span>${String(index+1).padStart(2,'0')}</span>${section.title}</button>`).join('')}</nav>`:''}${related ? `<a class="related-page" href="#${related[0]}"><span>${t("Связанный раздел")}<strong>${related[1]}</strong></span>${icon('arrow')}</a>`:''}<div class="save-panel${total ? ' is-dirty':''}"><div class="aside-heading"><h2>${icon('save')}${t("Конфигурация")}</h2></div><strong data-dirty-count>${total ? t("{0} несохранённых изменений", total):t('Изменений нет')}</strong><p>${t("Сохрани настройки перед перезапуском генератора.")}</p><button class="button" data-action="save">${t("Сохранить")} <kbd>Ctrl S</kbd></button></div><details class="config-file"><summary>${icon('folder')}${t("Файл настроек")}</summary><code>${esc(state.remote.configPath || 'config.env')}</code><button class="text-button" data-action="openConfig">${t("Открыть файл")} ${icon('arrow')}</button></details></aside>`;
  }
  function defaultsSummary() {
    const offer=state.remote?.defaultsUpdate,count=offer?.changes?.length || 0;
    if(!count) return t('Новых рекомендаций нет.');
    if(offer.dismissed) return t("Рекомендации {0} отложены. Доступны для сравнения.", offer.version || '');
    return t("Доступно {0} рекомендаций {1}. Сравни изменения перед применением.", count, offer.version || '');
  }
  function configureSummaryCards() {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary();
    return [
      ['text','providers',t('Текст и механика'),provider.name,provider.detail],
      ['image','images',t('Источник изображения'),image.name,image.detail],
      ['pixel','sprites',t('Спрайты и цвет'),sprite.name,sprite.detail],
      ['stack','models',t('Модели и LoRA'),value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? t('sd.cpp не используется'):basename(value('INFINI_SDCPP_LORA_FILE')) || t('LoRA не выбрана'),value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? t("Текущий источник: {0}", image.name):value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? t('Управляемый запуск sd.cpp'):t('Основные модели выбирает внешний sd.cpp')],
      ['network','multiplayer',t('Совместная игра'),state.lan ? 'LAN / Radmin':t('Этот компьютер'),value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? t('Доставка спрайтов по HTTP'):t('Доставка спрайтов внутри Terraria')],
      ['pulse','diagnostics',t('Диагностика'),value('INFINI_TRACE_PROMPTS') === '1' ? t('Запись промптов включена'):t('Запись промптов выключена'),t("Лимит просмотра: {0} событий", chosen('INFINI_TRACE_EVENTS_TAIL','—'))]
    ];
  }
  function updateConfigureSummary() {
    const profile=$('#current-profile-name');if(profile) profile.textContent=presetLabel(value('INFINI_GUI_PIPELINE_PRESET'));
    const label=$('#configure-selection-status');if(label) label.textContent=state.dirty.size || state.lan !== state.baselineLan ? t('Черновик этой вкладки'):t('Сохранённая конфигурация');
    for(const [,route,,summary,detail] of configureSummaryCards()) {
      const main=$(`[data-config-value="${route}"]`),copy=$(`[data-config-detail="${route}"]`);
      if(main) main.textContent=summary;if(copy) copy.textContent=detail;
    }
  }
  function presetLabel(name) {
    if(!name || name === 'Custom') return t('Свои настройки');
    if(name.startsWith('Мой: ')) return t('Мой: {0}',name.slice(5));
    return Object.hasOwn(state.remote?.presets || {},name) ? t(name) : name;
  }
  function renderConfigure() {
    const selected=state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    const presetEntries=[...Object.keys(state.remote.presets || {}),...Object.keys(state.remote.userPresets || {}).map(name=>`Мой: ${name}`)];
    const cards=configureSummaryCards();
    $('#workspace').innerHTML=`${heading('configure')}<div class="settings-layout"><div class="settings-main"><section class="preset-sheet profile-sheet"><div class="profile-heading"><span class="profile-symbol">${icon('sliders')}</span><div><span class="eyebrow">${t("Текущая конфигурация")}</span><h2 id="current-profile-name">${esc(presetLabel(value('INFINI_GUI_PIPELINE_PRESET')))}</h2></div></div><div class="preset-selector"><select id="preset-select" aria-label="${t("Профиль настроек")}"><option value="">${t("Выбери профиль…")}</option>${presetEntries.map(name=>`<option value="${esc(name)}" ${name === selected ? 'selected':''}>${esc(presetLabel(name))}</option>`).join('')}</select><button class="button" data-ui="apply-preset">${t("Сравнить и применить")} ${icon('arrow')}</button></div><div class="profile-foot"><p>${t("Применение профиля меняет черновик. Ключи остаются твоими.")}</p><button class="text-button" data-ui="save-preset">${t("Сохранить как профиль")} ${icon('save')}</button></div></section><div class="section-heading"><h2>${t("Что настроено сейчас")}</h2><span class="meta" id="configure-selection-status">${state.dirty.size || state.lan !== state.baselineLan ? t('Черновик этой вкладки'):t('Сохранённая конфигурация')}</span></div><div class="configure-index">${cards.map(([glyph,route,title,summary,detail])=>`<a class="index-row" href="#${route}" data-flow-card><div class="index-card-top"><span class="index-number">${icon(glyph)}</span><h3>${title}</h3>${icon('arrow')}</div><strong data-config-value="${route}">${esc(summary)}</strong><p data-config-detail="${route}">${esc(detail)}</p></a>`).join('')}</div><section class="recommendation-row"><span class="recommendation-icon">${icon('refresh')}</span><div><h2>${t("Рекомендации к настройкам")}</h2><p id="defaults-summary">${esc(defaultsSummary())}</p></div><button class="text-button" data-ui="defaults-update">${t("Посмотреть")} ${icon('arrow')}</button></section>${disclosure('all-settings',t('Все параметры одним списком'),state.fields,t('Все настройки config.env, включая служебные поля и параметры других источников.'))}</div>${aside('configure')}</div>`;
  }
  function pageExtras(page) {
    if(page === 'providers' && value('INFINI_LLM_PROVIDER') === 'openai_codex' || page === 'images' && value('INFINI_IMAGE_BACKEND') === 'openai_codex') return `<section class="account-panel"><div class="account-panel-heading"><h2>${icon('work')}${t("Аккаунт ChatGPT / Codex")}</h2><span class="small-badge" data-account-auth>${state.remote.account?.authenticated ? t('Вход выполнен'):t('Требуется вход')}</span></div><p>${t("Вход по подписке. Текст и изображения используют отдельные модели.")}</p><div class="page-actions"><button class="button" data-action="codexLogin">${t("Войти в Codex")} ${icon('arrow')}</button><button class="button" data-action="codexStatus">${t("Статус аккаунта")}</button><button class="text-button" data-action="codexLogout">${t("Выйти")}</button>${page === 'providers' ? `<button class="button" data-action="codexCatalog">${t("Обновить модели")}</button>`:`<button class="button" data-action="codexPing">${t("Проверить аккаунт")}</button>`}</div><div class="account-status-panel"><p id="account-status">${esc(accountText(page))}</p></div></section>`;
    if(page === 'images' && value('INFINI_IMAGE_BACKEND') === 'sdcpp') return `<div class="context-banner">${icon('stack')}<p>${value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? t('Управляемый запуск: программа и веса выбираются в разделе «Модели и LoRA».'):t('Внешний sd.cpp запускается отдельно. Здесь настраиваются его адрес и параметры запросов.')}</p><a class="text-button" href="#models">${t("Модели и LoRA")} ${icon('arrow')}</a></div>`;
    if(page === 'sprites') return `<div class="page-actions sprite-actions"><button class="button" data-ui="reset-sprite">${icon('refresh')}${t("Вернуть базовый BOX")}</button><button class="text-button" data-action="openCache" title="${t("Открыть папку кеша на компьютере генератора")}">${icon('folder')}${t("Папка спрайтов и кеша")}</button>${value('INFINI_IMAGE_BACKEND') === 'off' ? `<span class="small-badge">${t("Обработка неактивна: изображения выключены")}</span>`:''}</div>`;
    if(page === 'models') return `<div class="context-banner">${icon('stack')}<p>${value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? t('Сейчас выбран другой источник изображений. Эти файлы используются только с sd.cpp.'):value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1' ? t('Внешний sd.cpp выбирает основные модели при своём запуске. Для управления файлами здесь включи управляемый запуск.'):t('Генератор использует эти файлы при запуске sd.cpp. Проверка путей не запускает создание изображения.')}</p><button class="button" data-action="validate">${icon('check')}${t("Проверить пути")}</button></div>`;
    if(page === 'multiplayer') return `<div class="network-mode"><div><h2 id="lan-title">${t("Режим LAN / Radmin")}</h2><p>${t("Доступ по сети к генератору. Студия остаётся на этом компьютере.")}</p></div><label class="toggle-control"><input id="lan-enabled" type="checkbox" aria-labelledby="lan-title" data-lan ${state.lan ? 'checked':''}><span class="toggle-track"></span><span class="toggle-label">${state.lan ? t('Включено'):t('Выключено')}</span></label></div>`;
    return '';
  }
  function renderSettings(page) {
    let fields=state.fields.filter(field=>field.route === page);
    if(state.filter) fields=fields.filter(field=>matches(field,state.filter));
    $('#workspace').innerHTML=`${heading(page)}<div id="page-overview">${pageOverview(page)}</div><div class="settings-layout"><div class="settings-main">${pageExtras(page)}${page === 'diagnostics' ? diagnosticsMarkup():''}<div class="settings-toolbar"><label class="inline-search">${icon('search')}<input id="page-search" placeholder="${t("Найти в этом разделе…")}" value="${esc(state.filter)}" autocomplete="off" aria-label="${t("Поиск в разделе")}"></label><span class="field-counter">${fields.length} ${t("параметров")}${state.filter ? t(' найдено'):''}</span></div><div class="field-section">${page === 'diagnostics' && !state.filter ? disclosure('diagnostic-settings',t('Запись журнала и отладка'),fields,t('Параметры записи и технические режимы генератора.')):fieldGroups(fields,!!state.filter)}</div>${page === 'diagnostics' ? `<details class="advanced emergency-controls"><summary>${t("Аварийное управление")}</summary><p class="details-note">${t("Принудительный перезапуск прерывает активный крафт. Требуется подтверждение.")}</p><div class="page-actions"><button class="button button-danger" data-ui="force-restart">${t("Принудительный перезапуск…")}</button></div></details>`:''}</div>${aside(page)}</div>`;
    if(page === 'diagnostics') updateDiagnostics();
  }
  function diagnosticsMarkup() {
    const tabs={summary:t('Сводка'),events:t('События'),prompts:t('Промпты'),pipeline:t('Этапы'),sdcpp:'sd.cpp',failure:t('Ошибка')};
    return `<section class="diagnostic-workspace"><div class="journal-heading"><div><h2>${t("Журнал крафта")}</h2><p>${t("Последние доступные записи генератора или локального кеша.")}</p></div><button class="button button-primary" data-action="trace">${icon('refresh')}${t("Обновить журнал")}</button></div><div class="page-actions diagnostic-actions"><button class="button" data-action="health">${icon('pulse')}${t("Проверить соединение")}</button><button class="text-button" data-action="openCache" title="${t("Открыть папку кеша на компьютере генератора")}">${icon('folder')}${t("Папка кеша")}</button><button class="text-button" data-action="cancelTrace">${t("Отменить обновление")}</button><button class="text-button" data-ui="clear-trace">${t("Очистить…")}</button></div><p id="trace-status" class="trace-status" role="status"></p><div class="trace-tabs" role="tablist" aria-label="${t("Разделы журнала")}">${Object.entries(tabs).map(([key,name])=>`<button id="tab-${key}" role="tab" aria-controls="trace-view" aria-selected="${key === state.traceTab}" tabindex="${key === state.traceTab ? '0':'-1'}" class="${key === state.traceTab ? 'active':''}" data-trace-tab="${key}">${name}</button>`).join('')}</div><div id="trace-view" class="trace-view" role="tabpanel" aria-labelledby="tab-${state.traceTab}" tabindex="0"></div><details class="diagnostic-raw"><summary>${icon('pulse')}${t("Подробный ответ сервера")}</summary><p class="details-note">${t("Соединение и журнал используют сохранённую конфигурацию или сервер, запущенный этой студией.")}</p><div id="diagnostic-status" class="diagnostic-status"></div></details></section>`;
  }
  // Insert inside studio.js's IIFE; uses the existing esc() and icon() helpers.
  // Returns null for unsupported content so the existing textContent fallback stays intact.
  function traceContent(raw, tab) {
    if (tab !== 'sdcpp' && tab !== 'failure') return null;
    const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
    const text = value => typeof value === 'string' ? value.trim() : '';
    const shorten = value => value.length > 440 ? value.slice(0, 440) + '…' : value;
    const readout = (label, value, hint = '', tone = 'neutral') =>
      '<div class="trace-readout" data-tone="' + tone + '"><dt>' + esc(label) +
      '</dt><dd>' + esc(value) +
      (hint ? '<small>' + esc(hint) + '</small>' : '') + '</dd></div>';
    const head = (glyph, label, title) =>
      '<div class="trace-inspector-head"><span class="trace-inspector-icon">' + icon(glyph) +
      '</span><div><p class="trace-inspector-label">' + esc(label) + '</p><h3>' +
      esc(title) + '</h3></div></div>';

    let data = raw;
    try {
      if (typeof raw === 'string') {
        if (!raw.trim()) return null;
        data = JSON.parse(raw);
      }
      // These are the owner's explicit empty representations, not inferred success.
      if (tab === 'failure' && (data === null ||
          object(data) && (Object.keys(data).length === 0 ||
            data.ok === true && Object.hasOwn(data, 'lastFailure') && data.lastFailure === null))) {
        return '<section class="trace-inspector trace-inspector-empty">' + icon('pulse') +
          `<h3>${t("Сохранённой ошибки нет")}</h3><p>${t("В этом снимке нет сохранённого отчёта о сбое крафта.")}</p></section>`;
      }
      if (!object(data)) return null;
      const serialized = JSON.stringify(data, null, 2);
      if (typeof serialized !== 'string') return null;
      const rawDetails = `<details class="trace-inspector-raw"><summary>${t("Полный снимок")}</summary><pre>` +
        esc(serialized) + '</pre></details>';

      if (tab === 'sdcpp') {
        const known = ['serverAliveProbed', 'serverAlive', 'processAlive', 'autostart', 'serverConfigured']
          .some(key => typeof data[key] === 'boolean');
        if (!known) return null;
        const probed = data.serverAliveProbed === true;
        const alive = probed && typeof data.serverAlive === 'boolean' ? data.serverAlive : null;
        const managed = typeof data.autostart === 'boolean' ? data.autostart : null;
        const process = typeof data.processAlive === 'boolean' ? data.processAlive : null;
        const exited = process === false && Number.isInteger(data.processReturncode);
        const rows = [
          readout(t('HTTP-ответ'), alive === true ? t('Есть ответ') : alive === false ? t('Нет ответа') : probed ? t('Нет данных') : t('Не проверен'),
            alive === null ? (probed ? t('Результат не указан') : t('HTTP-проверка не выполнена')) : t('На момент снимка'),
            alive === true ? 'positive' : alive === false && managed === false ? 'attention' : 'neutral'),
          readout(t('Управляемый процесс'), process === true ? t('Работает') : exited ? t('Завершён') : process === false ? t('Не работает') : t('Нет данных'),
            exited ? t('Код выхода: ') + data.processReturncode : t('Отдельно от HTTP-ответа')),
          readout(t('Запуск'), managed === true ? t('По требованию') : managed === false ? t('Внешний сервер') : t('Нет данных'),
            managed === true ? t('Автозапуск включён') : managed === false ? t('Запускается отдельно') : '')
        ];
        if (managed === true && typeof data.serverConfigured === 'boolean') {
          rows.push(readout(t('Локальная конфигурация'), data.serverConfigured ? t('Задана') : t('Не настроена'), t('Параметры запуска')));
        }
        const endpoint = text(data.serverUrl);
        const startError = text(data.lastStartError);
        return '<section class="trace-inspector" data-trace-kind="sdcpp">' +
          head('image', t('Сервер изображений'), 'sd.cpp') +
          (endpoint ? '<p class="trace-inspector-context"><code>' + esc(endpoint) + '</code></p>' : '') +
          '<dl class="trace-readouts">' + rows.join('') + '</dl>' +
          (startError ? `<p class="trace-inspector-message"><strong>${t("Сохранённая ошибка запуска")}</strong>` +
            esc(shorten(startError)) + '</p>' : '') + rawDetails + '</section>';
      }

      const stage = text(data.stage), error = text(data.error);
      if (data.ok !== false || !stage && !error) return null;
      const rows = [];
      if (stage) rows.push(readout(t('Этап'), stage));
      if (text(data.time)) rows.push(readout(t('Время записи'), text(data.time)));
      const transport = object(data.transportDebug) ? data.transportDebug : {};
      if (Number.isInteger(transport.httpStatus) && transport.httpStatus >= 100 && transport.httpStatus <= 599) {
        rows.push(readout('HTTP', String(transport.httpStatus)));
      }
      if (text(data.version)) rows.push(readout(t('Версия генератора'), text(data.version)));
      const parents = object(data.parents) ? [text(data.parents.a), text(data.parents.b)].filter(Boolean) : [];
      return '<section class="trace-inspector" data-trace-kind="failure">' +
        head('alert', t('Сохранённый отчёт'), t('Последний сбой крафта')) +
        (parents.length ? `<p class="trace-inspector-context">${t("Крафт:")} ` + esc(shorten(parents.join(' + '))) + '</p>' : '') +
        '<p class="trace-inspector-message">' + esc(shorten(error) || t('Текст ошибки не сохранён.')) + '</p>' +
        (rows.length ? '<dl class="trace-readouts">' + rows.join('') + '</dl>' : '') +
        rawDetails + '</section>';
    } catch {
      return null;
    }
  }

  function updateDiagnostics() {
    if(!$('#diagnostic-status')) return;
    $('#diagnostic-status').textContent=[state.remote.status,state.remote.appliedConfig,state.remote.activity].filter(Boolean).map(text => t(text)).join('\n\n');
    $('#trace-status').textContent=t((state.remote.traceStatus || t('Журнал ещё не запрошен.')).replace('Нажми Refresh trace. Если сервер не запущен, Studio показывает локальные cache/*.ndjson.',t('Обнови журнал. Если генератор недоступен, студия покажет записи локального кеша.')));
    const raw=state.remote.trace?.[state.traceTab] ?? (state.traceTab === 'failure' ? state.remote.trace?.last_failure:undefined);
    const view=$('#trace-view'),key=JSON.stringify([state.traceTab,raw]);
    if(view._traceKey !== key) {
      const keepOpen=view._traceTab === state.traceTab && !!view.querySelector('.trace-inspector-raw[open]');
      const inspector=raw === undefined || raw === '' ? null:traceContent(raw,state.traceTab);
      view.classList.toggle('is-empty',inspector === null && (!raw || typeof raw === 'string' && !raw.trim()));
      if(inspector !== null) {view.innerHTML=inspector;if(keepOpen) view.querySelector('.trace-inspector-raw')?.setAttribute('open','');}
      else if(view.classList.contains('is-empty')) view.innerHTML=`${icon('pulse')}<h3>${t("Нет загруженных записей")}</h3><span>${t("Нажми «Обновить журнал», чтобы получить промпты, этапы и ошибки крафта.")}</span>`;
      else view.textContent=typeof raw === 'string' ? raw:JSON.stringify(raw,null,2);
      view._traceKey=key;view._traceTab=state.traceTab;
    }
    updatePageOverview();
  }
  function render() {
    syncLanguage();
    if (!state.remote || state.shutdown) return;
    state.openDetails = new Set([...state.openDetails,...$$('details[open]').map(detail => detail.dataset.details)]);
    if (state.page === 'operate') renderOperate();
    else if (state.page === 'configure') renderConfigure();
    else renderSettings(state.page);
    $$('details[data-details]').forEach(detail => detail.addEventListener('toggle',() => detail.open ? state.openDetails.add(detail.dataset.details):state.openDetails.delete(detail.dataset.details)));
    updateActionButtons();
    if(state.page !== 'operate') document.dispatchEvent(new Event('studio:render'));
  }
  function renderPreservingFocus() {
    const active=document.activeElement;
    const key=active?.dataset?.field,id=active?.id;
    const selection=typeof active?.selectionStart === 'number' ? [active.selectionStart,active.selectionEnd] : null;
    render();
    const target=id ? document.getElementById(id) : key ? $(`[data-field="${key}"]`) : null;
    if(!target) return;
    for(let parent=target.parentElement;parent;parent=parent.parentElement) {
      if(parent.tagName === 'DETAILS') {parent.open=true;if(parent.dataset.details) state.openDetails.add(parent.dataset.details);}
    }
    target.focus({preventScroll:true});
    if(selection && target.setSelectionRange) target.setSelectionRange(...selection);
  }
  function syncInputs() {
    $$('[data-derived]').forEach(output=>{const derived=derivedField(output.dataset.derived);if(derived) output.textContent=derived.value;});
    $$('[data-field]').forEach(input => {
      if (document.activeElement === input) return;
      const val = value(input.dataset.field);
      if (input.type === 'checkbox') input.checked = val === '1'; else if (input.value !== val) input.value = val;
      input.closest('.field-row')?.classList.toggle('is-dirty',state.dirty.has(input.dataset.field));
      if (input.type === 'checkbox' && input.parentElement.querySelector('.toggle-label')) input.parentElement.querySelector('.toggle-label').textContent = input.checked ? t('Включено'):t('Выключено');
    });
    updatePageOverview();
  }
  function setMenu(open, restoreFocus=true) {
    const rail = $('.rail'), menu = $('.mobile-menu');
    const wasOpen=rail.classList.contains('is-open'),focusVersion=state.menuFocusVersion=(state.menuFocusVersion || 0)+1;
    open = !!open && innerWidth <= 720;
    rail.classList.toggle('is-open',open);
    menu.setAttribute('aria-expanded',String(open));
    $('#navigation-backdrop').hidden = !open;
    $('.main-shell').inert = open;
    $('#save-tray').inert = open;
    document.body.classList.toggle('menu-open',open);
    if (open) {
      rail.setAttribute('role','dialog'); rail.setAttribute('aria-modal','true');
      const focusNavigation=()=>$('.nav-link.active',rail)?.focus({preventScroll:true});
      focusNavigation();
      // A responsive CSS/inert update may not be painted during this click.
      // Retry once after layout, but never steal an intentional drawer focus.
      requestAnimationFrame(()=>{if(state.menuFocusVersion === focusVersion && rail.classList.contains('is-open') && !rail.contains(document.activeElement) && !document.querySelector('dialog[open]')) focusNavigation();});
    } else {
      rail.removeAttribute('role'); rail.removeAttribute('aria-modal');
      if (restoreFocus && (wasOpen || rail.contains(document.activeElement))) menu.focus({preventScroll:true});
    }
  }
  function navigate() {
    const target = location.hash.slice(1).split('?')[0];
    const animateRoute = state.pointerRoute === target && target !== state.page && !!state.remote;
    state.pointerRoute = null;
    const workspace = $('#workspace');
    workspace.classList.remove('route-enter');
    state.page = routes[target] ? target : 'operate'; state.filter = '';
    document.body.dataset.page = state.page;
    $$('.nav-link').forEach(link => {link.classList.toggle('active',link.dataset.route === state.page); if (link.dataset.route === state.page) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');});
    $('#crumb').textContent = t(routes[state.page][0]);document.title = `${t(routes[state.page][0])} — Infinicraft`;
    const fromMenu = $('.rail').classList.contains('is-open');
    setMenu(false,false);
    render();if (fromMenu) $('#workspace').focus({preventScroll:true});
    if(state.focusKey) {const key=state.focusKey;state.focusKey=null;focusFieldRow(key);} else window.scrollTo({top:0,behavior:'instant'});
    maybeLoadCatalog();
    // The persistent workspace animates only a pointer-driven route change;
    // snapshot updates and control renders never replay the entrance.
    if (animateRoute && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      void workspace.offsetWidth;
      workspace.classList.add('route-enter');
      document.dispatchEvent(new Event('studio:route'));
    }
  }
  function matches(field,query) {
    const haystack = `${label(field)} ${field.key} ${t(field.help) || ''} ${t(routes[field.route][0])}`.toLocaleLowerCase();
    return query.toLocaleLowerCase().trim().split(/\s+/).every(part => haystack.includes(part));
  }
  function showSearch() {setMenu(false);$('#search-dialog').showModal();$('#global-search').value='';state.searchIndex=0;renderSearch();$('#global-search').focus();}
  function renderSearch() {
    const query = $('#global-search').value;
    state.searchMatches = state.fields.filter(field => matches(field,query));
    state.searchIndex = Math.min(state.searchIndex,Math.max(0,state.searchMatches.length-1));
    $('#search-results').innerHTML = state.searchMatches.length ? state.searchMatches.map((field,index) => `<button class="search-result ${index === state.searchIndex ? 'selected':''}" data-search-key="${field.key}" id="search-hit-${index}"><span><strong>${esc(label(field))}</strong><small>${field.key}</small></span><span>${esc(t(routes[field.route][0]))}</span></button>`).join('') : `<div class="empty-search">${t("Ничего не найдено. Ищи по названию или ключу INFINI_.")}</div>`;
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
  function utility(title,body) {setMenu(false);$('#utility-dialog').dataset.kind='';$('#utility-title').textContent=t(title);$('#utility-body').innerHTML=body;$('#utility-dialog').showModal();updateActionButtons();}
  function showSaveConflict() {
    const disk={...state.remote.defaults,...state.remote.savedValues};
    const changed=[...new Set([...Object.keys(state.revisionValues || {}),...Object.keys(disk)])].filter(key=>disk[key] !== state.revisionValues?.[key]);
    const display=(key,val)=>isCredentialKey(key) ? (val ? '••••••••':t('Не задано')) : val || t('Не задано');
    utility(t('Конфигурация изменилась на диске'), `<p class="dialog-copy">${t("Другой процесс или вкладка сохранили настройки после начала твоего черновика. Проверь изменения ниже. Твои правки останутся в этой вкладке; сохранение потребует отдельного нажатия.")}</p><div class="confirm-list">${changed.map(key=>`<div><span>${esc(t(names[key]) || key)}<small>${t("На диске:")} ${esc(display(key,disk[key]))}</small></span><span>${t("Черновик:")} ${esc(display(key,value(key)))}</span></div>`).join('')}</div><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Вернуться")}</button><button class="button button-primary" id="reconcile-draft">${t("Продолжить с моими правками")}</button></div>`);
    const revision=state.remote.savedRevision;
    $('#reconcile-draft').onclick=()=>{
      // Polling may have observed a second writer while this comparison was
      // open. Never acknowledge a revision different from the reviewed one.
      if(!state.remote.savedRevision) {toast(t('Не удалось проверить конфигурацию на диске. Дождись восстановления чтения и обнови сравнение.'),true);return;}
      if(state.remote.savedRevision !== revision) {showSaveConflict();$('#utility-dialog [data-ui="close-dialog"]').focus({preventScroll:true});toast(t('Конфигурация изменилась ещё раз. Сравнение обновлено; проверь новые значения перед продолжением.'),true);return;}
      const edits=Object.fromEntries([...state.dirty].map(key=>[key,state.draft[key]]));
      state.draft={...disk,...edits};state.baseline={...disk};state.savedRevision=revision;state.revisionValues={...disk};
      $('#utility-dialog').close();recomputeDirty();render();toast(t('Черновик сохранён в этой вкладке. Проверь его и нажми «Сохранить», когда будешь готов.'));
    };
  }
  function showDocument(result) {
    utility(result.title || t('Локальный документ'), `<p class="dialog-copy">${esc(result.path || '')}</p><pre class="document-view">${esc(result.content || '')}</pre><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Закрыть")}</button></div>`);
  }
  async function showFilePicker(key,kind='file') {
    state.picker={key,kind,request:0};
    utility(t('Выбрать на компьютере генератора'), `<p class="dialog-copy">${esc(t(names[key]) || key)}${t(". Выбор изменит только черновик; файлы не загружаются и не изменяются.")}</p><form id="file-location"><label class="dialog-field-label" for="file-path">${t("Папка или полный путь")}</label><div class="file-location"><input class="dialog-input" id="file-path" autocomplete="off" spellcheck="false"><button class="button" type="submit">${t("Открыть")}</button></div></form><p id="file-error" role="alert" class="defaults-error" hidden></p><div id="file-entries" class="file-entries" aria-live="polite"></div><p id="file-selection" class="dialog-copy" aria-live="polite"></p><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Отмена")}</button><button class="button button-primary" id="file-select" disabled>${kind === 'folder' ? t('Выбрать папку'):t('Выбрать файл')}</button></div>`);
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
    toast(t('Путь выбран. Сохрани настройки, чтобы записать его в config.env.'));
  }
  async function loadFiles(path) {
    const picker=state.picker;if (!picker) return;
    const request=++picker.request;
    $('#file-select').disabled=true;$('#file-error').hidden=true;
    $('#file-entries').textContent=t('Читаем папку…');
    try {
      const listing=await api(`/api/files?path=${encodeURIComponent(path)}&kind=${encodeURIComponent(picker.kind)}`);
      if(state.picker !== picker || picker.request !== request || !$('#utility-dialog').open || $('#utility-dialog').dataset.kind !== 'files') return;
      $('#file-path').value=listing.path;
      if(listing.warning) {$('#file-error').hidden=false;$('#file-error').textContent=listing.warning;}
      picker.selection=picker.kind === 'folder' ? listing.path : listing.selected?.path || (listing.entries || []).find(entry=>!entry.directory && entry.path === path)?.path || null;
      $('#file-select').disabled=!picker.selection;
      $('#file-selection').textContent=picker.selection ? t("Выбрано: {0}", picker.selection) : t('Выбери файл из списка или открой полный путь.');
      const entries=listing.entries || [];
      $('#file-entries').innerHTML=`${listing.parent ? `<button class="file-entry" data-file-parent>${t("↑ На уровень выше")}</button>`:''}${entries.map((entry,index)=>`<button class="file-entry" data-file-index="${index}">${icon(entry.directory ? 'folder':'text')}<span>${esc(entry.name)}</span>${entry.directory ? icon('arrow'):''}</button>`).join('')}${!entries.length ? `<p class="dialog-copy">${t("Подходящих файлов здесь нет.")}</p>`:''}${listing.truncated ? `<p class="dialog-copy">${t("Показана часть папки. Укажи более точный путь.")}</p>`:''}`;
      $('[data-file-parent]')?.addEventListener('click',()=>loadFiles(listing.parent));
      $$('[data-file-index]').forEach(button=>button.onclick=()=>{
        const entry=entries[Number(button.dataset.fileIndex)];
        if(entry.directory) {loadFiles(entry.path);return;}
        picker.selection=entry.path;$('#file-select').disabled=false;$('#file-selection').textContent=t("Выбрано: {0}", entry.path);
        $$('[data-file-index]').forEach(row=>row.classList.toggle('selected',row === button));
      });
    } catch(error) {
      if(state.picker !== picker || picker.request !== request || $('#utility-dialog').dataset.kind !== 'files') return;
      $('#file-error').hidden=false;$('#file-error').textContent=t(error.message);
      $('#file-entries').textContent=t('Проверь путь и попробуй снова.');
    }
  }
  function defaultsError(message) {
    if ($('#defaults-error')) {$('#defaults-error').textContent=t(message);$('#defaults-error').hidden=false;}
  }
  function showDefaultsUpdate() {
    const offer = state.remote?.defaultsUpdate;
    state.defaultsPreview = offer ? {...offer,changes:(offer.changes || []).map(row=>({...row}))} : null;
    const changes = state.defaultsPreview?.changes || [];
    utility(t("Рекомендации {0}", offer?.version || ''),`<p class="dialog-copy">${t("Необязательные рекомендации для сравнения с сохранённым config.env. Личные настройки могут отличаться; применять рекомендации не обязательно. Будут записаны только перечисленные изменения. Несохранённые настройки, ключи, источники моделей и пути остаются без изменений. Работающий генератор применит изменения после безопасного перезапуска.")}</p><div id="defaults-changes" class="defaults-changes">${changes.length ? changes.map(row=>`<div data-defaults-key="${esc(row.key)}"><code>${esc(row.key)}</code><p class="defaults-values"><span>${esc(row.current || t("Пусто (off)"))}</span> → <strong>${esc(row.recommended)}</strong></p><p>${esc(t(row.reason))}</p></div>`).join('') : t('Обновлений рекомендованных значений нет.')}</div><p id="defaults-error" class="defaults-error" role="alert" hidden></p><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Позже")}</button><button class="button" id="defaults-refresh" data-ui="defaults-refresh">${t("Обновить список")}</button>${changes.length ? `<button class="button" id="defaults-decline" data-submit-action>${t("Оставить текущие")}</button><button class="button button-primary" id="defaults-accept" data-submit-action>${t("Применить рекомендации")}</button>` : ''}</div>`);
    $('#utility-dialog').dataset.kind='defaults';
    const decide = name => action(name,{revision:state.defaultsPreview.revision});
    if ($('#defaults-accept')) $('#defaults-accept').onclick=()=>decide('acceptDefaults');
    if ($('#defaults-decline')) $('#defaults-decline').onclick=()=>decide('declineDefaults');
  }
  async function refreshDefaultsUpdate() {
    if (state.pending || state.posting) return;
    const preview=state.defaultsPreview;
    if (!preview) return;
    const request=preview.refreshRequest=(preview.refreshRequest || 0)+1;
    // A dismissed/replaced preview or newer refresh owns the dialog now. Do
    // not apply an obsolete snapshot or reopen the old consent surface.
    const current=()=>state.defaultsPreview === preview && preview.refreshRequest === request && $('#utility-dialog').open && $('#utility-dialog').dataset.kind === 'defaults' && !state.pending && !state.posting;
    try {const remote=await api('/api/state');if(current() && acceptSnapshot(remote)) showDefaultsUpdate();}
    catch(error) {if(current()) defaultsError(error.message);}
  }
  function confirm(title,description,actionName,extra={},labelText=t('Подтвердить')) {
    utility(title,`<p class="dialog-copy">${esc(description)}</p><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Отмена")}</button><button class="button ${actionName === 'stop' || actionName === 'clearTrace' ? 'button-danger':'button-primary'}" id="confirm-submit" data-submit-action>${esc(labelText)}</button></div>`);
    $('#confirm-submit').onclick=() => {$('#utility-dialog').close();action(actionName,extra);};
  }
  function showHelp() {
    utility(t('Как начать крафт'),`<p class="dialog-copy">${t("Студия настраивает генератор. Сам крафт происходит в Terraria с модом InfiniCrafterLocal.")}</p>${[
      ['01',t('Выбери автора'),t('Подключи локальную текстовую модель или API. Автор отвечает за свойства и механику.')],['02',t('Настрой изображение'),t('Выбери источник рисунка. Для sd.cpp укажи существующие файлы моделей; для API — адрес и ключ.')],['03',t('Запусти генератор'),t('Сохрани настройки и запусти генератор. «Проверить» показывает реальное соединение, не готовность всех моделей.')],['04',t('Продолжи в игре'),t('Открой Terraria с модом. Предметы создаются через игровой крафт. Студия не запускает пробную платную генерацию.')]
    ].map(([n,title,text]) => `<div class="help-step"><span>${n}</span><div><h3>${title}</h3><p>${text}</p></div></div>`).join('')}<div class="dialog-actions"><a class="button" href="/guide?token=${encodeURIComponent(token)}#/docs/user/START_RU.md" target="_blank" rel="noopener">${t("Локальная инструкция ↗")}</a><button class="button button-primary" data-ui="close-dialog">${t("К работе")} ${icon('arrow')}</button></div>`);
  }
  function showPresetPreview() {
    const name = $('#preset-select').value;
    if (!name) {toast(t('Сначала выбери профиль.'),true);return;}
    const source = name.startsWith('Мой: ') ? state.remote.userPresets[name.slice(5)] : state.remote.presets[name];
    const preset = source?.settings || source?.values || source;
    if (!preset || typeof preset !== 'object') {toast(t('Профиль не найден в локальной конфигурации.'),true);return;}
    const changes = Object.entries(preset).filter(([key,val]) => key.startsWith('INFINI_') && !isCredentialKey(key) && String(val) !== value(key));
    utility(t('Применить сборку?'),`<p class="dialog-copy">${esc(presetLabel(name))}<br>${t("Текущие ключи остаются. Изменения будут подготовлены, но ещё не записаны в config.env.")}</p><div class="confirm-list">${changes.length ? changes.map(([key,val]) => `<div><span>${esc(t(names[key]) || key)}</span><span>${esc(val)}</span></div>`).join(''):t('Значения профиля уже совпадают с текущими.')}</div><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Отмена")}</button><button class="button button-primary" id="confirm-submit" data-submit-action>${t("Применить")} ${icon('arrow')}</button></div>`);
    $('#confirm-submit').onclick=() => {$('#utility-dialog').close();action('applyPreset',{name});};
  }
  function showSavePreset() {
    utility(t('Сохранить профиль'),`<p class="dialog-copy">${t("Именованный профиль сохраняется отдельно. Ключи и токены в него не входят; config.env не меняется.")}</p><label class="dialog-field-label" for="new-preset-name">${t("Название профиля")}</label><input class="dialog-input" id="new-preset-name" placeholder="${t("Локальная модель")}" maxlength="80" autocomplete="off"><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Отмена")}</button><button class="button button-primary" id="confirm-submit" data-submit-action>${t("Сохранить профиль")}</button></div>`);
    const submit=() => {
      const name=$('#new-preset-name').value.trim();
      if (!name) {$('#new-preset-name').focus();return;}
      if (Object.hasOwn(state.remote.userPresets || {},name)) {
        $('#utility-dialog').close();
        confirm(t('Заменить существующий профиль?'),t("Профиль «{0}» уже существует. Сохраним текущую сборку вместо него; config.env не изменится.", name),'savePreset',{name},t('Заменить профиль'));
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
      state.edits[key]=++state.editClock;recomputeDirty();target.closest('.field-row')?.classList.toggle('is-dirty',state.dirty.has(key));
      $$('[data-derived]').forEach(output=>{const derived=derivedField(output.dataset.derived);if(derived) output.textContent=derived.value;});
      if(target.type === 'checkbox') target.parentElement.querySelector('.toggle-label').textContent=target.checked ? t('Включено'):t('Выключено');
      if(key === 'INFINI_LLM_PROVIDER') state.fields=makeFields(state.remote);
      if(target.tagName === 'SELECT' || target.type === 'checkbox') {const selection=target.id;render();document.getElementById(selection)?.focus({preventScroll:true});}
      if(key === 'INFINI_CODEX_LLM_MODEL') {
        state.fields=makeFields(state.remote);
        for(const field of state.fields.filter(field=>['INFINI_LLM_REASONING_MODE','INFINI_CODEX_VISUAL_REASONING'].includes(field.key))) {
          const row=$(`[data-field-row="${field.key}"]`);if(row) row.outerHTML=fieldHTML(field);
        }
        if($('#account-status')) $('#account-status').textContent=accountText('providers');
      }
      if(['INFINI_LLM_REASONING_MODE','INFINI_CODEX_VISUAL_REASONING'].includes(key) && $('#account-status')) $('#account-status').textContent=accountText('providers');
      if(key === 'INFINI_LLM_PROVIDER') maybeLoadCatalog();
      updatePageOverview();
    }
    if(target.matches('[data-lan]')) {state.lan=target.checked;state.lanEdit=++state.editClock;target.parentElement.querySelector('.toggle-label').textContent=target.checked?t('Включено'):t('Выключено');recomputeDirty();render();$('#lan-enabled')?.focus({preventScroll:true});}
    if(target.id === 'file-path' && state.picker) {state.picker.request++;state.picker.selection=null;$('#file-select').disabled=true;$('#file-selection').textContent=t('Нажми «Открыть», чтобы проверить новый путь.');$$('[data-file-index]').forEach(row=>row.classList.remove('selected'));}
    if(target.id === 'preset-select') state.presetChoice=target.value;
    if(target.id === 'global-search') {state.searchIndex=0;renderSearch();}
    if(target.id === 'page-search') {const start=target.selectionStart;state.filter=target.value;render();$('#page-search').focus({preventScroll:true});$('#page-search').setSelectionRange(start,start);}
  });
  document.addEventListener('click',event => {
    const routeLink = event.target.closest('a[href^="#"]');
    const pointerTarget = routeLink?.hash.slice(1).split('?')[0];
    state.pointerRoute = event.detail > 0 && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && !routeLink?.dataset.ui && !routeLink?.target && routes[pointerTarget] && pointerTarget !== state.page ? pointerTarget : null;
    const navigation = event.target.closest('.rail a[href^="#"]');
    if (navigation && $('.rail').classList.contains('is-open') && navigation.hash === location.hash) {
      setMenu(false,false); $('#workspace').focus({preventScroll:true});
    }
    const button=event.target.closest('button,[data-ui],[data-search-key]');if(!button) return;
    if (button.tagName === 'A' && button.dataset.ui) event.preventDefault();
    if(button.dataset.action) {action(button.dataset.action);return;}
    if(button.dataset.browse) {showFilePicker(button.dataset.browse,button.dataset.browseType);return;}
    if(button.dataset.reveal) {const input=$(`[data-field="${button.dataset.reveal}"]`);input.type=input.type === 'password'?'text':'password';button.setAttribute('aria-pressed',String(input.type === 'text'));button.setAttribute('aria-label',input.type === 'text'?t('Скрыть ключ'):t('Показать ключ'));return;}
    if(button.dataset.helpField) {event.preventDefault();const key=button.dataset.helpField;state.helpFields.has(key)?state.helpFields.delete(key):state.helpFields.add(key);const y=window.scrollY;render();window.scrollTo(0,y);$(`[data-help-field="${key}"]`)?.focus({preventScroll:true});return;}
    if(button.dataset.searchKey) {focusField(button.dataset.searchKey);return;}
    if(button.dataset.sectionLink) {const heading=document.getElementById(button.dataset.sectionLink);if(heading) {heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant':'smooth'});}return;}
    if(button.dataset.traceTab) {state.traceTab=button.dataset.traceTab;$$('[data-trace-tab]').forEach(tab => {tab.classList.toggle('active',tab === button);tab.setAttribute('aria-selected',String(tab === button));tab.tabIndex=tab === button?0:-1;});$('#trace-view').setAttribute('aria-labelledby',button.id);updateDiagnostics();return;}
    switch(button.dataset.ui) {
      case 'defaults-update':showDefaultsUpdate();break;
      case 'defaults-refresh':refreshDefaultsUpdate();break;
      case 'search':showSearch();break;
      case 'review-conflict':showSaveConflict();break;
      case 'notifications':utility(t('Уведомления'),state.notifications.length ? `<div class="notification-history">${[...state.notifications].reverse().map(notice=>`<article class="notification-entry${notice.error ? ' is-error':''}"><span>${icon(notice.error ? 'alert':'check')}</span><p>${esc(notice.message)}</p></article>`).join('')}</div>` : `<p class="dialog-copy">${t("Уведомлений пока нет.")}</p>`);break;
      case 'retry':poll();break;
      case 'close-dialog':if (button.closest('dialog')?.dataset.kind !== 'defaults' || !(state.pending || state.posting)) button.closest('dialog')?.close();break;
      case 'menu':setMenu(!$('.rail').classList.contains('is-open'));break;
      case 'close-menu':setMenu(false);break;
      case 'help':showHelp();break;
      case 'force-restart':confirm(t('Прервать крафт и перезапустить?'),t('Активный и ожидающий крафт будет прерван. Это не подтверждает возврат материалов в игре. Используй только если безопасный перезапуск недоступен.'),'forceRestart',{confirm:true},t('Прервать и перезапустить'));break;
      case 'stop':confirm(t('Остановить генератор?'),t('Проверим активный крафт перед остановкой собственного запущенного сервера. Черновик адреса не меняет цель; чужие процессы не изменяются.'),'stop',{},t('Остановить безопасно'));break;
      case 'exit':confirm(
        state.remote?.managed ? t('Закрыть студию и генератор?') : t('Закрыть студию?'),
        state.remote?.managed ? t('Если Studio запустила генератор, он остановится вместе с ней, а текущий крафт прервётся. Несохранённые изменения в этой вкладке будут потеряны.') : t('Закроется только локальный интерфейс. Это действие не останавливает генератор. Несохранённые изменения в этой вкладке будут потеряны.'),
        'exitStudio',{},t('Закрыть студию'));break;
      case 'clear-trace':confirm(t('Очистить локальный журнал?'),t('Будут удалены диагностические записи сохранённой конфигурации. Черновик пути не меняет цель. Готовые игровые предметы и рецепты не меняются. Это действие нельзя отменить.'),'clearTrace',{confirm:true},t('Очистить журнал'));break;
      case 'clear-lora':confirm(t('Отключить адаптер?'),t('Сбросим настройки LoRA. Сам файл на диске не удаляется.'),'clearLora',{},t('Отключить LoRA'));break;
      case 'reset-sprite':confirm(t('Вернуть базовый resize?'),t('Фильтр станет BOX, premultiplied resize будет включён. Остальные параметры спрайта остаются.'),'resetSprite',{},t('Вернуть BOX'));break;
      case 'apply-preset':showPresetPreview();break;
      case 'save-preset':showSavePreset();break;
      case 'discard':{
        if(state.pending || state.posting) {toast(t('Дождись подтверждения перед отменой.'),true);break;}
        utility(t('Отменить изменения?'), `<p class="dialog-copy">${t("Все несохранённые изменения в этой вкладке будут заменены значениями из config.env.")}</p><div class="dialog-actions"><button class="button" data-ui="close-dialog">${t("Продолжить редактирование")}</button><button class="button button-danger" id="confirm-submit">${t("Отменить изменения")}</button></div>`);
        $('#confirm-submit').onclick=()=>{state.draft={...state.remote.defaults,...state.remote.savedValues};state.baseline={...state.draft};state.lan=state.baselineLan=!!state.remote.savedLanEnabled;state.savedRevision=state.remote.savedRevision;state.revisionValues={...state.draft};state.presetChoice=null;state.editClock++;Object.keys(state.draft).forEach(key=>state.edits[key]=state.editClock);state.lanEdit=state.editClock;recomputeDirty();$('#utility-dialog').close();render();};break;
      }
    }
  });
  document.addEventListener('keydown',event => {
    state.pointerRoute = null;
    $('#workspace').classList.remove('route-enter');
    if((event.ctrlKey || event.metaKey) && event.code === 'KeyK') {event.preventDefault();if(!$('#utility-dialog').open) showSearch();}
    if((event.ctrlKey || event.metaKey) && event.code === 'KeyS') {event.preventDefault();if(state.remote && !state.shutdown && !document.querySelector('dialog[open]')) action('save');}
    if($('#search-dialog').open && event.target.id === 'global-search' && ['ArrowDown','ArrowUp','Enter'].includes(event.key)) {
      event.preventDefault();
      if(event.key === 'Enter') {if(state.searchMatches[state.searchIndex]) focusField(state.searchMatches[state.searchIndex].key);}
      else {state.searchIndex=Math.max(0,Math.min(state.searchMatches.length-1,state.searchIndex+(event.key === 'ArrowDown'?1:-1)));$$('.search-result').forEach((result,index)=>result.classList.toggle('selected',index === state.searchIndex));const result=$(`#search-hit-${state.searchIndex}`);if(result) {const panel=$('#search-results');if(result.offsetTop < panel.scrollTop) panel.scrollTop=result.offsetTop;else if(result.offsetTop+result.offsetHeight>panel.scrollTop+panel.clientHeight) panel.scrollTop=result.offsetTop+result.offsetHeight-panel.clientHeight;}}
    }
    if(event.target.matches('[data-trace-tab]') && ['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();const tabs=$$('[data-trace-tab]'),index=tabs.indexOf(event.target);const next=event.key === 'Home'?0:event.key === 'End'?tabs.length-1:(index+(event.key === 'ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();tabs[next].scrollIntoView({block:'nearest',inline:'nearest'});
    }
    if(event.key === 'Escape') setMenu(false);
    if(event.key === 'Tab' && $('.rail').classList.contains('is-open') && !document.querySelector('dialog[open]')) {
      const items = $$('a[href],button:not(:disabled)', $('.rail')), first=items[0], last=items.at(-1);
      if(event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
    }
  });
  document.addEventListener('animationend',event => {if(event.target.id === 'workspace') event.target.classList.remove('route-enter');});
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
