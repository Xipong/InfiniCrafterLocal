#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Cache source syntax, never an actor/sample or evaluated AI state. Dump can
    // ask about thousands of clones; the very large native dispatcher is decoded
    // once. JSON is cloned on read so callers cannot mutate the cached program.
    private static readonly ConcurrentDictionary<MethodBase, Lazy<List<AmmoIl>>> AttackSourceCode = new();
    internal sealed class ProjectileAttackCapture
    {
        // Serialize once into immutable backing, without retaining the builder's
        // eager nodes or a second full string. Create returns independent lazy
        // wrappers: consumers materialize/mutate only their own node trees.
        private readonly JsonElement source;
        private readonly JsonElement spawns;
        internal long Characters { get; }
        internal ProjectileAttackCapture(JsonObject source, JsonArray spawns)
        {
            this.source = JsonSerializer.SerializeToElement(source);
            this.spawns = JsonSerializer.SerializeToElement(spawns);
            Characters = this.source.GetRawText().Length + (long)this.spawns.GetRawText().Length;
        }
        internal JsonObject CloneSource() => JsonObject.Create(source)!;
        internal JsonObject? CloneMechanics() => source.TryGetProperty("mechanicsSource", out var mechanics)
            ? JsonObject.Create(mechanics) : null;
        internal JsonArray CloneSpawns() => JsonArray.Create(spawns)!;
    }
    private static readonly ProjectileAttackProgramCache AttackSourcePrograms = new(
        BuildProjectileAttackSource, () => currentParentAnalysis?.ThrowIfCancelled());
    private static List<AmmoIl> AttackCode(MethodBase method)
        => AttackSourceCode.GetOrAdd(method, m => new Lazy<List<AmmoIl>>(() => ReadAmmoIl(m, preserveStructure: true, sourceGraph: true))).Value;

    internal static JsonObject CaptureProjectileAttackReference(Projectile projectile)
        // This reader inspects the currently loaded native IL; it does not borrow a frozen catalog.
        => VerifiedProjectileAttackReference(projectile, true);

    internal static JsonObject VerifiedProjectileAttackReference(Projectile projectile, bool moduleVerified)
    {
        var refusal = new JsonObject { ["source"] = "read_only_native_attack_source", ["coverage"] = new JsonObject
            { ["unresolved"] = "native_module_certificate_unavailable_or_nonvanilla_identity" } };
        if (!moduleVerified || projectile.ModProjectile is not null || projectile.type <= ProjectileID.None || projectile.type >= ProjectileID.Count) return refusal;
        int type = projectile.type, style = projectile.aiStyle;
        var admission = new JsonObject { ["ownerHitCheck"] = projectile.ownerHitCheck,
            ["ownerHitCheckDistance"] = projectile.ownerHitCheckDistance, ["usesOwnerMeleeHitCD"] = projectile.usesOwnerMeleeHitCD,
            ["scope"] = "current_projectile_fields; native_target_immunity_and_mod_hook_admission_unresolved" };
        JsonObject Analyze()
        {
            JsonObject result = ProjectileAttackSource(type, style).CloneSource();
            result.Remove("mechanicsSource"); // Separate approximate profile view, never part of the strict reference.
            result["admission"] = admission.DeepClone();
            return result;
        }
        return currentParentAnalysis is { } analysis ? analysis.Defer(Analyze) : Analyze();
    }

    // Entry identity fences invalidation: detached in-flight work may finish
    // for its borrower but cannot repopulate a cleared or replaced cache entry.
    internal sealed class ProjectileAttackProgramCache(
        Func<int, int, ProjectileAttackCapture> build, Action throwIfCancelled)
    {
        internal const int EntryLimit = 256;
        internal const long CharacterLimit = 16 * 1024 * 1024;
        private readonly object gate = new();
        private readonly Dictionary<(int Type, int Style), Entry> entries = new();
        private readonly LinkedList<(int Type, int Style)> recent = new();
        private long characters;

        private sealed class Entry(Lazy<ProjectileAttackCapture> program, LinkedListNode<(int Type, int Style)> node)
        {
            internal readonly Lazy<ProjectileAttackCapture> Program = program;
            internal readonly LinkedListNode<(int Type, int Style)> Node = node;
            internal long Characters;
        }

        private void Remove((int Type, int Style) key)
        {
            var entry = entries[key];
            entries.Remove(key);
            recent.Remove(entry.Node);
            characters -= entry.Characters;
        }

        internal ProjectileAttackCapture Get(int type, int style)
        {
            var key = (type, style);
            while (true)
            {
                throwIfCancelled();
                Entry entry;
                lock (gate)
                {
                    if (!entries.TryGetValue(key, out entry!))
                    {
                        while (entries.Count >= EntryLimit) Remove(recent.First!.Value);
                        entry = new Entry(new Lazy<ProjectileAttackCapture>(() =>
                        {
                            var complete = build(type, style);
                            // Source refusal handlers may have caught cancellation.
                            // Check the executing owner's context before publishing.
                            throwIfCancelled();
                            return complete;
                        }), recent.AddLast(key));
                        entries.Add(key, entry);
                    }
                    else
                    {
                        recent.Remove(entry.Node);
                        recent.AddLast(entry.Node);
                    }
                }
                ProjectileAttackCapture result;
                try { result = entry.Program.Value; }
                catch (OperationCanceledException)
                {
                    lock (gate)
                        if (entries.TryGetValue(key, out var failed) && ReferenceEquals(failed, entry)) Remove(key);
                    // A live borrower retries a cancelled owner's Lazy in its own
                    // context; the retired owner still exits.
                    throwIfCancelled();
                    continue;
                }
                lock (gate)
                {
                    if (entries.TryGetValue(key, out var retained) && ReferenceEquals(retained, entry)
                        && entry.Characters == 0)
                    {
                        long size = result.Characters;
                        if (size > CharacterLimit) Remove(key);
                        else
                        {
                            // This completion is a use too. Evict only the oldest
                            // entries needed to fit, not the entire working set.
                            recent.Remove(entry.Node);
                            recent.AddLast(entry.Node);
                            while (characters + size > CharacterLimit) Remove(recent.First!.Value);
                            entry.Characters = size;
                            characters += size;
                        }
                    }
                }
                // Outside the catch and after accounting: a cancelled borrower
                // cannot discard a live owner's result or leave it uncounted.
                throwIfCancelled();
                return result;
            }
        }

        internal void Clear()
        {
            lock (gate) { entries.Clear(); recent.Clear(); characters = 0; }
        }
    }

    private static ProjectileAttackCapture ProjectileAttackSource(int type, int style)
        => AttackSourcePrograms.Get(type, style);

    private static void ClearProjectileAttackCaches()
    {
        AttackSourcePrograms.Clear();
        AttackSourceCode.Clear();
        ClearNativeCSharpSourceCache();
    }

    private static JsonArray ProjectileSpawnReferences(Projectile projectile)
        => projectile.ModProjectile is null
            && projectile.type > ProjectileID.None && projectile.type < ProjectileID.Count
            ? ProjectileAttackSource(projectile.type, projectile.aiStyle).CloneSpawns() : new JsonArray();

    private static ProjectileAttackCapture BuildProjectileAttackSource(int type, int style)
    {
        var profilePhases = ParentAnalysis.ProfileJobs;
        long phaseStarted = profilePhases ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
        long phaseAllocated = profilePhases ? GC.GetAllocatedBytesForCurrentThread() : 0;
        void ProfilePhase(string phase)
        {
            if (!profilePhases) return;
            long now = System.Diagnostics.Stopwatch.GetTimestamp();
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            Console.Error.WriteLine(FormattableString.Invariant(
                $"PARENT_SOURCE type={type} style={style} phase={phase} ms={System.Diagnostics.Stopwatch.GetElapsedTime(phaseStarted, now).TotalMilliseconds:F3} allocated={allocated - phaseAllocated}"));
            phaseStarted = now; phaseAllocated = allocated;
        }
        var spawnReferences = new JsonArray();
        var result = new JsonObject { ["source"] = "read_only_native_attack_source", ["version"] = 1,
            ["identityPredicates"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
            ["scope"] = "Source statements, not execution, inheritance, final hit/DPS or a gameplay preset. Every observation requires reaching its offset. Predicates retain both successor offsets; alternatives are reaching definitions, not independent rolls. Native hook overrides/detours, enclosing dispatcher flow, hit admission and GPU/texture extent remain unresolved. Fields are live source reads, not captured AI values. Source order is significant.",
            ["units"] = "position/cone length: native world pixels (16 per Terraria block); rotation: radians; localAI/ai timing: AI invocations, not seconds; texture Frame: image coordinates; scale: dimensionless" };
        var certificates = new JsonArray(); var gaps = new JsonArray();
        var certified = new HashSet<MethodBase>();
        var mechanicsBoundReceivers = new HashSet<MethodBase>();
        var mechanicsUnboundReceivers = new HashSet<MethodBase>();
        void Certify(MethodBase method)
        {
            if (certified.Add(method)) certificates.Add(MethodSourceIdentity(method));
        }
        JsonObject Observe(MethodBase method, string role, List<AmmoIl>? slice = null, bool boundActor = false, List<JsonObject>? helperSpawns = null, List<JsonObject>? sourceEffects = null)
        {
            Certify(method);
            var observeProfile = profilePhases;
            long observeStarted = observeProfile ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
            long observeAllocated = observeProfile ? GC.GetAllocatedBytesForCurrentThread() : 0;
            void ObservePhase(string phase)
            {
                if (!observeProfile) return;
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                long allocated = GC.GetAllocatedBytesForCurrentThread();
                Console.Error.WriteLine(FormattableString.Invariant(
                    $"PARENT_OBSERVE type={type} style={style} method={SourceMember(method)} role={role} phase={phase} ms={System.Diagnostics.Stopwatch.GetElapsedTime(observeStarted, now).TotalMilliseconds:F3} allocated={allocated - observeAllocated}"));
                observeStarted = now; observeAllocated = allocated;
            }
            if (boundActor) mechanicsBoundReceivers.Add(method);
            else mechanicsUnboundReceivers.Add(method);
            try
            {
                var next = slice is null ? null : AttackCode(method).Zip(AttackCode(method).Skip(1), (a, b) => (a.Offset, b.Offset))
                    .ToDictionary(p => p.Item1, p => p.Item2);
                var body = slice is null ? ReadCompleteSourceMethod(method) : new ParentSourceMethod(method, slice, next);
                ObservePhase("decode_il_cfg");
                JsonObject? specialized = null;
                AttackSourceObservation? selectedObservation = null;
                ParentSourceMethod? selectedBody = null;
                AttackIdentitySelection? identity = null;
                string? selectionFailure = null;
                // Select the captured actor before traversing/serializing every
                // sibling's equations. Raw audit capture has an independent work
                // budget and cannot erase a successfully proved selected body.
                if (boundActor && role is "motion" or "draw" or "dispatch")
                {
                    try
                    {
                        var selection = new AttackIdentitySelection(body, type, style);
                        if (selection.Selected.Count > 0)
                        {
                            selectedBody = new ParentSourceMethod(method, slice ?? AttackCode(method), next, selectedSuccessors: selection.Selected);
                            identity = selection;
                            selectedObservation = new AttackSourceObservation(selectedBody, role, selection: selection);
                            specialized = selectedObservation.Finish();
                            specialized["identitySelection"] = selection.Receipt;
                        }
                    }
                    catch (Exception error) when (error is not OutOfMemoryException)
                    { selectionFailure = error is NotSupportedException ? error.Message : error.GetType().Name; }
                }
                ObservePhase("identity_selection");
                var observation = new AttackSourceObservation(body, role);
                JsonObject program;
                MethodBase[]? rawReferences = null;
                var analysis = currentParentAnalysis;
                if (slice is null && analysis is not null
                    && analysis.TryRawObservation(body, role, out var cachedProgram, out rawReferences))
                    program = cachedProgram!;
                else
                {
                    bool cacheable = true;
                    try { program = observation.Finish(); }
                    catch (Exception error) when (error is not OutOfMemoryException)
                    {
                        program = MethodSourceIdentity(method);
                        program["coverage"] = "unknown";
                        program["unresolved"] = error is NotSupportedException ? error.Message : error.GetType().Name;
                        cacheable = IsDeterministicRawObservationRefusal(error);
                    }
                    if (cacheable && slice is null && analysis is not null)
                        analysis.RememberRawObservation(body, role, program, observation.ReferencedMethods);
                }
                ObservePhase("raw_observation");
                if (specialized is not null) program["identitySelected"] = specialized;
                if (selectionFailure is not null) program["identitySelectionUnavailable"] = selectionFailure;
                // AI helpers use the motion view, but their projectile effects are
                // independent roots. Capture each connected sink separately so a
                // large unrelated motion expression cannot erase its spawn facts.
                if (helperSpawns is not null)
                {
                    var effects = CaptureProjectileSpawnSlices(selectedBody ?? body, identity);
                    foreach (var effect in effects.Programs)
                        if (!TryMergeProjectileSourcePrograms(program, effect)) helperSpawns.Add(effect);
                    foreach (var reference in effects.References) spawnReferences.Add(reference!.DeepClone());
                    foreach (var called in effects.Methods.Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(called);
                }
                ObservePhase("spawn_effects");
                if (sourceEffects is not null && role is "motion" or "dispatch")
                {
                    // Keep the established motion/dispatch slice even when an
                    // additional connected effect exceeds its own work budget.
                    var effects = CaptureProjectileAdditionalEffectSlices(selectedBody ?? body, identity, role);
                    foreach (var effect in effects.Programs)
                        if (!TryMergeProjectileSourcePrograms(program, effect)) sourceEffects.Add(effect);
                    foreach (var called in effects.Methods.Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(called);
                }
                ObservePhase("additional_effects");
                var exposed = specialized ?? program;
                if (exposed["observations"] is JsonArray)
                    foreach (var reference in (specialized is not null ? selectedObservation! : observation).LiteralProjectileSpawns(exposed))
                        spawnReferences.Add(reference!.DeepClone());
                foreach (var call in (rawReferences ?? observation.ReferencedMethods.ToArray()).Concat(selectedObservation?.ReferencedMethods ?? new HashSet<MethodBase>())
                    .Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(call);
                ObservePhase("source_and_spawn_refs");
                return program;
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            { ObservePhase("refused");
                return new JsonObject { ["method"] = SourceMember(method), ["coverage"] = "unknown", ["unresolved"] = error is NotSupportedException ? error.Message : error.GetType().Name }; }
        }
        MethodInfo? Native(Type owner, string name) => owner.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
            .FirstOrDefault(m => m.Name == name);
        foreach (string root in new[] { "VanillaAI", "Colliding" })
        {
            MethodInfo? method = Native(typeof(Projectile), root);
            if (method is null) { gaps.Add(root + "_root_missing"); continue; }
            try
            {
                var code = AttackCode(method);
                bool windowRefused = false;
                var windows = ProjectileIdentityWindows(code, type, style, reason => { windowRefused = true; gaps.Add(root + "_" + reason); }, meaningfulBudget: root == "VanillaAI").ToArray();
                if (windows.Length == 0) { if (!windowRefused) gaps.Add(root + "_identity_dispatch_outside_supported_source_shape"); continue; }
                var slice = windows.SelectMany(w => w.Code).GroupBy(i => i.Offset).Select(g => g.First()).OrderBy(i => i.Offset).ToList();
                var inlineEffects = new List<JsonObject>();
                var dispatch = Observe(method, root == "VanillaAI" ? "dispatch" : "collision", slice, boundActor: !method.IsStatic && method.DeclaringType == typeof(Projectile), sourceEffects: inlineEffects);
                if (inlineEffects.Count > 0) result["motionDispatchEffects"] = new JsonArray(inlineEffects.Select(p => (JsonNode?)p).ToArray());
                dispatch["identityWindows"] = new JsonArray(windows.Select(w => (JsonNode?)new JsonObject
                    { ["field"] = w.Field, ["literal"] = w.Literal, ["guardOffset"] = w.Guard }).ToArray());
                if (root == "Colliding")
                {
                    result["collision"] = dispatch;
                    // Retain the actual predicate implementation, not an invented
                    // analytic cone/AABB formula. Helpers remain source-only.
                    var helpers = new JsonArray();
                    var pending = new Queue<MethodBase>(slice.Select(i => i.Arg).OfType<MethodInfo>()
                        .Where(m => m.DeclaringType == typeof(Utils) && m.Name.Contains("Cone", StringComparison.Ordinal)));
                    var seen = new HashSet<MethodBase>();
                    while (pending.Count > 0 && seen.Count < 4)
                    {
                        MethodBase helper = pending.Dequeue(); if (!seen.Add(helper)) continue;
                        helpers.Add(Observe(helper, "predicate"));
                        foreach (var call in AttackCode(helper).Select(i => i.Arg).OfType<MethodInfo>()
                            .Where(m => m.DeclaringType == typeof(Utils) && m.Name.Contains("Cone", StringComparison.Ordinal))) pending.Enqueue(call);
                    }
                    if (helpers.Count > 0) dispatch["predicateSources"] = helpers;
                }
                else
                {
                    result["motionDispatch"] = dispatch;
                    var helpers = slice.Select(i => i.Arg).OfType<MethodInfo>().Where(m => m.DeclaringType == typeof(Projectile)
                        && m.Name is not ("Kill" or "Damage")
                        && m.GetParameters().Length == 0 && m.ReturnType == typeof(void) && m.GetMethodBody() is not null).Distinct().ToArray();
                    ParentSourceMethod? caller = null;
                    string? callerFailure = null;
                    try { caller = ParentSourceMethod.ForCallPrefixes(method, AttackCode(method), helpers); }
                    catch (Exception error) when (error is not OutOfMemoryException)
                    { callerFailure = error is NotSupportedException ? error.Message : error.GetType().Name; }
                    var helperSpawns = new List<JsonObject>();
                    var motionPrograms = helpers.Select(m => Observe(m, "motion", boundActor: caller is not null && AttackCallBindsCapturedActor(caller, caller.Statements, m), helperSpawns: helperSpawns, sourceEffects: helperSpawns)).ToArray();
                    var programs = motionPrograms.Concat(helperSpawns).ToArray();
                    if (callerFailure is not null)
                        foreach (var program in programs) program["identitySelectionUnavailable"] = "caller_prefix:" + callerFailure;
                    if (programs.Length > 0)
                    {
                        result["motion"] = new JsonObject { ["programs"] = new JsonArray(programs.Select(p => (JsonNode?)p).ToArray()) };
                        foreach (var program in programs)
                            if (program["coverage"]?.GetValue<string>() == "unknown")
                                gaps.Add("motion_source:" + program["method"]?.GetValue<string>() + ":" + program["unresolved"]?.GetValue<string>());
                    }
                    else gaps.Add("motion_helper_outside_supported_source_shape");
                }
            }
            catch (Exception error) when (error is not OutOfMemoryException) { gaps.Add(root + ":" + (error is NotSupportedException ? error.Message : error.GetType().Name)); }
        }
        ProfilePhase("ai_and_collision_dispatch");
        // Draw dispatch is selected only from actual source type comparisons or
        // integer switch selectors. No item name, controller label or ID roster.
        MethodInfo? drawRoot = Native(typeof(Main), "DrawProj_DrawSpecialProjs");
        if (drawRoot is not null)
        {
            try
            {
                var body = ReadCompleteSourceMethod(drawRoot);
                var selected = SelectedProjectileDispatch(body, type, style).ToArray();
                var helpers = selected.Select(v => v.Operand).OfType<MethodInfo>().Where(m => m.DeclaringType == typeof(Main)
                    && m.GetParameters().Any(p => p.ParameterType == typeof(Projectile)) && m.GetMethodBody() is not null).Distinct().ToArray();
                if (helpers.Length > 0)
                {
                    var observation = new AttackSourceObservation(body, "dispatch", selected);
                    var dispatch = observation.Finish(); Certify(drawRoot);
                    foreach (var call in observation.ReferencedMethods.Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(call);
                    result["draw"] = new JsonObject { ["dispatch"] = dispatch,
                        ["programs"] = new JsonArray(helpers.Select(m => (JsonNode?)Observe(m, "draw", boundActor: AttackCallBindsCapturedActor(body, selected, m))).ToArray()) };
                }
                else gaps.Add("draw_type_dispatch_outside_supported_source_shape");
            }
            catch (Exception error) when (error is not OutOfMemoryException) { gaps.Add("draw_source:" + error.GetType().Name); }
        }
        ProfilePhase("draw_dispatch");
        if ((result["motion"] is not null || result["motionDispatch"] is not null) && Native(typeof(Projectile), "UpdatePosition") is { } integration)
        {
            // This is a direct entry-point source conditioned on the captured
            // actor identity, not a claim that an enclosing Update has reached it.
            // Mutable tables, hooks and identity reads after actor escape remain
            // symbolic under the same selector safety rules as AI helpers.
            var program = Observe(integration, "motion", boundActor: true);
            if (program["identitySelected"]?["identitySelection"] is JsonObject receipt)
                receipt["scope"] = receipt["scope"]!.GetValue<string>()
                    + " Assumes captured Projectile.type/aiStyle at UpdatePosition entry; enclosing caller identity preservation is not proved.";
            if (program["identitySelected"] is JsonObject selected && program["predicates"] is JsonArray)
            {
                try { selected["identityAlternatives"] = DescribeIdentityAlternatives(ReadCompleteSourceMethod(integration), program, selected); }
                catch (Exception error) when (error is not OutOfMemoryException)
                { selected["identityAlternatives"] = new JsonObject { ["coverage"] = "unknown", ["unresolved"] = error is NotSupportedException ? error.Message : error.GetType().Name }; }
            }
            result["positionIntegration"] = program;
        }
        ProfilePhase("position_integration");
        result["lifecycle"] = CaptureProjectileLifecycleSource(type, style, spawnReferences);
        ProfilePhase("lifecycle");
        // Keep method identity as a native fact outside the optional readable
        // view, including when every conditional region was refused.
        if (Native(typeof(Projectile), "Kill") is { } lifecycleRoot) Certify(lifecycleRoot);
        result["sourceMethods"] = certificates;
        result["coverage"] = new JsonObject { ["proved"] = "bounded_native_source_observations_only", ["unresolved"] = gaps,
            ["boundaries"] = "ProjectileLoader.Colliding/ShouldUpdatePosition and all other hooks remain unevaluated; no source fact is absence of a mechanic; damage may stop before visual lifetime; held-item draw is separate and not inferred from noMelee" };
        AttachNativeCSharpSource(result, certified, spawnReferences, type, style, mechanicsBoundReceivers.Except(mechanicsUnboundReceivers).ToHashSet());
        ProfilePhase("decompiler_and_mechanics");
        var captured = new ProjectileAttackCapture(result, spawnReferences);
        ProfilePhase("immutable_source_capture");
        return captured;
    }

    // This is a syntax recognizer for immutable identity selectors, NOT an IL
    // interpreter. Only constant/type/aiStyle and the switch's integer subtraction
    // are accepted. Opaque state-dependent selectors never choose an arm.
    private static IEnumerable<ParentSourceMethod.Value> SelectedProjectileDispatch(ParentSourceMethod body, int type, int style)
    {
        int? Identity(string id, int depth = 0)
        {
            if (depth > 12) return null;
            var defs = body.Definitions(id).ToArray(); if (defs.Length != 1) return null;
            var value = defs[0];
            if (value.Op == "const" && value.Operand is int literal) return literal;
            if (value.Op == "ldfld" && value.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile))
                return f.Name == "type" ? type : f.Name == "aiStyle" ? style : null;
            if (value.Op == "sub" && value.Inputs.Count == 2 && Identity(value.Inputs[0], depth + 1) is int left && Identity(value.Inputs[1], depth + 1) is int right) return left - right;
            return null;
        }
        bool HasIdentity(string id) => body.Definitions(id).Any(v => v.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile) && f.Name is "type" or "aiStyle"
            || v.Op == "sub" && v.Inputs.Any(HasIdentity));
        var selected = new HashSet<int>();
        foreach (var branch in body.Statements.Where(v => v.Op == "switch" || v.Op.StartsWith("beq", StringComparison.Ordinal) || v.Op.StartsWith("bne", StringComparison.Ordinal)))
        {
            if (!branch.Inputs.Any(HasIdentity)) continue;
            int target;
            if (branch.Op == "switch" && branch.Operand is int[] targets && branch.Inputs.Count == 1 && Identity(branch.Inputs[0]) is int index && index >= 0 && index < targets.Length)
                target = targets[index];
            else if (branch.Inputs.Count == 2 && Identity(branch.Inputs[0]) is int a && Identity(branch.Inputs[1]) is int b && a == b && body.Blocks[branch.Block].Next.Count == 2)
                target = body.Blocks[branch.Block].Next[branch.Op.StartsWith("beq", StringComparison.Ordinal) ? 0 : 1];
            else continue;
            // Dispatch arm starts at a stack-empty basic block; follow only its
            // straight-line body. Unknown nested dispatch remains explicitly out
            // of coverage rather than leaking unrelated source arms.
            if (body.Blocks.TryGetValue(target, out var block)) selected.Add(block.Start);
        }
        return body.Statements.Where(v => selected.Contains(v.Block) && v.Operand is MethodInfo);
    }

    internal static JsonObject InspectProjectileAttackSource(MethodInfo method, string role)
    {
        var body = new ParentSourceMethod(method);
        var result = new AttackSourceObservation(body, role).Finish();
        if (role is "motion" or "dispatch")
        {
            var effects = CaptureProjectileAdditionalEffectSlices(body, null, role);
            var separate = effects.Programs.Where(program => !TryMergeProjectileSourcePrograms(result, program)).ToArray();
            if (separate.Length > 0) result["effectSources"] = new JsonArray(separate.Select(p => (JsonNode?)p).ToArray());
        }
        return result;
    }

    internal static JsonObject InspectProjectileAttackIdentitySource(MethodInfo method, int type, int style)
    {
        var body = new ParentSourceMethod(method);
        var selection = new AttackIdentitySelection(body, type, style);
        var result = new AttackSourceObservation(new ParentSourceMethod(method, selectedSuccessors: selection.Selected), "motion", selection: selection).Finish();
        result["identitySelection"] = selection.Receipt;
        return result;
    }

    // Only deterministic limits of this exact observation are reusable. Other
    // resolver/reflection failures may change and must be retried on next use.
    internal static bool IsDeterministicRawObservationRefusal(Exception error)
        => error is NotSupportedException && (error.Message.StartsWith("connected_source_dependency_count_bound:", StringComparison.Ordinal)
            || error.Message.StartsWith("connected_source_expression_work_bound:", StringComparison.Ordinal));

    private sealed class AttackSourceObservation
    {
        private readonly ParentSourceMethod body;
        private readonly string role;
        private readonly bool explicitRoots;
        private readonly AttackIdentitySelection? selection;
        private readonly ParentSourceMethod.Value[] roots, branches;
        private readonly JsonObject dependencies = new(), symbols = new();
        internal readonly HashSet<MethodBase> ReferencedMethods = new();
        private string Symbol(MemberInfo member)
        {
            if (member is MethodBase method) ReferencedMethods.Add(method);
            string full = SourceMember(member);
            string name = member.DeclaringType?.Name + "." + member.Name;
            if (symbols[name] is JsonValue existing && existing.GetValue<string>() != full) name += "#" + member.MetadataToken;
            symbols[name] = full;
            return name;
        }
        private readonly JsonArray predicates = new();
        private readonly HashSet<string> visiting = new(), predicateIds = new();
        private readonly Dictionary<int, ParentSourceMethod.Value[]> requiredBranches = new();
        private int expressionCount;
        internal Action? AdditionalExpressionWork;
        internal int ExpressionLimit = 12000;
        internal AttackSourceObservation(ParentSourceMethod body, string role, IEnumerable<ParentSourceMethod.Value>? selected = null, AttackIdentitySelection? selection = null)
        {
            this.body = body; this.role = role; this.selection = selection; explicitRoots = selected is not null;
            roots = (selected ?? body.Statements.Where(IsRoot)).Where(v => selection is null || selection.Reachable.Contains(v.Block)).OrderBy(v => v.At).ToArray();
            branches = body.Statements.Where(v => (selection is null || selection.Reachable.Contains(v.Block) && !selection.Selected.ContainsKey(v.Block)) && body.Blocks[v.Block].Next.Distinct().Count() > 1
                && (v.Op == "switch" || v.Op.StartsWith("b", StringComparison.Ordinal))).ToArray();
        }
        internal bool IsRoot(ParentSourceMethod.Value value)
        {
            if (role is "collision" or "predicate") return value.Op == "ret" || value.Operand is MethodInfo m && m.ReturnType == typeof(bool);
            if (role == "dispatch" && value.Op == "ret") return true;
            if (role == "dispatch" && value.Operand is MethodInfo effect && effect.DeclaringType == typeof(Projectile))
            {
                // Effect roots and the same native AI helper entrypoints already
                // followed below. Ordinary math/VFX calls remain dependencies only
                // when a mechanical argument or predicate actually references them.
                if (effect.Name is "NewProjectile" or "NewProjectileDirect" or "Damage" or "Kill"
                    || effect.GetParameters().Length == 0 && effect.ReturnType == typeof(void) && effect.GetMethodBody() is not null) return true;
            }
            if (role == "draw") return value.Operand is MethodBase draw && (draw.Name.Contains("Draw", StringComparison.Ordinal)
                || draw.Name == "Frame" || draw.IsConstructor && draw.DeclaringType?.Name == "Color");
            if (value.Op == "stfld" && value.Operand is FieldInfo field && (field.DeclaringType == typeof(Projectile) || field.DeclaringType == typeof(Entity)))
                return field.Name is "position" or "velocity" or "rotation" or "scale" or "timeLeft" or "direction" or "spriteDirection"
                    || role == "dispatch" && field.Name is "width" or "height" or "damage" or "knockBack" or "penetrate" or "active";
            if (value.Operand is MethodInfo call && (call.DeclaringType == typeof(Projectile) || call.DeclaringType == typeof(Entity))
                && (call.Name is "set_Center" or "Kill")) return true;
            // Native movement commonly writes velocity.Y/position.X through a
            // Vector2 address rather than replacing Entity.velocity as a whole.
            if (value.Op == "stfld" && value.Operand is FieldInfo component && component.DeclaringType == typeof(Microsoft.Xna.Framework.Vector2)
                && component.Name is "X" or "Y" && value.Inputs.Count > 0 && ContainsMotionVector(value.Inputs[0], new())) return true;
            if (value.Op.StartsWith("stind", StringComparison.Ordinal) || value.Op.StartsWith("stelem", StringComparison.Ordinal))
                return value.Inputs.Count > 0 && (ContainsClock(value.Inputs[0], new HashSet<string>()) || ContainsMotionVector(value.Inputs[0], new()));
            return false;
        }
        private bool CapturedMotionActor(string id, HashSet<string> seen)
        {
            if (seen.Count >= 128 || !seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return false;
            if (value.Op == "ldarg" && value.Operand is int slot)
                return slot == AttackActorArgument(body.Method) && !body.WrittenArguments.Contains(slot);
            return value.Op is "ldloc" or "stloc" && value.Inputs.Count == 1 && CapturedMotionActor(value.Inputs[0], seen);
        }
        private bool ContainsMotionVector(string id, HashSet<string> seen)
        {
            if (seen.Count >= 128 || !seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return false;
            // Only an address into the captured actor is a motion sink. A copied
            // Vector2 local or another actor's vector is not its movement.
            if (value.Op == "ldflda" && value.Operand is FieldInfo field && value.Inputs.Count == 1)
                return field.DeclaringType == typeof(Entity) && field.Name is "position" or "velocity"
                    ? CapturedMotionActor(value.Inputs[0], new())
                    : field.DeclaringType == typeof(Microsoft.Xna.Framework.Vector2) && field.Name is "X" or "Y"
                        && ContainsMotionVector(value.Inputs[0], seen);
            return value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives" && value.Inputs.Count > 0
                && value.Inputs.All(input => ContainsMotionVector(input, new(seen)));
        }
        private bool ContainsClock(string id, HashSet<string> seen)
            => seen.Count < 128 && seen.Add(id) && body.Values.TryGetValue(id, out var v)
                && (v.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile) && f.Name is "ai" or "localAI" || v.Inputs.Any(i => ContainsClock(i, seen)));
        private JsonArray Required(ParentSourceMethod.Value value)
        {
            var conditions = new JsonArray();
            bool cached = requiredBranches.TryGetValue(value.Block, out var required);
            List<ParentSourceMethod.Value>? found = cached ? null : new();
            // Discover lazily in the original order. Predicate expressions can
            // recurse or refuse, so publish only after this traversal succeeds.
            foreach (var branch in cached ? required! : branches.Where(b => b.Block != value.Block && body.ControlledRegion(b.Block).Contains(value.Block)))
            {
                found?.Add(branch);
                string name = "b" + branch.At; conditions.Add(name);
                if (!predicateIds.Add(name)) continue;
                predicates.Add(new JsonObject { ["id"] = name, ["at"] = branch.At, ["op"] = branch.Op,
                    ["inputs"] = new JsonArray(branch.Inputs.Select(i => (JsonNode?)JsonValue.Create(Expression(i))).ToArray()),
                    ["successors"] = new JsonArray(body.Blocks[branch.Block].Next.Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()) });
            }
            if (found is not null) requiredBranches[value.Block] = found.ToArray();
            return conditions;
        }
        private string Local(ParentSourceMethod.Value value)
        {
            string name = "l" + value.Operand + "@" + value.At;
            if (dependencies.ContainsKey(name)) return name;
            dependencies[name] = null;
            dependencies[name] = new JsonObject { ["expression"] = value.Inputs.Count == 1 ? Expression(value.Inputs[0]) : value.Op,
                ["at"] = value.At, ["block"] = value.Block, ["requiredPredicates"] = Required(value) };
            return name;
        }
        private string AddressLocal(ParentSourceMethod.Value value)
        {
            string name = "addressed_l" + value.Operand;
            if (dependencies.ContainsKey(name)) return name;
            dependencies[name] = null;
            bool Address(string id) => body.Values.TryGetValue(id, out var v) && v.Op == "ldloca" && Equals(v.Operand, value.Operand);
            var writes = body.Statements.Where(v => selection is null || selection.Reachable.Contains(v.Block)).Where(v => v.Op == "stloc" && Equals(v.Operand, value.Operand)
                || v.Inputs.Count > 0 && v.Inputs.Any(Address)).OrderBy(v => v.At).ToArray();
            dependencies[name] = new JsonObject { ["scope"] = "address_exposed_local; ordered_source_uses_and_stores; alias_effects_and_reaching_value_unresolved",
                ["orderedSourceUses"] = new JsonArray(writes.Select(v => (JsonNode?)new JsonObject { ["at"] = v.At, ["block"] = v.Block,
                    ["expression"] = v.Op == "stloc" ? Local(v) : Operation(v), ["requiredPredicates"] = Required(v) }).ToArray()) };
            return name;
        }
        private string Alternative(string id)
        {
            string expression = Expression(id);
            if (!body.Values.TryGetValue(id, out var value)) return expression;
            var conditions = Required(value);
            // A stack merge after a conditional can have no conditional stloc.
            // Retain the predecessor block/predicates of each actual value;
            // alternatives(.2,.6) alone would erase the source choice.
            return conditions.Count == 0 ? expression : "source_block(" + value.Block
                + ",requires=" + conditions.ToJsonString() + ",value=" + expression + ")";
        }

        private string Expression(string id)
        {
            AdditionalExpressionWork?.Invoke();
            if (++expressionCount > ExpressionLimit) throw new NotSupportedException("connected_source_expression_work_bound:" + expressionCount + ">" + ExpressionLimit);
            if (dependencies.Count > 192) throw new NotSupportedException("connected_source_dependency_count_bound:" + dependencies.Count + ">192");
            if (!body.Values.TryGetValue(id, out var value)) return "unresolved(" + id + ")";
            if (value.Op is "ldloca" or "address_exposed_local") return AddressLocal(value);
            // Local() installs its named dependency before walking connected
            // address uses/predicates. Re-entry references that definition; it
            // is not evidence of a loop in the native instruction stream.
            if (value.Op == "stloc") return Local(value);
            if (!visiting.Add(id)) return "loop_or_alias(" + id + ")";
            try
            {
                if (value.Op is "ldloc" or "predecessor_stack_alternatives")
                {
                    var inputs = value.Inputs.Where(i => selection is null || !body.Values.TryGetValue(i, out var definition) || selection.Reachable.Contains(definition.Block)).ToArray();
                    return inputs.Length == 1 ? Expression(inputs[0]) : "alternatives(" + string.Join(",", inputs.Select(Alternative)) + ")";
                }
                if (value.Op is "ldarg" or "ldarga" or "written_or_address_exposed_argument" && value.Operand is int slot)
                {
                    string argument = !body.Method.IsStatic && slot == 0 ? "this" : body.Method.GetParameters()[slot - (body.Method.IsStatic ? 0 : 1)].Name ?? "arg" + slot;
                    return value.Op == "ldarg" ? argument : "address_or_written(" + argument + ")";
                }
                if (value.Op == "const" || value.Op is "ldc.r4" or "ldc.r8") return SourceOperand(value.Operand)?.ToJsonString() ?? "null";
                return Operation(value);
            }
            finally { visiting.Remove(id); }
        }
        private string Operation(ParentSourceMethod.Value value)
        {
            string[] inputs = value.Inputs.Select(Expression).ToArray();
            if (value.Operand is FieldInfo field) return value.Op + "(" + Symbol(field) + (inputs.Length > 0 ? "," + string.Join(",", inputs) : "") + ")";
            if (value.Operand is MethodBase method) return Symbol(method) + "[" + string.Join(",", inputs) + "]";
            return value.Op + "(" + string.Join(",", inputs) + (value.Operand is null ? "" : ";" + (SourceOperand(value.Operand)?.ToJsonString() ?? "null")) + ")";
        }
        internal JsonArray LiteralProjectileSpawns(JsonObject program)
        {
            var references = new JsonArray();
            foreach (var call in roots.Where(v => v.Operand is MethodInfo method && method.DeclaringType == typeof(Projectile)
                && method.Name is "NewProjectile" or "NewProjectileDirect"))
            {
                var method = (MethodInfo)call.Operand!;
                int parameter = Array.FindIndex(method.GetParameters(), p => string.Equals(p.Name, "Type", StringComparison.OrdinalIgnoreCase));
                int slot = parameter + (method.IsStatic ? 0 : 1);
                var row = MethodSourceIdentity(body.Method);
                row["at"] = call.At;
                row["requiredPredicates"] = program["observations"]!.AsArray().First(v => v!["at"]!.GetValue<int>() == call.At)!["requiredPredicates"]!.DeepClone();
                var candidates = new JsonArray();
                bool unknown = parameter < 0 || slot >= call.Inputs.Count;
                if (!unknown)
                {
                    var definitions = body.Definitions(call.Inputs[slot])
                        .Where(v => selection is null || selection.Reachable.Contains(v.Block) || v.Op.StartsWith("unresolved", StringComparison.Ordinal)).ToArray();
                    unknown = definitions.Length == 0 || definitions.Any(v => v.Op != "const" || v.Operand is not int);
                    foreach (int id in definitions.Where(v => v.Op == "const" && v.Operand is int).Select(v => (int)v.Operand!).Distinct()) candidates.Add(id);
                }
                row["projectileTypes"] = candidates;
                if (unknown) row["unresolved"] = "spawn_type_requires_runtime_expression_or_unresolved_definition";
                references.Add(row);
            }
            return references;
        }

        internal JsonObject Finish()
        {
            JsonObject result = MethodSourceIdentity(body.Method);
            var observations = new JsonArray();
            foreach (var value in roots)
            {
                string kind = value.Operand is FieldInfo f ? f.Name == "scale" ? "live_scale" : f.Name == "rotation" ? "rotation" : "state_write"
                    : value.Operand is MethodBase m ? m.Name == "set_Center" ? "center_assignment" : m.Name == "Kill" ? "lifetime_end" : role + "_call" : value.Op == "ret" ? "return" : value.Inputs.Count > 0 && ContainsMotionVector(value.Inputs[0], new()) ? "state_write" : "clock_or_ai_write";
                var row = new JsonObject { ["kind"] = kind, ["at"] = value.At, ["block"] = value.Block,
                    ["requiredPredicates"] = Required(value) };
                if (value.Operand is MethodBase call)
                {
                    row["call"] = Symbol(call);
                    int skip = call.IsStatic || value.Op == "newobj" ? 0 : 1;
                    if (skip == 1 && value.Inputs.Count > 0) row["receiver"] = Expression(value.Inputs[0]);
                    row["arguments"] = new JsonObject(call.GetParameters().Select((p, n) => new KeyValuePair<string, JsonNode?>(p.Name ?? "arg" + n,
                        n + skip < value.Inputs.Count ? JsonValue.Create(Expression(value.Inputs[n + skip])) : JsonValue.Create("unresolved_signature_input"))));
                }
                else row["expression"] = Operation(value);
                observations.Add(row);
            }
            result["observations"] = observations; result["dependencies"] = dependencies; result["predicates"] = predicates; result["symbols"] = symbols;
            result["coverage"] = role == "dispatch"
                ? "effect_motion_and_ai_state_source_slice; nonselected_calls_and_opaque_helper_effects_are_unresolved; not_complete_AI_or_cadence"
                : "connected_source_slice; opaque_fields_calls_and_address_aliases_are_symbolic";
            var unknown = body.Unknown.ToList();
            if (role == "dispatch" && !explicitRoots)
            {
                var unobservedCalls = body.Statements.Where(v => !roots.Contains(v) && v.Operand is MethodInfo
                    && (selection is null || selection.Reachable.Contains(v.Block))).ToArray();
                // Passing values only rules out a direct argument alias, not
                // mutation through static/global state inside an opaque helper.
                if (unobservedCalls.Length > 0) unknown.Add("nonselected_call_global_side_effects_unresolved");
                foreach (var value in unobservedCalls)
                {
                    var call = (MethodInfo)value.Operand!;
                    int skip = call.IsStatic ? 0 : 1;
                    var parameters = call.GetParameters();
                    // Value arguments cannot alias the actor or its clock array.
                    // Reference/byref arguments and an instance receiver can;
                    // their effects stay unknown even when no return is consumed.
                    if (value.Inputs.Where((_, index) => index < skip || index - skip < parameters.Length
                            && (!parameters[index - skip].ParameterType.IsValueType || parameters[index - skip].ParameterType.IsByRef))
                        .Any(input => CapturedMotionActor(input, new()) || ContainsClock(input, new()) || ContainsMotionVector(input, new())))
                        unknown.Add("opaque_actor_call_side_effects:" + SourceMember(call) + "@" + value.At);
                }
            }
            if (unknown.Count > 0) result["unresolved"] = new JsonArray(unknown.Distinct().Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
            // Source evidence is not a prompt-size budget. CFG, expression and
            // dependency work remain bounded; never throw away complete captured
            // mechanics solely because their JSON spelling crosses a text length.
            return result;
        }
    }
}
