using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ReactiveBuffTooltipShowsAcceptedEffectsAndCooldown()
    {
        using var actors = new SwarmRuntimeScope();
        WithForgePresentationLanguages(locale =>
        {
            var item = ReactiveUtilityItem(delay: 30, exhaustion: 120);
            typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(item, new TooltipProbeMod());
            var action = item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId)!.Events.Single();
            string before = item.Data.ToNetworkJson();
            var lines = new List<TooltipLine>(); item.ModifyTooltips(lines);
            Equal(true, lines.Any(l => l.Name.StartsWith("InfiniMovementReaction") && l.Text.Contains("+25%")
                && l.Text.Contains(locale == "ru-RU" ? "1 с" : "1 s")), "actual reactive buff magnitude and duration visible");
            Equal(true, lines.Any(l => l.Name.StartsWith("InfiniReactionCooldown")), "reaction's own cooldown visible before activation");
            Equal(true, lines.Any(l => l.Name.StartsWith("InfiniReactionDelay") && l.Text.Contains(locale == "ru-RU" ? "0,5" : "0.5")), "actual scheduler delay in localized seconds");
            Equal(true, lines.Any(l => l.Name.StartsWith("InfiniExhaustionReaction")), "source exhaustion remains distinct from reaction cooldown");
            Equal(before, item.Data.ToNetworkJson(), "tooltip projection never modifies accepted action or buff");
            action.Event = RuntimeEventKind.OnEnemyKill;
            lines.Clear(); item.ModifyTooltips(lines);
            Equal(true, lines.Any(l => l.Name.StartsWith("InfiniMovementReaction")
                && l.Text.Contains(locale == "ru-RU" ? "убийств" : "killed")), "effect label follows exact kill event");
            item.Data.RuntimeProgram.Bindings = System.Array.Empty<RuntimeBindingSpec>();
            lines.Clear(); item.ModifyTooltips(lines);
            Equal(false, lines.Any(l => l.Name.Contains("Reaction")), "unreachable equipment event cannot advertise a buff");
        });
    }
}
