# Индивидуальные VFX-элементы — контракт 0.4.245

Это спецификация расширения существующего VFX-контракта, а не заявление о художественном качестве всех сгенерированных предметов. Native/CPU-проверки подтверждают свои исполнительные границы; разнообразие и качество реальной генерации проверяются отдельно на model-authored результатах.

## Что изменяется

Существующие rendererKinds сохраняются. В том же `vfxManifest.slots` добавляются:

- `spriteElement` с payload `element`: изображение с независимыми параметрами движения, привязки и изменения по времени;
- `texturedPath` с payload `path`: текстура на связной истории движения либо на реальной текущей геометрии beam/whip.

Это не weapon presets, не выбор дизайна по имени/категории и не произвольный исполняемый код. Нет новой VM, shader generation, второго effect graph или четвёртой текстовой LLM-роли.

## Стадии и владельцы

`Gameplay Author → Visual Director → VFX Director → image generation → strict delivery → C#`.

VFX Director и VFX Repair получают `acceptedRuntimeProgramReadOnly`: точную копию принятого runtimeProgram без per-entity `visual` (отдельный Visual context уже передаётся). Не создаётся второй механический контракт и не выводятся траектории из описания. Числа, entity IDs, движения, controllers, collision, события и bindings не меняются этим handoff.

VFX владеет своими image requests и временно-пространственной композицией. Он не меняет внешний вид основного предмета, gameplay, коллизии, урон или события. Image backend выполняет принятые запросы через существующий ограниченный generation gate; никакой скрытой смены backend/provider или подмены отсутствующего изображения.

Лимит ответа VFX Director и его условного Repair по умолчанию — 8000 токенов (`INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS`). Явная настройка пользователя сохраняет приоритет; новая LLM-роль или дополнительные Repair-попытки не добавляются.

## Собственные изображения

Optional `assets` в Director/manifest содержит до четырёх самостоятельных ингредиентов. Отсутствие означает отсутствие новых запросов и остаётся отсутствием в старом wire; явный null не является отсутствием.

У каждого запроса обязательны:

- `id`: точный безопасный идентификатор `[A-Za-z0-9_-]{1,48}`;
- `prompt`, `negativePrompt`;
- `canvasSize`: 16, 24, 32, 48, 64, 96 или 128;
- `layout`: `cutout` или `strip`.

`cutout` — отдельный объект с мягкой alpha и обычным вписыванием. `strip` — полный frame для UV-текстуры: keying/resize не должны менять его смысл bbox-crop, вращением, центрированием или silhouette-refit. Это технический выбор обработки изображения, не classifier эффекта: оба layout можно явно использовать в обоих новых renderers.

Одна декларация даёт одну image job; несколько слотов могут ссылаться на тот же ID. Дубликаты, dangling references и неиспользованные новые requests не принимаются. Runtime path/URL/status/score пишет image pipeline, не LLM. Серверные descriptors/PNG hashes и передача остаются у существующего AssetSync.

Delivery/cache проверяют безопасное PNG-имя и реальные файлы из тех же roots, которые обслуживает `/get_asset`, а не только существование произвольного локального пути. Проверяется весь непустой runtime PNG-roster, включая сохранённые overlay/entity/impact entries: complete PNG, до 8 МиБ на файл, до 16 МиБ суммарно и не более 32 файлов. Необязательное отсутствие картинки отличается от присутствующего, но неготового пути.

ID сохраняется буквально, включая регистр. Конечное имя PNG не строится из raw ID: `Glow`/`glow` и `spark`/`spark_refit` не должны сталкиваться после case-insensitive sync или refit. Временные jobs отделены namespace/digest, финальная атомарная публикация использует ASCII digest от exact recipe/asset identity и окончательных PNG bytes. Изменение изображения не перезаписывает ранее распределённый filename. Это техническое именование, не второй механизм проверки целостности.

Texture selector новых payload: `{source, assetId}`. source = `item`, `entity`, `impact`, `asset`; assetId пуст для первых трёх и ссылается на объявленный ID для asset. Существующий impact dependency сохраняется. Пути файлов или URL модель не авторит.

У `entity` должна быть принятая `baked_sprite`/`reuse_item_icon` image role; `no_asset`/`runtime_geometry` — несовместимый выбор, а не временно незагруженная текстура. У `impact` обязателен тот же entity и существующий `impactSprite`-producer. Эти зависимости относятся и к вложенным texture selectors, видны в Director/Repair и не разрешают менять уже принятую Visual-часть.

Fresh requests требуют непустого prompt. Полный локальный cache сохраняет captions; network projection обнуляет обе строки prompt/negativePrompt и оставляет asset identity, размер/layout, render references и готовые технические metadata. Runtime admission принимает этот объявленный stripped-вид, не применяет к нему правило нового image-запроса. Storage/delivery отдельно проверяют готовность ассетов, даже если проверка промежуточного compiled wire допускает pending records. Полный C# `GeneratedItemData.FromJson` принимает каждый объявленный VFX-ассет только с непустым PNG-path и точным `spriteStatus=generated|generated_warn_invalid` — и с captions, и в stripped network-виде. `pending`, `skipped`, `not_required`, `failed`, `prompt_only`, иной регистр или произвольный status не означают готовность. Это admission metadata; реальные PNG bytes по-прежнему проверяет существующий AssetSync.

## Поведение spriteElement

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

## Профили

Width/height/opacity/color profiles — объекты `{start,middle,end,curve}` для нормализованных позиций 0, 0.5 и 1. `curve` = `linear`, `easeIn`, `easeOut`, `smoothStep`, применяется отдельно к каждому интервалу. Это фиксированная математика, не выражения/код модели.

Размеры/ширина имеют knots 0..4, opacity 0..1. Явный ноль сохраняется. Color knots — opaque rendering color tokens плюс `effect` для захваченного существующего цвета; `white` сохраняет RGB исходного изображения. RGB-профиль не заменяет opacity и не должен умножать прозрачность дважды. Все параметры снимаются в immutable state, изменения исходного DTO не переписывают уже испущенный эффект.

Именованные поля позволяют Repair менять одну ошибочную точку без общего indexed-array merge и без размораживания соседних корректных параметров.

Validator-diagnosed foreign/additional fields допускают точное удаление через существующие delete-path permissions: например, лишний `path` у spriteElement. Только для этих диагностированных leaves omission означает delete; остальные omissions остаются no-change. Дублирующая asset-строка удаляется по ошибочному индексу, не вместе с корректной строкой того же ID.

## TexturedPath

`source=anchorHistory` хранит действительные timestamped позиции выбранного anchor, до 32 samples; identical points не образуют фиктивных segments. `historyTicks` задаёт retention, `minDistancePx` — порог записи.

`source=beam|whip` читает существующий canonical collision geometry supplier. Это не короткая декоративная линия, не вычисление range по картинке и не генерация новых damaging entities. Геометрические corners сохраняются; при необходимости средний profile knot добавляется линейно на существующий отрезок. Geometry ограничена 66 sections; history — 32. Decorative width не меняет collision width.

Совместимость следует реальному приоритету collision consumer: активный ChannelBeam выбирает beam до whip movement. Нельзя объявить обе геометрии доступными только по присутствию двух компонентов. Для beam/whip `anchor=self` нейтрален — supplier владеет размещением centerline; иной anchor не переносит её в выдуманную позицию. Временно отсутствующая geometry ничего не рисует.

`profileDomain=age` применяется только к истории; `length` использует нормализованную накопленную длину. `uvMode=stretch` натягивает текстуру; `repeat` использует явную `repeatLengthPx` и `scrollPxPerTick`. Геометрия источник/история не сглаживается в выдуманную траекторию. Пропуски/скачки больше явно заданного `maxSegmentLengthPx` не соединяются.

Live paths доступны projectile `periodic`/`on_spawn`, не item_body и не terminal event. История после retirement затухает по retention; текущая beam/whip geometry заканчивается вместе с источником. StartTick управляет началом sampling; repeatEvery=0 и duration=3 — нейтральные значения неиспользуемых здесь common controls.

## Старые поля, безопасность и доставка

Новые payload условно обязательны лишь для своего renderer. Непотребляемые common knobs должны иметь явно нейтральные значения, чтобы старые scale/density/fade/particle поля не притворялись вторыми владельцами нового поведения. Свет/звук/Dust остаются отдельными существующими возможностями с честными ограничениями, а не автоматически добавленными слоями.

Сохраняются event/entity producer validation, frozen-first Repair, лимиты source/tick/draw, работа после source retirement для world effects, finite checks и controlled Begin/End. Симуляция не живёт в Draw. Dedicated server не исполняет presentation. Networking использует проверенную definition/asset identity, не пересылает произвольные image paths/bytes в VFX-event packet.

Незапрошенный/отсутствующий PNG не заменяется stock маской, белым quad или Dust. Требуемый PNG блокирует delivery при ошибке; ещё не загруженная клиентом текстура временно не рисуется. Старые слоты без новых fields не получают новые значения автоматически.

## Исправленные исполнительные границы 0.4.245

| Граница | Канонический владелец и текущая семантика |
|---|---|
| Periodic item budget | `InfiniDetachedVfxSystem.Materials.StartMaterialEmission`: без per-Item activation clock положительный `maxParticlesTotal` не превращается ни в бессрочный item lifetime cap, ни в cap одной periodic-группы. Действуют общий source/world-tick allowance и существующие resource/draw caps; явный total=0 остаётся запретом. Для одного nonperiodic item event `MaterialEventAllowance` общий между material/legacy слотами; projectile lifetime ledger не меняется. |
| Nonowner lifecycle | `GeneratedProjectile.EmitAndSyncVfxEvent`: owner исполняет свои element events локально; у другого MP-клиента их единственный event-producer — validated server relay. Локальные legacy callbacks и регистрация live `texturedPath` не отключены. `on_spawn`, release/channel-complete, tile-collision, expire/kill не складываются второй раз при local-before-relay или relay-before-local. |
| Ordered replay | `VfxOrderedPeerStream`: отдельно для projectile/item event lane один monotone owner stream охватывает все source generations; сервер даёт каждому принятому claim свой sequence из одного outbound stream этой lane. Generation остаётся attachment identity, не replay/admission bucket. Нет rolling generation cap, TTL-replay window или eviction живых claims. Owner cursor ограничен `Main.maxPlayers` и сбрасывается при замене Player/socket; relay cursor — при замене server socket. World-exit/unload очищают состояние. Это контракт упорядоченного ModPacket/TCP transport, не независимое доказательство collision или anti-cheat. |
| Unresolved Item forwarding | `GeneratedItem.NetSend/NetReceive` и `GeneratedItem.Presentation`: полученный material token/capability сохраняется до registry hydration и при дальнейшей пересылке compact reference (item payload v6). Отсутствие уже загруженных material slots не понижает его до legacy v5; точный instance/generation не заменяется definition ID. |
| Runtime readiness | `GeneratedItemData.ValidateVfxEntityEventReferences`: точный ready-domain `generated\|generated_warn_invalid` применяется одинаково к full/cache/network VFX asset records. Обязательные authored keys остаются обязательными; наличие path без ready-status не проходит полный runtime admission. |
| PNG byte authority | `GeneratedAssetSyncService` сертифицирует canonical cache bytes по PNG/length/SHA на lifecycle boundary; proof остаётся на существующем descriptor. `RuntimeSpriteCache.TryGet` предпочитает этот путь существующему local shadow только при непротиворечивой declared identity: любой retained descriptor того же filename с другим length/hash отменяет certificate priority независимо от registration order и наличия у него proof. Equal identities могут разделять proof; без приоритета сохраняется прежний local-only путь. Derived filename → descriptor-reference index обновляется на manifest replacement, validation/commit и disposal; Draw делает O(1) lookup и обычную length/mtime freshness-проверку, без roster scan, PNG decode или SHA ради выбора owner. Изменённые file stats или disposal лишают proof приоритета; DTO paths/captions и сетевой definition hash не переписываются. |
| Texture-load backoff | `RuntimeSpriteCache.TryGet` сохраняет окончательный normalized selected key вне try; catch, retry admission и lifecycle invalidation используют один и тот же ключ выбранного canonical cache path, а не исходный authored alias. После неудачного load повторный вызов не открывает файл до истечения backoff либо явной invalidation. |

Версии technical transport не совпадают с runtime ABI: projectile event v5, material item event v5, compact material Item v6 и genuine legacy Item v5; это не новая model-authored схема. Для этих границ зарегистрированы headless regression checks. Их PASS подтверждает именно вызванные CPU/packet/byte-owner seams; он не означает native/GPU, socket delivery, Terraria multiplayer-матч, художественную или model/image-generation приёмку.

## Проверка

Проверять не только отдельные поля, но комбинации: texture source × applicability × attachment × event × profiles × zero/delay/cadence. Реальные составные файлы проходят Director validation → compile → asset generation boundary → storage/delivery → C# FromJson → executor/transport.

Offline native fixtures должны явно называться hand-authored test inputs. Структурно разные stamp/particles/delayed scatter/history/beam/whip сцены, отсутствующие слои, реальные разные texture bytes и negative controls доказывают доступные способы исполнения, но не качество LLM/image-model.

Проверять source replacement/retirement, immutable event snapshots, exact beam/whip centerline, repeated Draw/frozen clock, alpha/additive на тёмном/светлом, zero budgets/missing texture, общий расход caps, unload и восстановление batch/device state. Не выдавать headless/native за Terraria game-loop или сетевой матч.
