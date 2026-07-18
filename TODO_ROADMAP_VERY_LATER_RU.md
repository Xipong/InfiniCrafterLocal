# ToDo Roadmap — единый backlog InfiniCrafterLocal

Статус: **единый каноничный ToDo-документ**. Он является единственным project backlog/roadmap для prompt/history follow-up, Skeleton/multipass, applied-vs-authored, оставшихся finite runtime slices, injection bridge, image-pipeline экспериментов и optional reference-guide expansion. Отдельные исторические TODO-черновики и встроенные backlog-копии поглощены сюда. Это не описание текущего runtime: выполненное явно помечается как implemented foundation, а открытые пункты не считаются разрешением на реализацию.

> **APPROVAL GATE:** наличие идеи, плана или implementation order в этом документе **не является разрешением на реализацию**. Не менять код, contracts, prompts, config, runtime, tests или production pipeline по пунктам этого roadmap без отдельного явного согласования с пользователем. По умолчанию разрешены только чтение и обсуждение.

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
| Skeleton / multipass authoring V3.1 | Implemented foundation | Один внешний craft проходит Planner → bounded repairers → Visual → VFX через self-contained authoritative dossiers и deterministic validation/adoption seams. |
| Item-level LLM pool / Responses | Implemented foundation | Round-robin profile lease на item; optional `/responses` state/cache; аварийный switch на следующий profile с cooldown и stateless correctness. |
| Applied vs Authored Validator | Very later, но обязательно | Проверять, дошло ли authored поле до реального C# runtime или честно помечено future/debug-only. |
| Remaining finite runtime slices | Later / explicit approval | RuntimeArchetype data shell уже есть; открыты только конкретные PacketRegistry/multi-beam/held-overlay/feline/sticky/heat-jam/paired executors. |
| InfiniVanillaHookBridge / injection bridge | Very later / experimental | Глобальные detour/IL мосты, но локально gated только на конкретный generated item и только через whitelist contract. |
| Flat-icon authoring + deterministic pixelization A/B | Next visual experiment / explicit approval | Сравнить fake pixel-art prompt с чистым flat-shaded icon prompt при неизменных seed/model/settings и оставить BOX как production downscale. Это существенно уже Skeleton/multipass и прежде всего является prompt A/B. |
| Optional Terraria reference-guide expansion | Documentation-only / very low | Расширять локальный guide до Wiki-like reference только по отдельному запросу; это не runtime feature. |

---

# 1. Skeleton / multipass authoring и кодовая валидация каждого запроса

Этот документ фиксирует дальний ToDo, а не текущее runtime-поведение. Пока нет отдельной реализации, тестов и contract markers, текущий pipeline остаётся single-pass authoring + deterministic Python/C# validation.

> **RADICAL ARCHITECTURE REBUILD — EXPLICIT USER APPROVAL REQUIRED:** Skeleton/multipass нельзя начинать автоматически из-за наличия этого roadmap. Он меняет количество и ownership LLM-pass'ов, fragment schemas, retry budgets, deterministic merge, prompt/history boundaries, debug provenance и failure semantics всего combine pipeline. Не создавать Skeleton fragments/specialists/merger, не менять production authoring topology и не включать multipass flags без отдельного явного согласования с пользователем.

Текущий pipeline уже получил менее радикальные anti-error улучшения и пока должен оставаться на них:

```text
- transient attributed Planner provenance (`role/name/content`) сохраняется только там, где он нужен для bounded author repair, но не является correctness gate downstream presentation stages
- self-contained Name/Genome/Runtime/Visual/VFX dossiers с stage-specific system authority
- latest accepted stage packet = authoritative current truth; Planner transcript не replay'ится
- Visual/VFX имеют один self-contained stage request; malformed/absent history не создаёт standalone author path
exact validation errors returned to the repair model
repair-patch adoption gate
rejected candidates remain feedback-only and never mutate accepted baseline
```

Это движение в сторону более чёткой stage ownership, но **не Skeleton/multipass**: planner history не разрезана на specialist-authored fragments, нет нового Core/Specialist/Merger architecture, и один успешный обычный craft не получает дополнительные author calls. Сначала оценить, достаточно ли сегодняшних fixes на реальной игре/генерационных сериях; архитектурную пересборку делать только если останется доказанный класс ошибок, который ими не закрывается.

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


## Уже реализовано: targeted repair boundary перед C#

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

Retry нужен только когда code-only repair уже начал бы сочинять вместо модели. Current owner: `LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py`; repair принимает только `repairPatch`, возвращает модели exact validator errors, не даёт failed candidates мутировать accepted baseline и fail-closed завершает live craft после исчерпания budget.

## Уже реализовано: armor/accessory soft budgets

Старый открытый пункт выполнен:

- `equipment_stats.py` владеет accessory total-stat budget;
- armor имеет отдельные piece/set-bonus budgets;
- `combine_gameplay.py` применяет или report-only проводит policy;
- `balance_report.py` классифицирует clamps;
- `test_equipment_budget_contract.py` проверяет total accessory и piece-vs-set behavior.

Не создавать второй equipment budget owner под видом выполнения старого ToDo.

## Уже реализовано: single-pass replay harness; открыто только multipass extension

`tools/replay_generation_case.py` уже поддерживает save/list/show/replay, strict recompile/semantic comparison и raw-response rerun без скрытого внешнего LLM call. `LocalGenerator/tests/test_replay_harness.py` проверяет deterministic strict drift/fail-closed boundary.

Для будущего Skeleton остаётся только расширить существующий case format, а не писать новый harness:

```text
core_author_response.json
specialist_responses.json
fragment_validation_reports.json
retry_patches.json
merge_report.json
```

Эти artifacts добавляются лишь после отдельного разрешения на Skeleton/multipass.

---

# 2. Applied vs Authored Validator

Статус: **частично реализованный foundation, unified user-facing report ещё открыт**.

Уже существуют:

- `contracts/field_lifecycle.json` + `tools/contract_parity.py` для source-level stage parity;
- compiler provenance: `authoredFields`, `authoredByFunction`, `fieldSources`, `unsupported`, `futureDisabled`, normalization;
- `runtimePromiseTruth` и machine-resolvable backing refs;
- strict replay, который сохраняет compiler/provenance/validation semantics.

Открытая цель — не дублировать эти owners, а собрать их в один честный per-field report от raw authored value до C# executor/player-visible status.

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

Открытая delivery-часть:

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

Статус: базовый data shell, normalize/compiler support и несколько finite families уже реализованы. Этот раздел больше не является планом «добавить RuntimeArchetypeSpec с нуля»; он фиксирует guardrails и оставшиеся finite slices.

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

---

# 7. ToDo: clean flat icon → deterministic pixelization

## Статус и граница

Это **будущий контролируемый image-pipeline A/B**, а не запрос немедленно менять production prompt.

> **EXPERIMENT GATE — EXPLICIT USER APPROVAL REQUIRED:** не запускать этот A/B автоматически. Основной предполагаемый scope — проверить альтернативную формулировку image prompt на frozen subjects/seeds; это не сопоставимо по архитектурной радикальности со Skeleton/multipass. Любое фактическое изменение production prompt, postprocess, config default или новая платная/ресурсоёмкая генерационная серия всё равно требует отдельного согласования. Запись в ToDo означает только «обсудить позже».

Уже реализовано в текущем WSL source of truth и не является ToDo:

```text
processing profile = master_soft
master canvas = 256
premultiplied RGBA resize = on
production downscale = BOX
NEAREST production branch = removed
```

Открытый вопрос:

```text
Нужно ли просить image model имитировать pixel art на 512×512,
или лучше просить чистый flat-shaded 2D game-item icon без fake pixel grid,
а настоящую пиксельную структуру создавать deterministic postprocess'ом?
```

## Зафиксированное evidence

Вчерашний Windows cache `v0.4.239` содержит восемь item RAW/final pairs:

```text
Grappling Spear       g_45e3683865cd7aba
Ignis Flare-Orb       g_099dafbeb9cbb559
Carpentry Blade       g_4158f55cd9eed57f
Rope-Bound Harpoon    g_500513dfa662c513
Star-Shard Thrower    g_c0638dc21f81071c
Sun-Wreathed Blade    g_d2b7f45b393be45e
Solar Flare Censer    g_8798b82bf1368a13
Sticky Stinger        g_7601a32a5a6414c0
```

Фактический inference profile этого cache:

```text
FLUX.2 Klein 4B Q8
Qwen3-4B-UD-Q5_K_XL text encoder
512x512, 4 steps, CFG 1.0, Euler, flow shift 3
diffusion=ROCm, VAE=Vulkan, TE compute=ROCm, TE params=CPU
LoRA was NOT active in the captured server command/prompt
```

Trace evidence:

- 19 image calls: 8 item, 4 projectile, 4 impact, 3 child;
- 19/19 accepted on attempt 0, no image rejection;
- raw generation median about 3.66 seconds;
- technical score `1.0` did not prove aesthetic quality;
- item candidate score range included `0.535..0.952`;
- final alpha was hard/clean (`partialPct=0`), so the principal comparison was downscale quality, not chroma leakage;
- old Windows config used `INFINI_SPRITE_DOWNSCALE_FILTER=nearest`;
- filter montage showed NEAREST stair-steps/moiré and BOX produced the most stable cross-item result.

Исторический disposable evidence находится рядом со старой Windows sandbox-копией:

```text
D:\Download\InfiniCrafterLocal_v0_4_234_secondary_refit_noise_cleanup\LocalGenerator\cache
D:\Download\InfiniCrafterLocal_v0_4_234_secondary_refit_noise_cleanup\photo_2026-07-12_23-14-00.jpg
```

Не считать D: source of truth. Если corpus нужен для длительного A/B, сначала явно скопировать выбранные RAW/prompts/seeds в отдельный именованный каталог под `image_tests/`.

Дополнительные GPT Image 2 probes сейчас лежат уровнем выше versioned tree:

```text
../ChatGPT Image 13 июл. 2026 г., 19_21_23.png
../ChatGPT Image 13 июл. 2026 г., 19_22_53.png
../ChatGPT Image 13 июл. 2026 г., 19_21_23_64x64_box.png
../ChatGPT Image 13 июл. 2026 г., 19_22_53_64x64_box.png
```

Они показывают другую крайность: detailed high-res illustration после чистого BOX остаётся читаемой, но выглядит как мягкая миниатюра, а не как Terraria-native sprite. Поэтому цель не `photorealistic`, а чистый flat-shaded game icon.

## Гипотеза нового authoring contract

Не просить модель рисовать fake pixel grid, fake dithering и high-res «пиксельные кластеры». Просить:

```text
clean flat-shaded 2D game-item concept/icon
one connected readable silhouette
large coherent color regions
limited material complexity
strong material separation
no microtexture
no dithering
no pixel-grid simulation
no photorealism
no scene/UI/text
fully isolated on the normal chroma-key background
```

Сохранить model-authored:

- предмет и его topology;
- silhouette contract;
- материалы и palette intent;
- orientation/pose;
- role-specific subject (item/projectile/impact/child/field).

Не выводить эти решения из item names или code-owned semantic tables.

## Контролируемый A/B

Сравнивать на одном frozen наборе subjects/seeds:

### A — current fake-pixel authoring

- текущие `pixel art`, `hard edges`, `readable clusters`, `limited palette` clauses;
- current image model/settings;
- current deterministic postprocess.

### B — clean flat icon authoring

- убрать просьбу имитировать pixel grid/clusters/dithering;
- оставить 2D, silhouette, flat shading, palette/material separation;
- те же model, VAE, text encoder, seed, dimensions, steps, CFG, sampler, flow shift;
- тот же chroma/keyer и тот же BOX postprocess.

### B-postprocess variants без повторного image call

Из одного RAW сравнить:

1. current aspect-preserving master-soft + BOX до native 24/32/48;
2. BOX до более низкой logical grid, затем NEAREST upscale только для presentation/export, не как high-res→native production filter;
3. BOX + current palette/posterize + alpha threshold;
4. optional deterministic cluster cleanup только если он не меняет topology/identity.

Не искажать non-square source принудительным resize в квадрат. Сначала alpha bbox crop, затем aspect-preserving fit с прозрачным margin.

## Human gold references

Для понимания верхней границы можно вручную очистить 1–2 GPT Image/FLUX результата и использовать их как visual reference:

- это не production ручной труд на каждый бесконечно generated item;
- это calibration target для автоматического postprocess;
- manual gold не должен молча подменять generated output в runtime cache.

## Acceptance criteria

Решение принимается только по frozen A/B contact sheets и просмотру в реальном масштабе игры.

Проверять отдельно:

- silhouette readability at native canvas;
- connected topology and grip/body continuity;
- role fidelity;
- diagonal stability without stair-step noise;
- absence of rope/petal/crystal moiré;
- material separation after downscale;
- no magenta fringe;
- no sharpen/ringing halo;
- no accidental loss of thin but required parts;
- no extra image-model call/retry caused by the new wording;
- generation latency and rejection rate do not regress.

Human review/contact sheets остаются authority. Technical score/candidate score — только diagnostics, не aesthetic pass/fail.

## Hard bans для эксперимента

- Не возвращать NEAREST как high-res→native production default.
- Не менять model/settings между A и B.
- Не запускать независимый planner для каждой стороны A/B.
- Не добавлять per-image multimodal LLM judge или платный retry без отдельного решения пользователя.
- Не строить semantic classifier по item name/prompt words.
- Не превращать flat-icon prompt в photorealistic/3D/rendered scene prompt.
- Не сохранять D: cache как новый source of truth.

## Минимальный порядок работы

1. Выбрать 8–12 frozen item/role subjects с сохранёнными final prompts и seeds.
2. Сохранить corpus под отдельным `image_tests/<named_run>/`, не в runtime cache.
3. Сгенерировать A/B при полностью фиксированных inference settings.
4. Из каждого RAW выпечь одинаковый deterministic BOX pipeline.
5. Собрать RAW и native-scale contact sheets; enlarged preview держать вторичным.
6. Провести human review по item/role, не только общий «красиво/некрасиво».
7. Если B стабильно выигрывает, заменить общий image prompt suffix и обновить prompt contract tests.
8. После изменения прогнать production batch и проверить в Terraria inventory/held/projectile view.

---

# 8. LLM item conversation V3.1 — implemented foundation

## Статус

**V3 implemented 2026-07-13; superseded by V3.1 on 2026-07-14.** Current source of truth: `docs/LLM_ITEM_CONVERSATION_V3_1.md`.

V3.1 не replay'ит Planner transcript. Downstream stages получают достаточные self-contained dossiers. Один item получает round-robin LLM profile lease; optional Responses state не является correctness boundary; provider failure повторяет текущий dossier на следующем profile и закрепляет его до конца item. Раздел ниже сохраняет доказательства и historical V3 transport baseline, но `retarget_planner_messages()` и четырёхсообщенческая topology удалены.

## Цель и доказанный transport contract

Current target:

```text
provider = Google OpenAI-compatible
model = gemini-3.1-flash-lite
```

Source + local capture-server доказали:

- `stage_chat_message()` валидирует finite `role/name` pair;
- `_llmHistory` принимает только canonical Planner signature;
- `role`, `name`, `content` доходят до final serialized HTTP JSON body;
- compatibility retry без reasoning/response_format сохраняет `messages[]` byte-equivalent по JSON values;
- primary/fallback transport меняет provider/model/reasoning controls, но не stage messages;
- `agentHandoff` находится внутри message content и не теряется transport'ом;
- `_llmHistory` удаляется только после Runtime/VFX stages и не попадает в world persistence;
- serialized localhost capture test подтверждает exact ordered `role/name/content`, embedded `agentHandoff/currentItem` и неизменность `messages[]` при compatibility retry.

Live Flash Lite probes показали:

1. Google endpoint принимает `messages[].name` без HTTP error.
2. Модель **не воспринимает `name` как надёжный participant/stage label**: на запрос скопировать имена `item_author_contract`, `recipe_context`, `item_planner`, `runtime_validator` она вернула content values `alpha`, `beta` вместо metadata names.
3. Та же модель точно прочитала и вернула `agentHandoff.previousSpeaker/currentSpeaker/nextSpeaker`, когда handoff был явно передан в JSON content.

Вывод:

```text
role = Chat Completions authority
name = trace/provider/replay-routing hint, но не correctness boundary
stage-specific system + latest stage packet = фактическая model-visible authority и current truth
agentHandoff = explicit provenance/cause/next-stage metadata внутри content
```

Цель механизма — уменьшить противоречивые инструкции и галлюцинации, а не симулировать роли через metadata.

## Historical V3 topology (superseded; не current contract)

Initial Planner остаётся обычным initial request с `item_author_contract`. Promise Truth retry остаётся continuation той же Planner-задачи. Для всех подходящих post-Planner стадий используется один `retarget_planner_messages()`:

```text
system    <stage-specific contract>
user      recipe_context                 # preserved parent/recipe context
assistant item_planner                   # preserved provenance, not current truth
user      <validator/director context>    # authoritative currentItem/current packet
```

На эту topology переведены:

- Name Repair → `name_repair_contract`;
- legacy Genome Repair → `genome_repair_contract`;
- Runtime Repair → `runtime_repair_contract`;
- Visual Director → `visual_director_contract`;
- VFX Director → `vfx_director_contract`.

Genome/Runtime continuation отправляют delta/current state без повторного full parent packet. Visual/VFX получают current accepted item после validation/repair/compile через собственные bounded packets. Старый Planner JSON явно называется provenance only и не конкурирует по приоритету с latest packet.

## Fallback policy

```text
valid Planner history
→ retargeted attributed continuation

history entirely absent on legacy/non-live data
→ explicit legacy_no_history standalone request

history present but malformed, или live Planner marker без history
→ никакого standalone LLM downgrade
```

Failure semantics:

- Name/Genome/Runtime repair fail closed; craft получает существующий refund/PlannerUnavailable path;
- Visual Director сохраняет existing visual transactionally;
- VFX Director уходит в deterministic recipe fallback;
- failed/invalid VFX continuation использует только свой bounded repair budget и **никогда** не запускает второй standalone LLM prompt.

Canonical replay-stage routing сначала использует finite system `message.name`, а prose heuristic оставлен только для старых replay fixtures без names. Runtime correctness при этом не зависит от `name`.

## Prompt budget

Current canonical gate:

```text
planner payload chars = 24024
allowed chars = 24750
remaining budget = 726
function cards present = 25/25
missing functions = none
```

`PLANNER_PROMPT_LIMIT_CHARS = 24_750` — единственный owner тестового/release-usability бюджета. Linux/Windows release wrappers больше не переопределяют его старым `24000`.

Это **не runtime limit**. `try_llm_plan()` не должен отвергать, обрезать или refund'ить craft только потому, что реальный dynamic parent context превысил `24 750`; такой payload всё равно отправляется модели. Превышение означает, что test/release gate просит отдельно пересмотреть статический контракт или fixtures, а не блокировать генерацию во время игры.

## Что не считать дефектом

- Completion response остаётся обычным `assistant`; `nextSpeaker` — model-visible instruction/provenance, не новый Chat Completions role.
- `_llmHistory` transient и намеренно не сохраняется в recipe/world JSON.
- После Promise Truth retry canonical history может хранить исходный parent context + финальный accepted Planner artifact без всех промежуточных failed turns. Retry trace остаётся diagnostics; downstream stage не должен считать rejected drafts current truth.
- Отсутствие model-visible semantics у optional `name` не является дефектом: correctness задают `role`, stage system, latest packet, validators и adoption gates.
- Explicit legacy/no-history standalone не является silent fallback. Дефектом был бы downgrade из malformed live history или второй standalone prompt после failed continuation; оба случая запрещены tests.
- Отсутствие production reject по `PLANNER_PROMPT_LIMIT_CHARS` не является дефектом: лимит существует для тестов и release-usability контроля, не для runtime craft boundary.

---

# 9. Поглощённые остаточные backlog-разделы

## 9.1. Remaining finite runtime slices

Уже реализовано и не должно повторно появляться как общий ToDo:

- `RuntimeArchetypeSpec`/`RuntimeContractSpec` DTO, normalize, compiler и promise-truth foundation;
- finite boomerang/returning, yoyo, flail, whip, held thrust, channel beam, charge-release, overhead-barrage и sentry paths в их текущих bounded формах;
- charge-release terminal release executor;
- `GeneratedHeldItemDrawLayer` для current held item presentation;
- finite `syncFields` validation для уже известных channel-beam/charge-release/sentry/overhead-barrage state;
- source-level lifecycle parity manifest и tests.

Открыты только отдельные finite slices, каждый требует самостоятельного source/runtime/MP contract и согласования:

1. Full PacketRegistry consumer для произвольного поддержанного `runtimeContract.syncFields`; текущий validator лишь сверяет известные finite field sets.
2. Richer multi-beam variants из finite knobs. Базовый charge-release уже executable и не является открытым пунктом целиком.
3. True generic held-projectile swing overlay, если current item draw + существующие held-family executors реально не покрывают требуемый gameplay/visual case. Не путать с уже существующим `GeneratedHeldItemDrawLayer`.
4. Feline-bounce executor как отдельный finite mechanic; ordinary projectile bounce уже существует и не равен Meowmere-like behavior.
5. Sticky-puddle executor; slime effect сейчас не является полноценным slowing field/puddle runtime.
6. Heat/jam executor с bounded state/sync; слова `heat/overheat/jam` сейчас не создают механику.
7. True paired/offhand dual-wield как finite supported executor; visual/prose twin weapon не считается gameplay implementation.

Overhead barrage уже executable и не возвращается в backlog.

## 9.2. Optional Terraria reference-guide expansion

Это documentation-only backlog, не LocalGenerator/C# feature. Выполнять только если пользователь отдельно попросит превратить `docs/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md` в локальный Wiki-like reference.

Открытый optional scope:

1. Полные melee/ranged/magic/summon/sentry/whip tables с exact stats и acquisition.
2. Exact boss HP по Classic/Expert/Master, включая части/сегменты.
3. Exact boss/event drop rates.
4. Full NPC happiness matrix.
5. Все актуальные Shimmer transmutations.
6. Potion recipes и food tiers.
7. Exact armor set bonuses.
8. Exact accessory effects и crafting trees.
9. Отдельная справочная секция mod-balancing budgets по progression bands.
10. Optional JSON/YAML reference schema для машинной проверки справочных данных.

Не дублировать здесь уже существующий runtime/equipment budget owner и не превращать guide в gameplay authority.

## 9.3. Merge lineage

Полностью поглощены и остаются удалёнными:

```text
docs/TODO_LIST_MULTIPASS_AUTHORING_RU.md
docs/TODO_APPLIED_VS_AUTHORED_VALIDATOR_RU.md
```

Встроенные backlog sections в `docs/runtime_archetype_contract.md` и `docs/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md` заменены ссылкой на этот документ. Они остаются reference/contract docs, а не параллельными ToDo owners.
