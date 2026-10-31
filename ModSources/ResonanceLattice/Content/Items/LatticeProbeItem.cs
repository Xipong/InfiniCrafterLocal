#nullable enable
using Microsoft.Xna.Framework;
using ResonanceLattice.Content.Buffs;
using ResonanceLattice.Content.NPCs;
using ResonanceLattice.Core;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Items;

/// <summary>
/// Diagnostic tool for the lattice. Left click reads the network near the player (a pure
/// local read of synced state) and reports nodes/charge/capacity in chat; if the network is
/// at least half charged the player gains the attunement buff (faster mana regen).
/// Right click summons a Lattice Wisp bound to the player (server-validated request in
/// multiplayer).
/// </summary>
public sealed class LatticeProbeItem : ModItem
{
    public override void SetDefaults()
    {
        Item.width = 24;
        Item.height = 28;
        Item.maxStack = 1;
        Item.useStyle = ItemUseStyleID.HoldUp;
        Item.useTime = 30;
        Item.useAnimation = 30;
        Item.value = Item.buyPrice(gold: 1);
        Item.rare = ItemRarityID.Green;
    }

    public override bool CanRightClick() => true;

    public override bool? UseItem(Player player)
    {
        bool ownerClient = Main.netMode == NetmodeID.MultiplayerClient && player.whoAmI == Main.myPlayer;
        if (!ownerClient && Main.netMode != NetmodeID.SinglePlayer)
            return null;

        LatticeNetwork? network = ResonanceLattice.NetworkNearWorldPos(player.Center, LatticeLimits.ProbeQueryRadiusTiles);
        if (network is null)
        {
            Main.NewText(Language.GetTextValue("Mods.ResonanceLattice.Chat.NoNetwork"), 200, 120, 120);
            return null;
        }
        Main.NewText(Language.GetTextValue("Mods.ResonanceLattice.Chat.ProbeReport",
            network.Nodes.Count, network.TotalCharge().ToString("0.#"), network.Capacity.ToString("0.#"),
            (network.ChargeFraction * 100f).ToString("0")), 140, 240, 255);

        if (network.ChargeFraction >= LatticeLimits.AttunementThresholdFraction)
            player.AddBuff(ModContent.BuffType<LatticeAttunementBuff>(), LatticeLimits.AttunementBuffDurationTicks);
        return null;
    }

    public override void RightClick(Player player)
    {
        bool ownerClient = Main.netMode == NetmodeID.MultiplayerClient && player.whoAmI == Main.myPlayer;
        if (!ownerClient && Main.netMode != NetmodeID.SinglePlayer)
            return;
        LatticeWispNPC.TrySummon(player, player.Center + new Vector2(0, -24f));
    }

    public override void AddRecipes()
    {
        CreateRecipe()
            .AddIngredient(ItemID.Glass, 10)
            .AddIngredient(ItemID.FallenStar, 2)
            .AddIngredient(ItemID.Wire, 5)
            .AddTile(TileID.WorkBenches)
            .Register();
    }
}
