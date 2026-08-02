# Read-Only Architecture Review: Multi-Lane InfiniCraftPlayer

## Executive Summary

The current `InfiniCraftPlayer` is a **single-lane** craft state machine with one A/B input pair, one in-flight generation task, one server request ID, and one set of refund/escrow state. Implementing 2-3 independent craft lanes (per `/multidevcraft`) requires converting every piece of per-player craft state into per-lane arrays, threading a `lane` parameter through the station UI, MP packet handlers, escrow logic, and world-exit refund paths.

The good news: `GeneratorClient.Prepare` already carries `llmProfileId` and `multiDevCraft` fields in the wire format (GeneratorClient.cs:200-232), so the LLM-profile routing is already partially plumbed. The bad news: the state machine, packet protocol, and UI are all hard-coded to one lane, and the coupling is deep.

---

## Current Single-Lane State Map

All state lives in `InfiniCraftPlayer` (Common/Players/InfiniCraftPlayer.cs):

| State | Type | Purpose |
|-------|------|---------|
| `InputA`, `InputB` | `Item` | Station input slots (lines 106-107) |
| `_request`, `_task` | `PreparedGenerationRequest?`, `Task?` | In-flight generation (lines 48-49) |
| `_ticksLeft`, `_elapsedTicks`, `_totalCraftTicks` | `int` | Progress timers (lines 50-52) |
| `_awaitingServerCommit`, `_serverCraftWaitTicks` | `bool`, `int` | MP client wait state (lines 55-56) |
| `_serverRequestId`, `_label` | `string` | Dedupe + display (lines 61-62) |
| `_retryWaitTicks`, `_generationAttempt`, … | `int` | Retry backoff (lines 57-60) |
| `_craftSoundVolumeSnapshot` etc. | `float` | Audio guard (lines 79-84) |
| `_pendingStationEscrowOperationId` etc. | `string`, `byte`, `int`, `Item`, `int` | Escrow in-flight (lines 63-67) |
| `_stationEscrowResultCache`, `_stationEscrowResultOrder` | `Dict`, `Queue` | Escrow dedupe/replay (lines 75-76) |
| `_deferredExitRefunds`, `_pendingRefundSavedForWorldExit` | `List<Item>`, `bool` | World-exit refund backup (lines 77-78) |

Key derived properties:
- `HasPendingCraft` (line 109): `_request is not null || _task is not null || _awaitingServerCommit`
- `CanStartStationCraft` (line 115): `!HasPendingCraft && !HasPendingStationEscrowOperation && HasInputA && HasInputB`

---

## Minimal Safe Patch Map

### 1. State Arrays (InfiniCraftPlayer.cs)

Convert every per-craft field to `T[]` indexed by lane (0..N-1, N=2 or 3):

```csharp
private const int MaxCraftLanes = 3; // configurable

private GeneratorClient.PreparedGenerationRequest?[] _requests = new ...;
private Task<GeneratedItemData?>?[] _tasks = new ...;
private int[] _ticksLefts = new int[MaxCraftLanes];
private int[] _elapsedTickss = new int[MaxCraftLanes];
private int[] _totalCraftTickss = new int[MaxCraftLanes];
private int[] _announceTicks = new int[MaxCraftLanes];
private bool[] _lateMessageShowns = new bool[MaxCraftLanes];
private bool[] _awaitingServerCommits = new bool[MaxCraftLanes];
private int[] _serverCraftWaitTickss = new int[MaxCraftLanes];
private int[] _retryWaitTickss = new int[MaxCraftLanes];
private int[] _generationAttempts = new int[MaxCraftLanes];
private int[] _lastRetryNoticeTicks = new int[MaxCraftLanes];
private int[] _lastGeneratorOfflineNoticeTicks = new int[MaxCraftLanes];
private string[] _serverRequestIds = new string[MaxCraftLanes];
private string[] _labels = new string[MaxCraftLanes];
private float[] _craftSoundVolumeSnapshots = new float[MaxCraftLanes];
...
private Item[] InputA = new Item[MaxCraftLanes];  // per-lane
private Item[] InputB = new Item[MaxCraftLanes];  // per-lane
```

Escrow state must also be per-lane:
```csharp
private string[] _pendingStationEscrowOperationIds = new string[MaxCraftLanes];
private byte[] _pendingStationEscrowActions = new byte[MaxCraftLanes];
private int[] _pendingStationEscrowIndexes = new int[MaxCraftLanes];
private Item?[] _pendingStationEscrowItems = new Item?[MaxCraftLanes];
private int[] _pendingStationEscrowWaitTicks = new int[MaxCraftLanes];
private Dictionary<string, StationEscrowResultCacheEntry>[] _laneEscrowResultCaches = new ...;
private Queue<string>[] _laneEscrowResultOrders = new ...;
```

### 2. Property Changes

- `HasPendingCraft` → `HasPendingCraft(int lane)` (per-lane) + `HasAnyPendingCraft` (any lane)
- `CanStartStationCraft` → `CanStartStationCraft(int lane)` (per-lane)
- `HasAnyInput` → `HasAnyInput(int lane)`
- `HasInputA`/`HasInputB` → parameterized
- `CraftProgress` → `CraftProgress(int lane)`
- `IsWaitingForModel` → `IsWaitingForModel(int lane)`
- `IsWaitingForRetry` → `IsWaitingForRetry(int lane)`
- `CraftLabel` → `CraftLabel(int lane)`

### 3. Method Signatures Requiring `lane` Parameter

| File | Method | Line |
|------|--------|------|
| InfiniCraftPlayer.CraftState.cs | `BeginCraft(request, label)` → `BeginCraft(lane, request, label)` | 150 |
| InfiniCraftPlayer.CraftState.cs | `StartGenerationTask(reason)` → `StartGenerationTask(lane, reason)` | 178 |
| InfiniCraftPlayer.CraftState.cs | `ScheduleEarlyRetry(reason)` → `ScheduleEarlyRetry(lane, reason)` | 190 |
| InfiniCraftPlayer.CraftState.cs | `ScheduleGeneratorOfflineRetry(reason)` → `ScheduleGeneratorOfflineRetry(lane, reason)` | 202 |
| InfiniCraftPlayer.CraftState.cs | `FailCraft(localMessage, remoteMessage)` → `FailCraft(lane, localMessage, remoteMessage)` | 352 |
| InfiniCraftPlayer.CraftState.cs | `SpawnGeneratedItem(data)` → `SpawnGeneratedItem(lane, data)` | 368 |
| InfiniCraftPlayer.CraftState.cs | `ClearCraft()` → `ClearCraft(lane)` (or `ClearAllCrafts()`) | 556 |
| InfiniCraftPlayer.CraftState.cs | `AbortTransientCraftForWorldExit()` → iterate all lanes | 399 |
| InfiniCraftPlayer.CraftState.cs | `CaptureAudioSettingsSnapshot()` → `CaptureAudioSettingsSnapshot(lane)` | 419 |
| InfiniCraftPlayer.Multiplayer.cs | `BeginRemoteServerCraft(a, b)` → `BeginRemoteServerCraft(lane, a, b)` | 34 |
| InfiniCraftPlayer.Multiplayer.cs | `BeginServerAuthoritativeCraft(request, label, requestId)` → add `lane` | 92 |
| InfiniCraftPlayer.Multiplayer.cs | `SendStationEscrowRequest(action, index, item)` → `SendStationEscrowRequest(lane, action, index, item)` | 117 |
| InfiniCraftPlayer.Multiplayer.cs | `HandleRequestServerCraftPacket(reader, whoAmI)` — must read lane from packet | 711 |
| InfiniCraftPlayer.Multiplayer.cs | `HandleCancelServerCraftPacket(reader, whoAmI)` — must read lane | 803 |
| InfiniCraftPlayer.Multiplayer.cs | `HandleCraftCommitResult(requestId, success, itemName, message)` → check per-lane | 669 |
| InfiniCraftPlayer.Multiplayer.cs | `SendCraftCommitResult(toClient, requestId, success, itemName, message)` → include lane | 1173 |
| InfiniCraftPlayer.Multiplayer.cs | `SendStationEscrowResult(toClient, operationId, action, index, success, message)` → include lane | 1159 |
| InfiniCraftPlayer.Multiplayer.cs | `HandleStationEscrowRequestPacket(reader, whoAmI)` — must read lane | 373 |
| InfiniCraftPlayer.Multiplayer.cs | `HandleStationEscrowResultPacket(reader, whoAmI)` — must read lane | 361 |
| InfiniCraftPlayer.Multiplayer.cs | `TryDepositServerMouseItem(index, itemRef, ...)` → `TryDepositServerMouseItem(lane, index, itemRef, ...)` | 968 |
| InfiniCraftPlayer.Multiplayer.cs | `TryTakeServerEscrowToMouse(index, ...)` → add `lane` | 1010 |
| InfiniCraftPlayer.Multiplayer.cs | `TryReturnServerEscrowToInventory(index, ...)` → add `lane` | 1035 |
| InfiniCraftPlayer.Multiplayer.cs | `TryReturnAllServerEscrowToInventory(...)` → add `lane` | 1055 |
| InfiniCraftPlayer.Multiplayer.cs | `TryTakeServerEscrowInput(index, itemRef, ...)` → add `lane` | 1078 |
| InfiniCraftPlayer.Station.cs | `TryPutMouseItemIntoInput(index)` → `TryPutMouseItemIntoInput(lane, index)` | 33 |
| InfiniCraftPlayer.Station.cs | `TryTakeInputToMouse(index)` → add `lane` | 75 |
| InfiniCraftPlayer.Station.cs | `TryClearInputToInventory(index)` → add `lane` | 92 |
| InfiniCraftPlayer.Station.cs | `TryClearAllInputsToInventory()` → add `lane` or all lanes | 106 |
| InfiniCraftPlayer.Station.cs | `TryStartCraftFromStation()` → `TryStartCraftFromStation(lane)` | 118 |
| InfiniCraftPlayer.Station.cs | `ReturnStationInputs()` → add `lane` or all lanes | 170 |
| InfiniCraftPlayer.Station.cs | `InputSlot(index)` → `InputSlot(lane, index)` | 163 |
| InfiniCraftPlayer.Station.cs | `RefundIngredients()` → `RefundIngredients(lane)` | 190 |
| InfiniCraftPlayer.cs | `Initialize()` → init all lanes | 35 |
| InfiniCraftPlayer.cs | `OnEnterWorld()` → restore all lanes | 43 |
| InfiniCraftPlayer.cs | `SaveData(tag)` → save all lanes | 59 |
| InfiniCraftPlayer.cs | `LoadData(tag)` → load all lanes | 79 |
| InfiniCraftPlayer.cs | `PostUpdate()` → iterate all lanes | 222 |

### 4. Packet Protocol Changes (InfiniNetPacketIds.cs)

Every MP packet that touches craft state must carry a `lane` byte:

| Packet | ID | Current wire | New wire |
|--------|----|-------------|----------|
| `RequestServerCraft` | 5 | `requestId, aRef, bRef` | `lane, requestId, aRef, bRef` |
| `CraftCommitResult` | 4 | `requestId, success, itemName, message` | `lane, requestId, success, itemName, message` |
| `CancelServerCraft` | 12 | `requestId, reason?` | `lane, requestId, reason?` |
| `RequestStationEscrow` | 14 | `operationId, action, index, itemRef?` | `lane, operationId, action, index, itemRef?` |
| `StationEscrowResult` | 15 | `operationId, action, index, success, message` | `lane, operationId, action, index, success, message` |

**Backward compatibility**: Old clients sending packets without lane byte will deserialize incorrectly. If backward compat is needed, lane must be appended at the end with a default of 0, or a protocol version bump is required.

### 5. UI Changes (InfiniCraftStationUISystem.cs)

- `DrawInventoryStation` currently draws one panel at a fixed position. Needs to draw N panels, either stacked vertically or in a grid.
- `HandleMouse` needs to know which panel/lane the mouse is over.
- Each panel needs its own `CanStartStationCraft(lane)`, `CraftProgress(lane)`, `CraftLabel(lane)`, etc.
- Panel positioning: with 3 lanes, 3 × 190px = 570px height — may need horizontal layout or collapsible panels.

### 6. World Exit System (InfiniCraftWorldExitSystem.cs)

- `AbortTransientCraftForWorldExit()` (InfiniCraftPlayer.CraftState.cs:399) currently handles one lane. Must iterate all lanes:
  ```csharp
  for (int lane = 0; lane < MaxCraftLanes; lane++)
      AbortTransientCraftForWorldExit(lane);
  ```

### 7. Save/Load (InfiniCraftPlayer.CraftState.cs)

- `SaveData` (line 59) saves `infiniPendingCraftRefunds` and `infiniPendingCraftLabel` for one lane. Must iterate all lanes and prefix keys with lane index.
- `LoadData` (line 79) must restore all lanes.
- `PendingRefundTagsForSave` (line 107) checks `HasPendingCraft && _request is not null` — needs lane.

---

## Traps and Edge Cases

### Trap 1: `HasPendingCraft` as a global guard (HIGH SEVERITY)

**Location**: `InfiniCraftPlayer.cs:109`, used in `InfiniCraftPlayer.Station.cs:35,77,94,108,120`, `InfiniCraftPlayer.Multiplayer.cs:36,119,149,749`, `InfiniCraftPlayer.CraftState.cs:152,465`

If `HasPendingCraft` remains a single boolean (any lane), then having a craft running in lane 0 blocks all input/escrow operations in lanes 1 and 2. This defeats the purpose of multi-lane. **Must become per-lane.**

### Trap 2: Station escrow blocked by craft in another lane (HIGH SEVERITY)

**Location**: `InfiniCraftPlayer.Multiplayer.cs:119`
```csharp
if (Main.netMode != NetmodeID.MultiplayerClient || HasPendingCraft || HasPendingStationEscrowOperation)
    return false;
```

A player depositing items into lane 2's escrow should not be blocked by lane 0 being mid-craft. The `HasPendingCraft` and `HasPendingStationEscrowOperation` checks must be per-lane.

### Trap 3: Server-side `HasPendingCraft` check in `HandleRequestServerCraftPacket` (HIGH SEVERITY)

**Location**: `InfiniCraftPlayer.Multiplayer.cs:749`
```csharp
if (modPlayer.HasPendingCraft)
{
    SendCraftCommitResult(whoAmI, requestId, false, "", "у игрока уже есть активный InfiniCraft");
    return;
}
```

If a client has craft in lane 0 and sends a craft request for lane 1, the server rejects it. **Must check per-lane:** `modPlayer.HasPendingCraft(lane)`.

### Trap 4: Packet wire format lacks lane ID (HIGH SEVERITY)

**Location**: All packet handlers in `InfiniCraftPlayer.Multiplayer.cs` and `InfiniNetPacketIds.cs`

No packet currently carries a lane identifier. Adding a `lane` byte to the beginning of each packet is the minimal change. Without it, the server cannot route craft requests to the correct lane.

### Trap 5: `ClearCraft()` wipes all state (MEDIUM SEVERITY)

**Location**: `InfiniCraftPlayer.CraftState.cs:556-577`

Currently clears every field. With per-lane state, `ClearCraft()` must become `ClearCraft(int lane)` that only clears one lane's fields, leaving others untouched. A separate `ClearAllCrafts()` can wipe everything (for world unload).

### Trap 6: `_stationEscrowResultCache` is per-player, not per-lane (MEDIUM SEVERITY)

**Location**: `InfiniCraftPlayer.cs:75-76`

Escrow result cache uses `operationId` as key. Since operation IDs are GUIDs, they're globally unique, so the cache technically works across lanes. However, `ApplyStationEscrowResult` (line 324) checks `_pendingStationEscrowOperationId`, `_pendingStationEscrowAction`, `_pendingStationEscrowIndex` — these must be per-lane, otherwise an escrow result for lane 2 could be misapplied to lane 0.

### Trap 7: `InputSlot(index)` maps 0→A, 1→B (MEDIUM SEVERITY)

**Location**: `InfiniCraftPlayer.Station.cs:163-167`

Server-side escrow methods (`TryDepositServerMouseItem`, `TryTakeServerEscrowToMouse`, etc.) call `InputSlot(index)` where index is 0 or 1. With multi-lane, the server needs to know which lane's A/B slots to operate on. The method must become `InputSlot(lane, index)`.

### Trap 8: `PostUpdate` runs single craft tick loop (MEDIUM SEVERITY)

**Location**: `InfiniCraftPlayer.CraftState.cs:222-349`

The entire `PostUpdate` method is a single state machine. It must be refactored into a `TickCraftLane(int lane)` method called in a loop over all lanes.

### Trap 9: Audio snapshot arrays (LOW SEVERITY)

**Location**: `InfiniCraftPlayer.cs:79-84`, `InfiniCraftPlayer.CraftState.cs:419-426`

Audio snapshots are per-craft. With concurrent crafts in multiple lanes, each lane needs its own snapshot so that one lane finishing doesn't restore audio that another lane is still using.

### Trap 10: `IsServerAuthoritativeCraft` property (LOW SEVERITY)

**Location**: `InfiniCraftPlayer.Multiplayer.cs:652`
```csharp
private bool IsServerAuthoritativeCraft => Main.netMode == NetmodeID.Server && !_awaitingServerCommit && !string.IsNullOrWhiteSpace(_serverRequestId);
```

Must become `IsServerAuthoritativeCraft(int lane)`.

### Trap 11: `AbortTransientCraftForWorldExit` double-refund (MEDIUM SEVERITY)

**Location**: `InfiniCraftPlayer.CraftState.cs:399-416`

Already handles `_pendingRefundSavedForWorldExit` to avoid double-refund. With multiple lanes, each lane needs its own `_pendingRefundSavedForWorldExit` flag, or the check must be per-lane.

### Trap 12: `GeneratorClient.Prepare` already supports multi-dev (GOOD)

**Location**: `GeneratorClient.cs:200-232`

The `Prepare` method already accepts `llmProfileId` and `multiDevCraft` parameters and serializes them into the wire JSON. This means the LLM-profile routing is already implemented on the Generator side. The C# side just needs to pass the correct `llmProfileId` per lane (e.g., `"llm_1"`, `"llm_2"`, `"llm_3"`).

### Trap 13: `ServerCommittedCraftRequests` dedupe key (LOW SEVERITY)

**Location**: `InfiniCraftPlayer.Multiplayer.cs:729,850-851`

Key is `"servercraft:" + whoAmI + ":" + requestId`. Since `requestId` is a per-request GUID (generated in `BeginRemoteServerCraft` at line 41), dedupe works correctly across lanes as long as each lane generates its own GUID. No change needed here, but the packet must carry the lane so the server knows which lane to associate the request with.

### Trap 14: UI panel layout and screen real estate (LOW SEVERITY)

**Location**: `InfiniCraftStationUISystem.cs:45-114`

Three 392×190 panels = 570px vertical or 1176px horizontal. The current positioning logic (`Math.Clamp(Main.screenWidth - width - 28, ...)`) places one panel at the right edge. Multi-panel layout needs rework — either stack vertically with adjusted Y positions or arrange horizontally.

### Trap 15: `PlayerHasCore` UI gate (LOW SEVERITY)

**Location**: `InfiniCraftStationUISystem.cs:210-217`

UI is shown if player has `InfiniCore` item OR has station state. Multi-dev craft may need a different gate (e.g., a different item or config flag). This is a design decision, not a technical trap.

---

## Recommended Implementation Order

1. **State arrays** — Convert all per-craft fields to `T[MaxCraftLanes]` arrays in `InfiniCraftPlayer.cs`
2. **Per-lane properties** — Add `lane` parameter to all `HasPendingCraft`, `CanStartStationCraft`, etc.
3. **Per-lane methods** — Add `lane` parameter to `BeginCraft`, `ClearCraft`, `FailCraft`, `SpawnGeneratedItem`, etc.
4. **Packet protocol** — Add `lane` byte to all MP packet wire formats and handlers
5. **Station methods** — Add `lane` parameter to `TryPutMouseItemIntoInput`, `TryTakeInputToMouse`, etc.
6. **PostUpdate loop** — Refactor into `TickCraftLane(int lane)` called per lane
7. **World exit** — Iterate all lanes in `AbortTransientCraftForWorldExit`
8. **Save/Load** — Per-lane refund serialization
9. **UI** — Multi-panel draw and mouse handling
10. **Escrow** — Per-lane escrow state and server-side routing

---

## Files to Patch (Read-Only Review — No Edits Made)

| File | Lines | What Changes |
|------|-------|-------------|
| `Common/Players/InfiniCraftPlayer.cs` | 21-105 | State fields → arrays; constants for MaxCraftLanes |
| `Common/Players/InfiniCraftPlayer.CraftState.cs` | 35-579 | All craft lifecycle methods → per-lane; SaveData/LoadData → all lanes; PostUpdate → loop |
| `Common/Players/InfiniCraftPlayer.Multiplayer.cs` | 34-1254 | All MP methods → per-lane; packet handlers → read/write lane byte; escrow → per-lane |
| `Common/Players/InfiniCraftPlayer.Station.cs` | 33-261 | All station methods → per-lane; InputSlot → InputSlot(lane, index) |
| `Common/UI/InfiniCraftStationUISystem.cs` | 45-163 | Multi-panel draw; per-lane mouse handling |
| `Common/InfiniNetPacketIds.cs` | 8-26 | Document lane byte in wire format (no ID changes needed) |
| `Common/Systems/InfiniCraftWorldExitSystem.cs` | 21-27 | Call per-lane abort for all lanes |

---

## Conclusion

The architecture is **well-structured for single-lane** but requires a systematic per-lane conversion. The deepest traps are:
1. `HasPendingCraft` used as a global guard (blocks cross-lane independence)
2. Packet wire format lacking lane ID (protocol breaking change)
3. Server-side `HandleRequestServerCraftPacket` rejecting cross-lane crafts

The `GeneratorClient.Prepare` method already supports `llmProfileId` and `multiDevCraft`, which is a strong signal that the backend is ready — the C# mod just needs to thread the lane parameter through to it.

Estimated patch surface: ~15 files, ~800 lines of changes, mostly mechanical array conversions plus packet protocol updates.
