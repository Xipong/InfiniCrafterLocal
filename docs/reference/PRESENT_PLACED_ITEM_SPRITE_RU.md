# Явный placed-body из PNG предмета

`present_placed_item_sprite` — optional capability Gameplay Author. Она выбирает существующий корневой PNG **этого же** предмета для тела его размещённого native tile. Это отдельная явная проекция картинки, не новый тип оружия, не router и не дополнительное image-задание. Старые recipes без операции сохраняют native appearance; обновление не дописывает её в сохранённые предметы.

## Author → wire

- `target` — существующий `item_body`.
- `placementCallId` — точный ID `configure_tile_placement` того же item-body, на который ссылается исполняемый `place_item` binding.
- Placement — tile-only (`tileId >= 0`, `wallId = -1`). Wall, чужая/неисполняемая ссылка и дублирующая presentation-ссылка отвергаются.
- Десять исходных transform-полей обязательны. Только новый `pivotSpace` optional: отсутствие точно эквивалентно `frame`, без переавторства сохранённых definitions.

| Параметр | Тип / границы | Значение |
|---|---|---|
| `renderSizePx` | integer, 1…512 | Длинная сторона **полного PNG frame** в world pixels; прозрачные поля входят в размер. |
| `footprintAnchorX`, `footprintAnchorY` | number, 0…1 | Точка прямоугольника native footprint: 0 — левый/верхний край, 1 — правый/нижний. |
| `pivotSpace` | optional enum: `frame`, `alpha_bounds` | Базис pivot: полный frame либо прямоугольник ненулевой alpha **финального выбранного PNG**. Omission = `frame`. |
| `imagePivotX`, `imagePivotY` | number, 0…1 | Нормализованная точка внутри выбранного базиса; 0/1 — края пикселей, не центры. |
| `offsetXPx`, `offsetYPx` | integer, −512…512 | Смещение world anchor: +X вправо, +Y вниз. |
| `rotationDegrees` | number, −180…180 | Поворот вокруг pivot в экранной/world системе с +Y вниз. |
| `flipX`, `flipY` | boolean | Отражение вокруг явно заданного pivot, до поворота. |

Compiler переносит десять обязательных transform-полей и выбранный `pivotSpace` в `runtimeProgram.bindings[].usePolicy.action.placement.placedBody`. `placementCallId` остаётся source association/receipt, не новым C# wire-полем. Каждое поле имеет точный source→wire receipt; association имеет отдельный технический receipt. Для пропущенного optional `pivotSpace` после полной validation материализуется только объявленная нейтраль `frame` с `declared_neutral_omission` receipt; явные `frame`/`alpha_bounds` имеют `delivered`. Double-поля не сужаются в compiler/DTO: float-конверсия происходит только при вызове графического API. Отсутствие `placedBody` допустимо; present-null, неизвестные/пропущенные обязательные transform-поля и выход за границы — RED.

Visual Director и его существующий Repair получают выбранную placement presentation read-only. Они не могут менять её transform или механику. Root PNG остаётся обязательным selected asset, без нового project/source selector; отсутствие PNG — pending/error, не повод показывать native body или подставлять картинку.

## Явная регистрация по alpha bounds

Для `alpha_bounds` cache измеряет все пиксели с **alpha > 0** в уже существующем `Color[]` premultiply/upload проходе. Никакого нового decoder, второго `GetData`, per-draw обхода или threshold PCA. Bounds сохраняются на том же exact selected `CachedTexture` generation, что texture и local forward angle. Правая/нижняя граница exclusive: `(left, top, right, bottom)` охватывает полные pixel cells. Полностью прозрачный PNG имеет измеренный empty bounds; borrowed 3-argument fixture имеет unknown bounds. Оба случая при явном `alpha_bounds` отказывают только custom body draw — **без** подмены базиса на frame/native, изменения ledger или возврата материала.

`pivot = (left + (right-left)*imagePivotX, top + (bottom-top)*imagePivotY)`. После этого прежние scale, отражение вокруг pivot, поворот и world-axis offset применяются к **целому uncropped PNG**. Viewport culling использует тот же pivot, но полный frame. `renderSizePx` всегда измеряет полный frame: alpha-bounds не растягивает видимую часть до этого размера. Отсутствие/явный `frame` сохраняют прежний pivot, включая намеренные прозрачные поля.

Для нового неподвижного наземного рисунка Author может сознательно выбрать `pivotSpace=alpha_bounds`, `imagePivotY=1`, `footprintAnchorY=1`, нулевые `offsetYPx`/`rotationDegrees` и `flipY=false`: нижний край alpha rectangle совпадёт с нижним краем native footprint. Это не автоматическое правило для мебели и не универсальное доказательство соприкосновения силуэта/collider: glow/shadow с ненулевой alpha тоже входит в bounds; другие rotation/flip/offset/composition могут сознательно оставлять воздух. `frame` остаётся законным выбором. Нет name/category/parent routing, обязательного self-report, crop или миграции существующего мира.

## Runtime ownership

Единственный material owner — `GeneratedPlacementLedgerSystem`. Он хранит exact selected binding, canonical definition hash, native footprint и raw frame/packed-alternate witness. Footprint декодируется из actual `TileObjectData`/`TopLeft`, не из связных соседних блоков и не из `/18`. Packed alternate remainder не является registration ordinal. Cosmetic pose/PNG/registry/socket failure не отменяет принятую material claim и расходную receipt.

При native разрушении/support loss group переходит в существующую durable return queue: один exact generated item, не vanilla surrogate. NBT сохраняет выбранную presentation и диагностические raw witnesses. Initial snapshot и ordered commit/remove stream передают компактную group/witness, а definition и PNG идут через существующие registry/asset owners. Hydration bound — 32 round-robin visits за world tick; definition должна совпадать по hash, same-ID конфликт не перезаписывается молча. Client mirror не становится material authority. Placement Ready v6 выдаёт server-owned group GUID до native mutation; клиент и сервер обновляются вместе. Для обычных placements originating client использует тот же GUID, так что authoritative commit/removal не конфликтует с provisional claim. Host `assetTransport` (`http`/`native`) canonicalized только внутри existing definition-hash owner как routing metadata: исходные definition и raw transport SHA не переписываются.

`GeneratedPlacedBodyDrawSystem` рисует один root PNG на group после native tile pass. Это **статичная полная замена картинки**, включая native animation, flame submissions и визуальные on/off состояния: нарисованное в PNG пламя не анимируется и не гаснет вместе с native костром. Поздние обычные VFX-слоты предмета сами по себе не становятся эффектами установленной мебели. Отдельный explicit `enable_placed_vfx` с matching slot `placementBindingId` может исполнять независимые live flames/assets; он не анимирует этот root PNG и не восстанавливает native flame pictures. Если нужны существующие native-анимация и визуальное переключение, Author должен осознанно не выбирать эту операцию; рантайм не удаляет её автоматически и не заменяет готовые сохранённые определения. Размер independent от inventory `itemScale` и размера native tile-texture. Native support/collision/mining/wiring/interaction/light сохраняются. V1 оставляет authored PNG color, применяет world lighting, visibility/echo/fullbright/actuation; native paint bits и механика остаются, но native atlas paint-tint на PNG не имитируется. Обычные wired frame changes не отменяют selected body.

## Native draw boundary и явные отказы

Source adapter закрывает normal/basic/flame/sliced/Xmas/track и cached special passes, в том числе native tree/grass/vine/pylon/trophy/lens submissions. Он подавляет **final visual call**, сохраняя argument evaluation, updates, RNG, light, dust/liquids и чужие neighbors; не заменяет global texture и не прекращает whole Draw. Устанавливается полный набор 19 hooks / 156 final submissions атомарно и снимается своим lifecycle owner.

Эта v1 сертифицирует два проверенных native DLL profiles и bounded native footprints (до 16×16 и 256 cells). Обычные tile placements требуют exact callback-free native metadata, включая alternates. Для WaterChest `tileId=21, placeStyle=17` отдельно реализован [сертифицированный native actor lifecycle](#native-waterchest), совместимый с body/light/VFX. Остальные container post-place hooks без такого сертификата не поддерживаются, в том числе без косметических calls. Unknown DLL/изменённая hook-chain shape, ModTile/чужие tile-visual callbacks и post-place actor/callback без отдельного ownership certificate дают явный отказ **до mutation**. Наличие пустого `TileEntity.ByPosition` до placement не считается доказательством отсутствия будущего actor. Indirect actor hooks присутствуют, но actor placements без generation/content/callback certificate не допускаются. Это не обещание покрыть arbitrary cross-mod drawing.

Native byte profiles: installed `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`; SDK tModLoader 2026.7.3.0 `d530e508b2841e66d880ce279a609624b5ab66ce8093eedfa04f47c3d12d485c`. Каждый profile проходит прежний полный preflight 19 exact method shapes и повторную проверку текущей MonoMod hook chain; совпадение версии без точного SHA256 не даёт admission. Refusal диагностируется через существующий mod logger; disabled adapter не разрешает PNG overlay поверх неподтверждённого native тела.

<a id="native-waterchest"></a>
## Сертифицированный native WaterChest

`configure_tile_placement(tileId=21,placeStyle=17)` исполняется как настоящий native сундук в SP и MP на проверенном installed runtime `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`. Другой DLL profile, изменённые native callback tuples/alternates или чужие placement callbacks дают pre-mutation refusal; одна версия tML без совпадения source certificate недостаточна. Нового Author-поля для storage lifecycle нет; это сертификат исполнения уже выбранного tile/style, не выбор механики по имени.

Одна запись прежней material ledger связывает exact definition/binding/prefix, четыре новых клетки, результат native callback и реально созданный `Terraria.Chest`. SP завершается штатным post-placement callback; предсказуемый отказ проверяется до mutation, проигранная capacity race или callback fault откатывают только собственные новые клетки и наблюдавшийся новый пустой actor. Чужие/наполненные actor не удаляются.

В MP используется прежний intent/Ready/Notify с протоколом **6**: клиент не предсказывает сундук и не расходует предмет заранее. Сервер проверяет exact source instance, выполняет настоящий `WorldGen.PlaceChest`, фиксирует единственный debit и отправляет native message 34 success, native inventory sync и точный sequenced outcome. Отказ не создаёт vanilla-компенсацию; чужой vanilla запрос сохраняет обычное поведение. Мод клиента/сервера и генератор обновляются совместно.

Содержимое — только native 40-slot inventory: native open/exclusivity, WorldFile/WorldIO/TagIO save/load и ItemIO остаются владельцами. ICL не сериализует копию содержимого и не создаёт отсутствующий inventory при загрузке. После легитимной загрузки world разрешено однократное native coordinate rebind: array index при сохранении меняется. Живая подмена actor/slot reuse не перепривязывают claim. Native Chest не имеет persistent incarnation GUID, поэтому необнаруженную замену тем же типом на тех же координатах между сохранением и загрузкой этот контракт различить не может.

Наполненный сундук сохраняет native отказ разрушения; `CanDrop` подавляет surrogate drop, но сам не выпускает generated material. Возврат одного exact prefix-preserving предмета разрешён только после наблюдавшегося удаления native actor **и** всего footprint, через прежнюю durable pending queue, включая полный world-item pool. Body/light/VFX читают ту же actor liveness. Повреждённый footprint/foreign actor диагностируются с сохранением claim и существующего native inventory; точный native save hook не даёт vanilla pruning выбросить inventory, но не чинит мир, не присваивает чужой actor и не обещает восстановить произвольные внешние world edits.

## Проверки и границы доказательств

Зарегистрированные headless checks исполняют actual DTO/NBT/material/net handlers, installed MonoMod IL hooks, CPU-FNA draw queue, actual vanilla torch pose metadata и registry conflicts. Это не запуск игры/world, GPU pixel acceptance или MP socket match. Художественное качество новых model choices требует отдельного разрешённого live измерения.

Diagnostic request capture сохраняет полные sanitized builder messages перед provider conversion с recipe/stage/hash join через существующий trace owner. Полное логирование и его OFF/хранение/GUI scope описаны в [одном operator-разделе](../user/DIAGNOSTICS_RU.md); ошибка публикации даёт explicit refusal, не обрезанный parent tail. Это не восстановление старого HTTP wire. Новые advisory clauses оставляют purposeful alternate use optional, делают стоимость/темп/выбранную физику явными и передают downstream complete accepted drivers, spawn/lifetime/collision/timings и calibration; они не добавляют judge, preset или переавторство saved recipes.
