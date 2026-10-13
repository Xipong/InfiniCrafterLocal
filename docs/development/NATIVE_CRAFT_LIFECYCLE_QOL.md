# Native craft: claims, доставка и lifecycle

## Владельцы

- Локальный refund передаётся от station/request существующему per-player владельцу отложенного возврата. Хранится только недоставленный остаток. `infiniDeferredCraftRefundsV1` сохраняет его через native ItemIO/TagIO отдельно от save-on-exit резервирования ещё активных craft; один claim не учитывается дважды.
- Настоящий native world-item slot должен быть неактивен и иметь **ровно нулевой** reuse timer. Full pool, cooling slots, отрицательный/ненулевой timer и dummy slot не дают capacity. Inventory/world delivery списывают один claim один раз; давление пула не заменяет прежний занятый drop.
- Remote inputs остаются в world escrow journal. Клиентская отмена использует существующий scoped cancel packet и сохраняет request/mirror до ответа host. `cancelRequested` хранится в прежней pending remote craft row, включая reconnect к тому же origin. Нового packet или клиентской refund authority нет.
- Cancel, встретивший уже committed craft, воспроизводит реальный journal outcome. Unknown/stale owners не создают failure acknowledgement, способный воскресить потраченные inputs.
- Station wire v2 добавляет stable client token в cancel packet для main и extra lanes. После reconnect отмена восстанавливает только известную journal transaction с тем же world scope и session pinning; orphan pending request завершается failure с сохранением exact escrow, без нового generation. Unknown request не создаёт owner/transaction/outcome; живой чужой owner и token rotation отклоняются. Client и host должны использовать v2: v1 отвергается до чтения изменённых полей. Saved escrow/journal format не меняется.

Regression `cancelled craft reconnect resolves only owned journal` проверяет actual cancel handler: новый server player получает terminal outcome без повторного craft request; pending orphan сохраняет inputs, committed success сохраняет identity. Дополнительно проверяются live-worker cancellation, same-token foreign-live-session refusal, wrong scope/v1 refusal, unknown-ID no-op и повторный replay. Это CPU/intercepted-socket проверка, не реальный multiplayer reconnect.

## Worker и доставка

Прежний 20-минутный recovery deadline завершает incomplete workers и retry waits, не только интервалы между attempts. Каждая local/host lane отменяет захваченный request и снимает consumer. Server timeout сохраняет единственное material escrow и durable failed outcome. Remote deadline запрашивает отмену; отсутствие host acknowledgement не даёт права refund.

Завершённый non-null результат, ожидающий world-item capacity, остаётся у исходного craft/task owner. Retry пытается **доставить**, не сгенерировать повторно. Прежний SP save-on-exit возвращает исходные ingredients недоставленного craft; server unload сохраняет world escrow, restart разрешает прерванную работу через прежний journal. Это изменение намеренно не добавляет durable generated-output storage.

Metadata HTTP discovery остаётся в generation workers или bounded queued registry refresh. Update-thread sharing/stamping читает immutable volatile transport snapshot: не делает HTTP и не берёт worker discovery lock. Прежние host transport normalization и final asset-roster validation сохраняются.

Закрытие inventory возвращает каждую idle lane независимо. Busy lanes сохраняют material owner; работа одной lane не удерживает чужие idle inputs и не возвращает mirrors другой работающей lane.

## Presentation API

`InfiniCraftPlayer.Lifecycle.cs` предоставляет:

- `TryCancelCraftLane(int laneIndex)` — явное действие, не draw/read hook.
- `GetCraftLaneOutcome(int laneIndex)` — чистый bounded presentation snapshot. `Kind`: `None`, `Succeeded`, `Failed`, `Cancelled`, `TimedOut`; actual outcome detail не длиннее 240 символов. Переживает transient clear 30 секунд, но не является material authority.
- `IsCraftLaneWaitingForDelivery(int laneIndex)` — чистое local/host наблюдение capacity для ready-result.

`CraftLaneStatus` включает локализованный retained terminal kind и bounded actual failure/name detail. `IsCraftLaneCancellationPending(int)` наблюдает отмену, ожидающую host; явная per-lane кнопка заблокирована до решения owner. Delivery capacity наблюдается только local/host owner, не выводится из клиентского item pool. `HasPendingCraftRefunds` читает существующий player-wide список: оставляет панель видимой и добавляет локализованный pending-return footer, не приписывая материал произвольной lane. Drawing не вызывает cancel action или authority-refresh hooks.

## Историческая проверенная граница

В исходной проверке canonical C# sources собирались Windows .NET 8 с tModLoader `2026.6.3.6` и ParticleLibrary/Luminance references, без warnings/errors. Named CPU checks зарегистрированы в `EngineRuntimeChecks.csproj` и runner:

- 11 craft QoL checks: full-pool native refund preservation, три native TagIO reloads, exact prefix/stack, inventory/actual vanilla world return, cooling/negative timer refusal, partial-merge remainder, metadata HTTP barrier с 250ms nonblocking reads, incomplete deadline/late-result refusal, server durable escrow timeout, completed delivery wait/save-on-exit, bounded terminal presentation, independent-lane cancellation, remote cancel save/reconnect, committed cancel replay и idle-lane closure.
- Пять retained cancellation checks, включая withheld HTTP, shared-lock waiters и unload всех server owners.
- 23 retained persistence checks, включая exact origin/session/replay, full-pool output refusal и durable placement returns.
- Тогда targeted Python craft cancellation/multi-dev/MP simulator: девять passed; C# contract scanner и project hygiene passed.

До исправления наблюдались RED: occupied-drop replacement, metadata-lock blocking, incomplete-worker deadline, ready-output owner retirement, partial refund duplication, lost terminal status и idle-lane asymmetry. Cancel replay воспроизвёл false acknowledgement после committed success.

Игра, GPU, provider/inference, installed-mod update и реальный peer packet delivery не запускались. Full suite до parent integration не запускался. Первоначальные branch fixtures останавливались до успешной generated proxy allocation; integrated observer ниже закрывает именно CPU границу. Actual vanilla refund allocation также упражняется.

## Историческая интеграция станции

- Явные cancel hit rectangles используют один geometry helper с renderer; retained viewport checks включают все кнопки при ширине 400 px. RU/EN состояния различают cancellation acknowledgement, local/host delivery space, success/failure/cancellation/timeout и player-wide pending return. Bar остаётся craft timer, не model progress/ETA.
- Tk trace panel показывает bounded `generationActivity.requests` из guarded async health read: opaque backend request ID, profile, exact entered stage либо unknown, elapsed/stage elapsed, wait reason и true/false/unknown network boundary. IDs не native lane IDs. Refresh явный и подписан как последний health snapshot; changed endpoint/foreign server отвергаются. Нового activity protocol, model call или native-job correlation нет.
- Тогда fresh Windows .NET 8 linked-canonical build: без warnings/errors. Passed 59 distinct focused native checks: 5 integrated, 9 forge, 11 craft QoL, 5 cancellation, 23 persistence, 6 asset lifecycle. Passed 150 scoped desktop/station/backend-activity Python tests. Full suite не запускался. Это результаты исходного снимка, не текущий acceptance count.
- Actual installed `ItemLoader.Register`/array setup даёт настоящий GeneratedItem template в isolated CPU scope. Неизменный путь `PostUpdate` → `Item.NewItem` → `GeneratedItem.SetData`, включая actual fixture-PNG roster admission, завершает три lane в SP и host-server role mode после освобождения full/cooling/negative-timer capacity. Сохраняется identical ready task за прежним 20-minute deadline, выделяется ровно один proxy, exact ID/PNG/gameplay сохранены, старые occupied drops не меняются; refund/regeneration нет. Server cases проверяют четыре оставшихся unrelated escrow slots и exact durable success через native ItemIO/TagIO save/unload/reload. Перехвачен только отсутствующий peer transport; allocator, hydration, journal и update consumer настоящие.
- Actual client acknowledgement обрабатывает cancel/failure и late committed success для трёх lane; foreign/repeated acknowledgements отвергаются без inventory copies. Retained same-origin pending-cancel save/reconnect и server late-cancel replay оставались green.
- RED покрывал client-local capacity mislabelling, отсутствующее localized pending/outcome presentation, cancel hit wiring, request-row display, потерянные unknown-between-stage rows и stale endpoint activity. Новый material owner или production commit/escrow mutation не понадобились.

CPU role-mode/intercepted transport не равны полному game dispatch, реальному socket/peer delivery, GPU/image generation, installed-mod packaging или visual GUI acceptance. В исходной WSL Python среде не было tkinter, реальное Tk окно не запускалось. Evidence: `/home/xipong/.hermes/cache/scratch/icl-qol-integrated/` (fresh build/run logs, exact DLL/source pin, scoped Python XML); harness setup failures сохранены отдельно от final acceptance. Для текущих проверок используй [тестовый runbook](TESTING_RU.md).
