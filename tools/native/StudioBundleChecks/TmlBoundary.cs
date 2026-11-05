namespace Terraria.ModLoader
{

    // The .tmod reader and mod-owned asset service are test boundaries. Installation,
    // image-root resolution and process ownership execute linked production code.
    public sealed class Mod
    {
        private readonly string _resourceRoot;

        public Mod(string resourceRoot) => _resourceRoot = resourceRoot;

        public bool FileExists(string name) => File.Exists(Path.Combine(_resourceRoot, name));

        public Stream GetFileStream(string name, bool newFileStream = false) =>
            File.OpenRead(Path.Combine(_resourceRoot, name));
    }

}

namespace InfiniCrafterLocal
{
    internal static class InfiniCrafterLocalMod
    {
        internal static Common.Services.GeneratedAssetSyncService? AssetSync { get; set; }
    }
}

namespace InfiniCrafterLocal.Common.Services
{
    // Studio only reads the game-selected root. Asset transport and PNG validation
    // are exercised by AssetTransportChecks, not by this process lifecycle fixture.
    internal sealed class GeneratedAssetSyncService(string cacheRoot)
    {
        internal string CacheRoot { get; } = cacheRoot;
        internal const int MaxAssetBytes = 8 * 1024 * 1024;
        internal static bool IsCompletePng(byte[] bytes) =>
            throw new NotSupportedException("PNG validation is outside the Studio fixture boundary.");
    }
}
