using System;
using System.Collections;
using InfiniCrafterLocal.Common.Services;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System.Collections.Generic;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Actual packet encoder/receiver, registry lookup and detached consumer; no sockets/world loop.
    private static void TexturedBodyUsesDeclaredAxisAndPreservesNativeSpin()
    {
        SameBodyTextureAxisObligations(false); // real FNA UV ABI control before modern assertions
        SameBodyTextureAxisObligations(true);
    }

    private static Vector2 QueueTextureDeclaredAxis(SpriteBatch batch, int index, float degrees)
    {
        // Real FNA CPU vertex storage; pair position/UV members in declaration
        // traversal order. The legacy suite executes first and checks this ABI.
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var vertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", flags)!.GetValue(batch)!;
        var positions = new List<Vector3>();
        var uvs = new List<Vector2>();
        void Visit(object value)
        {
            if (value is Vector3 position) { positions.Add(position); return; }
            if (value is Vector2 uv) { uvs.Add(uv); return; }
            foreach (var field in value.GetType().GetFields(flags))
                if (field.FieldType == typeof(Vector3) || field.FieldType == typeof(Vector2) ||
                    field.FieldType.IsValueType && !field.FieldType.IsPrimitive && !field.FieldType.IsEnum)
                    Visit(field.GetValue(value)!);
        }
        Visit(vertices.GetValue(index)!);
        Equal(4, positions.Count, "FNA observer ABI: four positions");
        Equal(4, uvs.Count, "FNA observer ABI: four UVs");
        Vector2 Basis(bool vertical)
        {
            float min = float.MaxValue, max = float.MinValue;
            foreach (var uv in uvs) { float coordinate = vertical ? uv.Y : uv.X; min = Math.Min(min, coordinate); max = Math.Max(max, coordinate); }
            Equal(true, max - min > 0.9f, "complete synthetic texture UV extent");
            Vector2 low = Vector2.Zero, high = Vector2.Zero; int lowCount = 0, highCount = 0;
            for (int i = 0; i < 4; i++)
            {
                var p = new Vector2(positions[i].X, positions[i].Y); float coordinate = vertical ? uvs[i].Y : uvs[i].X;
                if (Math.Abs(coordinate - min) < 0.001f) { low += p; lowCount++; }
                if (Math.Abs(coordinate - max) < 0.001f) { high += p; highCount++; }
            }
            Equal(2, lowCount, "two low-UV vertices"); Equal(2, highCount, "two high-UV vertices");
            return Vector2.Normalize(high / highCount - low / lowCount);
        }
        float radians = degrees * MathF.PI / 180f;
        return Vector2.Normalize(Basis(false) * MathF.Cos(radians) + Basis(true) * MathF.Sin(radians));
    }

    private static void SameBodyTextureAxisObligations(bool newPresentation)
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 64);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 8);
            var cacheProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? savedCache = cacheProperty.GetValue(null);
            Player savedOwner = Terraria.Main.player[0];
            int savedLocal = Terraria.Main.myPlayer, savedMode = Terraria.Main.netMode;
            var cache = new RuntimeSpriteCache();
            var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", instance)!.GetValue(cache)!;
            var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "axis_texture_cpu.png");
            textures.Add(path, Activator.CreateInstance(record, texture, 0f, 0L)!);
            var failures = new List<string>(); int checkedCases = 0;
            try
            {
                cacheProperty.SetValue(null, cache);
                owner.active = true; owner.whoAmI = 0; owner.position = new Vector2(300, 300);
                Terraria.Main.player[0] = owner; Terraria.Main.myPlayer = 1; // aim from real synced projectile velocity, not mouse
                Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
                foreach (int movement in new[] { 0, 19, 14, 16, 17 })
                foreach (Vector2 aim in new[] { Vector2.UnitX, Vector2.UnitY, Vector2.Normalize(new Vector2(-3, 4)) })
                foreach (int facing in new[] { -1, 1 })
                foreach (string mode in new[] { "baked_sprite", "reuse_item_icon" })
                foreach (int canvas in new[] { 64, 128 })
                foreach (float declared in newPresentation ? new[] { 0f, 45f } : new[] { 0f })
                foreach (float sourceScale in new[] { 0.01f, 1.7f, 12f })
                {
                    typeof(Texture2D).GetProperty("Width")!.SetValue(texture, canvas); typeof(Texture2D).GetProperty("Height")!.SetValue(texture, canvas / 8);
                    var data = GeneratedItemData.Placeholder(); data.Id = "axis_contract_probe";
                    data.Visual.SpritePath = path;
                    data.RuntimeProgram.PrimaryEntityId = "body_probe";
                    data.RuntimeProgram.PrimaryOwner = RuntimeProgramSpec.ProjectileOwner;
                    var entity = new RuntimeEntitySpec { Id = "body_probe", Kind = movement == 19 ? RuntimeEntityKind.OwnerAttachedProjectile : RuntimeEntityKind.FreeProjectile };
                    entity.Visual.AssetMode = mode; entity.Visual.SpritePath = path; entity.Visual.SpriteStatus = "generated";
                    entity.Movement.Code = movement;
                    entity.Movement.Name = movement == 19 ? "move_forward_then_retract" : movement == 14 ? "move_returning_glaive" : movement == 16 ? "move_flail_tether" : movement == 17 ? "move_yoyo_hover" : "move_straight";
                    entity.Movement.Params.RangeTiles = 5f; entity.Movement.Params.DurationTicks = 30;
                    entity.Movement.Params.ReturnAfterTicks = 60;
                    entity.Hitbox.WidthPx = 24; entity.Hitbox.HeightPx = 24;
                    entity.LifetimeTicks = 120; owner.channel = true;
                    data.RuntimeProgram.Entities = new[] { entity };
                    // Local +X is explicit even for spins: native spinning poses remain unchanged.
                    if (newPresentation) {
                        data.Visual.RenderSizePx = mode == "baked_sprite" ? 80 : 40; data.Visual.ForwardAngleDegrees = mode == "baked_sprite" ? -45f : declared;
                        if (mode == "baked_sprite") { entity.Visual.RenderSizePx = 40; entity.Visual.ForwardAngleDegrees = declared; }
                    }
                    var projectile = new Projectile { owner = 0, whoAmI = 7, Center = new Vector2(400, 400), velocity = aim, rotation = 0.23f, spriteDirection = facing };
                    var generated = Attach(projectile);
                    generated.Configure(data, entity, 0, 8, aim);
                    generated.AI(); // actual movement 19 and canonical quarter-turn assignment
                    projectile.scale = sourceScale; // native live/growth state, not definition rewrite
                    float rotation = projectile.rotation;
                    float rawScale = projectile.scale; Vector2 rawVelocity = projectile.velocity;
                    int rawWidth = projectile.width, rawHeight = projectile.height;
                    string unchanged = System.Text.Json.JsonSerializer.Serialize(data);
                    int index = count();
                    DrawBodyGeometry(generated); // actual textured consumer -> FNA CPU queue, no GPU
                    string label = $"movement={movement} aim={aim} facing={facing} mode={mode} modern={newPresentation}";
                    checkedCases++;
                    try
                    {
                        Equal(index + 1, count(), "one authored texture quad");
                        Vector2 actual = QueueTextureDeclaredAxis(batch, index, declared);
                        float radians = declared * MathF.PI / 180f;
                        Vector2 nativeTextureAxis = new Vector2(MathF.Cos(radians) * facing, MathF.Sin(radians)).RotatedBy(rotation);
                        Vector2 expected = newPresentation && movement is not (14 or 16 or 17) ? aim : nativeTextureAxis;
                        AssertVfxNear(expected, actual, "signed authored +X axis: " + label);
                        Equal(rotation, projectile.rotation, "draw cannot modify AI rotation or sync/gameplay state");
                        Equal(rawScale, projectile.scale, "draw cannot change projectile physics scale"); Equal(rawVelocity, projectile.velocity, "draw cannot change movement");
                        Equal(rawWidth, projectile.width, "draw cannot change collision width"); Equal(rawHeight, projectile.height, "draw cannot change collision height");
                        var quad = positions(index); float longest = 0f;
                        for (int i = 0; i < quad.Length; i++) for (int j = i + 1; j < quad.Length; j++) longest = Math.Max(longest, Vector3.Distance(quad[i], quad[j]));
                        float expectedBase = (newPresentation ? 40f : canvas) * Math.Clamp(sourceScale, 0.1f, 8f);
                        Equal(true, Math.Abs(longest - expectedBase * MathF.Sqrt(1f + 1f / 64f)) < 0.001f, "actual main quad uses selected R not canvas resolution");
                        Equal(unchanged, System.Text.Json.JsonSerializer.Serialize(data), "draw preserves exact authored definition");
                        if (movement == 19) Equal(7, owner.heldProj, "real primary owner still claims held projectile");
                    }
                    catch (Exception error) { failures.Add(label + ": " + error.Message); }
                    // Avoid the existing fixed 128-entry queue growing across controls.
                    batch.End(); batch.Begin();
                }
                Console.WriteLine($"Texture-axis obligations modern={newPresentation}: {checkedCases - failures.Count}/{checkedCases}");
            }
            finally
            {
                textures.Clear(); // constructor-bypassed texture: never dispose GPU resources
                cacheProperty.SetValue(null, savedCache);
                Terraria.Main.player[0] = savedOwner;
                Terraria.Main.myPlayer = savedLocal; Terraria.Main.netMode = savedMode;
            }
            if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        }));
    }
    private static void BodyCopiesCaptureSelectedSizeAndAxisWithoutChangingNetworkPose()
    {
        WithActiveShape((unused, slot, manifest, batch, count, positions, colors) =>
        {
            var texture = Terraria.GameContent.TextureAssets.MagicPixel.Value;
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = sprites.GetValue(null);
            var cache = new InfiniCrafterLocal.Common.Services.RuntimeSpriteCache();
            var textures = (System.Collections.IDictionary)cache.GetType().GetField("_textures", instance)!.GetValue(cache)!;
            var record = cache.GetType().GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string rootPath = System.IO.Path.Combine(Terraria.Program.SavePath, "copy_root.png"), bodyPath = System.IO.Path.Combine(Terraria.Program.SavePath, "copy_body.png"), impactPath = System.IO.Path.Combine(Terraria.Program.SavePath, "copy_impact.png");
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", statics)!.GetValue(null)!;
            var drawLayer = typeof(InfiniDetachedVfxSystem).GetMethod("DrawProjectiles", statics)!;
            var vertexField = typeof(SpriteBatch).GetField("vertexInfo", instance)!;
            var oldView = Terraria.Main.GameViewMatrix;
            var oldProjectiles = Terraria.Main.projectile;
            object? observed = null;
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!,
                (Action<Action<SpriteBatch>, SpriteBatch>)((orig, self) => {
                    if (count() > 0) observed = ((Array)vertexField.GetValue(batch)!).GetValue(0);
                    orig(self);
                }));
            void SameGeometry(object expected, object actual, string label)
            {
                int examined = 0;
                foreach (var f in expected.GetType().GetFields())
                    if (f.Name.StartsWith("Position") || f.Name.StartsWith("Texture")) {
                        examined++;
                        object a = f.GetValue(expected)!, b = f.GetValue(actual)!;
                        Equal(true, a is Vector3 av && b is Vector3 bv ? Vector3.DistanceSquared(av, bv) < 0.000001f : Equals(a, b), label + " " + f.Name);
                    }
                Equal(8, examined, "FNA observer ABI: four positions and four texture coordinates");
            }
            try
            {
                sprites.SetValue(null, cache);
                foreach (string path in new[] { rootPath, bodyPath, impactPath }) textures.Add(path, Activator.CreateInstance(record, texture, 0.37f, 0L)!);
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Microsoft.Xna.Framework.Graphics.Viewport(0, 0, 800, 600));
                foreach (bool modern in new[] { false, true })
                foreach (int canvas in new[] { 64, 128 })
                foreach (string mode in new[] { "reuse_item_icon", "baked_sprite" })
                foreach (string role in new[] { "entity", "item", "impact" })
                foreach (float sourceScale in new[] { 0.01f, 1.7f, 12f })
                {
                    batch.End(); batch.Begin(); system.OnWorldUnload();
                    typeof(Microsoft.Xna.Framework.Graphics.Texture2D).GetProperty("Width")!.SetValue(texture, canvas);
                    typeof(Microsoft.Xna.Framework.Graphics.Texture2D).GetProperty("Height")!.SetValue(texture, canvas / 8);
                    var data = GeneratedItemData.Placeholder(); data.Id = "copy_presentation";
                    InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                    data.Visual.SpritePath = rootPath;
                    var entity = new RuntimeEntitySpec { Id = "probe", Kind = RuntimeEntityKind.FreeProjectile, VisualRole = "projectile" };
                    entity.Visual.AssetMode = mode; entity.Visual.SpritePath = bodyPath; entity.Visual.ImpactSpritePath = impactPath;
                    entity.Movement.Code = 0;
                    data.RuntimeProgram.Entities = new[] { entity }; data.VfxManifest = manifest;
                    if (modern) { data.Visual.RenderSizePx = 1; data.Visual.ForwardAngleDegrees = 45f; if (mode == "baked_sprite") { entity.Visual.RenderSizePx = 3; entity.Visual.ForwardAngleDegrees = 0f; } }
                    var projectile = new Projectile { owner = 4, identity = 17, width = 24, height = 20, Center = new Vector2(160, 140), velocity = Vector2.UnitX,
                        rotation = MathHelper.PiOver2, spriteDirection = -1, gfxOffY = 7f, scale = sourceScale };
                    slot.RendererKind = "projectileAfterimage"; slot.TextureRole = role; slot.Event = RuntimeEventKind.Periodic; slot.Scale = 1f; slot.Anchor = "self";
                    int? expectedR = !modern || role == "impact" ? null : role == "item" || mode == "reuse_item_icon" ? 1 : 3;
                    float expectedRotation = projectile.rotation;
                    if (modern && role != "impact") {
                        float declared = role == "item" || mode == "reuse_item_icon" ? 45f : 0f;
                        float a = declared * MathF.PI / 180f;
                        expectedRotation = -MathF.Atan2(MathF.Sin(a), -MathF.Cos(a));
                    }
                    float dimensionless = Math.Clamp(sourceScale, 0.1f, 8f);
                    var state = new InfiniVfxState(); for (int i = 0; i < 3; i++) state.Push(projectile.Center);
                    InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                    Equal(1, count(), "real live copy dispatch");
                    float liveScale = expectedR.HasValue ? expectedR.Value / (float)canvas * dimensionless : Math.Max(0.05f, sourceScale);
                    batch.Draw(texture, projectile.Center + new Vector2(0, 7) - Terraria.Main.screenPosition, null, Color.White,
                        expectedRotation, texture.Bounds.Size() / 2f, liveScale, Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipHorizontally, 0);
                    var v = (Array)vertexField.GetValue(batch)!;
                    SameGeometry(v.GetValue(1)!, v.GetValue(0)!, "live selected texture size and signed axis");
                    batch.End(); batch.Begin();
                    slot.Event = RuntimeEventKind.OnKill; slot.Scale = 1.5f;
                    float detachedScale = dimensionless * slot.Scale * (expectedR.HasValue ? expectedR.Value / (float)canvas : 1f);
                    batch.Draw(texture, projectile.Center + new Vector2(0, 7) - Terraria.Main.screenPosition, null, Color.White,
                        expectedRotation, texture.Bounds.Size() / 2f, detachedScale, Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipHorizontally, 0);
                    object expected = ((Array)vertexField.GetValue(batch)!).GetValue(0)!;
                    batch.End(); batch.Begin();
                    var snapshot = InfiniVfxProjectileSnapshot.Capture(projectile, data, "probe");
                    Equal(projectile.Center + Vector2.UnitX * (projectile.width * projectile.scale / 2f), snapshot.Tip, "tip remains hitbox/P based, not R based");
                    Equal(dimensionless, snapshot.Pose.Scale, "snapshot/network remains dimensionless, never q*P");
                    Equal(projectile.rotation, snapshot.Pose.Rotation, "raw packet pose is not rewritten");
                    byte[] packet = EncodeProjectileVfxForCheck(data, projectile, slot.Event, projectile.Center);
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, manifest, ref state, projectile.Center);
                    Equal(1, queue.Count, "body event persists after retirement");
                    object emission = queue[0]!;
                    Equal(true, Equals(expectedR, emission.GetType().GetProperty("RenderSizePx")!.GetValue(emission)), "immutable selected base size captured");
                    projectile.active = false; projectile.rotation = -2f; projectile.scale = 0.2f; projectile.Center = Vector2.Zero;
                    if (modern) { data.Visual.RenderSizePx = 512; if (mode == "baked_sprite") entity.Visual.RenderSizePx = 512; }
                    batch.End(); observed = null;
                    On_Main.orig_DrawProjectiles original = _ => { };
                    drawLayer.Invoke(null, new object?[] { original, null });
                    Equal(true, observed is not null, "detached reaches real FNA flush boundary"); SameGeometry(expected, observed!, "retired immutable selected copy");
                    // Remote uses the receiver's canonical metadata plus the captured raw pose, never a live source lookup.
                    if (modern) { data.Visual.RenderSizePx = 1; if (mode == "baked_sprite") entity.Visual.RenderSizePx = 3; }
                    system.OnWorldUnload(); Terraria.Main.projectile = Array.Empty<Projectile>(); observed = null;
                    ReceiveProjectileVfxForCheck(data, packet); Equal(1, queue.Count, "real v5 decoder resolves canonical metadata");
                    drawLayer.Invoke(null, new object?[] { original, null }); SameGeometry(expected, observed!, "remote dimensionless pose plus selected size/axis");
                    batch.Begin();
                }
            }
            finally { textures.Clear(); sprites.SetValue(null, oldCache); Terraria.Main.GameViewMatrix = oldView; Terraria.Main.projectile = oldProjectiles; system.OnWorldUnload(); }
        });
    }

    private static void ItemBodyCopyUsesRootSizeAndDedicatedImpactStaysIndependent()
    {
        WithActiveShape((unused, slot, manifest, batch, count, positions, colors) =>
        {
            var texture = Terraria.GameContent.TextureAssets.MagicPixel.Value;
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = sprites.GetValue(null);
            var cache = new InfiniCrafterLocal.Common.Services.RuntimeSpriteCache();
            var textures = (System.Collections.IDictionary)cache.GetType().GetField("_textures", instance)!.GetValue(cache)!;
            var record = cache.GetType().GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "item_body_copy.png");
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", statics)!.GetValue(null)!;
            var wrapper = typeof(InfiniDetachedVfxSystem).GetMethod("DrawProjectiles", statics)!;
            var oldView = Terraria.Main.GameViewMatrix;
            float actualExtent = -1;
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!,
                (Action<Action<SpriteBatch>, SpriteBatch>)((orig, self) => {
                    if (count() > 0) { var p = positions(0); actualExtent = Vector3.Distance(p[0], p[1]); }
                    orig(self);
                }));
            try
            {
                sprites.SetValue(null, cache); textures.Add(path, Activator.CreateInstance(record, texture, 0.37f, 0L)!);
                typeof(Microsoft.Xna.Framework.Graphics.Texture2D).GetProperty("Width")!.SetValue(texture, 128);
                typeof(Microsoft.Xna.Framework.Graphics.Texture2D).GetProperty("Height")!.SetValue(texture, 16);
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Microsoft.Xna.Framework.Graphics.Viewport(0, 0, 800, 600));
                var data = GeneratedItemData.Placeholder(); data.Visual.SpritePath = path; data.Visual.RenderSizePx = 1; data.Visual.ForwardAngleDegrees = 45f;
                var body = data.RuntimeProgram.Entities[0]; body.Visual.AssetMode = "baked_sprite"; body.Visual.SpritePath = path; body.Visual.ImpactSpritePath = path;
                slot.EntityId = body.Id; slot.TextureRole = "entity"; slot.Scale = 0.25f; slot.Event = RuntimeEventKind.OnUse; slot.Anchor = "self";
                foreach (bool impact in new[] { false, true })
                {
                    system.OnWorldUnload(); slot.RendererKind = impact ? "impactSprite" : "actorAfterimage";
                    InfiniVfxRuntime.EmitEventSprite(data, body.Id, new Vector2(160, 140), Vector2.UnitX, slot, manifest, "item_copy");
                    Equal(1, queue.Count, "exact item body selection reaches detached queue"); object emission = queue[0]!;
                    Equal(true, Equals(impact ? null : (object)1, emission.GetType().GetProperty("RenderSizePx")!.GetValue(emission)), "dedicated impact never borrows root R");
                    Equal(!impact, (bool)emission.GetType().GetProperty("HasCapturedPose")!.GetValue(emission)!, "declared axis only for body copy, impact retains cache convention");
                    if (!impact) Equal(true, Math.Abs((float)emission.GetType().GetProperty("Rotation")!.GetValue(emission)! + MathF.PI / 4f) < 0.001f, "item copy final-texture axis captured explicitly");
                    batch.End(); actualExtent = -1;
                    On_Main.orig_DrawProjectiles original = _ => { };
                    wrapper.Invoke(null, new object?[] { original, null });
                    Equal(true, Math.Abs(actualExtent - (impact ? 32f : 0.25f)) < 0.001f, "q occurs after old dimensionless clamp, not before its floor");
                    batch.Begin();
                }
            }
            finally { textures.Clear(); sprites.SetValue(null, oldCache); Terraria.Main.GameViewMatrix = oldView; system.OnWorldUnload(); }
        });
    }

    private static ulong _probeVfxSequence;
    private static byte[] EncodeProjectileVfxForCheck(GeneratedItemData data, Projectile projectile, string eventName, Vector2 eventPoint)
    {
        var type = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile);
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        var payloadType = type.GetNestedType("VfxEventPayload", BindingFlags.NonPublic)!;
        object payload = Activator.CreateInstance(payloadType, projectile.owner, projectile.identity, 123L,
            data.Id, "probe", eventName, eventPoint, projectile.velocity,
            InfiniVfxProjectileSnapshot.Capture(projectile, data, "probe"))!;
        payloadType.GetProperty("Occurrence")!.SetValue(payload,++_probeVfxSequence);
        using var stream = new System.IO.MemoryStream();
        using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true))
            type.GetMethod("WriteVfxEventPayload", flags)!.Invoke(null, new[] { (object)writer, payload });
        return stream.ToArray();
    }

    private static void ReceiveProjectileVfxForCheck(GeneratedItemData data, byte[] bytes)
    {
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
        var property = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = property.GetValue(null);
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        using var registry = new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
        try
        {
            property.SetValue(null, registry);
            ((System.Collections.IDictionary)registry.GetType().GetField("_byId", instance)!.GetValue(registry)!).Add(data.Id, data);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new System.IO.MemoryStream(bytes);
            using var reader = new System.IO.BinaryReader(stream);
            InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.HandleVfxEventSyncPacket(reader, 256);
        }
        finally { property.SetValue(null, oldRegistry); Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; }
    }

    private static void ProjectileEventSnapshotRelayPreservesAnchors()
    {
        WithLighting((config, lights) =>
        {
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var oldOwner = Terraria.Main.player[4];
            var oldProjectiles = Terraria.Main.projectile;
            try
            {
                var owner = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(600, 700) };
                var data = GeneratedItemData.Placeholder();
                InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                var entity = new RuntimeEntitySpec { Id = "probe" }; entity.Movement.Code = 14;
                data.RuntimeProgram.Entities = new[] { entity };
                var slot = new VfxSlotSpec { Id = "relay", EntityId = "probe", Event = RuntimeEventKind.OnHit,
                    RendererKind = "beamLine", ParticleSystemId = "none", Scale = 1f, Duration = 24 };
                data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
                foreach (string anchor in new[] { "self", "owner", "tip", "hitPoint", "field", "tipHistory", "velocity" })
                {
                    system.OnWorldUnload(); owner.active = true; owner.Center = new Vector2(600, 700); slot.Anchor = anchor;
                    var projectile = new Projectile { owner = 4, identity = 11, width = 40, height = 20,
                        Center = new Vector2(160, 140), velocity = Vector2.UnitX, rotation = 1.1f, scale = 1.7f, gfxOffY = 7f, spriteDirection = -1 };
                    var state = new InfiniVfxState(); Vector2 hit = new(900, 1000);
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, data.VfxManifest, ref state, hit);
                    Equal(1, queue.Count, "local anchor witness");
                    object local = queue[0]!;
                    Vector2 expectedCenter = (Vector2)local.GetType().GetProperty("Center")!.GetValue(local)!;
                    Vector2 expectedForward = (Vector2)local.GetType().GetProperty("Forward")!.GetValue(local)!;
                    byte[] packet = EncodeProjectileVfxForCheck(data, projectile, slot.Event, hit);
                    // The remote no longer has a projectile or active source owner.
                    projectile.active = false; projectile.Center = Vector2.Zero; projectile.rotation = -2;
                    owner.active = false; owner.Center = Vector2.Zero; Terraria.Main.projectile = Array.Empty<Projectile>();
                    system.OnWorldUnload(); ReceiveProjectileVfxForCheck(data, packet);
                    Equal(1, queue.Count, anchor + " relay survives removed projectile");
                    object remote = queue[0]!;
                    AssertVfxNear(expectedCenter, (Vector2)remote.GetType().GetProperty("Center")!.GetValue(remote)!, anchor + " relay uses captured anchor, not hit point");
                    AssertVfxNear(expectedForward, (Vector2)remote.GetType().GetProperty("Forward")!.GetValue(remote)!, anchor + " relay uses captured body forward");
                }
                var source = new Projectile { owner = 4, Center = new Vector2(100, 200), velocity = Vector2.UnitX,
                    width = 40, height = 20, scale = 1f, rotation = 0.8f, spriteDirection = -1, gfxOffY = 3f };
                owner.active = true; owner.Center = new Vector2(600, 700);
                slot.Anchor = "self";
                byte[] valid = EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900, 1000));
                Equal((byte)5, valid[0], "snapshot packet is version 5 preserving immutable v3/v4 facts with ordered occurrences");
                int start;
                using (var stream = new System.IO.MemoryStream(valid))
                using (var reader = new System.IO.BinaryReader(stream))
                {
                    reader.ReadByte(); reader.ReadInt32(); reader.ReadInt32(); reader.ReadInt64();
                    reader.ReadString(); reader.ReadString(); reader.ReadString();
                    start = (int)stream.Position; // event point + velocity, then fixed presentation fields
                }
                void Reject(byte[] bytes, string label)
                {
                    system.OnWorldUnload(); ReceiveProjectileVfxForCheck(data, bytes);
                    Equal(0, queue.Count, label);
                }
                var oldVersion = (byte[])valid.Clone(); oldVersion[0] = 2; Reject(oldVersion, "old version rejected");
                Reject(valid[..^1], "truncated pose rejected");
                // Every coordinate/pose float in the wire must reject non-finite values.
                int snapshotStart = start + 16, ownerFlag = snapshotStart + 24;
                int rotationOffset = ownerFlag + 1 + 8, flipOffset = rotationOffset + 8;
                foreach (int offset in new[] { start, start + 4, start + 8, start + 12,
                    snapshotStart, snapshotStart + 4, snapshotStart + 8, snapshotStart + 12,
                    snapshotStart + 16, snapshotStart + 20, ownerFlag + 1, ownerFlag + 5,
                    rotationOffset, rotationOffset + 4, flipOffset + 1 })
                foreach (float bad in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity })
                {
                    var bytes = (byte[])valid.Clone(); BitConverter.GetBytes(bad).CopyTo(bytes, offset);
                    Reject(bytes, "nonfinite packet float rejected at " + offset);
                }
                foreach (int offset in new[] { ownerFlag, flipOffset })
                { var bytes = (byte[])valid.Clone(); bytes[offset] = 2; Reject(bytes, "malformed pose discriminator rejected"); }
                foreach (float scale in new[] { 0f, -1f, 9f })
                {
                    var bytes = (byte[])valid.Clone(); BitConverter.GetBytes(scale).CopyTo(bytes, rotationOffset + 4);
                    Reject(bytes, "out-of-range captured scale rejected");
                }
                var zeroForward = (byte[])valid.Clone(); Array.Clear(zeroForward, snapshotStart + 16, 8);
                Reject(zeroForward, "missing forward axis rejected instead of invented");
                // Absence of an active owner is an exact optional fact, not center fallback.
                owner.active = false; slot.Anchor = "owner";
                byte[] noOwner = EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900, 1000));
                Reject(noOwner, "owner anchor unavailable at capture stays silent");
                slot.Anchor = "self"; ReceiveProjectileVfxForCheck(data, EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900,1000)));
                Equal(1, queue.Count, "missing owner does not suppress independent self anchor");
            }
            finally { system.OnWorldUnload(); Terraria.Main.player[4] = oldOwner; Terraria.Main.projectile = oldProjectiles; }
        });
    }

    private static void ItemVfxParticleSelectorsAndBudgets()
    {
        WithLighting((config, lights) =>
        {
            var oldDust = Terraria.Main.dust;
            var random = Terraria.Main.rand;
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int max = Terraria.Main.maxDustToDraw, width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            Vector2 screen = Terraria.Main.screenPosition;
            float count = Dust.dCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var detached = new InfiniDetachedVfxSystem();
            try
            {
                Terraria.Main.gameMenu = false; WorldGen.gen = false;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 600;
                Terraria.Main.screenPosition = Vector2.Zero;
                config.ParticleSpawnMultiplier = 1f;
                var player = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                foreach (var choice in new[] { ("dust", DustID.GemDiamond, true), ("pl:smoke", DustID.Smoke, false),
                    ("pl:shard", DustID.Glass, true), ("pl:spark", DustID.Electric, true), ("pl:glow", DustID.TintableDustLighted, true) })
                {
                    detached.OnWorldUnload();
                    InfiniItemVfxRuntime.ClearUseEventCaches();
                    clock.SetValue(null, 100u);
                    Terraria.Main.dust = new Dust[oldDust.Length];
                    for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                    Dust.dCount = 0; Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                    var data = GeneratedItemData.Placeholder();
                    string entity = data.RuntimeProgram.ItemEntityId;
                    var slot = new VfxSlotSpec { Id = "dust_probe", EntityId = entity, Event = RuntimeEventKind.OnUse,
                        RendererKind = "impactRing", ParticleSystemId = choice.Item1, Density = 1f };
                    data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
                    // First isolate the selector with an unrestricted allowance.
                    data.VfxManifest.Budget.MaxParticlesPerTick = 32;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    foreach (Dust dust in Terraria.Main.dust.Where(d => d.active))
                    {
                        Equal(choice.Item2, dust.type, "exact authored item dust selector " + choice.Item1);
                        Equal(choice.Item3, dust.noGravity, "smoke preserves existing gravity semantics");
                        Equal(player.Center, dust.position, "item producer world coordinates");
                    }
                    Equal(8, Terraria.Main.dust.Count(d => d.active), "existing item particle count preserved");
                    slot.ParticleSystemId = "none";
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(8, Terraria.Main.dust.Count(d => d.active), "explicit none does not fall back to diamond dust");
                    slot.ParticleSystemId = choice.Item1;
                    detached.OnWorldUnload();
                    foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                    InfiniItemVfxRuntime.ClearUseEventCaches();
                    data.VfxManifest.Budget.MaxParticlesPerTick = 2;
                    data.VfxManifest.Budget.MaxParticlesTotal = 3;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "item per-tick budget");
                    slot.Event = RuntimeEventKind.OnHit;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnHit);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "different event shares item source budget");
                    clock.SetValue(null, 101u);
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnHit);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "reused item gets a new tick allowance, not a permanent total cap");
                    slot.Event = RuntimeEventKind.Periodic; slot.RepeatEvery = 1;
                    // Keep touching this exact source beyond detached-budget retention.
                    // Real Dust is reset only for observation, never the source ledger.
                    uint endTick = 102u + (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks;
                    for (uint tick = 102; tick <= endTick; tick++)
                    {
                        clock.SetValue(null, tick);
                        foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                        detached.PostUpdateEverything();
                        InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                        InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                        Equal(2, Terraria.Main.dust.Count(d => d.active), "continuous periodic renews only per-tick allowance tick=" + tick);
                    }
                    slot.Event = RuntimeEventKind.OnUse;
                    clock.SetValue(null, endTick + 1);
                    foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "reuse after continuous periodic remains live");
                    var otherPlayer = new Player { whoAmI = 5, active = true, Center = player.Center };
                    InfiniItemVfxRuntime.EmitAndSyncEvent(otherPlayer, data, entity, RuntimeEventKind.OnUse);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "different player has independent tick allowance");
                    clock.SetValue(null, endTick + 2);
                    data.VfxManifest.Budget.MaxParticlesTotal = 0;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "explicit zero particle budget stays silent");
                }
            }
            finally
            {
                detached.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, oldClock);
                Terraria.Main.dust = oldDust; Terraria.Main.rand = random;
                Terraria.Main.gameMenu = menu; WorldGen.gen = gen;
                Terraria.Main.maxDustToDraw = max; Terraria.Main.screenWidth = width; Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen; Dust.dCount = count;
            }
        });
    }

    private delegate ReLogic.Utilities.SlotId EventSoundObserver(in Terraria.Audio.SoundStyle style,
        Vector2? position, Terraria.Audio.SoundUpdateCallback? callback);

    private static void ItemVfxSoundPreservesAuthoredPhase()
    {
        WithLighting((config, lights) =>
        {
            Terraria.Audio.SoundStyle? observed = null;
            Vector2? location = null;
            EventSoundObserver observer = (in Terraria.Audio.SoundStyle style, Vector2? position,
                Terraria.Audio.SoundUpdateCallback? callback) => {
                observed = style; location = position;
                return ReLogic.Utilities.SlotId.Invalid; // observe API boundary; no audio device
            };
            var play = typeof(Terraria.Audio.SoundEngine).GetMethod("PlaySound", new[] {
                typeof(Terraria.Audio.SoundStyle).MakeByRefType(), typeof(Vector2?), typeof(Terraria.Audio.SoundUpdateCallback) })!;
            using var hook = new MonoMod.RuntimeDetour.Hook(play, observer);
            var player = new Player { active = true, Center = new Vector2(160f) };
            var data = GeneratedItemData.Placeholder();
            string entity = data.RuntimeProgram.ItemEntityId;
            var slot = new VfxSlotSpec { Id = "sound_probe", EntityId = entity, Event = RuntimeEventKind.OnUse,
                RendererKind = "soundCue", Channel = "sound", Lane = "cue", Alpha = 0.4f };
            data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
            foreach (float phase in new[] { -1f, 0f, 1f })
            {
                slot.PhaseOffset = phase; observed = null;
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                Equal(true, observed.HasValue, "item sound API reached");
                Equal(phase * 0.25f, observed!.Value.Pitch, "existing authored phase-to-pitch mapping");
                Equal(0.4f, observed.Value.Volume, "authored volume preserved");
                Equal(SoundID.Item1.SoundPath, observed.Value.SoundPath, "no new sound-style mapping");
                Equal(player.Center, location!.Value, "sound stays at producer world position");
            }
            Terraria.Main.dedServ = true; observed = null;
            InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
            Equal(false, observed.HasValue, "dedicated server remains silent");
        });
    }

    private static void ItemVfxRemoteRejectsInactiveSource()
    {
        WithLighting((config, lights) =>
        {
            var old = Terraria.Main.player[4];
            int mode = Terraria.Main.netMode;
            try
            {
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                var player = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.OnHit);
                var item = player.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
                var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
                typeof(Terraria.ModLoader.ModType<Item>).GetProperty("Entity")!.SetValue(generated, item);
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                void Receive(string eventName)
                {
                    using var stream = new System.IO.MemoryStream();
                    using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    { writer.Write((byte)3); writer.Write((byte)4); writer.Write(data.Id); writer.Write(entity); writer.Write(eventName); writer.Write(160f); writer.Write(160f); }
                    stream.Position = 0;
                    using var reader = new System.IO.BinaryReader(stream);
                    InfiniItemVfxRuntime.HandleUseEventPacket(reader, 4);
                }
                Receive(RuntimeEventKind.OnHit);
                Equal(1, lights.Count, "valid relay still uses local light consumer");
                lights.Clear(); Receive(RuntimeEventKind.OnCrit);
                Equal(0, lights.Count, "relay cannot substitute a different event");
                player.active = false; Receive(RuntimeEventKind.OnHit);
                Equal(0, lights.Count, "inactive remote source cannot emit a late event");
            }
            finally { Terraria.Main.player[4] = old; Terraria.Main.netMode = mode; }
        });
    }

    // Observe real AI -> slot clock / gameplay scheduler. No world spawning or GPU.
    private static void ProjectilePeriodicVfxIsIndependentOfGameplayActions()
    {
        WithLighting((config, lights) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var oldOwner = Terraria.Main.player[0]; var oldNpcs = Terraria.Main.npc;
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem)
                .GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var pending = (System.Collections.IList)typeof(InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler)
                .GetField("Pending", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            try
            {
                config.PresentationLightMultiplier = 1f;
                Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, Center = new Vector2(160f) };
                Terraria.Main.npc = new NPC[oldNpcs.Length];
                for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i };
                var npc = Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0, life = 1000, lifeMax = 1000,
                    knockBackResist = 1f, width = 16, height = 16, Center = new Vector2(176, 160) };
                foreach (bool actions in new[] { true, false })
                foreach (int extra in new[] { 0, 2 })
                {
                    system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                    npc.velocity = Vector2.Zero;
                    var entity = Entity(); entity.Id = "periodic_probe"; entity.Kind = RuntimeEntityKind.StationaryProjectile;
                    entity.LifetimeTicks = 60;
                    entity.Events = actions ? new[] {
                        new RuntimeEventActionSpec { Id = "immediate", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.Pull, PeriodTicks = 6, Mode = "target_to_point", RadiusTiles = 4, Strength = 0.5f },
                        new RuntimeEventActionSpec { Id = "delayed_a", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 6, DelayTicks = 2, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_b", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 6, DelayTicks = 3, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_c", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 12, DelayTicks = 4, Count = 1 },
                    } : Array.Empty<RuntimeEventActionSpec>();
                    var data = GeneratedItemData.Placeholder(); data.RuntimeProgram.Entities = new[] { entity };
                    data.VfxManifest.Slots = new[] {
                        new VfxSlotSpec { Id = "periodic_shape", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "impactRing", ParticleSystemId = "none", RepeatEvery = 5, StartTick = 0, SlotSeed = 0 },
                        new VfxSlotSpec { Id = "periodic_light", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "lightCue", ParticleSystemId = "none", RepeatEvery = 5, StartTick = 0, SlotSeed = 0 },
                    };
                    var projectile = new Projectile { active = true, owner = 0, Center = new Vector2(160f), damage = 100 };
                    var generated = Attach(projectile); generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    projectile.extraUpdates = extra;
                    for (uint tick = 1; tick <= 12; tick++)
                    {
                        clock.SetValue(null, tick); lights.Clear(); projectile.netUpdate = false;
                        for (int update = 0; update <= extra; update++) generated.AI();
                        Equal(actions && tick >= 6 ? tick >= 12 ? 5 : 2 : 0, pending.Count,
                            "gameplay periods remain world-tick based with extraUpdates=" + extra + " tick=" + tick);
                        Equal(actions && tick % 6 == 0, projectile.netUpdate, "delayed spawn reservation keeps netUpdate timing");
                        Equal(actions ? -(float)(tick / 6) * 0.5f : 0f, npc.velocity.X, "real immediate periodic pull executes at authored period");
                        Equal(tick % 5 == 0 ? 1 : 0, lights.Count,
                            "periodic light follows own slot, not gameplay action period; actions=" + actions + " tick=" + tick);
                        Equal(0, queue.Count, "live periodic shape never gains a second detached presentation clock");
                    }
                    if (actions)
                    {
                        string ids = string.Join(",", pending.Cast<object>().Select(p =>
                            ((RuntimeEventActionSpec)p.GetType().GetProperty("Action")!.GetValue(p)!).Id));
                        Equal("delayed_a,delayed_b,delayed_a,delayed_b,delayed_c", ids, "authored scheduler enqueue order unchanged");
                        Equal("2,3,2,3,4", string.Join(",", pending.Cast<object>().Select(p =>
                            unchecked((uint)p.GetType().GetProperty("DueTick")!.GetValue(p)!
                                - (uint)p.GetType().GetProperty("EnqueuedTick")!.GetValue(p)!))), "authored delays unchanged");
                    }
                    // Exact event lanes remain independent after removing only the periodic relay.
                    data.VfxManifest.Slots = new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit,
                        RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill }.Select(ev => new VfxSlotSpec {
                            Id = ev, EntityId = entity.Id, Event = ev, RendererKind = "impactRing", ParticleSystemId = "none" }).ToArray();
                    clock.SetValue(null, 13u);
                    generated.OnHitNPC(npc, new NPC.HitInfo { Crit = true }, 1);
                    Equal(2, queue.Count, "actual critical hit keeps both hit and crit presentation");
                    projectile.timeLeft = 1; generated.AI(); generated.OnKill(0);
                    Equal(4, queue.Count, "final AI and kill keep both expire and kill presentation");
                }
            }
            finally
            {
                system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                clock.SetValue(null, oldClock); Terraria.Main.player[0] = oldOwner; Terraria.Main.npc = oldNpcs;
            }
        });
    }

    private static void ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick()
    {
        ItemPeriodicPresentationHasOneWorldTickOwner();
        ProjectilePeriodicVfxIsIndependentOfGameplayActions();
        WithLighting((config, lights) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previous = clock.GetValue(null);
            try
            {
                var player = new Player { active = true, Center = new Vector2(160f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.Periodic);
                var slot = data.VfxManifest.Slots[0];
                slot.StartTick = 5; slot.RepeatEvery = 3; slot.SlotSeed = 0;
                for (uint tick = 0; tick < 10; tick++)
                {
                    clock.SetValue(null, tick); lights.Clear();
                    InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                    Equal(tick % 3 == 0 ? 1 : 0, lights.Count, "item world-clock cadence ignores projectile-only StartTick tick=" + tick);
                }
                slot.Event = RuntimeEventKind.OnUse;
                clock.SetValue(null, 0u); lights.Clear();
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                Equal(1, lights.Count, "nonperiodic event is not filtered by periodic cadence");
            }
            finally { clock.SetValue(null, previous); }
        });
    }
}
