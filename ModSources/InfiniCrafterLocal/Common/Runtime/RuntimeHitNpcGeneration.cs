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
        Hosts[slot] = npc;
        Tokens[slot] = token;
        npc.netUpdate = true;
    }

    public override void SendExtraAI(NPC npc, BitWriter bitWriter, BinaryWriter binaryWriter)
        => binaryWriter.Write(Get(npc));

    public override void ReceiveExtraAI(NPC npc, BitReader bitReader, BinaryReader binaryReader)
    {
        uint token = binaryReader.ReadUInt32();
        int slot = npc.whoAmI;
        if (slot < 0 || slot >= Hosts.Length) return;
        Hosts[slot] = npc;
        Tokens[slot] = token;
    }

    internal static void Clear()
    {
        Array.Clear(Hosts);
        Array.Clear(Tokens);
        _next = 0;
    }
}
