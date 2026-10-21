#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    // Collected by actual functional equip hooks, including modded accessory slots.
    // Inventory, held-only items and vanity never register here.
    private readonly List<GeneratedItem> _reactiveEquipment = new();
    private readonly Dictionary<(string Item, string Action), (uint Start, int Duration)> _reactionCooldowns = new();
    private bool _dispatchingEquipmentReaction;

    internal void RegisterReactiveEquipment(GeneratedItem item)
    {
        if (!_reactiveEquipment.Contains(item)) _reactiveEquipment.Add(item);
    }

    internal GeneratedItem? FindReactiveEquipment(string id)
        => _reactiveEquipment.Find(item => item.Data.Id == id);

    public override void PostHurt(Player.HurtInfo info)
    {
        if (info.Damage > 0 && Player.statLife > 0)
            RunEquipmentReaction(RuntimeEventKind.OnHurt, Player.Center);
    }

    internal void RunEquipmentReaction(string eventName, Vector2 position)
    {
        // Native Player.Hurt (including server receipt of vanilla player-hurt)
        // and NPC.OnKill produce the authoritative utility occurrence. The owner
        // still predicts its utility and records the existing local HUD cooldown;
        // only server-built utility snapshots can survive a later correction.
        bool server = Main.netMode == NetmodeID.Server;
        if ((!server && !InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player)) || Player.dead || !Player.active
            || _dispatchingEquipmentReaction || !float.IsFinite(position.X) || !float.IsFinite(position.Y)
            || eventName is not (RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)) return;
        uint now = Main.GameUpdateCount;
        foreach (var key in new List<(string, string)>(_reactionCooldowns.Keys))
            if (unchecked(now - _reactionCooldowns[key].Start) >= _reactionCooldowns[key].Duration)
                _reactionCooldowns.Remove(key);
        _dispatchingEquipmentReaction = true;
        try
        {
            foreach (GeneratedItem item in _reactiveEquipment.ToArray())
            {
                GeneratedItemData data = item.Data;
                RuntimeEntitySpec? body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId);
                if (body is null || !GeneratedItemRegistryService.IsCurrentWorldData(data)) continue;
                var budget = new RuntimeSpawnBudget(data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
                bool emitted = false;
                foreach (RuntimeEventActionSpec action in body.ActionsFor(eventName))
                {
                    // Projectile/damage reactions keep their owner-only execution.
                    // Only this accepted utility-group action has a server replica.
                    if (server && action.ActionCode != RuntimeEventActionCode.ApplyGeneratedBuff) continue;
                    // Identity survives copy/slot replacement; bounded table never evicts a live timer.
                    var key = (data.Id, action.Id);
                    if (action.ReactionCooldownTicks is < 6 or > 3600 || _reactionCooldowns.ContainsKey(key)
                        || _reactionCooldowns.Count >= 128) continue;
                    _reactionCooldowns[key] = (now, action.ReactionCooldownTicks);
                    item.ExecuteEquipmentReaction(Player, body, action, position, budget);
                    emitted = true;
                }
                if (emitted && !Main.dedServ)
                    global::InfiniCrafterLocal.Common.VFX.InfiniItemVfxRuntime.EmitAndSyncEvent(Player, data, body.Id, eventName, position);
            }
        }
        finally { _dispatchingEquipmentReaction = false; }
    }

    // This notification can only arrive from the server. Clients cannot claim kills.
    internal static void HandleEquipmentKillPacket(BinaryReader reader)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        int world = reader.ReadInt32();
        Vector2 position = new(reader.ReadSingle(), reader.ReadSingle());
        if (world == Main.worldID && float.IsFinite(position.X) && float.IsFinite(position.Y)
            && position.X >= 0 && position.Y >= 0 && position.X <= Main.maxTilesX * 16f && position.Y <= Main.maxTilesY * 16f)
            Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().RunEquipmentReaction(RuntimeEventKind.OnEnemyKill, position);
    }
}
