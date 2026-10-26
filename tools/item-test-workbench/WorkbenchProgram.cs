using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

internal static class WorkbenchProgram
{
    public static int Main(string[] args)
    {
        string? output = null;
        string sandbox = Directory.CreateTempSubdirectory("icl-workbench-").FullName;
        try
        {
            Terraria.Program.SavePath = sandbox;
            Terraria.Main.dedServ = true;
            if (args.Length == 1 && args[0] == "--check-assertions") { EngineRuntimeChecks.CheckWorkbenchAssertions(); return 0; }
            if (args.Length == 2 && args[0] == "--write-fixtures") { EngineRuntimeChecks.WriteWorkbenchFixtures(args[1]); return 0; }
            string itemBoundary="fresh"; string? item = null, scenario = null; int? vanillaItem = null;
            for (int i = 0; i < args.Length; i += 2)
            {
                if (i + 1 >= args.Length) throw new ArgumentException("Expected --item PATH --scenario PATH --output PATH");
                switch (args[i])
                {
                    case "--item-boundary": itemBoundary=args[i+1]; break;
                    case "--item": item = args[i + 1]; break;
                    case "--vanilla-item": vanillaItem = EngineRuntimeChecks.ResolveWorkbenchVanillaItem(args[i+1]); break;
                    case "--scenario": scenario = args[i + 1]; break;
                    case "--output": output = args[i + 1]; break;
                    default: throw new ArgumentException("Unknown argument: " + args[i]);
                }
            }
            if ((item == null) == (vanillaItem == null) || scenario == null || output == null) throw new ArgumentException("Required: exactly one --item PATH or --vanilla-item ID_OR_NAME, then --scenario PATH --output PATH");
            if(vanillaItem.HasValue && itemBoundary!="fresh") throw new ArgumentException("item-boundary applies only to generated JSON input");
            Terraria.Program.SavePath = sandbox;
            Terraria.Main.dedServ = true;
            var report = EngineRuntimeChecks.RunWorkbench(item, scenario, vanillaItem, output, itemBoundary);
            Write(output, report);
            return report["status"]!.GetValue<string>() switch { "passed" => 0, "failed" => 1, _ => 2 };
        }
        catch (Exception ex)
        {
            while (ex is System.Reflection.TargetInvocationException && ex.InnerException != null) ex = ex.InnerException;
            var failure = new JsonObject { ["schemaVersion"] = 1, ["status"] = "error", ["execution"] = new JsonObject { ["backend"] = "native-projectile-update", ["fullGameParity"] = false }, ["error"] = ex.ToString(), ["snapshots"] = new JsonArray(), ["assertions"] = new JsonArray() };
            if (output != null) Write(output, failure);
            Console.Error.WriteLine(ex);
            return 2;
        }
        finally { Directory.Delete(sandbox, recursive: true); }
    }
    private static void Write(string path, JsonObject report)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, report.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }
}
