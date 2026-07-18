#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Opt-in runtime contract smoke test for a real tModLoader process.
/// It is completely inert unless INFINI_AGENT_SELFTEST=1. The test exercises
/// compiled C# normalization, strict JSON rejection and child-family transforms;
/// it never creates an item/projectile or changes a world/player state.
/// </summary>
public sealed class InfiniAgentContractSelfTestSystem : ModSystem
{
    private const string EnabledEnv = "INFINI_AGENT_SELFTEST";
    private const string ReportEnv = "INFINI_AGENT_SELFTEST_REPORT";

    public override void PostSetupContent()
    {
        if (!string.Equals(Environment.GetEnvironmentVariable(EnabledEnv), "1", StringComparison.Ordinal))
            return;

        var checks = new List<object>();
        var failures = new List<string>();

        void Check(string id, bool ok, string detail)
        {
            checks.Add(new { id, ok, detail });
            if (!ok)
                failures.Add($"{id}: {detail}");
        }

        var item = new GeneratedItemData { Attack = new AttackSpec { DustSpawnDenom = 0 } };
        item.Normalize();
        Check("dust-zero-remains-disabled", item.Attack.DustSpawnDenom == 0, $"actual={item.Attack.DustSpawnDenom}");

        var mismatchedCategory = new GeneratedItemData
        {
            Category = "armor",
            Gameplay = new GameplaySpec { Kind = "weapon" },
            Accessory = new AccessorySpec { Enabled = false },
            Armor = new ArmorSpec { Enabled = false },
        };
        mismatchedCategory.Normalize();
        (bool mismatchArmor, bool mismatchAccessory) = GeneratedItemData.ResolveEquipmentRoles(
            mismatchedCategory.Gameplay,
            mismatchedCategory.Accessory,
            mismatchedCategory.Armor);
        mismatchedCategory.Category = "accessory";
        (bool renamedArmor, bool renamedAccessory) = GeneratedItemData.ResolveEquipmentRoles(
            mismatchedCategory.Gameplay,
            mismatchedCategory.Accessory,
            mismatchedCategory.Armor);
        Check(
            "category-cannot-select-equipment-role",
            !mismatchArmor && !mismatchAccessory && !renamedArmor && !renamedAccessory,
            $"armor={mismatchArmor}/{renamedArmor}, accessory={mismatchAccessory}/{renamedAccessory}");

        var sentryParent = new AttackSpec
        {
            RuntimeFamily = GeneratedRuntimeFamilyPolicy.Sentry,
            SecondaryLifetimeTicks = 40,
            MaxChildProjectiles = 8,
            MaxChildDepth = 1,
        };
        var sentryShot = new AttackSpec();
        GeneratedChildSpecPolicy.ConfigureSentryShot(sentryShot, sentryParent);
        Check(
            "sentry-shot-not-root",
            sentryShot.RuntimeFamily == GeneratedRuntimeFamilyPolicy.Shoot && sentryShot.MaxChildProjectiles == 0 && sentryShot.MaxChildDepth == 0,
            $"family={sentryShot.RuntimeFamily}, children={sentryShot.MaxChildProjectiles}, depth={sentryShot.MaxChildDepth}");

        var chargeParent = new AttackSpec
        {
            RuntimeFamily = GeneratedRuntimeFamilyPolicy.ChargeRelease,
            Delivery = "cast",
            ChannelUse = true,
        };
        var released = new AttackSpec();
        GeneratedChildSpecPolicy.ConfigureChargeReleasedShot(released, chargeParent);
        Check(
            "charge-shot-not-holdout",
            released.RuntimeFamily == GeneratedRuntimeFamilyPolicy.Cast && !released.ChannelUse && released.ChargePowerMultiplier == 1f,
            $"family={released.RuntimeFamily}, channel={released.ChannelUse}, power={released.ChargePowerMultiplier}");

        ContractJsonDiagnostics.Clear();
        GeneratedItemData? badItem = GeneratedItemData.FromJson("{\"attack\":{\"futureExecutableField\":1}}");
        Check(
            "strict-generated-item-json",
            badItem is null && ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out _),
            badItem is null ? "rejected" : "unexpectedly accepted");

        ContractJsonDiagnostics.Clear();
        VfxManifestSpec badVfx = VfxManifestSpec.FromJson("{\"slots\":[{\"futureRendererField\":1}]}");
        Check(
            "strict-vfx-json",
            !badVfx.HasSlots && ContractJsonDiagnostics.TryGet("VfxManifestSpec.FromJson", out _),
            badVfx.HasSlots ? "unexpectedly accepted" : "rejected");

        string configured = Environment.GetEnvironmentVariable(ReportEnv) ?? "";
        string reportPath = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Main.SavePath, "InfiniCrafterLocal", "agent_contract_selftest.json")
            : Path.GetFullPath(configured);
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath) ?? Main.SavePath);
        var report = new
        {
            schema = "infini.tml-runtime-selftest.v1",
            ok = failures.Count == 0,
            generatedAt = DateTimeOffset.UtcNow,
            checks,
            failures,
        };
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));

        if (failures.Count > 0)
            throw new InvalidOperationException("Infini agent runtime self-test failed: " + string.Join("; ", failures));

        Mod.Logger.Info($"Infini agent runtime self-test passed: {reportPath}");
    }
}
