using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable behavioral probes. Native RED/GREEN is parent-only;
    // no compiler, game loop or GPU execution is authorized in this author lane.
    public static void PlayedStatsUseSecondsCleanPercentAndNativeEquipmentUnits()
    {
        WithForgePresentationLanguages(locale =>
        {
            var data = MobilityConsumptionFixture("", 0);
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 90, MovementSpeed = .15f,
                ManaRegen = 10, LifeRegen = 1, EmitLightStrength = .35f, LightColorName = "white", ExhaustionTicks = 1800 };
            var host = AttachItem(new GeneratedItem(), new Item { type = 9, stack = 1 }, data);
            typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
            List<TooltipLine> Lines()
            {
                var lines = new List<TooltipLine>(); host.ModifyTooltips(lines); return lines;
            }
            string Line(List<TooltipLine> lines, string name) => lines.SingleOrDefault(l => l.Name == name)?.Text ?? "";
            var lines = Lines();
            string fraction = locale == "en-US" ? "1.5 s" : "1,5 с";
            Equal(true, Line(lines, "InfiniMovementPrimary").Contains("+15%"), "float32 percentage is human 15%, not binary expansion");
            Equal(true, Line(lines, "InfiniMovementPrimary").Contains(fraction), "fractional seconds follow UI culture");
            Equal(false, lines.Any(l => l.Text.Contains("ticks") || l.Text.Contains("тиков")), "ordinary player duration text excludes raw ticks");
            Equal(true, Line(lines, "InfiniManaRegenPrimary").Contains("+10")
                && !Line(lines, "InfiniManaRegenPrimary").Contains("/s")
                && !Line(lines, "InfiniManaRegenPrimary").Contains("/с"), "mana regeneration magnitude is a bonus, not a fabricated per-second rate");
            Equal(true, Line(lines, "InfiniLifeRegenPrimary").Contains(locale == "en-US" ? "0.5" : "0,5"), "lifeRegen 1 contributes half HP/s");
            string before = data.ToNetworkJson();
            _ = Lines();
            Equal(before, data.ToNetworkJson(), "presentation preserves exact stored ticks and magnitudes");

            // Captured Hearth contribution: no name/category/parent routing.
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec();
            data.Accessory.Enabled = true; data.Accessory.LifeRegen = 1;
            data.Accessory.ManaRegen = 10; data.Accessory.LightStrength = .35f;
            data.Accessory.MovementSpeed = .15f; data.Accessory.ManaCostReduction = .10f;
            data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Id = "wear", Input = RuntimeInputKind.Equipped,
                UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId } } } };
            lines = Lines();
            Equal(true, Line(lines, "InfiniEquipmentLifeRegen").Contains(locale == "en-US" ? "+0.5" : "+0,5"), "Hearth actual life contribution shown");
            Equal(true, Line(lines, "InfiniEquipmentManaRegen").Contains("+10") && !Line(lines, "InfiniEquipmentManaRegen").Contains("/s") && !Line(lines, "InfiniEquipmentManaRegen").Contains("/с"), "Hearth actual native mana bonus shown");
            Equal(true, Line(lines, "InfiniEquipmentLight").Contains(locale == "en-US" ? "0.35" : "0,35"), "Hearth actual light coefficient shown without float32 artifact");
            Equal(true, Line(lines, "InfiniEquipmentMovement").Contains("+15%"), "movement remains a signed bonus, not an absolute speed");
            Equal(true, Line(lines, "InfiniEquipmentManaCost").Contains("-10%"), "mana reduction remains negative, not an absolute 10 percent cost");
            data.Accessory.Enabled = false;
            Equal(false, Lines().Any(l => l.Name.StartsWith("InfiniEquipment")), "disabled equipment cannot advertise a contribution");
            data.Accessory.Enabled = true; data.RuntimeProgram.Bindings = Array.Empty<RuntimeBindingSpec>();
            Equal(false, Lines().Any(l => l.Name.StartsWith("InfiniEquipment")), "no equipped action cannot advertise a contribution");
        });
    }

    public static void PlayedMobilityCooldownIsIndependentReadOnlyStatus()
    {
        using var nativeMobility = new MobilityConsumptionNativeScope();
        WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            Type view = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.UI.GeneratedMobilityCooldownStatusView")
                ?? throw new InvalidOperationException("missing read-only mobility cooldown HUD view");
            MethodInfo build = view.GetMethod("Build", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? Row() => build.Invoke(null, new object[] { owner.GeneratedMobilityCooldownTicks, Language.ActiveCulture.CultureInfo });
            Equal(true, Row() is null, "no fake cooldown status at zero");
            int[] slots = (int[])player.buffType.Clone();
            Equal(true, owner.TryRunGeneratedMobility(new GameplaySpec { MobilityMode = "recall_home", MobilityCooldownTicks = 1800 }), "real recall starts existing shared mobility cooldown");
            Equal(1f, player.teleportTime, "native Teleport completed");
            object row = Row()!;
            T Field<T>(string name) => (T)row.GetType().GetProperty(name)!.GetValue(row)!;
            Equal(1800, Field<int>("RemainingTicks"), "exact ticks retained for HUD countdown");
            Equal(BuffID.ChaosState, Field<int>("IconBuffType"), "borrowed mobility icon distinct from immutable Exhaustion PNG");
            Equal(true, Field<string>("Tooltip").Contains("30") && !Field<string>("Tooltip").Contains("1800"), "player sees 30 seconds, not ticks");
            Equal(true, Field<string>("Tooltip").Length < 100, "mobility feedback is a concise countdown");
            Equal(0, ((IEnumerable)PresentationExhaustionCapture(owner)).Cast<object>().Count(), "mobility cooldown never creates generated-buff exhaustion");
            Equal(false, owner.TryReserveGeneratedMobilityCooldown(3600), "failed reservation refused by existing owner");
            Equal(1800, owner.GeneratedMobilityCooldownTicks, "failed attempt cannot extend cooldown");
            Equal(false, owner.TryRunGeneratedMobility(new GameplaySpec { MobilityMode = "recall_home", MobilityCooldownTicks = 3600 }), "failed recall refused during cooldown");
            Equal(1800, owner.GeneratedMobilityCooldownTicks, "failed recall cannot extend cooldown");
            Row(); Row();
            Equal(1800, owner.GeneratedMobilityCooldownTicks, "HUD reads never advance timer");
            using (var peers = new ReviewPeers())
            {
                PrepareMobilityConsumptionPlayer(player);
                var data = MobilityConsumptionFixture("recall_home", 0);
                data.Id = "played-mobility-pickaxe"; data.SourceMode = "test_fixture";
                data.Gameplay.PickPower = 35; data.Gameplay.MobilityCooldownTicks = 1800;
                var recall = data.RuntimeProgram.Bindings[0]; recall.Input = RuntimeInputKind.AlternateUse;
                data.RuntimeProgram.Bindings = new[] {
                    new RuntimeBindingSpec { Id = "mine", Input = RuntimeInputKind.PrimaryUse,
                        UsePolicy = new() { ContactDamage = true, Action = new() { Kind = RuntimeBindingAction.UseItemBody, TargetId = data.RuntimeProgram.ItemEntityId } } }, recall };
                peers.Register(data);
                var host = AttachItem(new GeneratedItem(), new Item { type = 9, stack = 1 }, data);
                typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
                bool menu = Terraria.Main.gameMenu, dedicated = Terraria.Main.dedServ;
                try
                {
                    Terraria.Main.gameMenu = false; Terraria.Main.dedServ = false;
                    var lines = new List<TooltipLine>(); host.ModifyTooltips(lines);
                    Equal(true, lines.Single(l => l.Name == "InfiniMobilityCooldownRemaining").Text.Contains("30"), "hybrid pickaxe gets live shared mobility countdown");
                    Equal(false, lines.Any(l => l.Name == "InfiniExhaustionRemaining"), "recall cooldown is not generated-buff exhaustion");
                    recall.UsePolicy.Action.Kind = RuntimeBindingAction.UseItemBody;
                    lines.Clear(); host.ModifyTooltips(lines);
                    Equal(false, lines.Any(l => l.Name == "InfiniMobilityCooldownRemaining"), "body-only/mining action does not advertise a mobility lock");
                    Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 1f }), "mobility cooldown cannot broadly block independent generated buffs");
                    player.pickSpeed = 1f; player.moveSpeed = 1f;
                    typeof(InfiniCraftPlayer).GetMethod("ApplyGeneratedUtilityBuffEffects", TestInstance)!.Invoke(owner, null);
                    Equal(1f, player.pickSpeed, "cooldown applies no mining penalty");
                    Equal(1f, player.moveSpeed, "cooldown applies no movement penalty");
                    Equal(1800, owner.GeneratedMobilityCooldownTicks, "independent buff does not extend mobility cooldown");
                }
                finally { Terraria.Main.gameMenu = menu; Terraria.Main.dedServ = dedicated; }
            }
            Equal(true, slots.SequenceEqual(player.buffType), "HUD does not populate native buff slots or impose debuffs");
            for (int tick = 0; tick < 1800; tick++)
                typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityCooldowns", TestInstance)!.Invoke(owner, null);
            Equal(true, Row() is null, "expired mobility status disappears without fatigue dependency");
            player.SpawnX = player.SpawnY = Terraria.Main.spawnTileX = Terraria.Main.spawnTileY = 0;
            Equal(false, owner.TryRunGeneratedMobility(new GameplaySpec { MobilityMode = "recall_home", MobilityCooldownTicks = 1800 }), "invalid spawn refuses real recall");
            Equal(0, owner.GeneratedMobilityCooldownTicks, "failed recall cannot create a countdown");
        }));
    }
}
