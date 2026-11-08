using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentItemDispatcherSourceReachesPrepare()
    {
        using var state = new NativeActorState();
        var owner = new Player();
        foreach (var pair in new[] { (ItemID.HermesBoots, ItemID.Aglet), (ItemID.MagicMirror, ItemID.Wood) })
        {
            var packet = JsonNode.Parse(new GeneratorClient().Prepare(new Item(pair.Item1), new Item(pair.Item2), owner).PayloadJson)!;
            foreach (string slot in new[] { "itemA", "itemB" })
            {
                var item = packet[slot]!; int type = item["id"]!.GetValue<int>();
                var source = item["nativeItemDispatchReference"]!;
                Equal(source.ToJsonString(), item["runtimeFacts"]!["nativeItemDispatchReference"]!.ToJsonString(), "one capture feeds the runtime envelope");
                Equal(source.ToJsonString(), item["fingerprint"]!["nativeItemDispatchReference"]!.ToJsonString(), "fingerprint retains exact dispatcher source identity");
                var records = source["roots"]!.AsArray().SelectMany(root => root!["records"]!.AsArray()).ToArray();
                if (type == ItemID.Wood) { Equal(0, records.Length, "material receives no borrowed identity region"); continue; }
                string text = string.Join("\n", records.Select(record => record!["code"]!.GetValue<string>()));
                string[] expected = type == ItemID.HermesBoots ? new[] { "type == 54", "accRunSpeed = 6f" }
                    : type == ItemID.Aglet ? new[] { "type == 285", "moveSpeed += 0.05f" }
                    : new[] { "type == 50", "itemAnimation > 0", "itemTime == itemTimeMax / 2", "RemoveAllGrapplingHooks", "Spawn(PlayerSpawnContext.RecallFromItem)" };
                foreach (string fragment in expected) Equal(true, text.Contains(fragment, StringComparison.Ordinal), "actual source retains " + fragment);
                foreach (var record in records)
                {
                    string code = record!["code"]!.GetValue<string>();
                    Equal(Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(code))).ToLowerInvariant(), record["codeSha256"]!.GetValue<string>(), "source checksum binds exact excerpt");
                    Equal(true, record["sourceIlOffsets"]!.AsArray().Count > 0, "original source offsets survive");
                    Equal(true, record["unknowns"]!.ToJsonString().Contains("local_bindings_and_receiver_aliases_not_evaluated"), "relevance is not execution");
                }
                if (type == ItemID.MagicMirror)
                    Equal(true, source.ToJsonString().Contains("!JustDroppedAnItem"), "outer mirror admission guard retained");
            }
        }
    }

    private sealed class ItemDispatchFixture : Player
    {
        internal static int Executions;
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void Conditional(Item candidate, bool allowed)
        {
            if (allowed)
            {
                if (candidate.type == 177 || candidate.type == 178) { Executions++; moveSpeed += 0.125f; }
                else { jumpSpeedBoost += 0.5f; }
            }
        }
    }

    private static void ParentItemDispatcherBoundsStayUnknown()
    {
        var method = typeof(ItemDispatchFixture).GetMethod(nameof(ItemDispatchFixture.Conditional))!;
        object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
        using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
        JsonObject Read(int identity, int bound = 24000, CancellationToken token = default)
        {
            var root = new JsonObject { ["records"] = new JsonArray(), ["unknowns"] = new JsonArray() };
            CSharpOwner.GetMethod("BuildNativeItemDispatchRegions", CSharpFlags)!.Invoke(null, new object[] { document, identity, root, token, 16, bound, 64000 });
            return root;
        }
        ItemDispatchFixture.Executions = 0;
        object declaration = document.GetType().GetField("Declaration", CSharpFlags)!.GetValue(document)!;
        string originalDeclaration = declaration.ToString()!;
        var source = Read(177); var otherArm = Read(178);
        Equal(originalDeclaration, declaration.ToString()!, "true-arm clone restores the cached original false arm and parent tree");
        Equal(source.ToJsonString(), otherArm.ToJsonString(), "compound guard never specializes away an alternative identity");
        Equal(1, source["records"]!.AsArray().Count, "synthetic typed Item guard admitted generically");
        Equal(true, source.ToJsonString().Contains("allowed"), "outer admission remains visible");
        var retained = source["records"]![0]!;
        Equal(false, retained["code"]!.GetValue<string>().Contains("jumpSpeedBoost"), "omitted false arm is not rendered");
        Equal("true", retained["enclosingConditions"]![0]!["requiredArm"]!.GetValue<string>(), "outer true admission is correctly attributed");
        var original = (System.Collections.IEnumerable)CSharpOwner.GetMethod("AttackCode", CSharpFlags)!.Invoke(null, new object[] { method })!;
        int checkedFalseStores = 0;
        foreach (object instruction in original)
        {
            var type = instruction.GetType();
            if (type.GetProperty("Op")!.GetValue(instruction) as string != "stfld"
                || type.GetProperty("Arg")!.GetValue(instruction) is not FieldInfo field || field.Name != "jumpSpeedBoost") continue;
            int offset = (int)type.GetProperty("Offset")!.GetValue(instruction)!; checkedFalseStores++;
            Equal(false, retained["sourceIlOffsets"]!.AsArray().Any(value => value!.GetValue<int>() == offset), "omitted false-arm store offset is not attributed to the excerpt");
        }
        Equal(1, checkedFalseStores, "negative provenance control locates the actual omitted false-arm store");

        Equal(0, Read(179)["records"]!.AsArray().Count, "unrelated typed identity gets no candidate body");
        var bounded = Read(177, 1);
        Equal(0, bounded["records"]!.AsArray().Count, "bound refuses whole region without clipping");
        Equal(true, bounded["unknowns"]!.ToJsonString().Contains("entire_region_omitted"), "omitted source is explicit");
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        bool cancelled = false;
        try { Read(177, token: cancellation.Token); }
        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
        Equal(true, cancelled, "warm document still respects cancellation");
        Equal(0, ItemDispatchFixture.Executions, "source inspection never executes dispatcher or hooks");
    }
}
