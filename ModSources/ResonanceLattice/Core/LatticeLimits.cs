#nullable enable

namespace ResonanceLattice.Core;

/// <summary>
/// Hard performance/network bounds for the lattice simulation. These cap CPU, memory and
/// packet size; they never change gameplay semantics, only how much of it runs per tick.
/// </summary>
public static class LatticeLimits
{
    /// <summary>Maximum conductor nodes tracked per world.</summary>
    public const int MaxNodesPerWorld = 2048;

    /// <summary>Two nodes link into one network when their centers are at most this far apart (tiles).</summary>
    public const float LinkRangeTiles = 12f;

    /// <summary>Charge one node can hold; network capacity is node count times this.</summary>
    public const float NodeCapacity = 100f;

    /// <summary>Networks may be overcharged up to this fraction of capacity before surging hard-caps.</summary>
    public const float MaxOverchargeFactor = 1.5f;

    /// <summary>Total charge a single network may move to sinks per simulation tick.</summary>
    public const float MaxFlowPerTickPerNetwork = 50f;

    /// <summary>Maximum charge one sink may request per simulation tick.</summary>
    public const float MaxSinkRequestPerTick = 8f;

    /// <summary>Simulation runs every N game ticks (authoritative side only).</summary>
    public const int SimIntervalTicks = 2;

    /// <summary>Ambient daylight trickle per sky-exposed node per simulation tick.</summary>
    public const float AmbientSolarTricklePerTick = 0.05f;

    /// <summary>Surge pulse period (ticks) while a network is overcharged.</summary>
    public const int SurgeIntervalTicks = 45;

    /// <summary>Hostile NPCs within this distance (tiles) of any node can be zapped by a surge.</summary>
    public const float SurgeRadiusTiles = 10f;

    /// <summary>Damage dealt per surge pulse to each target.</summary>
    public const int SurgeDamage = 25;

    /// <summary>Maximum hostile NPCs hit by one surge pulse.</summary>
    public const int MaxSurgeTargetsPerPulse = 4;

    /// <summary>Fraction of capacity a surge drains from the network per pulse.</summary>
    public const float SurgeDrainFraction = 0.25f;

    /// <summary>Charge injected by one Aether Cell.</summary>
    public const float CellChargeAmount = 60f;

    /// <summary>Charge injected by one Stormcaller bolt on tile impact (half of this on NPC hit).</summary>
    public const float BoltChargeAmount = 30f;

    /// <summary>Cooldown (ticks) between lattice charge requests from one client; enforced on both sides.</summary>
    public const int InjectRequestCooldownTicks = 20;

    /// <summary>Maximum distance (tiles) between the requesting player and the injection point.</summary>
    public const float MaxInjectRequestDistanceTiles = 40f;

    /// <summary>Maximum charge a single network request may inject (server-side clamp).</summary>
    public const float MaxInjectPerRequest = 100f;

    /// <summary>Maximum sinks considered per network per simulation tick.</summary>
    public const int MaxSinksPerNetwork = 16;

    /// <summary>Charge drained by a wisp per simulation tick (its sink request cap).</summary>
    public const float WispDrainPerSimTick = 1.5f;

    /// <summary>Charge a wisp can store before it starts zapping.</summary>
    public const float WispMaxStored = 100f;

    /// <summary>Stored charge spent per wisp zap.</summary>
    public const float WispZapCost = 25f;

    /// <summary>Damage dealt by one wisp zap.</summary>
    public const int WispZapDamage = 15;

    /// <summary>Radius (tiles) around a wisp in which it zaps hostiles.</summary>
    public const float WispZapRadiusTiles = 12f;

    /// <summary>Maximum wisps one player may have active.</summary>
    public const int MaxWispsPerPlayer = 2;

    /// <summary>Probe query radius (tiles) and attunement threshold.</summary>
    public const float ProbeQueryRadiusTiles = 30f;
    public const float AttunementThresholdFraction = 0.5f;
    public const int AttunementBuffDurationTicks = 600;
    public const int AttunementManaRegen = 4;

    /// <summary>Bonus damage multiplier against lattice-marked enemies.</summary>
    public const float MarkedDamageMultiplier = 1.3f;
    public const int MarkDurationTicks = 300;

    /// <summary>Charge sync cadence (ticks) and packet entry caps.</summary>
    public const int ChargeSyncIntervalTicks = 15;
    public const int MaxDeltaEntriesPerPacket = 512;
    public const int MaxTopologyNodesPerPacket = 1500;

    /// <summary>Node registry reconciliation cadence (ticks) and discovery radius around players (tiles).</summary>
    public const int ReconcileIntervalTicks = 60;
    public const float PlayerDiscoveryRadiusTiles = 80f;
}
