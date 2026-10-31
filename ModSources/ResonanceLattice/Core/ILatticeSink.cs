#nullable enable
using Microsoft.Xna.Framework;

namespace ResonanceLattice.Core;

/// <summary>
/// Reusable consumer contract. Any entity (NPC, tile logic, ModPlayer, another mod's system)
/// that wants to draw charge from the lattice implements this and registers itself with
/// <see cref="ResonanceLattice.RegisterSink"/>. The simulation calls these on the
/// authoritative side only, inside the per-network flow budget.
/// </summary>
public interface ILatticeSink
{
    /// <summary>World position the sink draws charge toward (may move every tick).</summary>
    Vector2 Position { get; }

    /// <summary>Higher priority sinks are served first when the flow budget is tight.</summary>
    int Priority { get; }

    /// <summary>How much charge this sink wants this simulation tick.</summary>
    float RequestCharge(LatticeNetwork network);

    /// <summary>Called with the amount actually delivered (authoritative side only).</summary>
    void OnChargeDelivered(float amount);
}
