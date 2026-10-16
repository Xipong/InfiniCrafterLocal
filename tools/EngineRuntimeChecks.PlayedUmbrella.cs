using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Real saved geometry through native DTO -> AI -> public PreDraw -> CPU FNA
    // queue. Texture shells preserve exact frame sizes; no pixel/GPU art claim.
    private static void PlayedUmbrellaSavedGeometryKeepsHandContactAndReach()
    {
        var rows = JsonNode.Parse(File.ReadAllText(Path.Combine("tools", "fixtures", "played-umbrellas-delivered.json")))!.AsArray();
        Equal(3, rows.Count, "all exact played umbrella definitions retained");
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) =>
        {
            using var scope = new FrontHandRepairScope();
            using var cache = new BorrowedSpriteCache();
            var texture = CpuTexture(64, 64);
            foreach (var row in rows)
            foreach (int facing in new[] { 1, -1 })
            foreach (float gravity in new[] { 1f, -1f })
            {
                var data = GeneratedItemData.FromJson(row!.ToJsonString())
                    ?? throw new InvalidOperationException("played umbrella DTO refused: " + ContractJsonDiagnostics.LastError);
                var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                Equal(20, entity.Movement.Code, "saved explicit front-hand, never code19");
                Equal("initial", entity.Movement.Params.AimMode, "accepted initial-axis design preserved");
                Equal(54, data.Visual.RenderSizePx!.Value, "authored R not enlarged");
                Equal(30, entity.Hitbox.WidthPx, "authored width not buffed");
                Equal(24f, entity.Movement.Params.HitboxOffsetPx!.Value, "authored offset not relocated");
                data.VfxManifest = VfxManifestSpec.Empty(); // only isolate main quad, no gameplay changes
                string path = Path.GetFullPath(data.Visual.SpritePath);
                if (!cache.Textures.Contains(path)) cache.Textures.Add(path, Activator.CreateInstance(cache.Record, texture, 0f, 0L)!);
                scope.Register(data);
                FrontHandRepairOwner(owner, data);
                owner.direction = facing; owner.gravDir = gravity; owner.fullRotation = 0;
                Vector2 axis = new(facing, 0);
                var generated = FrontHandRepairActor(owner, data, 7, axis);
                var projectile = generated.Projectile;
                for (int age = 1; age <= 13; age++)
                {
                    generated.AI();
                    if (age is not (1 or 6 or 7 or 13)) continue;
                    owner.ItemCheck_ApplyUseStyle(0, owner.HeldItem, new Rectangle(0, 0, 64, 64));
                    var stretch = age is 6 or 7 ? Player.CompositeArmStretchAmount.Full : Player.CompositeArmStretchAmount.None;
                    Vector2 hand = FrontHandExpected(owner, axis, stretch);
                    AssertVfxNear(hand + axis * 24, projectile.Center, "saved physical center follows actual native hand");
                    Rectangle hitbox = projectile.Hitbox; generated.ModifyDamageHitbox(ref hitbox);
                    Equal(30, hitbox.Width, "actual damage rectangle remains 30px");
                    Equal(30, hitbox.Height, "actual damage rectangle remains 30px");
                    int index = count(); Color light = Color.White;
                    Vector2 center = projectile.Center;
                    generated.PreDraw(ref light);
                    Equal(index + 1, count(), "one main quad from public native PreDraw");
                    AssertVfxNear(hand - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY),
                        FrontHandQueuedGrip(batch, index, data.Visual.Grip!), "actual queued grip is on hand, not a cosmetic detached offset");
                    AssertVfxNear(axis, BodyForwardFromCpuQueue(batch, index, 0, "played umbrella"), "selected forward remains aimed");
                    float side = positions(index).SelectMany(a => positions(index).Select(b => Vector3.Distance(a, b))).Max() / MathF.Sqrt(2);
                    Equal(true, Math.Abs(side - 54) < .01f, "64px frame draws at exact authored 54px, no double scale");
                    Equal(center, projectile.Center, "Draw never relocates collision");
                }
                projectile.active = false;
            }
        }));
    }
}
