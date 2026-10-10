using System;
using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags BeamPrivate = BindingFlags.Instance | BindingFlags.NonPublic;
    private static GeneratedItemData BeamFixture(bool extensions = true)
    {
        var data = RootSpawnFixture(32, 1);
        data.Id = "beam_contract_fixture";
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
        entity.Visual.Role = entity.VisualRole = RuntimeEntityKind.VisualRoleFor(entity.Kind);
        entity.Visual.AssetMode = "runtime_geometry";
        entity.Damage.Enabled = true; entity.Damage.Damage = 100; entity.Damage.DamageClass = "magic";
        entity.Collision.TileCollide = false; entity.LifetimeTicks = 120;
        entity.Controller = new RuntimeControllerSpec { Name = "channel_beam", Code = RuntimeControllerCode.ChannelBeam,
            Params = new RuntimeParamsSpec { RangeTiles = 20, WidthPx = 100, WarmupTicks = 100 } };
        if (extensions) {
            var p = entity.Controller.Params;
            p.ManaPayment = "each_use_time"; p.InitialDamageMultiplier = 0.35;
            p.InitialWidthMultiplier = 0.22; p.DamageStartProgress = 0.08; p.RaycastTiles = false;
        }
        data.RuntimeProgram.ItemUse.Channel = true;
        data.RuntimeProgram.Bindings = new[] { data.RuntimeProgram.Bindings[0] };
        data.Gameplay.ManaCost = 10; data.Gameplay.UseTime = data.Gameplay.UseAnimation = 4;
        data.Normalize();
        return data;
    }

    private static GeneratedProjectile BeamHost(GeneratedItemData data, int damage = 100, int slot = 0)
    {
        Player owner = Terraria.Main.player[0];
        var item = new Item(); data.ApplyToItem(item);
        var held = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(held, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, held);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(held, data);
        owner.inventory[0] = item; owner.selectedItem = 0; owner.channel = true;
        owner.active = true; owner.dead = owner.noItems = false;
        owner.frozen = owner.webbed = owner.stoned = false;
        var projectile = Terraria.Main.projectile[slot] = new Projectile { whoAmI = slot, owner = 0,
            identity = 123 + slot, active = true, velocity = Vector2.UnitX, damage = damage };
        var generated = Attach(projectile);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        generated.Configure(data, data.RuntimeProgram.TryGetEntity("root")!, 0, 32, Vector2.UnitX);
        return generated; // Isolated actual host; no native world registration claimed.
    }

    private static void BeamApply(GeneratedProjectile generated)
        => typeof(GeneratedProjectile).GetMethod("ApplyChannelBeam", BeamPrivate)!.Invoke(generated, null);
    private static void BeamAge(GeneratedProjectile generated, int updates)
        => typeof(GeneratedProjectile).GetField("_age", BeamPrivate)!.SetValue(generated, updates);
    private static (Vector2 Start, Vector2 End, float Width) BeamGeometry(GeneratedProjectile generated)
    {
        object[] args = { Vector2.Zero, Vector2.Zero, 0f };
        typeof(GeneratedProjectile).GetMethod("GetChannelBeamGeometry", BeamPrivate)!.Invoke(generated, args);
        return ((Vector2)args[0], (Vector2)args[1], (float)args[2]);
    }
    private static void BeamNear(float expected, float actual, string label)
        => Equal(true, Math.Abs(expected - actual) < 0.002f, label + " expected=" + expected + " actual=" + actual);

    private static void BeamStrictDtoAndRetainedAbsence()
    {
        var data = BeamFixture();
        foreach (string json in new[] { data.ToJson(), data.ToNetworkJson() }) {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("beam DTO rejected explicit fixture");
            var p = copy.RuntimeProgram.TryGetEntity("root")!.Controller.Params;
            Equal("each_use_time", p.ManaPayment ?? "", "native sustain selector round-trips");
            Equal(0.35, p.InitialDamageMultiplier ?? -1, "damage fraction retains raw double");
            Equal(0.22, p.InitialWidthMultiplier ?? -1, "width fraction retains raw double");
            Equal(0.08, p.DamageStartProgress ?? -1, "threshold retains raw double");
            Equal(false, p.RaycastTiles ?? true, "explicit false survives");
        }
        data = BeamFixture(false);
        var raw = JsonNode.Parse(data.ToJson())!.AsObject();
        string[] names = { "manaPayment", "initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress", "raycastTiles" };
        var legacy = GeneratedItemData.FromJson(raw.ToJsonString())!;
        foreach (string json in new[] { legacy.ToJson(), legacy.ToNetworkJson() })
            foreach (string name in names) Equal(false, json.Contains("\"" + name + "\"", StringComparison.Ordinal), "retained wire absence " + name);
        foreach (var pair in new[] {
            ("manaPayment", "null"), ("manaPayment", "\"Each_use_time\""), ("manaPayment", "true"),
            ("initialDamageMultiplier", "null"), ("initialDamageMultiplier", "0"), ("initialDamageMultiplier", "1.001"),
            ("initialDamageMultiplier", "0.9999999999"), ("initialWidthMultiplier", "false"),
            ("initialWidthMultiplier", "0.9999999999"), ("damageStartProgress", "-0.01"),
            ("damageStartProgress", "1.1"), ("raycastTiles", "null"), ("raycastTiles", "1") }) {
            var invalid = raw.DeepClone();
            invalid["runtimeProgram"]!["entities"]![1]!["controller"]!["params"]![pair.Item1] = JsonNode.Parse(pair.Item2);
            Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "strict present beam value " + pair);
        }
        foreach (string driver in new[] { "movement", "controller" }) {
            var invalid = raw.DeepClone();
            invalid["runtimeProgram"]!["entities"]![0]![driver]!["params"]!["raycastTiles"] = false;
            Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "item body cannot smuggle neutral beam params through " + driver);
        }
        var foreign = raw.DeepClone();
        foreign["runtimeProgram"]!["entities"]![1]!["movement"]!["params"]!["initialWidthMultiplier"] = 1.0;
        Equal(true, GeneratedItemData.FromJson(foreign.ToJsonString()) is null, "non-beam driver cannot carry a beam extension");
    }

    private static void BeamRampsConsumeLiveDamageAndSharedBodyGeometry()
    {
        using var scope = new SwarmRuntimeScope(visuals: true);
        WithBodyGeometryQueue((count, positions) => {
            foreach (int extra in new[] { 0, 2 }) {
                var data = BeamFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
                entity.Collision.ExtraUpdates = extra; entity.Controller.Params.ManaPayment = "initial_use_only";
                var host = BeamHost(data, damage: 200);
                foreach (var sample in new[] { (Age: 0, Damage: 70f, Width: 22f, Friendly: false),
                    (Age: 8, Damage: 80.4f, Width: 28.24f, Friendly: true),
                    (Age: 50, Damage: 135f, Width: 61f, Friendly: true),
                    (Age: 100, Damage: 200f, Width: 100f, Friendly: true),
                    (Age: 200, Damage: 200f, Width: 100f, Friendly: true) }) {
                    BeamAge(host, sample.Age * (extra + 1)); BeamApply(host);
                    Equal(sample.Friendly, host.Projectile.friendly, "inclusive explicit progress gate");
                    var modifiers = new NPC.HitModifiers(); host.ModifyHitNPC(new NPC(), ref modifiers);
                    BeamNear(sample.Damage, modifiers.SourceDamage.ApplyTo(host.Projectile.damage), "warmup uses live damage and native source modifier");
                    Equal(200, host.Projectile.damage, "hit modifier never compounds or changes inheritance base");
                    var geometry = BeamGeometry(host); BeamNear(sample.Width, geometry.Width, "exact width ramp");
                    int before = count(); DrawBodyGeometry(host);
                    Equal(before + 1, count(), "one runtime beam body");
                    AssertBodySegment(positions(before), geometry.Start, geometry.End, sample.Width);
                }
                BeamAge(host, 50 * (extra + 1));
                host.Projectile.damage = 300;
                host.Configure(data, entity, 0, 32, Vector2.UnitX, preserveSyncedState: true);
                var hydrated = new NPC.HitModifiers(); host.ModifyHitNPC(new NPC(), ref hydrated);
                BeamNear(202.5f, hydrated.SourceDamage.ApplyTo(host.Projectile.damage), "late live damage is multiplied once after hydration");
                entity.Controller.Params.WarmupTicks = 0; BeamAge(host, 0); BeamApply(host);
                var immediate = new NPC.HitModifiers(); host.ModifyHitNPC(new NPC(), ref immediate);
                BeamNear(300, immediate.SourceDamage.ApplyTo(host.Projectile.damage), "zero warmup is immediately full damage");
                BeamNear(100, BeamGeometry(host).Width, "zero warmup is immediately full width");
            }
            var tiny = BeamFixture(); var tinyEntity = tiny.RuntimeProgram.TryGetEntity("root")!;
            tinyEntity.Controller.Params.WidthPx = 2; tinyEntity.Controller.Params.InitialWidthMultiplier = 0.01;
            var thin = BeamHost(tiny); BeamAge(thin, 0);
            var narrow = BeamGeometry(thin); BeamNear(0.02f, narrow.Width, "explicit subpixel width reaches geometry");
            int index = count(); DrawBodyGeometry(thin);
            AssertBodySegment(positions(index), narrow.Start, narrow.End, 0.02f);
        });
    }

    private static void BeamSustainUsesNativeManaAndWorldClock()
    {
        foreach (var role in SwarmRoles)
        foreach (int extra in new[] { 0, 2 })
        foreach (uint origin in new[] { 100u, uint.MaxValue - 2 }) {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = BeamFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Collision.ExtraUpdates = extra;
            var host = BeamHost(data); var owner = Terraria.Main.player[0];
            owner.statMana = 100; owner.manaCost = 0.5f; owner.manaFlower = false;
            owner.HeldItem.mana = 10; owner.HeldItem.useTime = 4;
            int calls = 0; bool pays = role.Name is "SP" or "owner-client";
            using var observer = new Hook(typeof(Player).GetMethod(nameof(Player.CheckMana),
                new[] { typeof(Item), typeof(int), typeof(bool), typeof(bool) })!,
                (Func<Func<Player, Item, int, bool, bool, bool>, Player, Item, int, bool, bool, bool>)
                ((orig, player, item, amount, pay, blockQuickMana) => {
                    Equal(true, ReferenceEquals(owner, player) && ReferenceEquals(owner.HeldItem, item), "exact owner and held item reach native CheckMana");
                    Equal(-1, amount, "native GetManaCost owns cost"); Equal(true, pay, "native call actually pays");
                    Equal(false, blockQuickMana, "native missing-mana effects remain enabled");
                    calls++; return orig(player, item, amount, pay, blockQuickMana);
                }));
            for (uint tick = 0; tick <= 4; tick++) {
                MaterialClock(unchecked(origin + tick));
                for (int update = 0; update <= extra; update++) BeamApply(host);
                Equal(pays && tick == 4 ? 1 : 0, calls, "no initial or extraUpdates double-payment; native useTime cadence");
            }
            Equal(pays ? 95 : 100, owner.statMana, "native manaCost multiplier is applied once");
            owner.HeldItem.useTime = 2;
            MaterialClock(unchecked(origin + 5)); BeamApply(host);
            Equal(pays ? 1 : 0, calls, "current shorter useTime still waits two ticks");
            host.Configure(data, entity, 0, 32, Vector2.UnitX, preserveSyncedState: true);
            MaterialClock(unchecked(origin + 6)); BeamApply(host); BeamApply(host);
            Equal(pays ? 2 : 0, calls, "owner hydration retains cadence; peers never pay");
            Equal(pays ? 90 : 100, owner.statMana, "second native payment consumes exact live cost");
        }
        using (var scope = new SwarmRuntimeScope()) {
            var data = BeamFixture(); var first = BeamHost(data); var second = BeamHost(data, slot: 1);
            var owner = Terraria.Main.player[0]; owner.statMana = 100; owner.HeldItem.mana = 10; owner.HeldItem.useTime = 4;
            MaterialClock(20); BeamApply(first); BeamApply(second);
            Equal(100, owner.statMana, "two physical beams each skip their initial payment");
            MaterialClock(24); BeamApply(first); BeamApply(second);
            Equal(80, owner.statMana, "sustain is explicit per physical beam, not a shared free item timer");
            var legacy = BeamHost(BeamFixture(false)); owner.statMana = 100;
            MaterialClock(100); BeamApply(legacy); MaterialClock(500); BeamApply(legacy);
            Equal(100, owner.statMana, "retained missing sustain choice never creates recurring payment");
        }
    }

    private static void BeamManaFailureAndControlLossTerminateBeforeFurtherPayment()
    {
        using var scope = new SwarmRuntimeScope();
        var data = BeamFixture(); var owner = Terraria.Main.player[0];
        int kills = 0;
        using var kill = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill), Type.EmptyTypes)!,
            (Action<Projectile>)(projectile => { kills++; projectile.active = false; }));
        var host = BeamHost(data); owner.statMana = 0; owner.manaFlower = false;
        owner.HeldItem.mana = 10; owner.HeldItem.useTime = 4;
        MaterialClock(100); BeamApply(host); Equal(0, kills, "initial item payment is not repeated");
        MaterialClock(104); BeamApply(host);
        Equal(1, kills, "native failed CheckMana terminates at deadline");
        Equal(false, host.Projectile.active || host.Projectile.friendly, "failed sustain cannot remain a damaging beam");
        foreach (string reason in new[] { "release", "inactive", "dead", "noItems", "CCed", "different_item" }) {
            host = BeamHost(data); owner.statMana = 100;
            MaterialClock(200); BeamApply(host);
            if (reason == "release") owner.channel = false;
            if (reason == "inactive") owner.active = false;
            if (reason == "dead") owner.dead = true;
            if (reason == "noItems") owner.noItems = true;
            if (reason == "CCed") owner.frozen = true;
            if (reason == "different_item") owner.inventory[0] = new Item();
            int before = kills; MaterialClock(204); BeamApply(host);
            Equal(before + 1, kills, "loss of control terminates " + reason);
            Equal(100, owner.statMana, "termination precedes recurring payment " + reason);
        }
    }

    private static void BeamLaserScanClipsCollisionBodyAndVfxPathTogether()
    {
        using var scope = new SwarmRuntimeScope(visuals: true);
        WithBodyGeometryQueue((count, positions) => {
            foreach (bool tileCollide in new[] { false, true })
            foreach (bool ownerHitCheck in new[] { false, true }) {
                var data = BeamFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
                entity.Collision.TileCollide = tileCollide; entity.Damage.OwnerHitCheck = ownerHitCheck;
                entity.Controller.Params.WidthPx = 40; entity.Controller.Params.InitialWidthMultiplier = 0.5;
                entity.Controller.Params.RaycastTiles = true; entity.Controller.Params.ManaPayment = "initial_use_only";
                var host = BeamHost(data); BeamAge(host, 50); BeamApply(host);
                Equal(tileCollide, host.Projectile.tileCollide, "raycast does not change authored tileCollide");
                Equal(ownerHitCheck, host.Projectile.ownerHitCheck, "raycast does not change native owner-to-target check");
                float stop = 96; int scans = 0;
                using var scan = new Hook(typeof(Collision).GetMethod(nameof(Collision.LaserScan))!,
                    (Action<Vector2, Vector2, float, float, float[]>)((start, direction, width, max, samples) => {
                        scans++; BeamNear(1, direction.Length(), "normalized native scan direction");
                        BeamNear(30, width, "raycast samples current ramped width"); BeamNear(320, max, "native scan gets authored tile range in pixels");
                        Equal(3, samples.Length, "bounded three-ray native scan");
                        samples[0] = stop + 32; samples[1] = stop; samples[2] = stop + 64;
                    }));
                var geometry = BeamGeometry(host);
                BeamNear(96, Vector2.Distance(geometry.Start, geometry.End), "shortest sample sets exact segment end");
                var axis = Vector2.Normalize(geometry.End - geometry.Start);
                Equal(true, host.Colliding(default, BodyTarget(geometry.Start + axis * 80)) == true, "native collision reaches visible pre-wall segment");
                Equal(false, host.Colliding(default, BodyTarget(geometry.End + axis * 60)) == true, "native collision ends at clipped geometry");
                Equal(true, host.TryCapturePresentationGeometry("beam", out var path), "production VFX path captures active beam");
                Equal(geometry.Start, path[0], "VFX path begins at exact collision anchor"); Equal(geometry.End, path[1], "VFX path ends at exact wall-clipped endpoint");
                int before = count(); DrawBodyGeometry(host);
                AssertBodySegment(positions(before), geometry.Start, geometry.End, geometry.Width);
                stop = 48; var moved = BeamGeometry(host);
                BeamNear(48, Vector2.Distance(moved.Start, moved.End), "new closer wall is immediate without overshooting smoothing");
                stop = 0;
                Equal(false, host.Colliding(default, BodyTarget(moved.Start)) == true, "zero scan length has no collision segment");
                before = count(); DrawBodyGeometry(host); Equal(before, count(), "zero scan length draws no body");
                entity.Controller.Params.RaycastTiles = false; int priorScans = scans;
                var uncut = BeamGeometry(host); BeamNear(320, Vector2.Distance(uncut.Start, uncut.End), "explicit disabled raycast retains full range");
                Equal(priorScans, scans, "disabled raycast never queries native tiles");
            }
        });
    }
}
