# ToDo Roadmap Very Later — multipass authoring, applied-vs-authored, RuntimeArchetype и injection bridge

Статус: **единый каноничный ToDo-документ**. Он объединяет старые:

- `TODO_LIST_MULTIPASS_AUTHORING_RU.md`
- `TODO_APPLIED_VS_AUTHORED_VALIDATOR_RU.md`

Старые отдельные TODO-файлы больше не являются источником истины. Этот документ — backlog/roadmap, а не описание текущего runtime. Пока нет отдельной реализации, тестов и contract markers, текущий pipeline остаётся single-pass authoring + deterministic Python/C# validation.

## Главная рамка

InfiniCrafter должен оставаться data-authored:

```text
LLM authors identity / fantasy / runtimePlan / visual intent / numbers
Python validates, repairs shape, compiles explicit runtime specs, reports provenance
C# executes a finite set of bounded runtime primitives
```

Жёсткое правило на весь документ:

```text
routing идёт только из structured `authoringModules`, не из prompt text
```

Никаких category-router'ов по словам prompt, никаких item-specific таблиц, никаких скрытых gameplay-решений из visual prompt.

## Priority map

| Блок | Приоритет | Смысл |
|---|---:|---|
| Multipass authoring | Very later | Разбить один внешний craft на несколько узких LLM-pass'ов с кодовой валидацией между ними. |
| Applied vs Authored Validator | Very later, но обязательно | Проверять, дошло ли authored поле до реального C# runtime или честно помечено future/debug-only. |
| RuntimeArchetypeSpec compatibility guard | Later / architecture prework | Добавить archetype data shell без подмены runtimePlan.engineCalls и без enum-sprawl. |
| InfiniVanillaHookBridge / injection bridge | Very later / experimental | Глобальные detour/IL мосты, но локально gated только на конкретный generated item и только через whitelist contract. |

---

# 1. Multipass authoring и кодовая валидация каждого запроса

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

The Applied-vs-Authored validator is now part of this unified document. It checks whether each authored field was parsed, compiled, applied by C# runtime, or honestly marked as future/unsupported.

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

---

# 2. Applied vs Authored Validator

Очень позже, но обязательно: сделать отдельный валидатор, который сравнивает не только «что LLM написала», а весь путь поля до игры.

Цель:

```text
LLM authored
→ Python parsed
→ Python compiled
→ C# model field exists
→ C# runtime actually applies it
→ tooltip/debug честно показывает статус
```

Это не балансер и не автор предметов. Валидатор не должен решать, что предмет «должен быть мечом/луком/бронёй». Он только проверяет, что уже-authored поля реально дошли до исполнимого runtime или честно помечены как debug/future-disabled.

## Что проверять

Для каждого значимого поля:

- authored: есть ли поле в raw LLM JSON / runtimePlan.engineCalls;
- parsed: принял ли Python поле;
- compiled: попало ли оно в `GameplaySpec`, `AttackSpec`, `ArmorSpec`, `AccessorySpec` или debug/future блок;
- csharpField: есть ли поле в C# модели;
- runtimeApplied: есть ли реальный исполнитель в `GeneratedItem`, `GeneratedProjectile`, `InfiniCraftPlayer` и т.д.;
- tooltipVisible: видно ли игроку/разрабу, что поле применилось или было ограничено;
- status: `applied`, `clamped`, `future_disabled`, `unsupported`, `dropped`.

## Пример отчёта

```json
{
  "field": "AttackSpec.OnHitCode",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": true,
  "tooltipVisible": true,
  "status": "applied"
}
```

```json
{
  "field": "ArmorSpec.WhipRange",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": false,
  "tooltipVisible": true,
  "status": "future_disabled",
  "reason": "C# runtime does not implement generated whip range yet"
}
```

## Где хранить

В будущем:

```text
recipeMeta.appliedVsAuthored
/debug endpoint
/infiniitem command
Shift-tooltip short summary
```

## Жёсткие запреты

- Не делать category-routing по словам prompt.
- Не менять fantasy/resultKind.
- Не чинить баланс творчески.
- Не превращать validator в ещё одного автора.
- Не скрывать dropped/future fields.

Если поле не работает — отчёт должен прямо сказать, что оно future/debug-only, а не изображать готовую механику.

---

# 3. RuntimeArchetypeSpec compatibility guard

## Короткий вердикт

`RuntimeArchetypeSpec` **не убивает** multipass authoring и Applied-vs-Authored validator, если он вводится как **дополнительный data-authored contract layer**, а не как новый скрытый автор поведения.

Он, наоборот, может помочь: вместо бесконечного роста `movementCode` / `effectCode` / `onHitCode` можно описывать семью поведения на более высоком уровне:

```json
{
  "runtimeArchetype": {
    "source": "vanilla|generated|hybrid",
    "family": "boomerang|yoyo|flail|whip|held_swing|held_thrust|channel_beam|custom_executor",
    "vanillaProjectileId": "EnchantedBoomerang",
    "aiType": "EnchantedBoomerang",
    "overrideKnobs": {
      "returnDelayTicks": 24,
      "trailProfile": "amber_slime"
    }
  }
}
```

Но `RuntimeArchetypeSpec` должен быть **optional shell first**:

```text
Stage 1: model + JSON/network/save preservation only, no behavior change.
Stage 2: explicit adapters for a tiny whitelist: boomerang/yoyo/held projectile/channel beam. (`channel_beam` completed in the 2026-07-10 v9 gameplay patch.)
Stage 3: planner may author archetype, but validators decide supported/applied/future_disabled.
```

## Когда RuntimeArchetypeSpec полезен

Он полезен, если текущий executor layer начинает превращаться в enum-soup:

```text
movementCode 5 = boomerang
movementCode 16 = flail
movementCode 17 = yoyo
movementCode 18 = whip
movementCode 19 = ещё что-то
movementCode 20 = ещё что-то
...
```

Archetype layer позволяет говорить не “ещё один код”, а:

```text
family = yoyo
source = vanilla-like
adapter = supported_yoyo_adapter
knobs = bounded data
```

Это ближе к tModLoader/ExampleMod-паттернам: vanilla behavior можно использовать как archetype/adaptor, а не каждый раз переписывать AI с нуля.

## Когда RuntimeArchetypeSpec убьёт архитектуру

Он вреден, если сделать его так:

- C# сам выводит archetype из item name / tooltip words.
- Archetype silently overrides authored `runtimePlan.engineCalls`.
- `CloneDefaults` или vanilla AI подменяют damage/useTime/pierce/lifetime без provenance.
- Specialist modules пишут свои fields, archetype adapter пишет свои, merger молча выбирает “что красивее”.
- Applied-vs-Authored validator не видит archetype fields.
- Unsupported archetype исполняется fallback'ом без `future_disabled`/warning.
- Visual prompt выбирает gameplay archetype.

Это запрещено.

## Safe ownership model

Чтобы не конфликтовать с multipass:

```text
Core Author owns:
  resultKind, fantasy, mergeLogic, overall playstyle,
  authoringModules,
  optional runtimeArchetype intent/family/source.

Attack / Projectile Specialist owns:
  bounded archetype knobs,
  projectile dimensions,
  speed/lifetime/range/pierce,
  onHit/effect hooks within supported API.

Presentation Specialist owns:
  visual/sound/identity prompts,
  but never changes runtimeArchetype or resultKind.

Deterministic Merger owns:
  conflict resolution by fixed rules,
  field ownership enforcement,
  unsupported/future_disabled quarantine.

Compiler owns:
  mapping supported runtimeArchetype -> explicit AttackSpec/runtime fields.
```

## Required validator behavior

Every archetype field must participate in Applied-vs-Authored reporting:

```json
{
  "field": "AttackSpec.RuntimeArchetype.Family",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": true,
  "tooltipVisible": true,
  "status": "applied",
  "reason": "Exact overhead_barrage is backed by the bounded marker/delay/descending-child executor; retired family names are rejected"
}
```

If supported:

```json
{
  "field": "AttackSpec.RuntimeArchetype.Family",
  "authored": true,
  "parsed": true,
  "compiled": true,
  "csharpField": true,
  "runtimeApplied": true,
  "tooltipVisible": true,
  "status": "applied"
}
```

## Rule of thumb

```text
RuntimeArchetypeSpec may reduce executor sprawl.
RuntimeArchetypeSpec must not become a hidden author, category router, or bypass around runtimePlan.engineCalls.
```

---

# 4. InfiniVanillaHookBridge / injection bridge — Very later

## Идея

Очень позже можно сделать локальную для Infini систему недостающих Terraria/tModLoader хуков:

```text
global detour/IL bridge
→ per-item guard
→ only if current Item is GeneratedItem
→ only if generated data contains an allowed runtimeHookContract
→ otherwise immediate orig()/return
```

Это не “ИИ патчит Terraria”. Это заранее написанный C# bridge слой, который даёт нескольким редким generated mechanics доступ к хукам, которых нет в обычном tModLoader API.

Рабочее имя:

```text
InfiniVanillaHookBridge
```

## Почему это Very later

Сначала должны быть исчерпаны обычные средства:

- `ModItem`
- `ModProjectile`
- `GlobalItem` / `GlobalProjectile`, если уместно
- `ModPlayer`
- `ModSystem`
- `AltFunctionUse`
- held projectile
- `RuntimeArchetypeSpec`
- vanilla `CloneDefaults` / `AIType` adapters

Bridge нужен только если конкретная generated mechanic не может быть реализована обычными hooks/adapters.

## Необходимый security/architecture contract

LLM никогда не получает право писать raw method names, IL patterns или patch instructions.

LLM может максимум заявить intent:

```json
{
  "runtimeHookContract": {
    "bridge": "player_item_check",
    "mode": "after_vanilla_use",
    "scope": "held_generated_item_only",
    "features": ["paired_sword_secondary", "custom_release_window"]
  }
}
```

Код проверяет:

- `bridge` существует в whitelist;
- `mode` поддержан;
- `features` поддержаны;
- feature safe для MP/client-server split;
- enabled by server/client config;
- current item is generated and has matching generated id;
- old saves with unknown bridge fail closed.

## Fail-closed rules

Если bridge не загрузился, contract неизвестен или проверка не прошла:

```text
feature disabled
status = future_disabled / unsupported
no crash if possible
no vanilla behavior change for other items
```

Для 99.9% items bridge должен делать:

```text
not generated item → orig()
generated item but no matching contract → orig()
matching contract but disabled by config → orig() + debug/warning
```

## Почему это не должно быть текущим решением

Detour/IL хрупкие:

- обновления Terraria/tModLoader ломают signatures/IL patterns;
- другие моды могут patch'ить тот же метод;
- ошибка может ломать client/server sync;
- debug сложнее, чем у обычных `GeneratedItem`/`GeneratedProjectile` executors.

Поэтому порядок такой:

```text
normal hooks first
RuntimeArchetypeSpec / held projectile adapters second
InfiniVanillaHookBridge only after real blocker
IL editing only as last resort
```

## Потенциальные bridge targets

Very later examples:

- `Player.ItemCheck` timing bridge for exact custom release windows;
- paired sword secondary attack if normal `AltFunctionUse` + held projectile is insufficient;
- vanilla melee hitbox internals if generated melee requires more control than `ModItem` hooks provide;
- local vanilla behavior extension for one generated item family.

Не добавлять bridge “на всякий случай”. Каждый bridge требует отдельного risk note, tests, and rollback plan.

---

# 5. Future implementation order

## Wave A — architecture prework

1. Keep current single-pass pipeline stable.
2. Add Applied-vs-Authored reporting for existing fields.
3. Add RuntimeArchetypeSpec as data shell only.
4. Add tests that archetype fields do not override runtimePlan.engineCalls.

## Wave B — multipass foundation

1. Core Author fragment.
2. Code validation after Core Author.
3. One Specialist Author prototype, probably Presentation or Projectile.
4. Deterministic Merger with strict field ownership.
5. Debug trace for passes/retries/dropped fields.

## Wave C — runtime archetype behavior

1. One or two safe archetype adapters.
2. Applied-vs-Authored reports archetype `applied` vs `future_disabled`.
3. No name-based inference.

## Wave D — Very later experimental bridge

1. Design `InfiniVanillaHookBridge` interface and config flags.
2. Add exactly one minimal bridge only if a real blocker exists.
3. Add load/unload/MP tests.
4. Keep IL editing as last resort, not default.

---

# 6. Final hard bans

- No category routing by prompt words.
- No item-specific exception tables.
- No gameplay derived from visual prompt.
- No RuntimeArchetypeSpec overriding authored runtimePlan silently.
- No LLM-authored raw detours/IL/method names.
- No hidden future fields pretending to be applied.
- No creative balance decisions inside validators.
- No deterministic merger acting as another author.
