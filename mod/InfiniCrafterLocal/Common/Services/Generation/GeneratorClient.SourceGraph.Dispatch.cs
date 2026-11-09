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
        // Source bodies remain cached by MethodBase; invocation-dependent facts
        // must not be shared by two different captured concrete receivers.
        private readonly record struct SourceInvocation(Type? Receiver, Type? Origin, int? ProjectileType = null, int? AiStyle = null, bool NativeIdentityUnbound = false);
        private readonly Dictionary<int, SourceInvocation> invocations = new();
        private readonly Dictionary<string, HashSet<SourceInvocation>> methodInvocations = new(StringComparer.Ordinal);
        private SourceInvocation currentInvocation;
        private static SourceInvocation Captured(Type type) => new(type, type);
        private static string InvocationKey(MethodBase method, SourceInvocation invocation)
            => MethodKey(method) + (invocation == default ? "" : "|receiver=" + TypeKey(invocation.Receiver) + "|origin=" + TypeKey(invocation.Origin)
                + "|projectile=" + invocation.ProjectileType?.ToString(CultureInfo.InvariantCulture)
                + "|style=" + invocation.AiStyle?.ToString(CultureInfo.InvariantCulture) + "|unbound=" + invocation.NativeIdentityUnbound);
        private static string TypeKey(Type? type) => type is null ? "unknown" : type.Module.ModuleVersionId + ":" + type.FullName;

        private void AddInvocation(JsonObject row, int node)
        {
            SourceInvocation context = invocations[node];
            if (context.Receiver is not null) row["receiverType"] = Member(context.Receiver);
            if (context.Origin is not null && context.Origin != context.Receiver) row["originReceiverType"] = Member(context.Origin);
            if (context.ProjectileType is int type)
            {
                var identity = new JsonObject { ["projectileType"] = type, ["aiStyle"] = context.AiStyle,
                    ["scope"] = "captured_actor; see_selection_proof_or_window_boundary; live_conditions_are_not_evaluated" };
                string key = InvocationKey(methodByNode[node], context);
                if (nativeIdentityReceipts.TryGetValue(key, out var receipt))
                    foreach (var field in receipt) identity[field.Key] = field.Value?.DeepClone();
                row["nativeIdentity"] = identity;
            }
            else if (context.NativeIdentityUnbound)
                row["nativeIdentity"] = new JsonObject { ["scope"] = "unbound_actor; source_only; no_identity_specialization_or_child_admission" };
        }

        private static bool CallsCapturedThis(ParentSourceMethod body, ParentSourceMethod.Value call)
        {
            if (body.Method.IsStatic || call.Inputs.Count == 0 || call.Op is not ("call" or "callvirt")) return false;
            var seen = new HashSet<string>();
            bool IsThis(string id)
            {
                if (!seen.Add(id)) return false;
                var origins = body.Definitions(id).ToArray();
                return origins.Length > 0 && origins.All(value => value.Op == "ldarg" && value.Operand is int argument && argument == 0
                    || value.Op == "castclass" && value.Inputs.Count == 1 && IsThis(value.Inputs[0]));
            }
            return IsThis(call.Inputs[0]);
        }

        private static MethodInfo? CapturedVirtualTarget(MethodInfo declaration, Type receiver)
        {
            if (declaration.DeclaringType is not { } owner || !owner.IsAssignableFrom(receiver)) return null;
            if (owner.IsInterface)
            {
                InterfaceMapping map = receiver.GetInterfaceMap(owner);
                for (int index = 0; index < map.InterfaceMethods.Length; index++)
                    if (map.InterfaceMethods[index].Equals(declaration)) return map.TargetMethods[index];
                return null;
            }
            MethodInfo slot = declaration.GetBaseDefinition();
            for (Type? type = receiver; type is not null; type = type.BaseType)
                foreach (MethodInfo method in type.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                    if (method.IsVirtual && method.GetBaseDefinition().Equals(slot)) return method;
            return null;
        }

        private void FollowSourceCall(ParentSourceMethod body, ParentSourceMethod.Value value, MethodBase declared, int depth, int node)
        {
            bool boundThis = !declared.IsStatic && currentInvocation.Receiver is { } receiver
                && declared.DeclaringType?.IsAssignableFrom(receiver) == true && CallsCapturedThis(body, value);
            SourceInvocation context = new(boundThis ? currentInvocation.Receiver : null, currentInvocation.Origin,
                NativeIdentityUnbound: currentInvocation.NativeIdentityUnbound || nativeIdentityUnavailable.Contains(InvocationKey(body.Method, currentInvocation)));
            MethodBase target = declared;
            string kind = value.Op == "callvirt" ? "declared_virtual_helper_candidate" : "helper_source";
            string? refusal = null;
            if (value.Op == "callvirt" && declared is MethodInfo virtualMethod && virtualMethod.IsVirtual)
            {
                MethodInfo? resolved = boundThis ? CapturedVirtualTarget(virtualMethod, currentInvocation.Receiver!) : null;
                if (resolved is not null)
                {
                    target = resolved;
                    kind = "captured_receiver_virtual_helper_candidate";
                }
                else refusal = "virtual_receiver_not_bound; declared_body_only_candidate";
            }
            if (currentInvocation.ProjectileType is int capturedType)
            {
                if (!context.NativeIdentityUnbound && NativeCallBindsIdentity(body, value, declared))
                    context = context with { ProjectileType = capturedType, AiStyle = currentInvocation.AiStyle };
                else
                {
                    context = context with { NativeIdentityUnbound = true };
                    refusal = (refusal is null ? "" : refusal + "; ") + "native_actor_identity_not_proven_at_call";
                }
            }
            if (target.ContainsGenericParameters || target.GetMethodBody() is null)
            {
                Edge(node, null, kind, value.At,
                    new JsonArray(value.Inputs.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
                    refusal ?? "virtual_or_abstract_target_has_no_available_body");
                return;
            }
            if (nativeProjectileMethods.Contains(body.Method)) nativeProjectileMethods.Add(target);
            string key = InvocationKey(target, context);
            if (!callers.TryGetValue(key, out var contexts)) callers[key] = contexts = new();
            bool newContext = !contexts.Any(c => c.Body.Method == body.Method && c.Call.At == value.At && c.Invocation == currentInvocation);
            if (newContext) contexts.Add((body, value, currentInvocation));
            bool existing = admitted.TryGetValue(key, out int priorNode);
            int? destination = Add(target, depth + 1, invocation: context);
            if (newContext && existing && depth < DepthLimit)
                pending.Enqueue((target, priorNode, depth + 1, focuses[key]));
            Edge(node, destination, kind, value.At,
                new JsonArray(value.Inputs.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()), refusal);
        }
    }
}
