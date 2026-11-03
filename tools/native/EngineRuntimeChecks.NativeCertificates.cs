#nullable enable
using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Services;
using Mono.Cecil.Cil;

internal static partial class EngineRuntimeChecks
{
    private static void NativeSemanticCatalogsMatchLoadedContracts()
    {
        var owner = typeof(GeneratorClient);
        var verified = owner.GetMethod("NativeCatalogVerified", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string group in new[] { "attack", "ammo", "equipment", "buff_effect", "environment", "hit_status", "motion" })
            Equal(true, (bool)verified.Invoke(null, new object[] { group })!, "loaded native semantic dependency contract: " + group);
        var packet = GeneratorClient.ToWireItem(new Terraria.Item(Terraria.ID.ItemID.BladeofGrass));
        Equal(true, packet["nativeShootReference"] is not null, "actual parent wire retains proved shoot facts");
        Equal("partial_certified_source_record", packet["runtimeFacts"]!["parentSourceGraph"]!["nativeCatalogCoverage"]!["shoot"]!.GetValue<string>(), "coverage agrees with actual semantic-certified facts");
        var metadataLazy = owner.GetField("NativeMethodMetadata", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        object metadata = metadataLazy.GetType().GetProperty("Value")!.GetValue(metadataLazy)!;
        var assembly = (Mono.Cecil.AssemblyDefinition)metadata.GetType().GetProperty("Assembly")!.GetValue(metadata)!;
        var getter = assembly.MainModule.GetType("Terraria.Player").Methods.Single(m => m.Name == "get_magicDamage");
        string originalShape = NativeSourceFingerprint.Compute(getter);
        var call = getter.Body.Instructions.Single(i => i.Operand is Mono.Cecil.MethodReference m && m.Name == "get_Magic");
        object originalOperand = call.Operand;
        var changedClass = assembly.MainModule.GetType("Terraria.ModLoader.DamageClass").Methods.Single(m => m.Name == "get_Melee");
        void Clear()
        {
            foreach (string field in new[] { "NativeMethodProofs", "NativeCatalogProofs" })
            {
                object cache = owner.GetField(field, BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
                cache.GetType().GetMethod("Clear")!.Invoke(cache, null);
            }
        }
        try
        {
            call.Operand = changedClass; Clear();
            Equal(false, (bool)verified.Invoke(null, new object[] { "equipment" })!, "changed interpreted dependency with unchanged root withholds equipment");
            Equal(true, (bool)verified.Invoke(null, new object[] { "attack" })!, "unrelated catalog remains proved");
            Equal(false, NativeSourceFingerprint.Compute(getter) == originalShape, "magic-to-melee dependency change is semantic-certificate significant");
        }
        finally { call.Operand = originalOperand; Clear(); }
        Equal(true, (bool)verified.Invoke(null, new object[] { "equipment" })!, "original dependency restores proof");
        using var fixture = Mono.Cecil.ModuleDefinition.CreateModule("ScopeFixture", Mono.Cecil.ModuleKind.Dll);
        var body = new Mono.Cecil.MethodDefinition("Read", Mono.Cecil.MethodAttributes.Public | Mono.Cecil.MethodAttributes.Static, fixture.TypeSystem.Void);
        Mono.Cecil.TypeReference Type(string dependency) => new("Same", "Type", fixture, new Mono.Cecil.AssemblyNameReference(dependency, new Version(1, 0)));
        Mono.Cecil.TypeReference Array(string dependency)
        {
            var generic = new Mono.Cecil.GenericInstanceType(new Mono.Cecil.TypeReference("Collection", "List`1", fixture, new Mono.Cecil.AssemblyNameReference("Collection", new Version(1, 0))));
            generic.GenericArguments.Add(Type(dependency)); return new Mono.Cecil.ArrayType(generic);
        }
        var token = Instruction.Create(OpCodes.Ldtoken, Type("Original"));
        body.Body.Instructions.Add(token); body.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        void Different(object original, object changed, string reason)
        {
            token.Operand = original; string hash = NativeSourceFingerprint.Compute(body);
            token.Operand = changed; Equal(false, hash == NativeSourceFingerprint.Compute(body), reason);
        }
        Different(Type("Original"), Type("Other"), "same type fullname cannot hide changed assembly scope");
        Different(Array("Original"), Array("Other"), "nested generic element scope is significant");
        token.OpCode = OpCodes.Calli;
        Different(new Mono.Cecil.CallSite(Type("Original")), new Mono.Cecil.CallSite(Type("Other")), "callsite typed return scope is significant");
        token.Operand = new object(); bool refused = false;
        try { NativeSourceFingerprint.Compute(body); } catch (InvalidOperationException) { refused = true; }
        Equal(true, refused, "unsupported operand is not silently normalized away");
    }
}
