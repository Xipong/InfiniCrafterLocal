#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceGraph
    {
        // Discovery bounds limit analysis work. Export bounds limit transport.
        // Neither a method's size nor its export refusal can erase discovery.
        private readonly Dictionary<int, int> priorities = new();
        private readonly Dictionary<int, HashSet<int>> discoveryParents = new();
        private readonly HashSet<int> discoveryRoots = new(), principalNodes = new();
        private readonly Dictionary<string, HashSet<FieldInfo>> deferredConsumerFocus = new(StringComparer.Ordinal);
        private readonly Dictionary<int, (ParentSourceMethod Body, ParentSourceMethod.Value[] Statements)> projections = new();
        private readonly Queue<(Action Admit, int? Parent)> deferred = new();
        private int currentPriority, omittedDiscoveryRoots;
        private int? currentNode;

        private void RememberPath(int node)
        {
            if (currentNode is not int parent) { discoveryRoots.Add(node); return; }
            if (parent == node) return;
            if (!discoveryParents.TryGetValue(node, out var parents)) discoveryParents[node] = parents = new();
            parents.Add(parent);
        }

        private void Defer(Action admit)
        {
            if (deferred.Count >= DiscoveryNodeLimit) { Gap("deferred_dispatch_candidate_limit"); return; }
            deferred.Enqueue((admit, currentNode));
        }

        private void Drain()
        {
            while (pending.Count > 0)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                var next = pending.Dequeue();
                currentPriority = priorities[next.Node];
                currentNode = next.Node;
                currentInvocation = invocations[next.Node];
                try { Inspect(next.Node, next.Method, next.Depth, next.Focus); }
                catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
                {
                    var failure = CompactMethod(MethodSourceIdentitySafe(next.Method), next.Method);
                    failure["id"] = next.Node; failure["coverage"] = "unsupported_source_projection";
                    projections.Remove(next.Node);
                    AddInvocation(failure, next.Node);
                    nodes[next.Node] = failure; Gap("unsupported_source_projection");
                }
                finally { currentNode = null; currentInvocation = default; }
            }
        }

        private static IEnumerable<ParentSourceMethod.Value> DiscoveryValues(ParentSourceMethod body,
            ParentSourceMethod.Value[] statements)
        {
            var selected = new HashSet<string>();
            void Include(string id)
            {
                var work = new Stack<string>(); work.Push(id);
                while (work.Count > 0)
                {
                    string next = work.Pop();
                    if (!selected.Add(next) || !body.Values.TryGetValue(next, out var value)) continue;
                    foreach (string input in value.Inputs) work.Push(input);
                }
            }
            foreach (var statement in statements) Include(statement.Id);
            var branchOffsets = body.Blocks.Values.Where(block => block.Next.Distinct().Count() > 1)
                .Select(block => block.Code[^1].Offset).ToHashSet();
            var branches = body.Statements.Where(value => branchOffsets.Contains(value.At)).ToArray();
            int previous;
            do
            {
                previous = selected.Count;
                var blocks = selected.Where(body.Values.ContainsKey).Select(id => body.Values[id].Block).ToHashSet();
                foreach (var branch in branches)
                    if (blocks.Overlaps(body.ControlledRegion(branch.Block))) Include(branch.Id);
            } while (previous != selected.Count);
            return body.Values.Values.Where(value => selected.Contains(value.Id));
        }

        private static bool WritesSourceStorage(ParentSourceMethod.Value value)
            => value.Op.StartsWith("stind", StringComparison.Ordinal) || value.Op.StartsWith("stelem", StringComparison.Ordinal)
                || value.Op is "stfld" or "stsfld" or "stobj" or "cpobj" or "initobj";

        private static bool HasMutableArguments(ParentSourceMethod.Value value)
            => value.Operand is MethodBase call && call.GetParameters().Any(parameter => parameter.ParameterType.IsByRef || parameter.ParameterType.IsArray);

        private static bool IsSpawnOrBuff(ParentSourceMethod.Value value)
            => value.Operand is MethodInfo call &&
                (call.DeclaringType == typeof(Terraria.Projectile) && call.Name is "NewProjectile" or "NewProjectileDirect"
                || (call.DeclaringType == typeof(Terraria.NPC) || call.DeclaringType == typeof(Terraria.Player)) && call.Name == "AddBuff");

        private static bool IsActorType(Type? type)
            => type is not null && (typeof(Terraria.Entity).IsAssignableFrom(type) || typeof(Terraria.Item).IsAssignableFrom(type));

        private static bool WritesActorState(ParentSourceMethod body, ParentSourceMethod.Value value, bool includeModState = true)
        {
            bool Field(FieldInfo field) => IsActorType(field.DeclaringType)
                || includeModState && field.DeclaringType?.Assembly == body.Method.DeclaringType?.Assembly
                    && field.DeclaringType?.Assembly != typeof(Terraria.Projectile).Assembly
                    && field.DeclaringType?.Assembly != typeof(Microsoft.Xna.Framework.Vector2).Assembly
                    && field.DeclaringType?.Assembly != typeof(object).Assembly;
            if (value.Operand is MethodInfo setter && IsActorType(setter.DeclaringType)
                && (setter.Name.StartsWith("set_", StringComparison.Ordinal) || setter.Name is "Kill" or "Damage")) return true;
            if (!WritesSourceStorage(value)) return false;
            if (value.Operand is FieldInfo field && Field(field)) return true;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            bool ActorAddress(string id)
            {
                if (!seen.Add(id) || seen.Count > 64) return false;
                return body.Definitions(id).Any(origin => origin.Operand is FieldInfo destination && Field(destination)
                    || origin.Op is "ldflda" or "ldelema" or "ldind.ref" or "castclass" && origin.Inputs.Count > 0 && ActorAddress(origin.Inputs[0])
                    || origin.Operand is MethodInfo getter && getter.ReturnType.IsByRef && IsActorType(getter.DeclaringType));
            }
            return value.Inputs.Count > 0 && ActorAddress(value.Inputs[0]);
        }

        // Bounded source-selection normalization only. A formal output is not an
        // actor-state write: helper signatures alone must not make calls causal.
        private static bool WritesMethodOutput(ParentSourceMethod body, ParentSourceMethod.Value value)
        {
            if (value.Op == "ret" && value.Inputs.Count > 0) return true;
            // IsIn alone is marshaling metadata: [In] ref still permits managed
            // writes. Only the compiler's readonly parameter markers exclude it.
            static bool WritableByRef(ParameterInfo parameter) => parameter.ParameterType.IsByRef
                && !parameter.GetCustomAttributesData().Any(attribute => attribute.AttributeType.FullName is
                    "System.Runtime.CompilerServices.IsReadOnlyAttribute" or "System.Runtime.CompilerServices.RequiresLocationAttribute");
            var parameters = body.Method.GetParameters();
            bool OutputAddress(string id)
            {
                bool formalByRef = false;
                var seen = new HashSet<string>(StringComparer.Ordinal);
                var work = new Stack<string>(); work.Push(id);
                while (work.Count > 0)
                {
                    string next = work.Pop();
                    if (!seen.Add(next)) continue;
                    if (seen.Count > 128 || !body.Values.TryGetValue(next, out var address)) return false;
                    if (address.Op == "ldarg" && address.Operand is int argument)
                    {
                        int formal = argument - (body.Method.IsStatic ? 0 : 1);
                        if (formal < 0 || formal >= parameters.Length || !WritableByRef(parameters[formal])) return false;
                        formalByRef = true;
                    }
                    else if (address.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                    {
                        if (address.Inputs.Count == 0) return false;
                        foreach (string input in address.Inputs) work.Push(input);
                    }
                    else if (address.Op == "ldflda" && address.Inputs.Count == 1) work.Push(address.Inputs[0]);
                    // Local addresses, by-value argument addresses, ref returns,
                    // and written/address-exposed unknowns do not prove output.
                    else return false;
                }
                return formalByRef;
            }
            if (WritesSourceStorage(value) && value.Op != "stsfld" && value.Inputs.Count > 0
                && OutputAddress(value.Inputs[0])) return true;
            if (value.Op is not ("call" or "callvirt" or "newobj") || value.Operand is not MethodBase call) return false;
            var arguments = call.GetParameters();
            for (int index = 0; index < arguments.Length; index++)
            {
                int slot = index + (!call.IsStatic && value.Op != "newobj" ? 1 : 0);
                if (WritableByRef(arguments[index])
                    && slot < value.Inputs.Count && OutputAddress(value.Inputs[slot])) return true;
            }
            // A value-type instance call can mutate its receiver in place. A
            // constructor allocation has arguments but no implicit receiver.
            return value.Op != "newobj" && !call.IsStatic && call.DeclaringType?.IsValueType == true
                && !call.DeclaringType.IsDefined(typeof(System.Runtime.CompilerServices.IsReadOnlyAttribute), inherit: false)
                && !call.IsDefined(typeof(System.Runtime.CompilerServices.IsReadOnlyAttribute), inherit: false)
                && value.Inputs.Count > 0 && OutputAddress(value.Inputs[0]);
        }

        private static int StatementPriority(ParentSourceMethod.Value value, ParentSourceMethod body)
            => IsSpawnOrBuff(value) ? 0
            : value.Operand is MethodInfo effect && effect.ReturnType == typeof(void)
                && effect.DeclaringType?.Assembly == body.Method.DeclaringType?.Assembly
                && body.Method.DeclaringType?.Assembly != typeof(Terraria.NPC).Assembly ? 0
            : WritesActorState(body, value) ? 1
            : value.Op == "ret" && value.Inputs.Count > 0 ? 2
            : WritesMethodOutput(body, value) ? 1
            : value.Operand is MethodBase helper && helper.DeclaringType?.Assembly == body.Method.DeclaringType?.Assembly
                && body.Method.DeclaringType?.Assembly != typeof(Terraria.NPC).Assembly ? 3
            : HasMutableArguments(value) || WritesSourceStorage(value) ? 4
            : value.Op is "call" or "callvirt" ? 5 : 6;

        private static ParentSourceMethod.Value[][] StatementGroups(ParentSourceMethod body, ParentSourceMethod.Value[] statements)
        {
            // An array/ref-writing call and the stores/returns consuming that
            // same source allocation form one evidence bundle. Otherwise a scan
            // can survive while its output write disappears (or vice versa).
            var users = new Dictionary<string, List<string>>(StringComparer.Ordinal);
            foreach (var value in body.Values.Values)
                foreach (string input in value.Inputs)
                {
                    if (!users.TryGetValue(input, out var list)) users[input] = list = new();
                    list.Add(value.Id);
                }
            var groups = new List<ParentSourceMethod.Value[]>();
            var covered = new HashSet<string>(StringComparer.Ordinal);
            foreach (var call in statements.Where(HasMutableArguments))
            {
                if (covered.Contains(call.Id)) continue;
                var method = (MethodBase)call.Operand!;
                var parameters = method.GetParameters();
                var origins = new HashSet<string>(StringComparer.Ordinal);
                for (int index = 0; index < parameters.Length; index++)
                {
                    if (!parameters[index].ParameterType.IsArray && !parameters[index].ParameterType.IsByRef) continue;
                    int slot = index + (!method.IsStatic && call.Op != "newobj" ? 1 : 0);
                    if (slot >= call.Inputs.Count) continue;
                    foreach (var value in body.Definitions(call.Inputs[slot]))
                    {
                        if (value.Op is "newarr" or "ldarg" or "address_exposed_local") origins.Add(value.Id);
                        if (value.Op == "ldloca" && value.Operand is int local)
                        {
                            origins.Add(value.Id);
                            foreach (var read in body.Values.Values.Where(candidate => candidate.Op == "address_exposed_local"
                                && Equals(candidate.Operand, local))) origins.Add(read.Id);
                        }
                    }
                }
                var reached = new HashSet<string>(origins, StringComparer.Ordinal);
                var work = new Queue<string>(origins);
                while (work.Count > 0)
                    if (users.TryGetValue(work.Dequeue(), out var next))
                        foreach (string id in next) if (reached.Add(id)) work.Enqueue(id);
                var group = statements.Where(value => value == call || reached.Contains(value.Id)
                    && (WritesSourceStorage(value) || HasMutableArguments(value) || value.Op == "ret" && value.Inputs.Count > 0)).ToArray();
                foreach (var value in group) covered.Add(value.Id);
                groups.Add(group);
            }
            var returns = statements.Where(value => value.Op == "ret" && value.Inputs.Count > 0 && !covered.Contains(value.Id)).ToArray();
            if (returns.Length > 0)
            {
                groups.Add(returns);
                foreach (var value in returns) covered.Add(value.Id);
            }
            groups.AddRange(statements.Where(value => !covered.Contains(value.Id)).Select(value => new[] { value }));
            return groups.OrderBy(group => group.Min(value => StatementPriority(value, body)))
                .ThenBy(group => group.Min(value => value.At)).ToArray();
        }

        private JsonObject ExportCoreRow(int node) => ExportMechanicalRow(node, expanded: false);

        private JsonObject ExportMechanicalRow(int node, bool expanded)
        {
            if (!projections.TryGetValue(node, out var source)) return IdentityRow(node);
            var groups = StatementGroups(source.Body, source.Statements);
            var nativeRoots = invocations[node].ProjectileType is not null && !invocations[node].NativeIdentityUnbound
                ? new AttackSourceObservation(source.Body, "dispatch", selected: Array.Empty<ParentSourceMethod.Value>()) : null;
            bool Mechanical(ParentSourceMethod.Value value) => nativeRoots is not null
                ? nativeRoots.IsRoot(value) && !(value.Op == "ret" && value.Inputs.Count == 0)
                : WritesActorState(source.Body, value) || WritesMethodOutput(source.Body, value);
            int CoreRank(ParentSourceMethod.Value[] group)
                => group.Any(IsSpawnOrBuff) ? 0
                    : group.Any(HasMutableArguments) && group.Any(Mechanical) ? 1
                    : group.Any(Mechanical) ? 2
                    : group.Any(value => value.Op == "ret" && value.Inputs.Count > 0) ? 3 : 4;
            int rank = groups.Length == 0 ? 4 : groups.Min(CoreRank);
            var selected = (rank < 4 ? groups.Where(group => CoreRank(group) <= (expanded ? Math.Max(rank, 2) : rank)).SelectMany(group => group)
                : groups.Take(1).SelectMany(group => group)).Distinct().OrderBy(value => value.At).ToArray();
            var mechanicalFields = DiscoveryValues(source.Body, selected).Select(value => value.Operand).OfType<FieldInfo>().ToHashSet();
            bool CoreTarget(int target) => !invocations[target].NativeIdentityUnbound
                && (principalNodes.Contains(target) || invocations[target].ProjectileType is not null
                    || projections.TryGetValue(target, out var destination) && destination.Statements.Any(value =>
                        IsSpawnOrBuff(value) || WritesActorState(destination.Body, value, includeModState: false)
                        || WritesSourceStorage(value) && value.Operand is FieldInfo field && mechanicalFields.Contains(field)));
            var causalOffsets = edges.OfType<JsonObject>().Where(edge => edge["from"]?.GetValue<int>() == node
                && edge["to"] is JsonNode target && CoreTarget(target.GetValue<int>()) && edge["at"] is not null)
                .Select(edge => edge["at"]!.GetValue<int>()).ToHashSet();
            selected = selected.Concat(source.Statements.Where(value => causalOffsets.Contains(value.At)))
                .Distinct().OrderBy(value => value.At).ToArray();
            var projection = source.Body.ProjectForGraph(selected);
            var bound = projection.Bind(Member);
            // The minimal mechanical bundle gets its full declared controls
            // before optional statements compete for the remaining transport.
            if (bound.Characters > SourceGraphProjection.CharacterLimit) return IdentityRow(node);
            var row = projection.Materialize(bound.Members);
            row["id"] = node; AddInvocation(row, node);
            row["sourceSelection"] = rank < 4 || causalOffsets.Count > 0 ? "mechanical_core" : "optional_source";
            if (selected.Length != source.Statements.Length) row["omittedStatementCount"] = source.Statements.Length - selected.Length;
            return row;
        }

        private JsonObject ExportRow(int node, int characterLimit)
        {
            if (!projections.TryGetValue(node, out var source)) return nodes[node]!.DeepClone().AsObject();
            var selected = source.Statements;
            var groups = StatementGroups(source.Body, source.Statements);
            int groupCount = groups.Length;
            while (true)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                // Keep the declared control-dependency bound. Drop optional
                // statements before guards; any final guard omission stays explicit.
                var projection = source.Body.ProjectForGraph(selected);
                var bound = projection.Bind(Member);
                if (bound.Characters <= characterLimit)
                {
                    var row = projection.Materialize(bound.Members);
                    row["id"] = node;
                    AddInvocation(row, node);
                    if (selected.Length != source.Statements.Length)
                        row["omittedStatementCount"] = source.Statements.Length - selected.Length;
                    return row;
                }
                if (groupCount <= 1)
                {
                    // Only after reducing to one evidence bundle may an enclosing
                    // dependency exceed the method bound. Keep its explicit
                    // unresolved guard count instead of claiming completeness.
                    foreach (int controlLimit in new[] { 8, 0 })
                    {
                        projection = source.Body.ProjectForGraph(selected, controlLimit);
                        bound = projection.Bind(Member);
                        if (bound.Characters > characterLimit) continue;
                        var row = projection.Materialize(bound.Members);
                        row["id"] = node;
                        AddInvocation(row, node);
                        if (selected.Length != source.Statements.Length)
                            row["omittedStatementCount"] = source.Statements.Length - selected.Length;
                        return row;
                    }
                    return IdentityRow(node);
                }
                groupCount = Math.Max(1, groupCount / 2);
                selected = groups.Take(groupCount).SelectMany(group => group).Distinct().OrderBy(value => value.At).ToArray();
            }
        }

        private JsonObject IdentityRow(int node)
        {
            var row = nodes[node]!.DeepClone().AsObject();
            if (projections.ContainsKey(node)) row["coverage"] = "source_slice_exceeds_method_character_bound";
            return row;
        }

        private JsonObject SelectExport()
        {
            var chosen = new Dictionary<int, JsonObject>();
            int exportBudget = 30000 - CatalogCoverageReserve;
            var rows = new Dictionary<(int Node, int Limit), JsonObject>();
            int EvidenceRank(int id)
            {
                if (invocations[id].NativeIdentityUnbound) return 6;
                if (!projections.TryGetValue(id, out var source)) return 5;
                bool spawn = source.Statements.Any(value => value.Operand is MethodInfo call &&
                    (call.DeclaringType == typeof(Terraria.Projectile) && call.Name is "NewProjectile" or "NewProjectileDirect"
                    || (call.DeclaringType == typeof(Terraria.NPC) || call.DeclaringType == typeof(Terraria.Player)) && call.Name == "AddBuff"));
                if (spawn) return 0;
                if (source.Statements.Any(HasMutableArguments)) return 1;
                if (principalNodes.Contains(id) && source.Statements.Any(value => WritesSourceStorage(value)
                    || value.Op == "ret" && value.Inputs.Count > 0)) return 2;
                if (principalNodes.Contains(id) || invocations[id].ProjectileType is not null || priorities[id] == 1) return 3;
                return 4;
            }
            var ranks = Enumerable.Range(0, nodes.Count).ToDictionary(id => id, EvidenceRank);
            var order = Enumerable.Range(0, nodes.Count).OrderBy(id => priorities[id])
                .ThenBy(id => ranks[id]).ThenBy(id => principalNodes.Contains(id) ? 0 : 1).ThenBy(id => id).ToArray();
            JsonObject Row(int id, int limit)
            {
                if (!rows.TryGetValue((id, limit), out var row)) rows[(id, limit)] = row = limit == 0 ? ExportCoreRow(id)
                    : limit == -1 ? ExportMechanicalRow(id, expanded: true) : ExportRow(id, limit);
                return row;
            }
            // Measurements live only for this selection. Source rows are frozen
            // once measured; accepted output is materialized only at the end.
            var measurements = new ExportMeasurements();
            bool Fits(int? requestedBudget = null)
            {
                int budget = requestedBudget ?? exportBudget;
                var plan = PlanExport(chosen, budget, measurements);
                return plan.Characters <= budget && plan.RetainsRootPaths(discoveryRoots);
            }
            bool RetainsCore(JsonObject before, JsonObject after)
            {
                if (before["values"] is not JsonObject prior) return true;
                if (after["values"] is not JsonObject next) return false;
                if (prior.Any(value => next[value.Key]?.ToJsonString() != value.Value?.ToJsonString())) return false;
                var statements = after["statements"]!.AsArray().Select(value => value!.GetValue<string>()).ToHashSet();
                if (!before["statements"]!.AsArray().All(value => statements.Contains(value!.GetValue<string>()))) return false;
                var blocks = after["blocks"]!.AsArray().OfType<JsonArray>().ToDictionary(block => block[0]!.GetValue<int>());
                foreach (var block in before["blocks"]!.AsArray().OfType<JsonArray>())
                {
                    if (!blocks.TryGetValue(block[0]!.GetValue<int>(), out var replacement)) return false;
                    if (block[2] is not null && block[2]!.ToJsonString() != replacement[2]?.ToJsonString()) return false;
                    var guards = replacement[3]!.AsArray().Select(value => value!.GetValue<string>()).ToHashSet();
                    if (!block[3]!.AsArray().All(value => guards.Contains(value!.GetValue<string>()))) return false;
                }
                return true;
            }
            bool FitsEssential()
            {
                if (Fits()) return true;
                // Expand only for an already selected causal/mechanical bundle,
                // never to fill space with optional utility or common hooks.
                int previous = exportBudget;
                while (exportBudget < CharacterLimit - CatalogCoverageReserve)
                {
                    exportBudget = Math.Min(CharacterLimit - CatalogCoverageReserve, exportBudget + 1000);
                    if (Fits()) return true;
                }
                exportBudget = previous;
                return false;
            }
            bool HasPath(int id) => discoveryRoots.Contains(id) || !discoveryParents.TryGetValue(id, out var parents)
                || parents.Any(chosen.ContainsKey);
            void Admit(int id, bool identityOnly)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (chosen.Count >= NodeLimit || chosen.ContainsKey(id) || !HasPath(id)) return;
                var row = identityOnly ? IdentityRow(id) : Row(id, 6500);
                if (!identityOnly && row["values"] is null && projections.ContainsKey(id)) row = Row(id, SourceGraphProjection.CharacterLimit);
                if (identityOnly && projections.ContainsKey(id)) row["coverage"] = "source_character_bound";
                chosen[id] = row;
                if (!Fits(identityOnly ? 15000 : exportBudget))
                {
                    if (!identityOnly)
                    {
                        var smaller = Row(id, 1800);
                        if (smaller["values"] is not null) { chosen[id] = smaller; if (Fits()) return; }
                    }
                    chosen.Remove(id);
                }
            }
            void AdmitGroup(IEnumerable<int> candidates, bool identityOnly)
            {
                int previous;
                do
                {
                    previous = chosen.Count;
                    foreach (int id in candidates) Admit(id, identityOnly);
                } while (chosen.Count != previous && chosen.Count < NodeLimit);
            }
            // Reserve only causal dispatch/effect paths, not the inventory of
            // pure utility calls. Bodies and their guards precede that inventory.
            var backbone = order.Where(id => priorities[id] == 0 && ranks[id] < 6
                && (principalNodes.Contains(id) || ranks[id] == 0 || invocations[id].ProjectileType is not null)).ToHashSet();
            var ancestors = new Stack<int>(backbone);
            while (ancestors.Count > 0)
            {
                int id = ancestors.Pop();
                if (discoveryRoots.Contains(id) || !discoveryParents.TryGetValue(id, out var parents)) continue;
                int parent = parents.OrderBy(value => priorities[value]).ThenBy(value => value).First();
                if (backbone.Add(parent)) ancestors.Push(parent);
            }
            AdmitGroup(order.Where(backbone.Contains), identityOnly: true);
            foreach (int id in order.Where(chosen.ContainsKey)
                .OrderBy(id => Row(id, 0)["sourceSelection"]?.GetValue<string>() == "mechanical_core" ? 0 : 1))
            {
                var prior = chosen[id]; var row = Row(id, 0);
                if (row["values"] is null) row = Row(id, 1800);
                if (row["values"] is null && ranks[id] <= 1) row = Row(id, 6500);
                if (row["values"] is null && ranks[id] <= 1) row = Row(id, SourceGraphProjection.CharacterLimit);
                if (row["values"] is null) continue;
                chosen[id] = row;
                bool essential = row["sourceSelection"]?.GetValue<string>() == "mechanical_core";
                if (!(essential ? FitsEssential() : Fits())) chosen[id] = prior;
            }
            AdmitGroup(order.Where(id => priorities[id] == 0 && ranks[id] <= 3), identityOnly: false);
            // Recover enclosing predicates before adding more optional helpers.
            // Every important body gets a first allocation before any expansion.
            foreach (int id in order.Where(chosen.ContainsKey)
                .OrderBy(id => Row(id, -1)["sourceSelection"]?.GetValue<string>() == "mechanical_core" ? 0 : 1)
                .ThenByDescending(id => chosen[id]["unresolvedEnclosingBranchCount"]?.GetValue<int>() ?? 0))
            {
                var prior = chosen[id]; var row = Row(id, -1);
                if (row["values"] is null || !RetainsCore(prior, row)) continue;
                chosen[id] = row;
                if (!Fits()) chosen[id] = prior;
            }
            AdmitGroup(order.Where(id => priorities[id] == 1 && ranks[id] < 6), identityOnly: false);
            AdmitGroup(order.Where(id => priorities[id] == 0 && ranks[id] > 3 && ranks[id] < 6), identityOnly: false);
            AdmitGroup(order.Where(id => priorities[id] >= 2 && ranks[id] < 6), identityOnly: false);
            // An unbound actor may still contribute small source evidence, but
            // its whole native dispatch body must not displace captured actors.
            int previousUnbound;
            do
            {
                previousUnbound = chosen.Count;
                foreach (int id in order.Where(id => ranks[id] == 6))
                {
                    if (chosen.Count >= NodeLimit || chosen.ContainsKey(id) || !HasPath(id)) continue;
                    var row = Row(id, 1800);
                    if (row["values"] is null) row["coverage"] = "unbound_actor_source_not_expanded";
                    chosen[id] = row;
                    if (!Fits()) chosen.Remove(id);
                }
            } while (previousUnbound != chosen.Count && chosen.Count < NodeLimit);
            return PlanExport(chosen, exportBudget, measurements).Materialize();
        }

        private JsonObject BuildExport(Dictionary<int, JsonObject> chosen, int characterBudget = CharacterLimit - CatalogCoverageReserve)
            => PlanExport(chosen, characterBudget, new ExportMeasurements()).Materialize();
    }
}
