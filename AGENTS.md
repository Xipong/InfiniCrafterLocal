# AGENTS.md — InfiniCrafterLocal

Правила архитектуры и изменений; номер релиза и статус локальных обновлений — в [README.md](README.md).

## Быстрый вход по задаче

Если файл/метод уже известен, открой его и прямых callers. Если неизвестен — выбери один маршрут в [карте задач и исходников](docs/development/CODE_MAP_RU.md#fast-start); это единственная навигационная карта. Scoped инструкции: [Python](LocalGenerator/infini_local/AGENTS.md) и [C#](ModSources/InfiniCrafterLocal/AGENTS.md). Не перечитывай инструкции, карту и generated catalogs перед каждой правкой. Правила runtime ниже применяются к затронутым генерационным/игровым контрактам, а не автоматически к каждому файлу Python, CSS или JS.

## Масштаб проверки

Применяй правила и проверки только к затронутому владельцу и обещанному результату, а не как общий чеклист перед началом работы. Сделай рабочую версию, затем проверь реальные инварианты; не повторяй чтение и проверки неизменённого без новой причины. Тестовый хардкод оформления или реализации можно менять вместе с новым решением, сохраняя проверку существенного поведения. Пустой `verify --plan` — не подтверждение результата.

## Приоритеты проекта

**Архитектура обслуживает создание предметов, а не наоборот.** Три равноправные цели:

1. **Простота для LLM:** минимум необоснованных обязательных решений, повторений и ограничений. Model-facing имена capabilities/параметров должны быть краткими и однозначными: не повторять в них уже известный контекст, а единицы и ограничения объяснять в registry/docs. Важна вероятность получить правильный результат, а не минимальный JSON любой ценой.
2. **Поддерживаемость и читаемость:** понятный код, единый источник истины, минимум ненужных слоёв и дублирования.
3. **Максимум игровых примитивов:** как можно больше независимых, комбинируемых и **реально исполняемых** возможностей. Новая механика ценнее возможности, существующей лишь в описании или тултипе; не заменять исполнение текстовыми обещаниями.

**Ваншотный Author, не пошаговый tool-calling harness.** Модель сразу выдаёт всю композицию `runtimeProgram` в одном ответе, без промежуточных вызовов инструментов и обратной связи валидатора по каждому выбору. Условный Repair происходит уже после ответа и не заменяет успешную первую генерацию. Поэтому при упрощении model-facing API учитывать **число одновременно необходимых правил и исключений**, а не только длину JSON: сокращение повторов полезно лишь тогда, когда не делает форму сложнее для правильного ваншотного построения. Одинаковые явные правила иногда надёжнее многочисленных условных пропусков; это критерий оценки, не запрет точных aliases/omissions и не требование менять существующий контракт.

Сложность оправдана, когда она даёт реальную игровую возможность, устраняет существенную ошибку или заметно облегчает поддержку. Перед изменением оценить не только корректность кода, но и нагрузку на LLM, полезность результата и цену сопровождения. **Не усложнять ради формальной чистоты и не упрощать ради самого упрощения.** Подробнее: [issue #28](https://github.com/Xipong/InfiniCrafterLocal/issues/28).

## Архитектурный инвариант

Gameplay Author непосредственно составляет bounded `runtimeProgram` из низкоуровневых capabilities. Код не классифицирует предмет по оружейному архетипу и не достраивает композицию поведения. Lowering разрешён только для семантически без потерь технического дублирования движка. Baseline успешного craft — Gameplay Author, Visual Director, VFX Director; Repair условен для каждой стадии. Repair всегда leaf-local и frozen-first: передавай только invalid fragments, exact missing dependencies и валидный read-only context; применяй только `fieldPermissions`/create-policy, а любые попытки изменить уже валидные значения игнорируй с audit вместо отмены полезного исправления.

## Четыре класса преобразований

Перед добавлением любого compiler/runtime преобразования явно отнеси его ровно к одному классу:

1. **Fallback — запрещён.** Владелец-модель не передал поле, передал невалидное значение или не выбрал вариант, а код молча выбирает содержательную механику, target, текст, цвет, visual/VFX mode либо prompt и продолжает как GREEN. Пустой `allowedTuples` не раскрывается в декартово произведение; invalid enum не заменяется «разумным» enum; backend не дописывает отсутствующий authored prompt.
2. **Fix — только осознанный и доказуемый.** Код восстанавливает единственное технически возможное поле из уже полного model-authored описания и engine invariant, не выбирая между несколькими содержательными вариантами. Fix обязан иметь узкую предпосылку, audit/receipt с причиной `fix:*`, negative path и regression. Он не имеет права создавать отсутствующий дизайн целиком. Разрешённый пример: для `item_body` всегда нужен отдельный сгенерированный inventory PNG, поэтому его `assetMode` не является творческим выбором модели и технически обязан быть `baked_sprite`. Если Visual Director передал непустые `prompt`, `silhouette` и `visualIdentity`, но пропустил только `assetMode`, engine может явно дописать `baked_sprite`. Если отсутствует хотя бы одно из описаний внешности — Visual Repair/RED. Другие `assetMode` допустимы только для non-item entities.
3. **Normalization — разрешена только по объявленному wire-контракту.** Case/whitespace canonicalization, bounded clamp, transport truncation/dedupe и аналогичная форма допустимы там, где варианты контрактно эквивалентны или projection явно lossy. Normalization не должна выбирать механику или менять свободный authored смысл; иначе это Fallback. Clamp/trim должен оставаться видимым в receipt/audit, если меняет authoritative wire.
4. **Alias Lowering — разрешён.** Модель явно выбирает зарегистрированный alias, а canonical lowerer детерминированно и без потерь раскрывает его в низкоуровневый runtime wire. Один alias всегда даёт одну и ту же проекцию; запрещены prose/name/category routing, contextual guesses и defaults. Общие params можно сворачивать только при literal identity по установленному repetition threshold.

Явно согласованное исключение для полного Author: только optional-параметры с объявленными в `ParamSpec` одинаковыми `default` и `neutral` могут отсутствовать как точный эквивалент этой нейтрали. Это новая семантика контракта, не исправление ранее невалидного ответа. Compiler материализует нейтраль лишь после проверки всей композиции и пишет отдельный receipt отсутствия; неверное присутствующее значение, недостающая зависимость и пустой обязательный эффект остаются RED. Ни DamageClass, ни категория не выбирают значение. При Repair пропуск означает «не менять», а принятую пустоту нельзя заполнять вне exact scope. Новые разрешения требуют проверки совместных комбинаций и C#-потребителей; `neutral` без `default` сам по себе ничего не разрешает.

Если класс нельзя назвать однозначно — не менять production code до отдельного решения. `Fix`, `Normalization` и `Alias Lowering` не переименовывают в fallback и наоборот: для каждого действуют собственные owner, audit и тесты.

## Перед изменением runtime

Найди затронутый owner по известному symbol/caller либо [карте](docs/development/CODE_MAP_RU.md#fast-start) и читай только соответствующие контракт, consumer и документы. Для **новой capability** используй [инструкцию по добавлению](docs/development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) и полный vertical slice ниже; локальная правка не требует предварительного чтения всего runtime-каталога.

Owners: authored shape — `program_schema.py`; mechanical/event facts — `capability_registry.py`; lossless projections/receipts — `technical_lowering.py`; model-facing prose — `author_item_contract.py`. Для новой capability нельзя создавать facade/shadow contract или вручную добавлять её лишь в один слой.

## Запрещено

- whole-weapon macros и family/profile routers;
- `AttackSpec`, `weaponFamily`, `runtimeFamily` как gameplay authority;
- выбор movement/attachment/delivery/input/lifecycle из name/category/prose;
- параллельная legacy schema, migration/cache importer, hidden repair API;
- facade/shadow constants и event-name repair routers рядом с canonical owners;
- обязательный classifier/judge/critic LLM-pass;
- arbitrary VM, generated C#, reflection dispatch;
- placeholder PNG вместо обязательного asset.

## Обязательный vertical slice

Для новой runtime capability: `registry -> provider schema/prompt -> validator -> compiler receipts -> strict wire -> C# DTO -> C# executor -> tests -> docs`.

Рабочие команды из корня:

```bash
# Для затронутого runtime: точный вход вместо обхода дерева; --path тоже поддерживается.
python tools/agentctl.py context --task "описание задачи" --area runtime
# Известный файл или область: проверка без чтения Git diff.
python tools/agentctl.py verify --path LocalGenerator/infini_local/core/runtime_authoring/validator.py
python tools/agentctl.py verify --area transport
# После правок: owner-area проверки. --base включает уже закоммиченный diff ветки.
python tools/agentctl.py verify --changed --base origin/main --plan
python tools/agentctl.py verify --changed --base origin/main
# После изменения runtime contracts: существующие generators, затем offline handbook.
python tools/validate_release.py --refresh runtime
# Полная приёмка интегрированного commit; тот же набор используют CI и release wrappers.
python tools/validate_release.py
```

Для stacked PR укажи его реальную base branch вместо `origin/main`. Неизвестный production-путь после правки требует более широкой проверки; пустая выборка не считается PASS. Iteration не объявляет `releaseReady`. Команды, группы CI и refresh — один `.agent/manifest.json`; owner-area выбор — `.agent/impact_rules.json`. Подробнее: [TESTING](docs/development/TESTING_RU.md).

Для затронутого C# при доступной среде выполнить соответствующий build; игровой smoke — только при отдельном разрешении на запуск игры. Отсутствие среды записывается как `notRun`, а не как успех. Изменение только браузерной Studio не требует C# build или запуска Terraria.
