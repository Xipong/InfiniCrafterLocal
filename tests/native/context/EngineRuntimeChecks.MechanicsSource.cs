using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using Terraria;
using ICSharpCode.Decompiler.CSharp.Syntax;

internal static partial class EngineRuntimeChecks
{
    private sealed class MechanicsSourceFixture : Projectile
    {
        internal static int Executions;
        public void OverloadedIdentity(int unused) { if (type == 177) damage++; }
        public void OverloadedIdentity(float unused) { if (type == 177) damage++; }
        [MethodImpl(MethodImplOptions.NoInlining)] private static bool Touch() { Executions++; return true; }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void OpaquePrefix()
        {
            if (Touch() && type != 177) damage++;
            if (type != 177 && Touch()) damage += 9;
            if (type == 177) velocity.X *= 2;
        }
        public void ConditionalRegion()
        {
            if (aiStyle == 1)
            {
                if (type == 178) NewProjectile(null!, position.X, position.Y, 0, 0, 1, 1, 1, owner);
                if (type == 177 && Touch()) damage += 971;
                if (type == 177) damage += 972;
            }
            damage += 974; // Outside the admitted region, not included in the excerpt.
        }
        public void ConditionalForeignMutation()
        {
            if (type == 178) aiStyle = 2;
            if (aiStyle == 1) { if (type == 178) damage += 975; else damage += 976; }
        }
        public void ConditionalForeignIncrement()
        {
            if (type == 178) type++;
            if (aiStyle == 1) { if (type == 178) damage += 975; else damage += 976; }
        }
        public void ConditionalUnknownIncrement()
        {
            if (Touch()) type++;
            if (aiStyle == 1) { if (type == 178) damage += 975; else damage += 976; }
        }
        public void ConditionalUnknownMutation()
        {
            if (Touch()) aiStyle = 2;
            if (aiStyle == 1) { if (type == 178) damage += 975; else damage += 976; }
        }
        public void ConditionalRegionPriorMutation()
        {
            type = 178;
            if (aiStyle == 1) { if (type == 178) damage += 973; }
        }
        public void ConditionalRegionMutation()
        {
            if (aiStyle == 1) { type = 178; if (type == 178) damage += 973; }
        }
        public void NestedIdentity() { if (type == 177) { if (aiStyle == 1) damage += 2; else damage += 999; } else damage += 888; }
        public void UnknownMutation() { Touch(); if (type == 178) damage += 9; if (type == 177) damage++; }
        public void ExplicitMutation() { type = 178; if (type == 178) damage += 9; }
        public void AddressExposure() { TouchIdentity(ref type); if (type == 178) damage += 9; }
        private static void TouchIdentity(ref int value) { Executions++; value = 178; }
        public void ExceptionFilterMutation() { try { Touch(); } catch (Exception) when ((type = 178) > 0) { damage++; } if (type == 177) damage++; }
        public void ExceptionFilterRefEscape() { try { Touch(); } catch (Exception) when (System.Threading.Interlocked.Increment(ref type) > 0) { damage++; } if (type == 177) damage++; }
        public void ExceptionNestedIdentity()
        {
            if (type == 178) { try { Touch(); } finally { Executions++; } }
            switch (type) { case 178: try { try { Touch(); } catch { damage++; } } finally { Executions++; } break; }
            if (type == 178) damage += 979;
        }
        public void ExceptionReturnThrowFinally()
        {
            try { if (type == 178) return; if (type == 177) throw new InvalidOperationException(); }
            finally { Executions++; }
            if (type == 178) damage += 979;
        }
        public void ExceptionTryMutation() { try { type = 178; } catch { damage++; } if (type == 177) damage++; }
        public void ExceptionCatchMutation() { try { Touch(); } catch { type = 178; } if (type == 177) damage++; }
        public void ExceptionFinallyMutation() { try { Touch(); } finally { aiStyle = 2; } if (type == 177) damage++; }
        public void ExceptionRefEscape() { try { System.Threading.Interlocked.Increment(ref type); } finally { Executions++; } if (type == 177) damage++; }
        public void ExceptionIslandSiblings()
        {
            if (type == 178) damage += 971;
            try { if (type == 178) damage += 972; Touch(); }
            catch (Exception) when (Touch()) { if (type == 178) damage += 973; }
            finally { if (type == 178) damage += 974; }
            if (type == 178) damage += 975;
        }
        public void ExceptionScope() { try { if (type == 178) damage++; } finally { Executions++; } }
        public void OtherReceiver(Projectile other) { if (other.type == 178) damage++; }
        public void IdentitySwitch()
        {
            switch (type)
            {
                case 175: damage += 801; break;
                case 176: damage += 802; break;
                case 177: case 178: damage += 803; break;
                case 179: damage += 804; break;
                default: damage += 805; break;
            }
            damage += 806;
        }
        public void StyleSwitch()
        {
            switch (aiStyle)
            {
                case 0: damage += 821; break;
                case 1: damage += 822; break;
                case 2: damage += 823; break;
                case 3: damage += 824; break;
                default: damage += 825; break;
            }
        }
        public void NoDefaultSwitch()
        {
            switch (type)
            {
                case 175: NewProjectile(null!, position.X, position.Y, 0, 0, 175, 1, 1, owner); damage += 831; break;
                case 176: NewProjectile(null!, position.X, position.Y, 0, 0, 176, 1, 1, owner); damage += 832; break;
                case 177: NewProjectile(null!, position.X, position.Y, 0, 0, 177, 1, 1, owner); damage += 833; break;
                case 178: NewProjectile(null!, position.X, position.Y, 0, 0, 178, 1, 1, owner); damage += 834; break;
                case 179: NewProjectile(null!, position.X, position.Y, 0, 0, 179, 1, 1, owner); damage += 835; break;
            }
            damage += 836;
        }
        public void OpaqueSwitch()
        {
            switch (Touch() ? type : 178)
            {
                case 175: damage += 841; break;
                case 176: damage += 842; break;
                case 177: damage += 843; break;
                case 178: damage += 844; break;
                default: damage += 845; break;
            }
        }
        public void UnknownSwitch(Projectile other)
        {
            switch (other.type)
            {
                case 175: damage += 801; break;
                case 176: damage += 802; break;
                case 177: damage += 803; break;
                case 178: damage += 804; break;
                default: damage += 805; break;
            }
        }
        public void IdentityReturn()
        {
            if (type == 177) { damage += 807; return; }
            NewProjectile(null!, position.X, position.Y, 0, 0, 3, 1, 1, owner);
        }
        public void UnknownReturn() { if (Touch()) return; damage += 808; }
        public void IdentityThrow()
        {
            if (type == 177) throw new InvalidOperationException("fixture");
            damage += 809;
        }
        public void LoopBreak()
        {
            while (damage < 100) { if (type == 177) break; damage++; }
            damage += 810;
        }
        public void GotoSwitch()
        {
            switch (type)
            {
                case 175: damage += 811; goto case 177;
                case 176: damage += 812; break;
                case 177: damage += 813; break;
                case 178: damage += 814; break;
                default: damage += 815; break;
            }
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void LocalChildTypes()
        {
            int child = 0;
            if (type == 177) { child = 614; damage += 1; } else { child = 433; damage += 2; }
            if (Touch()) child = 615;
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void UnknownLocalChildType()
        {
            int child = 614;
            if (Touch()) child = damage;
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void AddressLocalChildType()
        {
            int child = 614;
            TouchIdentity(ref child);
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void MutatedLocalChildType()
        {
            int child = 614;
            if (Touch()) child++;
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void TypedReferenceChildType()
        {
            int child = 614;
            TypedReference reference = __makeref(child);
            __refvalue(reference, int) = 433;
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        public void ParameterChildType(int child)
        {
            NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void ConditionalLocalChildType()
        {
            if (aiStyle == 1)
            {
                int child = 309;
                if (type == 177) { child = 378; damage += 1; }
                NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
                child = 967;
                damage += child;
            }
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void ConditionalOuterLocalChildType()
        {
            int child = Touch() ? 309 : 378;
            if (aiStyle == 1) NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
            damage += child;
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void LoopLocalChildType()
        {
            int child = 614;
            while (Touch())
            {
                NewProjectile(null!, position.X, position.Y, 0, 0, child, 1, 1, owner);
                child = 615;
            }
        }
        public void ChildCalls()
        {
            if (type == 178) NewProjectile(null!, position.X, position.Y, 0, 0, 1, 1, 1, owner);
            if (type == 177) NewProjectile(null!, position.X, position.Y, 0, 0, 2, 1, 1, owner);
        }
    }
    private static JsonObject MechanicsFixtureRecord(string name, CancellationToken cancellation = default, bool capturedReceiverBound = true, int capturedType = 177, bool conditional = false, Type? parameterType = null)
    {
        var method = parameterType is null ? typeof(MechanicsSourceFixture).GetMethod(name)!
            : typeof(MechanicsSourceFixture).GetMethod(name, new[] { parameterType })!;
        object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
        using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
        if (conditional)
        {
            var tree = (SyntaxTree)document.GetType().GetField("Tree", CSharpFlags)!.GetValue(document)!;
            var ends = CSharpOwner.GetMethod("CSharpConditionalEnds", CSharpFlags)!.Invoke(null, new object[] { method })!;
            var guards = tree.Descendants.OfType<IfElseStatement>().Select(branch => CSharpOwner.GetMethod("ReadCSharpGuard", CSharpFlags)!
                .Invoke(null, new object[] { branch, ends })).Where(guard => guard is not null)
                .Where(guard => (string)guard!.GetType().GetProperty("Field")!.GetValue(guard)! == "aiStyle").ToArray();
            var record = new JsonObject { ["coverage"] = "conditional_ast_regions", ["entryGuards"] = new JsonArray(guards.Select(guard =>
                (JsonNode?)new JsonObject { ["ilOffset"] = (int)guard!.GetType().GetProperty("Offset")!.GetValue(guard)! }).ToArray()) };
            return (JsonObject)CSharpOwner.GetMethod("BuildMechanicsSourceView", CSharpFlags)!.Invoke(null,
                new object[] { document, capturedType, 1, cancellation, capturedReceiverBound, record })!;
        }
        return (JsonObject)CSharpOwner.GetMethod("BuildMechanicsSourceRecord", CSharpFlags)!.Invoke(null, new object[] { document, capturedType, 1, cancellation, capturedReceiverBound })!;
    }
    private static void MechanicsSourceBindsExplicitNativeRoots()
    {
        var projectile = new Projectile(); projectile.SetDefaults(Terraria.ID.ProjectileID.LastPrismLaser);
        var reference = (JsonObject)CSharpOwner.GetMethod("CaptureProjectileMechanicsSource", CSharpFlags)!.Invoke(null, new object[] { projectile })!;
        var collision = reference["records"]!.AsArray().OfType<JsonObject>().Single(record => record["method"]!.GetValue<string>() == "Terraria.Projectile.Colliding");
        Equal("captured_actor_source_binding", collision["receiverBinding"]!.GetValue<string>(), "explicit native instance root is the captured actor, not an ambiguous callee");
        Equal("approximate_identity_ast_method", collision["coverage"]!.GetValue<string>(), "collision root can specialize identity under the declared approximation");
        Equal(true, collision["removedConditionalCount"]!.GetValue<int>() > 0, "unrelated collision identities no longer force full generic source");
        Equal(false, InfiniCrafterLocal.Common.Services.GeneratorClient.CaptureProjectileAttackReference(projectile).ContainsKey("mechanicsSource"), "strict reference does not gain approximate fields");
        Console.WriteLine("mechanics region refusals: " + reference["unresolved"]!.ToJsonString());
        var dispatch = reference["records"]!.AsArray().OfType<JsonObject>().Single(record => record["method"]!.GetValue<string>() == "Terraria.Projectile.VanillaAI");
        Equal("approximate_identity_ast_regions", dispatch["coverage"]!.GetValue<string>(), "closed dispatcher region gets approximate pruning rather than oversized whole-method fallback");
        Equal(true, dispatch["removedConditionalCount"]!.GetValue<int>() > 0, "foreign identity arms are removed from dispatch region");
        Equal(true, dispatch["code"]!.GetValue<string>().Contains("aiStyle == 84"), "original entry guard survives approximate pruning");
        Equal(true, dispatch["unresolved"]!.ToJsonString().Contains("enclosing_dispatch"), "region enclosure is explicitly unknown");
        File.WriteAllText(Path.Combine(Path.GetTempPath(), "ifc-pruning-laser-dispatch.json"), dispatch.ToJsonString());
    }

    private static void MechanicsSourcePreservesEffectsAndUnknowns()
    {
        MechanicsSourceFixture.Executions = 0;
        var prefix = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OpaquePrefix));
        Equal(true, prefix["identityPruning"]!["allowed"]!.GetValue<bool>(), "safe bound method emits explicit pruning permission");
        Equal(true, prefix["identityPruning"]!["refusal"] is null, "allowed receipt has no refusal");
        var overloads = new[] { typeof(int), typeof(float) }.Select(t => MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OverloadedIdentity), parameterType: t)).ToArray();
        Equal(true, overloads[0]["metadataToken"]!.GetValue<int>() != overloads[1]["metadataToken"]!.GetValue<int>(), "overloads retain distinct real metadata tokens even with identical IL");
        foreach (var t in new[] { typeof(int), typeof(float) })
        {
            var method = typeof(MechanicsSourceFixture).GetMethod(nameof(MechanicsSourceFixture.OverloadedIdentity), new[] { t })!;
            var record = MechanicsFixtureRecord(method.Name, parameterType: t);
            Equal(method.MetadataToken, record["metadataToken"]!.GetValue<int>(), "certificate token is MethodBase token");
            Equal(method.Module.ModuleVersionId.ToString(), record["sourceModuleVersionId"]!.GetValue<string>(), "certificate binds exact module");
            Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(method.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(), record["sourceMethodSha256"]!.GetValue<string>(), "certificate binds exact IL");
        }
        string text = prefix["code"]!.GetValue<string>();
        Equal(true, text.Contains("Touch() && type != 177"), "opaque prefix remains evaluated and guarded");
        Equal(false, text.Contains("+= 9"), "pure false identity prefix excludes unevaluated short-circuit suffix and body");
        Equal(true, text.Contains("velocity.X *= 2"), "selected body effects survive");
        var region = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ConditionalRegion), conditional: true);
        string regionCode = region["code"]!.GetValue<string>();
        Equal(true, regionCode.Contains("aiStyle == 1") && regionCode.Contains("Touch()") && regionCode.Contains("971") && regionCode.Contains("972"), "region guard, runtime condition and selected effects remain");
        Equal(false, regionCode.Contains("NewProjectile") || regionCode.Contains("974"), "foreign arm and non-region tail excluded");
        Equal(1, region["excludedCallOffsets"]!.AsArray().Count, "discarded region spawn keeps exact offset exclusion");
        var unboundRegion = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ConditionalRegion), conditional: true, capturedReceiverBound: false);
        Equal(true, unboundRegion["code"]!.GetValue<string>().Contains("NewProjectile"), "unbound conditional source keeps all identity arms");
        Equal(0, unboundRegion["excludedCallOffsets"]!.AsArray().Count, "unbound region excludes no spawn offsets");
        foreach (string foreign in new[] { nameof(MechanicsSourceFixture.ConditionalForeignMutation), nameof(MechanicsSourceFixture.ConditionalForeignIncrement) })
        {
            var foreignMutation = MechanicsFixtureRecord(foreign, conditional: true);
            Equal(true, foreignMutation["code"]!.GetValue<string>().Contains("976") && !foreignMutation["code"]!.GetValue<string>().Contains("975"), "known-false foreign identity mutation does not block selected region");
        }
        foreach (string mutation in new[] { nameof(MechanicsSourceFixture.ConditionalRegionMutation), nameof(MechanicsSourceFixture.ConditionalRegionPriorMutation), nameof(MechanicsSourceFixture.ConditionalUnknownMutation), nameof(MechanicsSourceFixture.ConditionalUnknownIncrement) })
        {
            bool regionWriteRefused = false;
            try { MechanicsFixtureRecord(mutation, conditional: true); }
            catch (TargetInvocationException error) when (error.InnerException is NotSupportedException) { regionWriteRefused = true; }
            Equal(true, regionWriteRefused, "explicit identity mutation, including before region, refuses specialization");
        }
        var nested = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.NestedIdentity));
        Equal(2, nested["removedConditionalCount"]!.GetValue<int>(), "nested selected arms are both rewritten before outer clone");
        Equal(false, nested["code"]!.GetValue<string>().Contains("999") || nested["code"]!.GetValue<string>().Contains("888"), "neither discarded nested nor outer effects leak into practical code");
        Equal(true, nested["code"]!.GetValue<string>().Contains("+= 2"), "selected nested effect survives");
        var approximate = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.UnknownMutation));
        Equal("approximate_identity_ast_method", approximate["coverage"]!.GetValue<string>(), "opaque calls permit only explicitly approximate identity");
        Equal(true, approximate["code"]!.GetValue<string>().Contains("Touch()"), "opaque call itself is never erased");
        Equal(true, approximate["approximation"]!.GetValue<string>().Contains("assumed stable across opaque calls"), "assumption is explicit, not a proof");
        foreach (string name in new[] { nameof(MechanicsSourceFixture.ExplicitMutation), nameof(MechanicsSourceFixture.AddressExposure), nameof(MechanicsSourceFixture.ExceptionTryMutation), nameof(MechanicsSourceFixture.ExceptionCatchMutation), nameof(MechanicsSourceFixture.ExceptionFinallyMutation), nameof(MechanicsSourceFixture.ExceptionRefEscape), nameof(MechanicsSourceFixture.ExceptionFilterMutation), nameof(MechanicsSourceFixture.ExceptionFilterRefEscape) })
        {
            var refused = MechanicsFixtureRecord(name);
            Equal(false, refused["identityPruning"]!["allowed"]!.GetValue<bool>(), "unsafe scope has explicit denied receipt");
            Equal(true, refused["identityPruning"]!["refusal"] is not null, "denied receipt carries exact refusal");
            Equal("unpruned_method", refused["coverage"]!.GetValue<string>(), "unsafe scope preserves full source: " + name);
            Equal(0, refused["excludedCallOffsets"]!.AsArray().Count, "unsafe scope excludes no children");
            Equal(true, refused["unresolved"]!.AsArray().Count > 0, "unsafe scope reports unknown");
        }
        var exception = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionIslandSiblings));
        Equal(true, exception["identityPruning"]!["allowed"]!.GetValue<bool>(), "mapped EH permits outside-only approximation");
        Equal(2, exception["removedConditionalCount"]!.GetValue<int>(), "only sibling identity arms are removed");
        var exceptionCode = exception["code"]!.GetValue<string>();
        var originalException = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionIslandSiblings), capturedReceiverBound: false)["code"]!.GetValue<string>();
        string Island(string code)
        {
            int start = code.IndexOf("try", StringComparison.Ordinal);
            int end = code.IndexOf('{', code.IndexOf("finally", StringComparison.Ordinal));
            int depth = 1;
            while (depth > 0) { end++; if (code[end] == '{') depth++; else if (code[end] == '}') depth--; }
            return code.Substring(start, end + 1 - start);
        }
        Equal(Island(originalException), Island(exceptionCode), "entire rendered exception island, including filter and finally, is byte-identical");
        Equal(false, exceptionCode.Contains("971") || exceptionCode.Contains("975"), "foreign sibling effects removed");
        Equal(true, exceptionCode.Contains("972") && exceptionCode.Contains("973") && exceptionCode.Contains("974"), "all EH identity arms remain");
        var islandOnly = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionScope));
        Equal(0, islandOnly["removedConditionalCount"]!.GetValue<int>(), "finally-only island remains untouched");
        var nestedException = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionNestedIdentity));
        Equal(true, nestedException["identityPruning"]!["allowed"]!.GetValue<bool>(), "nested EH is mapped");
        Equal(1, nestedException["removedConditionalCount"]!.GetValue<int>(), "only the EH-free sibling is rewritten");
        Equal(0, nestedException["removedSwitchSectionCount"]!.GetValue<int>(), "switch containing EH remains intact");
        Equal(true, nestedException["code"]!.GetValue<string>().Contains("type == 178"), "identity wrapper containing EH remains intact");
        var transfers = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionReturnThrowFinally));
        var transfersOriginal = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ExceptionReturnThrowFinally), capturedReceiverBound: false);
        Equal(Island(transfersOriginal["code"]!.GetValue<string>()), Island(transfers["code"]!.GetValue<string>()), "return, throw and finally remain byte-identical");
        Equal(false, transfers.ContainsKey("spawnTypeCandidates"), "EH never uses normal-flow-only local spawn inference");
        var address = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.AddressExposure));
        Equal(true, address["unresolved"]!.ToJsonString().Contains("identity_field_address_exposure_not_pruned"), "exact IL identity-field address veto is active independently of AST spelling");
        var unbound = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ChildCalls), capturedReceiverBound: false);
        Equal(false, unbound["identityPruning"]!["allowed"]!.GetValue<bool>(), "unbound receiver has denied receipt");
        Equal("captured_receiver_binding_unproved", unbound["identityPruning"]!["refusal"]!.GetValue<string>(), "unbound receipt records reason");
        Equal("unpruned_method", unbound["coverage"]!.GetValue<string>(), "unknown caller/receiver binding keeps full source");
        Equal(0, unbound["excludedCallOffsets"]!.AsArray().Count, "unbound receiver never removes child calls");
        var other = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OtherReceiver));
        Equal(0, other["removedConditionalCount"]!.GetValue<int>(), "other actor identity is not captured receiver identity");
        Equal(true, other["code"]!.GetValue<string>().Contains("other.type"), "other receiver guard remains");
        var localChildren = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.LocalChildTypes));
        var candidates = localChildren["spawnTypeCandidates"]!.AsArray().OfType<JsonObject>().Single();
        Equal("[614,615]", candidates["projectileTypes"]!.ToJsonString(), "overwritten initializer excluded; both unknown conditional outcomes retained");
        Equal(true, candidates["at"]!.GetValue<int>() >= 0, "candidate proof names exact mapped native call offset");
        foreach (string name in new[] { nameof(MechanicsSourceFixture.UnknownLocalChildType), nameof(MechanicsSourceFixture.AddressLocalChildType),
            nameof(MechanicsSourceFixture.MutatedLocalChildType), nameof(MechanicsSourceFixture.TypedReferenceChildType), nameof(MechanicsSourceFixture.ParameterChildType) })
            Equal(false, MechanicsFixtureRecord(name).ContainsKey("spawnTypeCandidates"), "unknown, parameter, ref and mutated locals do not claim a bounded literal set");
        Equal(false, MechanicsFixtureRecord(nameof(MechanicsSourceFixture.LocalChildTypes), capturedReceiverBound: false).ContainsKey("spawnTypeCandidates"), "unbound method cannot claim spawn types");
        Equal(false, region.ContainsKey("spawnTypeCandidates"), "conditional excerpt with no retained spawn does not invent candidate evidence");
        var conditionalLocal = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ConditionalLocalChildType), conditional: true);
        Equal("[378]", conditionalLocal["spawnTypeCandidates"]![0]!["projectileTypes"]!.ToJsonString(), "closed local scope excludes overwritten and later stores at the exact spawn");
        bool outerLocalRefused = false;
        try { MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ConditionalOuterLocalChildType), conditional: true); }
        catch (TargetInvocationException error) when (error.InnerException is NotSupportedException refusal
            && refusal.Message == "csharp_region_external_local_dependency") { outerLocalRefused = true; }
        Equal(true, outerLocalRefused, "outer local without retained declaration remains an explicit unknown region");
        var loopLocal = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.LoopLocalChildType));
        Equal("[614,615]", loopLocal["spawnTypeCandidates"]![0]!["projectileTypes"]!.ToJsonString(), "loop backedge retains later store as a possible next iteration value");
        var queen = new Projectile(); queen.SetDefaults(377);
        var queenSource = (JsonObject)CSharpOwner.GetMethod("CaptureProjectileMechanicsSource", CSharpFlags)!.Invoke(null, new object[] { queen })!;
        Equal("[378]", queenSource["records"]!.AsArray().OfType<JsonObject>()
            .Single(record => record["method"]!.GetValue<string>() == "Terraria.Projectile.VanillaAI")
            ["spawnTypeCandidates"]!.AsArray().OfType<JsonObject>().Single()["projectileTypes"]!.ToJsonString(),
            "native Queen Spider scoped spawn retains only the reaching literal identity");
        var children = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ChildCalls));
        Equal(1, children["excludedCallOffsets"]!.AsArray().Count, "only exact omitted NewProjectile source offset is excluded");
        Equal(true, children["sourceMethodSha256"] is JsonValue && children["sourceModuleVersionId"] is JsonValue, "child exclusion is bound to exact original method certificate");
        Equal(0, MechanicsSourceFixture.Executions, "source reading never executes gameplay helpers");
        var switched = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.IdentitySwitch));
        string switchCode = switched["code"]!.GetValue<string>();
        Equal(false, switchCode.Contains("801") || switchCode.Contains("802") || switchCode.Contains("804") || switchCode.Contains("805"), "identity switch excludes unrelated sections");
        Equal(true, switchCode.Contains("803") && switchCode.Contains("806") && switchCode.Contains("break;"), "shared-label selected switch keeps effects, break scope and following code");
        Equal(true, switched["removedSwitchSectionCount"]!.GetValue<int>() > 0, "switch exclusions have an explicit count");
        var defaultSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.IdentitySwitch), capturedType: 180);
        Equal(true, defaultSwitch["code"]!.GetValue<string>().Contains("805") && !defaultSwitch["code"]!.GetValue<string>().Contains("803"), "unmatched identity selects literal default section");
        var styleSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.StyleSwitch));
        Equal(true, styleSwitch["code"]!.GetValue<string>().Contains("822") && !styleSwitch["code"]!.GetValue<string>().Contains("825"), "captured aiStyle switch specializes without type guesses");
        var noMatch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.NoDefaultSwitch), capturedType: 180);
        Equal(false, noMatch["code"]!.GetValue<string>().Contains("NewProjectile"), "no matching label and no default removes pure switch");
        Equal(true, noMatch["code"]!.GetValue<string>().Contains("836"), "no-match switch preserves following effects");
        Equal(5, noMatch["excludedCallOffsets"]!.AsArray().Count, "discarded switch invocation offsets are individually mapped");
        var selectedCall = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.NoDefaultSwitch));
        Equal(4, selectedCall["excludedCallOffsets"]!.AsArray().Count, "selected switch call remains in child reachability");
        var opaqueSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OpaqueSwitch));
        Equal(true, opaqueSwitch["code"]!.GetValue<string>().Contains("Touch()") && opaqueSwitch["code"]!.GetValue<string>().Contains("845"), "effectful unknown selector and its sections remain");
        var unboundSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.IdentitySwitch), capturedReceiverBound: false);
        Equal(true, unboundSwitch["code"]!.GetValue<string>().Contains("801") && unboundSwitch["code"]!.GetValue<string>().Contains("805"), "unproved receiver binding vetoes switch specialization");
        var unknownSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.UnknownSwitch));
        Equal(true, unknownSwitch["code"]!.GetValue<string>().Contains("801") && unknownSwitch["code"]!.GetValue<string>().Contains("805"), "unknown receiver switch remains intact");
        var returned = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.IdentityReturn));
        Equal(false, returned["code"]!.GetValue<string>().Contains("NewProjectile"), "selected return removes unreachable sibling tail");
        Equal(1, returned["excludedCallOffsets"]!.AsArray().Count, "unreachable call exclusion retains exact IL mapping");
        Equal(true, returned["code"]!.GetValue<string>().Contains("807"), "effect before return remains");
        Equal(false, MechanicsFixtureRecord(nameof(MechanicsSourceFixture.IdentityThrow))["code"]!.GetValue<string>().Contains("809"), "selected throw removes unreachable tail");
        Equal(true, MechanicsFixtureRecord(nameof(MechanicsSourceFixture.UnknownReturn))["code"]!.GetValue<string>().Contains("808"), "unknown conditional return does not erase reachable tail");
        Equal(true, MechanicsFixtureRecord(nameof(MechanicsSourceFixture.LoopBreak))["code"]!.GetValue<string>().Contains("810"), "loop break does not terminate enclosing method block");
        var gotoSwitch = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.GotoSwitch));
        Equal("unpruned_method", gotoSwitch["coverage"]!.GetValue<string>(), "goto case veto retains complete method");
        Equal(0, gotoSwitch["excludedCallOffsets"]!.AsArray().Count, "goto case veto excludes no calls");
        using var token = new CancellationTokenSource(); token.Cancel(); bool cancelled = false;
        try { MechanicsFixtureRecord(nameof(MechanicsSourceFixture.ChildCalls), token.Token); }
        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
        Equal(true, cancelled, "cancelled source read stops before pruning");
    }
}
