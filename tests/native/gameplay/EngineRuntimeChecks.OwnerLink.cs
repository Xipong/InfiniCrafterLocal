using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Uses only pre-existing helpers/APIs so the same check compiles on the
    // pre-product snapshot. The admission assertion must be RED there.
    private static VfxSlotSpec OwnerLinkSlot(VfxSlotSpec template) => new() {
        Id = "explicit_connector", EntityId = "actor", Event = "on_spawn", RendererKind = "texturedPath",
        Anchor = "self", Alpha = 1, Blend = "alpha", Layer = "BeforeProjectiles", StartTick = 0,
        Path = new VfxTexturedPathSpec {
            Texture = template.Element!.Texture, Source = "ownerLink", HistoryTicks = 0, MinDistancePx = 0,
            MaxSegmentLengthPx = 4096, WidthPx = 8,
            WidthProfile = new VfxNumericProfileSpec { Start = 1, Middle = 1, End = 1, Curve = "linear" },
            OpacityProfile = new VfxNumericProfileSpec { Start = 1, Middle = 1, End = 1, Curve = "linear" },
            ColorProfile = new VfxColorProfileSpec { Start = Rgb(255,0,0), Middle = Rgb(0,255,0), End = Rgb(0,0,255), Curve = "linear" },
            ProfileDomain = "length", UvMode = "repeat", RepeatLengthPx = 24, ScrollPxPerTick = -2,
        }
    };
    private static GeneratedItemData OwnerLinkData(string anchor)
    {
        var data = ReviewProjectileData("on_spawn");
        data.VfxManifest.Slots = new[] { OwnerLinkSlot(data.VfxManifest.Slots[0]) };
        // Reflection keeps this check compilable against the pre-anchor product.
        typeof(VfxTexturedPathSpec).GetProperty("OwnerAnchor")?.SetValue(data.VfxManifest.Slots[0].Path, anchor);
        return data;
    }
    private static void OwnerLinkWireAdmission()
    {
        var source = OwnerLinkData("frontHand"); string wire = source.ToJson();
        var data = GeneratedItemData.FromJson(wire);
        Equal(true, data is not null, "explicit generic ownerLink DTO admission");
        Equal("ownerLink", data!.VfxManifest.Slots[0].Path!.Source, "exact ownerLink spelling retained");
        Equal("frontHand", JsonNode.Parse(data.ToJson())!["vfxManifest"]!["slots"]![0]!["path"]!["ownerAnchor"]!.GetValue<string>(), "explicit frontHand survives serialization");
        Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "stripped network definition retains connector");
        foreach (var mutation in new (string Field, JsonNode? Value)[] {
            ("source", JsonValue.Create("ownerlink")), ("source", null),
            ("ownerAnchor", null), ("ownerAnchor", JsonValue.Create("MountedCenter")),
            ("ownerAnchor", JsonValue.Create(" frontHand")), ("ownerAnchor", JsonValue.Create("front_hand")),
            ("ownerAnchor", JsonValue.Create("")), ("ownerAnchor", JsonValue.Create(true)), ("ownerAnchor", JsonValue.Create(0)),
            ("historyTicks", JsonValue.Create(2)), ("minDistancePx", JsonValue.Create(1)),
            ("profileDomain", JsonValue.Create("age")), ("widthPx", JsonValue.Create(97)),
            ("maxSegmentLengthPx", JsonValue.Create(4097))
        }) {
            var root = JsonNode.Parse(wire)!;
            root["vfxManifest"]!["slots"]![0]!["path"]![mutation.Field] = mutation.Value?.DeepClone();
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "ownerLink refuses " + mutation.Field + "=" + mutation.Value);
        }
        foreach (string field in new[] { "source", "historyTicks", "profileDomain", "ownerAnchor" }) {
            var root = JsonNode.Parse(wire)!; root["vfxManifest"]!["slots"]![0]!["path"]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "ownerLink refuses missing " + field);
        }
        foreach (var mutation in new[] { ("anchor", "owner"), ("event", "on_hit"), ("entityId", source.RuntimeProgram.ItemEntityId) }) {
            var root = JsonNode.Parse(wire)!; root["vfxManifest"]!["slots"]![0]![mutation.Item1] = mutation.Item2;
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "ownerLink refuses foreign " + mutation.Item1);
        }
        var mounted = JsonNode.Parse(wire)!;
        mounted["vfxManifest"]!["slots"]![0]!["path"]!["ownerAnchor"] = "mountedCenter";
        Equal(true, GeneratedItemData.FromJson(mounted.ToJsonString()) is not null, "mountedCenter explicit admission");
        foreach (string pathSource in new[] { "anchorHistory", "beam", "whip" }) {
            foreach (JsonNode? anchor in new JsonNode?[] { null, JsonValue.Create("mountedCenter"), JsonValue.Create("frontHand") }) {
                var foreign = JsonNode.Parse(wire)!; var path = foreign["vfxManifest"]!["slots"]![0]!["path"]!;
                path["source"] = pathSource; path["ownerAnchor"] = anchor?.DeepClone();
                if (pathSource == "anchorHistory") path["historyTicks"] = 12;
                Equal(true, GeneratedItemData.FromJson(foreign.ToJsonString()) is null, pathSource + " forbids present ownerAnchor including null");
            }
        }
        var history = JsonNode.Parse(wire)!;
        var historyPath = history["vfxManifest"]!["slots"]![0]!["path"]!.AsObject();
        historyPath["source"] = "anchorHistory"; historyPath["historyTicks"] = 12; historyPath.Remove("ownerAnchor");
        var oldBranch = GeneratedItemData.FromJson(history.ToJsonString())
            ?? throw new InvalidOperationException("unchanged history fixture refused: " + ContractJsonDiagnostics.LastError);
        Equal(false, JsonNode.Parse(oldBranch.ToJson())!["vfxManifest"]!["slots"]![0]!["path"]!.AsObject().ContainsKey("ownerAnchor"), "old path branch omits new optional property");
        var noSlots = JsonNode.Parse(wire)!; noSlots["vfxManifest"]!["slots"] = new JsonArray();
        // The connector was the only consumer of Shard_A. Empty design must
        // remove its now-unused request, not weaken declared/used asset checks.
        noSlots["vfxManifest"]!["assets"] = new JsonArray();
        var silent = GeneratedItemData.FromJson(noSlots.ToJsonString())
            ?? throw new InvalidOperationException("empty explicit VFX fixture refused: " + ContractJsonDiagnostics.LastError);
        Equal(0, silent.VfxManifest.Slots.Length, "no connector is fabricated");
    }
    private static IList OwnerLinkPaths() => (IList)typeof(InfiniDetachedVfxSystem)
        .GetField("MaterialPaths", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
    private static Vector2[] OwnerLinkGeometry(object path) => (Vector2[])path.GetType()
        .GetField("Geometry", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(path)!;
    private static Vector2 OwnerLinkExpectedHand(Player owner) => owner.RotatedRelativePoint(
        owner.GetFrontHandPosition(owner.compositeFrontArm.stretch, owner.compositeFrontArm.rotation), addGfxOffY: false);
    private static void OwnerLinkLocalSpawn(GeneratedProjectile generated) => typeof(GeneratedProjectile)
        .GetMethod("EmitAndSyncVfxEvent", BindingFlags.Instance | BindingFlags.NonPublic)!
        .Invoke(generated, new object[] { "on_spawn", generated.Projectile.Center });

    private static void OwnerLinkLiveClientGeometryAndRetirement()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = OwnerLinkData("frontHand"); peers.Register(data);
            // Registration through the real local lifecycle; motion/retirement
            // through the all-client hook, with NO further producer or Draw.
            foreach (var mode in new[] { (NetmodeID.SinglePlayer, 0), (NetmodeID.MultiplayerClient, 0), (NetmodeID.MultiplayerClient, 2) }) {
                peers.System.OnWorldUnload(); peers.Mode(mode.Item1, mode.Item2); MaterialClock(300);
                var owner = Terraria.Main.player[0]; owner.dead = false; owner.direction = -1; owner.gravDir = -1;
                owner.Center = new Vector2(340, 190); owner.fullRotation = .35f;
                owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.ThreeQuarters, .7f);
                var generated = peers.Host(data); var host = generated.Projectile;
                var beforeCenter = host.Center; var beforeVelocity = host.velocity; int beforeDamage = host.damage;
                OwnerLinkLocalSpawn(generated); OwnerLinkLocalSpawn(generated);
                Equal(1, OwnerLinkPaths().Count, "same-generation connector registration deduplicates on each client");
                MaterialClock(301); peers.System.PostUpdateEverything();
                var geometry = OwnerLinkGeometry(OwnerLinkPaths()[0]!);
                Equal(2, geometry.Length, "bounded real two-point connector capture");
                AssertVfxNear(OwnerLinkExpectedHand(owner), geometry[0], "real native current hand, not owner center/image grip");
                AssertVfxNear(host.Center, geometry[1], "live connector terminates at projectile center");
                Equal(beforeCenter, host.Center, "connector does not move projectile"); Equal(beforeVelocity, host.velocity, "connector does not steer projectile");
                Equal(beforeDamage, host.damage, "connector does not author damage");
                owner.Center += new Vector2(13, 25); owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, -.4f);
                host.Center += new Vector2(-23, 5);
                MaterialClock(302); peers.System.PostUpdateEverything();
                geometry = OwnerLinkGeometry(OwnerLinkPaths()[0]!);
                AssertVfxNear(OwnerLinkExpectedHand(owner), geometry[0], "all-client update follows changed native hand");
                AssertVfxNear(host.Center, geometry[1], "all-client update follows changed projectile");
                owner.dead = true; MaterialClock(303); peers.System.PostUpdateEverything();
                Equal(0, OwnerLinkPaths().Count, "dead owner retires connector without another producer or Draw");
                owner.dead = false; MaterialClock(304); peers.System.PostUpdateEverything();
                Equal(0, OwnerLinkPaths().Count, "retired connector does not resurrect on owner revival alone");
                owner.fullRotation = 0; owner.gravDir = 1;
            }
            // currentMace uses flail movement without claiming a composite arm.
            // Obsolete disabled-arm rotation/stretch must never become a hand.
            foreach (bool obsoletePose in new[] { false, true }) {
                peers.System.OnWorldUnload(); peers.Mode(NetmodeID.MultiplayerClient, 2); MaterialClock(350);
                var owner = Terraria.Main.player[0]; owner.active = true; owner.dead = false;
                owner.Center = new Vector2(300, 170); owner.gravDir = -1; owner.fullRotation = .45f;
                owner.SetCompositeArmFront(false, obsoletePose ? Player.CompositeArmStretchAmount.Full : Player.CompositeArmStretchAmount.None, obsoletePose ? 2.2f : 0f);
                var unavailable = peers.Host(data); OwnerLinkLocalSpawn(unavailable);
                MaterialClock(351); peers.System.PostUpdateEverything();
                Equal(0, OwnerLinkPaths().Count, "disabled front arm refuses hand even with obsolete pose=" + obsoletePose);
                var mounted = OwnerLinkData("mountedCenter"); peers.Register(mounted);
                var mountedHost = peers.Host(mounted); OwnerLinkLocalSpawn(mountedHost);
                MaterialClock(352); peers.System.PostUpdateEverything();
                Equal(1, OwnerLinkPaths().Count, "mountedCenter remains available without composite pose");
                AssertVfxNear(owner.MountedCenter, OwnerLinkGeometry(OwnerLinkPaths()[0]!)[0], "mountedCenter is native exact anchor, not hand/offset");
                owner.Center += new Vector2(11, -6); MaterialClock(353); peers.System.PostUpdateEverything();
                AssertVfxNear(owner.MountedCenter, OwnerLinkGeometry(OwnerLinkPaths()[0]!)[0], "mountedCenter follows current native position");
                owner.fullRotation = 0; owner.gravDir = 1;
            }
            peers.Register(data);
            foreach (string retirement in new[] { "disabled_arm", "inactive_owner", "owner_slot_reuse", "invalid_owner", "nonfinite_hand", "nonfinite_projectile", "inactive_projectile", "projectile_slot_reuse", "identity", "generation", "kill" }) {
                peers.System.OnWorldUnload(); peers.Mode(NetmodeID.MultiplayerClient, 2); MaterialClock(400);
                var owner = Terraria.Main.player[0]; owner.active = true; owner.dead = false; owner.Center = new Vector2(300, 160);
                owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, .8f);
                var generated = peers.Host(data); var host = generated.Projectile;
                OwnerLinkLocalSpawn(generated); MaterialClock(401); peers.System.PostUpdateEverything();
                Equal(1, OwnerLinkPaths().Count, retirement + " starts with real connector");
                if (retirement == "disabled_arm") owner.SetCompositeArmFront(false, Player.CompositeArmStretchAmount.Full, 2.3f);
                if (retirement == "inactive_owner") owner.active = false;
                if (retirement == "owner_slot_reuse") Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
                if (retirement == "invalid_owner") host.owner = -1;
                if (retirement == "nonfinite_hand") owner.position = new Vector2(float.NaN, 0);
                if (retirement == "nonfinite_projectile") host.Center = new Vector2(float.PositiveInfinity, 0);
                if (retirement == "inactive_projectile") host.active = false;
                if (retirement == "projectile_slot_reuse") Terraria.Main.projectile[host.whoAmI] = new Projectile { whoAmI = host.whoAmI, owner = host.owner, identity = host.identity, type = host.type, active = true };
                if (retirement == "identity") host.identity++;
                if (retirement == "generation") generated.Configure(data, data.RuntimeProgram.TryGetEntity("actor")!, 0, 0, Vector2.UnitX);
                if (retirement == "kill") generated.OnKill(0);
                MaterialClock(402); peers.System.PostUpdateEverything();
                Equal(0, OwnerLinkPaths().Count, retirement + " retires exact binding without Draw");
                if (retirement == "disabled_arm") {
                    owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, .8f);
                    MaterialClock(403); peers.System.PostUpdateEverything();
                    Equal(0, OwnerLinkPaths().Count, "frontHand does not coast or resurrect after composite pose returns");
                }
                Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, direction = 1 };
            }
            peers.System.OnWorldUnload(); peers.Mode(NetmodeID.Server, 255);
            OwnerLinkLocalSpawn(peers.Host(data)); MaterialClock(500); peers.System.PostUpdateEverything();
            Equal(0, OwnerLinkPaths().Count, "dedicated server never owns cosmetic connector");
            peers.Mode(NetmodeID.MultiplayerClient, 2); peers.System.OnWorldUnload();
            data.VfxManifest.Slots = Array.Empty<VfxSlotSpec>();
            OwnerLinkLocalSpawn(peers.Host(data)); MaterialClock(501); peers.System.PostUpdateEverything();
            Equal(0, OwnerLinkPaths().Count, "missing explicit slot remains deliberate absence");
        });
    }

    private static void OwnerLinkFnaMeshControls()
    {
        var path = OwnerLinkData("frontHand").VfxManifest.Slots[0].Path!;
        VertexPositionColorTexture[] Mesh(Vector2[] points, Func<bool>? spend = null) {
            object design = LibraryInvoke("CopyPath", path, 1f, "alpha", "", "BeforeProjectiles", "self", 512, 0)!;
            return (VertexPositionColorTexture[])LibraryInvoke("BuildMaterialPathMesh", points, Array.Empty<float>(), design, 4UL, spend ?? (() => true))!;
        }
        var points = new[] { new Vector2(10,20), new Vector2(110,20) };
        foreach (string anchor in new[] { "mountedCenter", "frontHand" }) {
            typeof(VfxTexturedPathSpec).GetProperty("OwnerAnchor")?.SetValue(path, anchor);
            Equal(0, Mesh(new[] { points[0], new Vector2(60,20), points[1] }).Length, anchor + " preserves public ownerLink two-point input cap");
        }
        var mesh = Mesh(points);
        Equal(12, mesh.Length, "real FNA vertices include length-profile midpoint without smoothing");
        AssertVfxNear(points[0], new Vector2((mesh[0].Position.X+mesh[1].Position.X)/2, (mesh[0].Position.Y+mesh[1].Position.Y)/2), "FNA start center");
        AssertVfxNear(points[1], new Vector2((mesh[^1].Position.X+mesh[^3].Position.X)/2, (mesh[^1].Position.Y+mesh[^3].Position.Y)/2), "FNA end center");
        Equal(Color.Red, mesh[0].Color, "authored start RGB"); Equal(Color.Lime, mesh[2].Color, "authored midpoint RGB"); Equal(Color.Blue, mesh[^1].Color, "authored end RGB");
        Equal(true, Math.Abs(mesh[^1].TextureCoordinate.X-mesh[0].TextureCoordinate.X-100f/24f)<.001f, "repeat UV uses actual length");
        Equal(0, Mesh(points, () => false).Length, "zero shared draw allowance emits no FNA mesh");
        int allowance = 1; Equal(6, Mesh(points, () => allowance-- > 0).Length, "one shared segment allowance emits one segment");
        path.MaxSegmentLengthPx = 64; Equal(0, Mesh(points).Length, "original over-limit segment is not bridged by midpoint insertion");
        path.MaxSegmentLengthPx = 100; Equal(12, Mesh(points).Length, "exact maximum segment remains legal");
        path.WidthPx = 0; Equal(0, Mesh(points).Length, "zero width stays silent"); path.WidthPx = 8;
        Equal(0, Mesh(new[] { points[0], points[0] }).Length, "coincident endpoints do not invent connector");
        Equal(0, Mesh(new[] { points[0], new Vector2(float.NaN, 0) }).Length, "nonfinite geometry emits no vertices");
        path.UvMode = "stretch"; path.RepeatLengthPx = 1; path.ScrollPxPerTick = 0;
        mesh = Mesh(points); Equal(0f, mesh[0].TextureCoordinate.X, "stretch starts at zero"); Equal(1f, mesh[^1].TextureCoordinate.X, "stretch ends at one");
    }
}
