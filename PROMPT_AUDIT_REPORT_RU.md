# Аудит prompt → Author/Repair → Visual/VFX → wire/runtime

## 0. Краткий вердикт

Проверен не только текст Author prompt, а вся цепочка model-facing данных:

`parent extraction → canonical/semantics cards → Author prompt/schema → Author response → strict validation → bounded Repair → compiler/finalWireReceipts → Visual Director → VFX Director → generatedParentSummary → world-cache/delivery projection → C# DTO/runtime`.

Главный вывод: runtime-механика уже достаточно хорошо отделена от свободного текста, но финальное человекочитаемое обещание предмета всё ещё берётся почти исключительно из раннего `concept`. Поздние `claims` существуют, но не становятся description/recursive summary. Одновременно code-generated parent `canonical` содержит запрещённые и фактически неверные semantic classifiers.

Поэтому нужны две существенные работы, которые в этом проходе **не реализованы**:

1. заменить heuristic `canonical` на source-backed parent facts без name/category/weapon-family classifier;
2. добавить в тот же Author response позднее поле `realization`, расположенное после executable program и claims, и сделать его источником recursive description/Visual/VFX context.

Мелкие доказанные prompt/contract ошибки исправлены отдельно; gameplay mechanics не менялись.

---

## 1. Методика и доказательная база

### Исходники

Проверены владельцы:

- `LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py`
- `LocalGenerator/infini_local/pipelines/author_item_contract.py`
- `LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py`
- `LocalGenerator/infini_local/pipelines/parent_context_cards.py`
- `LocalGenerator/infini_local/pipelines/parent_context_pipeline.py`
- `LocalGenerator/infini_local/pipelines/item_power_knowledge.py`
- `LocalGenerator/infini_local/core/runtime_authoring/program_schema.py`
- `LocalGenerator/infini_local/core/runtime_authoring/validator.py`
- `LocalGenerator/infini_local/core/runtime_authoring/repair_scope.py`
- `LocalGenerator/infini_local/core/runtime_authoring/compiler.py`
- `LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py`
- `LocalGenerator/infini_local/core/vfx_manifest.py`
- `LocalGenerator/infini_local/pipelines/generated_parent_summary.py`
- `LocalGenerator/infini_local/storage/world_storage.py`
- C# `GeneratedItemData*`, `RuntimeProgramSpec`, `GeneratedItem`, projectile/VFX consumers.

### Реальные артефакты

Использован успешный Exact20:

`/home/xipong/agent-work-main/projects/InfiniCrafterLocal/artifacts/tool-runs/live20-exact20-ea56-final-20260731-234617`

Проверены:

- 20 initial Author request/response;
- 1 scoped Gameplay Repair request/response;
- 20 Visual Director request/response;
- 20 VFX Director request/response;
- 8 bounded VFX Repair;
- generated prompt traces и response field order.

Live/API заново не запускались: текущий working snapshot отличается от старого accepted snapshot, а данный goal не разрешал новый Live20.

---

## 2. Матрица важных полей: что реально их потребляет

| Поле/блок | Реальный consumer | Что происходит сейчас | Вердикт |
|---|---|---|---|
| `balanceCorridor` | Author-модель | Сильно влияет: в Exact20 7 из 10 боевых/частично боевых items взяли exact suggestedDamage, остальные сознательно ниже | Живое и полезное поле; не удалять |
| `concept.literalSynthesis` | Visual Director, generatedParentSummary, dev visual fixture, Repair context | Становится фактическим recursive `fantasy`, хотя написано до mechanics | Полезный intent, но находится у неправильного final consumer |
| `concept.coreMechanic` | Author token continuation, Visual через полный `concept`, Repair context/cache | Runtime не исполняет; может расходиться с program | Сохранить как intent/trace, не считать realization |
| `concept.playerExperience` | Visual через полный `concept`, Repair context/cache | Runtime не исполняет; у `lens_finch_staff` обещает loyal avian minions при straight projectile | Наиболее явный ранний promise leak |
| `concept.parentA/BContribution` | Visual через полный `concept`, Repair context/cache | Не проверяется по source и не исполняется | Intent/diagnostic, не runtime truth |
| `runtimeContract.parentSynthesis` | Последующая Author tokenization и Repair context | Свободные `facts/runtimeRoles`; нет vocabulary/source validation; после delivery удаляется | Полезен только как self-reflection scaffold; название переобещает контрактность |
| `runtimeContract.claims[].backedBy` | validator/Repair scope | Проверяется только существование cited IDs | Структурная provenance есть |
| `runtimeContract.claims[].text/kind` | Author tokenization; теперь также read-only Repair context | Semantic truth текста код не проверяет; block удаляется из delivery | Поздний self-report, но не финальное описание и не доказательство истины |
| `finalWireReceipts` | wire/audit gates | Подтверждает authored field → compiled field/DTO path | Техническая provenance; не description |
| parent `raw.item` | Author/Visual | Primary source facts | Нужен |
| parent `raw.crossModIdentity` | Author | Раньше дублировал `createTile/createWall`, хотя это не identity | Лишний дубль исправлен |
| parent `canonical` | Author, Repair, Visual; косвенно knowledge/balance/result policy | Code-generated semantic classifier, иногда фактически неверный | MAJOR: убрать/заменить source-backed projection |
| Visual `item.prompt` | image generation | Реально создаёт item PNG | Живое поле |
| Visual entity `prompt` | asset plan только при `baked_sprite`; также остаётся context для VFX | Для `reuse_item_icon/runtime_geometry/no_asset` отдельный entity PNG не строится | Условно избыточно; schema сейчас требует его всегда |
| Visual entity `impactPrompt` | Используется только если VFX позднее выбрал impact sprite slot | Visual обязан писать для каждого entity заранее | Неправильный owner/order; MAJOR перенос к выбранному VFX asset request |
| VFX input `description` | VFX-модель | Combine всегда передаёт `""`; hook фактически пуст | Dormant/wrong-stage hook; позже подать `realization.description` осознанно |
| Stage 04 visual defaults | delivery/C# defaults | Stage 05 делает merge, а не replacement; fixed style/offsets/status survive | Не prompt bug; низкоприоритетный cleanup |
| `generatedParentSummary.notableEffects` | Следующая recursive комбинация, C# typed DTO | Собирает только старые movement/controller/events/generatedBuff shapes; на всех 20 Author outputs оказался `[]` при 2–16 calls | MAJOR: текущий runtime summary фактически пуст |

---

## 3. Существенные проблемы — только план, без реализации

### MAJOR-1. `canonical` является запрещённым semantic/name classifier и иногда врёт

#### Доказанные Exact20 примеры

- `GlowingMushroom` → `headNoun=wings`, `class=accessory`, `shapeAnchors=[feathered silhouette, small wings, wings]`, потому что raw substring `wing` находится внутри `gloWING`.
- `JungleSpores` → `ore/material`, потому что `ore` находится внутри `spOREs`.
- `Boomstick` → `headNoun=ammo`, `shapeAnchors=compact ammo bundle`.
- `Minishark` → такой же `ammo` silhouette вместо firearm.
- `HellstoneBar` → stone/block silhouette.

Visual-модель в проверенных примерах смогла проигнорировать ложь благодаря raw names и раннему concept, но это не гарантия: prompt заставляет модель разрешать конфликт между первичкой и выдуманным code-generated fact.

#### Blast radius

- `canonicalize()` создаёт `headNoun/class/shapeAnchors/visualAnchors/hardTags/softTags`.
- `tags_of()` использует substring `if substr in names_blob` и смешивает name tokens с raw mechanics.
- Результат передаётся Author.
- Тот же результат передаётся Repair как parent canonical.
- Тот же результат передаётся Visual как parent facts.
- Tags участвуют в knowledge/result identity и местами в balance helper.
- Для generated parent старый `generatedData.canonical` рекурсивно считается фактом.

#### Как реализовать правильно

1. Не делать точечные hardcase-исключения `glowing/spores`; они маскируют архитектуру.
2. Разделить parent packet на:
   - `sourceIdentity`: sourceMod/fullName/internalName/displayName;
   - `sourceRuntimeFacts`: exact numeric/bool fields, projectile/controller snapshot, placement facts;
   - `generatedRealization`: только для уже generated parent;
   - `visualSourceFacts`: существующие source assets/dimensions, но не guessed weapon shape.
3. Удалить model-facing `class/headNoun/shapeAnchors` для vanilla/modded parent, если они не пришли из авторитетного source metadata.
4. Balance строить по numeric progression facts, а не по name token taxonomy.
5. Result identity/visual design оставлять модели; код проверяет wire и literal presence, но не выбирает noun/family.
6. Добавить RED fixtures минимум для пяти примеров выше и проверять отсутствие derived semantic class/shape.

Это не Normalization и не Alias Lowering. Нынешний classifier делает semantic invention, поэтому нужен отдельный архитектурный проход.

### MAJOR-2. Ранний `concept` является единственным реальным recursive promise

`generatedParentSummary.fantasy` берётся из `concept.literalSynthesis`. `notableEffects` на всех 20 случаях пуст, хотя items содержали 2–16 explicit calls.

Следовательно, следующая генерация видит ранний fantasy, а не реализованную механику. Это и есть корень promise mismatch.

#### Реальный `lens_finch_staff`

В одном Author response:

1. `coreMechanic`: straight summon projectile — относительно честно;
2. `playerExperience`: loyal avian minions — уже обещает отсутствующий controller;
3. late claim: straight-moving projectile — снова честно;
4. delivery/recursive summary берёт ранний `literalSynthesis`, а late claim удаляется.

Claims тоже не абсолютная semantic truth: `Glowshroom Elixir` claim говорил «light while held in inventory or equipment slots», хотя backing был `add_hold_light`. `backedBy` доказывает ссылку на call ID, а не значение английского предложения.

### MAJOR-3. Добавить поздний `realization` в тот же Author response

Не нужен второй LLM и не нужна отдельная verifier stage.

Рекомендуемый model-facing root order:

```text
name
category
concept
runtimeProgram
runtimeContract   # parent synthesis + claims, уже видит mechanics
realization       # свободный final self-report, видит mechanics и claims
```

Предлагаемая минимальная форма:

```json
{
  "realization": {
    "description": "Краткое свободное описание только реализованного поведения",
    "playerExperience": "Что игрок реально делает/видит",
    "backedByClaims": ["claim_id"],
    "trace": {
      "kept": ["..."],
      "changed": ["..."],
      "dropped": ["..."],
      "added": ["..."]
    }
  }
}
```

Ограничения:

- это human-visible promise/diagnostic, но не executable authority;
- runtime authority остаётся `runtimeProgram`/compiled DTO;
- `backedByClaims` проверяется как ID reference;
- свободный текст не объявлять машинно доказанным;
- никаких tooltip fields/rendering: тултипы остаются запрещены.

#### Consumers после внедрения

- `generatedParentSummary.fantasy` ← `realization.description`;
- recursive parent context ← realization + структурные runtime facts;
- Visual получает projected physical intent + realization, а не весь ранний concept;
- VFX получает `realization.description` вместе с immutable runtime surface;
- authoring/world cache может сохранять concept+realization для trace;
- network DTO не обязан возить оба свободных блока: typed `GeneratedParentSummary` уже является компактным consumer.

### MAJOR-4. Repair должен обновлять realization после accepted gameplay patch

Реальный единственный Gameplay Repair в Exact20:

- поменял inputs двух bindings;
- вернул `claimsUpsert=[]` и `metadataPatch={}`;
- до этой правки вообще не видел accepted claims;
- prose остался корректным только случайно.

В этом аудите claims уже добавлены в `acceptedItemContext` как read-only MINOR fix. Этого недостаточно для нового realization.

Нужно:

1. передавать Repair текущие concept, claims и realization;
2. заставлять Repair возвращать replacement realization последним;
3. при любой принятой mutation entities/bindings/calls/claims требовать realization replacement;
4. тестировать param change, binding input swap, node deletion, rejected extra rewrite;
5. явно решить atomicity risk: deterministic scope filter может принять полезную часть patch и отбросить лишнюю, а model prose мог описать и отброшенную часть.

Рекомендуемый безопасный вариант для обсуждения:

- сохранить current partial-salvage Repair;
- принимать replacement realization только вместе с accepted claim IDs;
- после filter/apply прогнать structural reference check;
- сохранять filter audit рядом с realization trace;
- если Repair попытался описать out-of-scope node/claim, считать весь Repair неуспешным, а не делать deterministic semantic rewrite.

Semantic validation текста всё равно невозможна без второго LLM/human review; это следует честно отразить в Live20 статусах.

### MAJOR-5. Visual handoff получает полный ранний `concept`

`visual_generation_pipeline.py` передаёт:

```python
{"name": ..., "concept": copy.deepcopy(data.get("concept") or {})}
```

В результате Visual видит `playerExperience/coreMechanic`, даже если late runtime реализовал другое. После realization следует передавать отдельно:

- literal physical composition/visual identity intent;
- accepted runtime entity card;
- final realization;
- accepted same-physical-object project mapping.

Не нужно передавать свободный ранний gameplay promise как финальную истину.

### MAJOR-6. Visual entity schema требует тексты до появления реального consumer

Сейчас каждый entity обязан иметь `prompt`, `silhouette`, `visualIdentity`, `impactPrompt`, даже когда:

- `reuse_item_icon` использует exact item PNG;
- `runtime_geometry` не генерирует entity PNG;
- `no_asset` не рисует entity body;
- impact sprite может вообще не быть выбран поздним VFX Director.

Предлагаемый перенос:

- для `baked_sprite` требовать отдельный visual project (`prompt/silhouette/visualIdentity`);
- для `reuse_item_icon` ссылаться на item visual project и не создавать фиктивный второй project;
- для `runtime_geometry/no_asset` хранить только нужные runtime presentation параметры;
- `impactPrompt` создавать в VFX/asset request только для реально выбранного impact sprite slot.

Это сохраняет invariant: один физический объект → один visual project; отдельный объект → отдельный project.

### MAJOR-7. Exported JSON schema уничтожает field order

`tools/export_contract_schemas.py` использует `json.dumps(..., sort_keys=True)`. Runtime provider schema строится прямо из Python dict и теперь имеет правильный order, но опубликованный `contracts/schemas/author_item_response.schema.json` сортирует properties.

Если внешний consumer использует JSON-файл как model schema, `runtimeContract` снова окажется до `runtimeProgram`.

Варианты:

- canonical serializer, который сортирует обычные metadata keys, но сохраняет `properties`/`required` model order;
- отдельный `x-infini-model-order` и gate, который восстанавливает order при transport;
- не использовать exported artifact как model-facing schema и явно это зафиксировать.

Нельзя просто выключить `sort_keys` без review: это переформатирует весь generated-contract набор.

### MAJOR-8. VFX `description` — пустой dormant hook

Combine вызывает VFX с `description=""`. Поле есть в prompt, но сегодня не несёт сигнала. После реализации realization нужно осознанно передавать туда `realization.description`; до этого нельзя считать, что VFX видит финальное описание.

---

## 4. Мелкие правки, внесённые сейчас

### MINOR-1. Исправлен model-facing field order

Было противоречие:

- shape card: `concept → runtimeContract → runtimeProgram`;
- фактический payload: `concept → runtimeProgram → runtimeContract`;
- response schema properties: снова Contract перед Program.

В старом Exact20 4/20 responses реально вывели `runtimeContract` перед `runtimeProgram`, 16/20 — наоборот.

Теперь единый source/provider order:

`name → category → concept → runtimeProgram → runtimeContract`.

Это не добавляет realization, но гарантирует, что claims токенизируются после mechanics.

### MINOR-2. Удалён дублированный ранний `balanceCorridor`

Один и тот же recipe-specific corridor находился:

- внутри `runtimeCapabilityContract` до static schema/self-check;
- повторно в конце payload.

Реальный старый common prefix обрывался на 77 605 символах внутри раннего corridor. После удаления ранней копии synthetic pair имеет:

- first payload: 82 432 chars;
- second payload: 82 411 chars;
- common prefix: 81 361 chars.

Единственный corridor оставлен в хвосте. Сам corridor не удалён: Exact20 доказал его сильное влияние на authored stats.

### MINOR-3. Уточнена граница semantic inference

Старый текст можно было прочитать как «Author не должен использовать parent facts». Теперь явно сказано:

- deterministic code не выводит gameplay из names/tooltips/tags/category/prose;
- Author может читать source-backed parent facts, но должен материализовать выбор в explicit runtimeProgram.

### MINOR-4. Исправлен naming collision

Prompt-only invariant `primaryEntitySelection` переименован в `primaryEntityOwnership`.

Repair transaction/wire field `primaryEntitySelection` не менялся. Раньше одинаковое имя обозначало две разные вещи.

### MINOR-5. Удалён лишний placement fact из `crossModIdentity`

`createTile/createWall` больше не дублируются в `raw.crossModIdentity`. Exact raw item, vanilla flags и explicit placement semantics сохранены.

Это только первая безопасная дедупликация. Полный parent-card weighting требует отдельного MAJOR review.

### MINOR-6. Удалена устаревшая инструкция

Placeable semantics ссылалась на несуществующие output fields `mergeLogic/sourceReading`. Теперь ссылка идёт на фактические `concept` и `runtimeProgram`.

### MINOR-7. Accepted claims добавлены в Repair dossier

`acceptedItemContext.claims` теперь передаётся read-only. Repair не получает новых permissions, но видит позднее обещание, которое может затронуть repair.

Generated targeted Repair audit обновлён тем же dependency-free owner mode (`python -S`).

### MINOR-8. Visual prompt запрещает opaque background

В реальном `astral_minishark` Visual response item prompt содержал `solid black background`, несмотря на inventory sprite contract. Добавлено явное правило:

- item и baked entity prompt требуют transparent background;
- нельзя просить solid/black/white/opaque background.

Image-generation параметры и постпроцесс не менялись.

---

## 5. Что намеренно не менялось

- `balanceCorridor` не удалялся и не превращался в deterministic rebalance.
- Не добавлялся fallback/second LLM/verifier/semantic router.
- Не добавлялись keyword hardcases для `GlowingMushroom`/`JungleSpores`.
- Не добавлялся `realization`: это cross-stage schema/Repair/delivery change.
- Не менялась Visual identity/project topology до отдельного решения.
- Не добавлялись и не отображались tooltips.
- Не менялся C# gameplay/runtime executor.
- Не запускались Live20, tML, C# build/package или commit.

---

## 6. Verification внесённых MINOR

Проверено на текущем working tree:

- focused prompt/runtime/parent tests: `78 passed`;
- полный Python suite: `194 passed`;
- exported contract schemas: `10 current`;
- planner prompt usability: GREEN;
  - 51/51 capabilities;
  - no missing/extra;
  - no weapon macro/family router;
  - 82 613 chars при лимите 96 000;
- targeted Repair audit: GREEN;
  - Author 82 419 chars;
  - policy 39/39;
  - frozen merge GREEN;
  - frozen callsites 7/7;
- project hygiene: GREEN;
- C# static runtime contract scanner: GREEN;
- `git diff --check`: GREEN.

Working tree до аудита уже содержал большой незакоммиченный refactor; этот документ не объявляет весь snapshot заново independently audited или Live GREEN.

---

## 7. Рекомендуемый порядок следующих работ

1. **Canonical/source-facts cleanup** — убрать semantic classifier до новых Live-оценок, иначе Visual/Author получают противоречивый вход.
2. **Realization schema + same-response ordering** — concept → program → claims → realization.
3. **Repair realization policy** — полный accepted context, re-emission, partial-filter atomicity tests.
4. **Recursive summary replacement** — realization + структурные runtime facts вместо раннего literalSynthesis.
5. **Visual/VFX handoff cleanup** — projected physical intent, realization, same-object project mapping, impact prompt ownership.
6. **Schema export order gate**.
7. После двух чистых независимых аудитов неизменного snapshot — только по отдельной команде новый Exact20/human visual review.
