# Native craft claims and lifecycle

## Ownership

- Local refunds transfer from the station/request to the existing per-player deferred-refund owner. Only the undelivered remainder is retained. `infiniDeferredCraftRefundsV1` persists that remainder through native ItemIO/TagIO; it is separate from the existing save-on-exit backup of still-active crafts so neither claim is counted twice.
- A real native world item slot must be inactive and have an **exactly zero** reuse timer. Full pools, cooling slots, negative/nonzero timers and the dummy slot are not capacity. Inventory and world delivery retire the same claim once; pressure does not replace an older occupied drop.
- Remote craft inputs remain in the world escrow journal. Client cancellation uses the existing scoped cancel packet and retains the request/mirror until the host responds. `cancelRequested` is retained inside the existing pending remote craft row, including same-origin reconnect. No new packet or client refund authority is introduced.
- A cancel racing a committed craft replays the journal's actual outcome. Unknown/stale owners do not manufacture failure acknowledgements that could resurrect spent inputs.

## Worker and delivery phases

The existing 20-minute recovery deadline now retires incomplete workers and retry waits, not only the gaps between attempts. Every local/host lane cancels its captured request and drops its consumer. Server timeout keeps the sole material escrow and durable failed outcome. Remote deadline requests cancellation; it does not pretend a missing host acknowledgement is permission to refund.

A completed non-null result waiting for world-item capacity remains under its original craft/task owner. Retries attempt delivery, never generation. Existing SP save-on-exit refunds the undelivered craft's original ingredients; server unload preserves world escrow and restart resolves interrupted work through the existing journal. This patch intentionally does not introduce durable generated-output storage.

Metadata HTTP discovery remains in generation workers or the bounded queued registry refresh. Update-thread sharing/stamping reads one immutable volatile transport snapshot: it performs no HTTP and never takes the worker's discovery lock. Existing host transport normalization and final asset-roster validation remain in place.

Inventory closure returns each idle lane independently. Busy lanes keep their material owner; one running lane no longer retains unrelated idle inputs or returns another running lane's mirrors.

## Presentation integration API

`InfiniCraftPlayer.Lifecycle.cs` exposes:

- `TryCancelCraftLane(int laneIndex)` — explicit action, not a draw/read hook.
- `GetCraftLaneOutcome(int laneIndex)` — pure bounded presentation snapshot; `Kind` is `None`, `Succeeded`, `Failed`, `Cancelled`, or `TimedOut`, with at most 240 characters of actual outcome detail. It survives transient clear for 30 seconds and is not material authority.
- `IsCraftLaneWaitingForDelivery(int laneIndex)` — pure local/host ready-result capacity observation.

`CraftLaneStatus` includes localized retained terminal kind plus bounded actual failure/name detail. `IsCraftLaneCancellationPending(int)` observes cancellation awaiting the host; the explicit per-lane button is disabled until that owner resolves. Delivery capacity is observed only for local/host owners, never inferred from a client item pool. `HasPendingCraftRefunds` observes the existing player-wide deferred-refund list; it keeps the panel visible and adds a localized pending-return footer without assigning material to arbitrary lanes. Drawing never calls the cancellation action or authority-refresh hooks.

## Verified boundary

Fresh canonical C# sources built with Windows .NET 8 and existing tModLoader `2026.6.3.6`/ParticleLibrary/Luminance references, zero warnings/errors. Named CPU checks are registered in both `EngineRuntimeChecks.csproj` and the runner:

- 11 craft QoL checks: full pool native refund preservation, three native TagIO reloads, exact prefix/stack, inventory and actual vanilla native world return, cooling/negative timer refusal, partial-merge remainder, metadata HTTP barrier with 250ms nonblocking reads, incomplete deadline/late-result refusal, server durable escrow timeout, completed delivery wait/save-on-exit, bounded terminal presentation, independent-lane cancellation, remote cancel save/reconnect, committed cancel replay, and idle-lane closure.
- Five retained cancellation checks, including withheld HTTP, shared-lock waiters and all-server-owner unload.
- 23 retained persistence checks, including exact origin/session/replay, full-pool output refusal and durable placement returns.
- Targeted Python craft cancellation, multi-dev and MP simulator tests: nine passed. C# contract scanner and project hygiene passed.

RED behavior was observed before fixes for occupied-drop replacement, metadata-lock blocking, incomplete-worker deadline, ready-output owner retirement, partial refund duplication, lost terminal status and idle-lane asymmetry. Cancel replay also reproduced the pre-fix false acknowledgement after a committed success.

No game, GPU, provider/inference, installed-mod update or real peer packet delivery was run. No full suite was run before parent integration. The initial branch fixtures stopped before successful generated proxy allocation; the integrated observer below closes that CPU boundary. Actual vanilla refund allocation is also exercised.

## Integrated station follow-up

- Explicit cancel hit rectangles share one geometry helper with rendering; retained viewport checks include all buttons at 400 px width. English/Russian states distinguish cancellation acknowledgement, local/host delivery space, success, failure, cancellation, timeout and player-wide pending return. The bar remains a craft timer, not model progress/ETA.
- The existing Tk trace panel displays bounded `generationActivity.requests` from its guarded asynchronous health read: opaque backend request ID, profile, exact entered stage or unknown, elapsed/stage elapsed, wait reason, and true/false/unknown network boundary. These IDs are not native lane IDs. Refresh is explicit and labelled as the last health snapshot; changed endpoint/foreign server results are refused. No new activity protocol, model call or native-job correlation was added.
- Fresh Windows .NET 8 linked-canonical build: zero warnings/errors. 59 distinct focused native checks passed (5 integrated, 9 forge, 11 craft QoL, 5 cancellation, 23 persistence, 6 asset lifecycle); 150 scoped desktop/station/backend-activity Python tests passed. No full suite was run.
- Actual installed `ItemLoader.Register`/array setup supplies a real GeneratedItem template in an isolated CPU scope. The unchanged `PostUpdate` → `Item.NewItem` → `GeneratedItem.SetData` path, including actual fixture-PNG roster admission, completes all three lanes in SP and host-server role mode after full/cooling/negative-timer pressure is released. Each case retains the identical ready task past the existing 20-minute deadline, allocates exactly one proxy, preserves exact ID/PNG/gameplay, leaves older occupied drops intact, and produces no refund or regeneration. Server cases assert four remaining unrelated escrow slots plus exact durable success through native ItemIO/TagIO save/unload/reload. Only absent peer transport is intercepted; allocator, hydration, journal and update consumer are not replaced.
- Actual client acknowledgement handles cancel/failure and late committed success across three lanes, refusing foreign/repeated acknowledgements without inventory copies. Retained same-origin pending-cancel save/reconnect and server late-cancel replay checks remain green.
- RED observations covered client-local capacity mislabelling, missing localized pending/outcome presentation, missing cancel hit wiring, missing request-row display, lost unknown-between-stage rows and stale endpoint activity. No new material owner or production commit/escrow mutation was needed.

CPU role-mode and intercepted transport checks are not full game dispatch, actual socket/peer delivery, GPU/image generation, installed-mod packaging or visual GUI acceptance. The WSL Python environments lack tkinter, so the actual Tk window was not launched. Evidence lives in `/home/xipong/.hermes/cache/scratch/icl-qol-integrated/` (fresh build/run logs, exact DLL/source pin, scoped Python XML); harness setup failures are retained separately from final acceptance.
