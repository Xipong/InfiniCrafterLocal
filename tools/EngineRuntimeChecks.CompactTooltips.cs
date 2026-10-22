using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void CompactTooltipsKeepInputsAndLockoutsAndExpandWithEitherShift()
    {
        using var actors = new SwarmRuntimeScope();
        KeyboardState previous = Terraria.Main.keyState;
        try
        {
            WithForgePresentationLanguages(locale =>
            {
                var host = ReactiveUtilityItem(delay: 30, exhaustion: 120);
                typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
                host.Data.Accessory.MaxLife = 20;
                host.Data.Accessory.FallDamageImmune = true;
                Terraria.Main.keyState = new KeyboardState();
                List<TooltipLine> Lines()
                {
                    var lines = new List<TooltipLine>(); host.ModifyTooltips(lines); return lines;
                }
                string before = host.Data.ToNetworkJson();
                var compact = Lines();
                Equal(true, compact.Any(l => l.Name == "InfiniEquipmentMaxLife" && l.Text.Contains("+20")), "compact keeps numeric equipment stats");
                Equal(false, compact.Any(l => l.Name == "InfiniEquipmentNoFallDamage"), "compact defers passive flags to details");
                Equal(true, compact.Any(l => l.Name.StartsWith("InfiniReactionCooldown")), "compact retains passive reaction cooldown");
                Equal(true, compact.Any(l => l.Name.StartsWith("InfiniExhaustionReaction")), "compact retains passive exhaustion");
                Equal(false, compact.Any(l => l.Name.StartsWith("InfiniMovementReaction")), "compact defers passive effect details");
                Equal(true, compact.Any(l => l.Name == "InfiniExpandDetails" && l.Text.Contains("Shift")
                    && !l.Text.Contains("Mods.InfiniCrafterLocal.")), "localized expansion affordance");
                foreach (Keys key in new[] { Keys.LeftShift, Keys.RightShift })
                {
                    Terraria.Main.keyState = new KeyboardState(key);
                    var expanded = Lines();
                    Equal(true, expanded.Any(l => l.Name == "InfiniEquipmentNoFallDamage"), "expanded exposes passive equipment flag");
                    Equal(true, expanded.Any(l => l.Name.StartsWith("InfiniMovementReaction")), "either Shift exposes real passive magnitude");
                    Equal(true, expanded.Any(l => l.Name.StartsWith("InfiniReactionDelay")), "expanded includes exact scheduling details");
                    Equal(false, expanded.Any(l => l.Name == "InfiniExpandDetails"), "expanded does not ask for expansion");
                }
                Terraria.Main.keyState = new KeyboardState();
                Equal(true, compact.Select(l => l.Name + l.Text).SequenceEqual(Lines().Select(l => l.Name + l.Text)), "release Shift returns to compact without stale state");
                Equal(before, host.Data.ToNetworkJson(), "expansion never changes authoritative item data");

                var data = MobilityConsumptionFixture("recall_home", 1);
                data.Gameplay.ManaCost = 17;
                data.Gameplay.UseConditionMode = "grounded";
                data.Gameplay.MobilityCooldownTicks = 1800;
                data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Concat(new[] {
                    new RuntimeBindingSpec { Id = "alternate", Input = RuntimeInputKind.AlternateUse,
                        UsePolicy = new() { StackCost = 0, Action = new() { Kind = RuntimeBindingAction.ApplyItemEffects,
                            TargetId = data.RuntimeProgram.ItemEntityId } } }
                }).ToArray();
                host = TooltipSecondaryHost(data);
                compact = Lines();
                foreach (string suffix in new[] { "Primary", "Alternate" })
                {
                    Equal(true, compact.Any(l => l.Name == "InfiniInput" + suffix && l.Text.Contains("17")), "compact keeps each input's mana and stack contract");
                    Equal(true, compact.Any(l => l.Name == "InfiniCondition" + suffix), "compact keeps each input's use conditions");
                    Equal(true, compact.Any(l => l.Name == "InfiniMobility" + suffix && l.Text.Contains("30")), "compact keeps each input's cooldown");
                }
            });
        }
        finally { Terraria.Main.keyState = previous; }
    }
}
