using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

internal static partial class EngineRuntimeChecks
{
    // CPU ingestion/cache test: decoded straight RGBA is supplied at FromStream;
    // GetData/SetData and disposal are intercepted. No GPU/PNG decoder acceptance.
    // Installed tML 2026.6.3.6 FNA FromStream uploads ReadImageStream unchanged.
    // ReLogic premultiplies explicitly: tModLoader commit
    // 29bf9785f5f4de8cd305be002c4cc48aa1177b20,
    // patches/TerrariaNetCore/ReLogic/Content/Readers/PngReader.cs.patch.
    private static void RuntimeSpriteCachePremultipliesDecodedPixelsOnce()
    {
        string sandbox = Directory.CreateTempSubdirectory("icl-sprite-alpha-").FullName;
        var oldGraphics = Terraria.Main.graphics;
        bool oldServer = Terraria.Main.dedServ;
        var source = new[] {
            new Color(200, 100, 50, 128), new Color(7, 129, 255, 1),
            new Color(17, 85, 203, 255), new Color(91, 182, 233, 0),
            new Color(255, 0, 0, 127), new Color(0, 255, 0, 64),
            new Color(0, 0, 255, 192), new Color(255, 255, 255, 8),
        };
        Color[] pixels = (Color[])source.Clone();
        int loads = 0, reads = 0, writes = 0, disposals = 0;
        bool failUpload = false, failRead = false;
        int width = source.Length;
        Func<GraphicsDevice, Stream, Texture2D> load = (_, _) => {
            loads++;
            var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            GC.SuppressFinalize(texture);
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, width);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 1);
            pixels = (Color[])source.Clone();
            return texture;
        };
        Action<Texture2D, Color[]> read = (_, destination) => {
            reads++;
            if (failRead) throw new InvalidOperationException("test readback failure");
            pixels.CopyTo(destination, 0);
        };
        Action<Texture2D, Color[]> write = (_, data) => {
            writes++;
            if (failUpload) throw new InvalidOperationException("test upload failure");
            pixels = (Color[])data.Clone();
        };
        Action<GraphicsResource> dispose = _ => disposals++;
        using var loadHook = new MonoMod.RuntimeDetour.Hook(typeof(Texture2D).GetMethod("FromStream", new[] { typeof(GraphicsDevice), typeof(Stream) })!, load);
        // RuntimeDetour cannot hook generic GetData<Color>/SetData<Color> directly.
        // Replace only these GPU calls in the canonical cache IL, not cache logic.
        var dataHooks = new System.Collections.Generic.List<MonoMod.RuntimeDetour.ILHook>();
        var cache = new RuntimeSpriteCache();
        try
        {
            foreach (var method in typeof(RuntimeSpriteCache).GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly))
                dataHooks.Add(new MonoMod.RuntimeDetour.ILHook(method, il => {
                    var cursor = new MonoMod.Cil.ILCursor(il);
                    while (cursor.TryGotoNext(i => i.Operand is Mono.Cecil.MethodReference m &&
                        ((m.DeclaringType.FullName == typeof(Texture2D).FullName && (m.Name == "GetData" || m.Name == "SetData") && m.Parameters.Count == 1)
                        || (m.Name == "Dispose" && m.Parameters.Count == 0 && m.DeclaringType.FullName == typeof(GraphicsResource).FullName))))
                    {
                        var name = ((Mono.Cecil.MethodReference)cursor.Next!.Operand).Name;
                        cursor.Remove();
                        if (name == "Dispose") cursor.EmitDelegate<Action<GraphicsResource>>(dispose);
                        else cursor.EmitDelegate<Action<Texture2D, Color[]>>(name == "GetData" ? read : write);
                    }
                }));
            Terraria.Main.dedServ = false;
            Terraria.Main.graphics = (GraphicsDeviceManager)RuntimeHelpers.GetUninitializedObject(typeof(GraphicsDeviceManager));
            GC.SuppressFinalize(Terraria.Main.graphics);
            string path = Path.Combine(sandbox, "soft.png");
            byte[] fileBytes = { 1, 2, 3, 4 }; // decode boundary is explicitly intercepted
            File.WriteAllBytes(path, fileBytes);
            Texture2D? first = cache.TryGet(path, out float angle);
            Equal(true, first != null, "canonical cache accepts decoded texture");
            for (int i = 0; i < source.Length; i++)
            {
                Color c = source[i];
                Equal(new Color(c.R * c.A / 255, c.G * c.A / 255, c.B * c.A / 255, c.A), pixels[i], "straight RGBA converted: " + i);
                Equal(c.A, pixels[i].A, "alpha/PCA mask unchanged: " + i);
            }
            Equal(1, reads, "conversion reuses PCA readback");
            Equal(1, writes, "one converted upload");
            Equal(true, ReferenceEquals(first, cache.TryGet(path, out float hitAngle)), "cache hit preserves texture identity");
            Equal(angle, hitAngle, "cache hit preserves PCA orientation");
            Equal(1, loads, "cache hit does not decode");
            Equal(1, reads, "cache hit does not readback");
            Equal(1, writes, "cache hit does not double-premultiply");
            Equal(true, fileBytes.SequenceEqual(File.ReadAllBytes(path)), "on-disk bytes unchanged");
            Equal(true, cache.TryGet(Path.Combine(sandbox, "wrong.jpg")) == null, "path extension rejected");
            Equal(true, cache.TryGet(Path.Combine(sandbox, "missing.png")) == null, "missing file rejected");
            Equal(1, loads, "rejected paths do not decode");
            string huge = Path.Combine(sandbox, "huge.png"); File.WriteAllBytes(huge, fileBytes);
            width = 513;
            Equal(true, cache.TryGet(huge) == null, "oversized dimensions rejected");
            Equal(1, disposals, "oversized texture disposed");
            Equal(1, reads, "dimensions checked before readback");
            width = source.Length;
            string bad = Path.Combine(sandbox, "upload-failure.png"); File.WriteAllBytes(bad, fileBytes);
            failUpload = true;
            Equal(true, cache.TryGet(bad) == null, "conversion upload failure not cached");
            Equal(2, disposals, "failed conversion texture disposed");
            failUpload = false; failRead = true;
            string unreadable = Path.Combine(sandbox, "read-failure.png"); File.WriteAllBytes(unreadable, fileBytes);
            Equal(true, cache.TryGet(unreadable) == null, "readback failure not cached");
            Equal(3, disposals, "failed readback texture disposed");
            Equal(1, cache.GetDebugSnapshot().TextureCount, "only successfully converted texture published");
            cache.Clear();
            Equal(4, disposals, "cached texture disposed on clear");

            // Nonzero principal axis, including the exact alpha threshold: RGB
            // conversion must not change which pixels contribute to metadata.
            var measure = typeof(RuntimeSpriteCache).GetMethod("MeasureLocalForwardRadians", BindingFlags.NonPublic | BindingFlags.Static)!;
            var straightMask = new Color[9 * 17];
            for (int y = 1; y < 16; y++) straightMask[y * 9 + 4] = new Color(203, 101, 57, y % 2 == 0 ? 8 : 128);
            straightMask[0] = new Color(255, 255, 255, 7);
            var convertedMask = straightMask.Select(c => new Color(c.R * c.A / 255, c.G * c.A / 255, c.B * c.A / 255, c.A)).ToArray();
            float before = (float)measure.Invoke(null, new object[] { straightMask, 9, 17 })!;
            float after = (float)measure.Invoke(null, new object[] { convertedMask, 9, 17 })!;
            Equal(true, Math.Abs(before) > 1f, "nontrivial vertical PCA control");
            Equal(before, after, "RGB conversion preserves alpha-only PCA");
        }
        finally
        {
            cache.Clear();
            foreach (var hook in dataHooks) hook.Dispose();
            Terraria.Main.graphics = oldGraphics;
            Terraria.Main.dedServ = oldServer;
            Directory.Delete(sandbox, true);
        }
    }
}
