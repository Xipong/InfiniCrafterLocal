# Явный placed-body из PNG предмета

`present_placed_item_sprite` — optional capability Gameplay Author. Она выбирает существующий корневой PNG **этого же** предмета для тела его размещённого native tile. Это отдельная явная проекция картинки, не новый тип оружия, не router и не дополнительное image-задание. Старые recipes без операции сохраняют native appearance; обновление не дописывает её в сохранённые предметы.

## Author → wire

- `target` — существующий `item_body`.
- `placementCallId` — точный ID `configure_placeable` того же item-body, на который ссылается исполняемый `place_item` binding.
- Placement — tile-only (`tileId >= 0`, `wallId = -1`). Wall, чужая/неисполняемая ссылка и дублирующая presentation-ссылка отвергаются.
- Никакого default transform: все параметры ниже обязательны.

| Параметр | Тип / границы | Значение |
|---|---|---|
| `renderSizePx` | integer, 1…512 | Длинная сторона **полного PNG frame** в world pixels; прозрачные поля входят в размер. |
| `footprintAnchorX`, `footprintAnchorY` | number, 0…1 | Точка прямоугольника native footprint: 0 — левый/верхний край, 1 — правый/нижний. |
| `imagePivotX`, `imagePivotY` | number, 0…1 | Опорная точка полного PNG frame. |
| `offsetXPx`, `offsetYPx` | integer, −512…512 | Смещение world anchor: +X вправо, +Y вниз. |
| `rotationDegrees` | number, −180…180 | Поворот вокруг pivot в экранной/world системе с +Y вниз. |
| `flipX`, `flipY` | boolean | Отражение вокруг явно заданного pivot, до поворота. |

Compiler переносит ровно десять transform-полей в `runtimeProgram.bindings[].usePolicy.action.placement.placedBody`. `placementCallId` остаётся source association/receipt, не новым C# wire-полем. Каждое поле имеет точный source→wire receipt; association имеет отдельный технический receipt. Double-поля не сужаются в compiler/DTO: float-конверсия происходит только при вызове графического API. Отсутствие `placedBody` допустимо; present-null, неизвестные/пропущенные transform-поля и выход за границы — RED.

Visual Director и его существующий Repair получают выбранную placement presentation read-only. Они не могут менять её transform или механику. Root PNG остаётся обязательным selected asset, без нового project/source selector; отсутствие PNG — pending/error, не повод показывать native body или подставлять картинку.

## Runtime ownership

Единственный material owner — `GeneratedPlacementLedgerSystem`. Он хранит exact selected binding, canonical definition hash, native footprint и raw frame/packed-alternate witness. Footprint декодируется из actual `TileObjectData`/`TopLeft`, не из связных соседних блоков и не из `/18`. Packed alternate remainder не является registration ordinal. Cosmetic pose/PNG/registry/socket failure не отменяет принятую material claim и расходную receipt.

При native разрушении/support loss group переходит в существующую durable return queue: один exact generated item, не vanilla surrogate. NBT сохраняет выбранную presentation и диагностические raw witnesses. Initial snapshot и ordered commit/remove stream передают компактную group/witness, а definition и PNG идут через существующие registry/asset owners. Hydration bound — 32 round-robin visits за world tick; definition должна совпадать по hash, same-ID конфликт не перезаписывается молча. Client mirror не становится material authority. Placement Ready v5 выдаёт server-owned group GUID до native mutation; originating client использует его же, так что authoritative commit/removal не конфликтует с provisional claim. Host `assetTransport` (`http`/`native`) canonicalized только внутри existing definition-hash owner как routing metadata: исходные definition и raw transport SHA не переписываются.

`GeneratedPlacedBodyDrawSystem` рисует один root PNG на group после native tile pass. Размер independent от inventory `itemScale` и размера native tile-texture. Native support/collision/mining/wiring/interaction/light сохраняются. V1 оставляет authored PNG color, применяет world lighting, visibility/echo/fullbright/actuation; native paint bits и механика остаются, но native atlas paint-tint на PNG не имитируется. Обычные wired frame changes не отменяют selected body.

## Native draw boundary и явные отказы

Source adapter закрывает normal/basic/flame/sliced/Xmas/track и cached special passes, в том числе native tree/grass/vine/pylon/trophy/lens submissions. Он подавляет **final visual call**, сохраняя argument evaluation, updates, RNG, light, dust/liquids и чужие neighbors; не заменяет global texture и не прекращает whole Draw. Устанавливается полный набор 19 hooks / 156 final submissions атомарно и снимается своим lifecycle owner.

Эта v1 сертифицирует два проверенных native DLL profiles и bounded native footprints (до 16×16 и 256 cells). Unknown DLL/изменённая hook-chain shape, ModTile/чужие tile-visual callbacks и post-place actor/callback без отдельного ownership certificate дают явный отказ **до mutation**. Наличие пустого `TileEntity.ByPosition` до placement не считается доказательством отсутствия будущего actor. Indirect actor hooks присутствуют, но actor placements без generation/content/callback certificate не допускаются. Это не обещание покрыть arbitrary cross-mod drawing.

Native byte profiles: installed `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`; SDK `0585f4ebb022708a5d2a52ba92c6b4a4f812154d0333b384ef64d2dbd4f5b124`. Refusal диагностируется через существующий mod logger; disabled adapter не разрешает PNG overlay поверх неподтверждённого native тела.

## Проверки и границы доказательств

Зарегистрированные headless checks исполняют actual DTO/NBT/material/net handlers, installed MonoMod IL hooks, CPU-FNA draw queue, actual vanilla torch pose metadata и registry conflicts. Это не запуск игры/world, GPU pixel acceptance или MP socket match. Художественное качество новых model choices требует отдельного разрешённого live измерения.

Diagnostic request capture сохраняет полные sanitized builder messages перед provider conversion с recipe/stage/hash join через существующий trace owner. При превышении storage/payload bounds пишет explicit refusal, не обрезанный parent tail. Это не восстановление старого HTTP wire. Новые advisory clauses оставляют purposeful alternate use optional, делают стоимость/темп/выбранную физику явными и передают downstream complete accepted drivers, spawn/lifetime/collision/timings и calibration; они не добавляют judge, preset или переавторство saved recipes.
