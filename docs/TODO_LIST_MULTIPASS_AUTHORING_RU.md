# ToDoList Very Later — multipass authoring и кодовая валидация каждого запроса

Этот документ фиксирует дальний ToDo, а не текущее runtime-поведение. Пока нет отдельной реализации, тестов и contract markers, текущий pipeline остаётся single-pass authoring + deterministic Python/C# validation.

## Главная идея

Один внешний combine-запрос игрока в будущем нужно дробить на несколько внутренних LLM-запросов, чтобы не держать весь предмет, gameplay, projectile, armor/accessory, VFX, sound, runtimePlan и debug в одном огромном промпте.

Правильная форма:

```text
один запрос игрока
→ Core Author request
→ code validation of core fragment
→ zero or more Specialist Author requests
→ code validation of each specialist fragment
→ optional targeted repair/retry of failed fragment
→ deterministic merge
→ final compiler/validator
→ C#/tModLoader runtime execution
```

То есть “несколько ИИ” — это не спорящие авторы, а несколько узких authoring-pass’ов, каждый со своим контрактом и полями, после которых код проверяет результат.

## Почему это нужно

Single-pass authoring будет всё хуже масштабироваться:

- контекст растёт быстрее, чем качество ответа;
- модель забывает поля и runtime API;
- projectile/armor/accessory/VFX начинают мешать друг другу;
- красивые prose-фрагменты иногда попадают туда, где нужен исполнимый JSON;
- один сломанный кусок вынуждает переотправлять весь предмет;
- debug становится нечитаемым: непонятно, кто именно сломал payload.

Multipass нужен, чтобы изолировать ответственность:

```text
Core Author отвечает за общий предмет.
Projectile Author отвечает только за projectile fragment.
Armor Author отвечает только за armor fragment.
Accessory Author отвечает только за accessory fragment.
VFX/Sound Author отвечает только за presentation fragment.
Код проверяет каждый fragment до мерджа.
```

## Обязательный принцип: routing не по словам prompt

Нельзя делать так:

```text
если prompt содержит “лук” → вызвать projectile author
если prompt содержит “броня” → вызвать armor author
```

Это нарушает философию проекта и превращает код в category-router.

Нужно делать так:

```json
{
  "authoringModules": {
    "projectile": true,
    "melee": false,
    "armor": false,
    "accessory": false,
    "mobility": true,
    "vfxSound": true
  }
}
```

То есть первый LLM-pass сам структурно заявляет, какие модули нужны. Код только проверяет, что заявка валидна и bounded.

## Будущие pass’ы

### 1. Core Author

Пишет только центральный замысел предмета:

- `displayName`;
- `fantasy`;
- `mergeLogic`;
- `resultKind`;
- общий playstyle;
- parent facts summary;
- primary/secondary runtime intent;
- список нужных `authoringModules`;
- общий budget envelope.

Core Author не обязан расписывать весь projectile/armor/accessory. Он должен дать достаточно устойчивый “скелет”, чтобы specialist не изобретал другой предмет.

### 2. Code validation после Core Author

Код проверяет core fragment до запуска specialists:

- валидный JSON object;
- текущий runtime API/schema markers;
- `resultKind` в поддержанном диапазоне;
- `authoringModules` не противоречат `resultKind`;
- нет gameplay из visual prompt;
- нет unsupported fishing/bait runtime;
- parent facts не потеряны;
- immutable fields можно зафиксировать для следующих pass’ов.

Если core fragment плохой — retry только Core Author, а не весь pipeline.

### 3. Specialist Authors

Каждый specialist получает:

- immutable core context;
- parent facts;
- свой allowed field list;
- свой budget;
- список поддержанных runtime opcodes/fields;
- structured error bundle, если это retry.

Примеры:

```text
Projectile Author owns:
- attack.projectileKind
- attack.projectileSpeed
- attack.projectileScale
- attack.pierce/bounce/homing-ish bounded fields
- attack.onHitCode / debuffTime
- runtimePlan projectile engineCalls

Armor Author owns:
- armor.defense
- armor.equip effects
- armor set bonus fragment

Accessory Author owns:
- accessory movement/combat/utility modifiers

Presentation Author owns:
- visual/sound intent
- tooltips/debug prose
```

Specialist не имеет права менять чужие поля. Если projectile author внезапно вернул `armor.defense`, код должен выкинуть это в debug/droppedFields, а не молча принять.

### 4. Code validation после каждого Specialist Author

Это ключевой пункт документа.

После каждого LLM-ответа код должен прогнать fragment через отдельный валидатор:

- JSON extraction/parse;
- schema check;
- ownership check;
- allowed fields check;
- runtime API compatibility;
- opcode support check;
- budget/clamp preview;
- serialization check;
- deterministic normalization;
- debug/future-disabled quarantine для unsupported хвостов.

Кодовая валидация не должна “сочинять предмет”. Она должна либо:

```text
accept fragment
accept with safe fixes
drop unsupported/non-owned fields with debug
request targeted retry
fail module and continue without it
fail craft, если core невозможно исполнить
```

## Safe auto-fix whitelist

Автоматически чинить можно только очевидную техническую мелочь:

- casing/alias известных enum-like значений;
- `null` → пустая строка/массив там, где это безопасно;
- string/number/bool coercion, если смысл однозначен;
- дедуп тегов/engineCalls;
- clamp чисел по уже существующим runtime budget rules;
- удаление полей вне ownership;
- перенос неизвестного debug/prose в quarantine/debug bag;
- future-disabled для unsupported runtime hints, если это не ядро предмета.

Все auto-fix события должны попадать в debug.

## Targeted retry

Retry нужен, если локальный repair уже начал бы сочинять вместо модели:

- fragment не является JSON object;
- specialist вернул prose вместо contract fragment;
- отсутствует центральная часть заявленного module;
- unsupported opcode является ядром specialist fragment;
- clamp уничтожает весь замысел;
- module output конфликтует с immutable core fields;
- fragment нельзя безопасно сериализовать/доставить C#.

Retry должен быть точечным:

```text
не “сгенерируй предмет заново”
а “projectile specialist: исправь только projectile fragment по этим ошибкам”
```

## Retry budget

Чтобы не получить бесконечную мясорубку:

- максимум 1 retry на Core Author;
- максимум 1 retry на каждый Specialist Author;
- общий hard cap attempts на один craft;
- retry prompt получает previous fragment + error bundle + allowed fields;
- retry не может менять immutable core fields;
- если retry не помог — module отключается или craft fails по понятной причине.

## Deterministic Merger

Merger не должен быть ещё одной ИИ.

Его работа:

- склеить accepted fragments;
- применить ownership result;
- применить clamps/budgets;
- разрешить конфликты по заранее заданным правилам;
- сохранить unsupported/future-disabled хвосты в debug;
- собрать final payload для текущего compiler/validator.

Merger не решает “какой предмет правильный”. Он только исполняет контракт.

## Debug transparency

Финальный payload должен показывать, как предмет прошёл multipass:

```json
{
  "authoringDebug": {
    "multipass": {
      "enabled": true,
      "passes": ["core", "projectile", "presentation"],
      "acceptedModules": ["projectile", "vfxSound"],
      "autoFixes": [
        {"pass": "projectile", "path": "attack.debuffTime", "raw": 9999, "final": 600, "reason": "runtime_clamp"}
      ],
      "droppedFields": [
        {"pass": "projectile", "path": "armor.defense", "reason": "field_not_owned_by_module"}
      ],
      "retries": [
        {"pass": "projectile", "attempt": 1, "result": "accepted"}
      ],
      "failedModules": []
    }
  }
}
```

Если поле не работает, было отброшено, future-disabled или переотправлено — это должно быть видно.

## Будущие env/config flags

Черновой список ручек:

```text
INFINI_MULTIPASS_AUTHORING=0/1
INFINI_MULTIPASS_CORE_RETRY=1
INFINI_MULTIPASS_SPECIALIST_RETRY=1
INFINI_MULTIPASS_DEBUG_TRACE=0/1
INFINI_MULTIPASS_MAX_SPECIALISTS=3
```

Default на старте реализации:

```text
INFINI_MULTIPASS_AUTHORING=0
```

Сначала debug-only/opt-in. Default-on только после логов и тестов.

## Минимальный план реализации Very Later

1. Добавить data classes для `CoreFragment`, `SpecialistFragment`, `ValidationReport`, `MergeReport`.
2. Реализовать validator для Core Author output.
3. Реализовать validator для одного specialist module.
4. Добавить debug-only multipass trace без изменения final payload.
5. Включить одного specialist’а, лучше projectile.
6. Добавить deterministic merger.
7. Добавить targeted retry.
8. Сравнивать single-pass vs multipass на replay fixtures.
9. Только потом включать opt-in для реального craft.

## Тесты перед реализацией

Нужны contract/regression tests:

- routing идёт только из structured `authoringModules`, не из prompt text;
- specialist не может менять чужие поля;
- validator ловит невалидный JSON до merger;
- auto-fix работает только по whitelist;
- retry ограничен budget’ом;
- unsupported opcode не исполняется молча;
- final merge deterministic;
- debug содержит accepted/dropped/fixed/retried modules;
- current runtime API sync не ломается;
- single-pass fallback остаётся рабочим.

## Что нельзя делать

- Нельзя category-routing по словам prompt.
- Нельзя давать specialist право менять fantasy/resultKind.
- Нельзя превращать visual prompt в gameplay.
- Нельзя делать merger через ещё одну свободную ИИ без ownership rules.
- Нельзя silently repair/drop без debug.
- Нельзя переотправлять весь предмет, если сломан только projectile fragment.
- Нельзя включать fishing/bait runtime без настоящей C# реализации.

## Статус

**ToDo Very Later / architecture note.**

Это общий ToDoList по будущему разделению одного combine-запроса на несколько внутренних LLM-запросов с обязательной кодовой валидацией каждого fragment. Это не текущая реализация.


## Related Very Later ToDo: Applied vs Authored Validator

See `docs/TODO_APPLIED_VS_AUTHORED_VALIDATOR_RU.md` for the future validator that checks whether each authored field was parsed, compiled, applied by C# runtime, or honestly marked as future/unsupported.

## v0.4.217 note: repair boundary before C#

Перед C#/tModLoader должен стоять явный repair/retry слой. Это не баланс-авторитет и не новый автор предмета.

Разделение:

```text
форма кривая, но данные/абилки норм → code-only structural repair
форма норм, но предмет не исполним → targeted retry
форма норм, но балансный пиздец → optional tradeoff retry later
форма/смысл полный труп → one retry, then fail/refund/debug
```

Structural repair должен чинить очевидную форму без LLM:

- `runtime_plan` / `engine_calls` / `calls` → `runtimePlan.engineCalls`;
- object/dict call → list of calls;
- `op` / `type` / `kind` / mapping shorthand → `fn`;
- `args` / `arguments` / `payload` → `params`;
- `shot_count`, `use_time`, `projectile_speed`, `homing` → canonical params;
- obvious numeric strings вроде `"24 ticks"`, `"3 shots"`, `"0.35"` → numbers.

Retry нужен только когда code-only repair уже начал бы сочинять вместо модели.

## ToDo: armor/accessory soft budgets

Не тащить сейчас в prompt и не делать helper. Позже добавить Python-owned soft budget layer для `ArmorSpec` и `AccessorySpec`, похожий по архитектуре на weapon balance, но без hard progression gates.

Нужно:

- total accessory budget, а не только per-field absolute caps;
- piece budget vs set bonus budget для generated armor;
- явное разделение `balanceClamp`, `safetyClamp`, `contractClamp`;
- внутреннее переименование stage-like bucket в powerBand/label, чтобы не звучало как hard gate;
- debug report, почему поле ужато.

## ToDo: replay harness вместе с multipass

Replay harness делать вместе с multipass, потому что максимальная ценность появится при нескольких author fragments.

Будущий replay-case должен сохранять:

```text
parents.json
core_author_response.json
specialist_responses.json
structural_repairs.json
retry_patches.json
merge_report.json
final_generated_item.json
validation_report.json
compiled_runtime.json
```

Команда будущего вида:

```text
python tools/replay_generation_case.py <case_id>
```

Цель: быстро понять, где сломалось — authoring, structural repair, targeted retry, merger, compiler или C# contract.
