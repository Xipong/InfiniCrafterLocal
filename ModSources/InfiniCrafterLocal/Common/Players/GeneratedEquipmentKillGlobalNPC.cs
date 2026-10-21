#nullable enable
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

public sealed class GeneratedEquipmentKillGlobalNPC : GlobalNPC
{
    public override void OnKill(NPC npc)
    {
        // Native OnKill runs exactly on the authority that owns NPC death.
        if (Main.netMode == NetmodeID.MultiplayerClient || npc.friendly || npc.townNPC
            || NPCID.Sets.CountsAsCritter[npc.type] || npc.type == NPCID.TargetDummy
            || npc.realLife >= 0 && npc.realLife != npc.whoAmI
            || npc.lastInteraction < 0 || npc.lastInteraction >= Main.maxPlayers) return;
        Player owner = Main.player[npc.lastInteraction];
        if (!owner.active || owner.dead) return;
        // The server applies only canonical utility-group actions; owner-only
        // projectile/damage reactions remain behind the existing notification.
        owner.GetModPlayer<InfiniCraftPlayer>().RunEquipmentReaction(RuntimeEventKind.OnEnemyKill, npc.Center);
        if (Main.netMode != NetmodeID.SinglePlayer)
        {
            var packet = InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(InfiniNetPacketIds.EquipmentEnemyKill);
            packet.Write(Main.worldID);
            packet.Write(npc.Center.X); packet.Write(npc.Center.Y);
            packet.Send(owner.whoAmI);
        }
    }
}
