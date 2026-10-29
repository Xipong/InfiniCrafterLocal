#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void NeutralLightBuffColorsDoNotDuplicateCombat()
    {
        WithPlayer((_, generated) =>
        {
            foreach (string color in new[] { "red", "blue" })
            {
                Equal(true, generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec
                {
                    DurationTicks = 120,
                    EmitLightStrength = 0f,
                    LightColorName = color,
                    Combat = new GeneratedCombatBuffSpec
                    {
                        AttackSpeedPercent = 25f,
                        DamageClass = "generic",
                    },
                }), "applying a same-effect unlit combat buff");
            }
            var snapshot = generated.CaptureGeneratedUtilityBuffPresentation();
            Equal(1, snapshot.Entries.Count, "unlit color is not a distinct combat effect");
            Equal(25f, snapshot.Current.AttackSpeed, "unlit color cannot stack +25% attack speed twice");

            foreach (string color in new[] { "red", "blue" })
                Equal(true, generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec
                {
                    DurationTicks = 120, EmitLightStrength = 0.5f, LightColorName = color,
                    Combat = new GeneratedCombatBuffSpec { AttackSpeedPercent = 25f, DamageClass = "generic" },
                }), "lit buff still applies");
            snapshot = generated.CaptureGeneratedUtilityBuffPresentation();
            Equal(3, snapshot.Entries.Count, "two physically distinct lit colors remain distinct");
        });
    }

    private static void GameplayRootNativeBuffsKeepAll48()
    {
        foreach (int count in new[] { 16, 17, 48 })
        {
            GeneratedItemData data = GeneratedItemData.Placeholder();
            data.Gameplay.ExtraBuffs = Enumerable.Range(0, count).Select(index => new BuffEntrySpec
            {
                BuffCode = BuffID.ObsidianSkin,
                BuffTime = 120 + index,
            }).ToArray();
            data.Normalize();
            Equal(count, data.Gameplay.ExtraBuffs.Length, "root gameplay must retain native buff tail count=" + count);
            Equal(120 + count - 1, data.Gameplay.ExtraBuffs[^1].BuffTime, "last authored duration remains unchanged");
        }

        var invalid = GeneratedItemData.Placeholder();
        invalid.Gameplay.ExtraBuffs = Enumerable.Range(0, 49).Select(_ => new BuffEntrySpec
        {
            BuffCode = BuffID.ObsidianSkin, BuffTime = 120,
        }).ToArray();
        bool refused = false;
        try { invalid.Normalize(); }
        catch (InvalidDataException) { refused = true; }
        Equal(true, refused, "49th root native buff must be rejected rather than silently lost");
    }

    private static void SustainedControlAndManaGateBeforeEvents()
    {
        using var scope = new SwarmRuntimeScope();
        using var kill = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill), Type.EmptyTypes)!,
            (Action<Projectile>)(projectile => { projectile.active = false; }));
        var data = BeamFixture();
        Player owner = Terraria.Main.player[0];
        var flag = typeof(GeneratedProjectile).GetField("_spawnEventRan", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var age = typeof(GeneratedProjectile).GetField("_age", BindingFlags.Instance | BindingFlags.NonPublic)!;

        GeneratedProjectile cancelled = BeamHost(data);
        owner.channel = false;
        MaterialClock(100);
        cancelled.AI();
        Equal(false, cancelled.Projectile.active, "released beam is retired before any authored update");
        Equal(false, (bool)flag.GetValue(cancelled)!, "released beam cannot run on_spawn");
        Equal(0, (int)age.GetValue(cancelled)!, "released beam cannot advance periodic event clock");

        GeneratedProjectile exhausted = BeamHost(data, slot: 1);
        owner.statMana = 0;
        owner.manaFlower = false;
        owner.HeldItem.mana = 10;
        owner.HeldItem.useTime = 4;
        MaterialClock(200);
        exhausted.AI(); // Native item-use charge covers the first active update.
        Equal(true, (bool)flag.GetValue(exhausted)!, "initial paid item use still admits on_spawn");
        int before = (int)age.GetValue(exhausted)!;
        MaterialClock(204);
        exhausted.AI();
        Equal(false, exhausted.Projectile.active, "failed recurring mana charge terminates beam");
        Equal(before, (int)age.GetValue(exhausted)!, "no last free periodic update after failed mana payment");
        Equal(false, exhausted.Projectile.friendly, "failed mana projectile cannot deal native contact damage");
    }
}
