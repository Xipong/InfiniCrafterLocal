# OpenRouter: точный upstream provider

**LocalGenerator 0.4.247 — поставка:** upstream pin включён; старый опубликованный ZIP 0.4.246 его не содержит. `LLM provider=openrouter` выбирает API; **OpenRouter provider slug** фиксирует upstream/endpoint за этим API. [Базовая настройка и restart](../QUICK_START_RU.md#настройки) общие.

## Настройка

GUI: **LLM → Другие провайдеры** → `openrouter` → API key/model slug → **OpenRouter provider slug**. Возьми точный slug из routing выбранной модели, не model slug/отображаемое название компании. Сохрани и перезапусти сервер.

```dotenv
INFINI_LLM_PROVIDER=openrouter
INFINI_OPENROUTER_API_KEY=<личный ключ вне Git>
INFINI_OPENROUTER_MODEL=owner/model
INFINI_OPENROUTER_PROVIDER=deepinfra
```

`deepinfra` — пример, не рекомендация/обещание доступности. Сохраняются регистр и endpoint suffix `/...`, если он опубликован OpenRouter; trim краёв не меняет содержимое. Пустой `INFINI_OPENROUTER_PROVIDER=` возвращает auto, **не** строка `auto`.

## Строгая семантика

Для непустого slug Chat Completions и Responses получают:

```json
{"provider":{"only":["deepinfra"],"allow_fallbacks":false}}
```

Pin принадлежит выбранному профилю, сохраняется в Author/Visual/VFX/Repair, stage model overrides, same-profile retries и допустимом [Responses → Chat downgrade](LLM_TRANSPORT_REQUEST_SHAPE_RU.md#retries-и-границы-ошибок). Недоступная площадка заканчивается ошибкой после допустимых повторов **на ней же**: соседний профиль/legacy fallback не обходят pin. Код не подбирает модель/цену и не запускает проверочную генерацию. Доступность и стоимость определяет сочетание model/provider/account.

Пустое поле сохраняет обычный routing/failover. В `local`, `openai_compat`, `openai_codex` provider object не отправляется.

## Несколько профилей

| Профиль | Независимое поле |
|---|---|
| LLM 1 | `INFINI_OPENROUTER_PROVIDER` |
| LLM 2 / 3 / 4 | `INFINI_LLM_POOL_2_OPENROUTER_PROVIDER` / `INFINI_LLM_POOL_3_OPENROUTER_PROVIDER` / `INFINI_LLM_POOL_4_OPENROUTER_PROVIDER` |
| Legacy fallback | `INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER` |

Pin не наследуется: пустое поле другого профиля — auto. Начальный round-robin явно enabled profiles сохраняется; для одного upstream оставь enabled только один профиль. После выбора pinned profile failover запрещён. Multi-dev lanes сохраняют своё profile закрепление.

Fallback pin действует, только когда fallback действительно выбран и его provider — OpenRouter; pinned primary туда не переходит. GUI сохраняет поля при смене provider, но выключает неиспользуемые. Апдейт не меняет личный `config.env`/ключи.

## Источники и проверка

[Transport owner](../LocalGenerator/infini_local/pipelines/llm_transport.py), [config](../LocalGenerator/infini_local/core/llm_config.py), [offline regressions](../LocalGenerator/tests/test_openrouter_provider_settings.py) проверяют bodies/retry/isolation/GUI roundtrip. Это не live availability/price check.

[OpenRouter Provider Routing](https://openrouter.ai/docs/guides/routing/provider-selection) · [Responses ProviderPreferences](https://openrouter.ai/docs/client-sdks/python/sdks/responses/README).
