# Common/Players — station state, MP authority, player runtime state

Player-owned state for the InfiniCraft station and generated item side effects.

- `InfiniCraftPlayer.cs` — shared fields/constants, inventory asset prefetch, registry catch-up.
- `InfiniCraftPlayer.Station.cs` — six explicit station slots (three A/B lanes), per-lane start/refund rules. No hidden “first two inventory items”.
- `InfiniCraftPlayer.CraftState.cs` — LocalGenerator task lifecycle, retries/cache recovery, world-exit refund protection, spawn commit cleanup.
- `InfiniCraftPlayer.MultiDev.cs` — isolated lane-2/lane-3 jobs, exact `llm_2`/`llm_3` pinning, per-request commit/cancel/refund and MP mode sync. Lane 1 remains the proven legacy state machine and pins `llm_1` only while multi-dev is enabled.
- `InfiniCraftPlayer.Multiplayer.cs` — server-authoritative MP craft: client request id + compact refs; server finds/consumes real slots; server sends ACK/FAIL/cancel.
- `InfiniCraftPlayer.Mobility.cs` — generated utility buff and mobility execution.
- `GeneratedHeldItemDrawLayer.cs` — per-instance generated held sprite renderer; MP packet is cheap id+pose only, sprite/style resolve through registry/assets.

Rules:
- MP client cannot commit `GeneratedItemData`; it only requests craft.
- Server must validate generated parent ids against registry and consume real inventory slots.
- World unload must refund/save/clear transient craft state safely.
- A pinned multi-dev lane may retry the same profile but cannot hop to a different profile/fallback.
