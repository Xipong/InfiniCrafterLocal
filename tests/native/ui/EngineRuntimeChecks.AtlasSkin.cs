using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasPackagedSkinPixelsMatchPngAlpha()
    {
        var straight = new[] {
            new Color(255, 255, 255, 0), new Color(255, 224, 153, 1),
            new Color(191, 162, 108, 40), new Color(131, 43, 33, 128),
            new Color(238, 220, 175, 254), new Color(238, 220, 175, 255),
        };
        foreach (string extension in new[] { ".rawimg", ".RAWIMG" })
        {
            var pixels = straight.ToArray();
            Equal(true, RecipeJournalUISystem.PrepareBookSkinPixels(pixels, extension), "packaged raw skin is converted");
            for (int i = 0; i < pixels.Length; i++)
            {
                Equal(Color.FromNonPremultiplied(straight[i].R, straight[i].G, straight[i].B, straight[i].A), pixels[i],
                    "packaged skin matches native PNG premultiplication exactly");
                Equal(straight[i].A, pixels[i].A, "authored opacity stays unchanged");
                Equal(true, pixels[i].R <= pixels[i].A && pixels[i].G <= pixels[i].A && pixels[i].B <= pixels[i].A,
                    "AlphaBlend never adds a bright edge at partial transparency");
            }
            foreach (string? loadedExtension in new string?[] { ".png", ".xnb", null })
            {
                var alreadyPrepared = pixels.ToArray();
                Equal(false, RecipeJournalUISystem.PrepareBookSkinPixels(alreadyPrepared, loadedExtension),
                    "PNG or unknown loader is never double-premultiplied");
                Equal(true, pixels.SequenceEqual(alreadyPrepared), "already prepared texture remains byte-identical");
            }
        }
    }
}
