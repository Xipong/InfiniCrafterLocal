using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Current independent composition with the original geometry observer's exact
    // 17px center offset and 12-tick quarter/full/quarter cycle. No archive input.
    private static string FrontHandWire()
    {
        var data = RootSpawnFixture(32, 1);
        data.Id = "current_front_hand"; data.SourceMode = "test_fixture";
        var body = data.RuntimeProgram.TryGetEntity("root")!;
        body.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
        body.VisualRole = body.Visual.Role = "held_body";
        body.Visual.AssetMode = "reuse_item_icon";
        body.Spawn.Aim = "cursor"; body.Spawn.SpeedPxPerTick = 0; body.Spawn.MaxActive = 1;
        body.Damage = new() { Enabled = true, Damage = 20, DamageClass = "generic", Knockback = 3 };
        body.LifetimeTicks = 120;
        body.Hitbox = new() { WidthPx = 24, HeightPx = 8, DrawScale = 1, HitboxScale = 1 };
        body.Collision = new() { TileCollide = false, Pierce = 1, NpcImmunityMode = "local", LocalNpcHitCooldownTicks = 10 };
        body.Aim = new() { Source = "initial", TurnOwner = false };
        body.Attachment = new() { Anchor = "front_hand", AxisOffsetPx = 17, NormalOffsetPx = 0 };
        body.ArmPose = new() { DurationTicks = 12, StartStretch = "quarter", PeakStretch = "full", EndStretch = "quarter", PeakProgress = .5 };
        body.Rotation = new() { Mode = "axis", OffsetRadians = 0 };
        body.OwnerControl = new() { RequireHeldItem = true, RequireChannel = false, RequireItemAnimation = false,
            ClaimHeldProjectile = true, Animation = "none", Lifetime = "authored" };
        data.RuntimeProgram.ItemUse.UseStyle = "rapier";
        data.RuntimeProgram.ItemUse.HideUseGraphic = true; data.RuntimeProgram.ItemUse.DisableMeleeHitbox = true;
        data.Gameplay.UseTime = data.Gameplay.UseAnimation = 60;
        data.Visual.SpritePath = "fixture_front_hand_root.png"; data.Visual.SpriteStatus = "generated";
        data.Visual.RenderSizePx = 32; data.Visual.ForwardAngleDegrees = 23;
        data.Visual.Grip = new() { NormalizedX = .15625, NormalizedY = .5 };
        data.VfxManifest = VfxManifestSpec.Empty();
        return data.ToNetworkJson();
    }
    private static GeneratedItemData FrontHandDefinition(string? json = null)
    {
        var data = GeneratedItemData.FromJson(json ?? FrontHandWire());
        if (data is null) throw new InvalidOperationException("RED: current hand composition rejected by native DTO: " + ContractJsonDiagnostics.LastError);
        return data;
    }
    private static JsonObject FrontHandEntity(JsonObject root)
        => root["runtimeProgram"]!["entities"]!.AsArray().Select(x => x!.AsObject())
            .Single(x => x["id"]!.GetValue<string>() == root["runtimeProgram"]!["primaryEntityId"]!.GetValue<string>());

    private static void FrontHandFreshWireAdmission()
    {
        string wire = FrontHandWire();
        var data = FrontHandDefinition(wire);
        var e = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
        Equal(false, e.Movement.IsConfigured, "independent hand does not retain bundled movement");
        Equal("initial", e.Aim!.Source, "explicit independent axis");
        Equal(12, e.ArmPose!.DurationTicks, "fixture cycle is 12 world ticks");
        Equal(17f, e.Attachment!.AxisOffsetPx, "physical center retains intended geometry");
        foreach (var field in new[] { ("aim", "source"), ("attachment", "axisOffsetPx"),
            ("armPose", "endStretch"), ("rotation", "mode") }) {
            var root = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(root)[field.Item1]!.AsObject().Remove(field.Item2);
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "required component leaf refuses absence " + field);
        }
        var zero = JsonNode.Parse(wire)!.AsObject();
        FrontHandEntity(zero)["attachment"]!["axisOffsetPx"] = 0;
        FrontHandDefinition(zero.ToJsonString());
        foreach (string mode in new[] { "no_asset", "runtime_geometry" }) {
            var invisible = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(invisible)["visual"]!["assetMode"] = mode;
            if (mode == "runtime_geometry")
                FrontHandEntity(invisible)["visual"]!["geometry"] = JsonSerializer.SerializeToNode(ExplicitBody());
            FrontHandDefinition(invisible.ToJsonString());
        }
        foreach (string leaf in new[] { "grip", "renderSizePx", "forwardAngleDegrees" }) {
            var missing = JsonNode.Parse(wire)!.AsObject(); missing["visual"]!.AsObject().Remove(leaf);
            Equal(true, GeneratedItemData.FromJson(missing.ToJsonString()) is null, "missing selected-root " + leaf + " fails closed");
        }
    }

    // Independent observer: the expected arm angle never comes from product helper.
    private static Vector2 FrontHandExpected(Player owner, Vector2 axis, Player.CompositeArmStretchAmount stretch)
        => owner.RotatedRelativePoint(owner.GetFrontHandPosition(stretch,
            axis.ToRotation() - owner.fullRotation - MathHelper.PiOver2), addGfxOffY: false);
    private static Vector2 FrontHandQueuedGrip(SpriteBatch batch, int index, ItemGripSpec grip)
    {
        var vertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!;
        object quad = vertices.GetValue(index)!;
        var pos = CpuVertexValues<Vector3>(quad); var uv = CpuVertexValues<Vector2>(quad);
        float u0 = uv.Min(v => v.X), u1 = uv.Max(v => v.X), v0 = uv.Min(v => v.Y), v1 = uv.Max(v => v.Y);
        Vector2 Corner(float u, float v)
        {
            int i = Array.FindIndex(uv, x => Math.Abs(x.X - u) < .001f && Math.Abs(x.Y - v) < .001f);
            Equal(true, i >= 0, "paired native FNA UV corner");
            return new(pos[i].X, pos[i].Y);
        }
        Vector2 origin = Corner(u0, v0);
        return origin + (Corner(u1, v0) - origin) * (float)grip.NormalizedX
            + (Corner(u0, v1) - origin) * (float)grip.NormalizedY;
    }
    private static void FrontHandNativePoseAndContact()
    {
        string wire = FrontHandWire(); // saved source remains untouched; current test envelope is explicit
        // A small pairwise roster, not a Cartesian coverage framework.
        var cases = new[] {
            (Facing: 1, Gravity: 1f, Angle: .35f, Full: 0f, Updates: 1, Cursor: false, After: false, Server: false, Distinct: false),
            (Facing: -1, Gravity: 1f, Angle: 2.65f, Full: .4f, Updates: 6, Cursor: true, After: true, Server: false, Distinct: true),
            (Facing: 1, Gravity: -1f, Angle: -.6f, Full: -.3f, Updates: 6, Cursor: false, After: true, Server: false, Distinct: false),
            (Facing: -1, Gravity: -1f, Angle: -2.7f, Full: .2f, Updates: 1, Cursor: true, After: false, Server: true, Distinct: false),
        };
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
            for (int i = 0; i < Terraria.Main.projectile.Length; i++)
                Terraria.Main.projectile[i] ??= new Projectile(); // native ActiveProjectiles requires initialized slots
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            try {
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(CpuTexture(1, 1));
                foreach (var c in cases) {
                    var root = JsonNode.Parse(wire)!.AsObject(); var er = FrontHandEntity(root);
                    er["aim"]!["source"] = c.Cursor ? "cursor" : "initial";
                    er["collision"]!["extraUpdates"] = c.Updates - 1;
                    // Explicit test-only visual variants; never modify archived art or definition.
                    string path = Path.Combine(Terraria.Program.SavePath, c.Distinct ? "fresh_hand_distinct.png" : "fresh_hand_root.png");
                    var vr = c.Distinct ? er["visual"]!.AsObject() : root["visual"]!.AsObject();
                    er["visual"]!["assetMode"] = c.Distinct ? "baked_sprite" : "reuse_item_icon";
                    vr["spritePath"] = path; vr["renderSizePx"] = c.Distinct ? 48 : 32;
                    vr["spriteStatus"] = "generated"; // declared synthetic ready texture below, not a pending producer
                    vr["forwardAngleDegrees"] = c.Distinct ? -37 : 23;
                    vr["grip"] = JsonNode.Parse(c.Distinct
                        ? "{\"normalizedX\":0.71875,\"normalizedY\":0.25}"
                        : "{\"normalizedX\":0.15625,\"normalizedY\":0.5}");
                    var selectedGrip = new ItemGripSpec {
                        NormalizedX = vr["grip"]!["normalizedX"]!.GetValue<double>(),
                        NormalizedY = vr["grip"]!["normalizedY"]!.GetValue<double>() };
                    float selectedSize = vr["renderSizePx"]!.GetValue<int>(), selectedAxis = vr["forwardAngleDegrees"]!.GetValue<int>();
                    var data = FrontHandDefinition(root.ToJsonString()); var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                    // Native collision width/height/scale/damage/lifetime stay the fresh compiler values.
                    data.VfxManifest = VfxManifestSpec.Empty(); // keep this focused observer's main-quad roster exact
                    var texture = CpuTexture(32, 32);
                    if (!cache.Textures.Contains(cache.Publish(path))) cache.Textures.Add(cache.Publish(path), Activator.CreateInstance(cache.Record, texture, 0f, 0L)!);
                    owner.active = true; owner.dead = false; owner.whoAmI = 0; owner.direction = c.Facing;
                    owner.position = new Vector2(300, 300); owner.gravDir = c.Gravity; owner.fullRotation = c.Full;
                    owner.fullRotationOrigin = new Vector2(10, 21); owner.gfxOffY = 5;
                    owner.itemAnimation = owner.itemAnimationMax = owner.itemTime = owner.itemTimeMax = 60;
                    var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
                    AttachItem(new GeneratedItem(), item, data); data.ApplyToItem(item);
                    owner.inventory[0] = item; owner.selectedItem = 0;
                    Terraria.Main.player[0] = owner; Terraria.Main.myPlayer = 1;
                    Terraria.Main.netMode = c.Server ? NetmodeID.Server : NetmodeID.SinglePlayer; Terraria.Main.dedServ = c.Server;
                    Vector2 initial = c.Angle.ToRotationVector2(), axis = initial;
                    var projectile = new Projectile { owner = 0, whoAmI = 7, active = true, damage = entity.Damage.Damage, Center = owner.MountedCenter };
                    var generated = Attach(projectile);
                    typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
                    Terraria.Main.projectile[7] = projectile;
                    generated.Configure(data, entity, 0, 8, initial);
                    string definition = JsonSerializer.Serialize(data);
                    for (int age = 1; age <= 14; age++) {
                        if (age == 6) { owner.position += new Vector2(17, -9); axis = (c.Angle + .22f).ToRotationVector2(); }
                        projectile.ai[0] = axis.X; projectile.ai[1] = axis.Y;
                        if (!c.Server && !c.After) owner.ItemCheck_ApplyUseStyle(0, item, new Rectangle(0, 0, 32, 32));
                        for (int update = 0; update < c.Updates; update++) generated.AI();
                        if (!c.Server && c.After) owner.ItemCheck_ApplyUseStyle(0, item, new Rectangle(0, 0, 32, 32));
                        if (age is not (1 or 6 or 12 or 14)) continue;
                        Vector2 expectedAxis = c.Cursor ? axis : initial;
                        var stretch = age == 6 ? Player.CompositeArmStretchAmount.Full : Player.CompositeArmStretchAmount.Quarter;
                        Vector2 hand = FrontHandExpected(owner, expectedAxis, stretch);
                        float offset = er["attachment"]!["axisOffsetPx"]!.GetValue<float>();
                        string label = $"front_hand facing={c.Facing} gravity={c.Gravity} updates={c.Updates} age={age} server={c.Server}";
                        Equal(true, projectile.active, label + "cycle does not own lifetime");
                        AssertVfxNear(hand + expectedAxis * offset, projectile.Center, label + "actual physics center C=H+axis*offset");
                        Equal(false, generated.ShouldUpdatePosition(), label + "no native second velocity integration");
                        Equal(Vector2.Zero, projectile.velocity, label + "position owner is not translational launch");
                        Equal(entity.Hitbox.WidthPx, projectile.width, label + "width unchanged"); Equal(entity.Hitbox.HeightPx, projectile.height, label + "height unchanged");
                        Equal(entity.Damage.Damage, projectile.damage, label + "live damage unchanged");
                        Equal(stretch, owner.compositeFrontArm.stretch, label + "real front arm follows same cycle");
                        AssertVfxNear(hand, owner.RotatedRelativePoint(owner.GetFrontHandPosition(owner.compositeFrontArm.stretch, owner.compositeFrontArm.rotation), addGfxOffY: false), label + "stored native arm sign");
                        Rectangle hitbox = projectile.Hitbox; generated.ModifyDamageHitbox(ref hitbox);
                        Equal(true, Vector2.Distance(hitbox.Center.ToVector2(), projectile.Center) <= 2f, label + "native damage rectangle follows C");
                        Equal<bool?>(null, generated.Colliding(projectile.Hitbox, hitbox), label + "retain native AABB, not hidden blade OBB");
                        if (!c.Server) {
                            Vector2 center = projectile.Center; float rotation = projectile.rotation, scale = projectile.scale;
                            int index = count(); Color light = Color.White; generated.PreDraw(ref light);
                            Equal(index + 1, count(), label + "real public PreDraw produces selected rigid quad");
                            AssertVfxNear(hand - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY), FrontHandQueuedGrip(batch, index, selectedGrip), label + "real FNA grip lands on H");
                            AssertVfxNear(expectedAxis, BodyForwardFromCpuQueue(batch, index, selectedAxis, label), label + "declared rigid forward axis");
                            float longest = positions(index).SelectMany(a => positions(index).Select(b => Vector3.Distance(a, b))).Max();
                            Equal(true, Math.Abs(longest - selectedSize * MathF.Sqrt(2) * scale) < .01f, label + "no stretching");
                            if (age == 6) {
                                int copy = count();
                                DrawCurrentBodyTrail(projectile, data, entity.Id);
                                Equal(copy + 1, count(), label + "one current sampled body-history quad");
                                AssertVfxNear(hand - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY),
                                    FrontHandQueuedGrip(batch, copy, selectedGrip), label + "body-history grip agrees with main PNG");
                            }
                            // Consecutive render, no AI; draw must not become a gameplay owner.
                            generated.PreDraw(ref light); Equal(center, projectile.Center, label + "draw never rewrites C");
                            Equal(rotation, projectile.rotation, label + "draw never re-aims"); Equal(scale, projectile.scale, label + "draw never rescales physics");
                        }
                        Console.WriteLine(label + " H=" + hand + " C=" + projectile.Center);
                    }
                    Equal(definition, JsonSerializer.Serialize(data), "no definition mutation");
                    owner.dead = true; generated.AI();
                    Equal(c.Server, projectile.active, "only gameplay authority retires on native control loss; server awaits owner state");
                    projectile.active = false;
                }
            } finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        }));
    }

    private static void FrontHandObserverCounterproofs()
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, _, _) => {
            using var actors = new NativeActorState();
            owner.position = new Vector2(300, 300); owner.direction = 1; owner.fullRotation = .3f;
            Vector2 axis = .6f.ToRotationVector2(), h = FrontHandExpected(owner, axis, Player.CompositeArmStretchAmount.Full);
            var grip = new ItemGripSpec { NormalizedX = .15625, NormalizedY = .5 };
            var texture = CpuTexture(32, 32); Vector2 c = h + axis * 17;
            // Renderer-only fake: actual FNA quad attached to H while physics stays body-center.
            var p = new Projectile { Center = owner.MountedCenter + axis * 40 };
            int i = count(); batch.Draw(texture, h - Terraria.Main.screenPosition, texture.Bounds, Color.White, axis.ToRotation(), new Vector2(5, 16), 1, SpriteEffects.None, 0);
            AssertVfxNear(h - Terraria.Main.screenPosition, FrontHandQueuedGrip(batch, i, grip), "renderer-only fake passes contact observer");
            Equal(true, Vector2.Distance(c, p.Center) > 1, "independent C observer rejects renderer-only fake");
            // Motion-only fake: native physics at C, real center-origin quad retains wrong grip.
            p.Center = c; i = count(); batch.Draw(texture, p.Center - Terraria.Main.screenPosition, texture.Bounds, Color.White, axis.ToRotation(), new Vector2(16), 1, SpriteEffects.None, 0);
            AssertVfxNear(c, p.Center, "motion-only fake passes physics observer");
            Equal(true, Vector2.Distance(h - Terraria.Main.screenPosition, FrontHandQueuedGrip(batch, i, grip)) > 1, "independent UV contact observer rejects motion-only fake");
        }));
    }
}
