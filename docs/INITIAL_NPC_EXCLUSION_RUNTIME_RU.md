# Точный исходный NPC для новых projectile emission adapters

Это общий технический seam для A10/A11, не самостоятельная gameplay capability.
Без явно переданного `RuntimeInitialNpcExclusion` все существующие spawn producers
сохраняют прежний collision путь. Новые Author capabilities должны передать свой
явный счётчик и собственный source target; им нельзя выводить их из имени предмета.

## Классификация

**Alias Lowering**: точный authored emission adapter передаёт выбранный target и
счётчик в native instance state. Slot и server-issued incarnation — техническая
идентичность выбранного NPC, а не выбор дополнительной цели. Missing/unknown
incarnation при ненулевом счётчике отказывает в spawn; ничего не достраивается.

`TryCapture(npc, updates, out snapshot)` принимает счётчик `0..600` native projectile
AI updates. Это historical remaining-counter semantics из
`f04ee02:GeneratedProjectile.Runtime.cs:671`: decrement происходит **до** collision.
Значение `10` запрещает contact до первого AI и девять последующих post-AI
collision opportunities; `1` — только до первого AI; `0` отключает исключение.
`extraUpdates` ускоряет расход; это не world ticks и не обещание десяти полных
collision updates. Activation delay также расходует счётчик.

`RuntimeHitNpcGeneration` остаётся единственным owner incarnation. Смена объекта,
повторное `SetDefaults` с новым token и повторное использование slot не наследуют
иммунитет; `Transform`, сохраняющий token, сохраняет его. Исключается только
точно выбранный NPC, обычные native immunity, tile collision и projectile movement
не меняются. Возможность столкнуться с другой NPC определяется её обычным hit path.

Generated projectile ExtraAI v3 добавляет slot, generation и **remaining** counter.
Принимается и v2 с точным отсутствием нового состояния. Авторитетный local owner
не продлевает и не очищает собственный countdown от same-source observation.
Hydration сохраняет состояние, новая Configure очищает. Peer snapshot не выдаёт
spawn budget. Это синхронизация выбранного owner состояния, не server proof hit.

`RuntimeSpawnTransform(Position, Direction)` — второй общий seam. Он передаёт
точное начало и ось отдельного emission, проверяет finite/nonzero geometry и
обходит child placement/aim/offset. Скорость и дальнейший movement принадлежат
authored child. Новый capability обязан явно объявить этот input и проверить
совместимость reference; helper сам не выбирает target или geometry policy.

Validation для malformed transport: rejected ExtraAI остаётся inert при следующем
AI; доступная registry metadata не может стереть испорченный exclusion и вернуть
снаряд в GREEN. Только новый полный валидный payload либо новая явная Configure
снимает refusal. RED payload не преобразуется в другой gameplay payload.

Для нескольких отдельных emissions caller резервирует весь bounded batch,
перед каждым вызовом передаёт ровно одну reservation и в `finally` возвращает
только ещё не вызванные попытки. При обычном отказе `SpawnRuntimeEntity` возвращает
число созданных actors; caller возвращает разницу. При exception этот обычный
return path не выполняется: callee сам возвращает переданный остаток за вычетом
успешных actors и пробрасывает исходную ошибку. Не полностью сконфигурированный
host деактивируется без terminal effects. Root spawn (`childDepth == 0`) не
резервирует event budget и не создаёт возврат при exception. Такой же boundary
использует отдельный PR A6 с concurrent descendant pool.

## Проверки

Добавлены native EngineRuntimeChecks для реальных `AI`, `CanHitNPC`, NPC token
decoder, `Transform`, v2/v3 projectile ExtraAI, owner/peer hydration и malformed
positive-counter/zero-token payload. Native spawn entry-intercept проверяет
точную геометрию и возврат reservation на exception, не подменяя создание
снаряда фиктивным объектом. .NET/tModLoader/game здесь недоступны:
native build и запуск этих сценариев — **notRun**. Source/contract gates проверяют
привязку seam к production consumers, но не заменяют native выполнение.
