#nullable enable
using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;

// Standalone source compiled with the adapter and actual IFC/tML references by
// verify_ifc_adapter_guards.py. It does not start Terraria or register any mod.
internal static class IFCAdapterGuardChecks
{
    private static int Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "ifc-adapter-guards-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string valid = Path.Combine(root, "sprite.png");
            File.WriteAllText(valid, "content does not matter for path validation");
            string outside = Path.GetTempFileName();
            try {
                var validate = typeof(IFCWorkbenchIFCAdapter.IFCWorkbenchIFCAdapter).GetMethod("ValidateAssets", BindingFlags.NonPublic | BindingFlags.Static)
                    ?? throw new MissingMethodException("Adapter asset guard not found");
                void Check(string name, string path, bool expected, string transport = "native", string inertUrl = "") {
                    var data = GeneratedItemData.Placeholder();
                    data.Visual.SpritePath = path;
                    data.RecipeMeta.AssetTransport = transport;
                    data.Visual.SpriteUrl = inertUrl;
                    bool accepted = true;
                    try { validate.Invoke(null, new object[] { data, root }); }
                    catch (TargetInvocationException ex) when (ex.InnerException is InvalidDataException or IOException or UnauthorizedAccessException) { accepted = false; }
                    if (accepted != expected) throw new InvalidOperationException(name + " expected " + expected + ", got " + accepted);
                    Console.WriteLine(name + ": PASS");
                }
                Check("sandbox-asset", valid, true);
                Check("outside-sandbox", outside, false);
                Check("relative-path", "sprite.png", false);
                Check("missing-path", Path.Combine(root, "missing.png"), false);
                Check("http-transport", valid, false, "http");
                Check("inert-sprite-url", valid, true, "native", "https://example.invalid/sprite.png");
                string link = Path.Combine(root, "link.png");
                try {
                    File.CreateSymbolicLink(link, valid);
                    Check("symlink", link, false);
                } catch (UnauthorizedAccessException) {
                    Console.WriteLine("symlink: SKIP (creation not permitted)");
                } catch (PlatformNotSupportedException) {
                    Console.WriteLine("symlink: SKIP (unsupported by platform)");
                } catch (IOException) {
                    Console.WriteLine("symlink: SKIP (unsupported by filesystem)");
                }
            } finally { File.Delete(outside); }
            return 0;
        } finally { Directory.Delete(root, recursive: true); }
    }
}
