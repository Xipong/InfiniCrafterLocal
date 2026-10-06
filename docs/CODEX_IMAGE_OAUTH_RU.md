# ChatGPT / Codex OAuth: LLM и PNG

Собственная InfiniCrafter сессия, не Platform key/баланс; Codex CLI/Hermes не нужны. [Setup/GUI](../QUICK_START_RU.md); LLM и PNG selectors независимы.

## Включение

GUI тем же Python/пользователем, что сервер: **Sign in with ChatGPT** → browser login → `LLM provider=openai_codex`/text catalog/model и/или `Image backend=openai_codex` → Save/restart.

```dotenv
INFINI_LLM_PROVIDER=openai_codex
INFINI_CODEX_LLM_MODEL=<текстовый slug>
INFINI_CODEX_VISUAL_REASONING=inherit
INFINI_IMAGE_BACKEND=openai_codex
INFINI_CODEX_IMAGE_MODEL=gpt-image-2
INFINI_CODEX_IMAGE_QUALITY=medium
INFINI_CODEX_IMAGE_SIZE=1024x1024
INFINI_CODEX_IMAGE_TIMEOUT=240
```

CLI из `LocalGenerator`, тем же окружением:

```console
python -m infini_local.services.codex_auth login
python -m infini_local.services.codex_auth status
python -m infini_local.services.codex_auth logout
```

## Модели, качество и расход

| Поле/проверка | Contract |
|---|---|
| Text refresh | Read-only `/backend-api/codex/models?client_version=…`, text slugs/efforts аккаунта, не request success. Ошибка/неизвестный manual slug не стирают выбор |
| Image account ping | Read-only text catalog, без image quota, **без image entitlement check**. Подтверждённого image model API-каталога нет; `gpt-image-2` — известное имя, не доступ |
| `INFINI_CODEX_IMAGE_QUALITY` | `low\|medium\|high\|auto`, image request `n=1`; точный quota расход неизвестен. `auto` выбирает сервер |
| `INFINI_CODEX_IMAGE_SIZE` | `1024x1024\|1536x1024\|1024x1536\|auto`, исходный request, не sprite canvas |
| `INFINI_CODEX_VISUAL_REASONING` | `inherit\|model_default\|none\|minimal\|low\|medium\|high\|xhigh\|max`, **текстовые** Visual Director/visual repair; inherit → общий effort, model_default → omit |

Effort должен поддерживаться text model; `ultra` не отправляется. Общий reasoning off не отменяет минимум medium Gameplay Author; Visual использует model default. У image endpoint нет reasoning field; text slug не image model.

Subscription `/responses` не отправляет temperature/`max_output_tokens`: `INFINI_LLM_MAX_TOKENS` **не spending cap** (локально time/response-size bounds, не output-token cap). Основной `INFINI_LLM_PROVIDER=openai_codex` не переходит при auth/quota на paid route; image failure также не подменяется paid/procedural PNG. Keyed `image_api`/другие routes настраиваются отдельно и могут быть платными.

## Сессия и ошибки

- PKCE S256/state, loopback `127.0.0.1:1455`, redirect `http://localhost:1455/auth/callback`, timeout 180 с. Занят порт — закончи конкурирующий login; закрытие GUI отменяет ожидание.
- `~/.infinicrafter/codex-auth.json` профиля **пользователя Python** (Windows `%USERPROFILE%\.infinicrafter\codex-auth.json`): Linux `0600`, Windows DPAPI; вне config/Git.
- Access refresh перед запросом сериализован между GUI/серверными threads/processes. `status` проверяет файл, не quota.
- Logout удаляет только локальную InfiniCrafter session, не CLI/все ChatGPT sessions. Во время login первая **Sign out** отменяет ожидание, следующая после завершения удаляет файл.
- Windows/WSL profiles/DPAPI не переносимы; Windows session держи в Windows profile: прежний probe не поддерживал byte-range locks на `\\wsl.localhost\…`.
- HTTP code + bounded credential-redacted error сохраняются; OAuth/quota/network сбой не требует автоматического повторения генерации/paid переключения.

## PNG pipeline

`Visual prompt → общий concurrency gate → Codex → PNG checks → sprite postprocess → delivery`. Endpoints: `https://chatgpt.com/backend-api/codex/responses`, `/images/generations`, не Platform `/v1/images/generations`.

Positive prompt без дополнительной LLM; negative — suffix `\n\nAvoid: …`, отдельного field нет. Требуется одна base64 PNG, valid decoding/file bytes/dimensions, atomic publication; URL/повреждённый ответ не asset. [Image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md). Сервер может изменить внутренний API/entitlement.

## Фон и уменьшение PNG

В 0.4.248 `BG color=transparent` выбирает нативную alpha-ветку: Visual/VFX/image-промпты требуют прозрачный фон, Codex JSON отправляет `background=transparent`, локальный chroma-keyer/retry-key не применяется. При magenta/white и включённом Remove BG запрос имеет `background=opaque`; финальную прозрачность создаёт локальный keyer. Выключенный Remove BG также выбирает native alpha. Неподдерживаемый цвет не заменяется автоматически на magenta.

Базовый resize — `INFINI_SPRITE_DOWNSCALE_FILTER=box`, `INFINI_SPRITE_PREMULTIPLIED_RESIZE=1`; **Reset BOX** сбрасывает только эти две настройки. Сохрани изменения и перезапусти server. Offline transport/PNG проверки подтверждают отправляемые параметры и обработку, но не текущую поддержку native alpha подписным endpoint: отказ сервера остаётся явной ошибкой, без paid/procedural/opaque подмены.

## Проверка реализации

[Codex contracts](../LocalGenerator/tests/test_codex_subscription_contract.py), [image adapters](../LocalGenerator/tests/test_image_adapter_contracts.py), [GUI](../LocalGenerator/tests/test_settings_gui_contract.py), [offline QA](../LocalGenerator/QUICK_START_RU.md): PKCE/state/locks/privacy/SSE completion/dispatch/catalog/manual slug/quality/Visual reasoning, не live quota.

**Прежние результаты, не текущий acceptance:** 363 Python passed; headless tML/FNA 40/0; 12 gates/Ruff; dummy-config Windows Tk UI/roundtrip без login. CLI session только в памяти: text catalog, `/images/models` 404, JSON `/responses` (`gpt-6-sol`, low), `max_output_tokens` 400. Один image (`gpt-image-2`, high, requested 1536x1024): illustration PNG 1672×941, 44.07 с, не sprite; секреты в repo не переносились. Собственный browser login, full craft/GPU/MP не доказаны; новых live запросов здесь нет.
