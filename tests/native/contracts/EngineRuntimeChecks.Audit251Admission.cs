using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void Audit251PrimaryOwnerAdmission()
    {
        foreach (string effect in new[] { "claim", "keep_alive", "match_lifetime", "lifetime", "held_guard", "animation_guard" })
        foreach (bool primary in new[] { true, false }) {
            var wire = MotionAdmissionWire("ownerControl");
            var owner = MotionAdmissionObject(wire, "ownerControl");
            if (effect == "claim") owner["claimHeldProjectile"] = true;
            else if (effect == "lifetime") owner["lifetime"] = "keep_alive";
            else if (effect == "held_guard") owner["requireHeldItem"] = true;
            else if (effect == "animation_guard") owner["requireItemAnimation"] = true;
            else owner["animation"] = effect;
            if (!primary) {
                var program = wire["runtimeProgram"]!;
                program["primaryEntityId"] = program["itemEntityId"]!.DeepClone();
                program["primaryOwner"] = RuntimeProgramSpec.ItemBodyOwner;
                program["itemUse"]!["hideUseGraphic"] = false;
                foreach (var binding in program["bindings"]!.AsArray())
                    binding!["role"] = RuntimeEntityRole.Secondary;
            }
            string label = $"audit251 {effect}, primary={primary}";
            if (!primary && effect is "claim" or "keep_alive" or "match_lifetime") {
                MotionRefuses(wire, label);
                Equal(true, ContractJsonDiagnostics.LastError?.Message.Contains("primary projectile entity", StringComparison.Ordinal) == true, label + " exact rejection: " + ContractJsonDiagnostics.LastError);
            }
            else MotionAdmits(wire, label);
        }
    }

    private static void Audit251AllRootGraphDepthAdmission()
    {
        foreach (string root in new[] { "on_use", "on_hit", "equipment", "projectile" })
        foreach (int depth in new[] { 3, 4 }) {
            var program = RootSpawnFixture(32, 1).RuntimeProgram;
            var item = program.TryGetEntity(program.ItemEntityId)!;
            var template = program.TryGetEntity("root")!;
            var entities = new System.Collections.Generic.List<RuntimeEntitySpec> { item };
            int count = depth + (root == "projectile" ? 1 : 0);
            for (int i = 0; i < count; i++) {
                var child = JsonSerializer.Deserialize<RuntimeEntitySpec>(JsonSerializer.Serialize(template))!;
                child.Id = "child" + i;
                entities.Add(child);
            }
            program.Entities = entities.ToArray();
            program.ItemUse.HideUseGraphic = false;
            program.ItemUse.DisableMeleeHitbox = false;
            program.PrimaryEntityId = root == "projectile" ? "child0" : item.Id;
            program.PrimaryOwner = root == "projectile" ? RuntimeProgramSpec.ProjectileOwner : RuntimeProgramSpec.ItemBodyOwner;
            program.Bindings = new[] { new RuntimeBindingSpec {
                Id = "activation", Input = root == "equipment" ? RuntimeInputKind.Equipped : RuntimeInputKind.PrimaryUse,
                Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec {
                    ContactDamage = root != "equipment",
                    Action = new RuntimeBindingActionSpec {
                        Kind = root == "equipment" ? RuntimeBindingAction.EquipPassive : root == "projectile" ? RuntimeBindingAction.SpawnEntity : RuntimeBindingAction.UseItemBody,
                        TargetId = program.PrimaryEntityId,
                    },
                },
            } };
            for (int i = 0; i < depth; i++) {
                var source = entities[i + (root == "projectile" ? 1 : 0)];
                var target = entities[i + (root == "projectile" ? 2 : 1)];
                string eventName = source == item ? (root == "equipment" ? RuntimeEventKind.Periodic : root) : RuntimeEventKind.OnSpawn;
                source.Events = new[] { new RuntimeEventActionSpec {
                    Id = "edge" + i, Event = eventName, Action = "spawn_entity_on_event", ActionCode = RuntimeEventActionCode.SpawnEntity,
                    EntityId = target.Id, Count = 1, DamageMultiplier = 1,
                    PeriodTicks = eventName == RuntimeEventKind.Periodic ? 60 : 0,
                    DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
                } };
            }
            string? failure = null;
            try { program.NormalizeAndValidate(); }
            catch (InvalidDataException error) { failure = error.Message; }
            if (depth == 3) Equal<string?>(null, failure, $"audit251 {root} graph depth 3 accepted");
            else Equal(true, failure?.Contains("depth") == true, $"audit251 {root} graph depth 4 rejected: {failure}");
        }
    }
}
