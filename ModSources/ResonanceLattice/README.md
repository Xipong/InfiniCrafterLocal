# Resonance Lattice

A reusable **gameplay library** for Terraria on stable tModLoader (.NET 8), implemented as a
self-contained mod project (`ResonanceLattice.csproj`, SDK `Tomat.Terraria.ModLoader.Sdk`,
`TmlVersion = stable`). It adds an original mechanic: a **placeable energy grid**.

## The mechanic

Players place **Resonant Crystals** (`ResonantConduitItem` → `ResonantCrystalTile`).
Crystals within 12 tiles auto-link into **lattice networks** that carry **aether charge**:

- Charge glows (per-node light) and arcs between linked nodes (custom world rendering).
- Sky-exposed nodes slowly resonate with daylight (ambient trickle).
- **Aether Cells** (items) and **Stormcaller bolts** (projectiles) inject charge.
- A **Lattice Wisp** (NPC) is an `ILatticeSink`: the simulation pays it charge under a flow
  budget; it stores charge and zaps nearby hostiles.
- The **Lattice Probe** reads a network and grants **Lattice Attunement** (mana regen) when
  the network is ≥ 50% charged; bolts also **mark** enemies for +30% damage from all sources.
- Overcharged networks **surge**: periodic lightning pulses that damage hostile NPCs near any
  node, with sound, dust and red-white arcs.

Everything is server-authoritative in multiplayer (clients send validated requests:
distance ≤ 40 tiles, 20-tick cooldown, ≤ 100 charge per request), persisted with the world
(`SaveWorldData`/`LoadWorldData` + join sync via `NetSend`/`NetReceive`), and bounded by
hard limits (`Core/LatticeLimits.cs`: max nodes, per-network flow budget, packet caps,
simulation cadence).

## Using the library from any content

The whole engine-agnostic API is the static facade `Core/ResonanceLattice.cs`:

```csharp
using ResonanceLattice.Core;

// From any ModItem / ModProjectile / ModNPC / ModSystem — safe on clients too:
float applied = ResonanceLattice.InjectCharge(entity.Center, 25f);
float taken   = ResonanceLattice.ConsumeCharge(entity.Center, 10f); // authoritative only
var net       = ResonanceLattice.NetworkNearWorldPos(entity.Center, 20f);

// Become a charge consumer:
public sealed class MyTurret : ModNPC, ILatticeSink
{
    public Vector2 Position => NPC.Center;
    public int Priority => 10;
    public float RequestCharge(LatticeNetwork network) => 2f;
    public void OnChargeDelivered(float amount) { /* spend it */ }
    // in AI: ResonanceLattice.RegisterSink(this); on kill: ResonanceLattice.UnregisterSink(this);
}

// React to topology changes anywhere:
ResonanceLattice.OnTopologyChanged += () => { /* redraw, re-path, ... */ };
```

To add your own conductor, place any tile and call
`ResonanceLattice.NotifyNodePlaced(new Point16(x, y))` / `NotifyNodeRemoved(...)` from its
`PlaceInWorld`/`KillTile` hooks (see `Content/Tiles/ResonantCrystalTile.cs`).

## Layout

```
ResonanceLatticeMod.cs          Mod entrypoint + packet router
Core/                           The reusable library (no demo content references)
  ResonanceLattice.cs           public static facade
  LatticeWorldSystem*.cs        ModSystem: registry, graph, sim, persistence, net, render
  LatticeNet.cs                 packet protocol (request/result/delta/topology)
  LatticeNode.cs / LatticeNetwork.cs / ILatticeSink.cs / LatticeLimits.cs
  LatticePlayer.cs              ModPlayer hook (attunement mana regen)
  LatticeMarkGlobalNPC.cs       GlobalNPC hook (marked enemies take bonus damage)
Content/                        Demo integration: tile, 4 items, projectile, NPC, buff
Localization/                   en-US / ru-RU hjson
```

## Build

Open `ResonanceLattice.csproj` in a tModLoader ModSources folder (or `dotnet build` it with
the Tomat tModLoader SDK available) and enable the mod in-game. No external mod dependencies.

> Note: this checkout was authored without a local tModLoader SDK/NuGet feed, so compilation
> was not run here; every API used was verified against the tModLoader 1.4.4 (stable) source.
