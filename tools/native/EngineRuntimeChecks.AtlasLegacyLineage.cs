using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static string AtlasLegacySidecarPath(GeneratedItemRegistryService registry)
    {
        string hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Terraria.Main.worldID.ToString(System.Globalization.CultureInfo.InvariantCulture))))
            .ToLowerInvariant();
        string directory = Path.Combine(Path.GetDirectoryName(registry.StoreRoot)!, "atlas_lineage");
        Directory.CreateDirectory(directory);
        return Path.Combine(directory, "world_" + hash + ".json");
    }

    private static JsonObject AtlasLegacySidecar(params (string Id, string Recipe, string[] Parents)[] entries)
    {
        var items = new JsonObject();
        foreach (var entry in entries)
            items[entry.Id] = new JsonObject { ["recipeKey"] = entry.Recipe,
                ["parentIdentities"] = new JsonArray(entry.Parents.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()) };
        return new JsonObject { ["worldId"] = Terraria.Main.worldID.ToString(System.Globalization.CultureInfo.InvariantCulture), ["items"] = items };
    }

    private static void AtlasRecoveryReadsExactLegacyLineageSidecar()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713266;
            using var registry = new GeneratedItemRegistryService();
            var parent = AtlasRecoveryItem("atlas-sidecar-parent");
            var child = AtlasRecoveryItem("atlas-sidecar-child");
            child.Gameplay.Damage = 91; child.Visual.SpritePath = "current-sidecar.png";
            child.GeneratedParentSummary.Description = ""; child.GeneratedParentSummary.PlayerExperience = "";
            registry.RegisterLocal(parent, ensureAssets: false);
            registry.RegisterLocal(child, ensureAssets: false);
            string[] parentIds = { "item:Terraria/Musket:96", "item:Terraria/FallenStar:75" };
            string[] childIds = { "generated:" + parent.Id, "item:Terraria/JestersArrow:51" };
            string path = AtlasLegacySidecarPath(registry);
            File.WriteAllText(path, AtlasLegacySidecar((parent.Id, parent.RecipeKey, parentIds),
                (child.Id, child.RecipeKey, childIds), ("unseen-item", "unseen-recipe", childIds)).ToJsonString());
            string root = Path.GetDirectoryName(registry.StoreRoot)!;
            var before = Directory.GetFiles(root, "*.json", SearchOption.AllDirectories).ToDictionary(file => file, File.ReadAllBytes);
            for (int repeat = 0; repeat < 2; repeat++)
            {
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(child.Id, out var restored), "legacy sidecar uses existing full definition");
                Equal(string.Join("|", childIds), string.Join("|", restored.RecipeMeta.ParentIdentities), "legacy sidecar restores exact ordered parents");
                Equal<int?>(2, RecipeLineageGraph.Build(restored, registry.Snapshot()).GenerationDepth, "legacy sidecar restores computed generation");
                Equal(91, restored.Gameplay.Damage, "sidecar cannot change mechanics");
                Equal("current-sidecar.png", restored.Visual.SpritePath, "sidecar cannot change assets");
                Equal("", restored.GeneratedParentSummary.Description, "sidecar does not invent description");
                Equal(0, restored.RecipeMeta.GenerationDepth, "sidecar does not fabricate saved generation");
                Equal(false, registry.TryGet("unseen-item", out _), "sidecar does not reveal undiscovered definitions");
                Equal(true, registry.GetLineageRecoveryReceipts().Any(value => value == "fix:restore_exact_recipe_parent_identity:" + child.Id + ":0"), "sidecar restoration is receipted");
                Equal(before.Count, Directory.GetFiles(root, "*.json", SearchOption.AllDirectories).Length, "sidecar read creates no files");
                foreach (var file in before) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "legacy sidecar and definitions stay byte exact");
            }
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static (int[] NativeTypes, int UnknownSlots) AtlasObservedDetailIngredients(GeneratedItemData data, GeneratedItemData[] known)
    {
        const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Static;
        Type ui = typeof(RecipeJournalUISystem);
        var types = new List<int>(); int unknown = 0;
        using var paper = new Hook(ui.GetMethod("DrawPaperSlip", flags)!, (Action<SpriteBatch, Rectangle, bool>)((_, _, _) => {}));
        using var button = new Hook(ui.GetMethod("Button", flags)!, (Func<SpriteBatch, Rectangle, string, bool, Vector2, bool, bool, bool>)((_, _, _, _, _, _, _) => false));
        using var label = new Hook(ui.GetMethod("Label", flags)!, (Action<SpriteBatch, string, Vector2, Color, float, int>)((_, _, _, _, _, _) => {}));
        using var text = new Hook(ui.GetMethod("Text", flags)!, (Func<string, object[], string>)((key, _) => key));
        using var fill = new Hook(ui.GetMethod("Fill", flags)!, (Action<SpriteBatch, Rectangle, Color>)((_, _, _) => {}));
        using var trace = new Hook(ui.GetMethod("Trace", flags)!, (Action<SpriteBatch, Vector2, Vector2, Color>)((_, _, _, _) => {}));
        using var well = new Hook(ui.GetMethod("ItemSlotBackground", flags)!, (Action<SpriteBatch, Rectangle, bool, bool>)((_, _, _, _) => {}));
        using var sprite = new Hook(ui.GetMethod("Sprite", flags)!, (Action<SpriteBatch, GeneratedItemData, Rectangle>)((_, _, _) => {}));
        using var paragraph = new Hook(ui.GetMethod("Paragraph", flags)!, (Action<SpriteBatch, string, Rectangle, Color, float, bool>)((_, _, _, _, _, _) => {}));
        using var centered = new Hook(ui.GetMethod("CenterLabel", flags)!, (Action<SpriteBatch, string, Rectangle, Color, float>)((_, value, _, _, _) => { if (value == "?") unknown++; }));
        using var native = new Hook(ui.GetMethod("DrawNativeLineageSprite", flags)!, (Action<SpriteBatch, Item, Rectangle>)((_, item, _) => types.Add(item.type)));
        new RecipeJournalUISystem().OnWorldUnload();
        try
        {
            ui.GetField("_known", flags)!.SetValue(null, known);
            ui.GetField("_selected", flags)!.SetValue(null, data.Id);
            ui.GetMethod("DrawDetail", flags)!.Invoke(null, new object?[] { null, data, new Rectangle(0, 0, 500, 600), new InfiniCraftPlayer(), false, new Vector2(-100) });
            return (types.ToArray(), unknown);
        }
        finally { new RecipeJournalUISystem().OnWorldUnload(); }
    }

    private static void AtlasRecoveryRestoresNativeIngredientDrawing()
    {
        int world = Terraria.Main.worldID;
        var samples = ContentSamples.ItemsByType.ToArray();
        try
        {
            Terraria.Main.worldID = 713269;
            // Native content samples are installed by tML during a real load.
            // Only that registry fixture and GPU draw boundaries are substituted.
            foreach (int type in new[] { ItemID.Musket, ItemID.FallenStar, ItemID.JestersArrow })
                ContentSamples.ItemsByType[type] = new Item { type = type, stack = 1 };
            using var registry = new GeneratedItemRegistryService();
            var parent = AtlasRecoveryItem("atlas-native-parent");
            var child = AtlasRecoveryItem("atlas-native-child");
            registry.RegisterLocal(parent, ensureAssets: false); registry.RegisterLocal(child, ensureAssets: false);
            Equal(2, AtlasObservedDetailIngredients(child, registry.Snapshot()).UnknownSlots, "actual detail shows missing slots before recovery");
            File.WriteAllText(AtlasLegacySidecarPath(registry), AtlasLegacySidecar(
                (parent.Id, parent.RecipeKey, new[] { "item:Terraria/Musket:96", "item:Terraria/FallenStar:75" }),
                (child.Id, child.RecipeKey, new[] { "generated:" + parent.Id, "item:Terraria/JestersArrow:51" })).ToJsonString());
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(child.Id, out var restored); registry.TryGet(parent.Id, out var restoredParent);
            var childDraw = AtlasObservedDetailIngredients(restored, registry.Snapshot());
            Equal("51", string.Join("|", childDraw.NativeTypes), "actual detail chooses native JestersArrow sprite branch after recovery");
            Equal(0, childDraw.UnknownSlots, "actual detail no longer draws question marks for known generated and native parents");
            var parentDraw = AtlasObservedDetailIngredients(restoredParent, registry.Snapshot());
            Equal("96|75", string.Join("|", parentDraw.NativeTypes), "actual detail draws both vanilla parents in exact saved order");
            Equal(0, parentDraw.UnknownSlots, "vanilla-only recipe no longer draws question marks");
        }
        finally
        {
            ContentSamples.ItemsByType.Clear(); foreach (var row in samples) ContentSamples.ItemsByType.Add(row.Key, row.Value);
            Terraria.Main.worldID = world;
        }
    }

    private static void AtlasRecoveryReadsOnlySelfBoundHistoricalParentCards()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713270;
            using var registry = new GeneratedItemRegistryService();
            var target = AtlasRecoveryItem("atlas-knowledge-current");
            registry.RegisterLocal(target, ensureAssets: false);
            string historicalPath = Path.Combine(registry.StoreRoot, "historical-knowledge.json");
            JsonObject Evidence()
            {
                var root = JsonNode.Parse(target.ToLocalCacheJson())!.AsObject();
                root["itemKnowledge"] = new JsonObject {
                    ["enabled"] = true,
                    ["resultCard"] = new JsonObject { ["identity"] = "generated:" + target.Id },
                    ["parents"] = new JsonArray(
                        new JsonObject { ["name"] = target.ParentA, ["identity"] = "item:Terraria/Mushroom:5" },
                        new JsonObject { ["name"] = target.ParentB, ["identity"] = "item:Terraria/Sunflower:63" }) };
                return root;
            }
            foreach (string mismatch in new[] { "result", "recipe", "world", "disabled", "slot-order", "missing-identity", "missing-caption", "extra-slot", "duplicate-identity" })
            {
                var root = Evidence(); var knowledge = root["itemKnowledge"]!;
                if (mismatch == "result") knowledge["resultCard"]!["identity"] = "generated:foreign";
                if (mismatch == "recipe") root["recipeKey"] = "foreign";
                if (mismatch == "world") root["recipeMeta"]!["worldId"] = "713271";
                if (mismatch == "disabled") knowledge["enabled"] = false;
                if (mismatch == "slot-order") knowledge["parents"]![0]!["name"] = target.ParentB;
                if (mismatch == "missing-identity") knowledge["parents"]![0]!.AsObject().Remove("identity");
                if (mismatch == "missing-caption") knowledge["parents"]![0]!.AsObject().Remove("name");
                if (mismatch == "extra-slot") knowledge["parents"]!.AsArray().Add(new JsonObject());
                string json = root.ToJsonString();
                if (mismatch == "duplicate-identity") json = json.Replace("\"identity\":\"item:Terraria/Mushroom:5\"", "\"identity\":\"item:Terraria/StoneBlock:3\",\"identity\":\"item:Terraria/Mushroom:5\"");
                File.WriteAllText(historicalPath, json);
                registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(target.Id, out var unchanged);
                Equal(0, unchanged.RecipeMeta.ParentIdentities.Length, "historical card rejects " + mismatch);
            }
            File.WriteAllText(historicalPath, Evidence().ToJsonString());
            var other = AtlasRecoveryItem("atlas-knowledge-same-recipe"); other.RecipeKey = target.RecipeKey;
            registry.RegisterLocal(other, ensureAssets: false);
            string rootPath = Path.GetDirectoryName(registry.StoreRoot)!;
            var before = Directory.GetFiles(rootPath, "*.json", SearchOption.AllDirectories).ToDictionary(file => file, File.ReadAllBytes);
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(target.Id, out var restored); registry.TryGet(other.Id, out var untouched);
            Equal("item:Terraria/Mushroom:5|item:Terraria/Sunflower:63", string.Join("|", restored.RecipeMeta.ParentIdentities), "self-bound cards restore only exact saved identities and order");
            Equal<int?>(1, RecipeLineageGraph.Build(restored, registry.Snapshot()).GenerationDepth, "native parent cards yield first generation");
            Equal(0, untouched.RecipeMeta.ParentIdentities.Length, "same recipe key cannot transfer identities to another generated result");
            foreach (var file in before) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "historical card recovery leaves input bytes unchanged");
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void AtlasRecoveryRefusesInvalidLegacyLineageSidecar()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713267;
            using var registry = new GeneratedItemRegistryService();
            var target = AtlasRecoveryItem("atlas-sidecar-negative");
            registry.RegisterLocal(target, ensureAssets: false);
            string path = AtlasLegacySidecarPath(registry);
            string[] parents = { "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3" };
            foreach (string mismatch in new[] { "world", "recipe", "result", "missing-recipe", "extra-slot", "empty-slot", "wrong-type", "duplicate-item", "duplicate-world", "duplicate-recipe", "malformed" })
            {
                JsonObject document = AtlasLegacySidecar((target.Id, target.RecipeKey, parents));
                JsonObject row = (JsonObject)document["items"]![target.Id]!;
                if (mismatch == "world") document["worldId"] = "713268";
                if (mismatch == "recipe") row["recipeKey"] = "foreign-recipe";
                if (mismatch == "result") { ((JsonObject)document["items"]!).Remove(target.Id); document["items"]!["foreign-id"] = row; }
                if (mismatch == "missing-recipe") row.Remove("recipeKey");
                if (mismatch == "extra-slot") ((JsonArray)row["parentIdentities"]!).Add("item:Terraria/Gel:23");
                if (mismatch == "empty-slot") row["parentIdentities"]![0] = "";
                if (mismatch == "wrong-type") row["parentIdentities"]![0] = 9;
                string json = document.ToJsonString();
                if (mismatch == "duplicate-item") json = json.Replace("\"items\":{", "\"items\":{\"" + target.Id + "\":" + row.ToJsonString() + ",");
                if (mismatch == "duplicate-world") json = json.Insert(1, "\"worldId\":\"713268\",");
                if (mismatch == "duplicate-recipe") json = json.Replace("\"recipeKey\":", "\"recipeKey\":\"different\",\"recipeKey\":");
                if (mismatch == "malformed") json = "{";
                File.WriteAllText(path, json);
                registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(target.Id, out var unchanged);
                Equal(0, unchanged.RecipeMeta.ParentIdentities.Length, "sidecar rejects " + mismatch);
            }
            // A competing full definition remains part of the same consensus.
            var conflicting = target.CloneForItemInstance(); conflicting.RecipeMeta.ParentIdentities = new[] { "item:Terraria/Gel:23", parents[1] };
            File.WriteAllText(Path.Combine(registry.StoreRoot, "legacy-conflict.json"), conflicting.ToLocalCacheJson());
            File.WriteAllText(path, AtlasLegacySidecar((target.Id, target.RecipeKey, parents)).ToJsonString());
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(target.Id, out var unresolved);
            Equal("", unresolved.RecipeMeta.ParentIdentities[0], "conflicting sidecar identity remains unknown");
            Equal(parents[1], unresolved.RecipeMeta.ParentIdentities[1], "independent agreeing slot remains recoverable");
            Equal<int?>(null, RecipeLineageGraph.Build(unresolved, registry.Snapshot()).GenerationDepth, "conflicting sidecar cannot fabricate generation");
            // A nonempty current slot always wins, and conflicts block the other slot.
            var current = AtlasRecoveryItem("atlas-sidecar-current", "item:Terraria/Gel:23", "");
            registry.RegisterLocal(current, ensureAssets: false);
            File.WriteAllText(path, AtlasLegacySidecar((current.Id, current.RecipeKey, parents)).ToJsonString());
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(current.Id, out var retained);
            Equal("item:Terraria/Gel:23", retained.RecipeMeta.ParentIdentities[0], "current nonempty identity is not overwritten");
            Equal("", retained.RecipeMeta.ParentIdentities[1], "incompatible sidecar cannot fill the other slot");
        }
        finally { Terraria.Main.worldID = world; }
    }
}
