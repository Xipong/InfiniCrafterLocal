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
        const string metadata = "{\"renderSizePx\":40,\"forwardAngleDegrees\":45,\"grip\":{\"normalizedX\":0.25,\"normalizedY\":0.75},\"accessoryMount\":\"shoulder\",\"effectColor\":\"gold\"}";
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
                Equal(40, resolved.Visual.RenderSizePx!.Value, "compact registry hydration preserves root R");
                Equal(45f, resolved.Visual.ForwardAngleDegrees!.Value, "compact registry hydration preserves root axis");
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


    private static void SpritePresentationMetadataStrictRoundTrips()
    {
        var legacy = GeneratedItemData.Placeholder();
        foreach (string json in new[] { legacy.ToJson(), legacy.ToLocalCacheJson(), legacy.ToNetworkJson(), System.Text.Json.JsonSerializer.Serialize(legacy) })
        {
            Equal(false, json.Contains("\"renderSizePx\"") || json.Contains("\"forwardAngleDegrees\""), "legacy omission survives every serializer");
            Equal(true, GeneratedItemData.FromJson(json) is not null, "legacy definition still admits");
        }
        // Inject the original JSON number only after serializing a valid fixture.
        // A typed float assignment/ToJson before admission would erase this regression.
        string RawAxis(string fixture, bool distinct, string literal, string property = "forwardAngleDegrees")
        {
            var root = JsonNode.Parse(fixture)!;
            var visual = distinct ? root["runtimeProgram"]!["entities"]![1]!["visual"]! : root["visual"]!;
            visual[property] = "__raw_forward_angle__";
            return root.ToJsonString().Replace("\"__raw_forward_angle__\"", literal, StringComparison.Ordinal);
        }
        float? Axis(GeneratedItemData data, bool distinct)
            => distinct ? data.RuntimeProgram.Entities[1].Visual.ForwardAngleDegrees : data.Visual.ForwardAngleDegrees;
        var distinctFixture = GeneratedItemData.Placeholder();
        var axisEntity = new RuntimeEntitySpec { Id = "sprite_axis_probe", Kind = RuntimeEntityKind.FreeProjectile };
        axisEntity.VisualRole = axisEntity.Visual.Role = RuntimeEntityKind.VisualRoleFor(axisEntity.Kind);
        axisEntity.Spawn.Enabled = true; axisEntity.Movement.Name = "move_straight"; axisEntity.Movement.Code = 0;
        axisEntity.Visual.AssetMode = "baked_sprite"; axisEntity.Visual.SpritePath = "axis-probe.png"; axisEntity.Visual.SpriteStatus = "generated";
        axisEntity.Visual.RenderSizePx = 37; axisEntity.Visual.PreferredCanvasSize = 64;
        distinctFixture.RuntimeProgram.Entities = new[] { distinctFixture.RuntimeProgram.Entities[0], axisEntity };
        foreach (bool distinct in new[] { false, true })
        {
            string fixture = distinct ? distinctFixture.ToJson() : legacy.ToJson();
            var control = GeneratedItemData.FromJson(fixture);
            Equal(true, control is not null, "axis boundary fixture passes unrelated DTO gates: " + distinct);
            Equal(false, Axis(control!, distinct).HasValue, "axis omission remains absence: " + distinct);
            if (distinct)
            {
                Equal("sprite_axis_probe", control!.RuntimeProgram.Entities[1].Id, "independent baked fixture is retained, not dropped");
                Equal("baked_sprite", control.RuntimeProgram.Entities[1].Visual.AssetMode, "independent fixture uses its own sprite owner");
            }
            foreach (var row in new (string Literal, float? Expected)[] {
                ("-180", -180f), ("0", 0f), ("180", 180f), ("45.125", 45.125f),
                ("-179.999999", -180f), ("179.999999", 180f), // legal source may round in storage
                ("179.999999999999999999999999999999", 180f), // exact double-endpoint comparison must also admit the inside
                ("18e1", 180f), ("-1800e-1", -180f), ("180.000000000000000000000000000000", 180f),
                ("1e-100", 0f),
                ("180.000001", null), ("-180.000001", null),
                ("180.000000000000000000000000000001", null), ("-180.000000000000000000000000000001", null),
                ("1.80000000000000000000000000000001e2", null),
                ("180000000000000000000000000000001e-30", null),
                ("180.01", null), ("-180.01", null), ("181", null),
                ("1e100", null), ("1e400", null), ("null", null), ("\"180\"", null) })
            {
                var admitted = GeneratedItemData.FromJson(RawAxis(fixture, distinct, row.Literal));
                Equal(row.Expected.HasValue, admitted is not null, "raw JSON axis admission: " + distinct + " " + row.Literal);
                if (!row.Expected.HasValue) continue;
                Equal(row.Expected.Value, Axis(admitted!, distinct)!.Value, "axis narrows only after source-domain admission");
                foreach (string json in new[] { admitted!.ToJson(), admitted.ToLocalCacheJson(), admitted.ToNetworkJson(), System.Text.Json.JsonSerializer.Serialize(admitted) })
                {
                    var copy = GeneratedItemData.FromJson(json);
                    Equal(true, copy is not null, "admitted raw axis survives full/cache/network/alternate serialization");
                    Equal(row.Expected.Value, Axis(copy!, distinct)!.Value, "nullable-float axis storage is unchanged");
                }
            }
            Equal(true, GeneratedItemData.FromJson(RawAxis(fixture, distinct, "45.125", "FORWARDANGLEDEGREES")) is not null, "axis retains case-insensitive property matching");
            Equal(true, GeneratedItemData.FromJson(RawAxis(fixture, distinct, "180.000001", "FORWARDANGLEDEGREES")) is null, "case-insensitive axis cannot bypass source-domain rejection");
        }
        Equal(true, PresentationWith("{\"renderSizePx\":32}") is not null, "saved wire may carry size without fresh-authoring axis requirement");
        Equal(true, PresentationWith("{\"forwardAngleDegrees\":0}") is not null, "explicit zero axis remains present without opting into root visibility");
        foreach (int size in new[] { 1, 32, 512 })
        foreach (float axis in new[] { -180f, 0f, 45f, 180f })
        {
            var data = PresentationWith($"{{\"renderSizePx\":{size},\"forwardAngleDegrees\":{axis.ToString(System.Globalization.CultureInfo.InvariantCulture)}}}");
            Equal(true, data is not null, "strict root bounds admitted");
            foreach (string json in new[] { data!.ToJson(), data.ToLocalCacheJson(), data.ToNetworkJson(), System.Text.Json.JsonSerializer.Serialize(data) })
            {
                var copy = GeneratedItemData.FromJson(json)!;
                Equal(true, copy is not null, "root presentation survives full/cache/network/alternate serializer");
                Equal(size, copy!.Visual.RenderSizePx!.Value, "root size unchanged");
                Equal(axis, copy.Visual.ForwardAngleDegrees!.Value, "root final-texture axis unchanged, including explicit zero");
            }
            var compact = GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!;
            Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(compact), "compact remains a reference, not second presentation authority");
        }
        foreach (string field in new[] { "renderSizePx", "forwardAngleDegrees" })
        foreach (string bad in new[] { "null", "true", "\"32\"", "[]", "{}" })
            Equal(true, PresentationWith($"{{\"{field}\":{bad}}}") is null, "strict root rejects type/null: " + field + bad);
        foreach (string bad in new[] { "0", "-1", "513", "1.5" })
            Equal(true, PresentationWith($"{{\"renderSizePx\":{bad}}}") is null, "size rejects rather than clamps " + bad);
        foreach (string bad in new[] { "-180.01", "180.01", "1e100" })
            Equal(true, PresentationWith($"{{\"forwardAngleDegrees\":{bad}}}") is null, "axis bounds/finite rejection " + bad);
        foreach (int canvas in new[] { 24, 32, 48, 64, 96, 128 })
        {
            var data = GeneratedItemData.Placeholder();
            var entity = new RuntimeEntitySpec { Id = "sprite_probe", Kind = RuntimeEntityKind.FreeProjectile };
            entity.VisualRole = entity.Visual.Role = RuntimeEntityKind.VisualRoleFor(entity.Kind);
            entity.Spawn.Enabled = true; entity.Movement.Name = "move_straight"; entity.Movement.Code = 0;
            entity.Visual.AssetMode = "baked_sprite"; entity.Visual.SpritePath = "body.png"; entity.Visual.SpriteStatus = "generated";
            entity.Visual.RenderSizePx = 37; entity.Visual.PreferredCanvasSize = canvas; entity.Visual.ForwardAngleDegrees = -45f;
            data.RuntimeProgram.Entities = new[] { data.RuntimeProgram.Entities[0], entity };
            foreach (string json in new[] { data.ToJson(), data.ToLocalCacheJson(), data.ToNetworkJson(), System.Text.Json.JsonSerializer.Serialize(data) })
            {
                var copy = GeneratedItemData.FromJson(json)!;
                Equal(true, copy is not null, "distinct baked presentation admits every serialization route");
                var v = copy!.RuntimeProgram.Entities[1].Visual;
                Equal(37, v.RenderSizePx!.Value, "entity size survives"); Equal(canvas, v.PreferredCanvasSize!.Value, "entity canvas survives"); Equal(-45f, v.ForwardAngleDegrees!.Value, "entity axis survives");
            }
            var root = JsonNode.Parse(data.ToJson())!;
            foreach (string field in new[] { "renderSizePx", "preferredCanvasSize", "forwardAngleDegrees" })
            foreach (string bad in new[] { "null", "false", "\"32\"" })
            {
                var invalid = root.DeepClone(); invalid["runtimeProgram"]!["entities"]![1]!["visual"]![field] = JsonNode.Parse(bad);
                Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "strict entity rejects present null/type " + field);
            }
            foreach (string field in new[] { "renderSizePx", "forwardAngleDegrees" })
            foreach (string bad in field == "renderSizePx" ? new[] { "0", "-1", "513", "1.5" } : new[] { "-180.01", "180.01", "1e100" })
            {
                var invalid = root.DeepClone(); invalid["runtimeProgram"]!["entities"]![1]!["visual"]![field] = JsonNode.Parse(bad);
                Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "strict entity bounds " + field + bad);
            }
            foreach (int bad in new[] { 0, 25, 129 })
            {
                var invalid = root.DeepClone(); invalid["runtimeProgram"]!["entities"]![1]!["visual"]!["preferredCanvasSize"] = bad;
                Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "entity canvas rejects rather than rounds");
            }
            foreach (string field in new[] { "renderSizePx", "preferredCanvasSize", "forwardAngleDegrees" })
            {
                var invalid = JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!;
                invalid["runtimeProgram"]!["entities"]![0]!["visual"]![field] = field == "forwardAngleDegrees" ? 0 : 32;
                Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "item-body alias metadata cannot become a second authority " + field);
            }
            foreach (string mode in new[] { "reuse_item_icon", "runtime_geometry", "no_asset" })
            {
                var invalid = root.DeepClone(); invalid["runtimeProgram"]!["entities"]![1]!["visual"]!["assetMode"] = mode;
                Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "non-baked branch rejects second size/axis authority");
            }
        }
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
