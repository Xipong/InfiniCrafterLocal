using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceGraphRetainsNativeSpawnCandidateProvenance()
    {
        // AI_075 contains both Last Prism's laser and a separate conditional
        // 600 -> 601 branch. Unknown identity guards remain source evidence;
        // registered child samples must not turn either spawn into an executed fact.
        int[] ids = { ProjectileID.LastPrism, ProjectileID.LastPrismLaser, 601 };
        var prior = ids.ToDictionary(id => id, id => ContentSamples.ProjectilesByType.TryGetValue(id, out var value) ? value : null);
        try
        {
            foreach (int id in ids)
            {
                var sample = new Projectile(); sample.SetDefaults(id);
                ContentSamples.ProjectilesByType[id] = sample;
            }
            var graph = GeneratorClient.CaptureParentSourceGraph(new Item { type = ItemID.Wood, stack = 1, shoot = ProjectileID.LastPrism, createTile = -1 });
            var edges = graph["edges"]!.AsArray().OfType<JsonObject>().ToArray();
            Equal(true, edges.Any(edge => edge["from"] is null && edge["to"] is not null
                && edge["kind"]?.GetValue<string>() == "certified_native_projectile_source_windows"), "the initial parent source still has its native identity certification");
            foreach (int child in new[] { ProjectileID.LastPrismLaser, 601 })
            {
                var children = edges.Where(edge => edge["to"] is not null && edge["context"] is JsonObject context
                    && context["projectileId"]?.GetValue<int>() == child).ToArray();
                Equal(true, children.Length > 0, "conditional child source is preserved, not deleted: " + child);
                Equal(true, children.All(edge => edge["kind"]?.GetValue<string>() == "conditional_native_projectile_spawn_source"), "native dispatch preserves the caller's conditional admission: " + child);
                Equal(true, children.All(edge => edge["context"]!["entryAndOmittedFlow"]?.GetValue<string>() == "unresolved"), "native source-window uncertainty is preserved: " + child);
            }
            AssertSelectionReferences(graph);
        }
        finally
        {
            foreach (int id in ids)
                if (prior[id] is { } value) ContentSamples.ProjectilesByType[id] = value;
                else ContentSamples.ProjectilesByType.Remove(id);
        }
    }
}
