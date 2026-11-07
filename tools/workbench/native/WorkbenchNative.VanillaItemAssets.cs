using System;
using System.Buffers.Binary;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

// Complete pinned source inventory, embedded in the checked native binary.
// Asset availability/integrity does not choose or certify item behavior.
internal static class WVanillaItemAssets
{
    private static readonly JsonObject Index = JsonNode.Parse(typeof(WVanillaItemAssets).Assembly
        .GetManifestResourceStream("Workbench.VanillaItemAssets.json")
        ?? throw new InvalidDataException("Embedded vanilla item source index missing"))!.AsObject();

    internal static byte[] Read(string root, int id, out JsonObject receipt)
    {
        var entry = Index["items"]?[id.ToString(System.Globalization.CultureInfo.InvariantCulture)]?.AsArray()
            ?? throw new FileNotFoundException("Pinned source has no Item_" + id + ".png; no replacement image is admitted");
        return ReadIndexed(root, "Item_" + id + ".png", Index, entry, out receipt);
    }

    internal static byte[] ReadIndexed(string root, string filename, JsonObject index, JsonArray entry, out JsonObject receipt)
    {
        if ((Path.GetFileName(filename) != filename && filename != "Misc/Ripples.png") || filename.Contains("..")) throw new InvalidDataException("Native asset filename must be a simple leaf");
        string path = Path.GetFullPath(Path.Combine(root, "Images", filename));
        for (FileSystemInfo? part = new FileInfo(path); part is not null;
             part = part is FileInfo file ? file.Directory : ((DirectoryInfo)part).Parent)
            if (part.LinkTarget is not null || (part.Exists && (part.Attributes & FileAttributes.ReparsePoint) != 0))
                throw new InvalidDataException("Vanilla asset must not traverse symlinks/reparse points");
        var info = new FileInfo(path);
        if (!info.Exists) throw new FileNotFoundException("Missing pinned native PNG: " + filename + "; provision the exact source asset in " + root, path);
        int expectedBytes = entry[1]!.GetValue<int>();
        if (expectedBytes < 33 || expectedBytes > 4 * 1024 * 1024 || info.Length != expectedBytes)
            throw new InvalidDataException("Vanilla asset PNG size differs from pinned source: " + path);
        byte[] bytes = File.ReadAllBytes(path);
        using var blob = IncrementalHash.CreateHash(HashAlgorithmName.SHA1);
        blob.AppendData(Encoding.ASCII.GetBytes("blob " + bytes.Length.ToString(System.Globalization.CultureInfo.InvariantCulture) + "\0"));
        blob.AppendData(bytes);
        string sha1 = Convert.ToHexString(blob.GetHashAndReset()).ToLowerInvariant();
        if (sha1 != entry[0]!.GetValue<string>()) throw new InvalidDataException("Vanilla asset PNG differs from pinned Git blob: " + path);
        if (!bytes.AsSpan(0, 8).SequenceEqual(new byte[] {137,80,78,71,13,10,26,10}) ||
            BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(8,4)) != 13 ||
            !bytes.AsSpan(12,4).SequenceEqual(new byte[] {73,72,68,82}))
            throw new InvalidDataException("Vanilla asset source must be a PNG with canonical IHDR");
        uint width = BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(16,4));
        uint height = BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(20,4));
        if (width == 0 || height == 0 || width > 4096 || height > 4096 || (ulong)width * height > 16UL * 1024 * 1024)
            throw new InvalidDataException("Vanilla asset PNG dimensions exceed bounded native admission");
        receipt = new JsonObject { ["path"] = path, ["sha256"] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            ["gitBlobSha1"] = sha1, ["communityCommit"] = index["communityCommit"]!.DeepClone(),
            ["sourceTreeSha"] = index["sourceTreeSha"]!.DeepClone(), ["source"] = "Pinned community Terraria source PNG; not official-byte-certified",
            ["width"] = width, ["height"] = height, ["bytes"] = bytes.Length,
            ["scope"] = "Exact pinned source bytes; gameplay and draw behavior remain owned by native Terraria" };
        return bytes;
    }
}
