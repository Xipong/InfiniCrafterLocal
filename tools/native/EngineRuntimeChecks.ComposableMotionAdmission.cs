using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable JSON-only tests, written before DTO/product changes.
    // Execution is reserved to the parent sole native compiler. Not run locally.
    private static IEnumerable<(string Name, Action Check)> ComposableMotionAdmissionChecks()
    {
        yield return ("composable motion every independent component strict admission", ComposableMotionEveryComponentAdmission);
        yield return ("composable motion phase ownership and cross-component dependencies", ComposableMotionOwnershipAdmission);
        yield return ("composable motion absence zero and old opcode identity", ComposableMotionSavedWireAdmission);
    }

    private static readonly Dictionary<string, string> MotionAdmissionExamples = new()
    {
        ["aim"] = "{\"source\":\"initial\",\"turnOwner\":false}",
        ["attachment"] = "{\"anchor\":\"owner_center\",\"axisOffsetPx\":0,\"normalOffsetPx\":0}",
        ["armPose"] = "{\"durationTicks\":12,\"startStretch\":\"full\",\"peakStretch\":\"quarter\",\"endStretch\":\"none\",\"peakProgress\":0.25}",
        ["reach"] = "{\"durationTicks\":12,\"startOffsetPx\":0,\"peakOffsetPx\":32,\"endOffsetPx\":-4,\"peakProgress\":0.75}",
        ["orbit"] = "{\"anchor\":\"owner_center\",\"radiusPx\":32,\"radiansPerUpdate\":-0.1,\"phaseRadians\":0,\"identityPhaseRadians\":0}",
        ["seek"] = "[{\"target\":\"cursor\",\"maxSpeed\":12,\"velocityLerpPerUpdate\":0,\"limitSpeedToDistance\":false}]",
        ["returnTrigger"] = "{\"afterTicks\":12,\"onOwnerRelease\":false,\"onTileCollision\":false,\"disableTileCollisionOnReturn\":false}",
        ["arrival"] = "{\"target\":\"owner_center\",\"radiusPx\":10,\"action\":\"kill\"}",
        ["proximity"] = "{\"searchRangeTiles\":20,\"triggerRadiusPx\":12,\"requireLineOfSight\":false,\"action\":\"expire_then_kill\"}",
        ["rotation"] = "{\"mode\":\"spin\",\"offsetRadians\":0,\"radiansPerUpdate\":0}",
        ["verticalAcceleration"] = "{\"accelerationYPerUpdate\":0}",
        ["velocityRetention"] = "{\"multiplierPerUpdate\":0}",
        ["oscillation"] = "{\"law\":\"angular_sine\",\"frequencyRadiansPerUpdate\":0,\"phaseRadians\":0,\"amplitude\":0}",
        ["opacity"] = "{\"alpha\":0}",
        ["visualScaleRate"] = "{\"deltaPerUpdate\":0,\"maxScale\":2}",
        ["ownerControl"] = "{\"requireHeldItem\":false,\"requireChannel\":false,\"requireItemAnimation\":false,\"claimHeldProjectile\":false,\"animation\":\"none\",\"lifetime\":\"authored\"}",
        ["charge"] = "{\"durationTicks\":12}",
        ["chargeRelease"] = "{\"damageMultiplier\":1,\"knockbackMultiplier\":0,\"speedMultiplier\":1,\"launchSpeed\":0,\"pauseLifetimeWhileCharging\":false}",
        ["contactGate"] = "{\"window\":{\"phase\":\"always\",\"clock\":\"active\",\"startDelayTicks\":0,\"durationTicks\":12},\"enabled\":false}",
        ["beamGeometry"] = "{\"lengthPx\":100,\"widthPx\":12,\"raycastTiles\":false}",
        ["beamRamp"] = "{\"warmupTicks\":0,\"initialWidthMultiplier\":1,\"initialDamageMultiplier\":1,\"damageStartProgress\":0}",
        ["manaSustain"] = "{\"cadence\":\"held_item_use_time\"}",
        ["lashGeometry"] = "{\"clock\":\"active\",\"durationTicks\":12,\"anchor\":\"owner_center\",\"reachPx\":80,\"segments\":3,\"sweepStartRadians\":-1,\"sweepEndRadians\":1,\"bendRatio\":0,\"useOwnerGravity\":false,\"useOwnerWhipRangeMultiplier\":false}"
    };

    private static JsonObject MotionAdmissionWire(string component)
    {
        var root = JsonNode.Parse(FrontHandWire())!.AsObject();
        root.Remove("runtimeContract");
        var program = root["runtimeProgram"]!;
        program["itemUse"]!["channel"] = true;
        var body = FrontHandEntity(root);
        body["movement"] = JsonNode.Parse("{\"name\":\"move_straight\",\"code\":0,\"params\":{}}");
        body["aim"] = JsonNode.Parse(MotionAdmissionExamples["aim"]);
        if (component == "reach") body["attachment"] = JsonNode.Parse(MotionAdmissionExamples["attachment"]);
        if (component == "chargeRelease") body["charge"] = JsonNode.Parse(MotionAdmissionExamples["charge"]);
        if (component == "beamRamp") body["beamGeometry"] = JsonNode.Parse(MotionAdmissionExamples["beamGeometry"]);
        if (component == "manaSustain") {
            body["ownerControl"] = JsonNode.Parse(MotionAdmissionExamples["ownerControl"]);
            body["ownerControl"]!["requireHeldItem"] = true;
            body["ownerControl"]!["requireChannel"] = true;
        }
        body[component] = JsonNode.Parse(MotionAdmissionExamples[component]);
        return root;
    }
    private static JsonObject MotionAdmissionObject(JsonObject root, string key)
        => key == "seek" ? FrontHandEntity(root)[key]![0]!.AsObject() : FrontHandEntity(root)[key]!.AsObject();
    private static void MotionAdmits(JsonObject root, string label)
        => Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is not null, label + ": " + ContractJsonDiagnostics.LastError);
    private static void MotionRefuses(JsonObject root, string label)
        => Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, label);

    private static void ComposableMotionEveryComponentAdmission()
    {
        foreach (string key in MotionAdmissionExamples.Keys) {
            var root = MotionAdmissionWire(key);
            MotionAdmits(root, key + " independent positive");
            foreach (string leaf in MotionAdmissionObject(root, key).Select(x => x.Key).ToArray()) {
                // Return AfterTicks is optional but is the only enabled trigger here.
                var missing = MotionAdmissionWire(key); MotionAdmissionObject(missing, key).Remove(leaf);
                MotionRefuses(missing, key + " missing " + leaf);
                var presentNull = MotionAdmissionWire(key); MotionAdmissionObject(presentNull, key)[leaf] = null;
                MotionRefuses(presentNull, key + " present null " + leaf);
            }
            var unknown = MotionAdmissionWire(key); MotionAdmissionObject(unknown, key)["unregistered"] = true;
            MotionRefuses(unknown, key + " unknown leaf");
            var nullComponent = MotionAdmissionWire(key); FrontHandEntity(nullComponent)[key] = null;
            MotionRefuses(nullComponent, key + " present null component");
            var wrongOwner = MotionAdmissionWire(key);
            var item = wrongOwner["runtimeProgram"]!["entities"]!.AsArray().Select(x => x!.AsObject()).Single(x => x["kind"]!.GetValue<string>() == "item_body");
            item[key] = FrontHandEntity(wrongOwner)[key]!.DeepClone();
            MotionRefuses(wrongOwner, key + " unsupported item owner");
        }
        foreach (var bad in new[] { ("attachment", "axisOffsetPx", "4096.000000000000000001"),
            ("velocityRetention", "multiplierPerUpdate", "1.200000000000000001"),
            ("armPose", "peakProgress", "0"), ("reach", "peakProgress", "1"),
            ("opacity", "alpha", "0.5"), ("seek", "maxSpeed", "\"12\"") }) {
            var root = MotionAdmissionWire(bad.Item1); MotionAdmissionObject(root, bad.Item1)[bad.Item2] = JsonNode.Parse(bad.Item3);
            MotionRefuses(root, "strict raw bound/type " + bad);
        }
    }

    private static JsonObject MotionWindow(string phase, int delay = 0)
        => JsonNode.Parse("{\"phase\":\"" + phase + "\",\"clock\":\"active\",\"startDelayTicks\":" + delay + ",\"durationTicks\":12}")!.AsObject();
    private static void ComposableMotionOwnershipAdmission()
    {
        var root = MotionAdmissionWire("attachment");
        FrontHandEntity(root).Remove("movement");
        MotionAdmits(root, "new position owner satisfies driver requirement without old movement");
        FrontHandEntity(root)["orbit"] = JsonNode.Parse(MotionAdmissionExamples["orbit"]);
        MotionRefuses(root, "two overlapping absolute owners");
        FrontHandEntity(root)["attachment"]!["window"] = MotionWindow("always", 0);
        FrontHandEntity(root)["orbit"]!["window"] = MotionWindow("always", 12);
        MotionAdmits(root, "same-clock adjacent finite windows prove disjoint");
        root = MotionAdmissionWire("seek"); var seeks = FrontHandEntity(root)["seek"]!.AsArray();
        seeks[0]!["window"] = MotionWindow("outbound"); seeks.Add(seeks[0]!.DeepClone());
        MotionRefuses(root, "overlapping seek instances");
        FrontHandEntity(root)["returnTrigger"] = JsonNode.Parse(MotionAdmissionExamples["returnTrigger"]);
        seeks[1]!["window"]!["phase"] = "returning";
        MotionAdmits(root, "independent outbound and returning seek");
        seeks[0]!["window"] = JsonNode.Parse("{\"phase\":\"outbound\"}");
        seeks[1]!["window"] = JsonNode.Parse("{\"phase\":\"returning\"}");
        MotionAdmits(root, "whole-phase outbound/returning seek has no arbitrary finite placeholder");
        root = MotionAdmissionWire("reach"); FrontHandEntity(root).Remove("attachment"); MotionRefuses(root, "reach requires attachment");
        root = MotionAdmissionWire("chargeRelease"); FrontHandEntity(root).Remove("charge"); MotionRefuses(root, "release requires charge");
        root = MotionAdmissionWire("beamRamp"); FrontHandEntity(root).Remove("beamGeometry"); MotionRefuses(root, "ramp requires beam geometry");
        root = MotionAdmissionWire("armPose"); root["runtimeProgram"]!["itemUse"]!["handPose"] = "one_handed"; MotionRefuses(root, "arm pose has sole native arm owner");
        root = MotionAdmissionWire("attachment"); FrontHandEntity(root)["attachment"]!["anchor"] = "front_hand";
        FrontHandEntity(root)["spawn"]!["count"] = 2; FrontHandEntity(root)["spawn"]!["maxActive"] = 2;
        MotionAdmits(root, "multiple hand readers do not claim a native pose writer");
        foreach (string key in new[] { "charge", "returnTrigger" }) {
            root = MotionAdmissionWire(key); root["runtimeProgram"]!["itemUse"]!["channel"] = false;
            if (key == "returnTrigger") { FrontHandEntity(root)[key]!["onOwnerRelease"] = true; }
            MotionRefuses(root, key + " explicit release input requires channel");
        }
        root = MotionAdmissionWire("returnTrigger"); root["runtimeProgram"]!["itemUse"]!["channel"] = false;
        MotionAdmits(root, "time-only return does not force channel");
        root = MotionAdmissionWire("seek"); MotionAdmissionObject(root, "seek")["target"] = "nearest_npc";
        MotionRefuses(root, "nearest NPC requires both explicit target fields");
        MotionAdmissionObject(root, "seek")["searchRangeTiles"] = 20;
        MotionAdmissionObject(root, "seek")["requireLineOfSight"] = false;
        MotionAdmits(root, "nearest NPC explicit range and LOS");
        MotionAdmissionObject(root, "seek")["cursorLeashPx"] = 32;
        MotionRefuses(root, "NPC target cannot carry cursor-only leash");
        root = MotionAdmissionWire("rotation"); MotionAdmissionObject(root, "rotation")["mode"] = "axis";
        MotionAdmissionObject(root, "rotation").Remove("radiansPerUpdate");
        MotionAdmits(root, "axis rotation permits absent spin-only rate");
        foreach (string key in new[] { "attachment", "opacity", "seek" }) {
            root = MotionAdmissionWire(key); MotionAdmissionObject(root, key)["window"] = MotionWindow("always");
            MotionAdmits(root, key + " explicit finite window");
            var phaseOnly = root.DeepClone().AsObject();
            MotionAdmissionObject(phaseOnly, key)["window"] = JsonNode.Parse("{\"phase\":\"always\"}");
            MotionAdmits(phaseOnly, key + " phase-only window has no invented maximum duration");
            var phaseData = GeneratedItemData.FromJson(phaseOnly.ToJsonString())!;
            var phaseReadback = JsonNode.Parse(phaseData.ToJson())!.AsObject();
            var phaseWindow = MotionAdmissionObject(phaseReadback, key)["window"]!.AsObject();
            Equal(1, phaseWindow.Count, "phase-only window preserves exactly one serialized leaf");
            foreach (string timing in new[] { "clock", "startDelayTicks", "durationTicks" }) {
                var partial = phaseOnly.DeepClone().AsObject();
                MotionAdmissionObject(partial, key)["window"]![timing] = MotionAdmissionObject(root, key)["window"]![timing]!.DeepClone();
                MotionRefuses(partial, key + " lone timing leaf requires complete timing group " + timing);
                MotionAdmissionObject(partial, key)["window"]![timing] = null;
                MotionRefuses(partial, key + " present null timing leaf " + timing);
            }
            foreach (string leaf in new[] { "phase", "clock", "startDelayTicks", "durationTicks" }) {
                var missing = root.DeepClone().AsObject();
                MotionAdmissionObject(missing, key)["window"]!.AsObject().Remove(leaf);
                MotionRefuses(missing, key + " incomplete window " + leaf);
            }
            MotionAdmissionObject(root, key)["window"] = null;
            MotionRefuses(root, key + " present null window");
        }
        root = MotionAdmissionWire("attachment"); FrontHandEntity(root)["attachment"]!["anchor"] = "front_hand";
        root["visual"]!.AsObject().Remove("grip");
        MotionRefuses(root, "new front-hand selected PNG requires its actual owner's grip");
        FrontHandEntity(root)["visual"]!["assetMode"] = "no_asset";
        MotionAdmits(root, "new hand reader without PNG does not acquire a texture dependency");
        root = MotionAdmissionWire("velocityRetention");
        MotionAdmissionObject(root, "velocityRetention")["multiplierPerUpdate"] = JsonNode.Parse("1.2");
        MotionAdmits(root, "decimal upper endpoint survives Single narrowing");
        var accepted = GeneratedItemData.FromJson(root.ToJsonString())!;
        Equal(true, GeneratedItemData.FromJson(accepted.ToJson()) is not null, "retention endpoint read-write-read");
    }

    private static void ComposableMotionSavedWireAdmission()
    {
        var original = JsonNode.Parse(FrontHandWire())!.AsObject(); original.Remove("runtimeContract");
        var data = GeneratedItemData.FromJson(original.ToJsonString());
        Equal(true, data is not null, "unchanged old opcode definition still admits");
        Equal(20, data!.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!.Movement.Code, "old opcode remains 20");
        string saved = data.ToJson();
        var savedBody = FrontHandEntity(JsonNode.Parse(saved)!.AsObject());
        foreach (string key in MotionAdmissionExamples.Keys) Equal(false, savedBody.ContainsKey(key), "absent new component remains absent " + key);
        var zero = MotionAdmissionWire("velocityRetention");
        MotionAdmits(zero, "new explicit retention zero is accepted, not old drift fallback");
        var accepted = GeneratedItemData.FromJson(zero.ToJsonString())!;
        var readback = JsonNode.Parse(accepted.ToJson())!.AsObject();
        Equal(0f, FrontHandEntity(readback)["velocityRetention"]!["multiplierPerUpdate"]!.GetValue<float>(), "explicit zero roundtrip");
    }
}
