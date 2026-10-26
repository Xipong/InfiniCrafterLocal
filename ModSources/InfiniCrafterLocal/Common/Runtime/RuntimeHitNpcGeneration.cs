#nullable enable
using System;
using System.IO;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Runtime;

// Server-issued NPC incarnation. Unlike the slot or type, Transform retains this token.
public sealed class RuntimeHitNpcGeneration : GlobalNPC
{
    private static uint _next;
    private static readonly NPC?[] Hosts = new NPC?[Main.maxNPCs];
    private static readonly uint[] Tokens = new uint[Main.maxNPCs];

    internal static uint Get(NPC npc)
    {
        int slot = npc.whoAmI;
        return slot >= 0 && slot < Hosts.Length && ReferenceEquals(Hosts[slot], npc)
            ? Tokens[slot] : 0;
    }

    public override void OnSpawn(NPC npc, IEntitySource source)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient) return;
        int slot = npc.whoAmI;
        if (slot < 0 || slot >= Hosts.Length) return;
        uint token = ++_next;
        if (token == 0) token = ++_next;
        RuntimeNpcEffects.Forget(npc);
        Hosts[slot] = npc;
        Tokens[slot] = token;
        npc.netUpdate = true;
    }

    public override void UpdateLifeRegen(NPC npc, ref int damage)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient) return;
        int penalty = RuntimeNpcEffects.GetTotals(npc).Regen;
        if (penalty == 0) return;
        if (npc.lifeRegen > 0) npc.lifeRegen = 0;
        npc.lifeRegen -= penalty;
        damage = Math.Max(damage, Math.Max(1, penalty / 2));
    }

    public override void ModifyIncomingHit(NPC npc, ref NPC.HitModifiers modifiers)
        => modifiers.Defense.Flat += RuntimeNpcEffects.GetTotals(npc).Defense;

    public override void ModifyHitPlayer(NPC npc, Player target, ref Player.HurtModifiers modifiers)
        => modifiers.SourceDamage *= RuntimeNpcEffects.GetTotals(npc).Contact;

    public override void ModifyHitNPC(NPC npc, NPC target, ref NPC.HitModifiers modifiers)
        => modifiers.SourceDamage *= RuntimeNpcEffects.GetTotals(npc).Contact;

    public override void PostAI(NPC npc)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient) return;
        float retention = RuntimeNpcEffects.GetTotals(npc).Retention;
        if (retention == 1f) return;
        var previous = npc.velocity;
        npc.velocity *= retention;
        // No client-side NPC-velocity authority: publish ongoing changes through
        // the existing native NPC channel (including its native netSpam budget).
        if (Main.netMode == NetmodeID.Server && npc.velocity != previous) npc.netUpdate = true;
    }

    public override void OnKill(NPC npc) => RuntimeNpcEffects.Forget(npc);

    public override void SendExtraAI(NPC npc, BitWriter bitWriter, BinaryWriter binaryWriter)
    {
        binaryWriter.Write(Get(npc));
        RuntimeNpcEffects.Send(npc, binaryWriter);
    }

    public override void ReceiveExtraAI(NPC npc, BitReader bitReader, BinaryReader binaryReader)
    {
        uint token = binaryReader.ReadUInt32();
        int slot = npc.whoAmI;
        if (slot < 0 || slot >= Hosts.Length) return;
        Hosts[slot] = npc;
        Tokens[slot] = token;
        RuntimeNpcEffects.Receive(npc, binaryReader);
    }

    internal static void Clear()
    {
        RuntimeNpcEffects.Clear();
        Array.Clear(Hosts);
        Array.Clear(Tokens);
        _next = 0;
    }
}
