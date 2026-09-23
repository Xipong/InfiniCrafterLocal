# ChatGPT / Codex OAuth для генерации PNG

## Включение

1. Открой `LocalGenerator/settings_gui.py`, вкладку **Image**.
2. Выбери **Image backend → openai_codex**.
3. Нажми **Sign in with ChatGPT** и заверши вход в браузере. Используется собственная сессия InfiniCrafter; установленный Codex CLI или Hermes не требуется.
4. Сохрани настройки и перезапусти LocalGenerator. Параметры image backend загружаются при старте сервера.

Поля по умолчанию:

```dotenv
INFINI_IMAGE_BACKEND=openai_codex
INFINI_CODEX_IMAGE_MODEL=gpt-image-2
INFINI_CODEX_IMAGE_QUALITY=medium
INFINI_CODEX_IMAGE_SIZE=1024x1024
INFINI_CODEX_IMAGE_TIMEOUT=240
```

Этот переключатель меняет только image backend. Gameplay Author, Visual Director и VFX Director продолжают использовать выбранный LLM provider. `image_api` остаётся отдельным Platform/OpenAI-compatible API backend; его ключи и платный баланс не используются при `openai_codex`.

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

- Offline-регрессии: PKCE/state и дубликаты callback-параметров, реальный loopback callback с подменой только внешнего token endpoint, form encoding, refresh при конкурентных потоках, приватное сохранение/выход, HTTP redaction, отдельный dispatch и отсутствие fallback, GUI schema/CLI.
- Полный Python suite после интеграции: **330 passed**. Headless C# runner против реальных tModLoader/FNA: **40 passed, 0 failed**; ограничения движкового acceptance перечислены в `ENGINE_RUNTIME_AUDIT_RU.md`.
- Native Windows probe: реальный DPAPI save/load и Tk build, доступность полей, очередь результата входа, выход и config roundtrip. Внешний login в этом UI-прогоне заменён offline-fixture; Windows file-lock на WSL UNC дал `EINVAL` и не засчитан как Windows lock acceptance. Linux refresh-lock проверен регрессией.
- Живая подписочная проверка backend через существующую Codex CLI-сессию: один PNG `1672×941`, `gpt-image-2`, high, **44.07 с**. Это демонстрационная иллюстрация, не игровой спрайт. Запрошенный size был `1536x1024`; указаны фактические размеры ответа. Credentials не переносились в сессию InfiniCrafter и не публиковались.
- Собственный браузерный вход с реальным аккаунтом, полный live craft и запуск игры этим прогоном не проверялись. Перед использованием нужно выполнить **Sign in with ChatGPT** в InfiniCrafter.
