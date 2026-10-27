using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using InfiniCrafterLocal;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using ReLogic.Content;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Core;

// This is an isolated, one-process headless loader, not a full game client.
// The mod code is in its own production assembly, separate from test fixtures.
internal sealed class WNativeLoader : IDisposable
{
    private const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    internal Mod Mod { get; }
    internal int ContentCount { get; }
    internal Mod? AdditionalMod { get; }
    internal string[] MissingIfcDependencies { get; }
    private WNativeLoader(Mod mod, Mod? additional, string[] missing) { Mod = mod; AdditionalMod = additional; ContentCount = mod.GetContent().Count(); MissingIfcDependencies = missing; }

    internal static WNativeLoader Bootstrap(string sandbox, string sourceRoot, string? extraAssembly = null, string? extraRoot = null)
    {
        string buildFile = Path.Combine(sourceRoot, "build.txt");
        string translations = Path.Combine(sourceRoot, "Localization");
        if (!File.Exists(buildFile) || !Directory.Exists(translations))
            throw new DirectoryNotFoundException("Native loader needs build.txt and Localization in the IFC source root");
        if (typeof(InfiniCrafterLocalMod).Assembly == typeof(EngineRuntimeChecks).Assembly)
            throw new InvalidOperationException("IFC production assembly must be separate from the workbench fixture assembly");
        if (ModLoader.Mods.Length != 0)
            throw new InvalidOperationException("Native loader requires a fresh isolated process");

        Terraria.Program.SavePath = sandbox;
        Main.dedServ = true;
        Main.netMode = 0;
        Main.rand = new Terraria.Utilities.UnifiedRandom(1);
        for (int i = 0; i < Main.player.Length; i++) Main.player[i] ??= new Player();
        ContentSamples.Initialize(); // vanilla samples before mod registration
        typeof(Main).GetMethod("Initialize_TileAndNPCData1", Any)!.Invoke(null, null);
        Terraria.ObjectData.TileObjectData.Initialize();
        TileEntity.InitializeAll();

        Type modType = typeof(Mod);
        var mod = new InfiniCrafterLocalMod();
        PrepareSourceMod(mod, typeof(InfiniCrafterLocalMod).Assembly, sourceRoot, sandbox, requireAssets: true);
        Mod? additional = null;
        if ((extraAssembly is null) != (extraRoot is null))
            throw new ArgumentException("Extra mod assembly and source root must be supplied together");
        if (extraAssembly is not null) {
            string path = Path.GetFullPath(extraAssembly);
            var assembly = Assembly.LoadFrom(path);
            if (assembly == typeof(EngineRuntimeChecks).Assembly || assembly == typeof(InfiniCrafterLocalMod).Assembly || assembly == typeof(Mod).Assembly)
                throw new InvalidOperationException("Extra content must come from a distinct mod assembly");
            var candidates = assembly.GetTypes().Where(t => !t.IsAbstract && !t.ContainsGenericParameters && typeof(Mod).IsAssignableFrom(t)).ToArray();
            if (candidates.Length != 1) throw new InvalidDataException("Extra assembly must define exactly one concrete Mod class");
            additional = (Mod)Activator.CreateInstance(candidates[0], nonPublic: true)!;
            PrepareSourceMod(additional, assembly, Path.GetFullPath(extraRoot!), sandbox, requireAssets: false);
        }

        // Match tML's built-in first-mod ordering. Do not hand-pick any global,
        // system, projectile, player or item classes from a production mod.
        Type coreType = typeof(Mod).Assembly.GetType("Terraria.ModLoader.Default.ModLoaderMod", throwOnError: true)!;
        var core = (Mod)Activator.CreateInstance(coreType, nonPublic: true)!;
        modType.GetProperty("Assets", Any)!.SetValue(core, new AssetRepository(new AssetReaderCollection(), new[] { core.CreateDefaultContentSource() }));
        var registry = (IDictionary<string, Mod>)typeof(ModLoader).GetField("modsByName", Any)!.GetValue(null)!;
        var mods = additional is null ? new[] { core, mod } : new[] { core, mod, additional };
        foreach (Mod loaded in mods) registry.Add(loaded.Name, loaded);
        Type buildPropertiesType = typeof(TmodFile).Assembly.GetType("Terraria.ModLoader.Core.BuildProperties", throwOnError: true)!;
        object ifcProperties = buildPropertiesType.GetMethod("ReadBuildFile", Any)!.Invoke(null, new object[] { sourceRoot })!;
        var ifcDependencies = (IEnumerable<string>)buildPropertiesType.GetMethod("RefNames", Any)!.Invoke(ifcProperties, new object[] { false })!;
        string[] missingIfcDependencies = ifcDependencies.Where(name => !registry.ContainsKey(name)).ToArray();
        if (additional is not null) {
            object properties = buildPropertiesType.GetMethod("ReadBuildFile", Any)!.Invoke(null, new object[] { Path.GetFullPath(extraRoot!) })!;
            // CLR-loaded assemblies do not receive tML ModLoadContext's
            // conditional type filtering. Refuse missing weak references and
            // ExtendsFromMod requirements instead of silently loading types
            // which tML would have omitted.
            var dependencies = (IEnumerable<string>)buildPropertiesType.GetMethod("RefNames", Any)!.Invoke(properties, new object[] { true })!;
            var conditional = additional.Code.GetTypes()
                .SelectMany(type => type.GetCustomAttributes<ExtendsFromModAttribute>(inherit: true))
                .SelectMany(attribute => attribute.Names);
            string[] missing = dependencies.Concat(conditional).Where(name => !registry.ContainsKey(name)).Distinct(StringComparer.Ordinal).ToArray();
            if (missing.Length != 0) throw new NotSupportedException("Extra mod dependencies not loaded: " + string.Join(", ", missing));
        }
        typeof(ModLoader).GetProperty("Mods", Any)!.SetValue(null, mods);
        foreach (Mod loading in mods) {
            ContentInstance.Register(loading);
            modType.GetField("loading", Any)!.SetValue(loading, true);
            modType.GetMethod("AutoloadConfig", Any)!.Invoke(loading, null);
            modType.GetMethod("Autoload", Any)!.Invoke(loading, null);
            loading.Load();
            typeof(SystemLoader).GetMethod("OnModLoad", Any)!.Invoke(null, new object[] { loading });
            typeof(SystemLoader).GetMethod("EnsureResizeArraysAttributeStaticCtorsRun", Any)!.Invoke(null, new object[] { loading });
            modType.GetField("loading", Any)!.SetValue(loading, false);
        }
        typeof(Mod).Assembly.GetType("Terraria.ModLoader.ContentCache", throwOnError: true)!
            .GetField("contentLoadingFinished", Any)!.SetValue(null, true);

        // Terraria's base initialization normally runs before ModContent.Load.
        // Its early class constructors keep native SetFactory reinitialization
        // from creating duplicate factories in a headless process.
        foreach (Type nested in typeof(SetFactory).Assembly.GetTypes()
            .Where(t => t.FullName?.StartsWith("Terraria.ID.", StringComparison.Ordinal) == true && t.Name == "Sets")
            .OrderBy(t => t.FullName, StringComparer.Ordinal))
            RuntimeHelpers.RunClassConstructor(nested.TypeHandle);
        Main.SceneMetrics = new SceneMetrics();
        FieldInfo pylonField = typeof(Main).GetField("PylonSystem", Any)!;
        if (pylonField.GetValue(null) is null) pylonField.SetValue(null, Activator.CreateInstance(pylonField.FieldType));
        object pylon = pylonField.GetValue(null)!;
        FieldInfo metricsField = pylon.GetType().GetField("_sceneMetrics", Any)!;
        if (metricsField.GetValue(pylon) is null) metricsField.SetValue(pylon, new SceneMetrics());
        typeof(Main).GetField("ShopHelper", Any)!.SetValue(null, new Terraria.GameContent.ShopHelper());
        typeof(WorldGen).GetField("TownManager", Any)!.SetValue(null, new Terraria.GameContent.TownRoomManager());
        Main.instance = (Main)RuntimeHelpers.GetUninitializedObject(typeof(Main));
        FieldInfo renderTargets = typeof(Main).GetField("ContentThatNeedsRenderTargets", Any)!;
        if (renderTargets.GetValue(null) is null) renderTargets.SetValue(null, Activator.CreateInstance(renderTargets.FieldType));
        typeof(ModContent).GetMethod("ResizeArrays", Any)!.Invoke(null, new object[] { false });
        foreach (Mod loaded in mods) modType.GetMethod("SetupContent", Any)!.Invoke(loaded, null);
        ContentSamples.Initialize(); // samples for registered content, before loader FinishSetup
        foreach (Type loader in new[] { typeof(TileLoader), typeof(BuffLoader), typeof(BiomeConversionLoader) })
            loader.GetMethod("PostSetupContent", Any)!.Invoke(null, null);
        foreach (Mod loaded in mods) {
            loaded.PostSetupContent();
            typeof(SystemLoader).GetMethod("PostSetupContent", Any)!.Invoke(null, new object[] { loaded });
        }
        foreach (Type loader in new[] { typeof(NPCLoader), typeof(ItemLoader), typeof(ProjectileLoader), typeof(BuffLoader) })
            loader.GetMethod("FinishSetup", Any)!.Invoke(null, null);
        return new WNativeLoader(mod, additional, missingIfcDependencies);
    }

    private static void PrepareSourceMod(Mod mod, Assembly assembly, string root, string sandbox, bool requireAssets)
    {
        string buildFile = Path.Combine(root, "build.txt");
        if (!File.Exists(buildFile)) throw new FileNotFoundException("Mod source build.txt missing", buildFile);
        Type modType = typeof(Mod);
        Type propertiesType = typeof(TmodFile).Assembly.GetType("Terraria.ModLoader.Core.BuildProperties", throwOnError: true)!;
        object properties = propertiesType.GetMethod("ReadBuildFile", Any)!.Invoke(null, new object[] { root })!;
        var version = (Version)propertiesType.GetField("version", Any)!.GetValue(properties)!;
        string name = assembly.GetName().Name ?? throw new InvalidDataException("Assembly has no name");
        byte[] info = (byte[])propertiesType.GetMethod("ToBytes", Any)!.Invoke(properties, null)!;
        var descriptor = (TmodFile)Activator.CreateInstance(typeof(TmodFile), Any, null,
            new object[] { Path.Combine(sandbox, "in-memory-" + name), name, version }, null)!;
        MethodInfo addFile = typeof(TmodFile).GetMethod("AddFile", Any)!;
        addFile.Invoke(descriptor, new object[] { "Info", info });
        string translations = Path.Combine(root, "Localization");
        if (Directory.Exists(translations)) foreach (string path in Directory.EnumerateFiles(translations, "*", SearchOption.AllDirectories))
            addFile.Invoke(descriptor, new object[] { "Localization/" + Path.GetRelativePath(translations, path).Replace('\\', '/'), File.ReadAllBytes(path) });
        var entries = (IDictionary)typeof(TmodFile).GetField("files", Any)!.GetValue(descriptor)!;
        FieldInfo tableField = typeof(TmodFile).GetField("fileTable", Any)!;
        Array table = Array.CreateInstance(tableField.FieldType.GetElementType()!, entries.Count);
        entries.Values.CopyTo(table, 0); tableField.SetValue(descriptor, table);
        modType.GetProperty("File", Any)!.SetValue(mod, descriptor);
        modType.GetProperty("Code", Any)!.SetValue(mod, assembly);
        string displayName = (string?)propertiesType.GetField("displayName", Any)!.GetValue(properties) ?? name;
        modType.GetProperty("DisplayName", Any)!.SetValue(mod, string.IsNullOrWhiteSpace(displayName) ? name : displayName);
        modType.GetProperty("Side", Any)!.SetValue(mod, propertiesType.GetField("side", Any)!.GetValue(properties));
        modType.GetProperty("TModLoaderVersion", Any)!.SetValue(mod, typeof(ModLoader).Assembly.GetType("Terraria.ModLoader.BuildInfo", true)!.GetField("tMLVersion", Any)!.GetValue(null));
        string assetSource = Path.Combine(root, "asset-content");
        if (!Directory.Exists(Path.Combine(assetSource, "Assets"))) {
            string original = Path.Combine(root, "Assets");
            if (requireAssets && !Directory.Exists(original)) throw new DirectoryNotFoundException("IFC Assets directory missing");
            assetSource = Path.Combine(sandbox, "asset-content", name);
            Directory.CreateDirectory(assetSource);
            if (Directory.Exists(original)) foreach (string file in Directory.EnumerateFiles(original, "*", SearchOption.AllDirectories)) {
                string destination = Path.Combine(assetSource, "Assets", Path.GetRelativePath(original, file));
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!); File.Copy(file, destination);
            }
        }
        modType.GetProperty("Assets", Any)!.SetValue(mod, new AssetRepository(new AssetReaderCollection(), new[] { new FileSystemContentSource(assetSource) }));
    }

    // Registries are process-global. The CLI runs exactly one scene per child
    // process; it does not promise to unload/reload or reuse this process.
    public void Dispose() { }
}

internal static partial class EngineRuntimeChecks
{
    internal static void CheckWorkbenchNativeLoader(string sandbox, string? probeDll = null, string? probeRoot = null, string? probeNpc = null)
    {
        string? configured = Environment.GetEnvironmentVariable("INFINI_MOD_SOURCE_ROOT");
        string root = !string.IsNullOrWhiteSpace(configured) ? Path.GetFullPath(configured) : Path.Combine(AppContext.BaseDirectory, "native-mod");
        using var loader = WNativeLoader.Bootstrap(sandbox, root, probeDll, probeRoot);
        var player = new Player();
        if (player.GetModPlayer<InfiniCraftPlayer>() is null) throw new InvalidOperationException("Native PlayerLoader did not attach InfiniCraftPlayer");
        Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs + 1).Select(_ => new NPC()).ToArray();
        int npcType = NPCID.Zombie;
        if (probeNpc is not null) {
            if (loader.AdditionalMod is null || !ModContent.TryFind<ModNPC>(probeNpc, out var nativeNpc))
                throw new InvalidDataException("Requested probe NPC is not registered: " + probeNpc);
            npcType = nativeNpc.Type;
        }
        int index = NPC.NewNPC(new EntitySource_Misc("standalone-native-loader-smoke"), 800, 700, npcType);
        if (index < 0 || index >= Terraria.Main.maxNPCs || RuntimeHitNpcGeneration.Get(Terraria.Main.npc[index]) == 0)
            throw new InvalidOperationException("Native NPC.NewNPC did not dispatch registered IFC OnSpawn");
        typeof(SystemLoader).GetMethod("PostUpdateEverything", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, null);
        Console.WriteLine(JsonSerializer.Serialize(new { status = "passed", loader.ContentCount,
            productionAssembly = loader.Mod.Code.Location, nativePlayerAttached = true, npcSpawnHook = true,
            missingIfcModDependencies = loader.MissingIfcDependencies,
            additionalMod = loader.AdditionalMod is null ? null : new { name = loader.AdditionalMod.Name,
                assembly = loader.AdditionalMod.Code.Location,
                sha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(loader.AdditionalMod.Code.Location))).ToLowerInvariant(),
                content = loader.AdditionalMod.GetContent().Select(x => x.GetType().FullName).ToArray() },
            scope = "headless tML autoload and explicit NPC spawn; not full game or graphical coverage" }));
    }
}
