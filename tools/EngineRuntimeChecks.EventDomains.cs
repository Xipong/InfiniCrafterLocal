using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static NPC EventDomainNpc(int slot, Vector2 center, float x)
    {
        var npc = new NPC { whoAmI = slot, active = true, life = 1000, lifeMax = 1000,
            defense = 0, width = 20, height = 20, HideStrikeDamage = true };
        npc.Center = center + new Vector2(x, 0);
        return npc;
    }

    private static void NearestDamageRetainsTheSingleCenterNativeAction()
    {
        var oldMetrics = Terraria.Main.SceneMetrics;
        var oldRandom = Terraria.Main.rand;
        try
        {
            Terraria.Main.SceneMetrics = new SceneMetrics();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            foreach (bool itemBody in new[] { false, true })
            foreach (string eventName in new[] { "on_hit", "on_crit" })
            foreach (int count in new[] { 1, 2, 3, 12 })
            {
                using var scope = new SwarmRuntimeScope();
                Vector2 center = new(1600, 1600);
                float[] distances = { 4, 100, 20, 175, -50, 128, 1 };
                for (int i = 0; i < distances.Length; i++)
                    Terraria.Main.npc[i] = EventDomainNpc(i, center, distances[i]);
                Terraria.Main.npc[6].friendly = true;
                Equal(true, Terraria.Main.npc[5].CanBeChasedBy(), "boundary target is chaseable");
                var data = SwarmGameplayFixture();
                var entity = data.RuntimeProgram.TryGetEntity("root")!;
                data.Gameplay.Damage = 100;
                data.Gameplay.DamageClass = "generic";
                if (itemBody) entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
                // Deserialize the old wire selected by the new Author alias.
                var action = JsonSerializer.Deserialize<RuntimeEventActionSpec>(JsonSerializer.Serialize(new {
                    id = "nearest", action = "chain_damage_on_event", actionCode = 4,
                    @event = eventName, count, rangeTiles = 8, damageMultiplier = 0.5,
                }), new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!;
                action.NormalizeAndValidate();
                var owner = Terraria.Main.player[0];
                var control = EventDomainNpc(20, center, 500);
                owner.ApplyDamageToNPC(control, 50, 0f, 1, false, Terraria.ModLoader.DamageClass.Generic, false);
                Equal(true, control.life < 1000, "real native damage positive control");
                RuntimeProgramExecutor.ExecuteAction(data, entity, action, owner,
                    owner.GetSource_Misc("nearest_domain_probe"), center, Vector2.UnitX,
                    Terraria.Main.npc[0], 777, 0, new RuntimeSpawnBudget(8));
                for (int i = 0; i < distances.Length; i++)
                {
                    bool hit = i == 2 || i == 4 && count >= 2 || i == 1 && count >= 3 || i == 5 && count >= 4;
                    Equal(hit ? control.life : 1000, Terraria.Main.npc[i].life,
                        $"{eventName} item={itemBody} count={count} NPC={i}: same-center sorted damage");
                }
                // NPC 3 is near the outer selected NPC but outside the original
                // radius: even count=12 must not create a second hopping center.
                Equal(1000, Terraria.Main.npc[3].life, "no radial-to-hopping semantic substitution");
                Equal(1000, Terraria.Main.npc[0].life, "directly hit NPC is excluded");
            }
        }
        finally { Terraria.Main.SceneMetrics = oldMetrics; Terraria.Main.rand = oldRandom; }
    }

    private static void TargetBiasKeepsSavedDtoDomainAndActualDistanceDiscount()
    {
        var find = typeof(GeneratedProjectile).GetMethod("FindNearestNpc", BindingFlags.Instance | BindingFlags.NonPublic)!;
        foreach (var role in SwarmRoles)
        foreach (float bias in new[] { 0f, 0.5f, 0.75f, 0.9f, 0.95f, 1f })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = SwarmGameplayFixture();
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Targeting.RangeTiles = 1.25f;
            entity.Targeting.SameTargetBias = bias;
            entity.Controller.Params.SameTargetBias = bias; // retained shared DTO field, independently unchanged
            data = GeneratedItemData.FromJson(JsonSerializer.Serialize(data,
                new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }))
                ?? throw new InvalidOperationException("saved target-bias DTO fixture rejected");
            entity = data.RuntimeProgram.TryGetEntity("root")!;
            Equal(bias, entity.Targeting.SameTargetBias, "strict reader preserves saved targeting 0..1");
            Equal(bias, entity.Controller.Params.SameTargetBias, "shared parameter DTO retains its old 0..1 clamp");
            var generated = SwarmHost(data, entity);
            Vector2 center = new(1600, 1600);
            var previous = Terraria.Main.npc[0] = EventDomainNpc(0, center, 100);
            var nearer = Terraria.Main.npc[1] = EventDomainNpc(1, center, 15);
            for (int repeat = 0; repeat < 3; repeat++)
            {
                var selected = (NPC?)find.Invoke(generated, new object[] { center, entity.Targeting.RangeTiles * 16, 0, entity.Targeting.SameTargetBias });
                Equal(bias >= 0.9f ? previous.whoAmI : nearer.whoAmI, selected!.whoAmI,
                    "native selector discounts distance; saved 0.9..1 saturates identically");
            }
            var noPrevious = (NPC?)find.Invoke(generated, new object[] { center, 20f, -1, bias });
            Equal(nearer.whoAmI, noPrevious!.whoAmI, "without a previous target there is no discount");
            nearer.active = false;
            var onlyOutside = (NPC?)find.Invoke(generated, new object[] { center, 20f, 0, bias });
            Equal(bias >= 0.9f, onlyOutside is not null, "range is a score threshold, not a hard physical cap for the previous target");
        }
    }
}
