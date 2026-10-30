#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    // VFX producer proof over the accepted definition. Runtime admission still
    // requires this player's exact active equipment/buff lifetime.
    internal bool HasAirJumpProducer
    {
        get
        {
            if (RuntimeProgram.Bindings.Any(binding => binding.Input == RuntimeInputKind.Equipped
                    && binding.UsePolicy.Action.Kind == RuntimeBindingAction.EquipPassive)
                && (Accessory.Enabled && Accessory.PlayerEffect?.AirJump is not null
                    || Armor.Enabled && Armor.PlayerEffect?.AirJump is not null)) return true;
            var groups = new HashSet<string>(StringComparer.Ordinal);
            foreach (RuntimeBindingSpec binding in RuntimeProgram.Bindings)
            {
                if (binding.UsePolicy.Action.Kind != RuntimeBindingAction.ApplyItemEffects) continue;
                if (binding.UsePolicy.Action.EffectGroupId is string id) groups.Add(id);
                else if (Gameplay.GeneratedBuff?.PlayerEffect?.AirJump is not null) return true;
            }
            if (RuntimeProgram.HeldEffectGroupId is string held) groups.Add(held);
            foreach (RuntimeEntitySpec entity in RuntimeProgram.Entities)
            foreach (RuntimeEventActionSpec action in entity.Events)
                if (action.ActionCode == RuntimeEventActionCode.ApplyGeneratedBuff && action.EffectGroupId is string id)
                    groups.Add(id);
            return (RuntimeProgram.EffectGroups ?? Array.Empty<RuntimeItemEffectGroupSpec>()).Any(group =>
                groups.Contains(group.Id) && group.GeneratedBuff?.PlayerEffect?.AirJump is not null);
        }
    }
}
