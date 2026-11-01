using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

internal static class WorkbenchProgram
{
    public static int Main(string[] args)
    {
        string? output = null;
        bool nativeLoaderScene=args.Contains("--native-loader-scene");
        string sandbox = Directory.CreateTempSubdirectory("icl-workbench-").FullName;
        try
        {
            Terraria.Program.SavePath = sandbox;
            Terraria.Main.dedServ = true;
            if (args.Length > 0 && args[0] == "--check-native-loader") {
                string? dll = null, root = null, npc = null;
                var modDlls = new List<string>(); var modRoots = new List<string>();
                for (int i = 1; i < args.Length; i += 2) {
                    if (i + 1 >= args.Length) throw new ArgumentException("Native loader probe options require a value");
                    switch (args[i]) {
                        case "--probe-dll": dll = args[i + 1]; break;
                        case "--probe-mod-root": root = args[i + 1]; break;
                        case "--probe-npc": npc = args[i + 1]; break;
                        case "--mod-dll": modDlls.Add(args[i + 1]); break;
                        case "--mod-root": modRoots.Add(args[i + 1]); break;
                        default: throw new ArgumentException("Unknown native loader probe option: " + args[i]);
                    }
                }
                EngineRuntimeChecks.CheckWorkbenchNativeLoader(sandbox, ModInputs(dll, root, modDlls, modRoots), npc); return 0;
            }
            if (args.Length == 1 && args[0] == "--check-assertions") { EngineRuntimeChecks.CheckWorkbenchAssertions(); return 0; }
            if (args.Length == 2 && args[0] == "--write-fixtures") { EngineRuntimeChecks.WriteWorkbenchFixtures(args[1]); return 0; }
            if(nativeLoaderScene) args=args.Where(a=>a!="--native-loader-scene").ToArray();
            string itemBoundary="fresh"; string? item = null, nativeItem = null, scenario = null, probeDll = null, probeRoot = null; int? vanillaItem = null;
            var additionalDlls = new List<string>(); var additionalRoots = new List<string>();
            for (int i = 0; i < args.Length; i += 2)
            {
                if (i + 1 >= args.Length) throw new ArgumentException("Expected --item PATH --scenario PATH --output PATH");
                switch (args[i])
                {
                    case "--item-boundary": itemBoundary=args[i+1]; break;
                    case "--item": item = args[i + 1]; break;
                    case "--native-item": nativeItem = args[i + 1]; break;
                    case "--vanilla-item": vanillaItem = EngineRuntimeChecks.ResolveWorkbenchVanillaItem(args[i+1]); break;
                    case "--probe-dll": probeDll = args[i+1]; break;
                    case "--probe-mod-root": probeRoot = args[i+1]; break;
                    case "--mod-dll": additionalDlls.Add(args[i+1]); break;
                    case "--mod-root": additionalRoots.Add(args[i+1]); break;
                    case "--scenario": scenario = args[i + 1]; break;
                    case "--output": output = args[i + 1]; break;
                    default: throw new ArgumentException("Unknown argument: " + args[i]);
                }
            }
            if ((item is null?0:1)+(nativeItem is null?0:1)+(vanillaItem.HasValue?1:0)!=1 || scenario == null || output == null) throw new ArgumentException("Required: exactly one --item PATH, --native-item ID_OR_MOD_NAME or --vanilla-item ID_OR_NAME, then --scenario PATH --output PATH");
            if((vanillaItem.HasValue || nativeItem is not null) && itemBoundary!="fresh") throw new ArgumentException("item-boundary applies only to generated JSON input");
            if(!nativeLoaderScene && nativeItem is not null)throw new ArgumentException("--native-item requires --native-loader-scene");
            if(!nativeLoaderScene && (probeDll is not null || probeRoot is not null || additionalDlls.Count != 0 || additionalRoots.Count != 0))throw new ArgumentException("Additional mod options require --native-loader-scene");
            var extraMods = ModInputs(probeDll, probeRoot, additionalDlls, additionalRoots);
            Terraria.Program.SavePath = sandbox;
            Terraria.Main.dedServ = true;
            var report = nativeLoaderScene?EngineRuntimeChecks.RunWorkbenchNativeLoaderScene(item,nativeItem ?? vanillaItem?.ToString(),scenario,sandbox,itemBoundary,extraMods):EngineRuntimeChecks.RunWorkbench(item, scenario, vanillaItem, output, itemBoundary);
            Write(output, report);
            return report["status"]!.GetValue<string>() switch { "passed" => 0, "failed" => 1, _ => 2 };
        }
        catch (Exception ex)
        {
            while (ex is System.Reflection.TargetInvocationException && ex.InnerException != null) ex = ex.InnerException;
            var failure = new JsonObject { ["schemaVersion"] = 1, ["status"] = "error", ["execution"] = new JsonObject { ["backend"] = nativeLoaderScene?"standalone-tml-loader":"native-projectile-update", ["fullGameParity"] = false }, ["error"] = ex.ToString(), ["snapshots"] = new JsonArray(), ["assertions"] = new JsonArray() };
            if (output != null) Write(output, failure);
            Console.Error.WriteLine(ex);
            return 2;
        }
        finally { Directory.Delete(sandbox, recursive: true); }
    }
    private static IReadOnlyList<WNativeLoader.ModInput> ModInputs(string? dll, string? root, List<string> dlls, List<string> roots)
    {
        if ((dll is null) != (root is null)) throw new ArgumentException("--probe-dll and --probe-mod-root must be supplied together");
        if (dlls.Count != roots.Count) throw new ArgumentException("Each --mod-dll requires a corresponding --mod-root");
        var result = new List<WNativeLoader.ModInput>();
        if (dll is not null) result.Add(new WNativeLoader.ModInput(dll, root!));
        for (int i = 0; i < dlls.Count; i++) result.Add(new WNativeLoader.ModInput(dlls[i], roots[i]));
        return result;
    }
    private static void Write(string path, JsonObject report)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, report.ToJsonString());
    }
}
