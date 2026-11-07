#nullable enable
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

// One native jump slot executes authored movement. It never selects a vanilla
// jump identity, sound or particle style; item VFX has its own authored route.
public sealed class GeneratedAirJump : ExtraJump
{
    public override Position GetDefaultPosition() => AfterBottleJumps;

    public override bool CanStart(Player player)
        => player.TryGetModPlayer<InfiniCraftPlayer>(out var owner) && owner.CanStartGeneratedAirJump();

    public override float GetDurationMultiplier(Player player)
        => player.TryGetModPlayer<InfiniCraftPlayer>(out var owner) ? owner.GeneratedAirJumpDurationMultiplier() : 0f;

    public override void OnStarted(Player player, ref bool playSound)
    {
        playSound = false;
        if (player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.StartGeneratedAirJump(this);
    }

    public override void OnRefreshed(Player player)
    {
        if (player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.RefreshGeneratedAirJumps();
    }

    public override void OnEnded(Player player)
    {
        if (player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.EndGeneratedAirJump();
    }

    public override void UpdateHorizontalSpeeds(Player player)
    {
        if (player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.ApplyGeneratedAirJumpHorizontalSpeeds();
    }
}
