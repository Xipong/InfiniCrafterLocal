#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks { private static void TargetingDtoContract(string valid, string[] invalid, params string[] optionalNames)
    {
        var options = new System.Text.Json.JsonSerializerOptions { PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase };
        var accepted = System.Text.Json.JsonSerializer.Deserialize<RuntimeTargetingSpec>(valid, options)!;
        accepted.Normalize();
        var roundtrip = System.Text.Json.JsonSerializer.Deserialize<RuntimeTargetingSpec>(System.Text.Json.JsonSerializer.Serialize(accepted, options), options)!;
        roundtrip.Normalize();
        string omitted = System.Text.Json.JsonSerializer.Serialize(new RuntimeTargetingSpec(), options);
        foreach (string name in optionalNames) Equal(false, omitted.Contains("\"" + name + "\""), "absent targeting choice keeps saved identity: " + name);
        foreach (string raw in invalid)
        {
            bool rejected = false;
            try { System.Text.Json.JsonSerializer.Deserialize<RuntimeTargetingSpec>(raw, options)!.Normalize(); }
            catch (System.IO.InvalidDataException) { rejected = true; }
            catch (System.Text.Json.JsonException) { rejected = true; }
            Equal(true, rejected, "strict native targeting DTO refuses " + raw);
        }
    }
    private static void StationTargetAdmission() {
        TargetingDtoContract("{\"rangeTiles\":10,\"minimumRangeTiles\":2,\"coneRadians\":1.2,\"coneDirection\":\"projectile_velocity\",\"bossFilter\":\"boss_only\",\"minimumHealthRatio\":0.2,\"maximumHealthRatio\":0.6}", new[] { "{\"minimumRangeTiles\":null}", "{\"rangeTiles\":1,\"minimumRangeTiles\":2}", "{\"coneRadians\":7}", "{\"coneDirection\":\"guess\"}", "{\"bossFilter\":\"BOSS\"}", "{\"minimumHealthRatio\":0.8,\"maximumHealthRatio\":0.2}" }, "minimumRangeTiles", "coneRadians", "coneDirection", "bossFilter", "minimumHealthRatio", "maximumHealthRatio");
using var state = new SentryTargetScope();
        var projectile = new Projectile { owner = 0, active = true, Center = new Vector2(1600, 1600), velocity = Vector2.UnitX };
        var generated = Attach(projectile); var npc = state.Target(0, 64); npc.boss = true; npc.life = 40;
        var spec = new RuntimeTargetingSpec { MinimumRangeTiles = 2, ConeRadians = Math.PI / 2, BossFilter = "boss_only", MinimumHealthRatio = .2, MaximumHealthRatio = .5 };
        Equal(true, generated.AdmitsTargetFilter(npc, spec, state.Owner), "joint annulus cone boss health admission");
        npc.Center = projectile.Center + Vector2.UnitX * 16;
        Equal(false, generated.AdmitsTargetFilter(npc, spec, state.Owner), "inner radius exclusion");
        npc.Center = projectile.Center - Vector2.UnitX * 64;
        Equal(false, generated.AdmitsTargetFilter(npc, spec, state.Owner), "rear cone exclusion");
        npc.Center = projectile.Center + Vector2.UnitX * 64; npc.life = 70;
        Equal(false, generated.AdmitsTargetFilter(npc, spec, state.Owner), "health band exclusion");
        npc.life = 40; spec.ConeDirection = "projectile_velocity"; projectile.velocity = Vector2.Zero;
        Equal(false, generated.AdmitsTargetFilter(npc, spec, state.Owner), "zero velocity cannot invent cone direction");
} }
