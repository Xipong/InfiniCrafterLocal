using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;

// Loads the pinned community NPC artwork and calls the real native NPC draw.
// The controlled zombie's gameplay/AI remain those of the workbench scene.
internal sealed class WNativeZombieRender : IDisposable
{
    const string PinnedSha256 = "7fc248f3b3a3c4ea8ea0acd056b5794646f4117dd11e005a3bc132ff3d19b482";
    readonly NPC npc;
    readonly AssetRepository assets;
    readonly Asset<Texture2D> texture;
    readonly Asset<Texture2D> previous;
    bool disposed;
    public JsonObject Report { get; }
    public JsonObject Frame { get; private set; } = new();

    public WNativeZombieRender(WorkbenchGraphicsContext graphics, NPC npc, string assetRoot)
    {
        if (npc.type != NPCID.Zombie) throw new ArgumentException("Native zombie rendering requires a Zombie target");
        this.npc = npc;
        string path = Path.GetFullPath(Path.Combine(assetRoot, "Images", "NPC_3.png"));
        for (FileSystemInfo? part = new FileInfo(path); part is not null; part = part is FileInfo f ? f.Directory : ((DirectoryInfo)part).Parent)
            if (part.LinkTarget is not null) throw new InvalidDataException("Zombie asset symlink refused: " + path);
        if (!File.Exists(path) || new FileInfo(path).Length != 1436)
            throw new InvalidDataException("Missing pinned community zombie asset " + path + "; fetch it using fetch_player_assets.py --include-zombie");
        byte[] bytes = File.ReadAllBytes(path);
        string digest = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        if (digest != PinnedSha256) throw new InvalidDataException("Zombie asset differs from pinned community source: " + path);
        var readers = new AssetReaderCollection();
        readers.RegisterReader(new PngReader(graphics.Device), ".png");
        assets = new AssetRepository(readers);
        try {
            using var stream = new MemoryStream(bytes, writable: false);
            texture = assets.CreateUntracked<Texture2D>(stream, "NPC_3.png", AssetRequestMode.ImmediateLoad);
            if (texture.State != AssetState.Loaded || texture.Value.Width != 38 || texture.Value.Height != 144)
                throw new InvalidDataException("Pinned zombie texture dimensions must be 38x144");
            previous = TextureAssets.Npc[NPCID.Zombie];
            TextureAssets.Npc[NPCID.Zombie] = texture;
        } catch { assets.Dispose(); throw; }
        Report = new JsonObject { ["entrypoint"] = "Main.DrawNPC -> Main.DrawNPCDirect -> NPCLoader.PreDraw/PostDraw (original)",
            ["animation"] = "NPC.FindFrame after controlled NPC.UpdateNPC", ["npcSlot"] = npc.whoAmI,
            ["npcType"] = npc.type, ["controlledWidth"] = npc.width, ["controlledHeight"] = npc.height,
            ["initialLife"] = npc.life, ["aiStyle"] = npc.aiStyle,
            ["sourcePath"] = path, ["sourceCommit"] = "c835594415e31ed88734dc778661014b48ffb648",
            ["source"] = "Pinned community Terraria 1.4.4.9 source PNG; official byte identity not verified",
            ["sha256"] = digest,
            ["width"] = texture.Value.Width, ["height"] = texture.Value.Height,
            ["scope"] = "Controlled zombie with NPC AI disabled; original NPC draw and frame logic, not world or NPC AI parity" };
    }

    public void UpdateFrame()
    {
        if (!npc.active) return;
        bool previousDedicated = Main.dedServ;
        Main.dedServ = false;
        try { npc.FindFrame(); }
        finally { Main.dedServ = previousDedicated; }
    }

    public void Draw()
    {
        if (!npc.active) { Frame = new JsonObject { ["active"] = false, ["drawCount"] = 0 }; return; }
        Main.spriteBatch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp,
            DepthStencilState.None, Main.Rasterizer, null, Main.GameViewMatrix.TransformationMatrix);
        JsonArray draws;
        try { draws = WNativeVisualGeometry.Capture(() => Main.instance.DrawNPC(npc.whoAmI, false)); }
        finally { Main.spriteBatch.End(); }
        Frame = new JsonObject { ["active"] = true, ["drawCount"] = draws.Count, ["geometry"] = draws,
            ["frameX"] = npc.frame.X, ["frameY"] = npc.frame.Y, ["frameWidth"] = npc.frame.Width,
            ["frameHeight"] = npc.frame.Height, ["life"] = npc.life };
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        TextureAssets.Npc[NPCID.Zombie] = previous;
        texture.Dispose();
        assets.Dispose();
    }
}
