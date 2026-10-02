# LLM transport: форма запроса и ошибки

[Transport owner](../LocalGenerator/infini_local/pipelines/llm_transport.py), [GUI presets](../LocalGenerator/infini_local/desktop/settings_schema.py), [setup/restart](../QUICK_START_RU.md#настройки). Локальный serializer и прежний live probe — не универсальные capabilities provider/model.

## Настройки

| Поле | Текущая семантика |
|---|---|
| `INFINI_LLM_RESPONSE_FORMAT=json_object` | JSON hint; shape в prompt, local validator/compiler/wire gate обязательны |
| `…=json_schema` | Provider schema; endpoint/model имеет собственный complexity budget |
| `…=auto` | **Remote → json_object, local → json_schema**, если stage не задал `auto_preference`; explicit choice сохраняется |
| `…=off` | Нет provider format, но local validation остаётся |
| `INFINI_LLM_API_MODE=chat_completions` | Stateless `/chat/completions` |
| `…=auto`/`responses` | Пробует `/responses`, допускает same-profile Chat compatibility downgrade |

Remote presets: `json_object` + `chat_completions`; local сохраняют schema. Это starting point, не availability guarantee. Codex — отдельный subscription Responses adapter: [auth/limits](CODEX_IMAGE_OAUTH_RU.md#модели-качество-и-расход).

`json_object` не semantic fallback: `requiredJsonShape`, `runtimeProgramInvariants`, `selfCheck` остаются в prompt; invalid response → условный Repair/RED. Без constrained grammar синтаксического брака **может стать больше**, но provider schema не gameplay authority.

## Retries и границы ошибок

| Событие | Policy |
|---|---|
| Chat 400 + sent `json_schema` | Один same-stage повтор с `json_object`; только envelope меняется, messages/model/sampling/reasoning сохранены |
| Повторный 400 с `json_object` | Второго schema downgrade нет; ошибка идёт higher-level policy |
| Responses 400/404/405/415/422/501 | Same-profile stateless Chat, если ошибка не распознана auth/budget; не network/timeout downgrade |
| 401/402/403/429 | Auth/billing/quota/rate-limit, не schema cure; 429 также transport-class с provider cooldown |
| 408/409/425/429/500/502/503/504, network/timeout | Bounded transport retry и/или настроенный pool/fallback |

Schema guard проверяет только status/format: **не доказывает причину каждого 400**. Profile/context capability memory действует на процесс; `config.env` не меняется. Debug: `strictSchemaDowngraded=true`, cause `json_schema_to_json_object_fallback`; API downgrade cause `responses_to_chat_fallback`. Content/length retry и profile failover отдельно учитываются в `transportRetryCount/Causes`: один envelope retry ≠ один суммарный HTTP.

[OpenRouter pin](OPENROUTER_ROUTING_RU.md#строгая-семантика) запрещает другой профиль/legacy fallback, но сохраняется при same-upstream envelope/API downgrade. Основной Codex не уходит на paid API. Unpinned pool/lease/cooldown и legacy резерв — отдельная явно настроенная policy; пустой `INFINI_LLM_FALLBACK_MODEL` выключает резерв.

## Диагностика

`request_shape_rejection_diagnosis`: только Chat 400 + `json_schema`, без изменения payload/retry. Повтор делает caller, событие `LLM strict json_schema rejected; retrying same stage with json_object for this run` (`was/now/status/repairedFor/schemaChars`).

| Где | Что смотреть |
|---|---|
| `cache/events.ndjson` | `LLM provider rejected the configured request shape`: configured/sent format, API mode, schemaChars, `knownWorkingResponseFormat/ApiMode`, bounded providerBody |
| `pipeline_trace.ndjson`, craft error | Stage `requestShapeRejection` / hint |
| `LLM usage`/debug | Retry count/causes, [cache counters](LLM_PROMPT_CACHE_AND_LATENCY_RU.md#наблюдаемость) |

`knownWorking*` и hint «модель ещё не получила задание» — локальная подсказка, **не remote billing proof**. Generic 400 не доказывает нулевой расход. Проверяй status/body/model/baseUrl.

## Исторический Gemini reproducer

Прежний конкретный Gemini Chat endpoint отклонял полную Author schema (400), Responses дал 404: **не запрет strict output всех нынешних Gemini**. Schema тогда: 85579 chars, 4043 nodes, depth 16, 519 constraints; calls `oneOf` 51 вариантов, maxItems 48.

| Изоляция | Прежний ответ |
|---|---|
| name/category/concept; entities; одиночный capability; oneOf 2 real / 32 synthetic objects | 200 |
| Полный runtimeProgram; calls 51 вариантов | 400 |
| Real variant maxItems 8 / 48 | 200 / 400 |
| String items maxItems 48 | 200 |

`pattern`, `const`, array bounds, `oneOf`, `$schema`, `x-infini-*` отдельно проходили; снятие pattern/min/max/всех constraints полную форму не исправляло. Complexity комбинации, не правило «до N chars»: [Google limitations](https://ai.google.dev/gemini-api/docs/structured-output).

Другой старый Live20 (json_object/Chat/parallel=3): три ~94k-char 400 при activeHttp=3 рядом с Connection refused/RemoteDisconnected. Concurrency — гипотеза, не доказанная причина; format не лечит network/rate-limit. Прежние free-tier 15 RPM — та конфигурация, не общий лимит новых моделей/аккаунтов.

## Проверка

[Request contracts](../LocalGenerator/tests/test_provider_request_contract.py), [transport](../LocalGenerator/tests/test_provider_transport_contract.py), [GUI](../LocalGenerator/tests/test_settings_gui_contract.py): envelopes/diagnosis/one-time downgrade/profile memory/pin/failure boundaries. [Offline QA](../LocalGenerator/QUICK_START_RU.md); [Live20](../toolbox/README.md) — отдельно разрешаемый запуск, не fixture-based billing/availability proof.
