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

    private static void ParentItemShootingDispatcherSourceReachesPrepare()
    {
        using var state = new NativeActorState();
        var owner = new Player();
        foreach (var pair in new[] { (ItemID.DaedalusStormbow, ItemID.Boomstick), (ItemID.Megashark, ItemID.Wood) })
        {
            var packet = JsonNode.Parse(new GeneratorClient().Prepare(new Item(pair.Item1), new Item(pair.Item2), owner).PayloadJson)!;
            foreach (string slot in new[] { "itemA", "itemB" })
            {
                var item = packet[slot]!; int type = item["id"]!.GetValue<int>();
                var source = item["nativeItemDispatchReference"]!;
                Equal(source.ToJsonString(), item["runtimeFacts"]!["nativeItemDispatchReference"]!.ToJsonString(), "shooting source reaches runtime facts unchanged");
                Equal(source.ToJsonString(), item["fingerprint"]!["nativeItemDispatchReference"]!.ToJsonString(), "shooting source reaches fingerprint unchanged");
                var roots = source["roots"]!.AsArray().Where(root => root!["root"]!.GetValue<string>() == "ItemCheck_Shoot").ToArray();
                Equal(1, roots.Length, "shooting dispatcher participates in native parent capture");
                var records = roots[0]!["records"]!.AsArray();
                if (type == ItemID.Wood)
                {
                    Equal(0, records.Count, "material receives no shooting branch");
                    continue;
                }
                Equal(true, records.Count > 0, "shooting branch retained for native weapon " + type);
                Equal(0, roots[0]!["unknowns"]!.AsArray().Count, "shooting source is admitted without a timeout or bound omission");
                Equal(true, records.Count <= source["limits"]!["regionsPerRoot"]!.GetValue<int>(), "shooting root respects the shared region bound");
                string text = string.Join("\n", records.Select(record => record!["code"]!.GetValue<string>()));
                if (type == ItemID.DaedalusStormbow)
                {
                    foreach (string fragment in new[] { "MountedCenter.Y - 600f", "Main.rand.Next(-100, 101)",
                        "Main.mouseX", "Main.mouseY", "Math.Sqrt", "Main.rand.Next(-40, 41)", "Projectile.NewProjectile", "noDropItem = true" })
                        Equal(true, text.Contains(fragment, StringComparison.Ordinal), "actual shooting source retains " + fragment);
                    Equal(true, records.Any(record => record!["enclosingConditions"]!.AsArray().Any(guard =>
                        guard!["condition"]!.GetValue<string>() == "projToShoot == 76" && guard["requiredArm"]!.GetValue<string>() == "false")),
                        "projectile-dependent admission stays conditional rather than an executed guarantee");
                }
                else
                    Equal(false, text.Contains("MountedCenter.Y - 600f", StringComparison.Ordinal), "unrelated weapon does not borrow the rain launch branch");
                foreach (var record in records)
                {
                    string code = record!["code"]!.GetValue<string>();
                    Equal(Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(code))).ToLowerInvariant(), record["codeSha256"]!.GetValue<string>(), "shooting source checksum binds exact excerpt");
                    Equal(true, record["sourceIlOffsets"]!.AsArray().Count > 0, "shooting source retains IL provenance");
                    Equal(true, code.Length <= source["limits"]!["charactersPerRegion"]!.GetValue<int>(), "shooting excerpt respects the shared character bound");
                    Equal(true, record["unknowns"]!.ToJsonString().Contains("local_bindings_and_receiver_aliases_not_evaluated"), "shooting source does not invent resolved input facts");
                }
            }
        }
    }

    private static void ParentItemIdentityHelpersReachPrepare()
    {
        using var state = new NativeActorState();
        var packet = JsonNode.Parse(new GeneratorClient().Prepare(new Item(ItemID.MechanicalLens), new Item(ItemID.Wood), new Player()).PayloadJson)!;
        var roots = packet["itemA"]!["nativeItemDispatchReference"]!["roots"]!.AsArray();
        var root = roots.Single(row => row!["root"]!.GetValue<string>() == "UpdateEquips")!;
        var record = root["records"]!.AsArray().Single(row => row!["code"]!.GetValue<string>().Contains("InfoAccMechShowWires = true"))!;
        Equal(true, record["code"]!.GetValue<string>().Contains("accType == 3619 || accType == 3611"), "helper preserves both original identity alternatives");
        var bindings = record["callerBindings"]!.AsArray();
        Equal(2, bindings.Count, "inventory and conditional void-bag calls have distinct source bindings");
        Equal(true, bindings.All(binding => binding!["identitySource"]!.GetValue<string>().Contains(".type")), "each integer has a typed Item source");
        Equal(true, bindings.All(binding => binding!["enclosingForLoops"]!.AsArray().Count > 0), "inventory iteration is retained as source context");
        Equal(true, bindings.Any(binding => binding!["enclosingConditions"]!.ToJsonString().Contains("WorksInVoidBag")), "void-bag admission remains conditional");
        Equal(true, bindings.Select(binding => binding!["sourceCallIlOffset"]!.GetValue<int>()).Distinct().Count() == 2, "each binding has exact independent call provenance");
        Equal(0, packet["itemB"]!["nativeItemDispatchReference"]!["roots"]!.AsArray().Sum(row => row!["records"]!.AsArray().Count), "unrelated material gets no helper body");
    }

    private static void ParentItemIdentityHelpersRejectUnprovedBindings()
    {
        JsonObject Read(string name, int item = 177, int calls = 8, int bound = 64000, CancellationToken token = default)
        {
            var method = typeof(ItemIdentityFixture).GetMethod(name)!;
            object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
            using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
                File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
            using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
            var root = new JsonObject { ["records"] = new JsonArray(), ["unknowns"] = new JsonArray() };
            CSharpOwner.GetMethod("BuildNativeItemDispatchHelpers", CSharpFlags)!.Invoke(null, new object[] { document, item, root, token, calls, 16, 24000, bound });
            return root;
        }
        ItemIdentityFixture.Executions = 0;
        foreach (string name in new[] { "Forward", "Direct", "Duplicate", "Second" })
        {
            var root = Read(name); Equal(1, root["records"]!.AsArray().Count, "immutable Item.type helper admitted: " + name);
            var bindings = root["records"]![0]!["callerBindings"]!.AsArray();
            Equal(name == "Duplicate" ? 2 : 1, bindings.Count, "exact call-site deduplication: " + name);
            if (name == "Forward") Equal(true, bindings[0]!["enclosingConditions"]!.ToJsonString().Contains("allowed"), "caller guard retained");
            if (name == "Second") Equal(1, bindings[0]!["parameterIndex"]!.GetValue<int>(), "non-first parameter identity is bound positionally");
            Equal(0, Read(name, item: 178)["records"]!.AsArray().Count, "unrelated identity is not borrowed: " + name);
        }
        foreach (string name in new[] { "Arbitrary", "Derived", "Reassigned", "AddressExposed", "CalleeMutation", "ConditionalCall", "LoopHelperCall" })
            Equal(0, Read(name)["records"]!.AsArray().Count, "unproved integer binding is refused: " + name);
        var bounded = Read("Forward", bound: 1);
        Equal(0, bounded["records"]!.AsArray().Count, "complete helper region and binding omitted at character bound");
        Equal(true, bounded["unknowns"]!.ToJsonString().Contains("bound"), "helper character omission remains visible");
        Equal(true, Read("Direct", calls: 0)["unknowns"]!.ToJsonString().Contains("dispatcher_helper_call_bound"), "helper call work bound is explicit");
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel(); bool cancelled = false;
        try { Read("Direct", token: cancellation.Token); }
        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
        Equal(true, cancelled, "helper work obeys cancellation");
        Equal(0, ItemIdentityFixture.Executions, "inspection never executes integer helpers");
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

internal sealed class ItemIdentityFixture : Player
{
    internal static int Executions;
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private void IdentityHelper(int identity) { if (identity == 177) { Executions++; moveSpeed += 0.25f; } }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private void SecondHelper(int unrelated, int identity) { if (identity == 177) { Executions += unrelated; moveSpeed += 0.25f; } }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private void MutableHelper(int identity, bool change) { if (change) identity = 178; if (identity == 177) { Executions++; moveSpeed += 0.25f; } }
    private void Mutate(ref int identity) { identity++; }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private bool BooleanHelper(int identity) { if (identity == 177) { Executions++; moveSpeed += 0.25f; } return true; }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private void LoopyHelper(int identity) { for (int i = 0; i < 3; i++) if (identity == 177) { Executions++; moveSpeed += 0.25f; } }
    public void ConditionalCall(Item candidate) { if (BooleanHelper(candidate.type)) jumpSpeedBoost += 1f; }
    public void LoopHelperCall(Item candidate) { LoopyHelper(candidate.type); }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    public void Forward(Item candidate, bool allowed) { int identity = candidate.type; if (allowed) IdentityHelper(identity); }
    public void Direct(Item candidate) { IdentityHelper(candidate.type); }
    public void Duplicate(Item candidate) { IdentityHelper(candidate.type); IdentityHelper(candidate.type); }
    public void Second(Item candidate) { SecondHelper(9, candidate.type); }
    public void Arbitrary(int identity) { IdentityHelper(identity); }
    public void Derived(Item candidate) { IdentityHelper(candidate.type + 1); }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    public void Reassigned(Item candidate, bool change) { int identity = candidate.type; if (change) identity = 178; IdentityHelper(identity); }
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    public void AddressExposed(Item candidate) { int identity = candidate.type; Mutate(ref identity); IdentityHelper(identity); }
    public void CalleeMutation(Item candidate, bool change) { MutableHelper(candidate.type, change); }
}

