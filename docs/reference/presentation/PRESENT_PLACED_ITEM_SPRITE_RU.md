# Собственные размещаемые объекты и PNG предмета

`place_object` создаёт собственный `ModTile` InfiniCrafterLocal. `placed_sprite` явно размещает полный корневой PNG этого же предмета относительно его footprint. Картинка больше не скрывает чужой/native tile: 19 IL draw hooks и frozen method shapes удалены.

## Два разных игровых примитива

- `place_object(width, height, collision, support)` — собственный объект: `width`/`height` от 1 до 16 клеток, `collision=open|solid`, `support=floor|wall|unanchored`. Все четыре решения явные. `floor` требует штатную опору под всей шириной, `wall` — заднюю стену, `unanchored` не требует опоры. Полный PNG обязателен через отдельный `placed_sprite` с точной ссылкой на этот call.
- `place_tile(tileId, placeStyle)` — настоящий загруженный native tile с его native изображением и поведением. ID и стиль берутся из фактов, а не угадываются. `placed_sprite` на этом пути отвергается. `place_wall` сохраняет отдельный native wall путь.

Собственный объект не наследует сундук, crafting station, баффы, анимацию, свет, wiring или callback родителя. Свет и живые эффекты выбираются отдельными `placed_light`/`placed_vfx`; они поддержаны для собственного и native tile. Другие функции не обещаются. Собственные варианты имеют статичную геометрию, штатное разрушение/потерю опоры, не погибают от воды/лавы; `solid` задаёт коллизию всего прямоугольника; hammer slope/half-block для него отключены. Это объявленная семантика примитива, не подбор поведения по имени предмета.

## Author → wire

- `target` — существующий `item_body`.
- `placementCallId` — ID исполняемого `place_object` того же item-body. Чужая/неисполняемая ссылка и повторная presentation-ссылка отвергаются.
- Собственный wire: `tileId=-1`, `wallId=-1`, `placeStyle=0`, `ownedTile={width,height,collision,support}`. Ровно один из owned/native tile/native wall путей допустим. Числовой загруженный ID собственного tile не попадает в authored wire.
- Десять transform-полей обязательны. Только `pivotSpace` optional: отсутствие эквивалентно `frame`.

| Параметр | Тип / границы | Значение |
|---|---|---|
| `renderSizePx` | integer, 1…512 | Длинная сторона **полного PNG frame** в world pixels; прозрачные поля входят в размер. |
| `footprintAnchorX`, `footprintAnchorY` | number, 0…1 | Точка прямоугольника footprint: 0 — левый/верхний край, 1 — правый/нижний. |
| `pivotSpace` | optional enum: `frame`, `alpha_bounds` | Базис pivot: полный frame либо прямоугольник ненулевой alpha **финального выбранного PNG**. Omission = `frame`. |
| `imagePivotX`, `imagePivotY` | number, 0…1 | Нормализованная точка внутри выбранного базиса; 0/1 — края пикселей, не центры. |
| `offsetXPx`, `offsetYPx` | integer, −512…512 | Смещение world anchor: +X вправо, +Y вниз. |
| `rotationDegrees` | number, −180…180 | Поворот вокруг pivot в экранной/world системе с +Y вниз. |
| `flipX`, `flipY` | boolean | Отражение вокруг явно заданного pivot, до поворота. |

Compiler переносит явно выбранные поля в `runtimeProgram.bindings[].usePolicy.action.placement`. Для owned shape и transform есть source→wire receipts; `placementCallId` остаётся association, а не отдельным C# полем. Пропущенный optional `pivotSpace` получает только объявленную нейтраль `frame` с receipt. Невалидное присутствующее значение, null или пропущенная обязательная механика остаются RED. Старый native tile + PNG не превращается в owned автоматически.

Root PNG остаётся существующим selected asset без дополнительного image-задания. Missing/invalid PNG означает pending/error, не native картинку и не placeholder. Сам `ModTile.PreDraw` всегда возвращает false, поэтому нет двойного тела и зависимости от чужих визуальных callback-списков.

## Явная регистрация по alpha bounds

Для `alpha_bounds` cache измеряет все пиксели с **alpha > 0** в уже существующем `Color[]` premultiply/upload проходе. Никакого нового decoder, второго `GetData`, per-draw обхода или threshold PCA. Bounds сохраняются на том же exact selected `CachedTexture` generation, что texture и local forward angle. Правая/нижняя граница exclusive: `(left, top, right, bottom)` охватывает полные pixel cells. Полностью прозрачный PNG имеет измеренный empty bounds; borrowed 3-argument fixture имеет unknown bounds. Оба случая при явном `alpha_bounds` отказывают только custom body draw — **без** подмены базиса на frame/native, изменения ledger или возврата материала.

`pivot = (left + (right-left)*imagePivotX, top + (bottom-top)*imagePivotY)`. После этого прежние scale, отражение вокруг pivot, поворот и world-axis offset применяются к **целому uncropped PNG**. Viewport culling использует тот же pivot, но полный frame. `renderSizePx` всегда измеряет полный frame: alpha-bounds не растягивает видимую часть до этого размера. Отсутствие/явный `frame` сохраняют прежний pivot, включая намеренные прозрачные поля.

Для нового неподвижного наземного рисунка Author может сознательно выбрать `pivotSpace=alpha_bounds`, `imagePivotY=1`, `footprintAnchorY=1`, нулевые `offsetYPx`/`rotationDegrees` и `flipY=false`: нижний край alpha rectangle совпадёт с нижним краем footprint. Это не автоматическое правило для мебели и не универсальное доказательство соприкосновения силуэта/collider: glow/shadow с ненулевой alpha тоже входит в bounds; другие rotation/flip/offset/composition могут сознательно оставлять воздух. `frame` остаётся законным выбором. Нет name/category/parent routing, обязательного self-report, crop или миграции существующего мира.

## Runtime ownership

`GeneratedOwnedTiles` регистрирует 1536 структурных вариантов: 16×16 размеров × 2 collision × 3 support. Имя `GeneratedOwned_{width}x{height}_{collision}_{support}` стабильно; текущий числовой `Type` — только адрес движка. tML сохраняет сам tile по имени; placement witness дополнительно сохраняет `ownedTileKey` и заново разрешает текущий Type после загрузки. Перестановка других модов не меняет authored definition/hash.

Единственный material owner — прежний `GeneratedPlacementLedgerSystem`: server-authorized exact item/binding/hash, complete footprint, prefix и одна расходная receipt. Footprint определяется фактическим `TileObjectData`/`TopLeft`, не связными соседями. Pose/PNG/registry/socket failure не стирает material claim.

Разрушение переводит group в durable pending-return queue до выдачи одного exact generated item. Для owned объекта удаляются только его оставшиеся клетки с тем же типом и точным origin/размером, без native surrogate drops. Полный item pool оставляет возврат в очереди; повторные callbacks не создают второй возврат.

NBT, компактный initial snapshot и ordered commit/remove stream используют существующую ledger. Definition и PNG идут через прежние registry/asset owners. Hydration ограничена 32 visits за world tick; same-ID/wrong-hash не присваивает presentation. Клиент не становится material authority. Placement Ready имеет протокол 7, ledger mirror — версию 5; стороны обновляются вместе.

`GeneratedPlacedBodyDrawSystem` рисует один root PNG на group после tile pass. Сохраняются full-frame transform, world lighting, visibility/echo/fullbright/actuation. PNG не получает native atlas paint-tint. `placed_vfx` сохраняет явные frame bounds: верхняя левая клетка owned объекта имеет frameY=0, поэтому активны только диапазоны, включающие 0. Нового on/off поведения не добавлено.

## Чистый переход и сохранения

Нет migration/importer и автоматического восстановления прежних parent mechanics. Старые item definitions с native tile + `placedBody` отвергаются как неподдержанный контракт. Если world ledger содержит такие definitions, загрузка останавливается **до** очистки claims, а сохранение пустой замены блокируется. Пользователю нужно сохранить резервную копию и вернуться к предыдущей версии для извлечения предметов либо начать новый мир. Исходный ledger не удаляется, ключи сохранения не переименовываются молча. Неизвестные/повреждённые raw claims остаются у существующего механизма сохранения и quarantine.

<a id="native-containers"></a>
## Нативные сундуки остаются нативными

`place_tile` сохраняет отдельный container путь и его 6 detours/3 guards. Текущая реализация принимает только `TileID.Containers` (21), `placeStyle=0`; остальные chest styles/families отказывают до mutation. Это не обещание поддержки всех vanilla/modded контейнеров.

Используется настоящий `Terraria.Chest`: штатное открытие, 40 inventory slots, contents/name persistence, refusal разрушить наполненный сундук. Ledger хранит лишь связь exact generated material с actor/footprint; второго инвентаря нет. Light/VFX могут использовать ту же actor liveness, но custom PNG native сундука не разрешён. Серверный intent/Ready/Notify путь, capacity rollback, guards сохранения и prefix-preserving pending returns остаются.

## Проверки и границы

Python проверяет Author/repair/provider/compiler/receipts/strict-wire контракт. Native CPU checks проверяют DTO, registration metadata, NBT, exact ledger, return queue, frame projection и handlers. Они не заменяют игровой client/GPU smoke, реальный multiplayer socket match или проверку произвольных чужих модов. Результаты публикуются для конкретного проверенного commit; старые прогоны удалённого IL adapter не являются доказательством новой реализации.
