using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private sealed class IdentityCatalogProbeBuff : ModBuff
    {
        internal static int HookCalls;
        public override string Name => "IdentityCatalogProbe";
        public override void Update(Player player, ref int buffIndex)
        {
            HookCalls++;
            throw new InvalidOperationException("Identity observation must not execute a buff");
        }
    }

    private static void ParentLoadedBuffIdentityCatalogIsNativeAndNotBehavior()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        MethodInfo? capture = typeof(GeneratorClient).GetMethod("CaptureLoadedBuffIdentities",
            BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        Equal(true, capture is not null, "native registry capture exists");
        using (var request = JsonDocument.Parse(new GeneratorClient().Prepare(
            new Item(ItemID.Wood), new Item(ItemID.Wood), new Player()).PayloadJson))
        {
            foreach (string side in new[] { "itemA", "itemB" })
            {
                JsonElement parent = request.RootElement.GetProperty(side);
                JsonElement catalog = parent.GetProperty("loadedBuffIdentitiesRaw");
                Equal("native_loaded_buff_registry", catalog.GetProperty("source").GetString(), "live identity provenance");
                Equal(true, catalog.GetProperty("scope").GetString()!.Contains("not parent behavior"), "identity is not an inherited effect");
                JsonElement poison = catalog.GetProperty("entries").EnumerateArray()
                    .Single(row => row.GetProperty("fullName").GetString() == "Terraria/Poisoned");
                Equal(BuffID.Poisoned, poison.GetProperty("id").GetInt32(), "actual engine ID, not an item mapping");
                Equal(false, parent.GetProperty("runtimeFacts").TryGetProperty("loadedBuffIdentitiesRaw", out _), "not replicated as a parent behavior fact");
                Equal(false, parent.GetProperty("fingerprint").TryGetProperty("loadedBuffIdentitiesRaw", out _), "not replicated as a fingerprint mechanic");
            }
        }
        var bounded = (JsonObject)capture!.Invoke(null, new object[] { 2 })!;
        Equal(false, bounded["complete"]!.GetValue<bool>(), "bounded vocabulary declares missing registry identities");
        Equal(2, ((JsonArray)bounded["entries"]!).Count, "bounded capture preserves a truthful partial choice set");

        const BindingFlags fields = BindingFlags.Static | BindingFlags.NonPublic;
        FieldInfo buffsField = typeof(BuffLoader).GetField("buffs", fields)!;
        FieldInfo nextField = typeof(BuffLoader).GetField("nextBuff", fields)!;
        var buffs = (IList)buffsField.GetValue(null)!;
        int next = (int)nextField.GetValue(null)!;
        var probe = new IdentityCatalogProbeBuff();
        typeof(ModType).GetProperty("Mod", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(probe, new TooltipProbeMod());
        typeof(ModBuff).GetProperty("Type", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(probe, next);
        const string fullName = "InfiniCrafterLocal/IdentityCatalogProbe";
        Equal(false, BuffID.Search.ContainsName(fullName), "isolated fixture identity name");
        Equal(false, BuffID.Search.ContainsId(next), "isolated fixture identity ID");
        IdentityCatalogProbeBuff.HookCalls = 0;
        try
        {
            buffs.Add(probe);
            nextField.SetValue(null, next + 1);
            BuffID.Search.Add(fullName, next);
            var catalog = (JsonObject)capture.Invoke(null, new object[] { 2048 })!;
            JsonObject observed = ((JsonArray)catalog["entries"]!).OfType<JsonObject>()
                .Single(row => row["fullName"]!.GetValue<string>() == "InfiniCrafterLocal/IdentityCatalogProbe");
            Equal(next, observed["id"]!.GetValue<int>(), "registered mod buff keeps actual runtime ID");
            Equal(0, IdentityCatalogProbeBuff.HookCalls, "native reference metadata does not execute arbitrary hooks");
            var paired = new GeneratorClient().Prepare(new Item(ItemID.BladeofGrass), new Item(ItemID.LightsBane), new Player());
            using var pairedJson = JsonDocument.Parse(paired.PayloadJson);
            var certified = pairedJson.RootElement.GetProperty("itemA").GetProperty("nativeContactHitStatusReference")
                .GetProperty("randomOutcomes")[0].GetProperty("alternatives")[0].GetProperty("effects")[0];
            Equal(BuffID.Poisoned, certified.GetProperty("buffId").GetInt32(), "old sword ingredients now carry the exact independently certified contact status");
            string? output = Environment.GetEnvironmentVariable("INFINI_PARENT_STATUS_PACKET");
            if (!string.IsNullOrEmpty(output))
                System.IO.File.WriteAllText(output, paired.PayloadJson);
        }
        finally
        {
            var dictionaryFlags = BindingFlags.Instance | BindingFlags.NonPublic;
            ((IDictionary)BuffID.Search.GetType().GetField("_nameToId", dictionaryFlags)!.GetValue(BuffID.Search)!).Remove(fullName);
            ((IDictionary)BuffID.Search.GetType().GetField("_idToName", dictionaryFlags)!.GetValue(BuffID.Search)!).Remove(next);
            buffs.Remove(probe);
            nextField.SetValue(null, next);
        }
    }
}
