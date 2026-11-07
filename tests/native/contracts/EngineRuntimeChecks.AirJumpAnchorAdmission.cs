using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static VfxSlotSpec JumpNativeAnchorSlot(string renderer, string entityId, string anchor)
    {
        // Canonical current fixtures carry each native renderer's exact payload.
        var slot = renderer == "nativeEffect" ? NativeEffectSlot() : NativeCueSlot(renderer == "nativeLight");
        slot.EntityId = entityId;
        slot.Event = RuntimeEventKind.OnJump;
        slot.Anchor = anchor;
        return slot;
    }

    private static void AirJumpNativeRenderersShareAnchorAdmission()
    {
        var source = NativeUtilityItem("\"playerEffect\":{\"airJump\":{\"count\":1,\"launchSpeedPxPerTick\":8,\"holdDurationTicks\":3}}").Data;
        var sourceJson = JsonNode.Parse(source.ToNetworkJson())!;
        var options = new JsonSerializerOptions {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        };
        var failures = new List<string>();
        void Expect(bool expected, bool actual, string label)
        {
            if (expected != actual) failures.Add(label + $": expected {expected}, got {actual}");
        }
        foreach (string renderer in new[] { "nativeEffect", "nativeDust", "nativeLight" })
        foreach (string anchor in new[] { "self", "owner", "hitPoint", "velocity", "field", "tip", "tipHistory" })
        {
            bool allowed = anchor is not ("tip" or "tipHistory");
            string label = renderer + "/" + anchor;
            var slot = JumpNativeAnchorSlot(renderer, source.RuntimeProgram.ItemEntityId, anchor);
            var manifest = new VfxManifestSpec { Slots = new[] { slot },
                Budget = new VfxQualityBudgetSpec { MaxParticlesPerTick = 256, MaxParticlesTotal = 1000, MaxDrawCalls = 64 } };
            // Serialize raw DTOs without calling ToJson/ToNetworkJson on the
            // candidate: refusal by a writer is not evidence of reader admission.
            string rawManifest = JsonSerializer.Serialize(manifest, options);
            bool dtoAccepted = true;
            try { slot.NormalizeAndValidate(); }
            catch (InvalidDataException) { dtoAccepted = false; }
            Expect(allowed, dtoAccepted, label + " direct slot DTO");
            Expect(allowed, VfxManifestSpec.FromJson(rawManifest).HasSlots, label + " raw manifest reader");
            var rawItem = sourceJson.DeepClone();
            rawItem["vfxManifest"] = JsonNode.Parse(rawManifest);
            Expect(allowed, GeneratedItemData.FromJson(rawItem.ToJsonString()) is not null,
                label + " raw final-item native reader with real on_jump producer");

            if (!allowed)
            {
                // This is event-specific admission, not a global ban on native
                // renderers' real tip/tipHistory anchors for other events.
                var otherEvent = JsonNode.Parse(rawManifest)!;
                otherEvent["slots"]![0]!["event"] = RuntimeEventKind.OnUse;
                Expect(true, VfxManifestSpec.FromJson(otherEvent.ToJsonString()).HasSlots,
                    label + " non-jump anchor retained");
            }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
