using System;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Terraria;

// Diagnostic scene only: native lighting and native view matrices, never gameplay motion.
internal sealed partial class WNativeVfxRenderer
{
    string lightingMode = "legacy_point";

    public void ApplyNativeViewport()
    {
        // Dust.NewDust performs native camera culling during Projectile.Update,
        // before Step draws. Rendering alone must not be the first camera owner.
        Vector2 aim=new(Main.mouseX+Main.screenPosition.X,Main.mouseY+Main.screenPosition.Y);
        Main.screenWidth=width;Main.screenHeight=height;Main.screenPosition=camera;
        Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(graphics.Device){Zoom=new Vector2(zoom)};
        Main.mouseX=(int)(aim.X-camera.X);Main.mouseY=(int)(aim.Y-camera.Y);
        Report["viewportAppliedBeforeGameplay"]=true;
        Report["viewportScope"]="Native player/projectile/dust updates and draw share this explicit camera; original Dust.NewDust culling is preserved";
    }

    void ConfigureScene(JsonObject settings)
    {
        lightingMode = settings["lightingMode"]?.GetValue<string>() ?? "legacy_point";
        if (lightingMode is not ("legacy_point" or "viewport_fill"))
            throw new ArgumentException("nativeRender.lightingMode must be legacy_point or viewport_fill");
    }

    // Use the renderer's actual matrix rather than approximating Terraria's zoom origin.
    Vector2[] ViewWorldCorners()
    {
        var inverse = Matrix.Invert(Main.GameViewMatrix.TransformationMatrix);
        return new[] { Vector2.Zero, new Vector2(width, 0), new Vector2(0, height), new Vector2(width, height) }
            .Select(p => Vector2.Transform(p, inverse) + camera).ToArray();
    }

    JsonObject LightingReport(int left, int right, int top, int bottom) => new()
    {
        ["backend"] = "Original Lighting.AddLight / Lighting.LightTiles",
        ["mode"] = lightingMode,
        ["scope"] = "Controlled diagnostic lighting, not a loaded world's illumination",
        ["gameMenu"] = false, ["mapEnabled"] = false,
        ["tileBounds"] = new JsonObject { ["left"] = left, ["rightExclusive"] = right, ["top"] = top, ["bottomExclusive"] = bottom },
        ["boundsSource"] = "Inverse native view matrix, 16-tile margin, clipped to initialized world",
        ["pointLightTileX"] = lightingMode == "legacy_point" ? JsonValue.Create(50) : null,
        ["pointLightTileY"] = lightingMode == "legacy_point" ? JsonValue.Create(45) : null,
        ["pointLightRgb"] = new JsonArray(1, 1, 1),
        ["fillSpacingTiles"] = lightingMode == "viewport_fill" ? JsonValue.Create(4) : null,
        ["warmupNativePhases"] = 4, ["nativePhasesPerTick"] = 1,
        ["perTickOrder"] = "Projectile.Update / Dust.UpdateDust / PostUpdateEverything / Lighting.LightTiles / native draw",
        ["drawAndNoDrawIdenticalUpdate"] = true, ["nativeDustUpdatePerTick"] = true
    };

    public void StepLighting()
    {
        int savedWidth = Main.screenWidth, savedHeight = Main.screenHeight;
        Vector2 savedCamera = Main.screenPosition;
        var savedView = Main.GameViewMatrix;
        try
        {
            Main.screenWidth = width; Main.screenHeight = height; Main.screenPosition = camera;
            Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(graphics.Device) { Zoom = new Vector2(zoom) };
            var corners = ViewWorldCorners();
            int left = (int)Math.Clamp(Math.Floor(corners.Min(p => p.X) / 16d) - 16, 1, Main.maxTilesX - 2);
            int right = (int)Math.Clamp(Math.Ceiling(corners.Max(p => p.X) / 16d) + 16, left + 1, Main.maxTilesX - 1);
            int top = (int)Math.Clamp(Math.Floor(corners.Min(p => p.Y) / 16d) - 16, 1, Main.maxTilesY - 2);
            int bottom = (int)Math.Clamp(Math.Ceiling(corners.Max(p => p.Y) / 16d) + 16, top + 1, Main.maxTilesY - 1);
            if (lightingMode == "viewport_fill")
                for (int x = left; x < right; x += 4)
                    for (int y = top; y < bottom; y += 4) Lighting.AddLight(x, y, 1f, 1f, 1f);
            else Lighting.AddLight(50, 45, 1f, 1f, 1f);
            Lighting.LightTiles(left, right, top, bottom);
            Report["lighting"] = LightingReport(left, right, top, bottom);
        }
        finally { Main.screenWidth = savedWidth; Main.screenHeight = savedHeight; Main.screenPosition = savedCamera; Main.GameViewMatrix = savedView; }
    }

    JsonObject SceneSnapshot()
    {
        JsonObject Bounds(Entity entity)
        {
            var corners = new[] { entity.position, entity.position + new Vector2(entity.width, 0),
                entity.position + new Vector2(0, entity.height), entity.position + new Vector2(entity.width, entity.height) }
                .Select(p => Vector2.Transform(p - camera, Main.GameViewMatrix.TransformationMatrix)).ToArray();
            float left = corners.Min(p => p.X), right = corners.Max(p => p.X), top = corners.Min(p => p.Y), bottom = corners.Max(p => p.Y);
            var light = Lighting.GetColor((int)entity.Center.X / 16, (int)entity.Center.Y / 16);
            return new JsonObject { ["screenLeft"] = left, ["screenRight"] = right, ["screenTop"] = top, ["screenBottom"] = bottom,
                ["hitboxIntersectsViewport"] = right > 0 && bottom > 0 && left < width && top < height,
                ["centerLightRgb"] = new JsonArray(light.R, light.G, light.B) };
        }
        var projectiles = new JsonArray();
        foreach (var p in Main.projectile.Where(p => p.active))
        {
            var row = Bounds(p); row["nativeSlot"] = p.whoAmI; row["nativeIdentity"] = p.identity; row["nativeType"] = p.type;
            projectiles.Add(row);
        }
        return new JsonObject { ["cameraX"] = camera.X, ["cameraY"] = camera.Y, ["zoom"] = zoom,
            ["scope"] = "Native transformed collision bounds and sampled lighting, not sprite bounds, occlusion, pixel visibility or visual approval",
            ["player"] = Bounds(Main.player[Main.myPlayer]), ["projectiles"] = projectiles };
    }
}
