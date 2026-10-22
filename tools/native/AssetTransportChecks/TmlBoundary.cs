// Test-only DTO and tML boundaries. No game loop, sockets, Steam, or GPU is run.
// PNG validation, request scheduling, bundle codec, queues, and file commits are
// the complete linked production GeneratedAssetSyncService implementation.
using System.Text;

namespace Terraria
{
    public static class Main
    {
        public const int maxPlayers = 255;
        public static int netMode;
        public static bool dedServ;
        public static uint GameUpdateCount;
        public static string SavePath = "";
        public static Player[] player = Enumerable.Range(0, maxPlayers).Select(_ => new Player()).ToArray();
        public static void QueueMainThreadAction(Action action) => action();
    }
    public sealed class Player { public bool active; }
}
namespace Terraria.ID
{
    public static class NetmodeID
    {
        public const int SinglePlayer = 0, MultiplayerClient = 1, Server = 2;
    }
}
namespace Terraria.ModLoader
{
    public sealed class ModPacket : BinaryWriter
    {
        internal static Action<byte[], int> OnSend = (_, _) => { };
        public ModPacket() : base(new MemoryStream(), Encoding.UTF8, leaveOpen: true) { }
        public void Send(int toClient = -1)
        {
            Flush();
            byte[] payload = ((MemoryStream)BaseStream).ToArray();
            // tML's ushort length includes its header and mod ID, absent at this
            // capture boundary. Reserve the larger five-byte envelope here.
            if (payload.Length + 5 > ushort.MaxValue) throw new InvalidDataException("oversized ModPacket");
            OnSend(payload, toClient);
        }
    }
}
namespace InfiniCrafterLocal.Common
{
    // Symbolic routing in this fixture, not a test of production packet-ID assignment.
    public static class InfiniNetPacketIds
    {
        public const byte RequestGeneratedAsset = 1, GeneratedAssetChunk = 2;
    }
}
namespace InfiniCrafterLocal.Common.Models
{
    public sealed class GeneratedItemData
    {
        public string Id { get; set; } = "probe";
        public RecipeMeta RecipeMeta { get; } = new();
        public Visual Visual { get; } = new();
        public VfxManifest VfxManifest { get; } = new();
        public RuntimeProgram RuntimeProgram { get; } = new();
    }
    public sealed class RecipeMeta
    {
        public string WorldId { get; set; } = "test-world";
        public string AssetTransport { get; set; } = "native";
        public string AssetBaseUrl { get; set; } = "";
    }
    public sealed class Visual
    {
        public string SpritePath { get; set; } = "";
        public string EquipOverlayPath { get; set; } = "";
        public string ImpactSpritePath { get; set; } = "";
    }
    public sealed class VfxAssetSpec { public string SpritePath { get; set; } = ""; }
    public sealed class VfxManifest { public VfxAssetSpec[] Assets { get; set; } = Array.Empty<VfxAssetSpec>(); }
    public sealed class RuntimeEntitySpec { public Visual Visual { get; } = new(); }
    public sealed class RuntimeProgram { public RuntimeEntitySpec[] Entities { get; set; } = Array.Empty<RuntimeEntitySpec>(); }
}
namespace InfiniCrafterLocal.Common.Services
{
    public sealed class GeneratedItemRegistryService
    {
        internal readonly Dictionary<string, Models.GeneratedItemData> Items = new(StringComparer.Ordinal);
        internal int RefreshRequests;
        public static bool IsCurrentWorldData(Models.GeneratedItemData data) => data.RecipeMeta.WorldId == "test-world";
        public bool TryGet(string id, out Models.GeneratedItemData data) => Items.TryGetValue(id, out data!);
        public void RequestOneFromServer(string itemId, bool forceAssetRetry = true, bool forceDefinitionRefresh = false)
            => RefreshRequests++;
    }
    public sealed class GeneratorClient
    {
        public string Endpoint { get; set; } = "";
        public string AssetBaseUrlForSharing() => "";
    }
    public sealed class RuntimeSpriteCache { public void Invalidate(string path) { } }
    public static class LocalHttpQuietFailure
    {
        public static void ClearAll() { }
        public static void Clear(string key) { }
        public static bool ShouldSkip(string key) => false;
        public static bool IsExpectedOffline(Exception error) => false;
        public static void Record(string key, Exception error, TimeSpan delay) { }
    }
}
namespace InfiniCrafterLocal
{
    public sealed class InfiniCrafterLocalMod
    {
        public static InfiniCrafterLocalMod Instance { get; } = new();
        public static Common.Services.GeneratorClient? Generator { get; set; }
        public static Common.Services.GeneratedItemRegistryService? GeneratedItems { get; set; }
        public static Common.Services.RuntimeSpriteCache? Sprites { get; set; }
        public Terraria.ModLoader.ModPacket GetPacket() => new();
    }
}
