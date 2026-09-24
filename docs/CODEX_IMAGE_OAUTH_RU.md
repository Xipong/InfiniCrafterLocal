# ChatGPT / Codex OAuth для LLM и генерации PNG

## Включение

1. Запусти `LocalGenerator/settings_gui.py` тем же Python/пользователем, что запускает сервер.
2. Нажми **Sign in with ChatGPT** и заверши вход в браузере. Это собственная сессия InfiniCrafter; установленный Codex CLI или Hermes не требуется.
3. Для обычных LLM-этапов выбери **LLM provider → openai_codex**, обнови список моделей аккаунта и выбери модель. Для картинок независимо выбери **Image backend → openai_codex**.
4. Сохрани настройки и перезапусти LocalGenerator: провайдеры и параметры загружаются при старте сервера.

```dotenv
INFINI_LLM_PROVIDER=openai_codex
INFINI_CODEX_LLM_MODEL=<slug выбранной текстовой модели>
INFINI_CODEX_VISUAL_REASONING=inherit
INFINI_IMAGE_BACKEND=openai_codex
INFINI_CODEX_IMAGE_MODEL=gpt-image-2
INFINI_CODEX_IMAGE_QUALITY=medium
INFINI_CODEX_IMAGE_SIZE=1024x1024
INFINI_CODEX_IMAGE_TIMEOUT=240
```

LLM и image-провайдеры независимы. `openai_codex` для LLM вызывает подписочный `/backend-api/codex/responses`, а для изображений — `/backend-api/codex/images/generations`. `image_api`, `openai_compat` и OpenRouter остаются отдельными ключевыми/возможно платными маршрутами: ключ Platform и его баланс **не используются** подписочными запросами. Ошибка подписки не переключает выбранный Codex-провайдер автоматически на платный API.

## Модели, качество и расход

- При открытии вкладки с выбранным Codex и сохранённой сессией выполняется read-only проверка автоматически; кнопка обновления текстовых моделей повторно делает GET `/backend-api/codex/models?client_version=…` с текущим аккаунтом. Пикер показывает только видимые в каталоге **текстовые** модели и их заявленные уровни reasoning. Список означает рекламируемую доступность для этого аккаунта, не гарантирует успешный конкретный запрос. При ошибке уже выбранное имя не стирается; неизвестное имя можно сохранить вручную.
- **Отдельного подтверждённого API-каталога image-моделей нет.** `gpt-image-2` — известное встроенное имя, не проверка image-entitlement. Проверка сеанса или account ping не расходует image quota, но не доказывает image-доступ: его покажет только настоящий запрос. Нельзя выбирать текстовые slugs как image-модели на основании текстового каталога.
- `INFINI_CODEX_IMAGE_QUALITY=low|medium|high|auto` передаётся именно в image endpoint вместе с размером и одной картинкой (`n=1`). `low` обычно дешевле по вычислениям, `high` — дороже/медленнее, `auto` оставляет выбор серверу; точное списание подписочной квоты локально не известно. Не используй `auto`, если важна предсказуемость.
- `INFINI_CODEX_VISUAL_REASONING=inherit|model_default|none|minimal|low|medium|high|xhigh|max` управляет **текстовым Visual Director / visual repair**, который готовит authored prompt; `inherit` берёт общий LLM effort, `model_default` не посылает effort; при общем `off` Gameplay Author всё равно требует минимум `medium` для сохранения контракта, а Visual Director оставляет выбор модели. Это **не** reasoning внутри image-модели: документированного отдельного поля image reasoning у подписочного image endpoint нет. Выбирай уровень, который выбранная текстовая модель объявила в каталоге; `ultra` намеренно не отправляется как обычный effort.
- Подписочный `/responses` отклоняет `max_output_tokens` (проверено HTTP 400), поэтому общий `INFINI_LLM_MAX_TOKENS` **не является лимитом расходов** для Codex. Запрос ограничен временем и размером ответа, но не числом серверных output tokens. Температура также не применяется к этому маршруту.

Альтернатива GUI — команды из каталога `LocalGenerator` в установленном Python-окружении проекта:

```console
python -m infini_local.services.codex_auth login
python -m infini_local.services.codex_auth status
python -m infini_local.services.codex_auth logout
```

## Сессия и ошибки

- Browser login: PKCE S256, случайный `state`, callback только на `127.0.0.1:1455` с redirect URI `http://localhost:1455/auth/callback`. Если порт занят другим входом Codex, закончи тот вход и повтори. Ожидание ограничено тремя минутами; закрытие GUI отменяет ожидание.
- Файл сессии: `~/.infinicrafter/codex-auth.json` в профиле **пользователя, запускающего Python**. В Windows это обычно `%USERPROFILE%\.infinicrafter\codex-auth.json`, не WSL home. Linux использует права `0600`; Windows — шифрование DPAPI текущего пользователя. Сессия не хранится в `config.env` или репозитории.
- Истёкший access token обновляется перед запросом. Refresh сериализован между потоками и процессами GUI/генератора. `Auth status` проверяет локальный файл, а не доступность квоты на сервере.
- `Sign out` удаляет только локальную сессию InfiniCrafter, не сессию Codex CLI и не все входы ChatGPT. Во время входа кнопка сначала отменяет ожидание; после завершения нажми её снова для удаления сохранённого файла.
- WSL и Windows имеют разные пользовательские профили; не копируй DPAPI-файл между ними. Windows-файл сессии должен оставаться в обычном Windows-профиле: byte-range locks на `\\wsl.localhost\…` не поддерживаются проверенной средой.
- HTTP-ошибки сохраняют код и ограниченное диагностическое сообщение с редактированием credentials. OAuth/квота/сетевой сбой не вызывают автоматический повтор генерации или переключение на платный API/процедурную картинку.

## Пайплайн

`Visual Director prompt → общий image concurrency gate → Codex image service → проверка PNG → существующий sprite postprocess → delivery gate`.

Положительный authored prompt передаётся без переписывания дополнительной LLM. Непустой negative prompt добавляется как `\n\nAvoid: …`, поскольку у этого endpoint нет отдельного negative-поля. Качество/размер относятся к исходной картинке, итоговый sprite canvas остаётся в существующем postprocess. Backend проверяет фактический формат, декодирование, размер файла и допустимые размеры изображения, затем атомарно публикует PNG. Он не выдаёт повреждённый ответ или URL за готовый asset.

Используется Codex endpoint `https://chatgpt.com/backend-api/codex/images/generations`, а не Platform `/v1/images/generations`. Доступ и квота определяются аккаунтом/сервером; внутренний Codex API может меняться.

## Проверка реализации

- Offline-регрессии: PKCE/state и callback, refresh/session privacy, раздельный LLM/image dispatch, SSE completion и отказ принимать обрывки ответа, каталог аккаунта/ошибки обновления GUI, сохранение ручного slug, отсутствие скрытого платного fallback, качество PNG и независимый reasoning Visual Director. Полный Python suite: **363 passed**; headless C# runner против установленных tModLoader/FNA: **40 passed, 0 failed**; 12 проектных quality gates и Ruff прошли. Ограничения движкового acceptance перечислены в `ENGINE_RUNTIME_AUDIT_RU.md`.
- Native Windows Tk probe с фиктивным конфигом и без входа/секретов: UI собирается, модель/quality/size/image ping видны в начальном viewport, состояния read-only/pending не выглядят как подтверждённый успех, настройки проходят roundtrip. Реальный браузерный login в UI-прогоне не выполнялся; Windows file-lock на WSL UNC остаётся неподдерживаемой границей. Linux refresh-lock покрыт регрессией.
- Read-only каталог подписки проверен через существующую Codex CLI-сессию **в памяти**; текстовые модели аккаунта видны, но это не тест отдельной сессии InfiniCrafter и не список image-моделей. Пробный GET предполагаемого `/images/models` вернул HTTP 404; подтверждённого image-каталога нет.
- Живая проверка текстового backend через ту же временно заимствованную CLI-сессию: подписочный `/responses` вернул валидный JSON при `gpt-6-sol` и low effort. Проверка показала, что `max_output_tokens` подписочный сервер отвергает HTTP 400, поэтому он не отправляется. Ни один API key/файл сессии в репозиторий не перенесён.
- Предыдущая живая проверка image backend: один PNG `1672×941`, `gpt-image-2`, high, **44.07 с**. Это демонстрационная иллюстрация, не игровой спрайт; запрошен был size `1536x1024`, указаны фактические размеры ответа. Новые image-запросы в этом цикле не выполнялись.
- Собственный браузерный вход с реальным аккаунтом, полный live craft, GPU/multiplayer и запуск игры этим прогоном не проверялись. Перед использованием выполни **Sign in with ChatGPT** в том же Python-профиле, что запускает сервер.
