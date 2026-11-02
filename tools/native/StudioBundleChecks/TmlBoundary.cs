namespace Terraria.ModLoader;

// Only the .tmod file-reader boundary is replaced. Installation and process
// ownership execute the complete production classes against the real payload.
public sealed class Mod
{
    private readonly string _resourceRoot;

    public Mod(string resourceRoot) => _resourceRoot = resourceRoot;

    public bool FileExists(string name) => File.Exists(Path.Combine(_resourceRoot, name));

    public Stream GetFileStream(string name, bool newFileStream = false) =>
        File.OpenRead(Path.Combine(_resourceRoot, name));
}
