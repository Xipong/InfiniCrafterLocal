using System;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData PresentationWith(string metadata)
    {
        var root = JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!;
        var fields = JsonNode.Parse(metadata)!.AsObject();
        foreach (var field in fields) root["visual"]![field.Key] = field.Value?.DeepClone();
        return GeneratedItemData.FromJson(root.ToJsonString())!;
    }

    private static void PresentationMetadataRoundTrips()
    {
        const string metadata = "{\"grip\":{\"normalizedX\":0.25,\"normalizedY\":0.75},\"accessoryMount\":\"shoulder\",\"effectColor\":\"gold\"}";
        var data = PresentationWith(metadata);
        Equal(true, data is not null, "strict DTO accepts explicit presentation metadata");
        foreach (string json in new[] { data!.ToJson(), data.ToLocalCacheJson(), data.ToNetworkJson() })
        {
            var reloaded = GeneratedItemData.FromJson(json);
            Equal(true, reloaded is not null, "full/cache/network reader accepts metadata");
            var visual = JsonNode.Parse(reloaded!.ToJson())!["visual"]!;
            Equal(0.25f, visual["grip"]!["normalizedX"]!.GetValue<float>(), "grip X survives");
            Equal(0.75f, visual["grip"]!["normalizedY"]!.GetValue<float>(), "grip Y survives");
            Equal("shoulder", visual["accessoryMount"]!.GetValue<string>(), "mount survives");
            Equal("gold", visual["effectColor"]!.GetValue<string>(), "finite rendering color survives");
        }
        string save = data.ToPlayerSaveJson();
        Equal(false, save.Contains("grip") || save.Contains("accessoryMount"), "save remains compact identity reference");
        var compact = GeneratedItemData.FromPlayerSaveJson(save);
        Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(compact), "save hydrates via canonical registry");
        var registryProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = registryProperty.GetValue(null);
        using (var registry = new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService())
        {
            try
            {
                registryProperty.SetValue(null, registry);
                var byId = (System.Collections.IDictionary)registry.GetType().GetField("_byId", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!.GetValue(registry)!;
                byId.Add(data.Id, data);
                var resolve = typeof(InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayDrawLayerBase).GetMethod("ResolveEquipPresentationData", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
                var resolved = (GeneratedItemData)resolve.Invoke(null, new object[] { compact! })!;
                Equal(true, ReferenceEquals(data, resolved), "compact equip save resolves exact canonical presentation metadata");
                Equal("shoulder", JsonNode.Parse(resolved.ToJson())!["visual"]!["accessoryMount"]!.GetValue<string>(), "registry mount survives compact equip route");
            }
            finally { registryProperty.SetValue(null, oldRegistry); }
        }
        Equal(false, GeneratedItemData.Placeholder().ToJson().Contains("\"grip\""), "absent grip remains absent");
        foreach (string invalid in new[] {
            "{\"grip\":null}", "{\"grip\":{}}", "{\"grip\":{\"normalizedX\":0.2}}",
            "{\"grip\":{\"normalizedX\":false,\"normalizedY\":0.2}}",
            "{\"grip\":{\"normalizedX\":\"0.2\",\"normalizedY\":0.2}}",
            "{\"grip\":{\"normalizedX\":-0.01,\"normalizedY\":0.2}}",
            "{\"grip\":{\"normalizedX\":0.2,\"normalizedY\":1.01}}",
            "{\"grip\":{\"normalizedX\":0.2,\"normalizedY\":0.2,\"extra\":0}}",
            "{\"accessoryMount\":null}", "{\"accessoryMount\":\"\"}", "{\"accessoryMount\":\"Chest\"}",
            "{\"accessoryMount\":\" chest\"}", "{\"accessoryMount\":false}", "{\"accessoryMount\":12}" })
            Equal(true, PresentationWith(invalid) is null, "invalid presentation rejected: " + invalid);
        foreach (string token in new[] { "white", "gray", "brown", "tan", "red", "orange", "yellow", "gold", "green", "cyan", "blue", "purple", "pink", "black" })
        {
            var colored = PresentationWith("{\"effectColor\":\"" + token + "\"}");
            Equal(true, colored is not null, "all rendering tokens reach real DTO: " + token);
            Equal(token, colored!.Visual.EffectColor!, "exact color preserved");
        }
        foreach (string value in new[] { "null", "false", "12", "\"\"", "\"Gold\"", "\" gold\"", "\"#ff0000\"", "\"verdigris\"" })
            Equal(true, PresentationWith("{\"effectColor\":" + value + "}") is null, "invalid effectColor rejected: " + value);
        foreach (string mount in new[] { "chest", "back", "waist", "shoulder", "orbit" })
            Equal(true, PresentationWith("{\"accessoryMount\":\"" + mount + "\",\"grip\":{\"normalizedX\":0,\"normalizedY\":1}}") is not null, "finite mount and grip endpoints accepted");
    }

    private static void ExplicitAccessoryMountDraws(PlayerDrawSet original, GeneratedItemData data)
    {
        var originalVisual = data.Visual;
        try
        {
            foreach (var mount in new[] { ("chest", 0f, -2f), ("back", -10f, -4f), ("waist", 0f, 10f), ("shoulder", 8f, -12f), ("orbit", 0f, 16f) })
            {
                data.Visual = PresentationWith("{\"accessoryMount\":\"" + mount.Item1 + "\"}").Visual;
                data.Visual.EquipOverlayPath = originalVisual.EquipOverlayPath;
                var info = original;
                info.DrawDataCache = new System.Collections.Generic.List<DrawData>();
                var layer = new InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayAccessoryDrawLayer();
                var drawMethod = typeof(InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayDrawLayerBase).GetMethod("Draw", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
                object[] args = { info };
                drawMethod.Invoke(layer, args);
                info = (PlayerDrawSet)args[0];
                Equal(1, info.DrawDataCache.Count, "one explicit mount draw");
                var player = info.drawPlayer;
                var top = new Vector2((int)(info.Position.X - Terraria.Main.screenPosition.X - 20 + player.width / 2),
                    (int)(info.Position.Y - Terraria.Main.screenPosition.Y + player.height - 56 + 4));
                Vector2 center = new(20 + mount.Item2 * player.direction, 56 - 4 - player.height * 0.5f + mount.Item3 * player.gravDir);
                Vector2 expected = top + player.bodyPosition + info.bodyVect + Vector2.Transform(center - info.bodyVect, Matrix.CreateRotationZ(player.bodyRotation));
                NearEquip(expected, info.DrawDataCache[0].position, "exact explicit " + mount.Item1 + " body-local anchor");
                Equal(player.bodyRotation, info.DrawDataCache[0].rotation, "mount follows body bone once");
                Equal((int)info.playerEffect, (int)info.DrawDataCache[0].effect, "mount retains facing/gravity sprite effects");
                PlayerDrawLayers.DrawPlayer_TransformDrawData(ref info);
                Vector2 pivot = info.Position - Terraria.Main.screenPosition + info.rotationOrigin;
                NearEquip(pivot + Vector2.Transform(expected - pivot, Matrix.CreateRotationZ(info.rotation)), info.DrawDataCache[0].position, "mounted badge follows full player rotation once");
            }
        }
        finally { data.Visual = originalVisual; }
    }

    private static void ExplicitGripDraws(Func<Vector2, DrawData> render, GeneratedItemData data, Player player)
    {
        var oldVisual = data.Visual;
        int oldDirection = player.direction;
        float oldGrav = player.gravDir;
        string oldStyle = data.RuntimeProgram.ItemUse.UseStyle;
        int oldX = data.RuntimeProgram.ItemUse.HoldoutOffsetX, oldY = data.RuntimeProgram.ItemUse.HoldoutOffsetY;
        try
        {
            var authored = PresentationWith("{\"grip\":{\"normalizedX\":0.25,\"normalizedY\":0.75}}");
            Equal(true, authored is not null, "explicit grip accepted before draw");
            data.Visual = authored!.Visual;
            data.Visual.SpritePath = oldVisual.SpritePath;
            data.RuntimeProgram.ItemUse.UseStyle = "swing";
            data.RuntimeProgram.ItemUse.HoldoutOffsetX = 3;
            data.RuntimeProgram.ItemUse.HoldoutOffsetY = 7;
            foreach (int direction in new[] { -1, 1 })
            foreach (float gravity in new[] { -1f, 1f })
            {
                player.direction = direction; player.gravDir = gravity;
                var draw = render(new Vector2(140, 260));
                Equal(new Vector2(64 * (direction < 0 ? 0.75f : 0.25f), 40 * (gravity < 0 ? 0.25f : 0.75f)), draw.origin, "explicit final-canvas grip follows flips");
                Equal(new Vector2(103, 200 + 7 * gravity), draw.position, "explicit grip removes legacy artistic offset, preserves screen-space HoldoutOffset");
            }
        }
        finally
        {
            data.Visual = oldVisual; player.direction = oldDirection; player.gravDir = oldGrav;
            data.RuntimeProgram.ItemUse.UseStyle = oldStyle;
            data.RuntimeProgram.ItemUse.HoldoutOffsetX = oldX; data.RuntimeProgram.ItemUse.HoldoutOffsetY = oldY;
        }
    }
}
