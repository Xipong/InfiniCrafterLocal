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

`CraftLaneStatus` includes retained terminal detail. Cancel buttons and localized delivery-wait/cancel-pending labels are left to the UI integration owner; presentation must not call the action or authority-refresh methods while drawing.

## Verified boundary

Fresh canonical C# sources built with Windows .NET 8 and existing tModLoader `2026.6.3.6`/ParticleLibrary/Luminance references, zero warnings/errors. Named CPU checks are registered in both `EngineRuntimeChecks.csproj` and the runner:

- 11 craft QoL checks: full pool native refund preservation, three native TagIO reloads, exact prefix/stack, inventory and actual vanilla native world return, cooling/negative timer refusal, partial-merge remainder, metadata HTTP barrier with 250ms nonblocking reads, incomplete deadline/late-result refusal, server durable escrow timeout, completed delivery wait/save-on-exit, bounded terminal presentation, independent-lane cancellation, remote cancel save/reconnect, committed cancel replay, and idle-lane closure.
- Five retained cancellation checks, including withheld HTTP, shared-lock waiters and all-server-owner unload.
- 23 retained persistence checks, including exact origin/session/replay, full-pool output refusal and durable placement returns.
- Targeted Python craft cancellation, multi-dev and MP simulator tests: nine passed. C# contract scanner and project hygiene passed.

RED behavior was observed before fixes for occupied-drop replacement, metadata-lock blocking, incomplete-worker deadline, ready-output owner retirement, partial refund duplication, lost terminal status and idle-lane asymmetry. Cancel replay also reproduced the pre-fix false acknowledgement after a committed success.

No game, GPU, provider/inference, installed-mod update or real peer packet delivery was run. No full suite was run before parent integration. Generated proxy allocation after capacity returns is not certified as successful registered-content delivery by these CPU fixtures; actual vanilla refund allocation is exercised.
