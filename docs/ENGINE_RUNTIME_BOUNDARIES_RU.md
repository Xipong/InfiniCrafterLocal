# Границы engine runtime

Практическая карта владельцев и ограничений `runtimeProgram` v5. **Это не сертификат игрового, сетевого или GPU acceptance.** Текущие правила ниже сверены с исходниками; прежние результаты аудитов и Live20 отделены в [историю](HISTORY_RU.md). Версия установленной Terraria/tModLoader и доступность зависимостей проверяются в среде запуска, а не выводятся из имени папки или старого отчёта.

Навигация: [контракт](#contract) · [authority](#authority) · [spawn](#spawn) · [delay/identity](#delay) · [единицы](#units) · [item/hooks](#items) · [placement/craft](#persistence) · [assets](#assets) · [presentation](#presentation) · [проверка](#verification) · [открытые границы](#limits).

<a id="contract"></a>
## Контракт и канонические владельцы

| Решение | Владелец | Граница |
|---|---|---|
| Entities, bindings, calls, ссылки и форма Author | [`program_schema.py`](../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py) | Author выбирает композицию. Имя, категория, DamageClass и prose не выбирают movement, controller, delivery или lifecycle. |
| Capability params, units, dependencies, event/authority facts | [`capability_registry.py`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) | Новый параметр требует полного vertical slice, а не одной карточки prompt. |
| Producer/source/target compatibility | [`event_producer_validation.py`](../LocalGenerator/infini_local/core/runtime_authoring/event_producer_validation.py) | Binding target и event source — разные вещи. VFX использует тот же фактический event surface, но не меняет gameplay. |
| Exact lowering, omissions и receipts | [`technical_lowering.py`](../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py), [`wire_validator.py`](../LocalGenerator/infini_local/core/runtime_authoring/wire_validator.py) | Каждому authored selector/value соответствует точный wire path; наличие пути среди outputs capability недостаточно. |
| Реальные инструкции модели и transport projection | [`author_item_contract.py`](../LocalGenerator/infini_local/pipelines/author_item_contract.py) | Проверять сериализованный system/user packet, не только helper или schema. |
| Strict DTO и исполнение | [`RuntimeProgramSpec.cs`](../ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs), [`GeneratedItem.cs`](../ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs), [`GeneratedProjectile.cs`](../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs), [`RuntimeProgramExecutor.cs`](../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeProgramExecutor.cs) | Finite typed dispatch, не arbitrary VM, generated C# или reflection scripting. |
| Completeness audit | [`primitive_loss_audit.py`](../LocalGenerator/infini_local/qa/primitive_loss_audit.py) | DTO declarations и reads конкретных consumers сопоставляются с Author; hidden/legacy fields требуют явной классификации. AST не доказывает весь game loop. |

Полные карточки и exact mappings не дублируются здесь: [generated inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [parity](PRIMITIVE_PARITY_RU.md), [lowery](../lowery.md). Правила преобразований и маршруты расширения — в [AGENTS](../AGENTS.md), [authoring](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) и [capability workflow](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md).

Baseline craft: Gameplay Author → Visual Director → VFX Director; Repair условен и leaf-local для своей стадии. Frozen siblings не меняются, optional additions вне permission игнорируются с audit, после merge проверяется полный stage output. Registry/runtime defect не исправляется моделью. [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md) владеет правами, read-only handoff и create/delete policy.

**Omission не равен invalid-value fallback.** В полном Author отсутствие разрешено лишь optional `ParamSpec` с одинаковыми объявленными `default` и `neutral`, после проверки композиции и с отдельным receipt. В Repair omission означает «не менять». Только реально применённый provider `json_schema`, чья nullable-обёртка optional object property объявляет такую encoding, допускает null → omission. `json_object`/off, unknown keys, null в arrays и ambiguous unions не очищаются/не угадываются; raw Repair сохраняется до projection. Подробности — [neutral omissions](DECLARED_NEUTRAL_OMISSIONS_RU.md).

<a id="authority"></a>
## Authority и hit trust

Основные guards — [`InfiniRuntimeAuthority.cs`](../ModSources/InfiniCrafterLocal/Common/Services/InfiniRuntimeAuthority.cs); различие NPC event roles — `RuntimeProgramExecutor.ShouldRunNpcEvent`. Общий `HasActionAuthority` используется перед delayed admission и при immediate/delayed dispatch. Enqueue не выдаёт вечное разрешение: execution перепроверяет роль и при отказе возвращает spawn reservation. Phase/peer authority остаётся обязанностью runtime, не новым выбором LLM; target/damage/depth preconditions сохраняются у effect consumers.

| Путь | Исполнитель | Чего не делать |
|---|---|---|
| Projectile child spawns, local cursor/mobility, hit lifesteal | SP или local owner-client | Dedicated server не создаёт вторую группу снарядов и не повторяет owner-side proc. |
| NPC status / AoE / chain на `on_hit` / `on_crit` | Owner через нативные `NPC.AddBuff` / `Player.ApplyDamageToNPC` | Vanilla strike packet не повторяет mod hit hook на сервере; простой server-only guard теряет эффект. |
| NPC effects на других events | Прежняя SP/server authority | Не переносить все events на owner из-за исключения для contact hit. |
| NPC velocity pull на owner-hit | Узкий server receipt bridge | Клиент не присылает authoritative force, buff или damage; сервер читает свои authored actions. |
| `owner_to_target` pull | Local owner при активной direct target | Отказ не переходит в NPC/area pull другого режима. |
| Presentation | Client-only | Косметический relay не повторяет gameplay/spawn. |

[`RuntimeHitPullBridge.cs`](../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeHitPullBridge.cs) сохраняет **vanilla owner-authoritative hit trust**, а не независимое доказательство server collision. Projectile lookup использует `owner + network identity`, не peer-local slot. Принимаются только известные item/entity/world identities, правильный sender, sequence и NPC generation; item source берётся из ограниченного недавнего server-observed activation, включая исходный input. Retired projectile grace и recent item source ограничены 60 world ticks. Admission — до 32 claims на sender/tick; delayed receipt actions — до 32 на owner в общей bounded queue. Сервер ставит `NPC.netUpdate` после velocity change.

[`RuntimeHitNpcGeneration.cs`](../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeHitNpcGeneration.cs) выдаёт NPC incarnation token на сервере и передаёт его через ExtraAI. Slot reuse не перенаправляет действие; `NPC.Transform` может сохранить ту же сущность. Без полученного token, вне source lifetime или при ambiguous identity receipt отвергается. Sender/generation/replay guards ограничивают claims, **не являются anti-cheat collision proof**. Native packet send observer и socket-free sender/receiver проверяют разные seams; ни один не подтверждает доставку в живом MP match. Custom whip tags и remote hit-VFX имеют отдельных потребителей, не принимаются автоматически этим gameplay bridge.

<a id="spawn"></a>
## Spawn: activation ledger, reservations и engine caps

`RuntimeSpawnBudget` в `RuntimeProgramExecutor.cs` — owner-local объект одной activation, общий для root siblings и descendants. Нельзя копировать оставшийся integer в каждого ребёнка или строить новый authoritative ledger из ExtraAI snapshot.

1. Root `HoldItem`/`Shoot` capacity задаётся authored `Spawn.Count`, ограниченным `MaxRuntimeSpawnCount`; root shots не тратят **event** allowance. `MaxEventSpawnsPerActivation=0` не запрещает корректный root shot.
2. Immediate event и controller shots расходуют общий ledger. Delayed spawn резервирует count **при enqueue**; sibling не может потратить забронированные slots.
3. Dispatch использует только reservation; children получают тот же ledger. Неиспользованные slots возвращаются; rejected enqueue, cancellation и clear не создают/не теряют allowance.
4. Для item-use общий `_itemEventBudget` живёт на Item activation; periodic item producer создаёт отдельный budget своей emission. Не объявлять этот clock универсальным lifetime предмета.

Consumers: `GeneratedItem.RootBindingSpawnCapacity/Shoot`, `GeneratedProjectile.SpawnRuntimeEntity/Configure`, [`GeneratedProjectile.Executors.cs`](../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs), scheduler. [`GeneratedProjectile.NetSync.cs`](../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs) передаёт **наблюдаемый** remaining count; remote scratch ledger не должен затирать полученный snapshot при terminal hooks.

Точные hard ceilings принадлежат [`InfiniRuntimeLimits.cs`](../ModSources/InfiniCrafterLocal/Common/InfiniRuntimeLimits.cs), не этой таблице:

| Лимит | Текущий ceiling / scope |
|---|---|
| Program shape | 12 entities, 8 bindings, 16 events/entity; declared lower limits также проверяются |
| Child depth / event allowance | 3 / 32 на activation |
| Одна spawn group / активные generated projectiles | 12 / 96 на owner |
| Runtime lifetime / range | 21 600 world ticks / 120 tiles |
| Pending delayed actions / due dispatch | 256 в общей очереди / 64 за world tick, совместно для всех scheduler visits |
| Delay / receipt subset | 1…600 world ticks при scheduling / 32 pending owner-hit actions на owner |
| Periodic action loop | Constant 16 ограничивает due-action loop projectile producer; это не доказательство общего per-owner rate limit |

Python graph/spawn validation, runtime ledger и active-projectile cap — разные ограничения. GREEN статического budget не доказывает реальное создание всей группы через `NewProjectileDirect`: для него нужны зарегистрированный content и world state.

<a id="delay"></a>
## Delayed actions: identity, source lineage и terminal events

Владелец — [`RuntimeDelayedActionScheduler.cs`](../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeDelayedActionScheduler.cs), обновление через `PostUpdateEverything`; `OnWorldUnload`/`Unload` очищают очередь и возвращают reservations. Enqueue сохраняет `Main.GameUpdateCount` и authored due tick с wrap-safe сравнением bounded delay. Повторный scheduler visit в том же world tick не продвигает delay и не пополняет dispatch allowance. При pressure исходный due tick сохраняется, а не заменяется новым countdown.

| Captured fact | Проверка / сохранённая семантика |
|---|---|
| Owner | Исходный `Player` + slot; due tick требует `ReferenceEquals` и active. Новый Player в том же слоте не становится владельцем старого события. Это не универсальный fence любого in-place reset. |
| Direct NPC target | Исходный instance + slot + active; reused slot даёт отсутствующую direct target. Delayed hit/crit pull при утрате direct NPC не превращается в area pull. Остальные действия сохраняют свои обычные null-target rules. |
| Item-use source | Клон Item при enqueue, точный поддержанный `EntitySource_ItemUse` или `_WithAmmo`, исходные Context/AmmoItemIdUsed. Расход последнего stack или поздний `SetDefaults` исходного Item не уничтожают stat lineage. |
| Projectile parent | Сам Projectile, slot/owner/type/identity **и ModProjectile generation**. Inactive terminal source допустим, заменённое поколение отменяет action и возвращает reservation. Terminal actions пока не полностью независимы от reuse. |
| Misc producer | Только объявленный item-body `periodic` с Context=`InfiniRuntimePeriodic`; произвольный source не переписывается в contextless Misc/ItemUse. |
| Position / damage source | Captured event center/direction и точная authored source entity; новый held item или движение retired host не выбирают источник заново. |

`RuntimeProgramExecutor.AuthoredEventDamage`: item body использует canonical Gameplay damage/class, projectile — свой Damage component. Это не live `Projectile.damage`, не `damageDone`, не primary entity и не категория. Hit/crit AoE исключает уже поражённую direct target; proximity/terminal AoE её не исключает, потому что proximity не является нанесённым contact hit. Lifesteal, напротив, использует фактический `damageDone` по своему контракту.

Charge-release controller — другая операция: один раз масштабирует **текущие** `Projectile.damage` и `knockBack`, уже включающие spawn/combat modifiers, не восстанавливает их из definition/`originalDamage`. Нулевая база остаётся нулевой; released-generation guard не допускает повторного scaling после AI/ExtraAI hydration.

[`GeneratedProjectile.RuntimeEvents.cs`](../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs) разделяет `on_expire` и `on_kill`: natural/final-AI expiry не должна повторить expire при OnKill; early kill не создаёт expiry. Два authored terminal actions с разными delay сохраняются независимо. Прежние headless матрицы проходили **последовательности mod hooks**, не vanilla `Projectile.Kill`/collision-driven game loop и не modded damage hooks.

<a id="units"></a>
## Единицы, нейтрали и precision

Все accepted domains, шаги и wire scales — в `ParamSpec`; таблица объясняет опасные различия, не создаёт альтернативную schema.

| Author / смысл | Доставка и ограничения |
|---|---|
| `configure_tool.axePowerTooltipPercent` | Целое 0…500, шаг 5 → прежний integer `gameplay.axePower = value / 5`. Старое Author-имя не становится alias. |
| `apply_generated_buff_on_use.lifeRegenHpPerSecond` | 0…60, шаг 0.5 → integer `gameplay.generatedBuff.lifeRegen = value × 2`. Equipment regen имеет собственный signed domain в registry. |
| Equipment bonus percent | `/100` в fraction там, где это объявлено; crit и damage-reduction percentage points не смешиваются с additive damage multiplier. |
| `taggedSummonSourceDamageBonusPercent` | Multiplier source damage против same-owner generated whip tag, не vanilla flat tag damage. |
| `periodTicks`, delays и duration | World ticks; `periodic` требует явный period, runtime minimum не разрешает отсутствующее authored значение. |
| `extraUpdates` / movement | Projectile update отличается от world tick; drift/gravity/turn/scale increments применяются на соответствующем update consumer. Raw local NPC cooldown и sentinel `-1` объясняются отдельно. |
| Mana regen, aggro, knockback, light strength | Объявленные engine coefficients/points, не выдуманные mana/s, probability, distance или light radius. |
| `DamageClass` / `ItemUseStyle` | Stat inheritance и animation/pose, а не weapon presets. Выбор summon не создаёт minion/controller; whip-class speed inheritance не означает melee damage inheritance. |

`ParamSpec.consumer_storage="float32"` для continuous generated-buff mining/movement/jump/light требует сохранить ненейтральность при storage. Exact neutral допустим; nonneutral, схлопывающийся в него, даёт `consumer_representability` на точном leaf до compilation, без округления/подстановки. Present malformed leaf не становится GREEN из-за другого рабочего buff. Это **storage representability**, не гарантия заметного изменения любого сколь угодно малого бонуса после последующей float32 арифметики Terraria.

При изменении units докажи обратимость **на всём прежнем accepted wire domain**, signed endpoints, neutral/sentinels и реальные JSON/runtime round trips. Сохрани wire и старые consumer clamps; иначе rename способен молча убрать диапазон. Замер compact cards или requiredness parity не измеряет model first-pass quality. [Историческая панель](HISTORY_RU.md#live) осталась RED; host defaults не являются её исправлением.

<a id="items"></a>
## Item projection, equipment и ammo

| Seam | Текущий invariant / нерасширенная граница |
|---|---|
| Binding effects | `ApplyActiveUseProjection/UseItem` исполняют resource/buff/mobility только с `apply_item_effects`. Один DTO с heal/buff без executable binding недостаточен. Pure `place_item` не производит `on_use`; contact и suppression проверяются независимо. |
| Defense | Signed accessory `defensePoints` передаётся в Item; vanilla начисляет defense, equip hook не прибавляет его второй раз. Глобальный Player floor не оправдывает сужение authored Item projection. |
| Move/mining aggregation | Sum/product сначала агрегируются, cap применяется к итогу; порядок получения buffs не выбирает результат. Refresh/expiry не превращаются в двойной stack. |
| Flat run speed | `AddGeneratedMaxRunSpeedBonus` копится в equip pass, ResetEffects сбрасывает; [`PostUpdateRunSpeeds`](../ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs) применяет после vanilla movement adjustments. `moveSpeed` остаётся ранним; прежний mount override сохранён. |
| Armor set | Exact setKey + реально надетые head/body/legs; set bonus не начисляется просто из наличия DTO. |
| Ammo | `Item.ammo`, `Item.useAmmo`, direct-use stackCost и ammo consumption различны. Rocket/solution `PickAmmo` возвращает authored projectile ID после vanilla offset, сохраняя speed/damage/knockback; поздний чужой GlobalItem hook может изменить выбор. |
| Custom whip | Geometry читает `Player.whipRangeMultiplier`; same-owner tag — отдельный [`GeneratedWhipTagGlobalNPC`](../ModSources/InfiniCrafterLocal/Common/Players/GeneratedWhipTagGlobalNPC.cs), не proof его отдельной MP replication. |
| Reusable throw / right-click | Returning projectile не возвращает Item, потраченный `stackCost=1`. `InfiniCore.ConsumeItem=false` защищает right-click consumption gate; это не полный UI lifecycle proof. |
| Parent facts | [`GeneratorClient`](../ModSources/InfiniCrafterLocal/Common/Services/GeneratorClient.cs) нормализует **request-only clone** без reforge, не original/refund copies. Generated ammo context сохраняет exact instance definition. `placeStyle=0` не означает missing; multiple placements нельзя свести к первому. |
| Diagnostics | `LastAppliedTrace` — последняя Item projection, не live stats после prefix/global hooks и не гарантированный per-Item журнал shared definition. JsonIgnore snapshot не меняет save/network/hash. |

[Standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) владеет намеренно не-exposed границами: weapon `Item.useAmmo` без полного PickAmmo vertical slice, sand ammo и ID-static immunity для shared proxy type. Numeric loaded-content IDs проверяются в сессии, но это не full-name переносимость между load orders. Built-in/strict `ModName/ClassName` DamageClass не подменяется Generic при ошибке.

<a id="persistence"></a>
## Placement, craft и durable storage

[`GeneratedPlacementLedgerSystem.cs`](../ModSources/InfiniCrafterLocal/Common/Systems/GeneratedPlacementLedgerSystem.cs) — владелец placement authorization, group/cells и возврата generated instance:

- Для tracked tile/wall `CanDrop/Drop` подавляет vanilla drop и ставит generated return. Group/cells снимаются из placement map, но **возврат не исчезает**: `PendingReturnRecord` содержит GeneratedItemId и `DefinitionJson`, сохраняется в world data и повторяется при временном spawn failure.
- `TrySpawnPendingReturnCore` использует подходящий current-world canonical registry record; при registry miss восстанавливает definition из сохранённого JSON. Настраивается именно Item, созданный `Item.NewItem`, а не новый объект вместо него; successful return снимает pending запись.
- Full item slots/мировая нагрузка и caught spawn exceptions — `TransientFailure`: запись ротируется и пробуется снова, не quarantined по числу попыток.
- Невалидная definition, mismatch ID или неправильный generated proxy — `PermanentFailure`: raw claim/definition/cause сохраняются в world quarantine, а не удаляются и не превращаются в vanilla replacement. Повреждённый quarantine envelope сохраняется целиком в отдельном versioned raw bucket и не прерывает загрузку корректных соседей. `TryRequeueQuarantinedReturn` допускает только явно предоставленную валидную definition с той же identity; повтор idempotent. Requeued forensic receipt остаётся историей, не вторым material owner и не второй занятой capacity. Raw history пока не имеет compaction policy; её сохранность не обещает автоматическое восстановление неизвестной definition.

Перед MP placement сервер фиксирует native before-state по intent **до** разрешения vanilla mutation. Protocol **v5** возвращает Ready с fingerprint server-owned canonical definition и заранее выделенным сервером group GUID; чужой binding/style или изменённые данные не принимаются по одному совпадению sequence. Peers требуют одинаковую версию, v3/v4 отвергаются без migration. Клиент использует выданный сервером GUID для provisional presentation и принимает commit/removal того же group ID; координата/type не являются identity. Runtime `PreItemCheck` один раз восстанавливает consumed input latch только для неизменённого, всё ещё удерживаемого и ещё не начатого intent; authored `autoReuse` не меняется. Отпускание, смена item/input/target, expiry или потеря identity не создают отложенное действие. Новый target может явно заменить точный старый sequence лишь до notify и при неизменённом before-state; поздний notify не восстанавливает старую authorization.

Remote station mirror не является локальным material/refund authority. Foreign/unscoped raw claims сохраняются отдельно от текущей работы и не блокируют свежие inputs другого мира. Hydration разрешена только для одного буквально совпавшего origin; ambiguous claims не выбираются/не сливаются, origin не угадывается. Save/reload/park сохраняют неизвестные расширения, не перезаписывая claim другого мира.

Strict player-save references — [`GeneratedItemData.cs`](../ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs): обязательные kind/version/runtime markers, exact current version; reference-only save не получает gameplay из DTO defaults и не мигрируется догадкой. Hook/JSON round trip не доказывает реальную `.plr` запись, binary ItemIO/TagIO, hydration или перенос world scope.

Craft lanes: [`InfiniCraftPlayer.MultiDev.cs`](../ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.MultiDev.cs) сохраняет lane 1 state machine и два отдельных jobs/inputs для llm_2/llm_3, а не прежний предложенный тотальный array refactor. Escrow, commit requestId, cancel/refund и world-exit backup должны рассматриваться совместно; профиль LLM не является gameplay authority. Старая multi-lane patch map — [история](HISTORY_RU.md#lanes), не инструкция к повторной реализации. Lost ACK, reconnect, full inventory и ошибка после spawn до final outcome требуют отдельного end-to-end acceptance.

<a id="assets"></a>
## Asset authority и lifecycle

[`GeneratedAssetSyncService.cs`](../ModSources/InfiniCrafterLocal/Common/Services/GeneratedAssetSyncService.cs) отвечает за declared byte identity, manifest/descriptors, bounded delivery и verified commit; [`RuntimeSpriteCache.cs`](../ModSources/InfiniCrafterLocal/Common/Services/RuntimeSpriteCache.cs) — за выбранный local key, GPU texture и retirement. Нельзя смешивать existence, byte certification, texture readiness и successful craft.

1. **Два transport paths.** HTTP bounded stream и server→client bounded PNG bundle/chunks существуют отдельно. Asset-request handler на сервере сверяет запрос с server-owned definition, проверяет length/PNG/SHA и вызывает `EnqueueAssetBundles`; chunk handler собирает bounded payload, проверяет bundle SHA и declared entries до commit. Client не авторитизует definition/PNG своими байтами. `assetTransport=http` не принимается chunk consumer. Packet transport не означает socket-match proof.
2. **Dispose и HTTP cancellation.** Общий lock/disposed flag сохраняет запрет нового download, late retry и file commit. Per-service cancellation завершает ожидание `HttpSlots`, HTTP и body read; worker освобождает только реально полученный permit, соседний service не отменяется. CTS освобождается после workers и завершения Cancel callbacks, cancellation не записывается как offline retry. Это не retirement уже queued main-thread callbacks и не общий job/resume manager.
3. **Canonical bytes.** `ResolveCertifiedLocalPath` использует certification существующего descriptor после full lifecycle PNG/length/hash validation или verified commit. Local shadow не outranks этот же declared certified asset. При conflicting filename length/SHA priority снимается; map order не выбирает владельца. Без certification сохраняется healthy local-only behavior.
4. **Hot-path boundary.** Freshness проверяется по file length/write timestamp, без decode/hash в Draw. Это не защита от adversarial same-stat mutation. Source selection не меняет authored path/visual design. Load failure и backoff адресуют exact selected normalized key.
5. **Texture borrowing.** Invalidate/LRU/Clear/Dispose снимают lookup authority сразу, но admitted Texture2D уходит в instance-owned retirement queue. Освобождение — через owner callback `Main.QueueMainThreadAction` на Update boundary вне Draw, а не немедленно в loader/download worker. Resident + retired учитываются при admission (ceiling — двойной effective resident capacity); pressure отказ не записывается как bad-file backoff. Доказательство quiescent boundary относится к проверенному installed API, при обновлении его надо перепроверить.
6. **Alpha и metadata.** Straight PNG RGB premultiplies один раз при cache insertion, alpha/disk bytes сохраняются; hits не повторяют conversion. Failed upload/conversion не публикует texture. Orientation metadata и художественный grip — разные решения.

Mandatory item-body baked PNG и PNG зависимость реально выбранного VFX consumer должны проходить [asset lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md); renderer selector не оправдывает missing PNG, dust downgrade или inventory-texture substitution. Existing placeholder draw при временной hydration/readiness ошибке **не делает обязательный asset contract GREEN**.

<a id="presentation"></a>
## Presentation отдельно от gameplay

[Presentation](PRESENTATION_CONSISTENCY_RU.md) и [VFX contract](VFX_MATERIAL_ELEMENTS_RU.md) владеют детальными controls; здесь только execution boundaries:

- Particle allowance живёт на world tick, draw allowance — на outer draw invocation, общий между under/over и active/detached consumers одного source. Новый simulation tick не должен пополнить draw allowance; новый draw не должен пополнить particle total.
- Client quality multiplier меняет effective allowance, не serialized authored budgets и не hard engine ceiling. Fractional Dust counts используют существующий RNG; короткая серия не гарантирует точную долю. LightCue client intensity не изменяет отдельный gameplay equipment light.
- Detached draws вне vanilla-owned SpriteBatch требуют собственного lazy Begin и finally-End только после успешного Begin; failed Begin не закрывает чужой batch. CPU FNA queues доказывают этот protocol, не GPU appearance.
- Detached retirement должен идти на all-client update без новых emissions/Draw; persistent item binding требует живого owner lifecycle, не одного `Player.active`. Death/replacement/generation и world snapshots имеют различные lifetime semantics.
- Material event admission выполняется один раз до immediate/delayed slot fanout через [`VfxOrderedPeerStream`](../ModSources/InfiniCrafterLocal/Common/VFX/VfxOrderedPeerStream.cs): synchronous-local и wire-relay sequences раздельны, replay cursors привязаны к transport session. История retired generations не является глобальным лимитом допуска новых source/owners. Live record/particle/source budgets сохраняются. Это контракт ordered transport, не поддержка произвольной перестановки пакетов.
- Remote Try-pattern rejection обязан не отдавать отвергнутую pose в out payload. Accessory hide-флаг использует реальный armor index. Это не proof dye/gravity/vanity precedence всех modded slots.
- Наличие config field/backend name само по себе не доказывает reachable consumption. Старые `EnableScreenCulling`/`ParticleAlphaMultiplier` observations и ParticleLibrary backend не объявляются исправленными одним light/particle/budget pass; нужен trace до update/draw consumer. Не подключать legacy BestAvailable с semantic fallback как «lossless» замену.

<a id="verification"></a>
## Как проверить изменение

1. Найди canonical owner и **реальный producer → consumer**, включая delay/NetSync; не ограничивайся enum/schema или вспомогательным тестом.
2. Пройди `registry → provider schema/prompt → validator → compiler receipts → strict wire → C# DTO → executor → tests → docs`. Проверяй точные source paths, type/range/unit conversion и frozen neighbors, а не только принадлежность output к capability.
3. Добавь positive/negative boundary к [тематическому test owner](TEST_CONTRACT_OWNERS_RU.md), сохрани captured bytes и independent historical wire hash. Не удаляй параметризованные numeric cases из-за размера collected count.
4. Запусти соответствующие read-only generated checks и contract gates, например из корня:

```bash
PYTHONPATH=LocalGenerator python tools/audit_targeted_repair.py --check
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/contract_parity.py
python tools/check_csharp_contracts.py
```

5. При доступных tML/FNA и внешних DLL отдельно собери и исполни **свежую** headless DLL. `tools/EngineRuntimeChecks.csproj` и его runner должны реально включать новый named check; наличие файла не означает coverage. Пример с host-supplied reference roots:

```bash
dotnet build tools/EngineRuntimeChecks.csproj -c Release \
  -p:InfiniTmlReferenceDir="<tModLoader lib/net8.0>" \
  -p:InfiniExternalDepsRoot="<ParticleLibrary/Luminance root>"
dotnet tools/bin/Release/net8.0/EngineRuntimeChecks.dll
```

Custom output paths требуют запуска точной построенной DLL. Ordinary mod DLL build, `.tmod` packaging, headless hooks и loaded game acceptance — отдельные результаты. Если зависимости отсутствуют, это `notRun`; downstream compiler/parser failure не превращается в SKIP по тексту лога. Игра, providers, GPU/MP кампании выполняются только по отдельному разрешению.

<a id="limits"></a>
## Неразрешённые ограничения и уровень доказательства

| Что остаётся отдельной проверкой | Почему прежний GREEN не заменяет её |
|---|---|
| World placement → save/reload → break/explosion → ровно один return, multi-tile и MP ordering | Native ledger/NBT/hook observer не является полной world chain; durable quarantine сохраняет corrupt claim, но не создаёт отсутствующую валидную definition. |
| Craft/escrow lost ACK, reconnect, dedupe/cancel/refund и post-spawn exceptions | Prepared refund copies и lane source reads не доказывают фактический inventory возврат. |
| Delayed in-place reset и reuse terminal lineage | Player/NPC replacement fences не универсальны; cancelled reused projectile generation не является immutable terminal snapshot. |
| Mobility safe destination, solid/lava, recall, camera/biome и intent packets | Реальный Teleport completion/position observer на ограниченном fixture не покрывает все world branches. |
| Save/hydration, world-scope spoofing, load-order переносимость content IDs | Strict DTO/version и network JSON не равны binary persistence или разрешению отсутствующей definition. |
| Movement/controller/collision combinations, group spawn и сторонние mods | Method anchors/AST и entry interception не доказывают registered world spawn или всю vanilla hook последовательность. |
| HTTP reads, queued callbacks, world/endpoint switch, PNG corruption matrix | Held-body/slot tests доказывают bounded HTTP retirement и permit restoration, не всю queued-callback/world-switch цепь; обычный PNG positive/negative не исчерпывает format/parser matrix. |
| Asset textures и VFX GPU/art acceptance, capture/camera/frame pacing | CPU queues, native offscreen material proof и in-game appearance — разные слои; отдельно требуются assets/body integration и visual review. |
| MP sockets, lag/reconnect, hit/VFX/tag replication и anti-cheat | Memory serialization/NetMessage observer не доставляют пакет; owner trust не становится независимым hit witness. |
| Export commands и performance | Applied field/JSON/hash observer не проверяет chat renderer, real dumps, export collision, allocation cost или frame-time. |
| Live first-Author success и реальные assets | Offline completeness/Replay и no-image pipeline GREEN не закрывают исторический acceptance RED. |

Этот список — сохранённые границы доказательства, **не перечень подтверждённых новых багов и не поручение автоматически запускать кампании**. Исторические поправки, snapshot counts и неизменённые RED verdicts доступны в [HISTORY_RU](HISTORY_RU.md); текущие runtime claims должны снова подтверждаться по указанным canonical owners.
