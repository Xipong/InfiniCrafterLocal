#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceGraph
    {
        private readonly Dictionary<int, MethodBase> methodByNode = new();
        private readonly Dictionary<string, List<AmmoIl>> nativeInvocationSlices = new(StringComparer.Ordinal);
        private readonly Dictionary<string, ParentSourceMethod?> invocationBodies = new(StringComparer.Ordinal);
        private readonly HashSet<string> nativeIdentityUnavailable = new(StringComparer.Ordinal);
        private readonly Dictionary<string, JsonObject> nativeIdentityReceipts = new(StringComparer.Ordinal);
        private readonly Dictionary<(string Caller, MethodBase Callee, int At), bool> nativeCallBindings = new();

        private ParentSourceMethod? ReadInvocation(MethodBase method)
        {
            if (currentInvocation.ProjectileType is not int type) return Read(method);
            string key = InvocationKey(method, currentInvocation);
            if (invocationBodies.TryGetValue(key, out var cached)) return cached;
            ParentSourceMethod? readableSource = null;
            try
            {
                if (nativeInvocationSlices.TryGetValue(key, out var slice))
                {
                    var window = new ParentSourceMethod(method, slice, nativeNext[method]);
                    nativeIdentityReceipts[key] = new JsonObject { ["selection"] = "conditional_identity_windows; entry_and_omitted_flow_unresolved" };
                    return invocationBodies[key] = window;
                }
                ParentSourceMethod? raw = Read(method);
                if (raw is null) return invocationBodies[key] = null;
                readableSource = raw;
                var selection = new AttackIdentitySelection(raw, type, currentInvocation.AiStyle ?? 0);
                ParentSourceMethod discovery = selection.Selected.Count == 0 ? raw
                    : new ParentSourceMethod(method, selectedSuccessors: selection.Selected);
                int blocked = selection.Receipt["blockedIdentityReads"]?.AsArray().Count ?? 0;
                int omitted = selection.Receipt["blockedIdentityReadsOmitted"]?.GetValue<int>() ?? 0;
                nativeIdentityReceipts[key] = new JsonObject { ["selection"] = "certified_receiver_identity_cfg",
                    ["selectedEdgeCount"] = selection.Selected.Count, ["blockedIdentityReadCount"] = blocked,
                    ["blockedIdentityReadsOmitted"] = omitted };
                if (blocked + omitted > 0) Gap("native_identity_reads_blocked_after_effect");
                return invocationBodies[key] = discovery;
            }
            catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
            {
                string reason = error is NotSupportedException ? error.Message : error.GetType().Name;
                Gap("native_identity_source_unavailable:" + reason);
                nativeIdentityUnavailable.Add(key);
                nativeIdentityReceipts[key] = new JsonObject { ["selectionUnavailable"] = reason,
                    ["scope"] = "identity_proof_unavailable; raw_source_only; no_identity_based_child_admission" };
                // This proof is optional. Its refusal must not erase a readable
                // method, or relabel a proof-work bound as a source-scan failure.
                return invocationBodies[key] = readableSource;
            }
        }

        private bool NativeCallBindsIdentity(ParentSourceMethod body, ParentSourceMethod.Value call, MethodBase callee)
        {
            var key = (InvocationKey(body.Method, currentInvocation), callee, call.At);
            if (nativeCallBindings.TryGetValue(key, out bool cached)) return cached;
            bool bound = false;
            try
            {
                // A disconnected equality window cannot certify everything that
                // ran before its entry. Reuse the owner's complete-prefix proof.
                if (nativeInvocationSlices.ContainsKey(key.Item1))
                {
                    var prefix = ParentSourceMethod.ForCallPrefixes(body.Method, nativeCode[body.Method], new[] { callee });
                    bound = AttackCallBindsCapturedActor(prefix, prefix.Statements, callee);
                }
                else bound = AttackCallBindsCapturedActor(body, new[] { call }, callee);
            }
            catch (NotSupportedException) { }
            return nativeCallBindings[key] = bound;
        }
    }
}
