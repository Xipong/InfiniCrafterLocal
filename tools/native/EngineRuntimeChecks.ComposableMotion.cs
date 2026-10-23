using System;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable consumer tracer: no reference to new product symbols.
    private static void ComposableMotionHandAttachmentAdmission()
    {
        var root = JsonNode.Parse(FrontHandWire())!.AsObject();
        var body = FrontHandEntity(root);
        body.Remove("movement");
        body["aim"] = JsonNode.Parse("{\"source\":\"initial\",\"turnOwner\":false}");
        body["attachment"] = JsonNode.Parse("{\"anchor\":\"front_hand\",\"axisOffsetPx\":0,\"normalOffsetPx\":0}");
        body["armPose"] = JsonNode.Parse("{\"durationTicks\":12,\"startStretch\":\"quarter\",\"peakStretch\":\"quarter\",\"endStretch\":\"quarter\",\"peakProgress\":0.5}");
        body["reach"] = JsonNode.Parse("{\"durationTicks\":12,\"startOffsetPx\":0,\"peakOffsetPx\":32,\"endOffsetPx\":0,\"peakProgress\":0.25}");
        // Compiler provenance is tested through real Python delivery separately;
        // this observer targets native executable admission, not authored receipts.
        root.Remove("runtimeContract");
        var data = GeneratedItemData.FromJson(root.ToJsonString());
        Equal(true, data is not null,
            "independent constant native arm pose + hand attachment + asymmetric physical reach must admit: "
            + ContractJsonDiagnostics.LastError);
    }
}
