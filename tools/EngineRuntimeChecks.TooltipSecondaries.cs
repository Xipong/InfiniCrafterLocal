using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem TooltipSecondaryHost(GeneratedItemData data)
    {
        var host = AttachItem(new GeneratedItem(), new Item { type = 9, stack = 1 }, data);
        typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
        return host;
    }

    private static List<TooltipLine> TooltipSecondaryLines(GeneratedItem host)
    {
        var lines = new List<TooltipLine>();
        host.ModifyTooltips(lines);
        return lines;
    }

    public static void PlayedTooltipSpeedsAreDisplayOnlyBlocksPerSecond()
    {
        WithForgePresentationLanguages(locale => WithPlayer((_, owner) =>
        {
            var data = MobilityConsumptionFixture("", 0);
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 90, JumpBoost = 2f };
            var host = TooltipSecondaryHost(data);
            // AttachItem installs its own definition; mutate only the actual consumer.
            data = host.Data;
            string before = JsonSerializer.Serialize(data);
            string unit = locale == "en-US" ? " blocks/s" : " блоков/с";
            var lines = TooltipSecondaryLines(host);
            string Line(string name) => lines.SingleOrDefault(x => x.Name == name)?.Text ?? "";
            Equal(true, Line("InfiniJumpPrimary").Contains((locale == "en-US" ? "7.5" : "7,5") + unit), "utility jump 2 engine units displays 7.5 blocks/s");
            Equal(before, JsonSerializer.Serialize(data), "utility tooltip conversion never changes authoritative values");
            Equal(false, lines.Any(x => x.Text.Contains("px") || x.Text.Contains("пикс")), "player tooltip excludes pixel units");
            Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 90, JumpBoost = 2f }), "real utility buff admission");
            var snapshot = owner.CaptureGeneratedUtilityBuffPresentation();
            var statuses = GeneratedUtilityBuffStatusView.Build(snapshot, CultureInfo.GetCultureInfo(locale));
            var jump = statuses.Single(x => x.Field == GeneratedUtilityBuffField.JumpBoost);
            Equal(true, jump.Tooltip.Contains((locale == "en-US" ? "+7.5" : "+7,5") + unit), "HUD aggregate and contributions use converted speed");
            Equal(false, jump.Tooltip.Contains("world tick") || jump.Tooltip.Contains("пикс./тик"), "HUD exposes no engine speed unit");
            Equal(2f, owner.CaptureGeneratedUtilityBuffPresentation().Current.JumpBoost, "HUD conversion never changes canonical aggregate");
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec();
            data.Accessory.Enabled = true;
            data.Accessory.MaxRunSpeed = .5f; data.Accessory.JumpSpeed = 1.25f; data.Accessory.AccRunSpeed = 6f;
            data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Id = "wear", Input = RuntimeInputKind.Equipped, Role = RuntimeEntityRole.Primary,
                UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId } } } };
            before = JsonSerializer.Serialize(data);
            lines = TooltipSecondaryLines(host);
            Equal(true, Line("InfiniEquipmentMaxRunSpeed").Contains((locale == "en-US" ? "+1.875" : "+1,875") + unit), "run contribution converts world ticks and world pixels");
            // Item tooltips use the shared compact display format: conversion
            // stays exact in the definition, while ordinary fractions show 3 places.
            Equal(true, Line("InfiniEquipmentJump").Contains((locale == "en-US" ? "+4.688" : "+4,688") + unit), "jump contribution converts units before compact display rounding");
            Equal(true, Line("InfiniEquipmentSprintFloor").Contains((locale == "en-US" ? "22.5" : "22,5") + unit), "sprint floor converts world ticks and world pixels");
            Equal(before, JsonSerializer.Serialize(data), "equipment tooltip conversion is display-only");
            Equal(false, lines.Any(x => x.Text.Contains("px") || x.Text.Contains("пикс")), "equipment tooltip excludes pixel units");
            data.Accessory.Enabled = false;
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniEquipment")), "disabled speed contributions absent");
            data.Armor.Enabled = true; data.Armor.MaxRunSpeed = -.125f; data.Armor.JumpSpeed = .125f;
            lines = TooltipSecondaryLines(host);
            Equal(true, Line("InfiniEquipmentMaxRunSpeed").Contains((locale == "en-US" ? "-0.469" : "-0,469") + unit), "signed armor run contribution keeps sign and localized compact fraction");
            Equal(true, Line("InfiniEquipmentJump").Contains((locale == "en-US" ? "+0.469" : "+0,469") + unit), "armor jump contribution keeps localized compact fraction");
            data.Armor.MaxRunSpeed = -.0001f; data.Armor.JumpSpeed = .0001f;
            before = JsonSerializer.Serialize(data);
            lines = TooltipSecondaryLines(host);
            Equal(true, Line("InfiniEquipmentMaxRunSpeed").Contains((locale == "en-US" ? "-0.000375" : "-0,000375") + unit), "tiny negative speed preserves significant digits instead of zero");
            Equal(true, Line("InfiniEquipmentJump").Contains((locale == "en-US" ? "+0.000375" : "+0,000375") + unit), "tiny positive speed preserves significant digits instead of zero");
            Equal(before, JsonSerializer.Serialize(data), "tiny signed display never rounds authoritative equipment values");
            data.RuntimeProgram.Bindings = Array.Empty<RuntimeBindingSpec>();
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniEquipment")), "inactive equipment data is not advertised");
        }));
    }

    public static void PlayedSecondaryTooltipsDescribeExactDeliveredCombat()
    {
        var rows = JsonNode.Parse(File.ReadAllText(Path.Combine("tools", "fixtures", "played-secondaries-delivered.json")))!.AsArray();
        WithForgePresentationLanguages(locale =>
        {
            foreach (var row in rows)
            {
                var data = GeneratedItemData.FromJson(row!.ToJsonString())
                    ?? throw new InvalidOperationException("played secondary fixture refused: " + ContractJsonDiagnostics.LastError);
                var host = TooltipSecondaryHost(data); data = host.Data;
                var source = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                var action = source.Events.Single();
                string before = JsonSerializer.Serialize(data);
                var lines = TooltipSecondaryLines(host);
                string text = string.Join("\n", lines.Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                Equal(true, text.Contains(locale == "en-US" ? "On projectile hit" : "При попадании снаряда"), "real typed hit occurrence");
                Equal(false, text.Contains("Mods.InfiniCrafterLocal.") || text.Contains("tick") || text.Contains("тик"), "localized seconds without raw engine ticks");
                if (action.ActionCode == RuntimeEventActionCode.DamageArea)
                {
                    Equal(true, text.Contains(locale == "en-US" ? "≈0.167 s" : "≈0,167 с"), "Stonegel exact ten-world-tick delay shown as rounded seconds");
                    Equal(true, text.Contains(locale == "en-US" ? "radius 1.5 blocks" : "радиус 1,5 блоков"), "Stonegel exact center-distance coverage");
                    Equal(true, text.Contains(locale == "en-US" ? "base damage 5" : "базовый урон 5"), "Stonegel authored source10 times .5, not live damageDone");
                    Equal(true, text.Contains(locale == "en-US" ? "directly hit target excluded" : "прямая цель попадания исключена"), "native contact target exclusion disclosed");
                    int radius = action.RadiusPx; action.RadiusPx = 1;
                    string subBlock = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                    Equal(true, subBlock.Contains(locale == "en-US" ? "radius 0.063 blocks" : "радиус 0,063 блоков"), "sub-block radius uses compact localized rounding instead of integer truncation");
                    Equal(1, action.RadiusPx, "rounded block display keeps exact authored pixel radius");
                    action.RadiusPx = radius;
                }
                else
                {
                    Equal(true, text.Contains(locale == "en-US" ? "up to 3" : "до 3"), "Ebongel real bounded child count");
                    Equal(true, text.Contains(locale == "en-US" ? "base damage 3 each" : "базовый урон 3 у каждого"), "literal authored child damage, not guaranteed DPS");
                    Equal(true, text.Contains(locale == "en-US" ? "15 blocks/s" : "15 блоков/с"), "real child launch speed converted");
                    var speedChild = data.RuntimeProgram.TryGetEntity(action.EntityId)!;
                    int updates = speedChild.Collision.ExtraUpdates;
                    speedChild.Collision.ExtraUpdates = 2;
                    string faster = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                    Equal(true, faster.Contains(locale == "en-US" ? "45 blocks/s" : "45 блоков/с"), "per-update launch speed includes extraUpdates in nominal seconds");
                    speedChild.Collision.ExtraUpdates = updates;
                    Equal(true, text.Contains(locale == "en-US" ? "≈0.667 s" : "≈0,667 с"), "real child lifetime seconds");
                    Equal(true, text.Contains(locale == "en-US" ? "initially ignored" : "вначале игнорируется"), "actual target-relative initial contact exclusion shown without claiming permanent immunity");
                    Equal(false, text.Contains(locale == "en-US" ? "radius" : "радиус"), "fragment spawn must not advertise inherited blast");
                }
                Equal(before, JsonSerializer.Serialize(data), "tooltip preserves admitted delivery JSON");
                string[] shown = lines.Select(x => x.Name + "=" + x.Text).ToArray();
                data.Name = "UNTRUSTED [i:1]"; data.Category = "potion"; data.ParentA = "UNTRUSTED";
                Equal(true, shown.SequenceEqual(TooltipSecondaryLines(host).Select(x => x.Name + "=" + x.Text)), "no name/category/parent/prose routing");
                source.Spawn.Enabled = false;
                Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "disabled root cannot advertise secondary combat");
                source.Spawn.Enabled = true;
                source.Damage.Enabled = false;
                Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "non-damaging projectile cannot emit on_hit");
                source.Damage.Enabled = true;
                source.Events = Array.Empty<RuntimeEventActionSpec>();
                Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "unreferenced authored event data not shown");
                source.Events = new[] { action };
                if (action.ActionCode == RuntimeEventActionCode.SpawnEntity)
                {
                    var child = data.RuntimeProgram.TryGetEntity(action.EntityId)!;
                    source.Events = new[] { new RuntimeEventActionSpec {
                        Id = action.Id, Event = action.Event, Action = action.Action,
                        ActionCode = action.ActionCode, EntityId = action.EntityId,
                        Count = action.Count, SpreadRadians = action.SpreadRadians, DamageMultiplier = action.DamageMultiplier,
                    } };
                    Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")),
                        "missing active child combat bases cannot advertise an authored-child fallback");
                    source.Events = new[] { action };
                    string aim = child.Spawn.Aim;
                    source.Events = new[] { new RuntimeEventActionSpec { Id = action.Id, Event = action.Event,
                        Action = action.Action, ActionCode = action.ActionCode, EntityId = action.EntityId,
                        Count = action.Count, SpreadRadians = action.SpreadRadians, DamageMultiplier = action.DamageMultiplier,
                        DamageBasis = action.DamageBasis, KnockbackBasis = action.KnockbackBasis } };
                    child.Spawn.Aim = "none";
                    string still = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                    Equal(false, still.Contains(locale == "en-US" ? "15 blocks/s" : "15 блоков/с"), "none aim cannot advertise inactive scalar launch speed");
                    child.Spawn.Aim = aim; source.Events = new[] { action };
                    child.Events = new[] { new RuntimeEventActionSpec { Id = "child_periodic", Event = RuntimeEventKind.Periodic,
                        Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                        RadiusPx = 24, DamageMultiplier = .5f, PeriodTicks = 60 } };
                    Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondaryArea")), "40 tick child cannot advertise first period at 60");
                    child.Events[0].PeriodTicks = 20;
                    Equal(true, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondaryArea")), "child can advertise period within actual lifetime");
                    child.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
                    child.Events[0].PeriodTicks = 60;
                    Equal(true, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondaryArea")), "charge keep-alive does not use authored lifetime as a hard clock");
                    child.Controller.Code = RuntimeControllerCode.None;
                    child.Events = Array.Empty<RuntimeEventActionSpec>();
                    child.Spawn.Enabled = false;
                    Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "disabled child not advertised");
                    child.Spawn.Enabled = true;
                    action.DamageBasis = RuntimeChildCombatBasis.LiveParent;
                    text = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                    Equal(true, text.Contains(locale == "en-US" ? "inherits event-time parent damage" : "наследует урон родителя в момент события"), "live-parent basis never presented as authored child3");
                    action.DamageBasis = RuntimeChildCombatBasis.AuthoredChild;
                    data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = 0;
                    Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "zero event budget cannot emit children");
                    data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = 32;
                    data.RuntimeProgram.Limits.MaxChildDepth = 0;
                    Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "depth-limited child not advertised");
                }
                else
                {
                    action.Event = RuntimeEventKind.OnExpire;
                    text = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondary")).Select(x => x.Text));
                    Equal(true, text.Contains(locale == "en-US" ? "On projectile expiry" : "При истечении времени жизни снаряда"), "terminal occurrence is not a contact hit");
                    Equal(false, text.Contains(locale == "en-US" ? "directly hit target excluded" : "прямая цель попадания исключена"), "native expiry blast does not exclude a proximity target");
                }
            }
        });
    }

    public static void SecondaryTooltipsRejectUnreachableEventsAndStayBounded()
    {
        WithForgePresentationLanguages(locale =>
        {
            var data = MobilityConsumptionFixture("", 0);
            var host = TooltipSecondaryHost(data); data = host.Data;
            var body = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
            RuntimeEventActionSpec Area(string trigger, string id = "area") => new() { Id = id, Event = trigger,
                Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                RadiusPx = 24, DamageMultiplier = .5f, DelayTicks = 10 };
            data.Gameplay.Damage = 10;
            body.Events = new[] { Area(RuntimeEventKind.OnUse) };
            Equal(true, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondaryArea")), "item on_use is a real non-placement producer");
            var binding = data.RuntimeProgram.Bindings[0];
            binding.UsePolicy.Action.Kind = RuntimeBindingAction.PlaceItem;
            binding.UsePolicy.Action.Placement = new() { TileId = 1 }; binding.UsePolicy.StackCost = 1;
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "placement does not emit item on_use");
            binding.UsePolicy.Action.Kind = RuntimeBindingAction.ApplyItemEffects;
            binding.UsePolicy.Action.Placement = null; binding.UsePolicy.StackCost = 0;
            body.Events = new[] { Area(RuntimeEventKind.OnHit) };
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "contact-disabled item cannot emit on_hit");
            body.Events = new[] { Area(RuntimeEventKind.OnSpawn) };
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "item cannot emit projectile on_spawn");
            body.Events = new[] { Area(RuntimeEventKind.OnUse) };
            body.Events[0].RadiusPx = 0;
            Equal(false, TooltipSecondaryLines(host).Any(x => x.Name.StartsWith("InfiniSecondary")), "zero-radius native no-op hidden");
            body.Events = Enumerable.Range(0, 1000).Select(i => Area(RuntimeEventKind.OnUse, "area" + i)).ToArray();
            var lines = TooltipSecondaryLines(host);
            Equal(true, lines.Count <= 64 && lines.Select(x => x.Name).Distinct().Count() == lines.Count, "global 64-line cap and unique fact names retained");
        });
    }
}
