#nullable enable
using System.ComponentModel;
using Terraria.ModLoader;
using Terraria.ModLoader.Config;

namespace InfiniCrafterLocal.Common.Config;

public sealed class InfiniParentTooltipServerConfig : ModConfig
{
    public override ConfigScope Mode => ConfigScope.ServerSide;

    // An explicit server policy: clients can report arbitrary text and craft a
    // shared world recipe influenced by it. It is never a verified native fact.
    [DefaultValue(false)]
    public bool TrustClientParentTooltips = false;

    internal static bool Enabled
    {
        get { try { return ModContent.GetInstance<InfiniParentTooltipServerConfig>()?.TrustClientParentTooltips == true; } catch { return false; } }
    }
}
