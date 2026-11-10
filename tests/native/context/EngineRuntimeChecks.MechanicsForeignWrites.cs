using System;
using System.Linq;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void MechanicsSourceExcludesOnlyUnreachableIdentityWrites()
    {
        MechanicsSourceFixture.Executions = 0;
        foreach (string method in new[] { nameof(MechanicsSourceFixture.ConditionalForeignMutation), nameof(MechanicsSourceFixture.ConditionalForeignIncrement) })
        {
            var selected = MechanicsFixtureRecord(method);
            Equal(true, selected["identityPruning"]!["allowed"]!.GetValue<bool>(), "whole-method known-false identity write must not disable selection: " + method);
            string code = selected["code"]!.GetValue<string>();
            Equal(true, code.Contains("976") && !code.Contains("975"), "useful selected effect remains and foreign effect disappears: " + method);
            var reachable = MechanicsFixtureRecord(method, capturedType: 178);
            Equal(false, reachable["identityPruning"]!["allowed"]!.GetValue<bool>(), "reachable identity write still vetoes whole-method selection: " + method);
            Equal(0, reachable["excludedCallOffsets"]!.AsArray().Count, "reachable mutation excludes no calls");
        }
        foreach (string method in new[] { nameof(MechanicsSourceFixture.ConditionalUnknownMutation), nameof(MechanicsSourceFixture.ConditionalUnknownIncrement), nameof(MechanicsSourceFixture.ConditionalRegionPriorMutation), nameof(MechanicsSourceFixture.AddressExposure) })
        {
            var refused = MechanicsFixtureRecord(method);
            Equal(false, refused["identityPruning"]!["allowed"]!.GetValue<bool>(), "unknown/reachable/address mutation remains refused: " + method);
            Equal(0, refused["excludedCallOffsets"]!.AsArray().Count, "uncertain mutation excludes no calls");
        }
        var opaque = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OpaqueIdentitySuffix));
        string opaqueCode = opaque["code"]!.GetValue<string>();
        Equal(true, opaqueCode.Contains("Touch() && type == 178") && opaqueCode.Contains("Touch() || type == 177"), "unknown prefixes and original short-circuit conditions remain evaluated");
        Equal(false, opaqueCode.Contains("601") || opaqueCode.Contains("602"), "only impossible arms lose their spawns");
        Equal(true, opaqueCode.Contains("977"), "selected useful effect remains under its original condition");
        Equal(2, opaque["excludedCallOffsets"]!.AsArray().Count, "only two discarded spawn calls receive exclusion anchors");
        var unknown = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.OpaqueIdentitySuffix), capturedType: 178);
        Equal(0, unknown["excludedCallOffsets"]!.AsArray().Count, "unknown branch results retain both possible spawns");
        var projectile = new Projectile(); projectile.SetDefaults(ProjectileID.FlowerPow);
        var source = (JsonObject)CSharpOwner.GetMethod("CaptureProjectileMechanicsSource", CSharpFlags)!.Invoke(null, new object[] { projectile })!;
        var flail = source["records"]!.AsArray().OfType<JsonObject>().Single(row => row["method"]!.GetValue<string>() == "Terraria.Projectile.AI_015_Flails");
        Equal(true, flail["identityPruning"]!["allowed"]!.GetValue<bool>(), "real Flower Pow ignores mutation in another captured identity arm");
        string native = flail["code"]!.GetValue<string>();
        Equal(false, native.Contains("928"), "Drippler child does not survive Flower Pow readable source");
        Equal(true, native.Contains("248") && native.Contains("NewProjectile"), "Flower Pow petal spawn remains");
        Equal(true, flail["excludedCallOffsets"]!.AsArray().Count > 0, "removed child calls have exact IL anchors for consumer exclusion");
        Equal(true, flail["approximation"]!.GetValue<string>().Contains("assumed stable across opaque calls"), "bounded approximation remains explicit");
        Equal(0, MechanicsSourceFixture.Executions, "source inspection never executes native or fixture helpers");
    }
}
