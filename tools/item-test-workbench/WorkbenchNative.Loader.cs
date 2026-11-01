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
    internal IReadOnlyList<Mod> AdditionalMods { get; }
    internal Mod? AdditionalMod => AdditionalMods.LastOrDefault();
    internal string[] MissingIfcDependencies { get; }
    internal sealed record ModInput(string AssemblyPath, string SourceRoot, string? TmodPath = null);
    private sealed record Source(Mod Mod, string[] Dependencies, bool IsIfc);
    private readonly IReadOnlyList<IDisposable> archiveHandles;
    private WNativeLoader(Mod mod, IReadOnlyList<Mod> additional, string[] missing, IReadOnlyList<IDisposable> handles) { Mod = mod; AdditionalMods = additional; ContentCount = mod.GetContent().Count(); MissingIfcDependencies = missing; archiveHandles = handles; }

    internal static WNativeLoader Bootstrap(string sandbox, string sourceRoot, IReadOnlyList<ModInput>? extraMods = null)
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
        // LocalizationLoader.Autoload adds mod GameTips to this real engine
        // collection. Main's normal initialization is absent in this process.
        FieldInfo gameTips = typeof(Main).GetField("gameTips", Any)!;
        if (gameTips.GetValue(null) is null) gameTips.SetValue(null, Activator.CreateInstance(gameTips.FieldType));
        for (int i = 0; i < Main.player.Length; i++) Main.player[i] ??= new Player();
        ContentSamples.Initialize(); // vanilla samples before mod registration
        typeof(Main).GetMethod("Initialize_TileAndNPCData1", Any)!.Invoke(null, null);
        Terraria.ObjectData.TileObjectData.Initialize();
        TileEntity.InitializeAll();

        Type modType = typeof(Mod);
        var mod = new InfiniCrafterLocalMod();
        PrepareSourceMod(mod, typeof(InfiniCrafterLocalMod).Assembly, sourceRoot, sandbox, requireAssets: true);
        // Load every supplied assembly before reflecting its types so CLR
        // references among different source directories resolve to the exact
        // explicitly supplied assemblies. tML's conditional type filtering is
        // not emulated: missing declared/conditional dependencies still refuse.
        // Keep genuine archives open for Mod.GetFileBytes/GetFileStream throughout
        // the run. Only the unmodified managed code is staged for LoadFrom.
        var archiveHandles = new List<IDisposable>();
        try {
        var archiveFiles = new Dictionary<string, (TmodFile File, object Properties)>(StringComparer.OrdinalIgnoreCase);
        var resolved = new List<ModInput>();
        var archivePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        Type archivePropertiesType = typeof(TmodFile).Assembly.GetType("Terraria.ModLoader.Core.BuildProperties", true)!;
        foreach (var input in extraMods ?? Array.Empty<ModInput>()) {
            if (input.TmodPath is null) { resolved.Add(input); continue; }
            string archivePath = Path.GetFullPath(input.TmodPath);
            if (!archivePaths.Add(archivePath)) throw new InvalidDataException("Duplicate extra mod archive: " + archivePath);
            // tML automatically upgrades pre-0.11 archives in place on Open.
            // Reject those first: a workbench run must not rewrite input files.
            using (var header = new BinaryReader(File.OpenRead(archivePath))) {
                if (System.Text.Encoding.ASCII.GetString(header.ReadBytes(4)) != "TMOD" ||
                    !Version.TryParse(header.ReadString(), out Version? archiveVersion) || archiveVersion < new Version(0, 11))
                    throw new NotSupportedException("Invalid or legacy tmod archive (automatic upgrades are disabled): " + archivePath);
            }
            var file = (TmodFile)Activator.CreateInstance(typeof(TmodFile), Any, null, new object?[] { archivePath, null, null }, null)!;
            archiveHandles.Add(file.Open());
            if (!(bool)typeof(TmodFile).GetMethod("VerifyHash", Any)!.Invoke(file, null)!)
                throw new InvalidDataException("Archive payload hash mismatch: " + archivePath);
            object properties = archivePropertiesType.GetMethod("ReadModFile", Any)!.Invoke(null, new object[] { file })!;
            string name = file.Name;
            if (string.IsNullOrWhiteSpace(name) || name is "." or ".." || Path.GetFileName(name) != name || name.Contains('/') || name.Contains('\\') || name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                throw new InvalidDataException("Invalid mod name in archive: " + name);
            if (!archiveFiles.TryAdd(name, (file, properties))) throw new InvalidDataException("Duplicate extra mod name: " + name);
            // Loading embedded arbitrary DLL references requires tML's isolated
            // assembly contexts. Refuse instead of substituting global assemblies.
            var libs = (string[])archivePropertiesType.GetField("dllReferences", Any)!.GetValue(properties)!;
            if (libs.Length != 0) throw new NotSupportedException("Archive mod declares embedded DLL references; isolated mod assembly contexts are not implemented: " + name);
            byte[] bytes = file.GetBytes(name + ".dll") ?? throw new InvalidDataException("Archive does not contain its original mod DLL: " + name);
            string stage = Path.Combine(sandbox, "archive-assemblies", name);
            Directory.CreateDirectory(stage);
            string dllPath = Path.Combine(stage, name + ".dll");
            File.WriteAllBytes(dllPath, bytes);
            resolved.Add(new ModInput(dllPath, "", archivePath));
        }
        var extra = new List<(ModInput Input, Assembly Assembly)>();
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var assemblyNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var input in resolved) {
            string path = Path.GetFullPath(input.AssemblyPath);
            if (!File.Exists(path)) throw new FileNotFoundException("Extra mod assembly missing", path);
            if (!paths.Add(path)) throw new InvalidDataException("Duplicate extra mod assembly: " + path);
            string name = AssemblyName.GetAssemblyName(path).Name ?? throw new InvalidDataException("Extra assembly has no name");
            if (!assemblyNames.Add(name)) throw new InvalidDataException("Duplicate extra mod assembly name: " + name);
            if (input.TmodPath is not null && !archiveFiles.ContainsKey(name))
                throw new InvalidDataException("Archive name and embedded assembly name differ: " + name);
        }
        foreach (var input in resolved) {
            string path = Path.GetFullPath(input.AssemblyPath);
            var assembly = Assembly.LoadFrom(path);
            if (assembly == typeof(EngineRuntimeChecks).Assembly || assembly == typeof(InfiniCrafterLocalMod).Assembly || assembly == typeof(Mod).Assembly)
                throw new InvalidOperationException("Extra content must come from a distinct mod assembly");
            if (!string.Equals(Path.GetFullPath(assembly.Location), path, StringComparison.Ordinal))
                throw new InvalidOperationException("CLR resolved a different assembly than supplied: " + path);
            extra.Add((input, assembly));
        }
        var additional = new List<Mod>();
        foreach (var (input, assembly) in extra) {
            var candidates = assembly.GetTypes().Where(t => !t.IsAbstract && !t.ContainsGenericParameters && typeof(Mod).IsAssignableFrom(t)).ToArray();
            if (candidates.Length != 1) throw new InvalidDataException("Extra assembly must define exactly one concrete Mod class: " + assembly.GetName().Name);
            var instance = (Mod)Activator.CreateInstance(candidates[0], nonPublic: true)!;
            if (input.TmodPath is not null) {
                var archive = archiveFiles[assembly.GetName().Name!];
                PrepareArchiveMod(instance, assembly, archive.File, archive.Properties, archivePropertiesType);
            } else {
                PrepareSourceMod(instance, assembly, Path.GetFullPath(input.SourceRoot), sandbox, requireAssets: false);
            }
            additional.Add(instance);
        }

        // Register every actual mod before calling any Load hook, then run
        // hooks in dependency order. This avoids substituting missing mods.
        Type coreType = typeof(Mod).Assembly.GetType("Terraria.ModLoader.Default.ModLoaderMod", throwOnError: true)!;
        var core = (Mod)Activator.CreateInstance(coreType, nonPublic: true)!;
        modType.GetProperty("Assets", Any)!.SetValue(core, new AssetRepository(new AssetReaderCollection(), new[] { core.CreateDefaultContentSource() }));
        var registry = (IDictionary<string, Mod>)typeof(ModLoader).GetField("modsByName", Any)!.GetValue(null)!;
        Type buildPropertiesType = typeof(TmodFile).Assembly.GetType("Terraria.ModLoader.Core.BuildProperties", throwOnError: true)!;
        string[] Dependencies(string root, bool includeWeak) {
            object properties = buildPropertiesType.GetMethod("ReadBuildFile", Any)!.Invoke(null, new object[] { root })!;
            return ((IEnumerable<string>)buildPropertiesType.GetMethod("RefNames", Any)!.Invoke(properties, new object[] { includeWeak })!).ToArray();
        }
        var all = new List<Source> { new(mod, Dependencies(sourceRoot, false), true) };
        for (int i = 0; i < additional.Count; i++) {
            Mod current = additional[i];
            var conditional = current.Code.GetTypes()
                .SelectMany(type => type.GetCustomAttributes<ExtendsFromModAttribute>(inherit: true))
                .SelectMany(attribute => attribute.Names);
            string[] dependencies = extra[i].Input.TmodPath is null
                ? Dependencies(Path.GetFullPath(extra[i].Input.SourceRoot), true)
                : ((IEnumerable<string>)buildPropertiesType.GetMethod("RefNames", Any)!.Invoke(archiveFiles[current.Name].Properties, new object[] { true })!).ToArray();
            all.Add(new Source(current, dependencies.Concat(conditional).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(), false));
        }
        var byName = new Dictionary<string, Source>(StringComparer.OrdinalIgnoreCase);
        foreach (Source source in all) {
            if (string.Equals(source.Mod.Name, core.Name, StringComparison.OrdinalIgnoreCase) || !byName.TryAdd(source.Mod.Name, source))
                throw new InvalidDataException("Duplicate native mod name: " + source.Mod.Name);
        }
        string[] missingIfcDependencies = all[0].Dependencies.Where(name => !byName.ContainsKey(name) && !string.Equals(name, core.Name, StringComparison.OrdinalIgnoreCase)).ToArray();
        foreach (Source source in all.Where(s => !s.IsIfc)) {
            string[] missing = source.Dependencies.Where(name => !byName.ContainsKey(name) && !string.Equals(name, core.Name, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (missing.Length != 0) throw new NotSupportedException("Extra mod dependencies not loaded: " + string.Join(", ", missing));
        }
        var sorted = new List<Mod>(); var state = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        void Visit(Source source) {
            if (state.TryGetValue(source.Mod.Name, out int mark)) {
                if (mark == 1) throw new InvalidDataException("Cyclic native mod dependencies: " + source.Mod.Name);
                return;
            }
            state[source.Mod.Name] = 1;
            foreach (string name in source.Dependencies)
                if (byName.TryGetValue(name, out Source? dependency)) Visit(dependency);
            state[source.Mod.Name] = 2; sorted.Add(source.Mod);
        }
        foreach (Source source in all) Visit(source);
        var mods = new[] { core }.Concat(sorted).ToArray();
        foreach (Mod loaded in mods) registry.Add(loaded.Name, loaded);
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
        return new WNativeLoader(mod, sorted.Where(m => !ReferenceEquals(m, mod)).ToArray(), missingIfcDependencies, archiveHandles);
        } catch {
            foreach (var handle in archiveHandles.AsEnumerable().Reverse()) handle.Dispose();
            throw;
        }
    }

    private static void PrepareArchiveMod(Mod mod, Assembly assembly, TmodFile file, object properties, Type propertiesType)
    {
        Type modType = typeof(Mod);
        modType.GetProperty("File", Any)!.SetValue(mod, file);
        modType.GetProperty("Code", Any)!.SetValue(mod, assembly);
        string displayName = (string?)propertiesType.GetField("displayName", Any)!.GetValue(properties) ?? file.Name;
        modType.GetProperty("DisplayName", Any)!.SetValue(mod, string.IsNullOrWhiteSpace(displayName) ? file.Name : displayName);
        modType.GetProperty("Side", Any)!.SetValue(mod, propertiesType.GetField("side", Any)!.GetValue(properties));
        modType.GetProperty("TModLoaderVersion", Any)!.SetValue(mod, propertiesType.GetField("buildVersion", Any)!.GetValue(properties));
        // In headless mode tML's source deliberately exposes no client assets.
        modType.GetProperty("Assets", Any)!.SetValue(mod, new AssetRepository(new AssetReaderCollection(), new[] { mod.CreateDefaultContentSource() }));
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
        // External mods keep their original content paths (e.g. Items/,
        // Projectiles/, Effects/), not just a copied Assets/ subtree. This is a
        // source repository, not a claim that tML's .tmod packing is replicated.
        string assetSource = requireAssets ? Path.Combine(root, "asset-content") : root;
        if (requireAssets && !Directory.Exists(Path.Combine(assetSource, "Assets"))) {
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
    public void Dispose() { foreach (var handle in archiveHandles.Reverse()) handle.Dispose(); }
}

internal static partial class EngineRuntimeChecks
{
    internal static void CheckWorkbenchNativeLoader(string sandbox, IReadOnlyList<WNativeLoader.ModInput> mods, string? probeNpc = null)
    {
        string? configured = Environment.GetEnvironmentVariable("INFINI_MOD_SOURCE_ROOT");
        string root = !string.IsNullOrWhiteSpace(configured) ? Path.GetFullPath(configured) : Path.Combine(AppContext.BaseDirectory, "native-mod");
        using var loader = WNativeLoader.Bootstrap(sandbox, root, mods);
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
            additionalMods = loader.AdditionalMods.Select(m => new { name = m.Name, assembly = m.Code.Location }).ToArray(),
            additionalMod = loader.AdditionalMod is null ? null : new { name = loader.AdditionalMod.Name,
                assembly = loader.AdditionalMod.Code.Location,
                sha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(loader.AdditionalMod.Code.Location))).ToLowerInvariant(),
                content = loader.AdditionalMod.GetContent().Select(x => x.GetType().FullName).ToArray() },
            limitations = new[] { "Dependency versions are not validated", "Source-root mods use reconstructed Mod.File; archive inputs retain original Mod.File", "Asset readers and client lifecycle are incomplete" },
            scope = "headless tML autoload and explicit NPC spawn; not full game or graphical coverage" }));
    }
}
