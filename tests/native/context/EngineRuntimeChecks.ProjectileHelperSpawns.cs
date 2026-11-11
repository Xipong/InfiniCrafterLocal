using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ProjectileHelperSpawnLastPrismReference()
    {
        var prism = new Item(ItemID.LastPrism);
        var raw = JsonSerializer.SerializeToNode(GeneratorClient.ProjectileRawSnapshot(prism.shoot, prism.shootSpeed, "helper_spawn_native_test", prism, -1))!.AsObject();
        Equal(true, raw["referencedProjectiles"] is JsonObject, "Last Prism native AI helper spawn must supply conditional child profiles");
        var refs = raw["referencedProjectiles"]!["references"]!.AsArray();
        var laser = refs.OfType<JsonObject>().Single(r => r["type"]!.GetValue<int>() == ProjectileID.LastPrismLaser);
        Equal(ProjectileID.LastPrismLaser, laser["profile"]!["type"]!.GetValue<int>(), "native literal laser type uses canonical profile");
        Equal(true, raw["referencedProjectiles"]!["sourceCalls"]!.AsArray().Any(r => r!["method"]!.GetValue<string>().EndsWith(".AI_075", StringComparison.Ordinal)
            && r["projectileTypes"]!.AsArray().Any(t => t!.GetValue<int>() == ProjectileID.LastPrismLaser)
            && r["requiredPredicates"]!.AsArray().Count > 0), "source call keeps helper provenance and conditional predicates");
        Equal(false, laser["profile"]!.AsObject().ContainsKey("referencedProjectiles"), "leaf helper child does not invent outgoing references");
    }
    private static int HelperSpawnExecutions;
    private static Projectile? HelperSpawnForeign = null;
    private static void HelperSpawnConditional(Projectile p)
    {
        HelperSpawnExecutions++;
        if (p.type == ProjectileID.LastPrism)
        {
            if (p.ai[0] > 0f) Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, 9, 0f);
        }
        else Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.PurpleLaser, 7, 0f);
    }
    private static void HelperSpawnDynamic(Projectile p)
    {
        int type = p.ai[0] > 0f ? ProjectileID.LastPrismLaser : (int)p.ai[1];
        Projectile.NewProjectile(null, p.Center, p.velocity, type, 11, 0f);
    }
    private static void HelperSpawnForeignIdentity(Projectile p)
    {
        if (HelperSpawnForeign!.type == ProjectileID.LastPrism)
            Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, 13, 0f);
        else Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.PurpleLaser, 17, 0f);
    }
    private static void HelperSpawnMutatedIdentity(Projectile p)
    {
        HelperSpawnMutate(p);
        if (p.type == ProjectileID.LastPrism)
            Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, 19, 0f);
        else Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.PurpleLaser, 23, 0f);
    }
    private static void HelperSpawnMutate(Projectile p) { p.type = ProjectileID.PurpleLaser; }
    private static void HelperSpawnLoop(Projectile p)
    {
        for (int i = 0; i < 3; i++)
            Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, i + 1, 0f, ai0: i);
    }
    private static void HelperSpawnTwoSites(Projectile p)
    {
        Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, 29, 0f);
        Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.PurpleLaser, 31, 0f);
    }
    private static void HelperSpawnLargeThenIndependent(Projectile p)
    {
        int value0 = (int)p.ai[0];
        int value1 = value0 + 1;
        int value2 = value1 + 1;
        int value3 = value2 + 1;
        int value4 = value3 + 1;
        int value5 = value4 + 1;
        int value6 = value5 + 1;
        int value7 = value6 + 1;
        int value8 = value7 + 1;
        int value9 = value8 + 1;
        int value10 = value9 + 1;
        int value11 = value10 + 1;
        int value12 = value11 + 1;
        int value13 = value12 + 1;
        int value14 = value13 + 1;
        int value15 = value14 + 1;
        int value16 = value15 + 1;
        int value17 = value16 + 1;
        int value18 = value17 + 1;
        int value19 = value18 + 1;
        int value20 = value19 + 1;
        int value21 = value20 + 1;
        int value22 = value21 + 1;
        int value23 = value22 + 1;
        int value24 = value23 + 1;
        int value25 = value24 + 1;
        int value26 = value25 + 1;
        int value27 = value26 + 1;
        int value28 = value27 + 1;
        int value29 = value28 + 1;
        int value30 = value29 + 1;
        int value31 = value30 + 1;
        int value32 = value31 + 1;
        int value33 = value32 + 1;
        int value34 = value33 + 1;
        int value35 = value34 + 1;
        int value36 = value35 + 1;
        int value37 = value36 + 1;
        int value38 = value37 + 1;
        int value39 = value38 + 1;
        int value40 = value39 + 1;
        int value41 = value40 + 1;
        int value42 = value41 + 1;
        int value43 = value42 + 1;
        int value44 = value43 + 1;
        int value45 = value44 + 1;
        int value46 = value45 + 1;
        int value47 = value46 + 1;
        int value48 = value47 + 1;
        int value49 = value48 + 1;
        int value50 = value49 + 1;
        int value51 = value50 + 1;
        int value52 = value51 + 1;
        int value53 = value52 + 1;
        int value54 = value53 + 1;
        int value55 = value54 + 1;
        int value56 = value55 + 1;
        int value57 = value56 + 1;
        int value58 = value57 + 1;
        int value59 = value58 + 1;
        int value60 = value59 + 1;
        int value61 = value60 + 1;
        int value62 = value61 + 1;
        int value63 = value62 + 1;
        int value64 = value63 + 1;
        int value65 = value64 + 1;
        int value66 = value65 + 1;
        int value67 = value66 + 1;
        int value68 = value67 + 1;
        int value69 = value68 + 1;
        int value70 = value69 + 1;
        int value71 = value70 + 1;
        int value72 = value71 + 1;
        int value73 = value72 + 1;
        int value74 = value73 + 1;
        int value75 = value74 + 1;
        int value76 = value75 + 1;
        int value77 = value76 + 1;
        int value78 = value77 + 1;
        int value79 = value78 + 1;
        int value80 = value79 + 1;
        int value81 = value80 + 1;
        int value82 = value81 + 1;
        int value83 = value82 + 1;
        int value84 = value83 + 1;
        int value85 = value84 + 1;
        int value86 = value85 + 1;
        int value87 = value86 + 1;
        int value88 = value87 + 1;
        int value89 = value88 + 1;
        int value90 = value89 + 1;
        int value91 = value90 + 1;
        int value92 = value91 + 1;
        int value93 = value92 + 1;
        int value94 = value93 + 1;
        int value95 = value94 + 1;
        int value96 = value95 + 1;
        int value97 = value96 + 1;
        int value98 = value97 + 1;
        int value99 = value98 + 1;
        int value100 = value99 + 1;
        int value101 = value100 + 1;
        int value102 = value101 + 1;
        int value103 = value102 + 1;
        int value104 = value103 + 1;
        int value105 = value104 + 1;
        int value106 = value105 + 1;
        int value107 = value106 + 1;
        int value108 = value107 + 1;
        int value109 = value108 + 1;
        int value110 = value109 + 1;
        int value111 = value110 + 1;
        int value112 = value111 + 1;
        int value113 = value112 + 1;
        int value114 = value113 + 1;
        int value115 = value114 + 1;
        int value116 = value115 + 1;
        int value117 = value116 + 1;
        int value118 = value117 + 1;
        int value119 = value118 + 1;
        int value120 = value119 + 1;
        int value121 = value120 + 1;
        int value122 = value121 + 1;
        int value123 = value122 + 1;
        int value124 = value123 + 1;
        int value125 = value124 + 1;
        int value126 = value125 + 1;
        int value127 = value126 + 1;
        int value128 = value127 + 1;
        int value129 = value128 + 1;
        int value130 = value129 + 1;
        int value131 = value130 + 1;
        int value132 = value131 + 1;
        int value133 = value132 + 1;
        int value134 = value133 + 1;
        int value135 = value134 + 1;
        int value136 = value135 + 1;
        int value137 = value136 + 1;
        int value138 = value137 + 1;
        int value139 = value138 + 1;
        int value140 = value139 + 1;
        int value141 = value140 + 1;
        int value142 = value141 + 1;
        int value143 = value142 + 1;
        int value144 = value143 + 1;
        int value145 = value144 + 1;
        int value146 = value145 + 1;
        int value147 = value146 + 1;
        int value148 = value147 + 1;
        int value149 = value148 + 1;
        int value150 = value149 + 1;
        int value151 = value150 + 1;
        int value152 = value151 + 1;
        int value153 = value152 + 1;
        int value154 = value153 + 1;
        int value155 = value154 + 1;
        int value156 = value155 + 1;
        int value157 = value156 + 1;
        int value158 = value157 + 1;
        int value159 = value158 + 1;
        int value160 = value159 + 1;
        int value161 = value160 + 1;
        int value162 = value161 + 1;
        int value163 = value162 + 1;
        int value164 = value163 + 1;
        int value165 = value164 + 1;
        int value166 = value165 + 1;
        int value167 = value166 + 1;
        int value168 = value167 + 1;
        int value169 = value168 + 1;
        int value170 = value169 + 1;
        int value171 = value170 + 1;
        int value172 = value171 + 1;
        int value173 = value172 + 1;
        int value174 = value173 + 1;
        int value175 = value174 + 1;
        int value176 = value175 + 1;
        int value177 = value176 + 1;
        int value178 = value177 + 1;
        int value179 = value178 + 1;
        int value180 = value179 + 1;
        int value181 = value180 + 1;
        int value182 = value181 + 1;
        int value183 = value182 + 1;
        int value184 = value183 + 1;
        int value185 = value184 + 1;
        int value186 = value185 + 1;
        int value187 = value186 + 1;
        int value188 = value187 + 1;
        int value189 = value188 + 1;
        int value190 = value189 + 1;
        int value191 = value190 + 1;
        int value192 = value191 + 1;
        int value193 = value192 + 1;
        int value194 = value193 + 1;
        int value195 = value194 + 1;
        int value196 = value195 + 1;
        int value197 = value196 + 1;
        int value198 = value197 + 1;
        int value199 = value198 + 1;
        int value200 = value199 + 1;
        int value201 = value200 + 1;
        int value202 = value201 + 1;
        int value203 = value202 + 1;
        int value204 = value203 + 1;
        int value205 = value204 + 1;
        int value206 = value205 + 1;
        int value207 = value206 + 1;
        int value208 = value207 + 1;
        int value209 = value208 + 1;
        int value210 = value209 + 1;
        Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, value210, 0f);
        Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.PurpleLaser, 1, 0f);
    }
    private static void HelperSpawnException(Projectile p)
    {
        try { HelperSpawnMutate(p); } catch (InvalidOperationException) { }
        Projectile.NewProjectile(null, p.Center, p.velocity, ProjectileID.LastPrismLaser, 37, 0f);
    }
    private static JsonObject InspectHelperSpawn(string method, int siteLimit = 32, int expressionLimit = 24000, int perSiteExpressionLimit = 12000)
        => GeneratorClient.InspectProjectileSpawnSource(typeof(EngineRuntimeChecks).GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic)!,
            ProjectileID.LastPrism, 75, siteLimit, expressionLimit, perSiteExpressionLimit);
    private static int[] HelperSpawnTypes(JsonObject source)
        => source["sourceCalls"]!.AsArray().SelectMany(r => r!["projectileTypes"]!.AsArray()).Select(t => t!.GetValue<int>()).Distinct().OrderBy(t => t).ToArray();
    private static void ProjectileHelperSpawnSlicesKeepUnknownControlFlow()
    {
        HelperSpawnExecutions = 0;
        var conditional = InspectHelperSpawn(nameof(HelperSpawnConditional));
        Equal(1, conditional["sourceCalls"]!.AsArray().Count, "captured identity excludes an immutable foreign sibling spawn");
        Equal(ProjectileID.LastPrismLaser, HelperSpawnTypes(conditional).Single(), "same native candidate from selected helper source");
        Equal(true, conditional["sourceCalls"]![0]!["requiredPredicates"]!.AsArray().Count > 0, "unknown AI guard survives on callsite");
        Equal(true, conditional.ToJsonString().Contains("Projectile.ai", StringComparison.Ordinal), "conditional source data closure remains");
        Equal(0, HelperSpawnExecutions, "inspected helper body is never executed");
        var dynamic = InspectHelperSpawn(nameof(HelperSpawnDynamic));
        Equal(1, dynamic["sourceCalls"]!.AsArray().Count, "one mixed dynamic/literal callsite");
        Equal(ProjectileID.LastPrismLaser, HelperSpawnTypes(dynamic).Single(), "known reaching literal is retained without guessing dynamic arm");
        Equal(true, dynamic["sourceCalls"]![0]!["unresolved"] is JsonValue, "dynamic alternative remains explicit alongside literal");
        foreach (string method in new[] { nameof(HelperSpawnForeignIdentity), nameof(HelperSpawnMutatedIdentity) })
        {
            var unknown = InspectHelperSpawn(method);
            Equal(2, unknown["sourceCalls"]!.AsArray().Count, "unproved actor identity cannot prune either source arm: " + method);
            Equal(2, HelperSpawnTypes(unknown).Length, "both conditional literal candidates remain: " + method);
            Equal(true, unknown["sourceCalls"]!.AsArray().All(r => r!["requiredPredicates"]!.AsArray().Count > 0), "unknown type guards remain: " + method);
        }
        var loop = InspectHelperSpawn(nameof(HelperSpawnLoop));
        Equal(1, loop["sourceCalls"]!.AsArray().Count, "loop remains one source site, never three sampled calls");
        var loopProgram = loop["programs"]![0]!["identitySelected"]!.AsObject();
        Equal(true, loopProgram["dependencies"]!.AsObject().Any(pair => pair.Value!["expression"]!.GetValue<string>().Contains(pair.Key, StringComparison.Ordinal)), "loop-carried reaching definition remains recursive source, not an evaluated value");
        // Debug IL stores the comparison in a bool local; Release branches
        // directly on the two operands. Follow connected definitions in both.
        Equal(true, loopProgram["predicates"]!.AsArray().SelectMany(predicate => predicate!["inputs"]!.AsArray())
            .Select(value => value!.GetValue<string>()).Any(input => input == "3"
                || loopProgram["dependencies"]?[input]?["expression"]?.GetValue<string>() is string expression
                    && expression.StartsWith("clt(", StringComparison.Ordinal) && expression.EndsWith(",3)", StringComparison.Ordinal)),
            "loop limit stays in the connected source predicate");
        bool refused = false;
        try { InspectHelperSpawn(nameof(HelperSpawnException)); } catch (NotSupportedException) { refused = true; }
        Equal(true, refused, "exception-bearing source is refused rather than silently ignoring handler flow");
    }
    private static void ProjectileHelperSpawnSlicesKeepBudgetRefusals()
    {
        var limited = InspectHelperSpawn(nameof(HelperSpawnTwoSites), siteLimit: 1);
        Equal(2, limited["sourceCalls"]!.AsArray().Count, "site bound retains omitted callsite identity");
        Equal(ProjectileID.LastPrismLaser, HelperSpawnTypes(limited).Single(), "later refused site cannot erase independent first slice");
        Equal(true, limited["sourceCalls"]![1]!["unresolved"]!.GetValue<string>().Contains("site_count_bound", StringComparison.Ordinal), "site bound reason remains explicit");
        Equal(0, limited["sourceCalls"]![1]!["projectileTypes"]!.AsArray().Count, "refused source cannot manufacture a child profile");
        var independent = InspectHelperSpawn(nameof(HelperSpawnLargeThenIndependent), perSiteExpressionLimit: 64);
        Equal(2, independent["sourceCalls"]!.AsArray().Count, "large and independent sink both remain accounted");
        Equal(true, independent["sourceCalls"]![0]!["unresolved"] is JsonValue, "large connected closure refuses rather than truncating fields");
        Equal(ProjectileID.PurpleLaser, HelperSpawnTypes(independent).Single(), "failed first closure does not erase later small independent slice");
        var noWork = InspectHelperSpawn(nameof(HelperSpawnTwoSites), expressionLimit: 0);
        Equal(2, noWork["sourceCalls"]!.AsArray().Count, "work bound records every refused source site");
        Equal(0, HelperSpawnTypes(noWork).Length, "no work cannot claim literal proof from a failed closure");
        Equal(true, noWork["sourceCalls"]!.AsArray().All(r => r!["unresolved"]!.GetValue<string>().Contains("expression_work_bound", StringComparison.Ordinal)), "work refusal reason is exact");
        foreach (var program in noWork["programs"]!.AsArray())
        {
            Equal("unknown", program!["coverage"]!.GetValue<string>(), "failure is not a healthy empty source method");
            Equal(true, program["unresolved"] is JsonValue, "motion coverage consumer receives the established refusal shape");
        }
        Equal(2, HelperSpawnTypes(InspectHelperSpawn(nameof(HelperSpawnTwoSites))).Length, "failed capture cannot poison a later source inspection");
    }

    private static void ProjectileHelperSpawnExactMergeIsLossless()
    {
        var source = InspectHelperSpawn(nameof(HelperSpawnTwoSites));
        Equal(1, source["programs"]!.AsArray().Count, "compatible per-sink source tables coalesce without duplicate methods");
        var original = source["programs"]![0]!.AsObject();
        Equal(2, original["identitySelected"]!["observations"]!.AsArray().Count, "both distinct spawn sites survive exact table union");
        var methodToken = typeof(EngineRuntimeChecks).GetMethod(nameof(HelperSpawnTwoSites), BindingFlags.Static | BindingFlags.NonPublic)!.MetadataToken;
        Equal(methodToken, original["metadataToken"]!.GetValue<int>(), "outer certificate preserves actual source method token");
        Equal(methodToken, original["identitySelected"]!["metadataToken"]!.GetValue<int>(), "selected graph preserves actual source method token");
        var merge = typeof(GeneratorClient).GetMethod("TryMergeProjectileSourcePrograms", BindingFlags.Static | BindingFlags.NonPublic)!;
        bool Merge(JsonObject target, JsonObject addition) => (bool)merge.Invoke(null, new object[] { target, addition })!;
        var duplicate = original.DeepClone().AsObject();
        Equal(true, Merge(duplicate, original.DeepClone().AsObject()), "exact duplicate source program can coalesce");
        Equal(true, JsonNode.DeepEquals(original, duplicate), "exact merge has no semantic or ordered-row change");
        // Independent source sinks may encounter overloads in another order.
        // Full member identity aligns their aliases without changing baseline
        // spellings, native string constants or an unknown future schema.
        const string alias = "Projectile.NewProjectile#123";
        var renamed = original.DeepClone().AsObject();
        var renamedProgram = renamed["identitySelected"]!.AsObject();
        var renamedSymbols = renamedProgram["symbols"]!.AsObject();
        renamedSymbols[alias] = renamedSymbols["Projectile.NewProjectile"]!.DeepClone();
        renamedSymbols.Remove("Projectile.NewProjectile");
        foreach (var row in renamedProgram["observations"]!.AsArray())
            if (row!["call"]?.GetValue<string>() == "Projectile.NewProjectile") row["call"] = alias;
        string renamedBefore = renamed.ToJsonString();
        var reboundTarget = original.DeepClone().AsObject();
        Equal(true, Merge(reboundTarget, renamed), "equal typed source member can merge despite sink-local alias spelling");
        Equal(original.ToJsonString(), reboundTarget.ToJsonString(), "alias union keeps original accepted spellings and all rows");
        Equal(renamedBefore, renamed.ToJsonString(), "incoming source graph remains immutable during namespace alignment");
        var textSource = renamed.DeepClone().AsObject();
        textSource["identitySelected"]!["symbols"]!["Nullable`1..ctor"] = "System.Nullable`1[System.Int32]..ctor(System.Int32)";
        textSource["identitySelected"]!["dependencies"]!["literal_text"] = new JsonObject {
            ["expression"] = "Nullable`1..ctor[" + alias + "[\"" + alias + "\"]]", ["at"] = 2000000000, ["block"] = 0, ["requiredPredicates"] = new JsonArray() };
        var textTarget = original.DeepClone().AsObject();
        Equal(true, Merge(textTarget, textSource), "known symbolic expression can align identifiers around quoted native text");
        Equal("Nullable`1..ctor[Projectile.NewProjectile[\"" + alias + "\"]]", textTarget["identitySelected"]!["dependencies"]!["literal_text"]!["expression"]!.GetValue<string>(), "generic type atom and native string constant remain literal while member identifier is rebound");
        var unknownNamespace = renamed.DeepClone().AsObject();
        unknownNamespace["identitySelected"]!["observations"]![0]!["futureSymbolUse"] = alias;
        var unknownTarget = original.DeepClone().AsObject();
        Equal(false, Merge(unknownTarget, unknownNamespace), "unrecognized expression fields refuse alias alignment");
        Equal(original.ToJsonString(), unknownTarget.ToJsonString(), "unrecognized schema cannot partly rename baseline");

        foreach (string mismatch in new[] { "identity", "symbol", "observation", "duplicate_row", "missing_offset", "future_wrapper", "method_token", "wrapper_token", "missing_token", "future_graph" })
        {
            var target = original.DeepClone().AsObject(); var addition = original.DeepClone().AsObject();
            var selected = addition["identitySelected"]!.AsObject();
            if (mismatch == "identity") selected["identitySelection"]!["identityPredicates"]!["Projectile.type"] = ProjectileID.PurpleLaser;
            if (mismatch == "symbol") selected["symbols"]!["Projectile.NewProjectile"] = "different_overload_signature";
            if (mismatch == "observation") selected["observations"]![0]!["arguments"]!["Damage"] = "999";
            if (mismatch == "duplicate_row") selected["observations"]!.AsArray().Add(selected["observations"]![0]!.DeepClone());
            if (mismatch == "missing_offset") selected["observations"]![0]!.AsObject().Remove("at");
            if (mismatch == "method_token") selected["metadataToken"] = methodToken + 1;
            if (mismatch == "wrapper_token") addition["metadataToken"] = methodToken + 1;
            if (mismatch == "missing_token") selected.Remove("metadataToken");
            if (mismatch == "future_graph") selected["futureEffectProvenance"] = "must_remain_literal";
            if (mismatch == "future_wrapper") addition["futureEffectProvenance"] = "must_remain_literal";
            Equal(false, Merge(target, addition), "incompatible source union refused: " + mismatch);
            Equal(original.ToJsonString(), target.ToJsonString(), "refusal cannot partly mutate accepted source tables: " + mismatch);
        }
    }

}
