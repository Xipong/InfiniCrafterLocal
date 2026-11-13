using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentCompositeSummonRetainsConstructionAndFollowerSource()
    {
        using var state = new NativeActorState();
        var packet = JsonNode.Parse(new GeneratorClient().Prepare(
            new Item(ItemID.StardustDragonStaff), new Item(ItemID.StardustCellStaff), new Player()).PayloadJson)!;
        var parent = packet["itemA"]!;
        // A correct root-projectile projection alone is not a complete item.
        // Native item use owns initial chain construction and later extension.
        var shoot = parent["nativeItemDispatchReference"]!["roots"]!.AsArray()
            .Single(root => root!["root"]!.GetValue<string>() == "ItemCheck_Shoot")!;
        Equal(0, shoot["unknowns"]!.AsArray().Count, "composite construction capture has no bound omission");
        string construction = string.Join("\n", shoot["records"]!.AsArray()
            .Select(record => record!["code"]!.GetValue<string>()));
        foreach (string required in new[] { "Projectile.NewProjectile", "projToShoot + 1", "projToShoot + 2",
            "projToShoot + 3", ".localAI[1]", ".ai[0]", "else if" })
            Equal(true, construction.Contains(required, StringComparison.Ordinal), "composite construction retains " + required);

        // Until separately captured segment profiles are proved to reach Author,
        // identity-specializing the head must not erase the only follower source.
        string source = parent["directProjectileRaw"]!["mechanicsSource"]!.ToJsonString();
        foreach (string required in new[] { "GetByUUID", "localAI[0]", "localAI[1]" })
            Equal(true, source.Contains(required, StringComparison.Ordinal), "composite follower source retains " + required);
    }
}
