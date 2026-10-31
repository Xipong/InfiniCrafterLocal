#nullable enable
using System;
using Microsoft.Xna.Framework;
using ResonanceLattice.Core;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.NPCs;

/// <summary>
/// A small friendly wisp summoned by the Lattice Probe. It hovers over the most charged
/// node of the nearest network and registers itself as an <see cref="ILatticeSink"/>, so
/// the lattice simulation pays it charge under the normal flow budget; the stored charge
/// is then spent zapping nearby hostile NPCs. Demonstrates NPC integration with the library
/// through the public sink contract instead of any direct graph access.
/// NPC AI (and therefore lattice mutation) runs on the server in multiplayer.
/// </summary>
public sealed class LatticeWispNPC : ModNPC, ILatticeSink
{
    public ref float AI_Owner => ref NPC.ai[0];
    public ref float AI_Stored => ref NPC.ai[1];
    public ref float AI_Timer => ref NPC.ai[2];

    private bool _registeredAsSink;

    public override void SetStaticDefaults()
    {
        Main.npcFrameCount[Type] = 1;
    }

    public override void SetDefaults()
    {
        NPC.width = 22;
        NPC.height = 22;
        NPC.aiStyle = -1; // fully custom AI
        NPC.friendly = true;
        NPC.damage = 0;
        NPC.defense = 4;
        NPC.lifeMax = 80;
        NPC.knockBackResist = 0.3f;
        NPC.noGravity = true;
        NPC.noTileCollide = true;
        NPC.HitSound = SoundID.NPCHit1;
        NPC.DeathSound = SoundID.NPCDeath6;
        NPC.value = 0f;
    }

    /// <summary>
    /// Summon a wisp for a player. Single player/server spawns directly with a per-player
    /// cap; a multiplayer client asks the server, which validates distance and the cap.
    /// </summary>
    internal static bool TrySummon(Player player, Vector2 worldPos)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            LatticeNet.SendSummonWispRequest(worldPos);
            return true; // request sent; result arrives via packet
        }
        if (CountWispsOf(player.whoAmI) >= LatticeLimits.MaxWispsPerPlayer)
            return false;
        int index = NPC.NewNPC(player.GetSource_ItemUse(player.SelectedItem),
            (int)worldPos.X, (int)worldPos.Y, ModContent.NPCType<LatticeWispNPC>(), 0, player.whoAmI);
        if (index >= 0 && index < Main.maxNPCs)
        {
            Main.npc[index].velocity = new Vector2(0f, -2f);
            Main.npc[index].netUpdate = true;
        }
        return index >= 0 && index < Main.maxNPCs;
    }

    internal static int CountWispsOf(int ownerWhoAmI)
    {
        int count = 0;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC npc = Main.npc[i];
            if (npc.active && npc.type == ModContent.NPCType<LatticeWispNPC>() && (int)npc.ai[0] == ownerWhoAmI)
                count++;
        }
        return count;
    }

    public override void AI()
    {
        int owner = (int)AI_Owner;
        if (owner < 0 || owner >= Main.maxPlayers || !Main.player[owner].active)
        {
            NPC.active = false;
            return;
        }

        if (ResonanceLattice.IsAuthoritative && !_registeredAsSink)
        {
            ResonanceLattice.RegisterSink(this);
            _registeredAsSink = true;
        }
        else if (!ResonanceLattice.IsAuthoritative && _registeredAsSink)
        {
            ResonanceLattice.UnregisterSink(this);
            _registeredAsSink = false;
        }

        AI_Timer++;

        // Hover around the most charged node of the nearest network; otherwise follow the owner.
        LatticeNetwork? network = ResonanceLattice.NetworkNearWorldPos(NPC.Center, LatticeLimits.LinkRangeTiles * 2f);
        Vector2 target;
        if (network is not null && network.Nodes.Count > 0)
        {
            LatticeNode best = network.Nodes[0];
            for (int i = 1; i < network.Nodes.Count; i++)
                if (network.Nodes[i].Charge > best.Charge)
                    best = network.Nodes[i];
            float angle = AI_Timer * 0.05f;
            target = best.WorldCenter + new Vector2((float)Math.Cos(angle), (float)Math.Sin(angle)) * 40f;
        }
        else
        {
            target = Main.player[owner].Center + new Vector2(0f, -60f);
        }

        Vector2 desired = target - NPC.Center;
        if (desired.Length() > 8f)
            NPC.velocity += Vector2.Normalize(desired) * 0.35f;
        else
            NPC.velocity *= 0.9f;
        if (NPC.velocity.Length() > 5f)
            NPC.velocity = Vector2.Normalize(NPC.velocity) * 5f;
        NPC.rotation = NPC.velocity.X * 0.05f;
        NPC.spriteDirection = NPC.velocity.X >= 0f ? 1 : -1;

        // Spend stored charge zapping nearby hostiles.
        if (ResonanceLattice.IsAuthoritative && AI_Stored >= LatticeLimits.WispZapCost && AI_Timer % 30 == 0)
        {
            NPC? hostile = FindHostileInRange();
            if (hostile is not null)
            {
                int direction = hostile.Center.X >= NPC.Center.X ? 1 : -1;
                hostile.SimpleStrikeNPC(LatticeLimits.WispZapDamage, direction);
                AI_Stored -= LatticeLimits.WispZapCost;
                SoundEngine.PlaySound(SoundID.Thunder, hostile.Center);
                for (int i = 0; i < 10; i++)
                {
                    Dust dust = Dust.NewDust(NPC.Center, 0, 0, DustID.Electric, 0f, 0f, 100, default, 1.2f);
                    dust.velocity = Vector2.Lerp(Vector2.Zero, hostile.Center - NPC.Center, Main.rand.NextFloat()) * 0.2f + Main.rand.NextVector2Circular(1f, 1f);
                    dust.noGravity = true;
                }
            }
        }

        if (Main.rand.NextBool(6))
        {
            Dust dust = Dust.NewDust(NPC.position, NPC.width, NPC.height, DustID.Enchanted_Pink, 0f, 0f, 100, default, 0.8f);
            dust.noGravity = true;
            dust.velocity *= 0.2f;
        }
    }

    private NPC? FindHostileInRange()
    {
        float range = LatticeLimits.WispZapRadiusTiles * 16f;
        NPC? best = null;
        float bestDist = range;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC npc = Main.npc[i];
            if (!npc.active || npc.friendly || npc.townNPC || npc.dontTakeDamage)
                continue;
            float d = Vector2.Distance(NPC.Center, npc.Center);
            if (d < bestDist)
            {
                bestDist = d;
                best = npc;
            }
        }
        return best;
    }

    public override void OnKill()
    {
        if (_registeredAsSink)
        {
            ResonanceLattice.UnregisterSink(this);
            _registeredAsSink = false;
        }
    }

    // ------------------------------------------------------------------
    // ILatticeSink — the simulation drains the network into the wisp here.
    // ------------------------------------------------------------------

    Vector2 ILatticeSink.Position => NPC.Center;

    int ILatticeSink.Priority => 5;

    float ILatticeSink.RequestCharge(LatticeNetwork network)
        => Math.Min(LatticeLimits.WispDrainPerSimTick, network.TotalCharge() * 0.25f);

    void ILatticeSink.OnChargeDelivered(float amount)
    {
        if (!ResonanceLattice.IsAuthoritative)
            return;
        AI_Stored = Math.Min(AI_Stored + amount, LatticeLimits.WispMaxStored);
    }
}
