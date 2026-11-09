#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed partial class InfiniDumpCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinidump";
    public override string Description => "Dump loaded Terraria/tModLoader item and projectile runtime snapshots for InfiniCrafter analysis.";

    public override string Usage => "/infinidump [textures|status|cancel]";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        string option = args.Length == 0 ? "" : args[0].ToLowerInvariant();
        if (args.Length > 1 || option is not ("" or "textures" or "status" or "cancel"))
        { caller.Reply(Usage); return; }
        if (option == "cancel") { CancelExport(notify: true); return; }
        if (activeExport is not null)
        { caller.Reply("InfiniCraft dump: " + activeExport.Progress + ". /infinidump cancel to stop."); return; }
        if (option == "status") { caller.Reply("InfiniCraft: no dump is running."); return; }

        bool textures = option == "textures";
        string dir = Path.Combine(Main.SavePath, "InfiniCrafterLocal");
        // Capture identity metadata now, but hash files only on the writer thread.
        JsonObject environment = CaptureDumpEnvironmentCore(includeFileHash: false);
        activeExport = new RuntimeDumpExport(dir, ItemLoader.ItemCount, ProjectileLoader.ProjectileCount,
            type =>
            {
                Item item = new();
                item.SetDefaults(type);
                return item.IsAir || string.IsNullOrWhiteSpace(item.Name) ? null : CaptureItemSnapshotForExport(item, textures);
            }, type => CaptureProjectileSnapshotForExport(type, textures), environment);
        nextProgressAt = DateTime.UtcNow.AddSeconds(5);
        caller.Reply("InfiniCraft dump started in small steps. /infinidump status or /infinidump cancel."
            + (textures ? " Texture diagnostics enabled; individual GPU reads may pause a frame." : " Texture diagnostics skipped; use /infinidump textures to include them."));
    }

    internal static void WriteSnapshot(TextWriter writer, int type, Func<JsonObject?> capture, JsonSerializerOptions options)
    {
        JsonObject? snapshot;
        try { snapshot = capture(); }
        catch (Exception error)
        {
            // Absence of a row must not masquerade as absence of mechanics.
            // I/O errors remain terminal; only definition capture is isolated.
            snapshot = new JsonObject { ["type"] = type, ["unavailable"] = true, ["captureError"] = error.GetType().Name };
        }
        if (snapshot is not null) writer.WriteLine(snapshot.ToJsonString(options));
    }

    // Dump rows are the same complete source observations used by live crafting.
    // Only dump-specific identity aliases, flags and graphics metrics are added here.
    internal static JsonObject CaptureItemSnapshot(Item item) => CaptureItemSnapshotForExport(item, true);

    private static JsonObject CaptureItemSnapshotForExport(Item item, bool textures)
    {
        JsonObject snapshot = GeneratorClient.ToWireItem(item);
        snapshot["type"] = item.type;
        snapshot["questItem"] = item.questItem;
        snapshot["expert"] = item.expert;
        snapshot["master"] = item.master;
        snapshot["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? RuntimeDumpTextureMetrics.TryItem(item.type) : SkippedTextureMetrics());
        if (snapshot["directProjectileRaw"] is JsonObject projectile)
            projectile["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? RuntimeDumpTextureMetrics.TryProjectile(item.shoot) : SkippedTextureMetrics());
        return snapshot;
    }

    internal static JsonObject CaptureProjectileSnapshot(int type) => CaptureProjectileSnapshotForExport(type, true);

    private static JsonObject CaptureProjectileSnapshotForExport(int type, bool textures)
    {
        object? facts = GeneratorClient.ProjectileRawSnapshot(type, 0f, "runtime_dump", null, -1);
        JsonObject snapshot = JsonSerializer.SerializeToNode(facts) as JsonObject
            ?? throw new InvalidOperationException("Projectile capture was unavailable");
        snapshot["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? RuntimeDumpTextureMetrics.TryProjectile(type) : SkippedTextureMetrics());
        return snapshot;
    }

    private static RuntimeDumpTextureMetrics SkippedTextureMetrics() => new() { unavailable = true, note = "not_requested; use /infinidump textures" };
}
