using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using ICSharpCode.Decompiler.CSharp;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void BundledDecompilerUsesOfficialResourcePackaging()
    {
        const string library = "ICSharpCode.Decompiler";
        const string expectedSha256 = "d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0";
        const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
        string source = Path.Combine("mod", "InfiniCrafterLocal", "lib");
        byte[] binary = File.ReadAllBytes(Path.Combine(source, library + ".dll"));
        byte[] notice = File.ReadAllBytes(Path.Combine(source, library + ".LICENSE.txt"));
        Equal(expectedSha256, Convert.ToHexString(SHA256.HashData(binary)).ToLowerInvariant(), "official pinned decompiler DLL");
        Equal(new Version(8, 2, 0, 7535), typeof(CSharpDecompiler).Assembly.GetName().Version!, "linked decompiler assembly version");
        Equal(true, File.ReadAllBytes(typeof(CSharpDecompiler).Assembly.Location).SequenceEqual(binary), "runtime resolves the shipped managed DLL");
        Equal(true, File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, library + ".LICENSE.txt")).SequenceEqual(notice), "build output ships the managed dependency notices");

        string directory = Directory.CreateTempSubdirectory("ifc-decompiler-package-").FullName;
        FieldInfo? activeField = null;
        bool wasActivelyModding = false;
        try
        {
            string fixture = Path.Combine(directory, "ManagedDependencyFixture");
            Directory.CreateDirectory(Path.Combine(fixture, "lib"));
            File.WriteAllText(Path.Combine(fixture, "build.txt"), "version = 0.1\ndllReferences = " + library + "\n");
            File.WriteAllBytes(Path.Combine(fixture, "lib", library + ".dll"), binary);
            File.WriteAllBytes(Path.Combine(fixture, "lib", library + ".LICENSE.txt"), notice);

            // Exercise the shipped tML resource packager directly. This is an
            // isolated resource fixture, not a playable mod or game startup.
            Assembly tml = typeof(ModLoader).Assembly;
            Type compileType = tml.GetType("Terraria.ModLoader.Core.ModCompile", true)!;
            var activelyModding = compileType.GetField("activelyModding", all)!;
            wasActivelyModding = (bool)activelyModding.GetValue(null)!;
            activeField = activelyModding;
            Type propertiesType = tml.GetType("Terraria.ModLoader.Core.BuildProperties", true)!;
            Type fileType = tml.GetType("Terraria.ModLoader.Core.TmodFile", true)!;
            object properties = propertiesType.GetMethod("ReadBuildFile", all)!.Invoke(null, new object[] { fixture })!;
            object file = Activator.CreateInstance(fileType, all, null,
                new object[] { Path.Combine(directory, "ManagedDependencyFixture.tmod"), "ManagedDependencyFixture", new Version(0, 1) }, null)!;
            object building = Activator.CreateInstance(compileType.GetNestedType("BuildingMod", all)!, all, null,
                new[] { file, properties, fixture }, null)!;
            object status = Activator.CreateInstance(compileType.GetNestedType("ConsoleBuildStatus", all)!, nonPublic: true)!;
            object compiler = Activator.CreateInstance(compileType, all, null, new[] { status }, null)!;
            compileType.GetMethod("PackageMod", all)!.Invoke(compiler, new[] { building });
            fileType.GetMethod("Save", all)!.Invoke(file, null);
            object packed = Activator.CreateInstance(fileType, all, null,
                new object?[] { Path.Combine(directory, "ManagedDependencyFixture.tmod"), null, null }, null)!;
            using var lease = (IDisposable)fileType.GetMethod("Open", all)!.Invoke(packed, null)!;
            Equal(true, (bool)fileType.GetMethod("VerifyHash", all)!.Invoke(packed, null)!, "official .tmod payload hash");
            foreach (var (name, expected) in new[] { (library + ".dll", binary), (library + ".LICENSE.txt", notice) })
            {
                var actual = (byte[])fileType.GetMethod("GetBytes", all, null, new[] { typeof(string) }, null)!
                    .Invoke(packed, new object[] { "lib/" + name })!;
                Equal(true, actual.SequenceEqual(expected), "official packager preserves exact " + name);
            }
            object loaded = propertiesType.GetMethod("ReadModFile", all)!.Invoke(null, new[] { packed })!;
            var refs = (string[])propertiesType.GetField("dllReferences", all)!.GetValue(loaded)!;
            Equal(library, string.Join(",", refs), "packaged Info declares the managed loader dependency");
        }
        finally
        {
            activeField?.SetValue(null, wasActivelyModding);
            Directory.Delete(directory, recursive: true);
        }
    }
}
