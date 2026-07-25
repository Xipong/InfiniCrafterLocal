#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Opt-in runtime contract smoke test for a real tModLoader process.
/// It is inert unless INFINI_AGENT_SELFTEST=1 and never mutates world state.
/// The checks exercise the v5 entity/input/event DTO, strict boundaries and
/// presentation references; no weapon-family compatibility path is involved.
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

        GeneratedItemData valid = BuildValidProgram();
        try
        {
            valid.Normalize();
            Check(
                "multi-entity-program-normalizes",
                valid.RuntimeProgram.Entities.Length == 3
                    && valid.RuntimeProgram.Bindings.Single().Target == "workbench_blade"
                    && valid.RuntimeProgram.TryGetEntity("nail") is not null,
                $"entities={valid.RuntimeProgram.Entities.Length}, bindings={valid.RuntimeProgram.Bindings.Length}");
        }
        catch (Exception exception)
        {
            Check("multi-entity-program-normalizes", false, exception.Message);
        }

        GeneratedItemData categoryProbe = BuildValidProgram();
        categoryProbe.Category = "armor";
        (bool firstArmor, bool firstAccessory) = GeneratedItemData.ResolveEquipmentRoles(
            categoryProbe.Gameplay, categoryProbe.Accessory, categoryProbe.Armor);
        categoryProbe.Category = "accessory";
        (bool renamedArmor, bool renamedAccessory) = GeneratedItemData.ResolveEquipmentRoles(
            categoryProbe.Gameplay, categoryProbe.Accessory, categoryProbe.Armor);
        Check(
            "category-cannot-select-equipment-role",
            !firstArmor && !firstAccessory && !renamedArmor && !renamedAccessory,
            $"roles={firstArmor}/{firstAccessory}/{renamedArmor}/{renamedAccessory}");

        RuntimeProgramSpec duplicateInput = BuildValidProgram().RuntimeProgram;
        duplicateInput.Bindings = duplicateInput.Bindings.Concat(new[]
        {
            new RuntimeBindingSpec
            {
                Id = "second_primary",
                Input = RuntimeInputKind.PrimaryUse,
                Action = RuntimeBindingAction.SpawnEntity,
                Target = "nail",
            },
        }).ToArray();
        Check(
            "duplicate-exclusive-input-rejected",
            ThrowsInvalidData(duplicateInput.NormalizeAndValidate),
            "two primary_use bindings must fail closed");

        RuntimeProgramSpec cycle = BuildValidProgram().RuntimeProgram;
        RuntimeEntitySpec nail = cycle.TryGetEntity("nail")!;
        nail.Events = new[]
        {
            new RuntimeEventActionSpec
            {
                Id = "nail_spawns_blade",
                Event = RuntimeEventKind.OnHit,
                Action = "spawn_entity_on_event",
                ActionCode = RuntimeEventActionCode.SpawnEntity,
                EntityId = "workbench_blade",
                Count = 1,
            },
        };
        Check(
            "event-cycle-rejected",
            ThrowsInvalidData(cycle.NormalizeAndValidate),
            "workbench_blade -> nail -> workbench_blade must fail closed");

        ContractJsonDiagnostics.Clear();
        GeneratedItemData? oldApi = GeneratedItemData.FromJson(
            "{\"schemaVersion\":5,\"runtimeApiVersion\":\"infini.runtime-program.v4\"}");
        Check(
            "old-runtime-api-rejected",
            oldApi is null && ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out _),
            oldApi is null ? "rejected" : "unexpectedly accepted");

        ContractJsonDiagnostics.Clear();
        GeneratedItemData? retiredShape = GeneratedItemData.FromJson(
            "{\"schemaVersion\":5,\"runtimeApiVersion\":\"infini.runtime-program.v5\",\"attack\":{}}");
        Check(
            "retired-shape-rejected",
            retiredShape is null && ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out _),
            retiredShape is null ? "rejected" : "unexpectedly accepted");

        ContractJsonDiagnostics.Clear();
        VfxManifestSpec badVfx = VfxManifestSpec.FromJson(
            "{\"schema\":\"infini.vfx.runtime-events.v15\",\"slots\":[{\"futureRendererField\":1}]}");
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
            schema = "infini.tml-runtime-selftest.v2",
            runtimeApi = RuntimeProgramSpec.CurrentApiVersion,
            ok = failures.Count == 0,
            generatedAt = DateTimeOffset.UtcNow,
            checks,
            failures,
        };
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));

        if (failures.Count > 0)
            throw new InvalidOperationException("Infini low-level runtime self-test failed: " + string.Join("; ", failures));

        Mod.Logger.Info($"Infini low-level runtime self-test passed: {reportPath}");
    }

    private static bool ThrowsInvalidData(Action action)
    {
        try
        {
            action();
            return false;
        }
        catch (InvalidDataException)
        {
            return true;
        }
    }

    private static GeneratedItemData BuildValidProgram()
    {
        const string itemId = "workbench_item";
        var blade = ProjectileEntity("workbench_blade", RuntimeEntityKind.OwnerAttachedProjectile, 42);
        blade.Movement = new RuntimeMovementSpec
        {
            Name = "move_forward_then_retract",
            Code = 19,
            Params = new RuntimeParamsSpec { RangeTiles = 6f, DurationTicks = 24 },
        };
        blade.Events = new[]
        {
            new RuntimeEventActionSpec
            {
                Id = "emit_nails",
                Event = RuntimeEventKind.OnHit,
                Action = "spawn_entity_on_event",
                ActionCode = RuntimeEventActionCode.SpawnEntity,
                EntityId = "nail",
                Count = 2,
                SpreadRadians = 0.35f,
            },
        };

        RuntimeEntitySpec nail = ProjectileEntity("nail", RuntimeEntityKind.ChildProjectile, 12);
        nail.Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 };

        return new GeneratedItemData
        {
            SchemaVersion = GeneratedItemData.CurrentSchemaVersion,
            RuntimeApiVersion = RuntimeProgramSpec.CurrentApiVersion,
            Id = "selftest_workbench_blade",
            Name = "Self-Test Workbench Blade",
            Category = "generic",
            SourceMode = "test_fixture",
            Gameplay = new GameplaySpec
            {
                Kind = "weapon",
                DamageClass = "melee",
                Damage = 42,
                Knockback = 4f,
                UseTime = 24,
                UseAnimation = 24,
                UseStyleName = "shoot",
                Width = 32,
                Height = 32,
                MaxStack = 1,
            },
            RuntimeProgram = new RuntimeProgramSpec
            {
                ItemEntityId = itemId,
                Entities = new[]
                {
                    new RuntimeEntitySpec
                    {
                        Id = itemId,
                        Kind = RuntimeEntityKind.ItemBody,
                        VisualRole = "inventory_item",
                        Visual = new RuntimeEntityVisualSpec { Role = "inventory_item", AssetMode = "no_asset" },
                    },
                    blade,
                    nail,
                },
                Bindings = new[]
                {
                    new RuntimeBindingSpec
                    {
                        Id = "primary",
                        Input = RuntimeInputKind.PrimaryUse,
                        Action = RuntimeBindingAction.SpawnEntity,
                        Target = blade.Id,
                    },
                },
                ItemUse = new RuntimeItemUseSpec
                {
                    UseStyle = "shoot",
                    HideUseGraphic = true,
                    DisableMeleeHitbox = true,
                },
            },
            Visual = new VisualSpec
            {
                ObjectType = "workbench_blade",
                SpriteStatus = "test_fixture",
                PreferredCanvasSize = 32,
            },
            VfxManifest = VfxManifestSpec.Empty(),
        };
    }

    private static RuntimeEntitySpec ProjectileEntity(string id, string kind, int damage)
        => new()
        {
            Id = id,
            Kind = kind,
            VisualRole = id,
            Visual = new RuntimeEntityVisualSpec { Role = id, AssetMode = "runtime_geometry" },
            Spawn = new RuntimeSpawnSpec
            {
                Enabled = true,
                Count = 1,
                SpeedPxPerTick = 12f,
                Aim = "cursor",
                Placement = "item_use_origin",
            },
            Damage = new RuntimeDamageSpec
            {
                Enabled = true,
                Damage = damage,
                DamageClass = "melee",
                Knockback = 3f,
            },
            LifetimeTicks = 120,
            Hitbox = new RuntimeHitboxSpec { WidthPx = 16, HeightPx = 16 },
            Collision = new RuntimeCollisionSpec { TileCollide = true, Pierce = 1 },
        };
}
