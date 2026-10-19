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
    // Baseline-compilable: no reference to new members/types, no saved-item rewrite.
    // Parent supplies a FRESH compiler/delivery fixture, not fixture.saved.json.
    private static string FrontHandWire() => File.ReadAllText(
        Environment.GetEnvironmentVariable("ICL_FRONT_HAND_FIXTURE")
        ?? Path.Combine("tools", "fixtures", "front-hand-compiled.json"));
    private static GeneratedItemData FrontHandDefinition(string? json = null)
    {
        var data = GeneratedItemData.FromJson(json ?? FrontHandWire());
        if (data is null) throw new InvalidOperationException("RED: fresh explicit move_front_hand definition rejected by native DTO: " + ContractJsonDiagnostics.LastError);
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
        Equal(20, e.Movement.Code, "new opcode, never code19 remapping");
        Equal("move_front_hand", e.Movement.Name, "explicit low-level selection");
        Equal(12, e.Movement.Params.DurationTicks, "fixture cycle is 12 world ticks");
        foreach (string field in new[] { "aimMode", "startStretch", "peakStretch", "hitboxOffsetPx", "durationTicks" })
        {
            var root = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(root)["movement"]!["params"]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "absent required " + field + " fails closed");
        }
        foreach (var bad in new[] {
            ("aimMode", "\"INITIAL\""), ("startStretch", "\"half\""), ("peakStretch", "null"),
            ("hitboxOffsetPx", "192.00000000000000000001"), ("hitboxOffsetPx", "\"0\""),
            ("durationTicks", "241"), ("durationTicks", "1"), ("durationTicks", "12.5") })
        {
            var root = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(root)["movement"]!["params"]![bad.Item1] = JsonNode.Parse(bad.Item2);
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "invalid present " + bad + " fails closed");
        }
        var reversed = JsonNode.Parse(wire)!.AsObject();
        var p = FrontHandEntity(reversed)["movement"]!["params"]!;
        p["startStretch"] = "full"; p["peakStretch"] = "quarter";
        Equal(true, GeneratedItemData.FromJson(reversed.ToJsonString()) is null, "ordered native enum, not CLR ordinal");
        var zero = JsonNode.Parse(wire)!.AsObject();
        FrontHandEntity(zero)["movement"]!["params"]!["hitboxOffsetPx"] = 0;
        FrontHandDefinition(zero.ToJsonString()); // explicit zero is not absent
        foreach (string aim in new[] { "cursor", "facing", "velocity", "none" }) {
            var root = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(root)["spawn"]!["aim"] = aim;
            Equal(aim != "none", GeneratedItemData.FromJson(root.ToJsonString()) is not null,
                "front-hand native initial axis admission " + aim);
        }
        foreach (string violation in new[] { "disabled", "count", "singleton", "speed", "spread", "tile", "controller", "handPose", "primary", "binding" }) {
            var root = JsonNode.Parse(wire)!.AsObject(); var body = FrontHandEntity(root);
            switch (violation) {
                case "disabled": body["spawn"]!["enabled"] = false; break;
                case "count": body["spawn"]!["count"] = 2; break;
                case "singleton": body["spawn"]!["maxActive"] = 2; break;
                case "speed": body["spawn"]!["speedPxPerTick"] = 1; break;
                case "spread": body["spawn"]!["spreadRadians"] = .1; break;
                case "tile": body["collision"]!["tileCollide"] = true; break;
                case "controller": body["controller"] = JsonNode.Parse("{\"name\":\"charge_then_release\",\"code\":2,\"params\":{\"chargeTicks\":12,\"powerMultiplier\":1}}"); break;
                case "handPose": root["runtimeProgram"]!["itemUse"]!["handPose"] = "one_handed"; break;
                case "primary": root["runtimeProgram"]!["primaryEntityId"] = "item"; root["runtimeProgram"]!["primaryOwner"] = "item_body"; break;
                case "binding": root["runtimeProgram"]!["bindings"]![0]!["input"] = "hold"; break;
            }
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "native explicit hand support rejects " + violation);
        }
        foreach (string mode in new[] { "no_asset", "runtime_geometry" }) {
            var invisible = JsonNode.Parse(wire)!.AsObject();
            FrontHandEntity(invisible)["visual"]!["assetMode"] = mode;
            FrontHandDefinition(invisible.ToJsonString()); // do not force root PNG reuse
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
        string wire = FrontHandWire(); // authentic receipt-bearing source remains untouched
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
                    er["movement"]!["params"]!["aimMode"] = c.Cursor ? "cursor" : "initial";
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
                    if (!cache.Textures.Contains(path)) cache.Textures.Add(path, Activator.CreateInstance(cache.Record, texture, 0f, 0L)!);
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
                        float offset = er["movement"]!["params"]!["hitboxOffsetPx"]!.GetValue<float>();
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
                                // Existing live same-body copy consumer, not a copied draw formula.
                                var state = new InfiniVfxState(); for (int n = 0; n < 4; n++) state.Push(projectile.Center);
                                object?[] args = { texture, projectile, entity, SpritePresentation.Entity(data, entity), data.VfxManifest, state, Color.White, 1f };
                                int copy = count();
                                typeof(InfiniVfxRuntime).GetMethod("DrawSelectedSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, args);
                                Equal(copy + 1, count(), label + "one real live body copy");
                                AssertVfxNear(hand - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY),
                                    FrontHandQueuedGrip(batch, copy, selectedGrip), label + "body-copy grip agrees with main PNG");
                            }
                            // Consecutive render, no AI; draw must not become a gameplay owner.
                            generated.PreDraw(ref light); Equal(center, projectile.Center, label + "draw never rewrites C");
                            Equal(rotation, projectile.rotation, label + "draw never re-aims"); Equal(scale, projectile.scale, label + "draw never rescales physics");
                        }
                        Console.WriteLine(label + " H=" + hand + " C=" + projectile.Center);
                    }
                    Equal(definition, JsonSerializer.Serialize(data), "no definition mutation");
                    owner.dead = true; generated.AI(); Equal(false, projectile.active, "native control loss retires hand owner");
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
