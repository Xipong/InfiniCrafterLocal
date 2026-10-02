# Technical lowering — классификация и proof boundary

[Generated boundary/manifest](../lowery.md) · [Machine receipts audit](../TECHNICAL_LOWERING_AUDIT_RU.md) · [Executable owner](../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py)

<a id="transformations"></a>
## Четыре разных класса

Классификация обязательна **до** изменения compiler/runtime; полные организационные определения и пример `item_body.assetMode` — [AGENTS](../AGENTS.md#четыре-класса-преобразований), не второй shadow policy.

| Класс | Условие и граница |
|---|---|
| **Fallback — запрещён** | Missing/invalid model choice → код сам выбирает содержательную механику, target, текст/цвет/mode/prompt и объявляет GREEN. Empty allowedTuples не Cartesian product; invalid enum не «разумный» enum; отсутствующий authored prompt не дописывается |
| **Fix — узкий и доказуемый** | Только единственное технически возможное поле из **уже полного** authored описания + engine invariant. Нужны narrow precondition, `fix:*` audit/receipt, negative path и regression; отсутствующий дизайн не создаётся |
| **Normalization — объявленная** | Wire-контракт считает формы эквивалентными либо явно объявляет lossy projection. Case/whitespace/clamp/truncate/dedupe не выбирают механику и не меняют свободный authored смысл; изменение authoritative wire видно в receipt/audit |
| **Alias Lowering — lossless** | Explicit registered alias → одна детерминированная без потерь low-level projection. Никаких prose/name/category routing, contextual guesses или defaults |

Узкий Fix item-body baked_sprite и его обязательные appearance preconditions определены в [AGENTS](../AGENTS.md#четыре-класса-преобразований): missing appearance → Repair/RED, не общий visual default.

Полный Author имеет отдельную [объявленную omission semantics](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract), а Repair omission означает no change. Эти классы нельзя переименовывать друг в друга; если классификация неоднозначна, production change требует отдельного решения.

<a id="projections"></a>
## Mandatory projection против compression

Mandatory technical projection сериализует уже authored identity/value: capability name → opcode, kind → visual role, primary id + exact target equality → wire role, один value → обязательные DTO fields. Порог повторений тут неприменим; новых choices нет.

Authoring compression сворачивает только **literal identical** low-level value при `count >= MIN_EXACT_REPETITION_COMPRESSION` (сейчас 5), с `addsDesignChoice=false`. Primary role/owner projection compression не является. Lowering скрывает неудобство API, не сжимает пространство дизайна.

Запрещены family/category/name/prose → movement/attachment/delivery/kind/input/lifecycle/targeting/topology, multi-choice prefix, whole-weapon executor fallback, broad undeclared output paths и unknown → semantic default. Нынешний gameplay surface не даёт Author-visible semantic aliases; retained technical/config/UI/VFX aliases перечисляет generated Lowery.

<a id="receipts"></a>
## Обязательное доказательство

Lowerer объявляет authored inputs, finite outputs, equivalence, preserved decisions и `addsDesignChoice=false`. Global receipt: `lowererId/authoredPaths/finalPath`; capability receipt: `callId/fn/finalPath`. `audit_compiler_receipts` проверяет происхождение и exact output; mutation gate отклоняет undeclared input/output. Explicit zero сохраняет provenance. Omission status и standalone/source-aware proof — [neutral receipt rules](DECLARED_NEUTRAL_OMISSIONS_RU.md#receipts).
