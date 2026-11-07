# Исходный контекст родителей: анализ, проекция и транспорт

Интеграция source analysis сохраняет контракт ammo main/#332: live inventory и fallback observations остаются отдельными от статических native source facts. Root использует Player, fingerprint — независимое player-free наблюдение. Source-профиль не означает исполненный выстрел.

## Анализ и проекция

Native IL/CFG collector сохраняет guards, неизвестные эффекты, ограниченные helper spawns и inline effects. Sparse locals не меняют условия statements. Подтверждённые identity predicates исключают лишь доказанно недостижимые source-ветви. Неизвестные значения, unsupported instructions, escapes и hooks сохраняют неопределённость; read-only observation не становится gameplay router.

Conditional arithmetic shot variants содержат provenance, исходную вероятность и зависимости значений, но не обещают final-shot identity/damage/speed после последующих native writes/hooks. Сохранённый byref до инициализации запрещает `inputBinding`; для address-exposed spawn-local значение чтения остаётся unknown, а `sourceDefinition` сохраняет только выражения direct stores, не подставляемые вместо текущего значения. Pinned ILSpy 8.2.0.7535 поставляется с модом. Readable C# records проходят source-identity/mapping checks, включая совпадение IL, local signature, InitLocals, MaxStack и EH descriptors с reflection; при неполноте используется исходный IL view и diagnostic. Из fingerprints исключаются только распознанные `attackReference.nativeCSharpSource` и certified lifecycle display envelopes; `mechanicsSource` и `nativeItemDispatchReference` остаются частью fingerprint.

Author получает исходники с guards, alias scopes, child-profile links и unknowns. Reversible shared-source/identifier/diagnostic notation сокращает повторения; literal tooltips и generated parents не переинтерпретируются. Inventory/fallback projectile profiles проходят тот же source-selection путь, что direct/effective/replacement profiles. Main source-projection cache сохраняет complete-method isolation, immutable values и cancellation перед warm hit.

### Практическое представление механики

Для native capture с `mechanicsSource` Author получает `packet.raw.mechanics`. Это явно приблизительная read-only проекция, а не сертифицированная полная спецификация оружия. AST-проекция предполагает стабильность captured `Projectile.type/aiStyle` через opaque calls; строгий исходный граф остаётся отдельно. Запись identity-поля, передача его адреса, неподтверждённый receiver, exception/nonlocal control scopes запрещают pruning. Известные identity-if и literal identity-switch ветви сокращаются без изменения порядка побочных эффектов; switch сохраняет область `break`. Удаляются только доказуемо недостижимые соседние statements после безусловного `return`/`throw`.

Независимые окна исходного dispatcher нельзя считать недостижимыми лишь потому, что между ними не захвачен код. В таком случае optional identity selection отказывается с диагностикой и сохраняет unspecialized source. Отказ доказательства receiver binding возвращает unbound, а не отменяет сбор исходников helper.

Если полный readable dispatcher превышает существующий лимит представления, та же approximate AST-проекция применяется к уже выделенным замкнутым conditional regions. Внешние входные guards и предупреждение о неизвестном enclosing control flow сохраняются. Это не обрезка текста по размеру и не превращение partial region в полный метод. Несвязанные exception scopes за пределами региона не блокируют его; store/address identity-поля по-прежнему запрещает pruning, кроме точно сопоставленного доступа в заведомо чужой identity-ветви без входящего перехода. Предшествующая безусловная запись или запись под неизвестным условием остаётся отказом. Исключение вызовов связано с точными IL offsets и исходной identity метода; неоднозначные surviving calls не исключаются.

Для полного допустимого метода native producer может сузить child-кандидаты конкретного `NewProjectile`: аргумент `Type` должен быть integer literal либо связанным local, у которого initializer и все surviving записи — integer literals. Берётся консервативное объединение всех таких значений, включая перезаписанные; порядок присваиваний и условия не вычисляются. Параметры, неизвестные RHS, mutation/ref/address escapes, nested writes и partial regions не дают такого доказательства. Consumer удаляет child только при исключении его типа каждым исходным вызовом с точным method/hash/module/IL-offset; ambiguous или отсутствующие связи сохраняют профиль. Поддерево, на которое указывает exact `sameAs`, также сохраняется. Это normalization приблизительного source view, не изменение runtime и не гарантия фактического spawn.

`source` содержит readable методы; `sourceSlices` сохраняет связанные symbolic caller programs, когда readable caller отсутствует. Helper без аргументов/guards вызывающего кода не заменяет collision или dispatch. В slices сохраняются dependencies, predicates, symbols и порядок. `mechanicsSourceIndex` указывает на запись `source` после раскрытия exact shared values; неизвестная ссылка остаётся explicit unresolved. Position integration сохраняется вместе с исключениями и hooks: ранний `return` может означать отсутствие обычного перемещения, поэтому эта часть не считается draw boilerplate.

Одинаковые projectile defaults объединяются только по точному равенству. `captures` сохраняет все пути/роли/slots и соответствующий `itemShootSpeed`: это наблюдение исходного item/ammo, не итоговая скорость выстрела. Exact aliases переносят наблюдение только по существующей цепочке; missing/cyclic paths не заполняются догадкой. Repeated site diagnostics группируются с сохранением всех IL offsets; остальные source gaps не обрезаются по числу записей. Неизвестные выражения, вызовы, отсутствующие child profiles и ограничения extraction не превращаются в утверждение об отсутствии механики.

## Повторное использование анализа

`NativeCSharpModule` владеет одним PE snapshot, resolver, dependency readers и type system ILSpy. Документы используют общую модульную подготовку, но отдельные decompiler transforms и cancellation. Перед каждым получением документа, включая cache hit, сохраняется полная проверка PE/reflection. Очистка освобождает readers под тем же lock, которым защищены работающие потребители.

Document cache сохраняет до 8 документов, 650000 AST nodes и 3000000 символов суммарно; admission одного метода ограничен 200000 nodes и 750000 символов. При вытеснении сначала выбирается старый дешёвый документ, чтобы короткий helper не заставлял повторно декомпилировать большой dispatcher. Подсчёт размера и code-only представления не клонируют AST для назначения coordinates; карта whole-method locations строится лениво и повторно используется только для неизменённого исходного дерева. Индекс концов conditional instructions живёт вместе с соответствующим immutable IL decode и не удерживает его после сброса source cache.

Для mechanics и lifecycle индекс `call/callvirt` строится один раз на проекцию. Поиск сохраняет точные token/type/name и реальные полуинтервалы IL annotations; пропуски между ними не становятся допустимыми offsets. Lifecycle дополнительно проверяет native `Projectile`, `MethodInfo` и число параметров. Неоднозначность не превращается в доказанное исключение вызова.

Projectile program cache также использует LRU: до 256 identities и 16 Mi символов сериализованного JSON. При давлении вытесняются только необходимые старые entries. Завершившийся после invalidation или eviction старый build не возвращается в кеш; живой потребитель может повторить отменённый build в своём контексте. Готовый source хранится как immutable `JsonElement`; strict reference, mechanics и spawn consumers получают независимые lazy JSON wrappers без повторного разбора полного текста. Изменение одной проекции не меняет остальные или кеш.

Эти пределы ограничивают сохраняемые документы и программы, а не transient allocations всего craft. Для затрат отдельно измеряются cold request, warm hits и source-cache-reset через `PrepareDeferred → CompleteAnalysis`; накопленные managed allocations и длительность headless-прогона не равны peak RAM и игровому frame time.

### Пакет source-проекций при сборке

`Data/native-source-pack.zip` переносит повторяемую декомпиляцию native-методов в сборку выпуска. Он содержит точные результаты существующих source builders для методов с IL от 2048 байтов. Генератор перечисляет все положительные `ProjectileID` с реальными `SetDefaults` и все положительные `ItemID` для item dispatch. Пар предметов, имён оружия и предустановок механики в ключах нет. Обычный craft не запускает генератор каталога и не прогревает анализ скрытым предварительным запросом.

Пакет хранит strict source вместе с optional identity specialization, mechanics source и их отдельными отказами. Lifecycle-запись включает также упорядоченные ссылки на дочерние снаряды. Ключ одного projectile method включает native method identity, captured type/style, receiver binding, полный ordered-distinct список identity windows и точное множество используемых IL offsets. `graphPaths` принадлежат текущему графу: они заполняются при чтении, в прежней позиции JSON-свойства. Пакет не хранит готовый parent payload, состояние игрока, inventory, результаты mod hooks или выбранную моделью механику.

Перед каждым hit выполняется прежняя проверка live PE/reflection: MVID, metadata, IL, local signature, InitLocals, MaxStack и EH. Manifest дополнительно фиксирует SHA native PE, pinned ILSpy, настройки, fingerprint исходников проекции и фактические пары «запрошенная dependency → разрешённый PE» с SHA. Архив и отдельные записи ограничены по размеру; читается только нужная запись, проверяются её размер и SHA, а отмена проверяется до публикации результата. Сброс source cache освобождает reader пакета вместе с native module snapshot.

Отсутствующий, устаревший, повреждённый или несовместимый пакет, другая identity/style либо другой вход проекции дают обычный cache miss: исполняется полный прежний анализ. В user payload не добавляется искусственный отказ из-за отсутствия ускоряющего ресурса. Генератор останавливается при конфликтующих результатах одного ключа и не публикует частично записанный архив. Timeout, отмена и недетерминированные ошибки разрешения сборок не становятся сохранёнными source-результатами.

Полная сборка на целевой платформе:

```bash
python tools/generate/build_native_source_pack.py --build \
  --tml-references <tModLoader-lib/net8.0> --external-deps <ParticleLibrary-and-Luminance> \
  --harness-output <temporary-bootstrap-directory> \
  --runtime-dotnet <private-tML-dotnet> --runtimeconfig <official-tModLoader.runtimeconfig.json> \
  --target-rid <win-x64-or-linux-x64>
python tools/generate/build_native_source_pack.py --check --tml-references <tModLoader-lib/net8.0>
```

После генерации native harness пересобирается, чтобы скопировать ресурс в output; официальный release wrapper делает подготовку пакета перед сборкой `.tmod`. SDK нужен для компиляции, а collector и холодные прогоны используют отдельный private runtime точной версии из официального `tModLoader.runtimeconfig.json` с `--roll-forward Disable`, как launcher игры. Release wrapper готовит его автоматически. Архив создаётся для конкретных native/runtime dependency bytes. Пакет другой платформы или версии .NET не считается совместимым автоматически. Изменение `GeneratorClient*.cs` требует нового fingerprint и пакета; `--check` выявляет устаревшее сочетание. Обычная compile-only проверка не обязана пересобирать каталог.

Для этого режима compiler references и исполняемые зависимости выбираются из официального `tModLoader.deps.json` с учётом RID. DLL из вложенных MSBuild/BuildHost-каталогов не подмешиваются. После каждой сборки восстанавливается точный набор runtime assets и проверяется фактическое связывание CLR по SHA. Native resolver использует выбранные host-ом `TRUSTED_PLATFORM_ASSEMBLIES`, включая вложенные `Libraries`; неоднозначная ссылка не считается допустимой. Ресурс `.tmod` копируется в ограниченный буфер перед ZIP-чтением, поскольку нестандартный stream может сообщать `CanSeek=true` без обычной семантики `SeekOrigin.End`.

Холодный A/B запускает каждую пару в отдельном процессе уже собранного продукта, без предварительного capture. В измерение входят загрузка пакета, его проверки, capture, анализ и получение полного JSON. Сверяются исходные payload bytes всех четырёх фаз каждой пары; прохождение parity и достижение пятисекундной цели — отдельные условия.

[Приёмка 7 ноября 2026](PARENT_SOURCE_BENCHMARK_20261107_RU.md): четыре контрольные пары прошли порог менее 5 секунд на Windows и Linux, в каждом окружении совпали все 16 пар исходных JSON. Отчёт содержит точные commits, runtime inputs, параметры измерений и отдельные ограничения по памяти и игровым сценариям.

## Размеры

300000 символов compact Author dossier — development/test цель, не runtime admission. Craft не отвергается и данные не обрезаются лишь из-за её превышения. При размере сериализованного dossier **от 350000 символов включительно** existing logger записывает warning с размером, порогом и stage, без prompt/recipe/parent данных. Настройка отключения диагностических логов сохраняется.

Размер относится к символам dossier JSON, не токенам или полному provider request. Provider/response/transport ограничения остаются. Ваншотный Author, Author → Visual → VFX и frozen-first Repair не меняются.

Ориентир около 15000 символов на развёрнутую карточку mechanics — цель читаемости, не hard cap и не гарантия для любого предмета. В сравнении размеров отдельно указываются все parent slots, slots с native producer, readable code и весь dossier после exact sharing. Восстановление потерянной существенной механики может увеличить карточку; ради целевого числа она не удаляется.

## HTTP

GeneratorClient gzip-кодирует UTF-8 craft JSON только свыше прежних 2 MiB и если gzip короче. Прежние допустимые запросы остаются identity JSON. Server принимает один complete gzip member лишь на `/combine`: wire cap 2 MiB, decoded cap 32 MiB. Bounded decoding и strict JSON идут до cache lookup/Author. Prepared JSON, arrays, null/zero и несовпадающие root/fingerprint значения сохраняются. Для oversized requests нужны обновлённые обе стороны.

## Проверка и границы

`tools/checks/check_planner_prompt_usability.py --parent-captures <directory> --all-pairs` проверяет полные Prepare packets, ordered pairs и полный каталог Author capabilities. Превышение 300000 делает dev report отрицательным, но не блокирует production craft.

Python tests проверяют reversible notation, mappings/unknowns, source order, ammo observations и CFG alternatives. `test_author_payload_headroom.py` проверяет warning boundary и полный HTTP Chat/Responses request без truncation. Native checks отдельно проверяют identity, helper/inline effects, fingerprints, inventory/fallback, cache/cancellation, gzip и managed dependency packaging.

Размеры должны относиться к итоговому main-based DLL и свежим captures; старые weapon-only measurements не являются результатом main integration. Full C# completeness, произвольные modded hooks/detours, graphics/game-loop/MP и качество генерации не следуют из offline tests. Dependency-count bound профиля 635 остаётся explicit unknown, не доказательством отсутствия поведения.
