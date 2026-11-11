# Карта графового анализа родителей

Короткий маршрут по файлам, которые собирают свидетельства об исходной механике родительского предмета и доводят её до Gameplay Author. Это специализированный раздел [общей карты исходников](../CODE_MAP_RU.md#fast-start), а не второй каталог всего проекта. Подробный контракт и ограничения: [анализ и транспорт](PARENT_SOURCE_ANALYSIS_RU.md), [native facts](PARENT_NATIVE_FACTS_RU.md).

Сверено с [main `0ccf50ac`](https://github.com/Xipong/InfiniCrafterLocal/commit/0ccf50acda24bd839d6348e2c707b1edc3f25298), 11 ноября 2026. Для новой задачи проверяй текущие символы и callers: номера строк и перечни лимитов здесь намеренно не фиксируются.

## 1. Что здесь называется графом

Не смешивай четыре представления:

- **`parentSourceGraph`**: ограниченный граф достижимых compiled-source кандидатов от item/hooks к helpers, projectiles, buffs, tile/state consumers. Его producer — `ParentSourceGraph`. Он содержит `roots/nodes/edges/members/modules`, причины неполноты и результат отбора.
- **`attackReference`**: отдельные native projectile observations, symbolic expressions, guards, зависимости, method certificates и ссылки на readable C#. Это не копия всего `parentSourceGraph`.
- **`mechanicsSource`**: отдельное приблизительное C#-представление для чтения механики. Допущение о стабильности captured identity через opaque calls не становится строгим доказательством.
- **Author context**: Python-проекция этих данных, включая `packet.raw.mechanics`, uncertainty, shared references и компактную notation. Она отличается от исходного capture и от окончательного HTTP request.

Ни один слой не является полным графом исполнения Terraria. Statement или child edge — источник возможного поведения, а не доказательство его выполнения. `unknown`, `unresolved`, отказ и omission не означают отсутствия механики. `whole_method` описывает одно тело метода, не полноту предмета, hooks или detours.

## 2. Путь данных: от предмета к модели

```text
Игровой поток: Item + Player
  PrepareDeferred → Prepare → ToWireItem
    → native facts / projectile-ammo snapshots + deferred source jobs
Worker: GeneratePreparedBlocking → CompleteAnalysis → ParentAnalysis.Resolve
    ├─ ParentSourceGraph.Item/Finish
    │    → ParentSourceMethod → discovery → SelectExport / BuildExport
    └─ ProjectileAttackSource
         → IL/CFG observations + spawn/lifecycle/interaction sources
         → verified C# + отдельный mechanicsSource
  → разрешённый payload → PayloadJson → HTTP /combine
  → Handler.do_POST → handle_combine_request → combine
  → try_llm_plan → build_initial_author_request → build_llm_author_payload
  → raw_parent_card_for_llm → parent_context_for_stage → mechanics_context
  → exact sharing + source notation → llm_chat_json
  → выбранный Chat / Responses / Codex transport
```

Нужные worker-у live snapshots возвращаются на исходный игровой поток через `SourceSnapshotOnMain` → `ParentAnalysis.OnMain` → `Pump`; source reader не запускает игровой сценарий на worker.

`parentSourceGraph` добавляется для обычных vanilla/modded родителей (`existing is null`), а accepted generated-parent data проходит отдельным путём. Native projectile `attackReference`/`mechanicsSource` требуют допустимой vanilla identity и не обещают readable C# для произвольного ModProjectile.

Это маршрут новой генерации. Cache/resume могут обойти первичный Author. Синхронный `Prepare` остаётся отдельным входом для offline capture; live craft использует deferred analysis. Игровые callers: `mod/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Station.cs`, `InfiniCraftPlayer.Multiplayer.cs`, `InfiniCraftPlayer.MultiDev.cs`; worker запускается в `InfiniCraftPlayer.CraftState.cs` / `InfiniCraftPlayer.MultiDev.cs`. Вызов `Pump` на каждом update и `Invalidate` при world/mod unload находится в `mod/InfiniCrafterLocal/Common/Commands/InfiniDumpCommand.Export.cs::InfiniDumpSystem`. HTTP ingress: `generator/infini_local/web/server_handler.py` → `generator/infini_local/services/combine_endpoint.py`.

## 3. C#: захват и ядро графа

Все файлы этой таблицы находятся в `mod/InfiniCrafterLocal/Common/Services/Generation/`. Имена с одинаковым префиксом — части одного `GeneratorClient`, не независимые сервисы.

| Файл | Роль и точка входа |
|---|---|
| `GeneratorClient.cs` | `PrepareDeferred`, `Prepare`, `PreparedGenerationRequest.CompleteAnalysis`, `GeneratePreparedBlocking`: сбор запроса, разрешение отложенного анализа до HTTP, admission payload. |
| `GeneratorClient.ParentFacts.cs` | `ToWireItem`, `CaptureParentNativeFacts`, `ProjectileRawSnapshot`, `ReferencedProjectileSnapshots`: observed item/projectile facts, root/runtimeFacts/fingerprint, child profiles. Player-aware ammo и player-free fingerprint остаются разными наблюдениями. |
| `GeneratorClient.ParentAnalysis.cs` | `ParentAnalysis.Defer/Resolve/OnMain/Pump/Invalidate`: перенос source-only работы на worker, возврат native snapshots на исходный игровой поток, cancellation и world lifetime. Внутренние deferred markers не должны дойти до HTTP. |
| `GeneratorClient.SourceGraph.cs` | `CaptureParentSourceGraph`, `ParentSourceGraph.Item/Inspect/Consumers/Finish`: roots, discovery helpers/детей/consumers, state links, fixed point. `ProjectileIdentityWindows` выделяет source windows, но не доказывает вход в них. |
| `GeneratorClient.SourceGraph.Selection.cs` | `DiscoveryValues`, `StatementGroups`, `WritesActorState`, `WritesMethodOutput`, `SelectExport`, `BuildExport`: отдельный от discovery отбор механических statements с dependencies/guards; actor-state writes и formal ref/out/return outputs имеют разные roots; приоритет связанного ядра, rooted transport graph, omissions и перенумерация ссылок. |
| `GeneratorClient.SourceGraph.Dispatch.cs` | `SourceInvocation`, `InvocationKey`, `FollowSourceCall`, `CapturedVirtualTarget`: контекст конкретного вызова и receiver. Выбор concrete virtual/interface target требует доказательства; unbound receiver может оставить declared body как unresolved candidate. Один метод может встречаться в разных invocation contexts. |
| `GeneratorClient.SourceGraph.NativeContext.cs` | `ReadInvocation`, `NativeCallBindsIdentity`: parent-local native slices и перенос identity в helper. Отказ optional identity proof сохраняет доступный raw source, но не разрешает identity-based child admission. |
| `GeneratorClient.SourceMethod.cs` | `ParentSourceMethod`, `Value`, `Block`, `Definitions/Reach/ControlledRegion/ProjectForGraph`: IL → value/CFG IR → data/control dependencies → компактная source-проекция. Exception regions дают явный `exception_regions` refusal; независимый verified C# может остаться доступным. |
| `GeneratorClient.SourceMethod.FastAnalysis.cs` | `LinkLocalsBitsets`, `SolvePostdominators`: reaching definitions и postdominators с work bounds. Менять вместе с семантикой основного reader, а не как отдельный упрощённый анализатор. |
| `GeneratorClient.SourceFiniteIntegers.cs` | `SourceFiniteIntegers.Evaluate`: bounded integer alternatives для source candidates. Неполное множество с unknown не даёт права исключать остальные варианты. |

**Важный порядок:** `Finish` сначала обрабатывает приоритетный parent/causal source и связанных consumers, затем deferred general dispatch с повторным замыканием зависимостей. `SelectExport` работает после discovery. Не лечи потерю причинной связи простым увеличением размера JSON или отбором первых N строк.

## 4. C#: native projectile source и readable C#

Префикс файлов тот же, что в предыдущем разделе.

| Файл | Когда открывать |
|---|---|
| `GeneratorClient.AmmoFacts.cs` | `ReadAmmoIl`: общий низкоуровневый IL decode. Ammo observations и source-derived варианты не приравниваются к реально выбранному боеприпасу/выстрелу. |
| `GeneratorClient.ProjectileAttackFacts.cs` | `CaptureProjectileAttackReference`, `BuildProjectileAttackSource`, `AttackSourceObservation`: основная сборка native attack evidence; связывает observations, certificates, C#, lifecycle/interaction и spawn references. |
| `GeneratorClient.AttackIdentitySelection.cs`, `GeneratorClient.AttackIdentityAlternatives.cs` | `AttackIdentitySelection`, `AttackCallBindsCapturedActor`, `DescribeIdentityAlternatives`: строгий identity-selected CFG, receiver binding и альтернативы. Не подменять приблизительным AST pruning. |
| `GeneratorClient.ProjectileSpawnFacts.cs` | `CaptureProjectileSourceSlices`, `CaptureProjectileSpawnSlices`: отдельные connected effect/spawn slices, сохранение symbols и зависимостей при объединении. |
| `GeneratorClient.NativeCSharpSource.cs` | `NativeCSharpModule`, `GetNativeCSharpDocument`, `AttachNativeCSharpSource`, `BuildNativeCSharpRecordForLinks`: проверка PE/reflection, ILSpy, readable records, source maps и optional certified specialization. Отказ IL/CFG не обязан уничтожать независимо проверенный полный C#-метод. |
| `GeneratorClient.MechanicsSource.cs` | `BuildMechanicsSourceRecord/View`, `CaptureProjectileMechanicsSource`: приблизительная identity AST-проекция и её явные assumptions/refusals. |
| `GeneratorClient.NativeCSharpIntervals.cs` | `NativeSourceCallIndex`, `PruneOwnedCSharpIdentityBranches`: точные IL intervals и AST edits. Пропуски между intervals нельзя превращать в покрытые offsets. |
| `GeneratorClient.ProjectileLifecycleFacts.cs` | `CaptureProjectileLifecycleSource`: условные регионы `Projectile.Kill` и связанные spawn callsites вне AI. |
| `GeneratorClient.ProjectileInteractionSource.cs` | `CaptureProjectileInteractionSource`: `Damage/StatusNPC/HandleMovement`, guards, неизвестные external inputs и ограниченные helpers. Relevance по identity не доказывает истинность guard. |
| `GeneratorClient.ItemDispatchSource.cs`, `GeneratorClient.ItemDispatchHelpers.cs` | `CaptureNativeItemDispatchReference`: отдельные item dispatcher regions и helper source. Нужны для item-only механики, не только для projectile AI. |
| `GeneratorClient.NativeCertificates.cs` | `NativeCatalogVerified`, `AuditedNativeCertificate`: проверка замороженных native catalog facts. Не путать с reader текущего loaded IL в `ProjectileAttackFacts.cs`. |

### Кэши и стоимость анализа

- `GeneratorClient.SourceGraphCache.cs` — `ReadCompleteSourceMethod` / `ParentSourceGraphCache`: complete-method facts и immutable projections. Не кешировать здесь actor state, parent-specific slices или решения текущего графа.
- `GeneratorClient.ProjectileAttackFacts.cs` — `ProjectileAttackProgramCache`: native source по type/style, immutable backing и независимые JSON views. Invalidation не должна позволять старому build заново наполнить сброшенный cache.
- `GeneratorClient.NativeCSharpSource.cs` — документы и lifetime общего PE/resolver; проверка перед cache hit сохраняется.
- `GeneratorClient.NativeSourcePack.cs`, `GeneratorClient.NativeSourcePack.Dependencies.cs` — проверенный build-time cache source-проекций, точные ключи/dependency bytes. Miss запускает обычный reader, не придумывает отсутствующую механику. Producer: `tools/generate/build_native_source_pack.py`.
- `mod/InfiniCrafterLocal/Common/Analysis/IndexedBitSet.cs`, `SourceAnalysisBuffers.cs` — низкоуровневые bitset/buffer helpers. Allocation-оптимизация не меняет dependency/guard semantics.

Числа лимитов бери из владельца и emitted `limits`: discovery, transport export, отдельный method и C# document имеют разные бюджеты. Не переносить предел одного слоя на другой.

## 5. Python: что действительно получает Author

Пути таблицы относительно `generator/infini_local/pipelines/`.

| Файл | Роль и якорь |
|---|---|
| `context/parents.py`, `context/cards.py` | `native_item_context_from_dump`, `compact_item_raw_for_llm`, `raw_parent_card_for_llm`: capture/dump → parent packet; отдельные item/projectile/ammo facts и accepted generated-parent data. |
| `context/attack_behavior.py`, `context/attack_expressions.py`, `context/attack_tables.py` | `project_attack_behavior`, `compact_attack_expressions`, `pack_attack_tables`: вызываются уже из `parents.py::_compact_attack_source`, до stage view; проецируют recognized attack evidence, expressions, зависимости и таблицы. Unknown formats не получают догаданную семантику. |
| `context/parent_stage.py` | `parent_context_for_stage`, `share_exact_native_parent_facts`: stage view, известные draw-only projections, точное shared factoring. |
| `context/mechanics_context.py` | `mechanics_context`, `_author_source_graph`: readable mechanics, source slices, uncertainty и known-schema graph view. Проверяй `transportOmissions` и `parentSourceGraphOmission`. |
| `context/mechanics_selection.py`, `context/author_mechanics_policy.py` | `select_gameplay_roots`, `_gameplay_identity_program`, `select_author_mechanics`: gameplay roots, транзитивные dependencies/predicates, certificate-bound выбор source и diagnostics. |
| `context/csharp_source_view.py`, `context/native_csharp_source.py`, `context/native_interaction_source.py` | Проверка и проекция producer C# records, exact source references, guards и source maps. Нельзя заменять привязку certificate совпадением имени метода. |
| `context/whole_method_author.py` | `prepare_whole_method_author/apply_whole_method_author`: альтернативный verified whole-method context. В `author/prompt.py` выбирается только если итоговый compact/shared вариант меньше обычного. |
| `context/author_source_notation.py` | `compact_author_parent_context`: обратимая notation, exact source sharing и diagnostics. Source indices/aliases принадлежат своему scope. |
| `author/prompt.py` | `build_llm_author_payload`: окончательная сборка dossier, сравнение вариантов context и `sourceWireUnits`. |
| `author/request.py` | `build_initial_author_request`, `try_llm_plan`: system/user messages, schema, options и trace; вызывает `llm_chat_json`. Warning о размере не означает truncation. |
| `combine_pipeline.py` | `combine`: orchestration новой генерации, cache/resume и последовательность стадий. |

**После dossier есть ещё transport.** `transport/client.py` выбирает маршрут; обычные Chat/Responses проходят `transport/http.py`, Responses дополнительно преобразуется в `transport/provider_wire.py`. Codex subscription идёт через `generator/infini_local/services/codex_text_backend.py` → `codex_auth.py`. Offline replay может вообще не обращаться к сети. Builder/preview не доказывает точные отправленные bytes, retries или выбранный physical model.

## 6. Как локализовать потерю данных

Сравнивай одну и ту же identity/callsite в соседних слоях, а не только конечный текст модели.

| Симптом | Первый seam и что проверить |
|---|---|
| Нет нужного hook/helper/child уже в capture | `GeneratorClient.SourceGraph.cs` → `GeneratorClient.SourceGraph.Dispatch.cs` / `GeneratorClient.SourceGraph.NativeContext.cs`: root, receiver/origin, admission, unresolved, causal edge. Для projectile child также `ProjectileSpawnFacts.cs` и `ReferencedProjectileSnapshots`. |
| Discovery нашёл механику, но экспорт её потерял | `SourceGraph.Selection.cs`: dependency/guard closure, mechanical bundle, retained root path, `omitted*Count`, `sourceCoverage`, `coverage`, `unresolved`. |
| Неверное значение local или исчез guard | `GeneratorClient.SourceMethod.cs` + `GeneratorClient.SourceMethod.FastAnalysis.cs`: reaching definitions, branches, address escapes, entry-from-omitted-flow. Не вычислять unknown по похожему соседнему literal. |
| Strict source есть, readable C# отсутствует/разошёлся | `NativeCSharpSource.cs`: method/MVID/hash/token, PE verification, IL/AST mapping, coverage и refusal; затем `MechanicsSource.cs`. Проверяй strict и approximate пути отдельно. |
| Raw capture верен, Author потерял dependency/child/unknown | `parents.py::_compact_attack_source` → `native_csharp_source.py` / `attack_behavior.py` → `parent_stage.py` → `mechanics_selection.py` / `mechanics_context.py` → `author_source_notation.py`: exact refs, `strictIdentitySelections`, `sourceSlices`, `uncertainty.sourceFacts`, omissions и scope aliases. |
| Всё есть в builder, но неизвестно, что ушло провайдеру | `author/request.py` → фактический provider/API route. `generator/infini_local/storage/trace_tools.py::persist_stage_request` сохраняет sanitized builder messages, не весь HTTP payload. Codex имеет отдельный transport-artifact путь через `trace_runtime.py::trace_codex_transport`; обычный `transport/http.py` пишет attempt diagnostics, но не сохраняет полный request body. Не объявляй exact wire наблюдённым по stage preview. |
| Задержка/память/повторная декомпиляция | `ParentAnalysis.cs`, method/program/document caches и source pack. `INFINI_PARENT_ANALYSIS_PROFILE=1` даёт job/source/C# фазы. Сравни cold, warm и cache-reset отдельно; allocated bytes не равны peak RAM, headless time не равен FPS. |

## 7. Проверки по затронутому слою

C# семейства находятся в `tests/native/context/`, общий префикс — `EngineRuntimeChecks.`:

- Graph/discovery/export: `ParentSourceGraph.cs`, `SourceGraphSelection.cs`, `SourceGraphMonotoneCore.cs`.
- Receiver/native identity/output: `SourceGraphDispatch.cs`, `SourceGraphConsumerDispatch.cs`, `SourceGraphGlobalBuffDispatch.cs`, `SourceGraphNativeContext.cs`, `SourceGraphHookOutputs.cs`.
- IR/cache/performance: `SourceSparseLocals.cs`, `SourceFiniteIntegers.cs`, `SourceGraphCache.cs`, `SourceProjectionCache.cs`, `SourceMemoBudget.cs`, `SourceIntervalPruning.cs`, `SourcePackDependencyLifetime.cs`, `ParentAnalysis.cs`, `ParentAnalysisProfiling.cs`.
- Strict/approximate source: `ProjectileAttackFacts.cs`, `MechanicsSource.cs`, `MechanicsForeignWrites.cs`, `ItemDispatchSource.cs`, `ProjectileLifecycleFacts.cs`, `ProjectileInteractionSource.cs`.
- Readable source/pack: `NativeCSharpSource.cs`, `NativeSourcePack.cs`, `NativeSourcePackSafety.cs`.

Python: `tests/generator/context/test_mechanics_context.py`, `test_mechanics_selection.py`, `test_author_mechanics_policy.py`, `test_mechanics_author_integrity.py`, `test_mechanics_supplement_projection.py`, `test_parent_source_order.py`, `test_native_attack_behavior_view.py`, `test_native_attack_expression_view.py`, `test_native_attack_tables.py`; notation/dossier: `tests/generator/authoring/test_author_source_notation.py`, `test_author_payload_headroom.py`.

Для известного owner не обходи дерево целиком:

```bash
python tools/agentctl.py context --path mod/InfiniCrafterLocal/Common/Services/Generation/GeneratorClient.SourceGraph.cs --find "internal static JsonObject CaptureParentSourceGraph("
python tools/agentctl.py context --path generator/infini_local/pipelines/context/mechanics_context.py --find "def _author_source_graph("
python tools/agentctl.py verify --path <изменённый-repo-relative-файл> --plan
```

Plan не запускает проверки. Native labels/filter выбирай из `tests/native/EngineRuntimeChecks.cs`; правила окружения и запуск свежесобранной DLL — в [TESTING](../TESTING_RU.md). Source inspection, unit tests, native CPU, реальный craft и GPU/MP — разные уровни доказательства. Документационные изменения требуют refresh/check handbook; не объявляй runtime или release проверенными по одной карте.
