#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasMotionWireAdmission()
 {
        var options = new System.Text.Json.JsonSerializerOptions { PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase };
        foreach (var row in new[] {
            (21, "move_spring_tether", "{\"springRestRadius\":2,\"springStiffness\":0.1,\"springDamping\":0,\"springMaxSpeed\":8}"),
            (22, "move_elliptic_orbit", "{\"ellipseRadiusAlong\":4,\"ellipseRadiusAcross\":2,\"ellipseAngularRate\":-0.02,\"ellipsePhase\":0}"),
            (23, "move_traveling_wave", "{\"waveForwardSpeed\":6,\"waveDisplacementAmplitude\":2,\"wavePhaseRate\":0.04,\"waveStartPhase\":0.3}") })
        {
            var p = System.Text.Json.Nodes.JsonNode.Parse(row.Item3)!.AsObject();
            var admitted = System.Text.Json.JsonSerializer.Deserialize<RuntimeParamsSpec>(p.ToJsonString(), options)!;
            new RuntimeMovementSpec { Code=row.Item1, Name=row.Item2, Params=admitted }.NormalizeAndValidate("free_projectile");
            foreach (string field in p.Select(kv=>kv.Key).ToArray())
            foreach (string mutation in new[] { "missing", "null", "string", "out_of_range" })
            {
                var bad=p.DeepClone().AsObject();
                if(mutation=="missing") bad.Remove(field);
                else bad[field]=System.Text.Json.Nodes.JsonNode.Parse(mutation=="null" ? "null" : mutation=="string" ? "\"1\"" : "1000000");
                bool rejected=false;
                try {
                    var invalid=System.Text.Json.JsonSerializer.Deserialize<RuntimeParamsSpec>(bad.ToJsonString(),options)!;
                    new RuntimeMovementSpec {Code=row.Item1,Name=row.Item2,Params=invalid}.NormalizeAndValidate("free_projectile");
                } catch(Exception e) when(e is System.IO.InvalidDataException or System.Text.Json.JsonException) { rejected=true; }
                Equal(true,rejected,row.Item2+" rejects "+mutation+" "+field);
            }
            bool nullRejected=false;
            try { new RuntimeMovementSpec {Code=row.Item1,Name=row.Item2,Params=null!}.NormalizeAndValidate("free_projectile"); }
            catch(System.IO.InvalidDataException) { nullRejected=true; }
            Equal(true,nullRejected,"null movement params cannot bypass required fields");
        }
        foreach(string json in new[] {"{}","{\"accelerationX\":0,\"accelerationY\":null,\"startDelayTicks\":0,\"durationTicks\":1}","{\"accelerationX\":2.0000000000000000001,\"accelerationY\":0,\"startDelayTicks\":0,\"durationTicks\":1}"})
        {
            bool rejected=false;
            try { System.Text.Json.JsonSerializer.Deserialize<RuntimeVectorAccelerationSpec>(json,options)!.Validate(); }
            catch(Exception e) when(e is System.IO.InvalidDataException or System.Text.Json.JsonException) { rejected=true; }
            Equal(true,rejected,"vector acceleration raw JSON admission");
        }
 }
}
