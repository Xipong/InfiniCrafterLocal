/* Guided setup owns only help progress. Model settings and secrets stay in Studio's draft. */
'use strict';
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const l = (ru, en) => document.documentElement.lang === 'en' ? en : ru;
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const link = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${text} <span aria-hidden="true">↗</span></a>`;
  const openrouterStarterModel = 'nvidia/nemotron-3.5-super-vl:free';
  const steps = () => [l('Начало','Welcome'),l('Текст','Text'),l('Изображения','Images'),l('Настройка','Setup'),l('Первый крафт','First craft')];
  const titles = () => [l('Твоя идея. Новый предмет.','Your idea. A new item.'),l('Выбери мозг генератора','Choose the creative brain'),l('Теперь добавим характер','Give it a look'),l('Соедини всё в Studio','Connect it in Studio'),l('Проверим, что осталось','Check what’s left')];
  const intro = () => [
    l('Пять простых шагов от первого запуска до своего предмета в Terraria.','Five simple steps from opening Studio to your own Terraria item.'),
    l('Текстовая модель придумывает механику, описание и задания для художника. Более сильная модель даёт больше возможностей для сложных и необычных предметов.','The text model creates mechanics, descriptions and art direction. A stronger model gives you more room for complex, unusual items.'),
    l('Отдельная модель рисует предмет. Для локального запуска рекомендуем Mage-Flow Turbo через sd.cpp. Если не хочешь запускать модель на своей видеокарте, выбери ChatGPT / Codex или Image API.','A separate model draws the item. We recommend Mage-Flow Turbo through sd.cpp for local generation. Choose ChatGPT / Codex or an Image API if you prefer not to run a model on your own GPU.'),
    l('Вводи настройки в знакомые поля Studio. Подстановка меняет только черновик после твоего нажатия.','Use Studio’s settings fields. Quick setup changes only the draft after your click.'),
    l('Сохрани конфигурацию, запусти генератор и продолжи в игре.','Save the configuration, start the generator and continue in the game.')
  ];
  const copyValue = (label, value) => `<div class="onboarding-copy"><span>${label}<code>${esc(value)}</code></span><button type="button" class="icon-button" data-onboarding-copy="${esc(value)}" aria-label="${esc(l('Копировать: ','Copy: ') + label)}">${icon('stack')}</button></div>`;
  const jump = (field, text) => `<button class="button" data-onboarding-field="${field}">${text}${icon('arrow')}</button>`;
  const numbered = rows => `<ol class="onboarding-instructions">${rows.map(([title,body])=>`<li><div><strong>${title}</strong><p>${body}</p></div></li>`).join('')}</ol>`;
  function welcome() {
    return `<div class="onboarding-hero-art" aria-hidden="true"><span class="onboarding-orbit"></span><span class="onboarding-tile tile-one">${icon('text')}</span><span class="onboarding-plus">+</span><span class="onboarding-tile tile-two">${icon('image')}</span><span class="onboarding-equals">→</span><span class="onboarding-tile tile-result">${icon('mark')}</span><span class="onboarding-art-caption">IDEA → MECHANICS → PIXELS</span></div>
      <div class="onboarding-two-col"><article class="onboarding-note"><span class="onboarding-eyebrow">01 / ${l('МЕХАНИКА','MECHANICS')}</span><h3>${l('Автор + арт-директор','Author + art director')}</h3><p>${l('Один текстовый API создаёт поведение, описание и визуальную идею предмета.','One text API creates the item’s behavior, description and visual concept.')}</p></article><article class="onboarding-note"><span class="onboarding-eyebrow">02 / ${l('РИСУНОК','ART')}</span><h3>${l('Локальная модель или API','Local model or API')}</h3><p>${l('Генератор изображений рисует спрайт. Studio подготавливает его для Terraria.','The image generator draws a sprite. Studio prepares it for Terraria.')}</p></article></div>
      <div class="onboarding-callout">${icon('check')}<p>${l('Доступный старт: бесплатный Gemini Flash-Lite через AI Studio или Nemotron 3.5 Super VL через OpenRouter + Mage-Flow Turbo локально. Более сильные модели помогут раскрыть потенциал мода. Если у тебя уже есть к ним доступ, начинай с них.','Accessible start: free-tier Gemini Flash-Lite via AI Studio or Nemotron 3.5 Super VL via OpenRouter + local Mage-Flow Turbo. Stronger models can unlock more of the mod’s potential. If you already have access, start with those.')}</p></div>
      <article class="onboarding-note"><h3>${l('Если ты в России','If you are in Russia')}</h3><p>${l('Для доступа к Google AI Studio и OpenRouter может понадобиться VPN. Проверь доступность сервиса и выбранной модели в своём регионе. OpenRouter запрещает обход региональных ограничений отдельных моделей.','You may need a VPN to access Google AI Studio and OpenRouter. Check whether the service and selected model are available in your region. OpenRouter prohibits bypassing regional restrictions on individual models.')}</p>${link('https://openrouter.ai/terms',l('Условия OpenRouter, §5.7','OpenRouter terms, §5.7'))}</article>
      <p class="onboarding-fine">${l('Можно закрыть помощник в любой момент. Кнопка «Быстрый старт» в углу вернёт тебя к нужному шагу.','Close the guide at any time. The Quick start button in the corner returns to your current step.')}</p>`;
  }
  function textModels() {
    return `<article class="onboarding-feature"><div><span class="onboarding-badge">${l('БЕСПЛАТНЫЙ СТАРТ','FREE START')}</span><h3>Gemini 3.5 Flash-Lite</h3><p>${l('Доступный базовый вариант: бесплатный уровень Gemini API, ключ из Google AI Studio. Для более сложной механики стоит попробовать более сильную текстовую модель.','An accessible baseline: Gemini API’s free tier, with a key from Google AI Studio. For more complex mechanics, try a stronger text model.')}</p></div><div class="onboarding-links">${link('https://aistudio.google.com/apikey',l('Получить ключ','Get an API key'))}${link('https://ai.google.dev/gemini-api/docs/pricing',l('Бесплатный уровень и тарифы','Free tier and pricing'))}</div></article>
      <article class="onboarding-model"><span class="onboarding-eyebrow">${l('120B ВСЕГО · 12B АКТИВНЫХ · БЕСПЛАТНО','120B TOTAL · 12B ACTIVE · FREE')}</span><h3>NVIDIA Nemotron 3.5 Super VL</h3><p>${l('Открытая мультимодальная MoE-модель: 120 млрд параметров всего, 12 млрд активных. Бесплатный маршрут OpenRouter поддерживает JSON Schema. Для механики предметов Studio отправляет текстовые запросы.','An open multimodal MoE model with 120 billion total parameters and 12 billion active. The free OpenRouter route supports JSON Schema. Studio sends text requests for item mechanics.')}</p><div class="onboarding-links">${link('https://openrouter.ai/'+openrouterStarterModel,'OpenRouter :free')}</div></article>
      <article class="onboarding-model"><span class="onboarding-eyebrow">${l('ВЫБОР МОДЕЛЕЙ','MODEL CHOICE')}</span><h3>OpenRouter</h3><p>${l('В Studio есть отдельный провайдер OpenRouter для бесплатных и платных моделей. Для бесплатного старта выбери конкретную модель 27B+ с ценой $0 и суффиксом :free. Для более требовательных идей сравни её с более сильной моделью из каталога.','Studio has a dedicated OpenRouter provider for free and paid models. For a free start, choose a specific 27B+ model priced at $0 with a :free suffix. For more demanding ideas, compare it with a stronger model from the catalog.')}</p><div class="onboarding-links">${link('https://openrouter.ai/collections/free-models',l('Бесплатные модели','Free models'))}${link('https://openrouter.ai/pricing',l('Тарифы','Pricing'))}${link('https://openrouter.ai/settings/keys',l('Создать ключ','Create a key'))}</div></article>
      <article class="onboarding-model"><span class="onboarding-eyebrow">${l('БОЛЬШЕ ВОЗМОЖНОСТЕЙ','MORE POSSIBILITIES')}</span><h3>${l('Более сильный автор механики','A stronger mechanics author')}</h3><p>${l('Уже есть подписка ChatGPT / Codex? В «Тексте и механике» выбери этот источник, войди и обнови каталог текстовых моделей своего аккаунта. Также можно указать более сильную платную модель OpenRouter или совместимого API. Сравни результат на своих идеях: цена и число параметров сами по себе не гарантируют качество.','Already have a ChatGPT / Codex subscription? Select that provider in Text & mechanics, sign in and refresh your account’s text model catalog. You can also choose a stronger paid OpenRouter or compatible API model. Compare results on your own ideas: price and parameter count alone do not guarantee quality.')}</p></article>
      <details class="onboarding-details"><summary>${l('Как устроено «бесплатно»','How the free tier works')}</summary><p>${l('Google: бесплатные входные и выходные токены в пределах квоты проекта. Лимиты видны в AI Studio. Контент бесплатного уровня может использоваться Google для улучшения продуктов.','Google: free input and output tokens within the project quota. See your limits in AI Studio. Google may use free-tier content to improve its products.')}</p><p>${l('OpenRouter :free: до 20 запросов в минуту и 50 в день; после суммарной покупки кредитов на $10 или больше — до 1000 бесплатных запросов в день. Один крафт использует несколько запросов; неудачные попытки тоже расходуют дневной лимит.','OpenRouter :free: up to 20 requests per minute and 50 per day; after purchasing at least $10 in total credits, up to 1,000 free requests per day. One craft uses several requests; failed attempts also count toward the daily limit.')}</p>${link('https://openrouter.ai/docs/api/reference/limits',l('Лимиты OpenRouter','OpenRouter limits'))}</details>
      <p class="onboarding-fine">${l('Не отправляй конфиденциальную информацию и персональные данные в бесплатный endpoint NVIDIA. Запросы могут сохраняться для безопасности и улучшения продуктов NVIDIA.','Do not send confidential information or personal data to NVIDIA’s free endpoint. Requests may be logged for security and to improve NVIDIA products.')}</p>
      ${jump('INFINI_LLM_PROVIDER',l('Открыть «Текст и механика»','Open Text & mechanics'))}`;
  }
  function imageModels() {
    return `<article class="onboarding-feature"><div><span class="onboarding-badge">${l('РЕКОМЕНДУЕМ ЛОКАЛЬНО','RECOMMENDED LOCAL MODEL')}</span><h3>Microsoft Mage-Flow Turbo</h3><p>${l('Рекомендуем для локальной генерации через sd.cpp. Studio уже передаёт ему диффузионную модель, текстовый энкодер Qwen3-VL и VAE: отдельный backend для Mage-Flow не нужен. Выбери сборку sd.cpp с поддержкой Mage-Flow и совместимые файлы из её инструкции.','Recommended for local generation through sd.cpp. Studio already passes the diffusion model, Qwen3-VL text encoder and VAE to sd.cpp: Mage-Flow does not need a separate backend. Choose an sd.cpp build with Mage-Flow support and compatible files from its guide.')}</p></div><div class="onboarding-links">${link('https://huggingface.co/microsoft/Mage-Flow-Turbo',l('Модель Turbo','Turbo model'))}${link('https://microsoft.github.io/Mage/flow/',l('Проект Mage-Flow','Mage-Flow project'))}${link('https://github.com/leejet/stable-diffusion.cpp/blob/master-1068-fc350be/docs/mage_flow.md',l('Mage-Flow в sd.cpp','Mage-Flow in sd.cpp'))}</div></article>
      <p class="onboarding-fine">${l('Microsoft публикует Mage-Flow как исследовательскую модель. Перед использованием проверь лицензию, ограничения и требования к видеопамяти для выбранных весов.','Microsoft releases Mage-Flow as a research model. Check the license, restrictions and VRAM requirements for your chosen weights before use.')} ${link('https://github.com/microsoft/Mage#responsible-ai',l('Условия использования','Usage terms'))}</p>
      <article class="onboarding-model"><span class="onboarding-eyebrow">${l('ЛОКАЛЬНАЯ АЛЬТЕРНАТИВА','LOCAL ALTERNATIVE')}</span><h3>FLUX.2 [klein] 4B</h3><p>${l('Альтернатива для локального запуска: distilled, не Base. Для неё нужны свои совместимые веса, энкодер Qwen3 4B и FLUX.2 VAE. Не смешивай файлы разных моделей.','A local alternative: choose distilled, not Base. It needs its own compatible weights, Qwen3 4B text encoder and FLUX.2 VAE. Do not mix files from different models.')}</p><div class="onboarding-links">${link('https://huggingface.co/black-forest-labs/FLUX.2-klein-4B',l('Официальная модель','Official model'))}${link('https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/flux2.md',l('Инструкция FLUX.2 для sd.cpp','FLUX.2 setup for sd.cpp'))}</div></article>
      <article class="onboarding-model"><span class="onboarding-eyebrow">${l('БЕЗ ЛОКАЛЬНОЙ ВИДЕОКАРТЫ','NO LOCAL GPU NEEDED')}</span><h3>ChatGPT / Codex · Image API</h3><p>${l('В Studio можно выбрать gpt-image-2 через ChatGPT / Codex. По умолчанию используется качество «Стандарт / medium»; начни с него. Доступ зависит от аккаунта. Для внешнего Image API укажи модель, поддерживаемую выбранным сервисом.','Studio offers gpt-image-2 through ChatGPT / Codex. Standard / medium quality is the default; start with that. Access depends on your account. For an external Image API, choose a model supported by your service.')}</p><p>${l('Эти варианты работают без локальной видеокарты. Подписку, тарифы и лимиты проверь у сервиса. Для своего локального набора моделей в Studio также доступны ComfyUI и Automatic1111.','These options work without a local GPU. Check the service’s subscription, pricing and limits. Studio also supports ComfyUI and Automatic1111 for your own local model setup.')}</p></article>
      ${jump('INFINI_IMAGE_BACKEND',l('Открыть «Изображения»','Open Images'))}`;
  }
  function setup() {
    return `<div class="onboarding-two-col"><article class="onboarding-model"><span class="onboarding-eyebrow">A / GOOGLE AI STUDIO</span><h3>${l('Подключи текстовый API','Connect the text API')}</h3>${numbered([
      [l('Создай API-ключ','Create an API key'),link('https://aistudio.google.com/apikey','Google AI Studio')],
      [l('Источник: «Совместимый API»','Provider: Compatible API'),l('Включи генерацию механики моделью. Вставь URL, ключ и точный ID модели. В «Тонкой настройке» выбери «Формат запроса к модели» → chat_completions.','Enable model-generated mechanics. Enter the URL, key and exact model ID. Under Fine tuning, set Model request format to chat_completions.')]
    ])}${copyValue('Base URL','https://generativelanguage.googleapis.com/v1beta/openai/')}${copyValue(l('Модель','Model'),'gemini-3.5-flash-lite')}<div class="onboarding-links">${link('https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite',l('Официальный ID модели','Official model ID'))}</div><div class="onboarding-links"><p class="onboarding-fine">${l('Подстановка меняет источник, адрес и модель только в черновике. Ключ другого API будет очищен в черновике; конфигурация на диске не меняется.','Quick setup changes the provider, URL and model only in the draft. A key for another API is cleared from the draft; the saved configuration is unchanged.')}</p><button class="button" data-onboarding-preset="gemini">${l('Подставить настройки Gemini','Use Gemini settings')}${icon('arrow')}</button>${jump('INFINI_LLM_API_MODE',l('Формат запроса','Request format'))}</div></article>
      <article class="onboarding-model"><span class="onboarding-eyebrow">B / OPENROUTER</span><h3>${l('Или выбери OpenRouter','Or choose OpenRouter')}</h3>${numbered([
        [l('Источник: OpenRouter','Provider: OpenRouter'),l('Вставь ключ OpenRouter в его отдельное поле.','Paste your OpenRouter key in its dedicated field.')],
        [l('Укажи модель :free','Choose a :free model'),l('Скопируй ID ниже. Площадку OpenRouter оставь пустой для автоматического выбора.','Copy the ID below. Leave the OpenRouter provider field empty for automatic routing.')]
      ])}${copyValue(l('Бесплатная модель NVIDIA','Free NVIDIA model'),openrouterStarterModel)}<button class="button" data-onboarding-preset="openrouter">${l('Подставить настройки OpenRouter','Use OpenRouter settings')}${icon('arrow')}</button><p class="onboarding-fine">${l('Есть локальная модель 27B+? Запусти сервер LM Studio и выбери «LM Studio · локально» в источнике текста.','Already have a local 27B+ model? Start the LM Studio server and select LM Studio · local as the text provider.')}</p></article></div>
      <article class="onboarding-model"><span class="onboarding-eyebrow">C / MAGE-FLOW TURBO</span><h3>${l('Подключи локальный художник','Connect the local artist')}</h3>${numbered([
        [l('Установи sd.cpp','Install sd.cpp'),l('Выбери sd-server под свою видеокарту с поддержкой Mage-Flow. Скачай совместимые веса Mage-Flow Turbo, энкодер Qwen3-VL 4B и Mage-VAE по ссылкам ниже.','Choose an sd-server build for your GPU with Mage-Flow support. Get compatible Mage-Flow Turbo weights, a Qwen3-VL 4B text encoder and Mage-VAE from the links below.')],
        [l('Укажи файлы','Select the files'),l('В «Изображениях» выбери sd.cpp. В «Моделях и LoRA» укажи программу sd.cpp, диффузионную модель, текстовый энкодер и VAE.','Choose sd.cpp in Images. In Models & LoRA, select the sd.cpp executable, diffusion model, text encoder and VAE.')],
        [l('Проверь настройки запуска','Check startup settings'),l('Включи управляемый запуск sd.cpp. Для Turbo инструкция рекомендует 4 шага и CFG 1.0. Размеры изображения должны быть кратны 16; диапазон обучения модели — 512–2048 px. Дополнительные аргументы выбирай по инструкции и своей видеокарте. Сохрани настройки и проверь журнал запуска.','Enable managed sd.cpp startup. The guide recommends 4 steps and CFG 1.0 for Turbo. Image dimensions must be multiples of 16; the model was trained at 512–2048 px. Choose extra arguments for your build and GPU. Save the settings and check the startup log.')]
      ])}<div class="onboarding-links">${link('https://github.com/leejet/stable-diffusion.cpp/blob/master-1068-fc350be/docs/mage_flow.md',l('Инструкция Mage-Flow для sd.cpp','Mage-Flow setup for sd.cpp'))}${link('https://huggingface.co/Comfy-Org/Mage-Flow/tree/main/diffusion_models',l('Веса Turbo','Turbo weights'))}${link('https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/tree/main','Qwen3-VL 4B GGUF')}${link('https://huggingface.co/Comfy-Org/Mage-Flow/tree/main/vae','Mage-VAE')}</div>${jump('INFINI_SDCPP_SERVER_EXE',l('Выбрать файлы моделей','Choose model files'))}</article>`;
  }
  function finish(state, value, getGaps) {
    const gaps=getGaps?.() || [];
    const saved = !state.dirty.size && state.lan === state.baselineLan;
    return `<div class="onboarding-checklist">${gaps.length ? gaps.map(gap=>`<div><span class="onboarding-check">${icon('sliders')}</span><span><strong>${esc(gap.title)}</strong><br><small>${esc(gap.detail)}</small></span>${jump(gap.key,l('Настроить','Set up'))}</div>`).join('') : `<div><span class="onboarding-check is-done">${icon('check')}</span><span>${l('Обязательные поля заполнены. Работоспособность ещё не проверена.','Required fields are filled. The setup has not been tested yet.')}</span></div>`}
      <div><span class="onboarding-check ${saved?'is-done':''}">${icon(saved?'check':'sliders')}</span><span>${saved?l('Нет несохранённых изменений','No unsaved changes'):l('Черновик ещё не сохранён','Draft is not saved yet')}</span></div></div>
      <p class="onboarding-fine">${l('Наличие пути не доказывает, что файл существует или модель совместима. Проверь пути и соединение в Studio. Эта проверка не запускает платную генерацию.','A path does not prove the file exists or the model is compatible. Check paths and the connection in Studio. This check does not start paid generation.')}</p>
      ${numbered([
        [l('Сохрани и запусти','Save and start'),l('Нажми «Сохранить» внизу Studio, затем «Запустить генератор» на рабочем столе. Дождись подтверждения соединения.','Click Save at the bottom of Studio, then Start generator on the dashboard. Wait for the connection to be confirmed.')],
        [l('Продолжи в Terraria','Continue in Terraria'),l('Открой игру с модом InfiniCrafterLocal. Создание предметов происходит в игре, а Studio остаётся центром настроек.','Open the game with the InfiniCrafterLocal mod. Items are crafted in-game; Studio remains your settings center.')],
        [l('Если что-то не получилось','If something goes wrong'),l('Открой «Диагностика»: проверь соединение и журнал. Ошибка 429 означает исчерпанный лимит API. Для sd.cpp сначала проверь пути к файлам и журнал запуска.','Open Diagnostics to check the connection and logs. Error 429 means an API limit was reached. For sd.cpp, check model paths and the startup log first.')]
      ])}<div class="onboarding-links"><button class="button" data-onboarding-route="operate">${l('Рабочий стол','Dashboard')}${icon('arrow')}</button><button class="button" data-onboarding-route="diagnostics">${l('Диагностика','Diagnostics')}${icon('pulse')}</button></div>`;
  }
  function presetValues(name,value) {
    if(name==='openrouter') return {INFINI_USE_LLM:'1',INFINI_LLM_PROVIDER:'openrouter',INFINI_OPENROUTER_MODEL:openrouterStarterModel,INFINI_OPENROUTER_PROVIDER:''};
    if(name!=='gemini') return null;
    const url='https://generativelanguage.googleapis.com/v1beta/openai/';
    let same=false;
    try {const current=new URL(value('INFINI_OPENAI_COMPAT_BASE_URL'));same=current.origin==='https://generativelanguage.googleapis.com' && current.pathname.replace(/\/$/,'')==='/v1beta/openai' && !current.username && !current.password && !current.search;} catch(_) {}
    return {INFINI_USE_LLM:'1',INFINI_LLM_PROVIDER:'openai_compat',INFINI_OPENAI_COMPAT_BASE_URL:url,INFINI_OPENAI_COMPAT_MODEL:'gemini-3.5-flash-lite',INFINI_LLM_API_MODE:'chat_completions',...(!same?{INFINI_OPENAI_COMPAT_API_KEY:''}:{})};
  }
  function create({api, focusField, value, state, navigateTo, notify, applyDraft, getGaps}) {
    const dialog = document.querySelector('#onboarding-dialog');
    const launcher = document.querySelector('#onboarding-launcher');
    let step=0, initialized=false, autoPending=false, completed=false, queued=null, pending=null, posting=false, error='', progressError='', language='', focusReturn=null, lastFinishView='', installState={}, selectedBuild='', installPending=null, installPosting=false;
    function render(focus=false) {
      const restoreFocus=dialog.open && dialog.contains(document.activeElement);
      const names=steps();language=document.documentElement.lang;
      dialog.innerHTML=`<div class="onboarding-top"><span class="onboarding-wordmark">${icon('mark')} INFINICRAFT <small>FIRST STEPS</small></span><button class="icon-button" data-onboarding-close aria-label="${l('Закрыть помощник','Close guide')}">${icon('close')}</button></div>
        <div class="onboarding-layout"><aside class="onboarding-sidebar"><span class="onboarding-eyebrow">${l('ТВОЯ СТУДИЯ','YOUR STUDIO')}</span><h2>${l('От идеи<br>к крафту.','From idea<br>to craft.')}</h2><nav aria-label="${l('Шаги настройки','Setup steps')}">${names.map((name,index)=>`<button data-onboarding-step="${index}" ${index===step?'aria-current="step"':''}><span>${String(index+1).padStart(2,'0')}</span>${name}${index<step?icon('check'):''}</button>`).join('')}</nav><p>${l('Настрой один раз.<br>Создавай бесконечно.','Set up once.<br>Create endlessly.')}</p></aside>
        <section class="onboarding-content"><div class="onboarding-step-label">${l('ШАГ','STEP')} ${step+1} / 5</div><h1 id="onboarding-title" tabindex="-1">${titles()[step]}</h1><p class="onboarding-intro">${intro()[step]}</p><div class="onboarding-step-body">${[welcome,textModels,imageModels,setup,()=>finish(state,value,getGaps)][step]()}${step===2 || step===3 ? '<div id="onboarding-installer"></div>':''}</div></section></div>
        <div class="onboarding-bottom"><p class="onboarding-freshness">${l('Список моделей может устареть. Проверено 09.11.2026.','The model list may become outdated. Checked November 9, 2026.')}</p><div class="onboarding-controls"><button class="text-button" data-onboarding-close>${l('Продолжу позже','Continue later')}</button><button class="button" data-onboarding-back ${step===0?'disabled':''}>${l('Назад','Back')}</button><button class="button button-primary" data-onboarding-next>${step===4?l('Закрыть помощник','Close guide'):l('Дальше','Next')}${icon('arrow')}</button></div><p id="onboarding-progress-feedback" class="onboarding-feedback" role="status">${esc(progressError)}</p><p id="onboarding-feedback" class="onboarding-feedback" role="status">${esc(error)}</p></div>`;
      updateInstaller();
      if(focus || restoreFocus) dialog.querySelector('#onboarding-title').focus({preventScroll:true});
      if(focus) dialog.querySelector('.onboarding-content').scrollTop=0;
    }
    const size = bytes => `${(Number(bytes || 0)/1048576).toFixed(1)} MiB`;
    function updateInstaller() {
      const panel=dialog.querySelector('#onboarding-installer');
      if(!panel || ![2,3].includes(step)) return;
      const builds=installState.builds || [];
      if(!builds.some(build=>build.id===selectedBuild)) selectedBuild=builds.find(build=>build.platformCompatible!==false && build.backend==='Vulkan')?.id || builds.find(build=>build.platformCompatible!==false)?.id || '';
      const selected=builds.find(build=>build.id===selectedBuild);
      const busy=!!installState.busy || installPosting || !!installPending;
      const view=JSON.stringify([installState,selectedBuild,busy,language]);
      if(panel.dataset?.view===view) return;
      const focused=document.activeElement?.id;
      const labels={idle:l('Выбери и скачай программу','Choose and download the program'),catalog:l('Получаем официальный каталог…','Loading official catalogue…'),downloading:l('Скачиваем…','Downloading…'),extracting:l('Проверяем и распаковываем…','Verifying and extracting…'),installed:l('Программа установлена. Подключи её к черновику.','Program installed. Connect it to the draft.'),cancelled:l('Загрузка отменена. Можно повторить.','Download cancelled. You can try again.'),error:l('Установка не завершена','Installation did not finish')};
      panel.innerHTML=`<article class="onboarding-model onboarding-install"><span class="onboarding-eyebrow">SD.CPP</span><h3>${l('Скачать программу прямо здесь','Download the program here')}</h3><p>${l('Vulkan: AMD и Intel, также NVIDIA. CUDA: NVIDIA с совместимым драйвером. CPU: без видеокарты, медленно. Выбирай сборку для компьютера, где работает Studio.','Vulkan: AMD and Intel, also NVIDIA. CUDA: NVIDIA with a compatible driver. CPU: no GPU, slow. Choose a build for the computer running Studio.')}</p>
        <div class="onboarding-links"><button id="onboarding-catalog" class="button" data-onboarding-install-action="sdCatalog" ${busy?'disabled':''}>${builds.length?l('Обновить список','Refresh list'):l('Показать сборки','Show builds')}</button>${link('https://github.com/leejet/stable-diffusion.cpp/releases/latest',l('Официальный релиз','Official release'))}</div>
        ${installState.release && !builds.some(build=>build.platformCompatible!==false) ? `<p class="onboarding-install-error">${l('В этом релизе нет поддерживаемой сборки для этого компьютера. Используй официальный релиз и ручной выбор программы.','No supported build for this computer in this release. Use the official release and select the program manually.')}</p>`:''}
        ${builds.length ? `<label class="onboarding-build-label" for="onboarding-build">${l('Сборка и размер загрузки','Build and download size')}</label><select id="onboarding-build" ${busy?'disabled':''}>${builds.map(build=>`<option value="${esc(build.id)}" ${build.id===selectedBuild?'selected':''} ${build.platformCompatible===false?'disabled':''}>${esc(build.label || build.name)} · ${size(build.size)}</option>`).join('')}</select><p class="onboarding-fine">${esc(selected?.name || '')}${selected?.verified===false ? ' · '+l('В релизе нет SHA-256','Release has no SHA-256'):''}</p><div class="onboarding-links"><button id="onboarding-download" class="button button-primary" data-onboarding-install-action="sdInstall" ${busy || !selected?'disabled':''}>${l('Скачать и распаковать','Download and extract')} · ${size(selected?.size)}</button></div>`:''}
        <p class="onboarding-install-status" role="status">${labels[installState.status] || labels.idle}</p>
        ${installState.totalBytes && installState.busy ? `<progress max="${Number(installState.totalBytes)}" value="${Math.min(Number(installState.downloadedBytes || 0),Number(installState.totalBytes))}"></progress><p class="onboarding-fine">${size(installState.downloadedBytes)} / ${size(installState.totalBytes)}</p>`:''}
        ${installState.error ? `<p class="onboarding-install-error" role="alert">${esc(installState.error)}</p>`:''}
        ${installState.busy ? `<button id="onboarding-cancel" class="button" data-onboarding-install-action="sdCancel" ${installPosting?'disabled':''}>${l('Отменить загрузку','Cancel download')}</button>`:''}
        ${installState.installedPath ? `<p class="onboarding-installed-path">${esc(installState.installedPath)}</p><button id="onboarding-use" class="button" data-onboarding-use ${state.shutdown?'disabled':''}>${l('Использовать в Studio','Use in Studio')}</button>`:''}
        <p class="onboarding-fine">${l('Скачивание только с официального GitHub. CUDA-библиотеки при необходимости входят в показанный размер. Пакет распакуется рядом с конфигурацией. Ничего не запускается; настройки меняются только кнопкой «Использовать в Studio». Веса модели, энкодер и VAE скачиваются отдельно. Закрытие помощника не отменяет загрузку.','Downloads come only from official GitHub releases. The size includes CUDA libraries when needed. Files are extracted next to the configuration. Nothing is launched; only Use in Studio changes the draft. Model weights, text encoder and VAE are separate downloads. Closing the guide does not cancel the download.')}</p></article>`;
      if(panel.dataset) panel.dataset.view=view;
      if(focused?.startsWith('onboarding-')) dialog.querySelector('#'+focused)?.focus?.({preventScroll:true});
    }
    async function installerAction(action) {
      if(installPosting || state.shutdown || action!=='sdCancel' && (installState.busy || installPending)) return;
      installPosting=true;status('');updateInstaller();
      try {
        const response=await api('/api/action',{action,values:{},extra:action==='sdInstall'?{buildId:selectedBuild}:{}});
        if(!response.ok || !response.id) throw Error();
        installPending=response.id;
      } catch(error) {
        failure(error?.httpStatus===400
          ? l('Studio отклонила команду (HTTP 400). Полностью закрой Studio и открой её заново через запускатор из актуальной папки.','Studio rejected the command (HTTP 400). Fully close Studio and reopen it with the launcher from the current folder.')
          : error?.message || l('Не удалось отправить действие. Проверь соединение со Studio.','Could not send the action. Check the connection to Studio.'));
      }
      finally {installPosting=false;updateInstaller();}
    }
    function status(message) {error=message;const feedback=dialog.querySelector('#onboarding-feedback');if(feedback) feedback.textContent=message;}
    function failure(message) {status(message);if(!dialog.open) notify?.(message);}
    function progressStatus(message) {progressError=message;const feedback=dialog.querySelector('#onboarding-progress-feedback');if(feedback) feedback.textContent=message;}
    function progressFailure(message) {progressStatus(message);if(!dialog.open) notify?.(message);}
    function progressRequestFailure(cause) {
      // Classify the transport without displaying exception text, URLs or session tokens.
      const reasons = {
        400: l('Запрос не принят. Перезапусти Studio из папки актуальной версии.','The request was rejected. Restart Studio from the current version folder.'),
        403: l('Сессия недоступна. Открой Studio заново через запускатор.','The session is unavailable. Reopen Studio from the launcher.'),
        409: l('Studio закрыта. Открой её заново через запускатор.','Studio is closed. Reopen it from the launcher.'),
        429: l('Studio занята. Попробуй следующий шаг чуть позже.','Studio is busy. Try the next step again shortly.')
      };
      const reason = cause?.name === 'AbortError' || cause?.httpStatus === 408
        ? l('Studio не ответила вовремя. Проверь соединение.','Studio did not respond in time. Check the connection.')
        : reasons[cause?.httpStatus] || l('Проверь соединение со Studio.','Check the connection to Studio.');
      return l('Сохранение прогресса не подтверждено. ','Progress saving is not confirmed. ') + reason
        + l(' Прогресс остаётся в этой вкладке; следующий шаг повторит сохранение.',' Progress remains in this tab; the next step will retry saving.');
    }
    async function flush() {
      if(posting || pending || !queued || state.shutdown) return;
      const update=queued;queued=null;posting=true;
      try {
        const response=await api('/api/action',{action:'onboardingProgress',values:{},extra:update});
        if(!response.ok || !response.id) throw new Error();
        pending=response.id;
      } catch (cause) {progressFailure(progressRequestFailure(cause));}
      finally {posting=false;if(queued && !pending) flush();}
    }
    function persist() {queued={step,completed};flush();}
    function open() {
      if(!initialized || state.shutdown || dialog.open || document.querySelector('dialog[open]')) return;
      autoPending=false;focusReturn=document.activeElement;render();dialog.showModal();dialog.querySelector('#onboarding-title').focus({preventScroll:true});persist();
    }
    function dismiss() {if(dialog.open) dialog.close();}
    function sync(remote) {
      launcher.disabled=state.shutdown || !remote.onboarding;
      if(!remote.onboarding) return;
      installState=remote.sdcppInstall || {};
      if(installPending) {
        const receipt=(remote.actionResults || []).find(item=>item.id===installPending && item.status!=='running');
        if(receipt) {installPending=null;if(!receipt.ok) failure(receipt.message || l('Не удалось выполнить действие.','The action failed.'));}
      }
      if(dialog.open) {
        updateInstaller();
        if(step===4) {
          const view=JSON.stringify([getGaps?.() || [],state.dirty.size,state.lan,state.baselineLan]);
          if(view!==lastFinishView) {lastFinishView=view;const content=dialog.querySelector('.onboarding-content');const scroll=content?.scrollTop || 0;render();dialog.querySelector('.onboarding-content').scrollTop=scroll;}
        }
      }

      if(!initialized) {initialized=true;step=remote.onboarding.step || 0;completed=!!remote.onboarding.completed;autoPending=!remote.onboarding.seen;}
      if(pending) {
        const result=(remote.actionResults || []).find(receipt=>receipt.id===pending && receipt.status!=='running');
        if(result) {
          pending=null;
          if(result.ok) progressStatus('');
          else progressFailure(l('Прогресс не сохранён. Проверь доступ к папке конфигурации.','Progress was not saved. Check access to the configuration folder.'));
          flush();
        }
      }
      if(dialog.open && language!==document.documentElement.lang) render(true);
      if(state.shutdown) dismiss();else if(autoPending) open();
    }
    dialog.addEventListener('click',async event=>{
      const button=event.target.closest('button');if(!button) return;
      if(button.dataset.onboardingInstallAction) {await installerAction(button.dataset.onboardingInstallAction);return;}
      if(button.hasAttribute('data-onboarding-use')) {
        if(!installState.installedPath || state.shutdown) return;
        applyDraft?.({INFINI_IMAGE_BACKEND:'sdcpp',INFINI_SDCPP_SERVER_AUTOSTART:'1',INFINI_SDCPP_SERVER_COMMAND_MODE:'safe_args',INFINI_SDCPP_SERVER_EXE:installState.installedPath});
        status(l('Путь и управляемый запуск safe_args добавлены в черновик. Выбери модель, энкодер и VAE, затем сохрани.','Path and managed safe-argument startup added to the draft. Choose the model, text encoder and VAE, then save.'));return;
      }
      if(button.dataset.onboardingPreset) {
        const values=presetValues(button.dataset.onboardingPreset,value);
        if(values && !state.shutdown) {applyDraft?.(values);dismiss();focusField(button.dataset.onboardingPreset==='gemini'?'INFINI_OPENAI_COMPAT_API_KEY':'INFINI_OPENROUTER_API_KEY');}
        return;
      }
      if(button.hasAttribute('data-onboarding-close')) {dismiss();return;}
      if(button.hasAttribute('data-onboarding-next')) {
        if(step===4) {completed=true;persist();dismiss();return;}step++;
      } else if(button.hasAttribute('data-onboarding-back')) step=Math.max(0,step-1);
      else if(button.dataset.onboardingStep!==undefined) step=Number(button.dataset.onboardingStep);
      else if(button.dataset.onboardingField) {dismiss();focusField(button.dataset.onboardingField);return;}
      else if(button.dataset.onboardingRoute) {dismiss();navigateTo(button.dataset.onboardingRoute);return;}
      else if(button.dataset.onboardingCopy) {
        try {await navigator.clipboard.writeText(button.dataset.onboardingCopy);status(l('Скопировано.','Copied.'));}
        catch (_) {status(l('Не удалось скопировать. Выдели значение и скопируй вручную.','Could not copy. Select the value and copy it manually.'));}return;
      } else return;
      render(true);persist();
    });
    dialog.addEventListener('change',event=>{if(event.target.id==='onboarding-build') {selectedBuild=event.target.value;updateInstaller();}});
    dialog.addEventListener('close',()=>{if(document.activeElement===document.body || dialog.contains(document.activeElement)) (focusReturn?.isConnected && focusReturn!==document.body?focusReturn:launcher).focus({preventScroll:true});});
    return {open,dismiss,sync};
  }
  window.InfiniOnboarding={create,presetValues};
})();
