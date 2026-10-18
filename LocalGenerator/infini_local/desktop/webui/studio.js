/* Infinicraft Studio. Same-origin bridge; drafts stay in memory, Save writes local config. */
'use strict';
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
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
    INFINI_USE_LLM:'Генерация механики моделью', INFINI_PROMPT_STYLE:'Художественное направление', INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK:'Технический запасной генератор', INFINI_GUI_PIPELINE_PRESET:'Профиль настроек', INFINI_LLM_PROVIDER:'Источник текста и механики', INFINI_CODEX_LLM_MODEL:'Текстовая модель Codex', INFINI_LMSTUDIO_URL:'Адрес LM Studio', INFINI_LMSTUDIO_MODEL:'Локальная текстовая модель', INFINI_OPENROUTER_API_KEY:'Ключ OpenRouter', INFINI_OPENROUTER_MODEL:'Модель OpenRouter', INFINI_OPENROUTER_PROVIDER:'Площадка OpenRouter', INFINI_OPENROUTER_HTTP_REFERER:'Источник запросов', INFINI_OPENROUTER_APP_TITLE:'Имя приложения в OpenRouter', INFINI_OPENAI_COMPAT_BASE_URL:'Адрес совместимого API', INFINI_OPENAI_COMPAT_API_KEY:'Ключ совместимого API', INFINI_OPENAI_COMPAT_MODEL:'Модель совместимого API', INFINI_LLM_API_MODE:'Формат запроса к модели', INFINI_LLM_RESPONSE_FORMAT:'Формат ответа', INFINI_LLM_TEMPERATURE:'Вариативность идеи', INFINI_LLM_REAUTHOR_TEMPERATURE:'Вариативность исправления', INFINI_VISUAL_DIRECTOR_TEMPERATURE:'Вариативность арт-директора', INFINI_LLM_MAX_TOKENS:'Лимит ответа, токены', INFINI_LLM_TIMEOUT:'Ожидание LLM-стадии, секунды', INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS:'Лимит VFX, токены', INFINI_VFX_LLM_DIRECTOR_TIMEOUT:'Ожидание VFX, секунды', INFINI_LLM_REASONING_MODE:'Глубина рассуждения', INFINI_LLM_REASONING_MAX_TOKENS:'Бюджет рассуждения, токены', INFINI_LLM_REASONING_EXCLUDE:'Не возвращать рассуждение в ответ', INFINI_LLM_LOCAL_REASONING_PROMPT:'Приватная самопроверка', INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS:'Пауза после сбоя, секунды', INFINI_LLM_FALLBACK_PROVIDER:'Запасной источник', INFINI_LLM_FALLBACK_MODEL:'Запасная модель', INFINI_LLM_FALLBACK_BASE_URL:'Адрес запасного API', INFINI_LLM_FALLBACK_API_KEY:'Ключ запасного API', INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER:'Запасная площадка OpenRouter', INFINI_LLM_FALLBACK_NETWORK_FAILS:'Сетевых сбоев до переключения',
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
  function value(key, fallback='') { return state.draft[key] ?? fallback; }
  function draftStatusText() { return state.dirty.size || state.lan !== state.baselineLan ? 'Черновик / Не сохранён' : 'Локальная конфигурация'; }
  function recomputeDirty() {
    state.dirty = new Set(Object.keys(state.draft).filter(key => state.draft[key] !== (state.baseline[key] ?? '')));
    $('#save-tray').hidden = !state.dirty.size && state.lan === state.baselineLan;
    const total = state.dirty.size + Number(state.lan !== state.baselineLan);
    $('#dirty-label').textContent = `${total} ${total === 1 ? 'изменение' : total < 5 ? 'изменения' : 'изменений'} в настройках`;
    $$('[data-draft-status]').forEach(element => element.textContent=draftStatusText());
    $$('[data-dirty-count]').forEach(element => element.textContent=total ? `${total} несохранённых изменений` : 'Изменений нет');
    $$('.save-panel').forEach(element => element.classList.toggle('is-dirty',!!total));
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
    const reasoning = value('INFINI_LLM_REASONING_MODE','off').toLowerCase().replaceAll('-','_');
    const reasoningOff = ['', 'off', 'false', '0', 'disabled', 'disable', 'none', 'no_reasoning'].includes(reasoning);
    const promptReasoning = ['prompt','prompt_light','prompt_strong','local_prompt','local_light','local_strong'].includes(reasoning);
    if (key === 'INFINI_LLM_REASONING_EXCLUDE' && (provider === 'local' || reasoningOff || promptReasoning)) return 'Для API reasoning, не prompt-only режима';
    if (key === 'INFINI_LLM_REASONING_MAX_TOKENS' && (provider === 'local' || !['tokens','token_budget','max_tokens','budget'].includes(reasoning))) return 'Для API с режимом бюджета токенов';
    if (key === 'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD' && value('INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED') !== '1') return 'Отладочная выдача выключена';
    if (key === 'INFINI_IMAGE_MAX_CONCURRENCY' && backend === 'off') return 'Изображения выключены';
    if (['INFINI_VISUAL_DIRECTOR_LLM','INFINI_VFX_LLM_DIRECTOR'].includes(key) && !['full','all','projectile','visualpack','assetpack'].includes(value('INFINI_VISUAL_ASSET_MODE'))) return 'Дополнительные визуальные ассеты выключены';
    if (['INFINI_CODEX_LLM_MODEL','INFINI_CODEX_VISUAL_REASONING'].includes(key) && value('INFINI_USE_LLM') === '0') return 'Текстовая генерация выключена';
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
    if (key === 'INFINI_ASSET_PUBLIC_BASE_URL' && !state.lan) return 'Режим LAN / Radmin выключен';
    if (key === 'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE' && value('INFINI_SDCPP_SERVER_COMMAND_MODE') !== 'template') return 'Запуск использует автоматический argv';
    // Native metadata describes the controller values, not unsaved browser edits.
    if (field.disabled && !state.dirty.size && state.lan === state.baselineLan && Object.entries(state.remote?.values || {}).every(([name,val])=>value(name) === val)) return field.disabled;
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
    if(page === 'providers' && /^(Текстовая модель аккаунта:|Сохранённый reasoning|Ручной slug вне текущего каталога:)/.test(detail || '')) detail=`В последнем каталоге аккаунта: ${Object.keys(account.textModels || {}).length} моделей. Image-доступ не проверен.`;
    const lines=[account.status,detail].filter(Boolean);
    if(page === 'providers' && value('INFINI_LLM_PROVIDER') === 'openai_codex') {
      const slug=value('INFINI_CODEX_LLM_MODEL'),model=account.textModels?.[slug];
      if(model) {
        lines.push(`Для выбранной модели ${slug} в последнем каталоге: ${model.efforts.join(', ') || 'effort не заявлен'}. По умолчанию: ${model.defaultEffort || 'не указан'}.`);
        const reasoning=value('INFINI_LLM_REASONING_MODE'),visual=value('INFINI_CODEX_VISUAL_REASONING');
        if(!['off',...model.efforts].includes(reasoning) || !['inherit','model_default',...model.efforts].includes(visual)) lines.push('Выбранный effort не поддерживается этой моделью. Значения сохранены; выбери поддерживаемый вариант.');
      } else lines.push(slug ? 'Выбранный slug ещё не подтверждён каталогом. Effort можно ввести вручную; значение не подменяется.' : 'Выбери текстовую модель. Каталог не выбирает её автоматически.');
    }
    return lines.join('\n') || 'Статус аккаунта ещё не запрошен.';
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
          toast(pending.action === 'acceptDefaults' ? 'Записаны только показанные рекомендации. Остальной черновик не сохранён.' : 'Рекомендации отклонены. config.env не изменён.');
        }
        if (transforming && (state.lanEdit || 0) <= pending.clock) state.lan = !!(receipt.lanEnabled ?? pending.lan);
        // A handled callback is not proof of a disk write or a running generator.
        if (['save','start','forceRestart'].includes(pending.action) && (receipt.status === 'succeeded' || /^saved:/i.test(remote.status || ''))) {
          if(!receipt.savedValues || !receipt.savedRevision) {
            reconcilePersistedValues(pending,{...receipt,savedValues:receipt.savedValues || saved},remote.defaults);
            if((state.lanEdit || 0) <= pending.clock && !receipt.savedValues) state.lan=state.baselineLan;
          }
          toast(pending.action !== 'save' ? (receipt.message || 'Процесс генератора запущен. Проверь соединение, чтобы подтвердить готовность.') : 'Настройки записаны в config.env.');
        } else if (pending.action === 'savePreset') toast('Профиль сохранён отдельно. config.env не изменён.');
        else if (transforming) toast('Изменения подготовлены. Сохрани конфигурацию, чтобы записать их на диск.');
        else if (pending.action !== 'exitStudio' && !defaultsDecision) toast(({start:'Запуск передан генератору. Его состояние — на рабочем столе.',stop:'Безопасная остановка завершена.',health:'Проверка соединения завершена. Состояние — на рабочем столе.',validate:'Проверка путей завершена.',trace:'Журнал обновлён. Источник и статус показаны над записями.',codexLogin:'Результат входа показан в статусе аккаунта.',codexStatus:'Статус аккаунта обновлён.',codexCatalog:'Каталог моделей обновлён.',codexPing:'Проверка аккаунта завершена.',codexLogout:'Выход из аккаунта обработан.',cancelTrace:'Обновление журнала отменено.',openConfig:'Сохранённая конфигурация открыта для просмотра.',openCache:'Открываем папку кеша.',clearTrace:'Очистка журнала завершена.'})[pending.action] || 'Действие обработано.');
      } else {
        const message = receipt.message || 'Действие не выполнено. Изменения сохранены в этой вкладке.';
        if (['acceptDefaults','declineDefaults'].includes(pending.action)) defaultsError(message);
        toast(message,true);
      }
      state.suppressToast=false;state.pending = null; clearTimeout(pending.timer);finished=pending;
      if(receipt.ok && ['applyPreset','savePreset'].includes(pending.action)) state.presetChoice=null;
      if (pending.action === 'exitStudio' && receipt.ok && receipt.status === 'succeeded') {
        state.shutdown=true;clearTimeout(state.pollTimer);$('#utility-dialog').close();
        $('#connection').innerHTML='<span class="status-dot"></span><span>Студия закрыта</span>';
        $('#workspace').innerHTML='<div class="initial-loading"><h1>Студия закрыта</h1><p>Закрыта только студия. Генератор не остановлен этим действием.<br>Эту вкладку можно закрыть.</p></div>';
        updateActionButtons();return true;
      }
      if (receipt.result?.kind === 'document') showDocument(receipt.result);
      if (receipt.result?.kind === 'guide' && receipt.result.url?.startsWith('/guide?')) utility(receipt.result.title || 'Инструкция', `<p class="dialog-copy">Интерактивное руководство открывается в отдельной вкладке.</p><a class="button button-primary" href="${esc(receipt.result.url)}" target="_blank" rel="noopener">Открыть руководство ↗</a>`);
      if (['applyPreset','browse','clearLora','useLora','resetSprite','savePreset'].includes(pending.action)) needsRender=true;
    }
    for (const notice of remote.notifications || []) {
      if (state.seenNotifications.has(notice.id)) continue;
      state.seenNotifications.add(notice.id);
      toast([notice.title,notice.message].filter(Boolean).join(' · '), notice.level !== 'info');
    }
    state.fields=makeFields(remote);
    recomputeDirty();
    if (state.page === 'configure' && $('#preset-select') && document.activeElement !== $('#preset-select')) $('#preset-select').value = state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    if (first || needsRender || previousPresentation !== presentation() || previousFields !== JSON.stringify(state.fields.map(f => [f.key,f.options])) || previousPresets !== JSON.stringify([remote.presets,remote.userPresets])) renderPreservingFocus();
    else if (state.page === 'operate') renderOperate();
    else if (state.page === 'diagnostics') updateDiagnostics();
    syncInputs();
    if ($('#account-status')) $('#account-status').textContent=accountText(state.page);
    $$('[data-account-auth]').forEach(element=>element.textContent=remote.account?.authenticated ? 'Вход выполнен':'Требуется вход');
    $('#version').textContent = `Версия ${remote.version || 'α'}`;
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
      if (!queued.ok || !queued.id) throw new Error('Локальный сервер не подтвердил очередь действия.');
      const pending = {id:queued.id,action:name,sent,clock,lan:sentLan,dirtyKeys,focus,timer:null};
      state.pending = pending;
      state.submission = null;
      pending.timer = setTimeout(() => {
        if (state.pending?.id !== queued.id) return;
        // Keep the pending submission protected after a timeout: an action may still finish.
        toast('Подтверждение задерживается. Изменения защищены; действие может ещё завершиться.',true);
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
    const locked = !state.connected || state.pending || state.posting || state.shutdown;
    $$('[data-action], [data-browse], [data-submit-action]').forEach(button => {button.disabled = !!locked;});
    const pendingAction=state.pending?.action || state.submission?.action;
    const progressLabels={save:'Сохраняем…',start:'Проверяем и запускаем…',health:'Проверяем соединение…',validate:'Проверяем пути…',trace:'Читаем журнал…',codexStatus:'Проверяем аккаунт…',codexCatalog:'Обновляем модели…',codexLogin:'Ожидаем вход…',codexPing:'Проверяем аккаунт…'};
    $$('[data-action]').forEach(button=>{
      if(button.dataset.action === pendingAction && progressLabels[pendingAction]) {
        // Keep the busy icon mounted across polls so its feedback stays smooth.
        if(!button.dataset.idleHtml) {
          button.dataset.idleHtml=button.innerHTML;
          button.innerHTML=`${icon('refresh')}${progressLabels[pendingAction]}`;
        }
        button.setAttribute('aria-busy','true');
      } else if(button.dataset.idleHtml) {button.innerHTML=button.dataset.idleHtml;delete button.dataset.idleHtml;button.removeAttribute('aria-busy');}
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
    const [,,title,subtitle] = routes[page];
    return `<div class="page-heading${page === 'operate' ? ' operate-heading':''}"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-note"><span class="draft-indicator" aria-hidden="true"></span><span data-draft-status>${draftStatusText()}</span></div></div>`;
  }
  function basename(path) { return String(path || '').split(/[\\/]/).pop() || ''; }
  function chosen(key,fallback='Не задано') { return String(value(key) || fallback); }
  function addressLabel(address,fallback='Адрес не задан') {
    if (!address) return fallback;
    try { const url=new URL(address);return `${url.hostname}${url.port ? `:${url.port}`:''}${url.pathname === '/' ? '' : url.pathname}`; }
    catch { return 'Проверь формат адреса'; }
  }
  function providerSummary() {
    const provider = value('INFINI_LLM_PROVIDER','local');
    if (value('INFINI_USE_LLM') === '0') return {name:'Текстовая модель выключена',detail:'Технический режим'};
    const modelKey = {local:'INFINI_LMSTUDIO_MODEL',openrouter:'INFINI_OPENROUTER_MODEL',openai_compat:'INFINI_OPENAI_COMPAT_MODEL',openai_codex:'INFINI_CODEX_LLM_MODEL'}[provider];
    const model = value(modelKey).trim();
    return {name:optionNames.INFINI_LLM_PROVIDER[provider] || provider,detail:!model ? provider === 'local' ? 'auto · выбор на сервере':'Модель не выбрана' : model === 'auto' && provider === 'local' ? 'auto · выбор на сервере':model};
  }
  function imageSummary() {
    const backend = value('INFINI_IMAGE_BACKEND','sdcpp');
    const modelKey = {sdcpp:'INFINI_SDCPP_MODEL',image_api:'INFINI_IMAGE_API_MODEL',openai_codex:'INFINI_CODEX_IMAGE_MODEL'}[backend];
    const model = backend === 'sdcpp' ? basename(value(modelKey)):value(modelKey).trim();
    if (backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1') return {name:'sd.cpp · внешний сервер',detail:addressLabel(value('INFINI_SDCPP_SERVER_URL'))};
    if (backend === 'a1111' || backend === 'comfyui') return {name:optionNames.INFINI_IMAGE_BACKEND[backend],detail:addressLabel(value(backend === 'a1111' ? 'INFINI_A1111_URL':'INFINI_COMFYUI_URL'))};
    return {name:optionNames.INFINI_IMAGE_BACKEND[backend] || backend,detail:backend === 'off' ? 'Генерация рисунка отключена':model || 'Модель не указана'};
  }
  function sourceSize() {
    const backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    if (backend === 'off') return 'Отключено';
    if (backend === 'sdcpp') return `${chosen('INFINI_SDCPP_WIDTH','—')} × ${chosen('INFINI_SDCPP_HEIGHT','—')}`;
    if (backend === 'openai_codex') return chosen('INFINI_CODEX_IMAGE_SIZE','auto');
    if (backend === 'image_api') return chosen('INFINI_IMAGE_API_SIZE','На стороне API');
    return 'На стороне источника';
  }
  function spriteSummary() {
    const off=value('INFINI_IMAGE_BACKEND') === 'off',transparent=value('INFINI_BG_COLOR') === 'transparent';
    const background=transparent ? 'Native alpha' : value('INFINI_REMOVE_BG') === '0' ? 'Фон сохраняется':'Chroma key';
    const colors=value('INFINI_PIXEL_POSTERIZE') === '1' ? `До ${chosen('INFINI_MAX_COLORS','—')} цветов`:'Без ограничения цветов';
    return {name:off ? 'Обработка отключена':`${chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()} · холст ${chosen('INFINI_SPRITE_MASTER_CANVAS','—')} px`,detail:off ? 'Изображения выключены':`${background} · ${colors.toLocaleLowerCase()}`,background,colors};
  }
  function healthSummary() {
    const home=state.remote?.home || {},raw=state.remote?.activity || '';
    const match=/Сервер отвечает|Идёт генерация/.test(home.state || '') && !state.remote?.busy?.includes('server-action') ? raw.match(/active=(\d+), waiting=(\d+), accepting=(True|False)/) : null;
    return {known:!!match,active:match ? match[1]:'—',waiting:match ? match[2]:'—',accepting:match ? match[3] === 'True' ? 'Открыт':'Закрыт':'—'};
  }
  function configStatus() {
    if (state.dirty.size || state.lan !== state.baselineLan) return {title:'Есть несохранённые изменения',detail:'Сводки настроек показывают черновик этой вкладки.',tone:'draft'};
    const applied=state.remote?.appliedConfig || '';
    if (/restart|mismatch|differs/i.test(applied)) return {title:'Нужен безопасный перезапуск',detail:'Последняя проверка обнаружила расхождение настроек с генератором.',tone:'attention'};
    if (/matches/i.test(applied)) return {title:'Проверенные параметры совпадают',detail:'По последней проверке. Ключи и дополнительные модели не проверены.',tone:'saved'};
    return {title:'Настройки сервера не сверены',detail:'Проверка соединения сравнит доступные параметры с сохранённым файлом.',tone:'unknown'};
  }
  function nextStep() {
    if (state.dirty.size || state.lan !== state.baselineLan) return {title:'Сохрани изменения',description:'Черновик ещё не записан в config.env.',route:'configure',link:'Открыть конфигурацию'};
    if(configStatus().tone === 'attention') return {title:'Примени сохранённые настройки',description:'Используй безопасный перезапуск в панели генератора.',route:'diagnostics',link:'Посмотреть состояние'};
    if(healthSummary().accepting === 'Закрыт') return {title:'Приём запросов закрыт',description:'Посмотри состояние генератора перед следующим крафтом.',route:'diagnostics',link:'Открыть диагностику'};
    if (/Сервер отвечает|Идёт генерация/.test(state.remote?.home?.state || '')) return {title:'Можно вернуться в Terraria',description:'Новые предметы создаются в игре с модом InfiniCrafterLocal.',route:'help',link:'Как начать крафт'};
    return {title:'Проверь соединение',description:'Получи состояние сохранённого или запущенного этой студией генератора.',route:'diagnostics',link:'Открыть диагностику'};
  }
  function configurationGaps() {
    const gaps=[],provider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp'),textEnabled=value('INFINI_USE_LLM') !== '0';
    if(value('INFINI_USE_LLM') === '0') gaps.push({title:'Текстовая модель выключена',detail:'Включить генерацию игровой механики',key:'INFINI_USE_LLM'});
    if(textEnabled && provider === 'local' && !value('INFINI_LMSTUDIO_URL').trim()) gaps.push({title:'Не указан адрес LM Studio',detail:'Добавить адрес текстового сервера',key:'INFINI_LMSTUDIO_URL'});
    if(textEnabled && provider === 'openrouter' && !value('INFINI_OPENROUTER_API_KEY').trim()) gaps.push({title:'Нет ключа OpenRouter',detail:'Подключить выбранный источник',key:'INFINI_OPENROUTER_API_KEY'});
    if(textEnabled && provider === 'openai_compat' && !value('INFINI_OPENAI_COMPAT_BASE_URL').trim()) gaps.push({title:'Не указан адрес API',detail:'Настроить источник текста',key:'INFINI_OPENAI_COMPAT_BASE_URL'});
    if(textEnabled && provider === 'openai_codex' && !value('INFINI_CODEX_LLM_MODEL').trim()) gaps.push({title:'Не выбрана текстовая модель',detail:'Указать модель Codex',key:'INFINI_CODEX_LLM_MODEL'});
    if((textEnabled && provider === 'openai_codex' || backend === 'openai_codex') && !state.remote?.account?.authenticated) gaps.push({title:'Нужен вход в Codex',detail:'Открыть настройки аккаунта',key:textEnabled && provider === 'openai_codex' ? 'INFINI_CODEX_LLM_MODEL':'INFINI_CODEX_IMAGE_MODEL'});
    if(backend === 'sdcpp') {
      if(value('INFINI_SDCPP_SERVER_AUTOSTART') === '1') {
        if(!value('INFINI_SDCPP_SERVER_EXE')) gaps.push({title:'Не выбрана программа sd.cpp',detail:'Указать путь к sd-server',key:'INFINI_SDCPP_SERVER_EXE'});
        if(!value('INFINI_SDCPP_MODEL')) gaps.push({title:'Не выбрана модель изображения',detail:'Указать файл локальных весов',key:'INFINI_SDCPP_MODEL'});
      } else if(!value('INFINI_SDCPP_SERVER_URL')) gaps.push({title:'Не указан адрес sd.cpp',detail:'Подключить внешний сервер изображений',key:'INFINI_SDCPP_SERVER_URL'});
    }
    if(backend === 'image_api' && !value('INFINI_IMAGE_API_BASE_URL')) gaps.push({title:'Не указан адрес Image API',detail:'Настроить источник изображений',key:'INFINI_IMAGE_API_BASE_URL'});
    return gaps;
  }
  function flowCards() {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary();
    const textProvider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    const textMeta=textProvider === 'openai_codex' ? `Effort: ${chosen('INFINI_LLM_REASONING_MODE','off')}` : `${chosen('INFINI_LLM_MAX_TOKENS','—')} токенов · t ${chosen('INFINI_LLM_TEMPERATURE','—')}`;
    const imageMeta=backend === 'sdcpp' ? `${sourceSize()} px · ${chosen('INFINI_SDCPP_STEPS','—')} шага` : backend === 'off' ? 'Изображения выключены':sourceSize();
    return `<ol class="pipeline-list">${[
      ['01','Текст и механика',provider.name,provider.detail,textMeta,'providers','text'],
      ['02','Исходное изображение',image.name,image.detail,imageMeta,'images','image'],
      ['03','Обработка спрайта',sprite.name,sprite.detail,value('INFINI_IMAGE_BACKEND') === 'off' ? 'Настройки сохранены':`Фон: ${optionNames.INFINI_BG_COLOR[value('INFINI_BG_COLOR')] || chosen('INFINI_BG_COLOR')}`,'sprites','pixel']
    ].map(([number,title,name,detail,meta,route,glyph]) => `<li><a class="pipeline-step flow-card" href="#${route}" data-flow-card><div class="flow-card-top"><span class="flow-index">${number}</span><span class="flow-title">${icon(glyph)}${title}</span><span class="step-arrow">${icon('arrow')}</span></div><h3>${esc(name)}</h3><p class="flow-detail">${esc(detail)}</p><div class="flow-card-meta">${esc(meta)}</div></a></li>`).join('')}</ol>`;
  }
  function homeActivity() {
    const health=healthSummary();
    return `<div class="server-readout">${[['Активных крафтов',health.active],['В очереди',health.waiting],['Приём запросов',health.accepting]].map(([label,val])=>`<div><span>${label}</span><strong>${val}</strong></div>`).join('')}</div><p class="readout-note">${health.known ? 'Последний ответ генератора. Обновляется при проверке соединения.':'Состояние очереди появится после проверки соединения.'}</p>`;
  }
  function serviceConnections() {
    const provider=value('INFINI_LLM_PROVIDER','local'),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    const textSource=providerSummary(),imageSource=imageSummary();
    const textAddress=provider === 'local' ? addressLabel(value('INFINI_LMSTUDIO_URL')) : provider === 'openai_compat' ? addressLabel(value('INFINI_OPENAI_COMPAT_BASE_URL')) : provider === 'openai_codex' ? state.remote.account?.authenticated ? 'Вход выполнен':'Нужен вход' : value('INFINI_OPENROUTER_API_KEY').trim() ? 'Ключ указан':'Ключ не указан';
    const imageAddress=backend === 'sdcpp' ? addressLabel(value('INFINI_SDCPP_SERVER_URL')) : backend === 'image_api' ? addressLabel(value('INFINI_IMAGE_API_BASE_URL')) : imageSource.detail;
    return `<div class="service-list"><a href="#providers" class="service-item"><span class="service-icon">${icon('text')}</span><div><strong>${esc(textSource.name)}</strong><span>${esc(textAddress)}</span><small>${provider === 'local' ? 'Запускается отдельно':'Внешний сервис'}</small></div>${icon('arrow')}</a><a href="#images" class="service-item"><span class="service-icon">${icon('image')}</span><div><strong>${esc(imageSource.name)}</strong><span>${esc(imageAddress)}</span><small>${backend === 'sdcpp' ? value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? 'Запускает генератор':'Запускается отдельно' : backend === 'off' ? 'Запросы изображений отключены':'Внешний сервис'}</small></div>${icon('arrow')}</a></div>`;
  }
  function renderOperate() {
    if (!state.remote || state.page !== 'operate') return;
    const home=state.remote.home || {},next=nextStep(),gaps=configurationGaps(),config=configStatus();
    const busy=state.remote.busy?.includes('server-action'),running=/Сервер отвечает|Идёт генерация/.test(home.state || '');
    const title=busy ? 'Проверяем состояние…':home.state || 'Состояние не проверено';
    const stationState=busy ? 'busy':running ? 'running':/внимание|подтверждено/.test(title) ? 'attention':'idle';
    const detail=title === 'Сервер отвечает' ? 'Генератор отвечает. Новые предметы создаются в Terraria.' : title === 'Состояние ещё не проверено' ? 'Запусти генератор или проверь уже работающий сервер.' : home.detail || 'Запусти генератор или проверь соединение.';
    const endpoint=`${state.remote.savedValues?.INFINI_HOST || '127.0.0.1'}:${state.remote.savedValues?.INFINI_PORT || '5055'}`;
    const hasTrace=Object.values(state.remote.trace || {}).some(raw=>typeof raw === 'string' && raw.trim());
    const signature=JSON.stringify([home,state.draft,state.lan,state.dirty.size,config,busy,state.remote.activity,state.remote.account?.authenticated,endpoint,hasTrace]);
    if(state.operateSignature === signature && $('.station')) {updateActionButtons();return;}
    state.operateSignature=signature;
    const focused=document.activeElement;
    const focusIdentity=focused?.closest('#workspace') ? ['id','data-action','data-ui','data-search-key','href'].map(name=>[name,focused.getAttribute(name)]).find(([,val])=>val) : null;
    $('#workspace').innerHTML=`${heading('operate')}
      <div class="dashboard-top"><section class="station" data-state="${stationState}" aria-labelledby="generator-title">
        <div class="station-top"><span class="serial">${icon('pulse')}Сервер генерации</span><span class="state-tag"><span class="status-dot"></span>${busy ? 'Проверка':running ? 'На связи':'Не подтверждён'}</span></div>
        <div class="station-content"><h2 id="generator-title">${esc(title)}</h2><p class="station-detail">${esc(detail)}</p></div>
        <div class="endpoint">${icon('network')}<span>${esc(endpoint)}</span><small>сохранённый адрес</small></div>
        ${homeActivity()}
        <div class="station-controls"><div class="station-buttons"><button class="button button-primary" data-action="start">${icon('play')}${running ? 'Безопасно перезапустить':'Запустить генератор'}<span class="start-arrow" aria-hidden="true">↗</span></button><button class="button" data-action="health" aria-label="Проверить сохранённый или запущенный генератор">${icon('refresh')}Проверить</button><button class="button button-small" data-ui="stop" title="Безопасно остановить генератор">${icon('stop')}Стоп</button></div><p class="station-caption">Запуск сохранит текущие настройки. Активный крафт защищён безопасным перезапуском.</p></div>
      </section><section class="setup-card${gaps.length ? ' has-gaps':''}" aria-labelledby="setup-title"><div class="section-kicker">${icon(gaps.length ? 'alert':'sliders')}Перед крафтом</div>${gaps.length ? `<h2 id="setup-title">Проверь настройки</h2><p>В текущей конфигурации есть пункты, требующие внимания.</p><div class="setup-list">${gaps.slice(0,3).map(gap=>`<button class="setup-item" data-search-key="${gap.key}"><span><strong>${gap.title}</strong><small>${gap.detail}</small></span>${icon('arrow')}</button>`).join('')}</div>` : `<h2 id="setup-title">Сервисы генерации</h2>${serviceConnections()}`}
        <div class="setup-foot">${gaps.length ? `${icon('help')}Показаны настройки этой вкладки.`:next.route === 'help' ? `<button class="text-button" data-ui="help">${next.link}${icon('arrow')}</button>`:`<a class="text-button" href="#${next.route}">${next.link}${icon('arrow')}</a>`}</div>
      </section></div>
      <section class="pipeline" aria-labelledby="pipeline-title"><div class="section-heading"><h2 id="pipeline-title">Конфигурация крафта</h2><a class="text-button" href="#configure">Профили и все настройки ${icon('arrow')}</a></div>${flowCards()}<div class="pipeline-foot"><span class="profile-chip">${icon('sliders')}${esc(value('INFINI_GUI_PIPELINE_PRESET') || 'Свои настройки')}</span><span>${state.dirty.size || state.lan !== state.baselineLan ? 'Показан черновик':'Показаны сохранённые настройки'}</span></div></section>
      <div class="dashboard-bottom"><a href="#multiplayer" class="utility-card" data-flow-card><span class="utility-icon">${icon('network')}</span><div><h2>Соединение с игрой</h2><p>${state.lan ? 'LAN / Radmin':'Этот компьютер'} · ${value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? 'Спрайты по HTTP':'Спрайты внутри Terraria'}</p></div>${icon('arrow')}</a><a href="#diagnostics" class="utility-card" data-flow-card><span class="utility-icon">${icon('pulse')}</span><div><h2>Журнал генерации</h2><p>${Object.values(state.remote.trace || {}).some(raw=>typeof raw === 'string' && raw.trim()) ? 'Есть загруженные записи':'Промпты, этапы и ошибки последнего крафта'}</p></div>${icon('arrow')}</a></div>
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
    return `<div class="field-row${state.dirty.has(key) ? ' is-dirty':''}" data-field-row="${key}"><div class="field-copy"><div class="field-label-line"><label for="${id}">${esc(title)}</label><button class="field-help-toggle" data-help-field="${key}" type="button" aria-label="Подробности: ${esc(title)}" aria-expanded="${help}">?</button></div><div class="field-key${help ? '':' hidden-key'}">${key}</div><p class="field-help" id="help-${key}">${esc(help ? field.help || shortHelp[key] || 'Параметр локального генератора. Значение сохраняется без преобразования.' : shortHelp[key] || '')}</p>${browse && !field.secret ? `<span class="field-file" data-file-basename="${key}" title="${esc(val)}" ${val.trim() ? '':'hidden'}>${esc(basename(val))}</span>`:''}</div><div class="field-control${field.secret || browse ? ' has-extra':''}">${control}${inactive && !derived ? `<span class="field-note" data-inactive-source>${esc(inactive)}</span>`:''}</div></div>`;
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
      ['queue','Очередь и ожидание','Нагрузка на источник изображений.',['INFINI_IMAGE_MAX_CONCURRENCY','INFINI_CODEX_IMAGE_TIMEOUT','INFINI_IMAGE_API_TIMEOUT']]
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
    return (sectionDefinitions[page] || []).map(([id,title,description,keys])=>({id,title,description,fields:keys.map(key=>fields.find(field=>field.key === key)).filter(field=>field && (page === 'models' || !inactiveReason(field)))})).filter(section=>section.fields.length);
  }
  function fieldGroups(fields,force=false) {
    if(!fields.length) return '<div class="empty-search">В этом разделе ничего не найдено. Попробуй другое слово.</div>';
    if(force) return `<div class="section-fields search-field-results">${fields.map(field=>fieldHTML(field,true)).join('')}</div>`;
    const sections=pageSections(state.page,fields),used=new Set(sections.flatMap(section=>section.fields.map(field=>field.key)));
    const remaining=fields.filter(field=>!used.has(field.key));
    const active=remaining.filter(field=>!inactiveReason(field)),inactive=remaining.filter(field=>inactiveReason(field));
    const pools=[2,3,4].map(number=>active.filter(field=>field.key.startsWith(`INFINI_LLM_POOL_${number}_`)));
    const fallback=active.filter(field=>field.key.startsWith('INFINI_LLM_FALLBACK_'));
    const advanced=active.filter(field=>!pools.flat().includes(field) && !fallback.includes(field));
    return sections.map((section,index)=>`<section class="parameter-section" data-inactive-section="${state.page === 'models' && section.fields.every(field=>inactiveReason(field))}" aria-labelledby="section-${state.page}-${section.id}"><header class="parameter-heading"><span class="section-number">${String(index+1).padStart(2,'0')}</span><div><h2 id="section-${state.page}-${section.id}" tabindex="-1">${section.title}</h2><p>${section.description}${state.page === 'models' && section.fields.every(field=>inactiveReason(field)) ? '<span class="section-inactive-label">Сохранено · не используется в текущем режиме</span>':''}</p></div></header><div class="section-fields">${section.fields.map(field=>fieldHTML(field)).join('')}</div>${state.page === 'models' && section.id === 'lora' ? `<div class="section-actions"><button class="button" data-action="useLora">Применить выбранную LoRA ${icon('arrow')}</button><button class="text-button" data-ui="clear-lora">Отключить LoRA</button><p>Отключение сбросит настройки адаптера. Файл на диске останется.</p></div>`:''}</section>`).join('')+
      pools.map((group,index)=>disclosure(`pool-${index+2}`,`Дополнительная линия ${index+2} · ${value(`INFINI_LLM_POOL_${index+2}_ENABLED`) === '1' ? 'включена':'выключена'}`,group,'Собственный источник, адрес и модель для дополнительной линии.')).join('')+
      disclosure(`${state.page}-fallback`,'Резервный источник',fallback,'Используется при настроенных условиях переключения.')+
      disclosure(`${state.page}-advanced`,'Тонкая настройка',advanced,'Дополнительные параметры текущего источника.')+
      disclosure(`${state.page}-inactive`,'Другие источники и неактивные параметры',inactive,'Значения доступны для редактирования. Причина неактивности указана у каждого поля.');
  }
  function summaryMetric(label,val,detail,glyph,extra='') {
    return `<div class="summary-metric${extra}"><span class="summary-label">${icon(glyph)}${esc(label)}</span><strong>${esc(val)}</strong><p>${esc(detail)}</p></div>`;
  }
  function pageOverview(page) {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary(),backend=value('INFINI_IMAGE_BACKEND','sdcpp');
    let metrics='';
    if(page === 'providers') {
      const count=[2,3,4].filter(n=>value(`INFINI_LLM_POOL_${n}_ENABLED`) === '1').length;
      metrics=summaryMetric(provider.name,provider.detail,value('INFINI_USE_LLM') === '0' ? 'Текстовая генерация выключена':'Выбранная текстовая модель','text',' summary-primary')+
        summaryMetric('Рассуждение',optionNames.INFINI_LLM_REASONING_MODE[value('INFINI_LLM_REASONING_MODE')] || chosen('INFINI_LLM_REASONING_MODE'),`Ожидание стадии: ${chosen('INFINI_LLM_TIMEOUT','—')} с`,'sliders')+
        summaryMetric('Дополнительные линии',count ? `Включено: ${count}`:'Выключены',count ? 'Собственные источники и модели':'Настроена только основная линия','stack');
    } else if(page === 'images') {
      metrics=summaryMetric('Источник изображения',image.name,image.detail,'image',' summary-primary')+
        summaryMetric('Размер исходника',sourceSize(),backend === 'off' ? 'Генерация рисунка отключена':'До удаления фона и уменьшения','expand')+
        summaryMetric(backend === 'sdcpp' ? 'Параметры sd.cpp':'Качество и очередь',backend === 'sdcpp' ? `${chosen('INFINI_SDCPP_STEPS','—')} шага` : backend === 'openai_codex' ? optionNames.INFINI_CODEX_IMAGE_QUALITY[value('INFINI_CODEX_IMAGE_QUALITY')] || chosen('INFINI_CODEX_IMAGE_QUALITY') : backend === 'off' ? 'Отключено':`${chosen('INFINI_IMAGE_MAX_CONCURRENCY','—')} параллельно`,backend === 'sdcpp' ? `CFG ${chosen('INFINI_SDCPP_CFG','—')} · ${chosen('INFINI_SDCPP_SAMPLER')}`:backend === 'off' ? 'Настройки обработки сохранены':`Лимит изображений: ${chosen('INFINI_IMAGE_MAX_CONCURRENCY','—')}`,'sliders');
    } else if(page === 'sprites') {
      metrics=backend === 'off' ? summaryMetric('Обработка изображения','Не используется','Источник изображений выключен','image',' summary-primary')+summaryMetric('Промежуточный холст','Не используется',`Сохранено: ${chosen('INFINI_SPRITE_MASTER_CANVAS','—')} px · ${chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()}`,'pixel')+summaryMetric('Палитра','Не используется',`Сохранено: ${sprite.colors.toLocaleLowerCase()}`,'sliders') :
        summaryMetric('Фон исходника',sprite.background,optionNames.INFINI_BG_COLOR[value('INFINI_BG_COLOR')] || chosen('INFINI_BG_COLOR'),'image',' summary-primary')+
        summaryMetric('Промежуточный холст',`${chosen('INFINI_SPRITE_MASTER_CANVAS','—')} px`,`${chosen('INFINI_SPRITE_DOWNSCALE_FILTER','box').toUpperCase()} · ${value('INFINI_SPRITE_PREMULTIPLIED_RESIZE') === '1' ? 'с учётом прозрачности':'обычное уменьшение'}`,'pixel')+
        summaryMetric('Палитра',sprite.colors,value('INFINI_PIXEL_POSTERIZE') === '1' ? 'Постеризация включена':'Исходные цвета сохраняются','sliders');
    } else if(page === 'models') {
      const managed=backend === 'sdcpp' && value('INFINI_SDCPP_SERVER_AUTOSTART') === '1',lora=basename(value('INFINI_SDCPP_LORA_FILE'));
      metrics=summaryMetric('Управление моделями',managed ? 'Из этой студии':backend === 'sdcpp' ? 'Внешний sd.cpp':'Другой источник',managed ? basename(value('INFINI_SDCPP_MODEL')) || 'Основная модель не указана':backend === 'sdcpp' ? 'Основные веса выбирает сервер':image.name,'stack',' summary-primary')+
        summaryMetric('Адаптер LoRA',backend !== 'sdcpp' ? 'Не используется':lora || 'Не выбран',backend !== 'sdcpp' ? lora ? `Сохранено: ${lora}`:'sd.cpp не используется' : lora ? `Сила: ${chosen('INFINI_SDCPP_LORA_WEIGHT','—')}`:'Без художественного адаптера','sliders')+
        summaryMetric('Сервер изображений',backend === 'sdcpp' ? addressLabel(value('INFINI_SDCPP_SERVER_URL')):image.name,'Выбор источника — в разделе «Изображения»','network');
    } else if(page === 'multiplayer') {
      const host=derivedField('INFINI_HOST')?.value || chosen('INFINI_HOST','127.0.0.1');
      metrics=summaryMetric(state.lan ? 'Режим LAN / Radmin':'Интерфейс генератора',`${host}:${chosen('INFINI_PORT','5055')}`,'Адрес из текущих настроек','network',' summary-primary')+
        summaryMetric('Доставка спрайтов',value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? 'По HTTP':'Внутри Terraria',value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? state.lan ? addressLabel(value('INFINI_ASSET_PUBLIC_BASE_URL'),'Публичный адрес не задан'):'Публичный адрес не используется: LAN выключен':'Без отдельного HTTP-адреса для ассетов','image')+
        summaryMetric('Порт Terraria',chosen('INFINI_TERRARIA_PORT','7777'),'Порт игрового сервера','work');
    } else if(page === 'diagnostics') {
      const health=healthSummary(),config=configStatus();
      metrics=summaryMetric('Генератор',state.remote.home?.state || 'Не проверен',`${state.remote.savedValues?.INFINI_HOST || '127.0.0.1'}:${state.remote.savedValues?.INFINI_PORT || '5055'} · сохранённый адрес`,'pulse',' summary-primary')+
        summaryMetric('Последняя проверка',health.known ? `${health.active} активных · ${health.waiting} в очереди`:'Нет данных',health.known ? `Приём запросов: ${health.accepting.toLocaleLowerCase()}`:'Нажми «Проверить соединение»','refresh')+
        summaryMetric('Конфигурация',config.title,config.detail,'sliders');
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
    const related={configure:['operate','Проверить генератор'],providers:['images','Источник изображения'],images:['models','Файлы моделей и LoRA'],sprites:['images','Параметры исходника'],models:['images','Способ запуска sd.cpp'],multiplayer:['diagnostics','Проверить соединение'],diagnostics:['multiplayer','Настроить адрес']}[page];
    const total=state.dirty.size+Number(state.lan !== state.baselineLan);
    return `<aside class="settings-aside">${sections.length ? `<nav class="section-nav" aria-label="Разделы этой страницы"><h2>На этой странице</h2>${sections.map((section,index)=>`<button data-section-link="section-${page}-${section.id}"><span>${String(index+1).padStart(2,'0')}</span>${section.title}</button>`).join('')}</nav>`:''}${related ? `<a class="related-page" href="#${related[0]}"><span>Связанный раздел<strong>${related[1]}</strong></span>${icon('arrow')}</a>`:''}<div class="save-panel${total ? ' is-dirty':''}"><div class="aside-heading"><h2>${icon('save')}Конфигурация</h2></div><strong data-dirty-count>${total ? `${total} несохранённых изменений`:'Изменений нет'}</strong><p>Сохрани настройки перед перезапуском генератора.</p><button class="button" data-action="save">Сохранить <kbd>Ctrl S</kbd></button></div><details class="config-file"><summary>${icon('folder')}Файл настроек</summary><code>${esc(state.remote.configPath || 'config.env')}</code><button class="text-button" data-action="openConfig">Открыть файл ${icon('arrow')}</button></details></aside>`;
  }
  function defaultsSummary() {
    const offer=state.remote?.defaultsUpdate,count=offer?.changes?.length || 0;
    if(!count) return 'Новых рекомендаций нет.';
    if(offer.dismissed) return `Рекомендации ${offer.version || ''} отложены. Доступны для сравнения.`;
    return `Доступно ${count} рекомендаций ${offer.version || ''}. Сравни изменения перед применением.`;
  }
  function configureSummaryCards() {
    const provider=providerSummary(),image=imageSummary(),sprite=spriteSummary();
    return [
      ['text','providers','Текст и механика',provider.name,provider.detail],
      ['image','images','Источник изображения',image.name,image.detail],
      ['pixel','sprites','Спрайты и цвет',sprite.name,sprite.detail],
      ['stack','models','Модели и LoRA',value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? 'sd.cpp не используется':basename(value('INFINI_SDCPP_LORA_FILE')) || 'LoRA не выбрана',value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? `Текущий источник: ${image.name}`:value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? 'Управляемый запуск sd.cpp':'Основные модели выбирает внешний sd.cpp'],
      ['network','multiplayer','Совместная игра',state.lan ? 'LAN / Radmin':'Этот компьютер',value('INFINI_MP_ASSET_TRANSPORT') === 'http' ? 'Доставка спрайтов по HTTP':'Доставка спрайтов внутри Terraria'],
      ['pulse','diagnostics','Диагностика',value('INFINI_TRACE_PROMPTS') === '1' ? 'Запись промптов включена':'Запись промптов выключена',`Лимит просмотра: ${chosen('INFINI_TRACE_EVENTS_TAIL','—')} событий`]
    ];
  }
  function updateConfigureSummary() {
    const profile=$('#current-profile-name');if(profile) profile.textContent=value('INFINI_GUI_PIPELINE_PRESET') || 'Свои настройки';
    const label=$('#configure-selection-status');if(label) label.textContent=state.dirty.size || state.lan !== state.baselineLan ? 'Черновик этой вкладки':'Сохранённая конфигурация';
    for(const [,route,,summary,detail] of configureSummaryCards()) {
      const main=$(`[data-config-value="${route}"]`),copy=$(`[data-config-detail="${route}"]`);
      if(main) main.textContent=summary;if(copy) copy.textContent=detail;
    }
  }
  function renderConfigure() {
    const selected=state.presetChoice ?? value('INFINI_GUI_PIPELINE_PRESET');
    const presetEntries=[...Object.keys(state.remote.presets || {}),...Object.keys(state.remote.userPresets || {}).map(name=>`Мой: ${name}`)];
    const cards=configureSummaryCards();
    $('#workspace').innerHTML=`${heading('configure')}<div class="settings-layout"><div class="settings-main"><section class="preset-sheet profile-sheet"><div class="profile-heading"><span class="profile-symbol">${icon('sliders')}</span><div><span class="eyebrow">Текущая конфигурация</span><h2 id="current-profile-name">${esc(value('INFINI_GUI_PIPELINE_PRESET') || 'Свои настройки')}</h2></div></div><div class="preset-selector"><select id="preset-select" aria-label="Профиль настроек"><option value="">Выбери профиль…</option>${presetEntries.map(name=>`<option value="${esc(name)}" ${name === selected ? 'selected':''}>${esc(name)}</option>`).join('')}</select><button class="button" data-ui="apply-preset">Сравнить и применить ${icon('arrow')}</button></div><div class="profile-foot"><p>Применение профиля меняет черновик. Ключи остаются твоими.</p><button class="text-button" data-ui="save-preset">Сохранить как профиль ${icon('save')}</button></div></section><div class="section-heading"><h2>Что настроено сейчас</h2><span class="meta" id="configure-selection-status">${state.dirty.size || state.lan !== state.baselineLan ? 'Черновик этой вкладки':'Сохранённая конфигурация'}</span></div><div class="configure-index">${cards.map(([glyph,route,title,summary,detail])=>`<a class="index-row" href="#${route}" data-flow-card><div class="index-card-top"><span class="index-number">${icon(glyph)}</span><h3>${title}</h3>${icon('arrow')}</div><strong data-config-value="${route}">${esc(summary)}</strong><p data-config-detail="${route}">${esc(detail)}</p></a>`).join('')}</div><section class="recommendation-row"><span class="recommendation-icon">${icon('refresh')}</span><div><h2>Рекомендации к настройкам</h2><p id="defaults-summary">${esc(defaultsSummary())}</p></div><button class="text-button" data-ui="defaults-update">Посмотреть ${icon('arrow')}</button></section>${disclosure('all-settings','Все параметры одним списком',state.fields,'Все настройки config.env, включая служебные поля и параметры других источников.')}</div>${aside('configure')}</div>`;
  }
  function pageExtras(page) {
    if(page === 'providers' && value('INFINI_LLM_PROVIDER') === 'openai_codex' || page === 'images' && value('INFINI_IMAGE_BACKEND') === 'openai_codex') return `<section class="account-panel"><div class="account-panel-heading"><h2>${icon('work')}Аккаунт ChatGPT / Codex</h2><span class="small-badge" data-account-auth>${state.remote.account?.authenticated ? 'Вход выполнен':'Требуется вход'}</span></div><p>Вход по подписке. Текст и изображения используют отдельные модели.</p><div class="page-actions"><button class="button" data-action="codexLogin">Войти в Codex ${icon('arrow')}</button><button class="button" data-action="codexStatus">Статус аккаунта</button><button class="text-button" data-action="codexLogout">Выйти</button>${page === 'providers' ? '<button class="button" data-action="codexCatalog">Обновить модели</button>':'<button class="button" data-action="codexPing">Проверить аккаунт</button>'}</div><div class="account-status-panel"><p id="account-status">${esc(accountText(page))}</p></div></section>`;
    if(page === 'images' && value('INFINI_IMAGE_BACKEND') === 'sdcpp') return `<div class="context-banner">${icon('stack')}<p>${value('INFINI_SDCPP_SERVER_AUTOSTART') === '1' ? 'Управляемый запуск: программа и веса выбираются в разделе «Модели и LoRA».':'Внешний sd.cpp запускается отдельно. Здесь настраиваются его адрес и параметры запросов.'}</p><a class="text-button" href="#models">Модели и LoRA ${icon('arrow')}</a></div>`;
    if(page === 'sprites') return `<div class="page-actions sprite-actions"><button class="button" data-ui="reset-sprite">${icon('refresh')}Вернуть базовый BOX</button><button class="text-button" data-action="openCache" title="Открыть папку кеша на компьютере генератора">${icon('folder')}Папка спрайтов и кеша</button>${value('INFINI_IMAGE_BACKEND') === 'off' ? '<span class="small-badge">Обработка неактивна: изображения выключены</span>':''}</div>`;
    if(page === 'models') return `<div class="context-banner">${icon('stack')}<p>${value('INFINI_IMAGE_BACKEND') !== 'sdcpp' ? 'Сейчас выбран другой источник изображений. Эти файлы используются только с sd.cpp.':value('INFINI_SDCPP_SERVER_AUTOSTART') !== '1' ? 'Внешний sd.cpp выбирает основные модели при своём запуске. Для управления файлами здесь включи управляемый запуск.':'Генератор использует эти файлы при запуске sd.cpp. Проверка путей не запускает создание изображения.'}</p><button class="button" data-action="validate">${icon('check')}Проверить пути</button></div>`;
    if(page === 'multiplayer') return `<div class="network-mode"><div><h2 id="lan-title">Режим LAN / Radmin</h2><p>Доступ по сети к генератору. Студия остаётся на этом компьютере.</p></div><label class="toggle-control"><input id="lan-enabled" type="checkbox" aria-labelledby="lan-title" data-lan ${state.lan ? 'checked':''}><span class="toggle-track"></span><span class="toggle-label">${state.lan ? 'Включено':'Выключено'}</span></label></div>`;
    return '';
  }
  function renderSettings(page) {
    let fields=state.fields.filter(field=>field.route === page);
    if(state.filter) fields=fields.filter(field=>matches(field,state.filter));
    $('#workspace').innerHTML=`${heading(page)}<div id="page-overview">${pageOverview(page)}</div><div class="settings-layout"><div class="settings-main">${pageExtras(page)}${page === 'diagnostics' ? diagnosticsMarkup():''}<div class="settings-toolbar"><label class="inline-search">${icon('search')}<input id="page-search" placeholder="Найти в этом разделе…" value="${esc(state.filter)}" autocomplete="off" aria-label="Поиск в разделе"></label><span class="field-counter">${fields.length} параметров${state.filter ? ' найдено':''}</span></div><div class="field-section">${page === 'diagnostics' && !state.filter ? disclosure('diagnostic-settings','Запись журнала и отладка',fields,'Параметры записи и технические режимы генератора.'):fieldGroups(fields,!!state.filter)}</div>${page === 'diagnostics' ? `<details class="advanced emergency-controls"><summary>Аварийное управление</summary><p class="details-note">Принудительный перезапуск прерывает активный крафт. Требуется подтверждение.</p><div class="page-actions"><button class="button button-danger" data-ui="force-restart">Принудительный перезапуск…</button></div></details>`:''}</div>${aside(page)}</div>`;
    if(page === 'diagnostics') updateDiagnostics();
  }
  function diagnosticsMarkup() {
    const tabs={summary:'Сводка',events:'События',prompts:'Промпты',pipeline:'Этапы',sdcpp:'sd.cpp',failure:'Ошибка'};
    return `<section class="diagnostic-workspace"><div class="journal-heading"><div><h2>Журнал крафта</h2><p>Последние доступные записи генератора или локального кеша.</p></div><button class="button button-primary" data-action="trace">${icon('refresh')}Обновить журнал</button></div><div class="page-actions diagnostic-actions"><button class="button" data-action="health">${icon('pulse')}Проверить соединение</button><button class="text-button" data-action="openCache" title="Открыть папку кеша на компьютере генератора">${icon('folder')}Папка кеша</button><button class="text-button" data-action="cancelTrace">Отменить обновление</button><button class="text-button" data-ui="clear-trace">Очистить…</button></div><p id="trace-status" class="trace-status" role="status"></p><div class="trace-tabs" role="tablist" aria-label="Разделы журнала">${Object.entries(tabs).map(([key,name])=>`<button id="tab-${key}" role="tab" aria-controls="trace-view" aria-selected="${key === state.traceTab}" tabindex="${key === state.traceTab ? '0':'-1'}" class="${key === state.traceTab ? 'active':''}" data-trace-tab="${key}">${name}</button>`).join('')}</div><div id="trace-view" class="trace-view" role="tabpanel" aria-labelledby="tab-${state.traceTab}" tabindex="0"></div><details class="diagnostic-raw"><summary>${icon('pulse')}Подробный ответ сервера</summary><p class="details-note">Соединение и журнал используют сохранённую конфигурацию или сервер, запущенный этой студией.</p><div id="diagnostic-status" class="diagnostic-status"></div></details></section>`;
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
          '<h3>Сохранённой ошибки нет</h3><p>В этом снимке нет сохранённого отчёта о сбое крафта.</p></section>';
      }
      if (!object(data)) return null;
      const serialized = JSON.stringify(data, null, 2);
      if (typeof serialized !== 'string') return null;
      const rawDetails = '<details class="trace-inspector-raw"><summary>Полный снимок</summary><pre>' +
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
          readout('HTTP-ответ', alive === true ? 'Есть ответ' : alive === false ? 'Нет ответа' : probed ? 'Нет данных' : 'Не проверен',
            alive === null ? (probed ? 'Результат не указан' : 'HTTP-проверка не выполнена') : 'На момент снимка',
            alive === true ? 'positive' : alive === false && managed === false ? 'attention' : 'neutral'),
          readout('Управляемый процесс', process === true ? 'Работает' : exited ? 'Завершён' : process === false ? 'Не работает' : 'Нет данных',
            exited ? 'Код выхода: ' + data.processReturncode : 'Отдельно от HTTP-ответа'),
          readout('Запуск', managed === true ? 'По требованию' : managed === false ? 'Внешний сервер' : 'Нет данных',
            managed === true ? 'Автозапуск включён' : managed === false ? 'Запускается отдельно' : '')
        ];
        if (managed === true && typeof data.serverConfigured === 'boolean') {
          rows.push(readout('Локальная конфигурация', data.serverConfigured ? 'Задана' : 'Не настроена', 'Параметры запуска'));
        }
        const endpoint = text(data.serverUrl);
        const startError = text(data.lastStartError);
        return '<section class="trace-inspector" data-trace-kind="sdcpp">' +
          head('image', 'Сервер изображений', 'sd.cpp') +
          (endpoint ? '<p class="trace-inspector-context"><code>' + esc(endpoint) + '</code></p>' : '') +
          '<dl class="trace-readouts">' + rows.join('') + '</dl>' +
          (startError ? '<p class="trace-inspector-message"><strong>Сохранённая ошибка запуска</strong>' +
            esc(shorten(startError)) + '</p>' : '') + rawDetails + '</section>';
      }

      const stage = text(data.stage), error = text(data.error);
      if (data.ok !== false || !stage && !error) return null;
      const rows = [];
      if (stage) rows.push(readout('Этап', stage));
      if (text(data.time)) rows.push(readout('Время записи', text(data.time)));
      const transport = object(data.transportDebug) ? data.transportDebug : {};
      if (Number.isInteger(transport.httpStatus) && transport.httpStatus >= 100 && transport.httpStatus <= 599) {
        rows.push(readout('HTTP', String(transport.httpStatus)));
      }
      if (text(data.version)) rows.push(readout('Версия генератора', text(data.version)));
      const parents = object(data.parents) ? [text(data.parents.a), text(data.parents.b)].filter(Boolean) : [];
      return '<section class="trace-inspector" data-trace-kind="failure">' +
        head('alert', 'Сохранённый отчёт', 'Последний сбой крафта') +
        (parents.length ? '<p class="trace-inspector-context">Крафт: ' + esc(shorten(parents.join(' + '))) + '</p>' : '') +
        '<p class="trace-inspector-message">' + esc(shorten(error) || 'Текст ошибки не сохранён.') + '</p>' +
        (rows.length ? '<dl class="trace-readouts">' + rows.join('') + '</dl>' : '') +
        rawDetails + '</section>';
    } catch {
      return null;
    }
  }

  function updateDiagnostics() {
    if(!$('#diagnostic-status')) return;
    $('#diagnostic-status').textContent=[state.remote.status,state.remote.appliedConfig,state.remote.activity].filter(Boolean).join('\n\n');
    $('#trace-status').textContent=(state.remote.traceStatus || 'Журнал ещё не запрошен.').replace('Нажми Refresh trace. Если сервер не запущен, Studio показывает локальные cache/*.ndjson.','Обнови журнал. Если генератор недоступен, студия покажет записи локального кеша.');
    const raw=state.remote.trace?.[state.traceTab] ?? (state.traceTab === 'failure' ? state.remote.trace?.last_failure:undefined);
    const view=$('#trace-view'),key=JSON.stringify([state.traceTab,raw]);
    if(view._traceKey !== key) {
      const keepOpen=view._traceTab === state.traceTab && !!view.querySelector('.trace-inspector-raw[open]');
      const inspector=raw === undefined || raw === '' ? null:traceContent(raw,state.traceTab);
      view.classList.toggle('is-empty',inspector === null && (!raw || typeof raw === 'string' && !raw.trim()));
      if(inspector !== null) {view.innerHTML=inspector;if(keepOpen) view.querySelector('.trace-inspector-raw')?.setAttribute('open','');}
      else if(view.classList.contains('is-empty')) view.innerHTML=`${icon('pulse')}<h3>Нет загруженных записей</h3><span>Нажми «Обновить журнал», чтобы получить промпты, этапы и ошибки крафта.</span>`;
      else view.textContent=typeof raw === 'string' ? raw:JSON.stringify(raw,null,2);
      view._traceKey=key;view._traceTab=state.traceTab;
    }
    updatePageOverview();
  }
  function render() {
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
    const target=key ? $(`[data-field="${key}"]`) : id ? document.getElementById(id) : null;
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
      if (input.type === 'checkbox' && input.parentElement.querySelector('.toggle-label')) input.parentElement.querySelector('.toggle-label').textContent = input.checked ? 'Включено':'Выключено';
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
    $('#crumb').textContent = routes[state.page][0];document.title = `${routes[state.page][0]} — Infinicraft`;
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
    const changed=[...new Set([...Object.keys(state.revisionValues || {}),...Object.keys(disk)])].filter(key=>disk[key] !== state.revisionValues?.[key]);
    const display=(key,val)=>isCredentialKey(key) ? (val ? '••••••••':'Не задано') : val || 'Не задано';
    utility('Конфигурация изменилась на диске', `<p class="dialog-copy">Другой процесс или вкладка сохранили настройки после начала твоего черновика. Проверь изменения ниже. Твои правки останутся в этой вкладке; сохранение потребует отдельного нажатия.</p><div class="confirm-list">${changed.map(key=>`<div><span>${esc(names[key] || key)}<small>На диске: ${esc(display(key,disk[key]))}</small></span><span>Черновик: ${esc(display(key,value(key)))}</span></div>`).join('')}</div><div class="dialog-actions"><button class="button" data-ui="close-dialog">Вернуться</button><button class="button button-primary" id="reconcile-draft">Продолжить с моими правками</button></div>`);
    const revision=state.remote.savedRevision;
    $('#reconcile-draft').onclick=()=>{
      // Polling may have observed a second writer while this comparison was
      // open. Never acknowledge a revision different from the reviewed one.
      if(!state.remote.savedRevision) {toast('Не удалось проверить конфигурацию на диске. Дождись восстановления чтения и обнови сравнение.',true);return;}
      if(state.remote.savedRevision !== revision) {showSaveConflict();$('#utility-dialog [data-ui="close-dialog"]').focus({preventScroll:true});toast('Конфигурация изменилась ещё раз. Сравнение обновлено; проверь новые значения перед продолжением.',true);return;}
      const edits=Object.fromEntries([...state.dirty].map(key=>[key,state.draft[key]]));
      state.draft={...disk,...edits};state.baseline={...disk};state.savedRevision=revision;state.revisionValues={...disk};
      $('#utility-dialog').close();recomputeDirty();render();toast('Черновик сохранён в этой вкладке. Проверь его и нажми «Сохранить», когда будешь готов.');
    };
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
    const preview=state.defaultsPreview;
    if (!preview) return;
    const request=preview.refreshRequest=(preview.refreshRequest || 0)+1;
    // A dismissed/replaced preview or newer refresh owns the dialog now. Do
    // not apply an obsolete snapshot or reopen the old consent surface.
    const current=()=>state.defaultsPreview === preview && preview.refreshRequest === request && $('#utility-dialog').open && $('#utility-dialog').dataset.kind === 'defaults' && !state.pending && !state.posting;
    try {const remote=await api('/api/state');if(current() && acceptSnapshot(remote)) showDefaultsUpdate();}
    catch(error) {if(current()) defaultsError(error.message);}
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
      if(key === 'INFINI_LLM_PROVIDER') state.fields=makeFields(state.remote);
      if(target.tagName === 'SELECT' || target.type === 'checkbox') {const selection=key;render();$(`[data-field="${selection}"]`)?.focus({preventScroll:true});}
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
    if(target.matches('[data-lan]')) {state.lan=target.checked;state.lanEdit=++state.editClock;target.parentElement.querySelector('.toggle-label').textContent=target.checked?'Включено':'Выключено';recomputeDirty();render();$('#lan-enabled')?.focus({preventScroll:true});}
    if(target.id === 'file-path' && state.picker) {state.picker.request++;state.picker.selection=null;$('#file-select').disabled=true;$('#file-selection').textContent='Нажми «Открыть», чтобы проверить новый путь.';$$('[data-file-index]').forEach(row=>row.classList.remove('selected'));}
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
    if(button.dataset.reveal) {const input=$(`[data-field="${button.dataset.reveal}"]`);input.type=input.type === 'password'?'text':'password';button.setAttribute('aria-pressed',String(input.type === 'text'));button.setAttribute('aria-label',input.type === 'text'?'Скрыть ключ':'Показать ключ');return;}
    if(button.dataset.helpField) {event.preventDefault();const key=button.dataset.helpField;state.helpFields.has(key)?state.helpFields.delete(key):state.helpFields.add(key);const y=window.scrollY;render();window.scrollTo(0,y);$(`[data-help-field="${key}"]`)?.focus({preventScroll:true});return;}
    if(button.dataset.searchKey) {focusField(button.dataset.searchKey);return;}
    if(button.dataset.sectionLink) {const heading=document.getElementById(button.dataset.sectionLink);if(heading) {heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant':'smooth'});}return;}
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
