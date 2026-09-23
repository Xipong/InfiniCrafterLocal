# Транспорт LLM: форма запроса и лимиты провайдера

Документ фиксирует одно проверенное ограничение: **strict JSON Schema для Gameplay
Author не принимается Google Gemini**, поэтому форма запроса — это осознанная
настройка, а не деталь реализации. Ownership: `llm_transport.py` (транспорт),
`settings_schema.py` (пресеты/подсказки GUI), `author_item_contract.py` (схема).

## Короткий вывод

| Настройка | Значение | Статус на Gemini |
| --- | --- | --- |
| `INFINI_LLM_RESPONSE_FORMAT` | `json_object` | работает |
| `INFINI_LLM_RESPONSE_FORMAT` | `json_schema` | **отклоняется**: `400 INVALID_ARGUMENT`, транспорт сам повторяет стадию с `json_object` и пишет об этом в лог |
| `INFINI_LLM_RESPONSE_FORMAT` | `auto` | для удалённых API разворачивается в `json_schema`, поэтому проходит через тот же авто-переход |
| `INFINI_LLM_API_MODE` | `chat_completions` | работает |
| `INFINI_LLM_API_MODE` | `responses` | у Gemini эндпоинта нет: `404`, затем downgrade в chat |

Пресеты с удалённым провайдером (`openai_compat`, `openrouter`) явно закрепляют
`json_object` + `chat_completions`. Локальные пресеты (LM Studio) не тронуты:
локальные серверы strict schema держат, и она там полезна.

## Что именно происходит

`400 INVALID_ARGUMENT` возвращается **до чтения промпта**: провайдер отклоняет
форму запроса, модель задание не получает, токены не расходуются. Из-за этого
ошибка выглядит как «генерация не запустилась» без объяснения причины.

Причина — не одно запрещённое ключевое слово и не объём промпта, а бюджет
сложности грамматики constrained decoding. Замеры на реальной схеме Author:

```
схема Author целиком        85 579 символов, 4043 узла, глубина 16, 519 ограничений
runtimeProgram.calls        51 вариант в oneOf, maxItems 48
```

Изоляция по частям (живые запросы к Gemini, chat completions):

```
name + category + concept                        200 OK
+ runtimeProgram                                 400        <- граница
runtimeProgram.entities                          200 OK
runtimeProgram.calls (51 вариант)                400
одиночный вариант capability как items           200 OK
oneOf[2 реальных варианта]                       200 OK
oneOf[32 синтетических объекта]                  200 OK
items = реальный вариант, maxItems 8             200 OK
items = реальный вариант, maxItems 48            400
items = string,            maxItems 48           200 OK
```

По отдельности допустимы и `pattern`, и `const`, и `minItems`/`maxItems`, и
`oneOf`, и неизвестные ключи `x-infini-*`, и `$schema`. Отклоняется их
произведение: широкий `oneOf` капабилити × большой `maxItems` × сотни
ограничений. Снятие отдельных ключей не помогает — проверено на вариантах
`minus pattern`, `minus minimum/maximum`, `minus все ограничения`.

Официальная документация Google описывает это только качественно: «Very large or
deeply nested schemas may be rejected», без числовых порогов. Поэтому лимит
нельзя выразить как «уменьшить схему до N символов».

## Почему json_object безопасен по архитектуре

`json_object` — не fallback в смысле `AGENTS.md` и не подмена авторства:

- форму ответа модель уже получает из промпта: `requiredJsonShape`
  (`author_item_prompt_shape_card`), плюс `runtimeProgramInvariants` и `selfCheck`;
- авторитетными остаются локальные владельцы: валидатор, компилятор и wire-гейт;
- механику по-прежнему выбирает модель, код не достраивает содержание;
- невалидный ответ идёт в единственный условный Repair, как и раньше.

Провайдерская strict schema была подстраховкой транспорта, а не источником
истины. Её отсутствие снижает вероятность синтаксического брака, но не меняет,
кто владеет смыслом.

## Диагностика вместо голого 400 и починка на прогон

Транспорт делает две разные вещи, и их важно не путать.

**1. Диагноз.** `request_shape_rejection_diagnosis` в `llm_transport.py` объясняет
отказ в терминах настроек пользователя. Вызывается только при `HTTP 400` с
отправленным `json_schema`, ничего не выбирает, не повторяет запрос и не меняет
payload. Результат попадает в три места:

1. `cache/events.ndjson` — событие `LLM provider rejected the configured request shape`
   с полями `configuredResponseFormat`, `configuredApiMode`, `schemaChars`,
   `knownWorkingResponseFormat`, `knownWorkingApiMode`, `providerBody`;
2. `pipeline_trace.ndjson` — в payload ошибки стадии как `requestShapeRejection`;
3. текст ошибки крафта — пользователь видит, что промпт не оценивался и какая
   комбинация настроек проходит.

**2. Починка на прогон.** По той же модели, что уже работает для
`responses -> chat_completions`, транспорт повторяет **ту же самую стадию** с
`response_format: json_object` и пишет об этом отдельное событие:

```
LLM strict json_schema rejected; retrying same stage with json_object for this run
    was: json_schema
    now: json_object
    status: 400
    repairedFor: this run only; config.env is not modified
    schemaChars: 85093
    configuredResponseFormat: json_schema
```

Свойства этого перехода:

- меняется **только конверт ответа**; `messages`, `model`, сэмплирование и
  reasoning копируются без изменений, то есть промпт остаётся тем же;
- `config.env` не правится — настройка пользователя остаётся его решением, а лог
  прямо говорит, что починка действует только на текущий прогон;
- результат помечается как транспортный ретрай:
  `transportRetryCauses: ["json_schema_to_json_object_fallback"]` и
  `strictSchemaDowngraded: true`, поэтому acceptance-прогоны с
  `--require-zero-transport-retries` его видят и не считают бесплатным;
- профиль запоминается на процесс: после первого отказа следующие стадии сразу
  уходят с `json_object`, без повторной платы отклонённым запросом;
- ровно одна повторная попытка. Если провайдер отклоняет и `json_object`, ошибка
  доходит до вызывающего — маскировки настоящей поломки нет.

Разграничение владельцев сохранено: `401/403/429` остаются auth/quota, `404` —
несовместимость эндпоинта, таймауты и `5xx` — транспорт и pool failover. И диагноз,
и переход формата срабатывают только для `400` с отправленным `json_schema`.

Это не `Fallback` в смысле запрета из `AGENTS.md`: смысл предмета никто не
достраивает, деградации авторства нет. Отклонена форма конверта, и заменяется
именно она — на ту, которая доказанно принимается тем же провайдером.

## Отдельно: 400 под параллельной нагрузкой

Существует второй, независимый источник `400` — параллельные тяжёлые запросы даже
с `json_object`. В прогоне Live20 (`json_object` + `chat_completions`,
`parallelCrafts 3`) три кейса получили `400` на запросах ~94k символов при
`activeHttp 3`, рядом с живыми `Connection refused` и `RemoteDisconnected`.
Прошедшие кейсы имели такие же промпты, поэтому дело в одновременности, а не в
размере. Это транспортная нагрузка, а не форма запроса, и она не лечится сменой
`response_format`.

Практическое следствие: `json_object` разблокирует одиночный крафт полностью, но
для параллельных кампаний надо учитывать лимиты провайдера (у бесплатного Gemini
это в том числе 15 запросов в минуту — минутное окно, а не исчерпание квоты).

## Проверка

```bash
PYTHONPATH=LocalGenerator pytest -q LocalGenerator/tests/test_llm_request_shape_diagnostics_contract.py
PYTHONPATH=LocalGenerator pytest -q LocalGenerator/tests/test_settings_gui_contract.py
```

Контракт закрепляет: диагноз выдаётся только для `400` + `json_schema`, содержит
обе конфигурации, не мутирует payload, не несёт готовый `response_format`;
авто-переход меняет только конверт ответа, сохраняет `messages`/`model`, помечает
результат как транспортный ретрай, запоминает профиль на процесс, делает ровно
одну повторную попытку и не маскирует ни повторный `400`, ни `429`; API-пресеты
закрепляют рабочий транспорт; `json_schema` остаётся выбираемым вариантом с
честной пометкой.
