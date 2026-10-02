# VFX material elements — активный контракт 0.4.246

Контракт расширяет существующие `vfxManifest.slots`, а не вводит weapon presets, classifier, VM, shader generation, второй effect graph или четвёртую текстовую LLM-роль. Художественное качество реальной генерации не следует из DTO/CPU/native fixtures.

<a id="owners"></a>
## Владельцы и handoff

`Gameplay Author → Visual Director → VFX Director → image generation → strict delivery → C#`.

VFX Director и VFX Repair получают `acceptedRuntimeProgramReadOnly`: точную копию принятого runtimeProgram без per-entity `visual` (отдельный Visual context уже передаётся). Не создаётся второй механический контракт и не выводятся траектории из описания. Числа, entity IDs, движения, controllers, collision, события и bindings не меняются этим handoff.

VFX владеет своими image requests и временно-пространственной композицией. Он не меняет внешний вид основного предмета, gameplay, коллизии, урон или события. Image backend выполняет принятые запросы через существующий ограниченный generation gate; никакой скрытой смены backend/provider или подмены отсутствующего изображения.

Лимит ответа VFX Director и его условного Repair по умолчанию — 8000 токенов (`INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS`). Явная настройка пользователя сохраняет приоритет; новая LLM-роль или дополнительные Repair-попытки не добавляются.

Источники: [VFX owner](../LocalGenerator/infini_local/core/vfx_manifest.py) — schema/surface/diagnostics/Repair; [material payloads](../LocalGenerator/infini_local/core/vfx_material_contract.py) — поля и нейтрали; [C# DTO](../ModSources/InfiniCrafterLocal/Common/Models/VfxManifestSpec.cs) и [material executor](../ModSources/InfiniCrafterLocal/Common/VFX/InfiniDetachedVfxSystem.Materials.cs). Image/byte/texture ownership вынесен в [жизненный цикл ассетов](IMAGE_ASSET_LIFECYCLE_RU.md).

<a id="assets"></a>
## Ингредиенты и selectors

`rendererKind=spriteElement` требует только payload `element`; `texturedPath` — только `path`. Legacy renderers не принимают эти payload. Material renderers не используют channel `light`/`sound`; renderer/event/entity applicability задаётся accepted surface, не независимым декартовым произведением enum.

Optional `assets` в Director/manifest содержит до четырёх самостоятельных ингредиентов. Отсутствие означает отсутствие новых запросов и остаётся отсутствием в старом wire; явный null не является отсутствием.

У каждого запроса обязательны:

- `id`: точный безопасный идентификатор `[A-Za-z0-9_-]{1,48}`;
- `prompt`, `negativePrompt`;
- `canvasSize`: 16, 24, 32, 48, 64, 96 или 128;
- `layout`: `cutout` или `strip`.

`cutout` — отдельный объект с мягкой alpha и обычным вписыванием. `strip` — полный frame для UV-текстуры: keying/resize не должны менять его смысл bbox-crop, вращением, центрированием или silhouette-refit. Это технический выбор обработки изображения, не classifier эффекта: оба layout можно явно использовать в обоих новых renderers.

Одна декларация даёт одну image job; несколько слотов могут ссылаться на тот же ID. Дубликаты, dangling references и неиспользованные новые requests не принимаются. Runtime path/URL/status/score пишет image pipeline, не LLM. Серверные descriptors/PNG hashes и передача остаются у существующего AssetSync.

Texture selector обоих payload — `{source, assetId}`: `source=item|entity|impact|asset`, `assetId=""` для первых трёх; `asset` требует exact declared ID. Пути/URL модель не авторит. `entity` требует принятую `baked_sprite|reuse_item_icon` image role, `impact` — same-entity `impactSprite` producer; `no_asset|runtime_geometry` не является незагруженным PNG. Все producer/dependency правила и различие fresh/cache/network admission — [единая PNG projection](IMAGE_ASSET_LIFECYCLE_RU.md#dependencies).

<a id="element"></a>
## SpriteElement: время, привязка, движение

- `attachment=world`: положение/направление захватывается в момент события; собственное движение дальше независимо от источника.
- `attachment=source`: локальное состояние преобразуется текущим forward/normal того же живого источника; при его исчезновении эффект заканчивается, не перепривязывается к переиспользованному slot и не превращается автоматически в world effect.
- Терминальные `on_expire`/`on_kill` не допускают source attachment.
- Count, source-local offset, диапазон начальной скорости, полный угол конуса, наследование скорости, drag, ускорение X/Y, начальный угол и spin выбирает модель.
- Для новых элементов наследуемая engine velocity сначала переводится в pixels/world tick: текущая `Projectile.velocity * (1 + extraUpdates)` либо неизменная `Player.velocity`. Коэффициент применяется один раз. Это не измеренное перемещение anchor (controller может использовать velocity как steering). Значение захватывается до retirement и сохраняется в сетевом snapshot; старый Dust/raw-velocity путь не переопределяется.
- При world attachment ускорение X/Y задано в мировых осях; при source attachment — в локальных осях источника.
- `widthPx` и `heightPx` независимы; texture axes используются буквально, без PCA-переориентации новой картинки.
- `duration` — lifetime экземпляра; для nonperiodic `startTick` — задержка от события, `repeatEvery=0`.
- Для periodic `repeatEvery>=1` — world-tick cadence; startTick ограничивает projectile age. Item periodic использует startTick=0, поскольку per-Item activation clock не объявлен.
- Delayed world хранит исходные event facts и может сработать после смерти источника. Delayed source требует тот же живой generation/Item instance.

Повторные emissions могут намеренно перекрываться, но остаются в общих лимитах. Повторные визиты одного periodic hook не должны удваивать emission; отдельные hit/crit и expire/kill остаются отдельными событиями.

Два настоящих одноимённых события в одном tick (например, два попадания в разные точки) также различаются у новых веток: runtime/relay несёт техническую occurrence identity. Повтор того же occurrence подавляется. Историческое dedup-поведение старых renderers не расширяется молча. Live attachment требует конкретный Item/projectile generation; равенства definition ID или номера переиспользованного slot недостаточно. Item event snapshots тоже сохраняют положение/направление/скорость в момент события, а не восстанавливают их из текущего Player после получения пакета.

Все payload keys обязательны, конечны и явно authored. Полные ranges/schema остаются у `element_schema`, не у отдельного ручного реестра.

| Поля | Единицы / граница |
|---|---|
| `count` | integer 0..64 за emission; 0 — тишина; расход при emission, не Draw |
| `offsetForwardPx`, `offsetSidePx` | −128..128 px в captured forward/normal |
| `speedMinPxPerTick`, `speedMaxPxPerTick` | 0..24 px/world tick; max ≥ min |
| `spreadRadians` | 0..2π, полный угол конуса, не half-angle |
| `inheritVelocity` | 0..1 доля captured engine velocity после одного перевода в world-tick units |
| `drag` | 0..1 множитель сохранения скорости/world tick: 1 сохраняет, 0 обнуляет |
| `accelerationXPxPerTickSquared`, `accelerationYPxPerTickSquared` | −2..2 px/world tick² в выбранной attachment frame |
| `rotationRadians`, `rotationSpeedRadiansPerTick` | −2π..2π относительно captured forward; spin −1..1 rad/world tick |
| `widthPx`, `heightPx` | независимые 0..128 px по буквальным texture X/Y; 0 сохраняется |

<a id="profiles"></a>
## Profiles и exact Repair

Width/height/opacity/color profiles — объекты `{start,middle,end,curve}` для нормализованных позиций 0, 0.5 и 1. `curve` = `linear`, `easeIn`, `easeOut`, `smoothStep`, применяется отдельно к каждому интервалу. Это фиксированная математика, не выражения/код модели.

Размеры/ширина имеют knots 0..4, opacity 0..1. Явный ноль сохраняется. Color knots — opaque rendering color tokens плюс `effect` для захваченного существующего цвета; `white` сохраняет RGB исходного изображения. RGB-профиль не заменяет opacity и не должен умножать прозрачность дважды. Все параметры снимаются в immutable state, изменения исходного DTO не переписывают уже испущенный эффект.

Именованные поля позволяют Repair менять одну ошибочную точку без общего indexed-array merge и без размораживания соседних корректных параметров.

Validator-diagnosed foreign/additional fields допускают точное удаление через существующие delete-path permissions: например, лишний `path` у spriteElement. Только для этих диагностированных leaves omission означает delete; остальные omissions остаются no-change. Дублирующая asset-строка удаляется по ошибочному индексу, не вместе с корректной строкой того же ID.

Color tokens: `white`, `gray`, `brown`, `tan`, `red`, `orange`, `yellow`, `gold`, `green`, `cyan`, `blue`, `purple`, `pink`, `black`, `effect`. На каждом полуинтервале для локального t: linear=t; easeIn=t²; easeOut=1−(1−t)²; smoothStep=t²(3−2t). Sprite profiles используют normalized age; path — выбранный age/length. Отсутствие, explicit null и ноль не взаимозаменяемы.

При пустом asset-domain ошибка относится и к `texture.source`, и к `texture.assetId`: допустимую замену явно выбирает Repair, не код. При непустом домене меняется только сломанная ссылка; source и requests frozen. Unknown target сначала требует identity Repair, а не размораживания валидного selector без контекста. Общая процедура — [frozen-first Repair](TARGETED_REPAIR_PROTOCOL_RU.md).

<a id="path"></a>
## TexturedPath: реальные geometry/UV

`source=anchorHistory` хранит действительные timestamped позиции выбранного anchor, до 32 samples; identical points не образуют фиктивных segments. `historyTicks` задаёт retention, `minDistancePx` — порог записи.

`source=beam|whip` читает существующий canonical collision geometry supplier. Это не короткая декоративная линия, не вычисление range по картинке и не генерация новых damaging entities. Геометрические corners сохраняются; при необходимости средний profile knot добавляется линейно на существующий отрезок. Geometry ограничена 66 sections; history — 32. Decorative width не меняет collision width.

Совместимость следует реальному приоритету collision consumer: активный ChannelBeam выбирает beam до whip movement. Нельзя объявить обе геометрии доступными только по присутствию двух компонентов. Для beam/whip `anchor=self` нейтрален — supplier владеет размещением centerline; иной anchor не переносит её в выдуманную позицию. Временно отсутствующая geometry ничего не рисует.

`profileDomain=age` применяется только к истории; `length` использует нормализованную накопленную длину. `uvMode=stretch` натягивает текстуру; `repeat` использует явную `repeatLengthPx` и `scrollPxPerTick`. Геометрия источник/история не сглаживается в выдуманную траекторию. Пропуски/скачки больше явно заданного `maxSegmentLengthPx` не соединяются.

Live paths доступны projectile `periodic`/`on_spawn`, не item_body и не terminal event. История после retirement затухает по retention; текущая beam/whip geometry заканчивается вместе с источником. StartTick управляет началом sampling; repeatEvery=0 и duration=3 — нейтральные значения неиспользуемых здесь common controls.

| Поля | Единицы / обязательные сочетания |
|---|---|
| `historyTicks`, `minDistancePx` | history: integer 2..32 world ticks и 0..16 px; beam/whip: оба 0 |
| `maxSegmentLengthPx` | 1..4096 px; разрыв пропускается, не мостится |
| `widthPx` | 0..96 decorative px; 0 сохраняется, collision width не меняется |
| `profileDomain` | history: `age\|length`; beam/whip: только `length` и `anchor=self` |
| `uvMode` | `stretch\|repeat`; stretch требует `repeatLengthPx=1`, `scrollPxPerTick=0` |
| `repeatLengthPx`, `scrollPxPerTick` | 1..512 px/repeat; −32..32 UV px/world tick |

<a id="runtime"></a>
## Нейтрали, бюджеты и transport identity

Непотребляемые common поля для обоих material renderers **обязаны** быть нейтральными: `scale=1`, `density=spread=jitter=fadeIn=fadeOut=signatureWeight=visualCost=0`, `budgetWeight=1`, `emissionMode=particleRole=particleSystemId=textureRole=none`. `spriteElement.backend=Sprite`; `texturedPath.backend=Primitive`, `repeatEvery=0`, `duration=3`. Это не автоматически достроенные defaults и не вторые владельцы поведения. `alpha` применяется с opacityProfile один раз; звук/свет/Dust — отдельные возможности, не незапрошенные слои.

Сохраняются event/entity producer validation, frozen-first Repair, лимиты source/tick/draw, работа после source retirement для world effects, finite checks и controlled Begin/End. Симуляция не живёт в Draw. Dedicated server не исполняет presentation. Networking использует проверенную definition/asset identity, не пересылает произвольные image paths/bytes в VFX-event packet.

Незапрошенный/отсутствующий PNG не заменяется stock маской, белым quad или Dust. Требуемый PNG блокирует delivery при ошибке; ещё не загруженная клиентом текстура временно не рисуется. Старые слоты без новых fields не получают новые значения автоматически.

| Исполнительная граница | Каноническая семантика |
|---|---|
| Periodic item budget | `InfiniDetachedVfxSystem.Materials.StartMaterialEmission`: без per-Item activation clock положительный `maxParticlesTotal` не превращается ни в бессрочный item lifetime cap, ни в cap одной periodic-группы. Действуют общий source/world-tick allowance и существующие resource/draw caps; явный total=0 остаётся запретом. Для одного nonperiodic item event `MaterialEventAllowance` общий между material/legacy слотами; projectile lifetime ledger не меняется. |
| Nonowner lifecycle | `GeneratedProjectile.EmitAndSyncVfxEvent`: owner исполняет свои element events локально; у другого MP-клиента их единственный event-producer — validated server relay. Локальные legacy callbacks и регистрация live `texturedPath` не отключены. `on_spawn`, release/channel-complete, tile-collision, expire/kill не складываются второй раз при local-before-relay или relay-before-local. |
| Ordered replay | `VfxOrderedPeerStream`: отдельно для projectile/item event lane один monotone owner stream охватывает все source generations; сервер даёт каждому принятому claim свой sequence из одного outbound stream этой lane. Generation остаётся attachment identity, не replay/admission bucket. Нет rolling generation cap, TTL-replay window или eviction живых claims. Owner cursor ограничен `Main.maxPlayers` и сбрасывается при замене Player/socket; relay cursor — при замене server socket. World-exit/unload очищают состояние. Это контракт упорядоченного ModPacket/TCP transport, не независимое доказательство collision или anti-cheat. |
| Unresolved Item forwarding | `GeneratedItem.NetSend/NetReceive` и `GeneratedItem.Presentation`: полученный material token/capability сохраняется до registry hydration и при дальнейшей пересылке compact reference (item payload v6). Отсутствие уже загруженных material slots не понижает его до legacy v5; точный instance/generation не заменяется definition ID. |

Technical transport: projectile event v5, material item event v5, compact material Item v6; genuine legacy Item v5. Это не новая model-authored schema. Token/capability сохраняется до registry hydration и дальнейшей пересылки: unloaded material slots не понижают compact Item до legacy.

`VfxSourceBinding.ItemBinding.IsLive` требует живого игрока. После смерти periodic-регистрация и source-attached effects завершаются без нового Draw/producer; captured world events сохраняют delay/duration. Respawn допускает новую регистрацию только через настоящий producer, без ослабления instance/generation fences.

<a id="verification"></a>
## Проверка и доказательные границы

Проверять не только отдельные поля, но комбинации: texture source × applicability × attachment × event × profiles × zero/delay/cadence. Реальные составные файлы проходят Director validation → compile → asset generation boundary → storage/delivery → C# FromJson → executor/transport.

Offline native fixtures должны явно называться hand-authored test inputs. Структурно разные stamp/particles/delayed scatter/history/beam/whip сцены, отсутствующие слои, реальные разные texture bytes и negative controls доказывают доступные способы исполнения, но не качество LLM/image-model.

Проверять source replacement/retirement, immutable event snapshots, exact beam/whip centerline, repeated Draw/frozen clock, alpha/additive на тёмном/светлом, zero budgets/missing texture, общий расход caps, unload и восстановление batch/device state. Не выдавать headless/native за Terraria game-loop или сетевой матч.

Текущие Python owners: `test_vfx_packet_contracts.py`, `test_vfx_material_admission_contracts.py`, `test_vfx_frozen_boundary_contracts.py`, `test_vfx_dependency_delivery_contracts.py`, `test_vfx_ingredient_generation_contracts.py`; реальные C# seams — зарегистрированные checks `tools/EngineRuntimeChecks.csproj`. Команды/изоляция — [test owners](TEST_CONTRACT_OWNERS_RU.md). Тестовый PASS не переносится на socket delivery, game-loop, GPU или новую художественную/model/image приёмку. История .243–.246 — [audit provenance](VISUAL_AUDIT_HISTORY_RU.md#rollback), не актуальный список открытых дефектов.
