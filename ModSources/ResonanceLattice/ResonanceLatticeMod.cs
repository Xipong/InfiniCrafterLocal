#nullable enable
using System.IO;
using ResonanceLattice.Core;
using Terraria.ModLoader;

namespace ResonanceLattice;

/// <summary>
/// Mod entrypoint. The lattice itself lives in <see cref="Core"/> and is engine-agnostic:
/// any ModItem, ModProjectile, ModNPC, ModPlayer or ModSystem can talk to it through
/// the static <see cref="ResonanceLattice"/> facade. This class only routes packets.
/// </summary>
public sealed class ResonanceLatticeMod : Mod
{
    public static ResonanceLatticeMod Instance { get; private set; } = null!;

    public override void Load()
    {
        Instance = this;
    }

    public override void Unload()
    {
        Instance = null!;
    }

    public override void HandlePacket(BinaryReader reader, int whoAmI)
    {
        LatticeNet.HandlePacket(reader, whoAmI);
    }
}
