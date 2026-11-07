#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

internal readonly record struct GeneratedReactionCooldownStatus(
    string ItemId, string ActionId, string Event, string ItemName, string SpritePath, int RemainingTicks);

public sealed partial class InfiniCraftPlayer
{
    internal IReadOnlyList<GeneratedReactionCooldownStatus> CaptureGeneratedReactionCooldowns()
    {
        var rows = new List<GeneratedReactionCooldownStatus>();
        if (Player is not { active: true, dead: false }) return rows.AsReadOnly();
        uint now = Main.GameUpdateCount;
        var seen = new HashSet<(string Item, string Action)>();
        // Functional native equip hooks alone populate this frame's roster. A
        // retained timer does not make inventory, vanity or unequipped gear active.
        foreach (var item in _reactiveEquipment)
        {
            GeneratedItemData data = item.Data;
            if (!GeneratedItemRegistryService.IsCurrentWorldData(data)) continue;
            RuntimeEntitySpec? body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId);
            if (body is null) continue;
            foreach (RuntimeEventActionSpec action in body.Events)
            {
                var key = (data.Id, action.Id);
                if (action.Event is not (RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)
                    || !seen.Add(key) || !_reactionCooldowns.TryGetValue(key, out var timer)) continue;
                uint elapsed = unchecked(now - timer.Start);
                if (elapsed >= timer.Duration) continue;
                rows.Add(new(data.Id, action.Id, action.Event, data.Name, data.Visual.SpritePath,
                    timer.Duration - (int)elapsed));
            }
        }
        // Value records detach display from mutable definitions and live timers.
        // Reads deliberately do not prune or advance the bounded owner dictionary.
        return rows.AsReadOnly();
    }
}
