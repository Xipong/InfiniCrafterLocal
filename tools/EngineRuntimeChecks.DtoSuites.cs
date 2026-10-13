using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Test data, not callbacks containing retired observers. Paths describe the
    // authored wire; literals reach FromJson before numeric narrowing occurs.
    private sealed record JsonChange(string Path, string? Literal);
    private sealed record JsonRefusal(string Name, params JsonChange[] Changes)
    {
        internal static JsonRefusal For(string path, string? literal)
            => new(path + "=" + (literal ?? "<absent>"), new JsonChange(path, literal));
    }

    private static JsonNode JsonAt(JsonNode root, string path)
    {
        foreach (string part in path.Split('/'))
            root = root is JsonArray array ? array[int.Parse(part)]! : root.AsObject()
                .Single(pair => pair.Key.Equals(part, StringComparison.OrdinalIgnoreCase)).Value!;
        return root;
    }

    private static string ChangedJson(string fixture, params JsonChange[] changes)
    {
        JsonNode root = JsonNode.Parse(fixture)!;
        for (int index = 0; index < changes.Length; index++)
        {
            var change = changes[index];
            int split = change.Path.LastIndexOf('/');
            var parent = JsonAt(root, change.Path[..split]);
            string leaf = change.Path[(split + 1)..];
            if (parent is JsonArray array) array[int.Parse(leaf)] = "__dto_literal_" + index + "__";
            else
            {
                var obj = parent.AsObject();
                string? existing = obj.Select(pair => pair.Key).FirstOrDefault(key => key.Equals(leaf, StringComparison.OrdinalIgnoreCase));
                if (change.Literal is null) { obj.Remove(existing ?? leaf); continue; }
                // Uppercase admission cases really change the wire spelling, not merely the lookup.
                if (existing is not null && leaf == leaf.ToUpperInvariant()) obj.Remove(existing);
                else leaf = existing ?? leaf;
                obj[leaf] = "__dto_literal_" + index + "__";
            }
        }
        string json = root.ToJsonString();
        for (int index = 0; index < changes.Length; index++)
            if (changes[index].Literal is string literal)
                json = json.Replace("\"__dto_literal_" + index + "__\"", literal, StringComparison.Ordinal);
        return json; // Raw numeric bytes are never narrowed through a fixture float/double.
    }

    private static IEnumerable<(string Route, string Json)> DtoRoutes(GeneratedItemData data, bool cache = false, bool alternate = false)
    {
        yield return ("full", data.ToJson());
        if (cache) yield return ("cache", data.ToLocalCacheJson());
        yield return ("network", data.ToNetworkJson());
        if (alternate) yield return ("alternate", JsonSerializer.Serialize(data));
    }

    private static void CheckDtoRefusals(string raw, IEnumerable<JsonRefusal> cases, string label,
        string[]? required = null)
    {
        foreach (string path in required ?? Array.Empty<string>())
            CheckJsonRefusal(raw, new("missing " + path, new JsonChange(path, null)), label);
        foreach (var test in cases) CheckJsonRefusal(raw, test, label);
    }

    private static void AssertDtoOmissions(GeneratedItemData data, string parent, string[] leaves, string label)
    {
        foreach (var (route, json) in DtoRoutes(data))
        {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException(label + "/" + route + ": omitted DTO rejected");
            var obj = JsonAt(JsonNode.Parse(json)!, parent).AsObject();
            foreach (string leaf in leaves)
                Equal(false, obj.ContainsKey(leaf), label + "/" + route + ": omitted " + leaf);
        }
    }

    private static void CheckJsonRefusal(string pristine, JsonRefusal refusal, string owner)
    {
        Equal(true, GeneratedItemData.FromJson(ChangedJson(pristine, refusal.Changes)) is null, owner + "/" + refusal.Name);
        Console.WriteLine("CASE PASS: " + owner + "/" + refusal.Name);
    }

    private static IEnumerable<JsonRefusal> InvalidJsonValues(string path, params string[] literals)
        => literals.Select(literal => new JsonRefusal(path + "=" + literal, new JsonChange(path, literal)));

    private const string ActorJson = "runtimeProgram/entities/1";
    private const string EventJson = ActorJson + "/events/0";

    private static void CheckHitboxCurveDto()
    {
        var source = RootSpawnFixture(8, 1);
        source.RuntimeProgram.Entities[1].HitboxCurve = HitboxCurve();
        string raw = source.ToJson();
        var data = GeneratedItemData.FromJson(raw) ?? throw new InvalidOperationException("valid hitbox curve rejected");
        Equal(4f, data.RuntimeProgram.Entities[1].HitboxCurve!.EndScale, "DTO preserves explicit scale");
        AssertDtoRoundTrips(data, 4f, copy => copy.RuntimeProgram.Entities[1].HitboxCurve!.EndScale, "HitboxCurve");
        const string path = ActorJson + "/hitboxCurve";
        CheckDtoRefusals(raw, InvalidJsonValues(path + "/startScale", "null", "true", "\"1\"", "0", "9")
            .Concat(new[] { JsonRefusal.For(path + "/unknown", "1"),
                JsonRefusal.For(path, "null") }), "HitboxCurve",
            new[] { "startScale", "endScale", "startDelayTicks", "durationTicks", "curve", "mirrorToSprite" }.Select(leaf => path + "/" + leaf).ToArray());
        var legacy = GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path, null)))
            ?? throw new InvalidOperationException("legacy curve absence rejected");
        AssertDtoOmissions(legacy, ActorJson, new[] { "hitboxCurve" }, "HitboxCurveLegacy");
    }

    private static void CheckBeamDto()
    {
        AssertDtoRoundTrips(BeamFixture(), ("each_use_time", .35, .22, .08, false), copy => {
            var p = copy.RuntimeProgram.TryGetEntity("root")!.Controller.Params;
            return (p.ManaPayment ?? "", p.InitialDamageMultiplier ?? -1, p.InitialWidthMultiplier ?? -1, p.DamageStartProgress ?? -1, p.RaycastTiles ?? true);
        }, "BeamDto");
        var legacy = BeamFixture(false);
        const string path = ActorJson + "/controller/params/";
        AssertDtoOmissions(legacy, path.TrimEnd('/'), new[] { "manaPayment", "initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress", "raycastTiles" }, "BeamLegacy");
        CheckDtoRefusals(legacy.ToJson(),
            InvalidJsonValues(path + "manaPayment", "null", "\"Each_use_time\"", "true")
            .Concat(InvalidJsonValues(path + "initialDamageMultiplier", "null", "0", "1.001", "0.9999999999"))
            .Concat(InvalidJsonValues(path + "initialWidthMultiplier", "false", "0.9999999999"))
            .Concat(InvalidJsonValues(path + "damageStartProgress", "-0.01", "1.1"))
            .Concat(InvalidJsonValues(path + "raycastTiles", "null", "1"))
            .Concat(new[] { JsonRefusal.For("runtimeProgram/entities/0/movement/params/raycastTiles", "false"),
                JsonRefusal.For("runtimeProgram/entities/0/controller/params/raycastTiles", "false"),
                JsonRefusal.For(ActorJson + "/movement/params/initialWidthMultiplier", "1.0") }), "BeamLegacy");
    }

    private static void CheckConcurrencyDto()
    {
        foreach (int value in new[] { 1, 3, 96 })
        {
            var data = ConcurrencyFixture(value);
            foreach (var (route, json) in DtoRoutes(data, alternate: true))
                Equal(value, JsonAt(JsonNode.Parse(json)!, ActorJson + "/spawn/maxActive").GetValue<int>(), "raw concurrency wire " + route);
            AssertDtoRoundTrips(data, (int?)value, copy => copy.RuntimeProgram.Entities[1].Spawn.MaxActive, "Concurrency/" + value, alternate: true);
        }
        var legacy = ConcurrencyFixture(null);
        AssertDtoOmissions(legacy, ActorJson + "/spawn", new[] { "maxActive" }, "ConcurrencyLegacy");
        CheckDtoRefusals(legacy.ToJson(), InvalidJsonValues(ActorJson + "/spawn/maxActive", "0", "97", "-1", "null", "true", "1.5", "\"1\"")
            .Concat(new[] { JsonRefusal.For("runtimeProgram/entities/0/spawn/maxActive", "1") }), "ConcurrencyLegacy");
        Equal(true, GeneratedItemData.FromJson(legacy.ToJson()) is not null, "legacy item-body absence stays valid");
    }

    private static void CheckNamedEffectsDto()
    {
        var data = NamedItemEffectsFixture();
        AssertDtoRoundTrips(data, ("alternate_effects", 35), copy => (copy.RuntimeProgram.Bindings[1].UsePolicy.Action.EffectGroupId!, copy.RuntimeProgram.EffectGroups![1].HealMana), "NamedEffectsDto");
        CheckDtoRefusals(data.ToJson(), new[] {
            JsonRefusal.For("runtimeProgram/effectGroups", "null"),
            JsonRefusal.For("runtimeProgram/effectGroups", "[]"),
            JsonRefusal.For("runtimeProgram/bindings/0/usePolicy/action/effectGroupId", "null"),
            JsonRefusal.For("runtimeProgram/bindings/0/usePolicy/action/effectGroupId", "\"missing\""),
            JsonRefusal.For("runtimeProgram/bindings/0/usePolicy/action/effectGroupId", null),
            JsonRefusal.For("runtimeProgram/effectGroups/0/damage", "999"),
            JsonRefusal.For("runtimeProgram/effectGroups/0/generatedBuff", "null") }, "NamedEffectsDto");
    }

    private static void CheckModifierDtos()
    {
        foreach (var row in ModifierObjects)
        {
            var fixture = SwarmGameplayFixture();
            string raw = ChangedJson(fixture.ToJson(), new JsonChange(ActorJson + "/" + row.Member, row.Json));
            var data = GeneratedItemData.FromJson(raw) ?? throw new InvalidOperationException(row.Member + ": fixture refused");
            string path = ActorJson + "/" + row.Member;
            Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "network modifier re-admission " + row.Member);
            CheckDtoRefusals(raw, new[] { JsonRefusal.For(path + "/durationTicks", "0"),
                JsonRefusal.For(path + "/unknown", "1"), JsonRefusal.For(path, "null") },
                "Modifier/" + row.Member, row.Required.Select(leaf => path + "/" + leaf).ToArray());
            Equal(true, GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path, null))) is not null, "old modifier absence");
        }
        foreach (var row in ModifierNumbers)
            CheckRawDtoPair(SwarmGameplayFixture().ToJson(), ActorJson + "/" + row.Member,
                row.Member == "hitboxCurve"
                    ? "{\"startScale\":1,\"endScale\":4,\"curve\":\"linear\",\"startDelayTicks\":0,\"durationTicks\":60,\"mirrorToSprite\":false}"
                    : ModifierObjects.Single(spec => spec.Member == row.Member).Json,
                row.Field, row.Outside, row.Valid, "ModifierRaw/" + row.Member + "/" + row.Field);
        var legacy = GeneratedItemData.FromJson(SwarmGameplayFixture().ToJson())!;
        Equal(false, legacy.ToJson().Contains("turnModifier", StringComparison.Ordinal), "old absence remains absent");
        CheckJsonRefusal(legacy.ToJson(), new("gravity requires whip", new JsonChange(ActorJson + "/whipUsesOwnerGravity", "true")), "Modifier");
    }

    private sealed record ModifierObject(string Member, string Json, string[] Required);
    private static readonly ModifierObject[] ModifierObjects = {
        new("turnModifier", "{\"turnRadiansPerUpdate\":0.1,\"startDelayTicks\":0,\"durationTicks\":60}", new[] { "turnRadiansPerUpdate", "startDelayTicks", "durationTicks" }),
        new("speedModifier", "{\"speedMultiplierPerUpdate\":1.01,\"maxSpeed\":20,\"startDelayTicks\":0,\"durationTicks\":60}", new[] { "speedMultiplierPerUpdate", "maxSpeed", "startDelayTicks", "durationTicks" }),
        new("homingModifier", "{\"rangeTiles\":10,\"maxTurnRadiansPerUpdate\":0.1,\"requireLineOfSight\":true,\"startDelayTicks\":0,\"durationTicks\":60}", new[] { "rangeTiles", "maxTurnRadiansPerUpdate", "requireLineOfSight", "startDelayTicks", "durationTicks" }),
        new("npcAttraction", "{\"rangeTiles\":10,\"strengthPerUpdate\":2,\"falloff\":\"linear\",\"maxTargets\":4,\"startDelayTicks\":0,\"durationTicks\":60}", new[] { "rangeTiles", "strengthPerUpdate", "falloff", "maxTargets", "startDelayTicks", "durationTicks" }),
        new("visualScaleCurve", "{\"startScale\":1,\"endScale\":4,\"curve\":\"exponential\",\"startDelayTicks\":0,\"durationTicks\":60}", new[] { "startScale", "endScale", "curve", "startDelayTicks", "durationTicks" }),
    };
    private sealed record ModifierNumber(string Member, string Field, string Outside, string Valid);
    private static readonly ModifierNumber[] ModifierNumbers = {
        new("turnModifier", "turnRadiansPerUpdate", "0.500000000000000000000000000001", "0.499999999999999999999999999999"),
        new("turnModifier", "turnRadiansPerUpdate", "1e-46", "0"),
        new("speedModifier", "speedMultiplierPerUpdate", "1.200000000000000000000000001", "1.19999999999999999999999999"),
        new("speedModifier", "speedMultiplierPerUpdate", "1.0000000000000002", "1"),
        new("speedModifier", "maxSpeed", "0.09999999999999999999999999", "0.10000000000000000000000001"),
        new("homingModifier", "rangeTiles", "120.00000000000000000000001", "120"),
        new("homingModifier", "maxTurnRadiansPerUpdate", "0.0000999999999999999999999", "0.0001"),
        new("npcAttraction", "rangeTiles", "80.00000000000000000000001", "80"),
        new("npcAttraction", "strengthPerUpdate", "0.0009999999999999999999999", "0.001"),
        new("visualScaleCurve", "startScale", "0.24999999999999999999999999", "0.25"),
        new("visualScaleCurve", "endScale", "8.000000000000000000000001", "8"),
        new("hitboxCurve", "startScale", "0.24999999999999999999999999", "0.25"),
        new("hitboxCurve", "endScale", "8.000000000000000000000001", "8"),
    };

    private static void CheckRawDtoPair(string fixture, string objectPath, string objectJson,
        string field, string outside, string valid, string name)
    {
        string raw = ChangedJson(fixture, new JsonChange(objectPath, objectJson));
        string path = objectPath + "/" + field;
        CheckJsonRefusal(raw, new("source-domain " + outside, new JsonChange(path, outside)), name);
        var accepted = GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path, valid)))
            ?? throw new InvalidOperationException(name + ": in-domain literal refused " + valid);
        foreach (var (route, json) in DtoRoutes(accepted))
            Equal(true, GeneratedItemData.FromJson(json) is not null, name + "/" + route + ": rounded endpoint re-admits");
        Console.WriteLine("CASE PASS: " + name + "/" + outside + "/" + valid);
    }


    private static void CheckTargetEmissionDto()
    {
        using var scope = new Rt01NpcScope(Terraria.ID.NetmodeID.SinglePlayer);
        var data = TargetEmissionFixture();
        AssertDtoRoundTrips(data, (2, 22.5, "previous_target", "allow_revisits", false, 10, 0), copy => {
            var action = copy.RuntimeProgram.TryGetEntity("root")!.Events.Single();
            return (action.StepCount!.Value, action.StepRangeTiles!.Value, action.SelectionAnchor!, action.RepeatPolicy!, action.RequireLineOfSight!.Value, action.InitialIgnoreCountdownUpdates!.Value, action.DelayTicks);
        }, "TargetEmissionDto", alternate: true);
        var invalidValues = new (string Field, string Literal)[] {
            ("stepCount", "null"), ("stepCount", "0"), ("stepCount", "13"),
            ("stepCount", "2.0"), ("stepCount", "true"), ("stepRangeTiles", "0.9999999999999999"),
            ("stepRangeTiles", "60.00000000000001"), ("stepRangeTiles", "null"), ("selectionAnchor", "\"closest\""),
            ("repeatPolicy", "null"), ("requireLineOfSight", "0"), ("initialIgnoreCountdownUpdates", "601"),
            ("initialIgnoreCountdownUpdates", "-1"), ("delayTicks", "601"), ("event", "\"on_kill\""),
            ("event", "\"ON_HIT\""), ("entityId", "\"HOP\""), ("damageMultiplier", "0.75"),
            ("count", "2"), ("actionCode", "4"), ("action", "\"chain_damage_on_event\""),
        };
        CheckDtoRefusals(data.ToJson(), invalidValues.Select(row => JsonRefusal.For(EventJson + "/" + row.Field, row.Literal)),
            "TargetEmissionDto", new[] { "event", "entityId", "stepCount", "stepRangeTiles", "selectionAnchor", "repeatPolicy",
                "requireLineOfSight", "initialIgnoreCountdownUpdates", "delayTicks" }.Select(leaf => EventJson + "/" + leaf).ToArray());
        string pristine = data.ToJson();
        var old = SwarmGameplayFixture();
        old.RuntimeProgram.TryGetEntity("root")!.Events = new[] { new RuntimeEventActionSpec {
            Id = "old_radial", Event = "on_hit", Action = "chain_damage_on_event", ActionCode = RuntimeEventActionCode.ChainDamage,
            Count = 2, RangeTiles = 22.5f, DamageMultiplier = 0.5f, DelayTicks = 0,
        } };
        string oldJson = SwarmWire(old).ToJson();
        Equal(false, oldJson.Contains("stepCount", StringComparison.Ordinal), "legacy action has no invented new fields");
        var oldRaw = JsonNode.Parse(oldJson)!;
        oldRaw["runtimeProgram"]!["entities"]![1]!["events"]![0]!["stepCount"] = 1;
        Equal(true, GeneratedItemData.FromJson(oldRaw.ToJsonString()) is null, "new fields cannot attach to another opcode");
        const string child = "runtimeProgram/entities/2/spawn";
        CheckDtoRefusals(pristine, new[] {
            JsonRefusal.For(child + "/aim", "\"cursor\""), JsonRefusal.For(child + "/aim", "\"VELOCITY\""),
            JsonRefusal.For(child + "/placement", "\"ITEM_USE_ORIGIN\""), JsonRefusal.For(child + "/offsetPx", "null"),
            JsonRefusal.For(child + "/overTarget", "{\"heightTiles\":-1,\"delayTicks\":0}"),
        }, "TargetEmissionOrigin", new[] { "aim", "placement", "offsetPx" }.Select(leaf => child + "/" + leaf).ToArray());
    }


    private static void CheckWeaponAmmoDto()
    {
        var data = WeaponAmmoFixture("bullet", "native_shot");
        AssertDtoRoundTrips(data, ("bullet", "native_shot"), copy => (copy.RuntimeProgram.WeaponAmmo!.AmmoCategory, copy.RuntimeProgram.WeaponAmmo.SpeedBasis), "WeaponAmmoDto");
        CheckDtoRefusals(data.ToJson(),
            new[] { JsonRefusal.For("runtimeProgram/weaponAmmo", "null"),
                JsonRefusal.For("runtimeProgram/weaponAmmo/ammoCategory", null),
                JsonRefusal.For("runtimeProgram/weaponAmmo/speedBasis", null),
                JsonRefusal.For("runtimeProgram/weaponAmmo/ammoCategory", "\"bullets\""),
                JsonRefusal.For("runtimeProgram/weaponAmmo/projectilePolicy", "\"native_ammo\""),
                new JsonRefusal("dual_ammo_role", new JsonChange("gameplay/ammoCategory", "\"bullet\""), new JsonChange("gameplay/ammoProjectileId", Terraria.ID.ProjectileID.Bullet.ToString())) }, "WeaponAmmoDto");
        var raw = JsonNode.Parse(WeaponAmmoFixture("bullet", "native_shot").ToJson())!;
        var bindings = raw["runtimeProgram"]!["bindings"]!.AsArray();
        for (int index = bindings.Count - 1; index >= 0; index--)
            if (RuntimeBindingSpec.IsActiveInput((string?)bindings[index]!["input"] ?? "")) bindings.RemoveAt(index);
        Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "WeaponAmmoDto/passive_only");
        Equal(true, GeneratedItemData.FromJson(RootSpawnFixture(0, 1).ToJson())!.RuntimeProgram.WeaponAmmo is null, "legacy has no invented ammo");
    }

    private static void CheckSentryTargetingDto()
    {
        var data = SentryTargetingFixture();
        const string path = ActorJson + "/targeting/";
        AssertDtoRoundTrips(data, (4, .6, "player_assigned_first", true), copy => {
            var target = copy.RuntimeProgram.TryGetEntity("root")!.Targeting;
            return (target.Count ?? 1, target.SpreadRadians ?? 0d, target.TargetPolicy ?? "distance_score", target.RequireLineOfSight == true && target.HardRange == true);
        }, "SentryTargetingDto");
        string raw = ChangedJson(data.ToJson(), new JsonChange(path + "count", null), new JsonChange(path + "spreadRadians", null),
            new JsonChange(path + "targetPolicy", null), new JsonChange(path + "requireLineOfSight", null), new JsonChange(path + "hardRange", null));
        var legacy = GeneratedItemData.FromJson(raw) ?? throw new InvalidOperationException("historical targeting absence refused");
        var kept = legacy.RuntimeProgram.TryGetEntity("root")!.Targeting;
        Equal(1, kept.Count ?? 1, "retained one shot"); Equal(0d, kept.SpreadRadians ?? 0d, "retained spread neutral");
        Equal("distance_score", kept.TargetPolicy ?? "distance_score", "retained policy");
        Equal(false, kept.RequireLineOfSight == true || kept.HardRange == true, "retained soft score without LOS");
        CheckDtoRefusals(raw,
            InvalidJsonValues(path + "count", "0", "5", "null", "true")
                .Concat(InvalidJsonValues(path + "spreadRadians", "-0.1", "0.8", "1e-50", "null"))
                .Concat(InvalidJsonValues(path + "targetPolicy", "\"nearest\"", "null"))
                .Concat(InvalidJsonValues(path + "requireLineOfSight", "null"))
                .Concat(InvalidJsonValues(path + "hardRange", "1")), "SentryTargetingLegacy");
        AssertDtoOmissions(legacy, path.TrimEnd('/'), new[] { "count", "spreadRadians", "targetPolicy", "requireLineOfSight", "hardRange" }, "SentryTargetingLegacy");
        foreach (string kind in new[] { RuntimeEntityKind.ItemBody, RuntimeEntityKind.ChildProjectile })
        {
            var owner = JsonNode.Parse(data.ToJson())!;
            owner["runtimeProgram"]!["entities"]!.AsArray().First(row => (string?)row!["kind"] == kind)!["targeting"]!["count"] = 1;
            Equal(true, GeneratedItemData.FromJson(owner.ToJsonString()) is null, "misplaced targeting " + kind);
        }
    }


    private static void AssertDtoRoundTrips<T>(GeneratedItemData data, T expected,
        Func<GeneratedItemData, T> observe, string label, bool cache = false, bool alternate = false)
    {
        foreach (var (route, json) in DtoRoutes(data, cache, alternate))
        {
            var copy = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException(label + "/" + route + ": rejected");
            Equal(expected, observe(copy), label + "/" + route);
        }
    }

    private static void CheckSpritePresentationDtos()
    {
        var legacy = GeneratedItemData.Placeholder();
        foreach (var (route, json) in DtoRoutes(legacy, cache: true, alternate: true))
        {
            Equal(false, json.Contains("\"renderSizePx\"") || json.Contains("\"forwardAngleDegrees\""), "legacy omission " + route);
            Equal(true, GeneratedItemData.FromJson(json) is not null, "legacy re-admission " + route);
        }
        foreach (bool distinct in new[] { false, true })
        {
            var fixture = distinct ? SpritePresentationFixture(64) : legacy;
            string path = distinct ? ActorJson + "/visual" : "visual";
            string raw = distinct ? ChangedJson(fixture.ToJson(), new JsonChange(path + "/forwardAngleDegrees", null)) : fixture.ToJson();
            var control = GeneratedItemData.FromJson(raw)!;
            Equal(false, (distinct ? control.RuntimeProgram.Entities[1].Visual.ForwardAngleDegrees : control.Visual.ForwardAngleDegrees).HasValue, "axis omission");
            if (distinct)
            {
                Equal("sprite_axis_probe", control.RuntimeProgram.Entities[1].Id, "independent baked entity retained");
                Equal("baked_sprite", control.RuntimeProgram.Entities[1].Visual.AssetMode, "independent sprite owner retained");
            }
            foreach (var row in SpriteAxisNumbers)
            {
                var data = GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path + "/forwardAngleDegrees", row.Literal)));
                string label = "SpriteAxis/" + path + "/" + row.Literal;
                Equal(row.Expected.HasValue, data is not null, label + "/admission");
                if (!row.Expected.HasValue) continue;
                float? Axis(GeneratedItemData copy) => distinct ? copy.RuntimeProgram.Entities[1].Visual.ForwardAngleDegrees : copy.Visual.ForwardAngleDegrees;
                Equal(row.Expected, Axis(data!), label + "/narrowed value");
                AssertDtoRoundTrips(data!, row.Expected, Axis, label, cache: true, alternate: true);
            }
            Equal(true, GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path + "/FORWARDANGLEDEGREES", "45.125"))) is not null, "case-insensitive legal axis");
            Equal(true, GeneratedItemData.FromJson(ChangedJson(raw, new JsonChange(path + "/FORWARDANGLEDEGREES", "180.000001"))) is null, "case-insensitive domain refusal");
        }
        Equal(true, PresentationWith("{\"renderSizePx\":32}") is not null, "size without fresh-authoring axis requirement");
        Equal(true, PresentationWith("{\"forwardAngleDegrees\":0}") is not null, "present zero does not opt into visibility");
        foreach (int size in new[] { 1, 32, 512 })
        foreach (float axis in new[] { -180f, 0f, 45f, 180f })
        {
            var data = PresentationWith($"{{\"renderSizePx\":{size},\"forwardAngleDegrees\":{axis.ToString(System.Globalization.CultureInfo.InvariantCulture)}}}");
            Equal(true, data is not null, "strict root bounds admitted");
            AssertDtoRoundTrips(data!, (size, axis), copy => (copy.Visual.RenderSizePx!.Value, copy.Visual.ForwardAngleDegrees!.Value), "root presentation", cache: true, alternate: true);
            Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(GeneratedItemData.FromPlayerSaveJson(data!.ToPlayerSaveJson())), "compact is not second presentation authority");
        }
        foreach (int canvas in new[] { 24, 32, 48, 64, 96, 128 })
        {
            var data = SpritePresentationFixture(canvas);
            AssertDtoRoundTrips(data, (37, canvas, -45f), copy => {
                var visual = copy.RuntimeProgram.Entities[1].Visual;
                return (visual.RenderSizePx!.Value, visual.PreferredCanvasSize!.Value, visual.ForwardAngleDegrees!.Value);
            }, "entity presentation", cache: true, alternate: true);
            CheckPresentationInvalids(data.ToJson(), ActorJson + "/visual", distinct: true);
            foreach (string leaf in new[] { "renderSizePx", "preferredCanvasSize", "forwardAngleDegrees" })
                CheckJsonRefusal(legacy.ToJson(), new("item alias " + leaf, new JsonChange("runtimeProgram/entities/0/visual/" + leaf, leaf == "forwardAngleDegrees" ? "0" : "32")), "SpritePresentation");
            foreach (string mode in new[] { "reuse_item_icon", "runtime_geometry", "no_asset" })
                CheckJsonRefusal(data.ToJson(), new("non-baked " + mode, new JsonChange(ActorJson + "/visual/assetMode", JsonSerializer.Serialize(mode))), "SpritePresentation");
        }
        CheckPresentationInvalids(legacy.ToJson(), "visual", distinct: false);
    }

    private static GeneratedItemData SpritePresentationFixture(int canvas)
    {
        var data = GeneratedItemData.Placeholder();
        var entity = new RuntimeEntitySpec { Id = "sprite_axis_probe", Kind = RuntimeEntityKind.FreeProjectile };
        entity.VisualRole = entity.Visual.Role = RuntimeEntityKind.VisualRoleFor(entity.Kind);
        entity.Spawn.Enabled = true; entity.Movement.Name = "move_straight"; entity.Movement.Code = 0;
        entity.Visual.AssetMode = "baked_sprite"; entity.Visual.SpritePath = "axis-probe.png"; entity.Visual.SpriteStatus = "generated";
        entity.Visual.RenderSizePx = 37; entity.Visual.PreferredCanvasSize = canvas; entity.Visual.ForwardAngleDegrees = -45f;
        data.RuntimeProgram.Entities = new[] { data.RuntimeProgram.Entities[0], entity };
        return data;
    }

    private static void CheckPresentationInvalids(string raw, string path, bool distinct)
    {
        foreach (string leaf in distinct ? new[] { "renderSizePx", "preferredCanvasSize", "forwardAngleDegrees" } : new[] { "renderSizePx", "forwardAngleDegrees" })
            foreach (var invalid in InvalidJsonValues(path + "/" + leaf, distinct ? new[] { "null", "false", "\"32\"" } : new[] { "null", "true", "\"32\"", "[]", "{}" }))
                CheckJsonRefusal(raw, invalid, "SpritePresentationTypes");
        foreach (var invalid in InvalidJsonValues(path + "/renderSizePx", "0", "-1", "513", "1.5")
            .Concat(InvalidJsonValues(path + "/forwardAngleDegrees", "-180.01", "180.01", "1e100")))
            CheckJsonRefusal(raw, invalid, "SpritePresentationBounds");
        if (distinct)
            foreach (var invalid in InvalidJsonValues(path + "/preferredCanvasSize", "0", "25", "129"))
                CheckJsonRefusal(raw, invalid, "SpritePresentationCanvas");
    }

    private sealed record AxisNumber(string Literal, float? Expected);
    private static readonly AxisNumber[] SpriteAxisNumbers = {
        new("-180", -180f), new("0", 0f), new("180", 180f), new("45.125", 45.125f),
        new("-179.999999", -180f), new("179.999999", 180f),
        new("179.999999999999999999999999999999", 180f), new("18e1", 180f), new("-1800e-1", -180f),
        new("180.000000000000000000000000000000", 180f), new("1e-100", 0f),
        new("180.000001", null), new("-180.000001", null),
        new("180.000000000000000000000000000001", null), new("-180.000000000000000000000000000001", null),
        new("1.80000000000000000000000000000001e2", null), new("180000000000000000000000000000001e-30", null),
        new("180.01", null), new("-180.01", null), new("181", null), new("1e100", null), new("1e400", null),
        new("null", null), new("\"180\"", null),
    };



    private static void AssertManifestRefusal(string raw, string label, params JsonChange[] changes)
    {
        Equal(0, VfxManifestSpec.FromJson(ChangedJson(raw, changes)).Slots.Length, label);
        Console.WriteLine("CASE PASS: " + label);
    }

}
