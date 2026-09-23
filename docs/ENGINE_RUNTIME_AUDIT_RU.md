# C# engine runtime: промежуточный широкий аудит

Это карта проверки, НЕ сертификат «весь движок исправен».
Аудит приостановлен по просьбе пользователя после закрытия detached SpriteBatch defect (п. 28).
Рабочий tree: `InfiniCrafterLocal_v0_4_234_secondary_refit_noise_cleanup`, ветка `main`.
На этапе этого аудита существовавший dirty tree сохранялся без commit/push; упаковка, игра, LLM/SDCPP и внешние агенты не запускались. Последующая интеграция и публикация накопленных изменений вместе с OAuth описана отдельно в `CODEX_IMAGE_OAUTH_RU.md`; она не расширяет приведённые ниже границы игрового acceptance.

## Подтверждено и исправлено в этом проходе

1. `Common/Systems/GeneratedPlacementLedgerSystem.cs`, `LoadWorldData`:
   boxed Int32 передавался в `Enum.IsDefined` для byte enum. Реальный hook падал
   на первой корректной tile-записи с `ArgumentException` (Int32 / Byte).
   Теперь перед приведением проверяется диапазон byte, затем типизированный enum.
   Регрессия проверяет tile/wall, повторный SaveWorldData/LoadWorldData,
   точное сохранение definitionJson, недопустимые слои и значения, которые
   при unchecked cast превратились бы в допустимый слой. У плохих строк отдельные
   координаты, чтобы dedupe не маскировал ошибку. Это НЕ тест физического разрушения
   тайла и выпадения предмета в загруженном мире.

2. `Content/Items/GeneratedItem.cs`, accessory `ApplyEquipmentEffects`:
   защита считалась дважды: Terraria `GrantArmorBenefits` применяет Item.defense,
   затем мод повторно прибавлял Accessory.Defense. RED: expected 20, actual 27.
   Убрано только второе прибавление. Реальный ApplyToItem → GrantArmorBenefits →
   UpdateAccessory проверен с hideVisual=false/true; MaxLife продолжает применяться.
   Броневой overload уже не дублировал защиту и не менялся.

3. `Common/Players/InfiniCraftPlayer.Mobility.cs`, movement aggregation:
   промежуточный clamp делал результат зависимым от порядка ускорений/замедлений.
   RED: moveSpeed expected 3, actual 2.5 для вкладов 1, 1.5, -0.5 и базы 1.
   Ограничение перенесено на итоговую сумму, прежние пределы сохранены.

4. Там же, mining aggregation:
   промежуточный clamp произведения искажал сочетание множителей по той же причине.
   RED: pickSpeed expected 1, actual 1.5 для множителей 2, 3, 0.5 и базы 3.
   Ограничение перенесено на итоговое произведение. Семантика применения
   к Player.pickSpeed не менялась. Обе регрессии проверяют все перестановки
   трёх различных эффектов; дополнительные контроли проверяют верхний/нижний cap,
   refresh без двойного стека и независимое истечение разных эффектов.

5. `Common/Players/GeneratedEquipOverlayDrawLayer.cs`, `CollectVisibleOverlays`:
   hideVisibleAccessory индексировался порядковым номером аксессуара 0..6,
   хотя Terraria использует соответствующий индекс armor 3..9.
   RED: скрытый slot 3 оставался в коллекции (expected 0, actual 1).
   Исправлен только индекс флага. Проверены все функциональные позиции,
   обычная видимость и чужой hide-флаг. GPU/draw/shader acceptance не выполнялась.

6. `Content/Items/InfiniCore.cs`, right-click consumption:
   ключ станции разрешал правый клик, но наследовал ConsumeItem=true.
   В установленной tModLoader `ItemLoader.RightClick` после hook вызывает
   ConsumeItem и уменьшает stack независимо от Item.consumable.
   RED: реальный ItemLoader.ConsumeItem возвращал true при ожидаемом false.
   Добавлен ConsumeItem=false; CanRightClick остаётся true.
   Проверен loader consumption gate, не полный UI/right-click lifecycle.

7. `Common/Players/GeneratedHeldItemDrawLayer.cs`, remote held pose:
   при несовпадении выбранного слота после grace-периода helper возвращал false,
   но оставлял отвергнутый payload в out-параметре. Draw игнорирует bool и мог
   использовать эту позу. RED: после отказа out всё ещё содержал пакет.
   В этой ветке теперь очищается out без преждевременного удаления cached packet.
   Регрессия проходит через настоящий binary packet decoder; проверяет grace,
   отказ при несовпадении, допустимый слот и истечение TTL. Clock/netMode/myPlayer
   восстанавливаются, cache очищается. Это не сетевой матч и не GPU draw test.

8. `Common/VFX/InfiniVfxRuntime.cs` и `InfiniItemVfxRuntime.cs`, lightCue:
   клиентский PresentationLightMultiplier не читался активными исполнителями.
   При нуле в настройке настоящий Terraria LightingEngine всё ещё получал источник
   света (RED: expected 0, actual 1). Теперь VFX-интенсивность умножается на
   клиентскую настройку после прежнего clamp; нулевой свет вообще не ставится в очередь.
   Проверены 1 / 0 / 0.5 через реальный Lighting.AddLight → LightingEngine:
   projectile periodic, hit, detached event, item periodic/use. Цвет и координаты
   не подбираются заново; manifest не меняется. Отдельный gameplay-свет экипировки
   специально проверен на неизменность. Это CPU light queue, не GPU light propagation.

9. `Common/VFX/InfiniItemVfxRuntime.cs`, periodic seed arithmetic:
   VfxManifestSpec JSON round trip принимает и сохраняет int.MinValue в SlotSeed,
   но Math.Abs(int.MinValue) выбрасывал OverflowException из OnPeriodic.
   Вычисление модуля расширено до long без изменения serialized seed и существующей
   фазовой семантики. Проверены 0, ±1 и обе границы int: один световой импульс за
   полный период. Важно: штатный Python _seed выдаёт только неотрицательные числа;
   это исправление принятой C#-границы, не доказательство такого сбоя обычной генерации.

10. `Common/Services/GeneratorClient.cs`, WithCacheOnlyFlag:
   строковая склейка превращала пустой JSON-объект в `{,"cacheOnly":true}`,
   добавляла второй cacheOnly при существующем флаге, а не-объект молча заменяла
   другим запросом. RED воспроизведён на `{}`. Теперь меняется JSON-объект;
   cacheOnly единственный и равен true, неверная форма отклоняется.
   Проверены вложенные поля, Unicode/скобки в строках, уже заданный флаг,
   большие целые и длинные десятичные литералы без преобразования через double.
   Это локальный transform, не HTTP/cache endpoint acceptance.

11. Там же, IsDeliverableGeneratedData / Normalize:
   ответ с пустым ID проходил delivery gate, после чего получал случайный ID.
   RED: реальный GeneratedItemData JSON round trip → gate принимал пустой ID.
   Gate теперь отвергает пустой/пробельный ID; генерация случайной identity удалена.
   Проверены пустой, пробельный, placeholder и нормальный ID с сохранением значения.
   Проверка общая для cache-only и обычного ответа; сервер/модели не вызывались.

12. `Common/Models/RuntimeProgramSpec.cs`, entity count:
   MaxEntityCount ограничивался общим потолком, но не использовался проверкой
   Entities.Length. RED: JSON round trip → NormalizeAndValidate принимал две
   сущности при MaxEntityCount=1; остальные 21 проверки проходили.
   Теперь проверяется нормализованный Limits.MaxEntityCount. Это применение
   существующего технического лимита, не подбор механики или обрезка программы.
   Регрессия проверяет точные границы 1/2/engine cap, превышение на одну сущность,
   пустой массив, невозможность поднять engine cap через wire и сохранение IDs
   при повторной валидации. Штатный Python compiler задаёт общий максимум;
   это дефект принятой C#-границы, не воспроизведённый сбой обычной генерации.

13. `Common/Models/GeneratedItemData.Normalize.cs`, equipment ranges:
   семь C#-границ сужали допустимые значения configure_accessory/configure_armor.
   RED на настоящих hooks после FromJson → ApplyToItem: movementSpeed -0.9 → -0.5
   и 3 → 2 (accessory, armor, set bonus), accessory life/mana regen и set life regen
   200 → 120, accessory sentrySlots 20 → 10. Все предыдущие 22 проверки проходили.
   Исправлены только эти семь границ; нижняя граница regen -120 сохранена как была,
   а не попутно ужесточена до Author minimum -100. Формулы Player не менялись.
   Реальный Python validator/compiler отдельно принял все 14 min/max случаев
   из registry и сохранил значения точно: `/tmp/icl-equipment-compiler-probe.py`,
   `/tmp/icl-engine-equipment-compiler.json`. C# regression проверяет границы,
   промежуточные и нулевые значения через UpdateAccessory/UpdateEquip/UpdateArmorSet,
   затем network JSON round trip; дополнительно — конечные caps и повторный Normalize.
   Input сериализуется до Normalize, иначе ToJson скрыл бы потерю значения.
   Это проверка реальных stat hooks, не полный armor-set loader/game-loop lifecycle.

14. `Common/Services/GeneratedAssetSyncService.cs`, late HTTP completion:
   Dispose очищал состояние, но не запрещал worker публиковать поздний результат.
   RED: loopback HTTP-сервер удерживал PNG body до Dispose, после чего файл всё-таки
   появлялся; некорректный ответ после Dispose заново добавлял KnownMissing entry.
   Добавлен disposed-флаг под общим lock: QueueDownloads больше не принимает работу,
   worker не обновляет late-result/retry state, CommitVerifiedAsset проверяет флаг
   атомарно с записью/rename. Нормальный живой сервис продолжает сохранять точные
   проверенные bytes и отмечать ошибки. Изменения только в этом production-файле.
   Regression использует настоящий DownloadOneAsync/HttpClient, временный loopback
   listener на случайном порту и barrier, а не sleep. Проверены active/disposed ×
   valid PNG / invalid PNG / отложенный HTTP 500; нет оставшихся .part, повторный
   Dispose безопасен, новые HTTP-загрузки после Dispose не запускаются.
   Стенд await-ит worker и server и удаляет только собственные sandbox-файлы.
   Это shutdown publication fence, НЕ отмена зависших reads, НЕ world-unload/MP/GPU
   acceptance и НЕ проверка ранее поставленных в очередь main-thread callbacks.

15. `Common/Runtime/RuntimeProgramExecutor.cs`, Pull mode/authority fallthrough:
   owner_to_target выбирался одним if вместе с наличием цели и owner authority.
   Если условие не выполнялось, исполнение продолжалось в NPC/area-pull ветке.
   RED: отсутствующая/неактивная цель двигала соседних NPC; на server mode даже
   активная прямая цель получала NPC-импульс вместо запрещённого owner-local эффекта.
   Выбор режима отделён от предусловий: owner_to_target всегда заканчивается return,
   импульс игроку выдаётся только при активной цели и правильной authority.
   Это сохранение authored mode, не выбор другого эффекта при недоступной цели.
   Regression вызывает настоящий ExecuteAction с Player/NPC и проверяет как
   нужного адресата, так и отсутствие движения остальных. Матрица охватывает три
   pull mode, SinglePlayer/Server/MultiplayerClient, local/remote owner, активность
   owner и active/inactive/absent target; target_to_owner/target_to_entity сохранены.
   Настоящая NPC eligibility проверена, Main.npc/netMode/myPlayer восстановлены.
   Это method-level authority proof, НЕ сетевой матч или NPC/world update loop.

16. `Common/Models/GeneratedItemData.Apply.cs`, signed accessory defense:
   configure_accessory допускает defense=-50..200; настоящий Python validator/compiler
   сохраняет -50, -1, 0, 7, 200. DTO также сохранял знак, но ApplyToItem обрезал
   отрицательные значения до нуля. RED на реальных Player.GrantArmorBenefits и
   GeneratedItem.UpdateAccessory: при базе 100, defense=-50 оставлял 100 вместо 50,
   defense=-1 — 100 вместо 99, независимо от hideVisual.
   Исправлена одна строка: Item.defense получает нормализованный Accessory.Defense
   без дополнительного нулевого floor. Класс изменения — Fix consumer projection:
   восстановлена точная передача authored значения, без нового дизайна или defaults.
   Vanilla по-прежнему единственный владелец начисления defense; armor bounds и
   остальные equipment hooks не менялись. Regression проверяет negative/zero/positive
   значения, обе видимости, повторный ApplyToItem и повторное применение после
   network JSON round trip. Это method-level stat proof, не тест фактического урона
   по игроку, инвентаря, сетевой доставки или полной экипировки в игре.

17. `GeneratedItemData.Normalize.cs` + `InfiniCraftPlayer.Mobility.cs`, blink range:
   move_player_on_use.rangeTiles допускает 0..120; Python validator/compiler сохраняет
   1, 80, 81, 100, 120. C# NormalizeGameplay и TryBlinkToTarget независимо обрезали
   дальность до 80. RED против настоящего Player.Teleport показал перемещение
   на 80 тайлов при заданных 81/100/120 — и на raw GameplaySpec, и после DTO/network
   round trip. Исправлены ровно два верхних предела: 80 → 120.
   Это Fix сужающей contract projection/execution, без нового mode или fallback.
   Новый `.Mobility.cs` тест проверяет близкую/далёкую цель, границу 120 и cap при 121,
   нулевой range, dead/inactive owner, unsafe world-edge destination и cooldown:
   успех расходует cooldown, отказ не двигает игрока и не расходует его.
   Наблюдаются фактический Player.Center и teleportTime=1 в конце реального Teleport:
   один bool недостаточен, т.к. vanilla Teleport содержит пустой catch.
   Headless fixture изолирует projectile/dust/pressure-plate/mouse/random state,
   читает пустой Tilemap без изменения tiles. SP authority используется с отдельным
   myPlayer, чтобы не заходить в camera/biome branch; GPU, game loop, реальный мир,
   server-intent transport, lava/solid-tile matrix и recall_home здесь не проверены.

18. `Common/Runtime/RuntimeDelayedActionScheduler.cs`, owner slot reuse:
   PendingAction хранил только OwnerId и брал текущий Main.player[OwnerId] в due tick.
   Настоящий Terraria.RemoteClient.Reset заменяет Player. RED использует этот Reset
   без сокета, затем активирует replacement в том же слоте: ранее queued pull начал
   тянуть NPC к новому игроку (velocity +2 вместо отсутствия эффекта).
   PendingAction теперь хранит исходный Player вместе с OwnerId; перед исполнением
   требуется ReferenceEquals текущего и исходного экземпляров. Класс — Fix exact
   owner identity, без выбора другого владельца или изменения authored action.
   Reference удерживается только ограниченной очередью до исполнения/снятия/clear;
   существующие queue/delay/per-tick caps не менялись. Это не cancellation по смерти
   исходного projectile: terminal event scheduling остаётся прежним.
   `.Events.cs` проверяет исполнение ровно на втором tick и единожды, inactive owner,
   replacement через реальный Reset, OnWorldUnload/Unload и отсутствие replay после
   восстановления исходного Player. Поля Main/NetMessage и очередь очищаются.
   Это method-level server-role proof с активацией нового слота тестом, НЕ сетевой
   handshake/reconnect или матч; NPC slot reuse и reset объекта in-place не закрыты.

19. `Common/Runtime/RuntimeDelayedActionScheduler.cs`, direct NPC slot reuse:
   В установленном tModLoader обычный NPC.NewNPC создаёт новый NPC в свободном
   слоте, а не просто вызывает SetDefaults на старом экземпляре. Headless regression
   реально вызывает NewNPC → SetDefaults → OnSpawn, ставит delayed on_hit status,
   деактивирует цель и создаёт в том же слоте новый NPC того же/другого типа.
   RED: новый BlueSlime и Zombie получали чужой OnFire через настоящий NPC.AddBuff.
   PendingAction теперь сохраняет Target; NPC доступен как directTarget только при
   совпадении slot + instance + active. Класс — Fix exact target identity.
   При потере цели передаётся null, как при обычной неактивной цели, а не отменяются
   все события: сохранённая позиция и существующие правила area/owner действий
   не менялись. Их сочетания после утраты цели отдельно не объявляются проверенными.
   Regression сохраняет применение к исходной цели с duration=90 на втором tick,
   отсутствие раннего/повторного применения, inactive/absent target; NPC-массив,
   player slot, netMode, random и world flag восстанавливаются. Первый fixture
   использовал Poisoned, но настоящий BlueSlime иммунен: это исправление тестовых
   данных, не найденный баг. Подтверждающий RED — отдельный red-status log с OnFire.
   В owner regression source event уточнён до registry-valid on_hit вместо on_kill;
   production owner fix не менялся. Полный hit/game loop/MP и in-place Transform/
   SetDefaults остаются за пределами этой проверки.

20. `Common/Models/GeneratedItemData.cs`, player-save reference version boundary:
   FromPlayerSaveJson принимал {} и отсутствие infiniSaveKind/version/runtimeApiVersion
   за счёт DTO defaults; явные integer version=0/4/6/-1/int.MaxValue также принимались,
   поскольку Version не проверялся. Это воспроизведено RED на каноническом parser.
   Три marker-поля теперь имеют JsonRequired; Version проверяется на CurrentSchemaVersion.
   Класс — Fix strict format validation, без миграции, угадывания версии или нового
   содержимого предмета. Формат корректного writer output остался прежним.
   `.Contract.cs` вызывает настоящие GeneratedItem.SaveData/LoadData с TagCompound:
   identity, recipe, name и world scope сохранены, повторно сохранённый JSON точен,
   исходная definition не мутируется; reference-only предмет не получает gameplay.
   Malformed/missing markers и wrong/null/type-invalid version отвергаются с diagnostic;
   LoadData оставляет существующий inert corrupt_reference, успешный parse очищает
   только соответствующий diagnostic. Missing identity/world-scope policy не менялась.
   Это hook/DTO proof, НЕ запись/чтение .plr, ItemIO/TagIO binary transport, registry
   hydration или multiplayer NetReceive lifecycle.

21. `RuntimeProgramExecutor` + immediate/delayed callers, event damage source:
   registry damage_area_on_event/chain_damage_on_event определяет multiplier от
   authored damage entity-владельца события. Executor ошибочно всегда использовал
   Gameplay.Damage/DamageClass предмета, теряя источник при dispatch и задержке.
   Compiler probe через настоящий canonical validator/compiler сохраняет разные
   значения: item 20/melee, projectile 100/magic, multiplier 0.5 (обе capabilities).
   RED: в настоящем OnHitNPC → ApplyDamageToNPC → StrikeNPC NPC имел 999 HP вместо
   контрольных 970 HP. Контроль использует реальный Terraria API с 50 magic damage,
   defense=80 и magic armor penetration=40, а не переписанную формулу урона.
   Fix: обязательный sourceEntity передаётся из item/projectile callers в executor
   и сохраняется в PendingAction. ItemBody читает свою каноническую Gameplay
   projection, остальные authored entities — собственный Damage component.
   Никаких name/category lookup, выбора primary entity, fallback или изменения wire.
   Регрессия `.Events.cs` вызывает настоящие GeneratedItem/GeneratedProjectile.OnHitNPC:
   item/projectile × AoE/chain × on_hit/on_crit × immediate/delay=2; прямой target
   и дальний NPC не задеты, отсутствуют раннее исполнение и повтор после retirement.
   Projectile.damage=777 и damageDone=333 намеренно не равны authored 100; после
   постановки delayed action projectile становится inactive с damage=1, но эффект
   сохраняет authored источник. Runtime damage modifiers не используются как база.
   Headless fixture изолирует SceneMetrics для vanilla banner checks; HideStrikeDamage
   отключает только combat-text/DPS presentation, NPC действительно теряет HP.
   RED 31/1 → GREEN 32/0. Terminal hook proof добавлен отдельным продолжением ниже.
   Это не world/game loop, client-server match либо сторонние modded DamageClass hooks.
   Compiler evidence: `/tmp/icl-event-damage-compiler-probe.py`,
   `/tmp/icl-event-damage-compiler-results.json`.

22. `GeneratorClient.CraftIdentityItem`, request-only prefix normalization:
   Prefix(0) в установленной Terraria немедленно возвращает false, не сбрасывая
   поля. Generated branch сохранял reforge, хотя Prepare объявлял
   base_item_stats_ignore_prefixes / prefixIgnored. RED через настоящий Prepare:
   при authored damage=100 Legendary отправлял 115, Broken — 70; Zealous менял
   rarity 0 → 1. Непрефиксный контроль проходит; ошибка относится к payload,
   исходные предметы и подготовленные refund-копии сохраняли свой reforge.
   Исправление: Item.Clone → CloneDefaults(item.type) → existing.ApplyToItem → stack.
   CloneDefaults сбрасывает stat fields, сохраняя ModItem identity клона;
   явная canonical definition восстанавливает authored значения поверх defaults.
   Это реализация уже объявленной request-only Normalization, не новая механика.
   ResetPrefix не используется: его Refresh проходит через ItemIO/NetReceive
   и может повторно загружать reference-only definition.
   Также удалён catch-fallback, возвращавший исходные prefixed stats после ошибки
   SetDefaults. Отдельный RED подтвердил реальный IndexOutOfRangeException на
   недопустимом type, который прежде скрывался. Теперь preparation отказывает,
   source остаётся нетронутым. Station/MultiDev catch вызывает RefundOne;
   server catch сообщает prepare_failed и оставляет inputs в station — это
   source-read подтверждение обработки, не выполненный end-to-end refund.
   `.Client.cs` проверяет Prepare для обеих сторон A/B: 0/Legendary/Broken/Zealous,
   поля payload, prefix diagnostics, crit/scale request-копии, исходные stats/stack/
   favorite/definition и RefundA/RefundB (stack=1, исходный prefix и definition).
   Есть vanilla default control, null/air и ошибка defaults. LoadData создаёт
   настоящий save-only host с damage=0: переданный helper-у resolved canonical
   argument восстанавливает request damage=100 без гидрации/мутации original host.
   SourceMode=test_fixture явно обходит asset delivery; графика/PNG не проверяются.
   GeneratedItem hooks привязаны к vanilla-allocated host type: полноценная
   ModLoader content registration, real registry lookup, сторонние GlobalItem/
   custom-prefix hooks, UI reforge, HTTP generator и physical refund НЕ проверены.
   RED 32/2 → GREEN 34/0. Логи: `/tmp/icl-engine-prefix-red.log`,
   `/tmp/icl-engine-prefix-green.log`, `/tmp/icl-engine-prefix-pytest.log`.

23. `GeneratorClient.FindPlayerAmmoCandidates`, generated inventory ammo context:
   вызов CraftIdentityItem(ammo) не передавал GeneratedItem.Data и строил defaults
   общего proxy type вместо authored instance. RED: два экземпляра одного host type
   с damage=120 и 210 превращались в одинаковые damage=5 (vanilla host defaults
   в headless fixture). Исправлена ровно передача definition из конкретного ModItem;
   vanilla продолжает идти с existing=null. Это Fix потери полного существующего
   instance-контекста, не новый selector, fallback или механика боеприпасов.
   Регрессия `.Client.cs` проходит через настоящие ApplyToItem / Item.Clone /
   CloneDefaults / FindPlayerAmmoCandidates / AmmoItemRawSnapshot; разные экземпляры
   стоят в слотах 4 и 54, vanilla control — 55. Лимиты 1/3 и порядок сохранены.
   Проверены damage, DamageClass, ammo category, projectile ID, shootSpeed, knockback,
   maxStack, stack, имя/slot в raw snapshot и точная per-instance definition identity.
   JSON snapshot исходных stats и definitions подтверждает отсутствие мутации;
   source quantity/favorite сохраняются. Не-ammo, другая категория и действительно
   inert save-only host не попадают в список; null player и AmmoID.None дают пустой.
   Сканирование исполняется на реальном Player.inventory, но GeneratedItem прикреплён
   к vanilla-allocated host type; full ModLoader registration не запускалась.
   Это context-extraction proof, НЕ Player.PickAmmo, Shoot, consume-ammo hooks,
   representative fallback scan, полный Prepare/HTTP/model или multiplayer матч.
   RED 34/1 → GREEN 35/0. Логи: `/tmp/icl-engine-ammo-red.log`,
   `/tmp/icl-engine-ammo-green.log`, `/tmp/icl-engine-ammo-pytest.log`.

24. Диагностика `ApplyToItem → LastAppliedTrace → /infiniitem trace`:
   regression воспроизвела пустой snapshot после успешного применения (35/1).
   Старый BuildAppliedTrace читал authored Gameplay вместо финального Item;
   RecordAppliedItemTrace был невызванным JSON-writer в Debug. Вместо подключения
   этого writer добавлен приватный StampAppliedTrace(Item) в конце ApplyToItem:
   компактный текст читает итоговые поля Item, включая passive damage/useStyle,
   signed defense и фактический DamageClass. Невызванный JSON writer удалён.
   Snapshot остаётся в существующем [JsonIgnore]-поле на definition, а не в Debug.
   Команда явно описывает его как последнюю проекцию, не live stats после hooks/
   prefix и не гарантированный per-Item журнал при совместном использовании DTO.
   Реальные ApplyToItem/ToJson/ToNetworkJson/ToPlayerSaveJson/ComputeDefinitionHash
   проверены на обычной и passive accessory definition. Проверены все выводимые
   Item-поля, authored damage=37 против passive Item.damage=0, повторное применение,
   неизменность JSON/save/hash, отсутствие snapshot после network round-trip,
   сохранение старого снимка при поздней мутации Item/DTO и замена при новой проекции.
   GREEN: 36/0; Python offline: 319 passed. Логи `/tmp/icl-engine-trace-red.log`,
   `/tmp/icl-engine-trace-final.log`, `/tmp/icl-engine-trace-pytest.log`.
   Chat renderer/команда в игре не запускались. Hot path теперь строит ограниченный
   набор строк и считает события; JSON serialization/полного graph dump там нет,
   но стоимость аллокаций и frame-time под реальной нагрузкой не измерялась.

25. `ParticleSpawnMultiplier` не потреблялся активными Dust emitters:
   RED actual Dust counts при setting=0 оставались 10 (projectile/detached) и 8
   (item-use/item-periodic); setting=0.5/2 также игнорировался. После RED 36/1
   добавлен общий ScaleParticleCount в существующий InfiniVfxClientOptions и
   подключён к двум emitter loops. Изменено только количество попыток spawn Dust
   после выбора light/sound/sprite веток; wire, authored density и бюджеты не менялись.
   Целая часть даёт точное количество, дробный остаток — Bernoulli округление
   через существующий Main.rand. Это не гарантирует точную долю в короткой серии;
   предотвращает постоянное округление singleton при 0.5 в 0 или 1. Целые результаты
   (включая default/zero) не расходуют дополнительный RNG; проверены clamp endpoints.
   Регрессия использует настоящие Dust.NewDustPerfect/NewDust и CPU LightingEngine,
   не графику. По декомпилированной Terraria.Dust настроены и восстановлены gameMenu,
   gamePaused/netMode, WorldGen.gen, viewport, maxDustToDraw, dust pool/dCount и RNG.
   Проверены 5 entry paths: projectile event/tick, detached, item use/periodic;
   setting 0/0.5/1/2, отдельные per-tick/total/zero caps для projectile/detached,
   независимый lightCue, spawn position, неизменные manifest JSON и projectile
   damage/velocity. В helper отдельно проверены fractional singleton и RNG parity.
   GREEN 37/0; Python offline 319 passed. Логи `/tmp/icl-engine-particles-red.log`,
   `/tmp/icl-engine-particles-final.log`, `/tmp/icl-engine-particles-pytest.log`.
   Ограничения: это CPU allocation/emission, НЕ GPU particles/update/render, не
   multi-player/ParticleLibrary acceptance. Точные shapes при изменённой плотности
   не оценены визуально; дробная настройка меняет расход общего RNG. Manifest
   SpawnRateMultiplier, particle alpha, DrawBudgetMultiplier и screen culling
   не исправлялись. Item emitter по-прежнему не применяет manifest particle budget.

26. `DrawBudgetMultiplier` не потреблялся активным и detached SpendDraw:
   RED при authored budget=8 множители 0.25/0.5 разрешали лишние вызовы после
   ожидаемых 2/4, а 2.0 отклонял девятый вместо allowance=16. Проверены реальные
   private SpendDraw методы канонического кода через reflection, не новая формула
   учёта в harness. После RED 37/1 общий EffectiveDrawBudget подключён к обеим
   точкам проверки: floor(authoredBudget * client setting), потолок 512; authored
   значение не изменяется. Нулевой бюджет остаётся нулём. Значения выше 1 повышают
   именно клиентский allowance по назначению опции, но не engine ceiling.
   Дополнительно проверены 7*0.5→3, 1*0.25→0, clamp настройки к 0.25..2, точные
   границы и повторный отказ, atomic rejection cost=2 при одном оставшемся draw,
   общий detached SourceKey между слоями и независимость другого SourceKey.
   Manifest JSON и stored detached MaxDrawCalls сохраняются без изменения.
   GREEN 38/0; Python offline 319 passed. Логи `/tmp/icl-engine-draw-red.log`,
   `/tmp/icl-engine-draw-final.log`, `/tmp/icl-engine-draw-pytest.log`.
   Scope: budget bookkeeping, НЕ SpriteBatch/GPU rendering или frame-rate perf.
   Fake texture filenames в Enqueue не открываются; DrawLayer не запускался.
   Сброс active/detached счётчиков по GameUpdateCount vs реальным draw frames
   не проверен и не исправлен; частоту config lookup под нагрузкой не измеряли.

27. Draw budget lifecycle ошибочно зависел от GameUpdateCount:
   active DrawCallsThisFrame сбрасывался в BeginWorldTick, detached reset сравнивал
   тот же simulation clock. Повторный draw без нового tick оставался без allowance.
   RED 38/1 подтвердил оба пути, включая повторный настоящий BeginDrawBudgetFrame
   с неизменным clock. Исправление: active reset один раз после hydration в PreDraw,
   detached reset один раз при входе в DrawProjectiles wrapper. Удалён tick-based
   draw reset; under/over layers разделяют allowance, particle budget остаётся tick-based.
   Headless test вызывает канонический PreDraw с no_asset/empty VFX и настоящий
   detached wrapper с пустой draw queue и orig-callback observer. Запись бюджета
   создана реальным Enqueue; SpendDraw вызывается на сохранённой записи. Это не
   mock GPU render и не запуск оригинального vanilla DrawProjectiles.
   Проверены три draw invocations при frozen clock, отказ повторного расхода,
   отсутствие reset после over-pass, неизменность active/detached particle counters
   при draw reset, восстановление particle tick budget только новым tick и
   сохранение total cap. GREEN 39/0; Python offline 319 passed.
   Логи `/tmp/icl-engine-draw-frame-red-final.log`,
   `/tmp/icl-engine-draw-frame-final.log`, `/tmp/icl-engine-draw-frame-pytest.log`.
   Остаточный отдельный риск: по реальному Terraria.Main.DrawProjectiles
   (декомпиляция `/tmp/icl-main-runtime.cs`, 21652..21692) vanilla сам делает
   SpriteBatch.Begin/End. Detached wrapper вызывает DrawLayer вокруг этого метода,
   а DrawLayer вызывает SpriteBatch.Draw без собственного Begin/End. Runtime
   воспроизведение batch-state ошибки не выполнялось в budget lifecycle pass;
   этот риск затем подтверждён и исправлен отдельно в п. 28. GPU, camera/capture passes и frame pacing
   не проверены; per-invocation reset не объявляется полной графической приёмкой.

28. Последний согласованный дефект: detached DrawLayer нарушал SpriteBatch lifecycle.
   Настоящий FNA SpriteBatch.Draw бросал InvalidOperationException: "Draw was called,
   but Begin has not yet been called" из канонического DrawLayer. Vanilla
   DrawProjectiles делает собственные Begin/End внутри метода, а detached wrapper
   рисовал до и после него. RED 39/1 получен на реальном FNA CheckBegin, не на stub.
   Fix локален в DrawLayer: ленивый Begin перед первым разрешённым draw, world
   transformation matrix, AlphaBlend/DefaultSamplerState/DepthStencil.None и
   Main.Rasterizer, End в finally только если Begin успешно завершился. Пустой,
   unmatched, missing-texture и zero-budget слой не открывают batch. Исключения
   не скрываются; неудачный Begin не закрывает чужой уже открытый batch.
   Регрессия исполняет реальные FNA Begin/Draw/End и CPU vertex queue. SpriteBatch
   и Texture2D — CPU-only shells через GetUninitializedObject с инициализированными
   буферами/размерами, без GraphicsDevice; finalizers отключены для этих shells.
   Только GPU-bound FlushBatch заменён scoped RuntimeDetour observer/drain.
   RuntimeSpriteCache использует реальную cache-hit ветку с CPU texture; только
   exception-case временно перехватывает второй TryGet и бросает fixture exception.
   Проверены отдельные under/vanilla/over queues (1/0/1), исходный callback один раз,
   world transform/blend/sampler, закрытие batch после partial draw и возможность
   следующего Begin, no flush на missing texture/zero budget, foreign-batch ownership.
   Hooks, static cache, viewport/view и SpriteBatch восстановлены в cleanup.
   GREEN 40/0; Python offline 319 passed. Логи `/tmp/icl-engine-batch-red.log`,
   `/tmp/icl-engine-batch-final.log`, `/tmp/icl-engine-batch-pytest.log`.
   Это доказательство FNA batch protocol/CPU queuing, не GPU upload/render,
   image-quality, full vanilla renderer или camera/capture acceptance.
   По просьбе пользователя аудит остановлен после этого исправления; дальнейшие
   открытые области ниже — ограничения, не поручение продолжать автоматически.

## Дополнительная проверка scheduler без production-изменений

- Реальный NPC.Transform(BlueSlime → Zombie) сохраняет instance/slot и active state.
  Delayed on_hit status продолжает действовать на эту же сущность после смены type:
  длительность 90, исполнение на втором tick, отсутствие повторного refresh.
  Это положительный контроль к rejection нового NPC в том же слоте; отмена по type
  была бы неверной для проверенного transformation. Полный player roster изолирован
  для vanilla TargetClosest, затем восстановлен.
- Очередь принимает ровно MaxPendingRuntimeActions=256 записей, overflow отклоняется.
  В due ticks реальные NPC-импульсы подтверждают MaxRuntimeDelayedActionsPerTick=64,
  отсутствие раннего исполнения, потерь и повторного запуска после drain.
- Full-queue rejection не расходует spawn budget. Reservation-only probe с бюджетом
  5 и count=3 резервирует сначала 3, затем оставшиеся 2; третья заявка отвергается.
  OnWorldUnload удаляет reservations: после него снова доступна полная capacity.
  Spawn probe намеренно проверяет только резервирование в scheduler, не создаёт
  projectile и не доказывает исполнение spawn/child-depth/asset/controller pipeline.
- Новых дефектов в этих проверенных случаях не найдено; изменены только тесты/docs.

## Terminal event damage: продолжение без production-изменений

Расширен существующий EventDamageUsesAuthoredSource без второго тестового движка
и копирования формул: **30 сценариев** проходят через канонические mod hooks и
настоящие Player.ApplyDamageToNPC / NPC.StrikeNPC в tModLoader 2026.6.3.6.

- Сохранены item/projectile, AoE/chain, on_hit/on_crit и immediate/delay=2 контроли.
- Для projectile AoE дополнительно вызван OnKill с timeLeft=0/1/10:
  on_expire действует при 0/1, но не при раннем уничтожении с 10;
  on_kill действует и после истечения, и при раннем уничтожении.
- Реальные GeneratedProjectile.AI при timeLeft=2 и затем 1, после которых вызывается
  OnKill(0), не дублируют on_expire damage/reservation. Отдельный on_kill после
  финального AI продолжает исполняться. Это последовательность mod hooks,
  НЕ вызов vanilla Projectile.Kill или автоматический game loop.
- Terminal AoE, в отличие от hit AoE, не имеет исключённой прямой цели: NPC в центре
  и соседний NPC получают ровно контрольный урон. Дальний NPC остаётся цел.
- После enqueue отложенного эффекта host деактивирован, его damage изменён на 1,
  а center перенесён к дальнему NPC. Scheduler сохраняет исходный центр и authored
  damage/class; до due tick урона нет, после исполнения очередь пуста и replay нет.
- Production-код не менялся: новых дефектов в этих случаях не воспроизведено.
  Эта исходная матрица не доказывала одновременные on_expire+on_kill;
  дополнительная проверка ниже закрывает их на том же method-level observer.
  Collision-driven kill, сторонние hooks, реальные сетевые strikes и GPU не проверены.

## Совместные terminal damage events без production-изменений

- Расширен существующий EventDamageUsesAuthoredSource, без копии damage формулы
  или отдельного тестового executor. Добавлены 24 сочетания одной entity с
  on_expire + on_kill: раннее уничтожение (10), expiry OnKill(0/1), final AI→OnKill,
  expire delay 0/2 и kill delay 0/2/4. Общая event damage matrix: 54 сценария.
- Различные множители 0.5/0.75 проверяют независимость действий: контрольные HP
  получают последовательными настоящими Player.ApplyDamageToNPC, с NPC defense
  и Magic armor penetration. На каждом tick наблюдаются центр и соседняя цель,
  дальняя цель и точное число pending actions; после due tick нет replay.
- Отдельная проверка сразу после final AI подтверждает исполнение/резервирование
  только on_expire до вызова OnKill. Раннее уничтожение не запускает on_expire,
  но сохраняет on_kill. Разные due ticks не сливаются и не исполняются раньше срока.
- Неактивный host переносится к дальней цели и получает damage=1; отложенные
  действия сохраняют исходный центр и authored source. Production-дефектов не найдено.
- Финальный лог `/tmp/icl-engine-terminal-pair-final.log`: 36 passed, 0 failed;
  DETAIL event damage scenarios passed=54. Игра/vanilla Projectile.Kill, collision,
  сетевые strikes и GPU не запускались. Это mod-hook sequence, не game-loop proof.

Лог: `/tmp/icl-engine-terminal-events.log` — DETAIL scenarios passed=30,
Engine runtime checks: 32 passed, 0 failed.

## Чем подтверждено

`tools/EngineRuntimeChecks.csproj` компилирует канонические исходники мода против
реальных tModLoader 2026.6.3.6 / FNA / ParticleLibrary / Luminance assemblies.
`tools/EngineRuntimeChecks.Player.cs`, `.World.cs`, `.Vfx.cs`, `.Client.cs`, `.Contract.cs`, `.Equipment.cs`, `.Assets.cs`, `.Events.cs` и `.Mobility.cs` расширяют исходный стенд;
это не переписанные в тестах формулы и не поддельные реализации Terraria.
Используются временный Program.SavePath и настоящие Player/Item/Projectile;
связи ModType и singleton тестовой регистрации восстанавливаются после проверки.

Последний запуск:

- Engine runtime checks: 40 passed, 0 failed.
- Python offline pytest: 319 passed in 13.87s.
- check_csharp_contracts.py: passed.
- check_project_hygiene.py: passed.
- git diff --check для затронутых engine production-файлов: passed.

Текущие логи: `/tmp/icl-engine-batch-red.log`, `/tmp/icl-engine-batch-final.log`,
`/tmp/icl-engine-batch-pytest.log`.
Предыдущий draw lifecycle pass: `/tmp/icl-engine-draw-frame-red-final.log`, `/tmp/icl-engine-draw-frame-final.log`,
`/tmp/icl-engine-draw-frame-pytest.log`.
Предыдущий draw multiplier pass: `/tmp/icl-engine-draw-red.log`, `/tmp/icl-engine-draw-final.log`,
`/tmp/icl-engine-draw-pytest.log`.
Предыдущий particle pass: `/tmp/icl-engine-particles-red.log`, `/tmp/icl-engine-particles-final.log`,
`/tmp/icl-engine-particles-pytest.log`.
Предыдущий terminal-pair C# лог: `/tmp/icl-engine-terminal-pair-final.log`.
Предыдущий trace pass: `/tmp/icl-engine-trace-red.log`, `/tmp/icl-engine-trace-final.log`,
`/tmp/icl-engine-trace-pytest.log`.
Предыдущий ammo pass: `/tmp/icl-engine-ammo-red.log`, `/tmp/icl-engine-ammo-green.log`,
`/tmp/icl-engine-ammo-pytest.log`.
Предыдущий prefix pass: `/tmp/icl-engine-prefix-red.log`, `/tmp/icl-engine-prefix-green.log`,
`/tmp/icl-engine-prefix-pytest.log`.
Предыдущие event checks: `/tmp/icl-engine-terminal-events.log`,
`/tmp/icl-engine-event-damage-red.log`, `/tmp/icl-engine-event-damage-green.log`.
Воспроизводимый C# запуск (пути зависимостей задаёт вызывающая среда):

```text
dotnet run --project tools/EngineRuntimeChecks.csproj --verbosity quiet   -p:InfiniTmlReferenceDir=<tModLoader-package/lib/net8.0>   -p:InfiniExternalDepsRoot=<ParticleLibrary-and-Luminance-root>
```

Это method-level headless проверки. Не запускались Terraria.Main/game loop,
загрузка .wld/.twld, графика, сетевой матч, HTTP generation endpoints.
Asset lifecycle test делает только локальные HTTP-запросы к своему loopback fixture;
реальный generator/asset server и внешняя сеть не используются.
Ранее обычная SDK-сборка была заблокирована отсутствующим
`tModLoaderDev/tModLoader.dll`; этот проход не объявляет её успешной.

## Что разобрано шире найденных багов

- Применение предмета и разделение vanilla/mod equipment effects.
- Активные utility buffs: aggregate, refresh, TTL; mobility authority и safe destination.
- Placement ledger: authorisation, commit, save/load, client/server packets, drop ownership.
- Station: единичный escrow, mouse slot 58, возврат в inventory;
  основная и дополнительные craft lanes, reconnect/replay, abort и durable backup.
- Registry: world filter, reference-only data, hydration dedupe, bounded decompression,
  definition hash, локальный атомарный persist.
- Asset delivery: native chunk ownership/hash, queue priority/dedupe,
  HTTP stream/commit и негативный texture cache. Дочитаны roster/cache descriptors,
  bundling и полный CPU PNG parser (CRC, IHDR/PLTE/IDAT/IEND, scanlines/Adam7).
  Parser не объявляется полностью проверенным: новый test покрывает обычный PNG
  и явно не-PNG body, не исчерпывающую матрицу PNG-форматов/повреждений.
- VFX: detached lifetime/budgets, equipment visibility и texture cache disposal.
  Новый CPU-test подтвердил cap очереди, удаление истёкшей записи при enqueue,
  per-source draw/particle caps, сохранение total cap между тиками, TTL неактивных
  budget entries и очистку всех трёх контейнеров при OnWorldUnload. Production
  detached-код не менялся. GPU draw и фактическая выгрузка мира не выполнялись.

- RuntimeProgramSpec: DTO/opcode validation, ownership/bindings, producer checks,
  cycle/depth validation, declared limits и loaded Terraria IDs. Новый исполняемый
  тест покрывает entity cardinality; остальные проверки не объявляются runtime PASS.
- InfiniDumpCommand / InfiniDumpPictureCommand: выбор данных, копирование файлов,
  экспорт TextureAssets, ограничение CPU texture metrics, HTML escaping и обработка
  ошибок прочитаны. Команды не запускались: GPU export и запись реальных дампов
  не проверены. У числового dump есть тихие per-entry catch, у picture dump —
  разрешение asset по basename и папки с точностью timestamp до секунды; последствия
  частичной выгрузки/коллизий отдельно не воспроизводились и не исправлялись.

- Завершено предметное чтение оставшихся RuntimeDelayedActionScheduler,
  RuntimeProgramExecutor и четырёх projectile partials: scheduling/budgets,
  event dispatch, movement/controller, collision hooks, binary ExtraAI/VFX sync.
  Этот шаг закрывает карту чтения всех исходных C#-файлов, но не все runtime-сценарии.

Чтение этих путей не означает, что для каждого есть исполняемый тест.
Старые projectile регрессии вновь запущены в составе общего C# стенда.

## Следующие непроверенные границы (не выдавать за найденные баги)

- Placement: реальная цепочка размещение → сохранение мира → перезагрузка →
  разрушение/взрыв → ровно один возврат, включая multi-tile и multiplayer ordering.
- Craft/escrow: потерянные ACK, reconnect с pending операцией, повторный requestId,
  полный inventory, исключение после появления результата, но до финального outcome.
- Asset lifetime: публикация file/retry state после Dispose воспроизведена и закрыта
  выше. Остаются зависшее тело после headers и освобождение HttpSlots, ранее
  поставленные main-thread callbacks, world switch без Dispose, stale descriptor/hash
  при перезаписи уже загруженной texture. Новая защита не отменяет сетевое чтение;
  она не даёт позднему результату записаться в disposed service.
- Presentation: vanity/functional precedence, locked/modded accessory slots,
  dye/gravity/rotation, actual draw passes, ресурсы GPU. Проверка hide-флага
  функциональных слотов не закрывает эти случаи.
- VFX wiring: ParticleSpawnMultiplier и DrawBudgetMultiplier подключены и проверены
  выше на CPU observers. EnableScreenCulling не читается активными исполнителями.
  ParticleAlphaMultiplier читается в VfxFoundation, но активный manifest runtime
  обходит этот backend. Исправление lightCue не закрывает эти настройки.
  Не подключать старый BestAvailable вслепую: VfxFoundation содержит автоматический
  fallback и цветовые selectors; это не lossless замена текущего runtime.
  Лимиты, GPU lifetime и очередь инициализации ParticleLibrary требуют отдельной
  проверки; прочтение registry не означает приёмку backend.
- Parent identity: request-only prefix normalization и подготовленные refund-копии
  проверены выше. Полная ModLoader registration, registry hydration, custom prefixes,
  GlobalItem hooks и фактический возврат inventory остаются непроверенными.
  Потеря definition в generated inventory ammo scan воспроизведена и исправлена
  выше. Фактические PickAmmo/Shoot/consumption, representative fallback scan,
  stale/malformed inventory entries и custom ammo hooks остаются непроверенными.
- Diagnostics: пустой/misleading applied snapshot исправлен и проверен на реальном
  Item/DTO/hash. Chat renderer и frame-time/allocation impact в игре не проверены.
- Client lifecycle: HTTP metadata probe удерживает lock до завершения запроса;
  переключение endpoint, late result после смены мира и concurrent recovery не
  покрыты новым JSON-тестом. Настоящий generator не вызывался; отдельный asset test
  использует только локальный HTTP fixture.
- Runtime: оставшиеся movement/collision/event combinations, multiplayer clone/
  rehydration и взаимодействие с другими модами.
- Event damage source: item/projectile immediate/delayed hit/crit и projectile
  terminal mod hooks закрыты выше. Реальный vanilla Projectile.Kill, collision-driven
  завершение, сетевые strikes и modded
  DamageClass hooks не проверены; method-level proof не является игровой приёмкой.
- Delayed identity: replacement через RemoteClient.Reset и NPC.NewNPC закрыт выше.
  In-place NPC.Transform подтверждён для BlueSlime → Zombie без отмены статуса.
  Произвольный modded in-place reset, Player in-place reset, полный reconnect и
  сочетания area/owner/spawn actions после утраты цели остаются непроверенными.
- Mobility follow-up: authored blink range и signed accessory defense воспроизведены
  и исправлены выше. Остаются safe destination для solid/lava, recall_home, packet
  intent/authority, camera/biome и полноценное use-item/world поведение.
- Player-save reference: обязательность markers/version и корректный hook round trip
  закрыты выше. Missing/blank/oversize identity, world-scope spoofing, реальная .plr
  persistence, binary transport и hydration остаются отдельными непроверенными границами.
- Карта предметного чтения закрыта; открытые поведенческие проверки выше остаются.

## Инвентаризация и фактическое покрытие

Статусы: `read` — предметное чтение файла в этом проходе, НЕ общий runtime PASS;
`partial` — только перечисленные диапазоны; `previous-pass` — просмотрен ранее,
часть методов покрыта прежними C# regression checks; `pending` — только учтён
в инвентаризации/компиляции, не считать просмотренным.

Всего C# source-файлов: 65. Статусы: partial=0, pending=0, previous-pass=0, read=65.
Список и число строк сверены программно с текущим деревом: пропусков и лишних
строк инвентаризации нет. Это покрытие чтением, не процент игровой приёмки.

| Файл относительно ModSources/InfiniCrafterLocal | Строк | Статус | Граница |
|---|---:|---|---|
| `Common/Commands/GetInfiniCommand.cs` | 38 | read |  |
| `Common/Commands/InfiniCacheCommand.cs` | 179 | read |  |
| `Common/Commands/InfiniCoreCommand.cs` | 20 | read |  |
| `Common/Commands/InfiniDummyCommand.cs` | 26 | read |  |
| `Common/Commands/InfiniDumpCommand.cs` | 463 | read | GPU/file export not run |
| `Common/Commands/InfiniDumpPictureCommand.cs` | 983 | read | GPU/file export not run |
| `Common/Commands/InfiniItemCommand.cs` | 94 | read |  |
| `Common/Commands/MultiDevCraftCommand.cs` | 69 | read |  |
| `Common/Config/InfiniGameplayQolConfig.cs` | 44 | read |  |
| `Common/Config/InfiniVfxClientConfig.cs` | 47 | read |  |
| `Common/InfiniNetPacketIds.cs` | 27 | read |  |
| `Common/InfiniRuntimeLimits.cs` | 29 | read |  |
| `Common/InfiniTerrariaSentinels.cs` | 21 | read |  |
| `Common/Models/ContractJsonDiagnostics.cs` | 86 | read |  |
| `Common/Models/GeneratedItemData.Apply.cs` | 149 | read |  |
| `Common/Models/GeneratedItemData.Debug.cs` | 34 | read |  |
| `Common/Models/GeneratedItemData.Model.cs` | 433 | read | DTO fields and effect predicates |
| `Common/Models/GeneratedItemData.Normalize.cs` | 299 | read | equipment-range hook regression; remaining validators read-only |
| `Common/Models/GeneratedItemData.cs` | 283 | read | save reference markers/version + hook round trip; full save/hydration not run |
| `Common/Models/RuntimeProgramSpec.cs` | 964 | read | entity count regression; other validation read-only |
| `Common/Models/TerrariaRuntimeVocabulary.cs` | 168 | read |  |
| `Common/Models/VfxManifestSpec.cs` | 322 | read |  |
| `Common/Players/GeneratedEquipOverlayDrawLayer.cs` | 241 | read |  |
| `Common/Players/GeneratedHeldItemDrawLayer.cs` | 459 | read |  |
| `Common/Players/GeneratedWhipTagGlobalNPC.cs` | 71 | read |  |
| `Common/Players/InfiniCraftPlayer.CraftState.cs` | 742 | read |  |
| `Common/Players/InfiniCraftPlayer.Mobility.cs` | 377 | read |  |
| `Common/Players/InfiniCraftPlayer.MultiDev.cs` | 448 | read |  |
| `Common/Players/InfiniCraftPlayer.Multiplayer.cs` | 1331 | read |  |
| `Common/Players/InfiniCraftPlayer.Station.cs` | 295 | read |  |
| `Common/Players/InfiniCraftPlayer.cs` | 236 | read |  |
| `Common/Runtime/RuntimeDelayedActionScheduler.cs` | 138 | read | owner/NPC replacement/timing/unload regressions; in-place lifecycle and full MP open |
| `Common/Runtime/RuntimeProgramExecutor.cs` | 205 | read | pull mode/authority + authored damage/class regression; full MP open |
| `Common/Services/GeneratedAssetSyncService.cs` | 1364 | read | loopback HTTP disposal regression; full MP/GPU and PNG matrix not run |
| `Common/Services/GeneratedItemRegistryService.cs` | 783 | read |  |
| `Common/Services/GeneratedTransferSystem.cs` | 11 | read |  |
| `Common/Services/GeneratorClient.cs` | 1306 | read | prefix + inventory ammo context regressions; full mod registration/MP open |
| `Common/Services/InfiniRuntimeAuthority.cs` | 59 | read |  |
| `Common/Services/LocalHttpQuietFailure.cs` | 113 | read |  |
| `Common/Services/RuntimeSpriteCache.cs` | 446 | read |  |
| `Common/Systems/GeneratedPlacementLedgerSystem.cs` | 700 | read |  |
| `Common/Systems/GeneratedStationEscrowStateSystem.cs` | 291 | read |  |
| `Common/Systems/InfiniAgentContractSelfTestSystem.cs` | 289 | read |  |
| `Common/Systems/InfiniCraftWorldExitSystem.cs` | 41 | read |  |
| `Common/UI/InfiniCraftStationUISystem.cs` | 268 | read |  |
| `Common/VFX/InfiniDetachedVfxSystem.cs` | 221 | read |  |
| `Common/VFX/InfiniItemVfxRuntime.cs` | 117 | read |  |
| `Common/VFX/InfiniVfxClientOptions.cs` | 64 | read |  |
| `Common/VFX/InfiniVfxRuntime.cs` | 335 | read |  |
| `Common/VFX/RuntimeColorPolicy.cs` | 52 | read |  |
| `Common/VFX/VfxCanonicalVocabulary.cs` | 36 | read |  |
| `Common/VFX/VfxFoundation.cs` | 561 | read |  |
| `Common/VFX/VfxParticleAddress.cs` | 60 | read |  |
| `Common/VFX/VfxParticleSystemRegistry.cs` | 174 | read |  |
| `Common/VFX/VfxRendererRegistry.cs` | 66 | read |  |
| `Content/Items/GeneratedArmorItems.cs` | 60 | read |  |
| `Content/Items/GeneratedItem.UseStyle.cs` | 20 | read |  |
| `Content/Items/GeneratedItem.cs` | 599 | read |  |
| `Content/Items/InfiniCore.cs` | 56 | read |  |
| `Content/Projectiles/GeneratedProjectile.Executors.cs` | 462 | read | remaining movement/controller combinations not verified |
| `Content/Projectiles/GeneratedProjectile.NetSync.cs` | 203 | read | binary parsing read; full multiplayer not run |
| `Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs` | 173 | read | hit/crit + terminal AI/OnKill damage regression; vanilla kill/collision/MP open |
| `Content/Projectiles/GeneratedProjectile.Visuals.cs` | 58 | read |  |
| `Content/Projectiles/GeneratedProjectile.cs` | 310 | read | existing Configure/hydration regressions rerun |
| `InfiniCrafterLocal.cs` | 146 | read |  |
