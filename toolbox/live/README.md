# Live10 / Live20 и явные real-image итерации

Исторический режим ниже по умолчанию жёстко блокирует image inference.
Отдельный `--real-images` не меняет старые панели и не использует synthetic PNG.

## Сначала offline

Из корня репозитория:

```bash
python -m toolbox live10
python -m toolbox panels
python -m toolbox live20 --expected-case-count 20
python -m toolbox live20 --preset live20-classic-sprites
python -m toolbox live10 --help
python -m toolbox live20 --config /path/outside/repo/private.env --preflight-only
```

`--preflight-only` — явный синоним безопасного режима по умолчанию, не разрешение
на сеть. Он не импортирует runtime и не пишет даже `--output`. Проверяет выбранные
комбинации и наличие родителей, формат/ranges аргументов, заданные ожидания config,
а с `--expected-head` — точный clean commit. **Не проверяет фактическую доступность
сервиса или effective request sampling**: `requestSettingsVerified=false` честно
остаётся в отчёте. Последние проверяются непосредственно перед sender.

Без `--config` учитываются environment и, если есть, `LocalGenerator/config.env`.
Environment имеет приоритет; используется канонический `core/env_file.py` codec
(legacy / JSON-string формат, first occurrence wins). `INFINI_SKIP_CONFIG_FILE=1`
отключает только неявный файл; явный `--config` читается и при нём. Файл не меняется,
ключи/credentials не выводятся. URL с userinfo/query/fragment отвергается без echo.
Настройки провайдера и токены хранятся **вне Git**.

## Панели и fixture

`live10` по умолчанию — **исторический midgame**: от `night_missile`
(`NightsEdge` + `MagicMissile`) до `meteor_star_cannon` (`StarCannon` + `MeteorStaff`).
Это прежние 10 кейсов в исходном порядке и 20 точных parent rows, не subset Live20.
`live20` — прежние 20 пар, от `woodwork_blade` до `silt_extractinator`, и отдельный
исходный snapshot из 39 родителей. Есть восстановленный вариант тех же запросов
со `spriteReferenceRaw`: `live20 --preset live20-classic-sprites`.

Все пары, источники и fixtures — в [каталоге входов](../fixtures/README.md);
`python -m toolbox panels` показывает доступные пакеты без runtime/network.
`--preset` выбирает пакет вместе с его собственным fixture. Нельзя смешивать его
с `--cases-file`; `--runtime-dump` остаётся явной заменой родительских данных.
Новый subset из PR141 доступен только как `live10 --preset live10-starter`.

Восстановлены исторические **входы**, не старая версия production-кода или ответов.
Исполняется настоящий текущий pipeline Gameplay Author → Visual/VFX → conditional
Repair и delivery с прежним no-image control. Старые модели/порты/температуры не
назначаются defaults. Точные bytes fixture и SHA256 case-пакета записываются в
preflight и campaign manifest; успешность прежних прогонов не наследуется.

`--cases id1,id2` выбирает subset известных IDs в порядке панели; `--cases-file`
читает JSON list или `{ "cases": [...] }` с `{ "case", "itemA", "itemB" }`, где
родители — `internalName` в dump. `--runtime-dump` заменяет fixture. Duplicate case
IDs / parent identities, неизвестные IDs и отсутствующие родители — отказ до сети.
Legacy `INFINI_LIVE_CASES` не уменьшает named panel неявно: subset выбирается только флагом.
Custom selection меняет знаменатель: не называйте запуск одного case «полным Live20».
При необходимости закрепите `--expected-case-count`.

## Явный live-запуск (нужна отдельная авторизация расходов)

Поддерживается только configured `openai_compat` с явно выбранным
`chat_completions` / `responses` и `json_object` / `json_schema`. Авторизация в
данной задаче **не включала live inference**; тесты toolbox используют offline doubles.

В private env должны быть `INFINI_USE_LLM=1`, provider/model/base URL/API mode/format
и нужные sampling/token settings. Подготовьте переменные shell из своей актуальной
конфигурации, а не копируйте исторические model/port presets. Все нижеследующие
значения — **ожидания**, они не перенастраивают production:

```bash
# QA_CONFIG / QA_OUT — приватные пути; остальные QA_* — уже выбранные вами значения.
# На этом шаге всё ещё НЕТ inference. QA_OUT не создаётся.
python -m toolbox live20 \
  --config "$QA_CONFIG" --output "$QA_OUT" \
  --expected-head "$QA_HEAD" --expected-case-count 20 \
  --expected-provider openai_compat --expected-model "$QA_MODEL" \
  --expected-base-url "$QA_BASE_URL" --expected-api-mode "$QA_API_MODE" \
  --expected-response-format "$QA_RESPONSE_FORMAT" \
  --expected-temperature "$QA_TEMPERATURE" \
  --expected-vfx-temperature "$QA_VFX_TEMPERATURE" \
  --expected-repair-temperature "$QA_REPAIR_TEMPERATURE" \
  --expected-max-tokens "$QA_AUTHOR_TOKENS" \
  --expected-visual-max-tokens "$QA_VISUAL_TOKENS" \
  --expected-vfx-max-tokens "$QA_VFX_TOKENS" \
  --parallel-crafts 3 --min-first-author "$QA_MIN_FIRST_AUTHOR"
```

После разрешения реальных text calls выполните **ту же команду с добавленным
`--run`**. Для Live10 замените имя и expected count. Run требует все показанные
freeze-поля (кроме явно дополнительного threshold/count), clean точный HEAD,
новый/пустой output, enabled LLM и отсутствие fallback/pools. `--run` и
`--preflight-only` несовместимы. Reasoning не назначается неявно:
`--expected-reasoning-effort VALUE` дополнительно проверяет все присутствующие
scalar/nested формы на logical **и actual HTTP** boundary. При отсутствии флага
нет заявления о frozen reasoning effort. Температуры, budgets, format и model
проверяются до отправки каждой стадии; изменение provider projection тоже RED.

Отсутствующий `--min-first-author` означает **0**, то есть без отдельного порога
first-Author quality, а не принятие исторического threshold. Успех всех cases,
author budget и полный accounting по-прежнему обязательны.

## Retry / evidence / границы результата

- Default: **0 case retries**, 3 parallel crafts. Low-level physical attempt budget
  принудительно равен 1 для учёта всех попыток. Model/route hopping запрещён.
- Явный `--transport-retries N` допускает повтор case **только** после подтверждённой
  transport-ошибки; `--transport-retry-delay-seconds` — 60..3600, по умолчанию 60.
  Malformed JSON/domain failures не запускают case retry. Стадийный scoped Repair
  остаётся у настоящего production producer и учитывается отдельно.
- Scheduled/completed waits, failed logical calls и physical starts сохраняются.
  Recovered case **не** превращает первый неудачный Author в first-Author success.
- `campaign_manifest.json` связывает HEAD, harness/accounting/fixture bytes,
  выбранные IDs, настройки и retry policy. `logical_llm.ndjson`, `http_llm.ndjson`,
  `harness_events.ndjson`, `image_boundary.ndjson`, `results.ndjson` сохраняются
  в private output. Завершённый result записывается сразу, не после общего barrier.
- `summary.json` — итог runner; `python -m toolbox summary "$QA_OUT"` независимо
  пересчитывает receipt accounting, включая прерванный запуск. Raw traces содержат
  prompts/ответы и **не входят в PR**.
- Cache, world-recipes и synthetic PNG изолированы в output; runtime config,
  игровые saves и постоянные world/cache записи не обновляются. Нет install/login,
  OAuth, game/GPU или публикации.
- Image backends hard-blocked. Один технический PNG и synthetic private readiness
  observer не доказывают настоящее изображение; production strict gate не ослаблен.
  PNG bytes/serving root/selected owner по-прежнему проверяются настоящими gates.

Общий каталог команд: [../README.md](../README.md).


## Восстановленный real-image runner

`--real-images --run` использует только canonical `openai_codex` Responses и image
backend, без agent bridge. Нужны все обычные `--expected-*` аргументы, дополнительно
`--expected-image-model`, `--expected-image-quality`, `--expected-image-size`,
`--expected-reasoning-effort`, `--attempt-budget` и `--parallel-crafts 1`.
Endpoint expectation: `https://chatgpt.com/backend-api/codex/`.
`INFINI_LLM_FALLBACK_NETWORK_FAILS=1`; `INFINI_SPRITE_RETRIES` должен совпасть с явным
`--image-retries` (по умолчанию0). Автоматических whole-craft повторов нет.

Ledger должен быть заранее инициализирован владельцем кампании: CLI не создаёт и
не сбрасывает бюджет. Восстановленная кампания имеет отдельный явно записанный
opening debit51, а не выдуманные исторические строки. Каждый новый combine сначала
получает атомарную reservation; ошибки и crash не возвращают её автоматически.

Для точного native request custom case может дополнительно содержать
`"inputJson": "relative/path/to/native.input.json"`. Путь разрешается относительно
cases file. Оба полных parent snapshots обязаны совпасть с `--runtime-dump`.
Root context сохраняется, SHA исходного файла проверяется до execution; сохраняются
исходные bytes и фактически переданный payload. Без inputJson используется стабильный
case-derived QA worldId, не позиция кейса в subset. Это новый контекст, не обещание
равенства потерянному историческому запросу.

`real_run.py` сохраняет canonical image processing, delivery/asset roster и storage
owners; все cache/world recipe roots изолированы внутри нового `--output`.
Физические POST наблюдаются через существующий `codex_auth.generation_observations`,
без headers, токенов или response body в metadata ledger. Незавершённые calls,
потерянные observations и отсутствующие обязательные стадии не превращаются в PASS.
Codex не отправляет logical temperature/output-token budget в wire: это не cost cap.

Каждая попытка имеет input, admission, logical requests, physical metadata,
final DTO (если получен) и terminal receipt. Существующий output не перезаписывается.
Pipeline PASS не является art/native gameplay PASS. Exact image reuse и VFX-only
replay пока не восстановлены: соответствующие flags явно отклоняются, а не молча
подменяются новой полной генерацией. Старые тестовые результаты не относятся
автоматически к этой реконструкции.

Effective projected text model/effort/format также проверяются перед canonical SSE send;
Visual reasoning override не может незаметно поменять выбранный effort.
`--require-zero-transport-retries` проверяет фактически наблюдаемые повторные POST,
включая изображения; разрешённый image retry всё равно виден и при этом flag даёт RED.
Незавершённые physical attempts не скрываются completed call envelope.
