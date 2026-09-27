# Исправления аудита `81509e2`

Область: девять подтверждённых находок аудита `81509e22dec0f149b597ad36ec3377f0358e5cb4` и дополнительная граница Gameplay frozen-first. Исходный отчёт и frozen Live20 не переписываются. Изменения не вводят semantic router, whole-weapon preset, новый модельный проход или выбор механики кодом.

## Контракты и владельцы

| Находка | Исправленная граница | Канонический владелец / регрессия |
|---|---|---|
| A1: явный null → default | Только фактически использованный `json_schema` и объявленная provider-схемой nullable-обёртка optional object property разрешают null → omission. `json_object`/off, неизвестные ключи и null в массивах сохраняются для отказа validator; индексы не сдвигаются. Raw Repair сохраняется до проекции. | `author_item_contract.py`, `llm_authoring_pipeline.py`; `test_gameplay_nullable_transport.py` |
| A2: frozen placement binding | Точное разрешение `placementCallId` допускает соответствующий binding в merge. Соседи frozen; существующий authored action root предлагается как exact reference repair, а не лишний новый binding. | `repair_scope.py`; `test_repair_scope_frozen_semantics.py` |
| A3: неверный путь VFX negative prompt | Каждое ошибочное sprite-поле получает собственный diagnostic path и только своё Repair permission. | `vfx_manifest.py`; `test_vfx_renderer_requirements.py` |
| A4: item impactSprite → dust | Item event использует тот же dedicated impact texture → detached sprite consumer, что projectile. Сохраняются event/entity, layer, scale, alpha, duration и draw budget; отсутствующий sprite не заменяется dust или inventory texture. | `InfiniItemVfxRuntime.cs`, `InfiniVfxRuntime.cs`; `EngineRuntimeChecks.ItemImpact.cs` |
| A5: малые бафы исчезают | Убраны произвольные C# deadbands `0.001f`; нейтрали сравниваются точно. Число, которое при float32 storage превращается из ненейтрального в нейтральное, явно отвергается до compilation, без изменения authored value. | `ParamSpec.consumer_storage`, `validator.py`, `GeneratedItemData.Model.cs`, `InfiniCraftPlayer.Mobility.cs`; `test_generated_buff_precision.py`, `EngineRuntimeChecks.BuffPrecision.cs` |
| A6: ошибка build → SKIP | Только preflight exit `77` и успешный parser означают notRun. Downstream compiler/parser exit 77 преобразуется в failure 1, прочие ошибки сохраняют код. Текст лога больше не выбирает статус. | `.github/workflows/ci.yml`, `build_tml_windows.ps1`; `tools/test_tml_ci.py` |
| A7: malformed buff скрывается соседним эффектом | Каждый присутствующий leaf проверяется по registry wire type/range/domain независимо от any-effect predicate. Неизвестные поля отвергаются; отсутствующие legacy leaves сохраняют DTO-default semantics. | `wire_validator.py`; `test_audit_wire_buff_fields.py` |
| A8: inert Repair меняет duration/color | Права выводятся из causal requirement metadata: ненейтральные/ненулевые effect params и только необходимые отсутствующие conditional companions. Уже валидная длительность и unrelated color frozen. | `repair_scope.py`; `test_repair_scope_frozen_semantics.py` |
| A9: malformed receipt падает | Тип строки и обязательных полей проверяется до чтения; structured violations сохраняют исходный receipt index. Невалидные строки не дают source coverage. | `technical_lowering.py`; `test_audit_malformed_receipts.py` |
| Gameplay frozen-first | Premerge проекция канонической schema проверяет структуру, типы, variant discriminators и unknown keys; numeric bounds и conditional value constraints проверяются после frozen merge. Невалидное frozen numeric-значение не отменяет полезный exact repair. | `program_schema.strict_repair_structure_report`, pipeline и scope filter; `test_repair_scope_frozen_semantics.py` |

## Точные ограничения

### Nullable transport не invalid-value fallback

Local Author не разрешает явный `manaCost: null`. Provider strict schema может потребовать nullable-ключ вместо отсутствующего optional-ключа; только в этом конкретном transport контракте null означает omission. Сопоставление использует local schema, реально отправленную provider schema и metadata фактически применённого response format. Пропуск после projection в полном Author имеет только объявленную семантику; в Repair — no change. Реальный system packet объясняет nullable transport при `json_schema`.

Массивы не фильтруются, unknown keys не удаляются, ambiguous union не угадывается. Syntax-only Repair сравнивает исходный и исправленный документы после их собственных transport projections и не получает права менять дизайн.

### Float32

`consumerConstraint` объявлен для четырёх continuous generated-buff параметров: mining multiplier, movement, jump, light. Он виден в реальных Author/Repair packets и schema annotations. Диапазоны и прежний wire не округляются и не сужаются произвольным epsilon. Exact neutral допустим; ненейтральное значение, схлопывающееся к нему при float32 storage, даёт `consumer_representability` на точном leaf и обычный bounded Repair.

Это проверка представимости **storage**, не обещание отсутствия обычного округления во всех последующих операциях Terraria или заметного эффекта любого сколь угодно малого коэффициента. Реальные hooks проверены для ±0.0005 и соседних с единицей float32 mining значений, отдельно как sole effect и с healing/ore companion.

### Headless sprite proof

Проверка проходит реальные `UseItem`/contact hooks, relay consumer без сокетов, shared detached queue и FNA `Begin/Draw/End`. Dedicated texture проверяется в CPU draw queue; только GPU `FlushBatch` перехвачен. Проверены missing/wrong assets, owner/event guards, lifetime, authored/client budgets, совместные слои и отсутствие dust downgrade. Это не GPU-скриншот и не сетевой матч.

## Проверка интегрированного дерева

- Полный Python suite после дополнительного A9 path-parser fix: **1299 passed**; Ruff clean; Pyright **0 errors / 0 warnings**. Исходное исключение на 4301-значном receipt index повторено родителем до исправления; после него возвращается structured RED с исходным индексом строки. Отдельная A9 suite — 39 passed, включая final/authored/source-list paths.
- C# headless runner: **69 passed, 0 failed**, включая два новых именованных checks в canonical csproj и runner.
- Обычная DLL-only сборка Windows `dotnet.exe`, tModLoader `2026.6.3.6`: **0 warnings / 0 errors**; packaging выключен явно.
- Восемь offline PowerShell CI regressions: **OK**. Workflow и production build/parser исполняются реально; только native compiler — явно synthetic fixture.
- Независимые ревью Python/Repair, C# consumer, CI и delivery завершены. Найденный при первом review A9 overlong-index gap исправлен; повторное узкое ревью — **passed**, без logic/security замечаний. Дополнительно 52 witnesses / 2926 receipts прошли source-aware и wire-only проверки.
- Все **12** registry/schema/docs/Repair/standardization/delivery/parity/mutation/C#/hygiene/sandbox gates: exit 0.
- Исторические **52 witnesses + 18 accepted Author documents**: compiled JSON и receipts **70/70** без изменений; сохранённые **18 VFX manifests** также идентичны.
- Точный captured `meteor_spacegun` Author + единственный captured Repair теперь проходят filter → final validation → compiler без counterfactual scope. Исходные captured bytes сохранены. Исторический Live20 по-прежнему **18/20 RED** — это новый offline replay, не новый live результат.

Артефакты родительской проверки находятся вне source tree: `../artifacts/audits/fixes-81509e2/`. Новый Live20/provider вызов, запуск игры, GPU, MP sockets и `.tmod` упаковка не выполнялись. Отдельная публикация на GitHub в эту проверку не входит.
