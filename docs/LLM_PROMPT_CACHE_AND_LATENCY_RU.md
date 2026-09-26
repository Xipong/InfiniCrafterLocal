# Prompt cache и задержка LLM-стадий

## Граница реализации

Prompt cache — переиспользование провайдером вычисленного KV-префикса, **не** кеш готового предмета и не JSON-файл с инструкциями на диске. Каждый craft получает новые ответы Author → Visual → VFX; валидация, scope/frozen Repair и выбор механик не меняются.

Author уже ставил инструкции и каталог перед recipe-specific полями. Новая реализация явно маркирует конец этого префикса для адаптеров. Visual/VFX и Repair переставляют только порядок существующих JSON-полей: постоянные правила/доступный каталог идут первыми; родители, runtime IDs, принятый visual kit, ошибки и точные per-item schemas остаются переменными. Полный JSON, его значения и два исходных сообщения сохранены. Никакие возможности не удаляются ради cache hit; полный Author-каталог не добавляется в scoped Repair или следующие стадии.

На одинаковом локальном serializer-входе Workbench + Sword: system 3457, user 88744 символа; отмеченный постоянный user-префикс — 87712 символов. Вместе с system это 91169 из 92201 символа. Это размер кандидата для повторного использования, **не** число закешированных токенов и не доказательство cache hit. Короткие префиксы Visual/VFX могут не достигнуть минимального token threshold конкретной модели.

## Owners и transport

- `core/llm_prompt_cache.py`: `json_prefix_chars` проверяет порядок начальных статических полей; `with_prompt_cache_prefix` добавляет только internal marker `_infini_prompt_cache = {messageIndex, prefixChars}`. Marker никогда не отправляется провайдеру.
- `pipelines/llm_authoring_pipeline.py`: границы обычного Author, scoped/format Repair и VFX.
- `pipelines/visual_generation_pipeline.py`, `core/vfx_manifest.py`: порядок статических/динамических полей Visual/VFX.
- `pipelines/llm_transport.py`: проверка endpoint/model, точная проекция breakpoints, content-derived routing identity и usage.
- `services/codex_text_backend.py`: whitelisted subscription payload и счётчики usage.

Для поддерживаемого routing hint ключ получается из SHA-256 system/предшествующих сообщений + точного статического user-префикса + выбранной модели/response format/reasoning. Recipe-specific суффикс, случайный craft UUID, время, API keys и account IDs в routing key не добавляются. Одинаковые байты дают тот же ключ в новом процессе; изменение инструкций, модели или каталога меняет identity. Различающаяся strict provider schema также может менять identity: нельзя скрывать exact entity IDs/schema ради кэша.

Отмеченные stage packets остаются самостоятельными. Responses не присоединяет к ним `previous_response_id` прежней стадии и не сохраняет continuation для следующей: conversation continuation не заменяет prompt cache и не должна добавлять уже переданные исторические токены к самодостаточному stage dossier. Неотмеченные legacy/generic transport calls сохраняют прежний API-контракт.

## Поддержка провайдеров

- **OpenAI Platform** на точном `https://api.openai.com/v1` и **OpenRouter/OpenAI** на точном `https://openrouter.ai/api/v1`: для числовых GPT-семейств 5.6+ transport отмечает конец постоянного префикса `prompt_cache_breakpoint`, использует `prompt_cache_options.mode=explicit` и стабильный `prompt_cache_key`. Chat получает `text` blocks, Responses — `input_text`; их конкатенация точно равна исходной строке. Переменный суффикс не маркируется для cache write. Более ранние распознанные GPT-модели получают routing key без новых breakpoint-параметров.
- **Codex subscription**: передаётся только поддержанный upstream `prompt_cache_key`; остаются `store=false` и subscription-only endpoint. Platform breakpoints, retention и cache resource API автоматически не переносятся в subscription transport. Routing hint не гарантирует переиспользование длинного префикса на всех версиях моделей.
- **Прямой Gemini/OpenAI-compatible**: сохранён стабильный префикс для implicit caching; OpenAI-параметры не отправляются в Google. Создание `cachedContents`, хранение с оплачиваемым TTL и переход на платный маршрут **не включены**. Для явного Gemini-кэша требуются отдельное разрешение на платную функцию и реализация lifecycle ресурса.
- **Остальные compatible/local endpoints**: получают прежние сообщения без чужих provider-specific параметров. Локальный `cache_prompt`, slot save/restore или долговечный KV-файл нельзя обещать без поддержки конкретного сервера; эта работа их не включает.

KV хранит провайдер, не LocalGenerator. Детерминированный ключ переживает перезапуск приложения, но сам provider cache может истечь или быть вытеснен. Для OpenAI 5.6+ документация описывает default TTL 30 минут; код не продлевает его отдельными платными запросами и не обещает бессрочное хранение. Смена модели/endpoint/account и изменения provider-side префикса могут дать miss даже при том же тексте.

## Наблюдаемость

Transport debug / `LLM usage` сохраняет:

- `cachedInputTokens`: фактически возвращённые `cached_tokens`, `null`, если провайдер их не сообщил;
- `cacheHit`: `true` только при сообщённом положительном числе, `false` при явном нуле, `null` при отсутствии данных;
- `cacheWriteTokens`: фактически сообщённые `cache_write_tokens` либо `null`.

Готовность запроса к caching и присутствие key/marker никогда не считаются cache hit. Codex пропускает только проверенные неотрицательные целочисленные counters, без произвольных metadata и credentials. OpenAI и OpenRouter могут брать отдельную ставку за cache write: explicit mode ограничивает запись постоянным префиксом, но не означает бесплатную запись.

## Локальная производительность

Убрана eager-сборка большой provider schema, если выбран `json_object` или response format отключён. В `json_schema` factory вызывается как прежде; локальные strict validator/schema checks не отключаются. Постоянный config, модель, reasoning, лимиты ответа и число стадий не изменены.

Парный offline-замер production `build_initial_author_request`: 5 прогревов и 101 измерение, одинаковые Workbench/Sword/model fixture. До — `591f439`; после — lazy schema и prefix marker. Медиана `json_object`: **4.921 → 2.236 мс**. Сериализованный request без internal marker имеет тот же SHA-256; system/user и смысловой запрос не изменились. В `json_schema` в этом замере **5.010 → 6.100 мс**: вычисление границы добавляет локальную работу, выигрыша в этом режиме не заявляется. Это один локальный microbenchmark, не игровая latency и не сетевой A/B.

Основное ускорение полного craft зависит от remote prefill, decode/reasoning, количества Repairs и квот/ожидания. Несколько миллисекунд подготовки не превращают десятки секунд LLM-работы в мгновенный craft. Урезание self-evaluation/capabilities, уменьшение reasoning и параллельный запуск зависимых стадий без доказательства эквивалентности не выполнялись.

## Проверка

Offline regressions проверяют разные recipes и процессы, invalidation, отсутствие internal marker в provider wire, побайтовое сохранение текста при split, unknown endpoints, explicit zero против missing usage, scoped Repair и настоящую ветвь same-profile Responses lease с предыдущим response ID. Проверки transport используют перехват HTTP/адаптера; это не доказательство принятия запроса живым провайдером или фактического GPU cache hit.

Новый live LLM/image/game/MP запуск в эту работу не входит. Для измерения end-to-end выигрыша нужен отдельный разрешённый paired cold/warm запуск на выбранном endpoint/model с сохранением provider usage; прежний Live20 не превращается в новый acceptance.

## Источники

- [OpenAI: prompt caching, breakpoints, routing key, lifetime](https://developers.openai.com/api/docs/guides/prompt-caching)
- [OpenRouter: sticky routing, cache usage, explicit OpenAI caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [Gemini: implicit/explicit caching и платное TTL-хранение](https://ai.google.dev/gemini-api/docs/generate-content/caching)
- [Codex upstream: ResponsesApiRequest.prompt_cache_key](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/common.rs)
