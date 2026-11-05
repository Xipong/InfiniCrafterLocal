#nullable enable
using System;
using System.Globalization;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace InfiniCrafterLocal.Common.Services;

// Disk contract shared with LocalGenerator/storage/image_store.py. The network
// continues to carry a basename, length and SHA; paths from peers are never used.
internal sealed class SharedImageStore
{
    internal const string Schema = "infini.image-store.v1";
    private static readonly object Gate = new();
    internal string Root { get; }
    internal sealed record Entry(string Path, string Sha256, int Length);

    internal SharedImageStore(string root) => Root = Path.GetFullPath(root);

    internal static string DefaultRoot(string saveDirectory)
    {
        string configured = Environment.GetEnvironmentVariable("INFINI_IMAGE_DIR") ?? "";
        return Path.GetFullPath(string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(saveDirectory, "InfiniCrafterLocal", "images") : configured);
    }

    private static string Digest(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    internal static bool IsFileName(string file) => file.Length > 4 && file.Length <= 160
        && file.EndsWith(".png", StringComparison.OrdinalIgnoreCase)
        && file.All(c => c is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or >= '0' and <= '9' or '.' or '_' or '-' or '@' or '+');

    private string IndexPath(string file) => Path.Combine(Root, ".index", Digest(file.ToLowerInvariant()) + ".json");

    // Every existing path component is checked, not only the leaf. A lexical
    // containment test alone would let an index escape through a directory link.
    internal bool IsOwnedPath(string path)
    {
        string relative = Path.GetRelativePath(Root, Path.GetFullPath(path));
        if (Path.IsPathRooted(relative) || relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)) return false;
        string current = Root;
        if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) return false;
        foreach (string component in relative.Split(Path.DirectorySeparatorChar))
        {
            current = Path.Combine(current, component);
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) return false;
        }
        return true;
    }

    private JsonDocument ReadJson(string path)
    {
        if (!IsOwnedPath(path) || new FileInfo(path).Length > 16 * 1024) throw new InvalidDataException("Invalid image store metadata.");
        return JsonDocument.Parse(File.ReadAllBytes(path));
    }

    internal bool HasIndex(string file) => IsFileName(file) && File.Exists(IndexPath(file));

    internal Entry? Resolve(string file) => ReadEntry(file, requireAvailable: true);

    private Entry? ReadEntry(string file, bool requireAvailable)
    {
        if (!IsFileName(file)) return null;
        try
        {
            using var json = ReadJson(IndexPath(file));
            JsonElement value = json.RootElement;
            if (value.GetProperty("schema").GetString() != Schema
                || !string.Equals(value.GetProperty("file").GetString(), file, StringComparison.OrdinalIgnoreCase)) return null;
            string relative = value.GetProperty("path").GetString() ?? "";
            string[] parts = relative.Split('/');
            if (parts.Length < 2 || parts.Any(x => x is "" or "." or ".." || x.Equals("diagnostics", StringComparison.OrdinalIgnoreCase) || x.Contains('\\') || x.Contains(':'))
                || parts[^2] != "final" || !IsFileName(parts[^1])) return null;
            string candidate = Path.GetFullPath(Path.Combine(Root, Path.Combine(parts)));
            int length = value.GetProperty("length").GetInt32();
            string sha = value.GetProperty("sha256").GetString() ?? "";
            if (!IsOwnedPath(candidate) || length <= 0 || length > GeneratedAssetSyncService.MaxAssetBytes
                || sha.Length != 64 || !sha.All(Uri.IsHexDigit)) return null;
            var info = new FileInfo(candidate);
            return !requireAvailable || (info.Exists && info.Length == length) ? new(candidate, sha.ToLowerInvariant(), length) : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or ArgumentException or KeyNotFoundException or FormatException) { return null; }
    }

    internal static string SafeLabel(string value, string fallback)
    {
        var text = new StringBuilder(); bool space = false;
        foreach (Rune rune in (value ?? "").Normalize(NormalizationForm.FormC).EnumerateRunes())
        {
            var category = Rune.GetUnicodeCategory(rune);
            bool alphanumeric = Rune.IsLetter(rune) || category is UnicodeCategory.DecimalDigitNumber or UnicodeCategory.LetterNumber or UnicodeCategory.OtherNumber;
            string part = alphanumeric || rune.Value is ' ' or '_' or '-' ? rune.ToString() : "_";
            if (part == " " && space) continue;
            text.Append(part); space = part == " ";
        }
        string cleaned = text.ToString().Trim(' ', '.', '_');
        cleaned = string.Concat(cleaned.EnumerateRunes().Take(20).Select(rune => rune.ToString())).TrimEnd(' ', '.', '_');
        return cleaned.Length == 0 ? fallback : cleaned;
    }

    private string IdentityDirectory(string parent, string identity, string label, string kind)
    {
        if (!IsOwnedPath(parent)) throw new IOException("Image directory is outside the owned store.");
        Directory.CreateDirectory(parent);
        string suffix = "--" + Digest(identity)[..16];
        foreach (string directory in Directory.EnumerateDirectories(parent, "*" + suffix).OrderBy(p => p, StringComparer.Ordinal))
        {
            try
            {
                using var saved = ReadJson(Path.Combine(directory, ".identity.json"));
                if (saved.RootElement.GetProperty("id").GetString() != identity || saved.RootElement.GetProperty("kind").GetString() != kind) continue;
                if (saved.RootElement.GetProperty("name").GetString() != label)
                    AtomicJson(Path.Combine(directory, ".identity.json"), new { kind, id = identity, name = label });
                return directory;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException) { }
        }
        string path = Path.Combine(parent, SafeLabel(string.IsNullOrEmpty(label) ? identity : label, kind) + suffix);
        if (Directory.Exists(path) || File.Exists(path) || !IsOwnedPath(path)) throw new IOException("Image directory ownership conflict.");
        string temporary = Path.Combine(parent, ".identity-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try
        {
            AtomicJson(Path.Combine(temporary, ".identity.json"), new { kind, id = identity, name = label });
            Directory.Move(temporary, path);
        }
        finally { if (Directory.Exists(temporary)) Directory.Delete(temporary, recursive: true); }
        return path;
    }

    private void AtomicJson(string path, object value) => AtomicBytes(path, JsonSerializer.SerializeToUtf8Bytes(value));

    private void AtomicBytes(string path, byte[] bytes)
    {
        if (!IsOwnedPath(path)) throw new IOException("Image store path is not owned.");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temporary = Path.Combine(Path.GetDirectoryName(path)!, "." + Path.GetFileName(path) + "." + Guid.NewGuid().ToString("N") + ".part");
        try
        {
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { output.Write(bytes); output.Flush(flushToDisk: true); }
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    [DllImport("libc", SetLastError = true)]
    private static extern int lockf(int descriptor, int command, long length);

    private static void LockStore(FileStream stream, bool unlock)
    {
        if (OperatingSystem.IsMacOS())
        {
            stream.Position = 0;
            if (lockf(stream.SafeFileHandle.DangerousGetHandle().ToInt32(), unlock ? 0 : 2, 1) != 0)
                throw new IOException("Could not lock shared image store.");
        }
        else if (unlock) stream.Unlock(0, 1);
        else stream.Lock(0, 1);
    }

    internal string Publish(string file, byte[] bytes, string worldId, string worldName, string itemId, string itemName, string role = "asset")
    {
        if (!IsFileName(file) || !GeneratedAssetSyncService.IsCompletePng(bytes)) throw new InvalidDataException("Invalid final PNG.");
        string sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        lock (Gate)
        {
            if (!IsOwnedPath(Root)) throw new IOException("Image store root is linked.");
            Directory.CreateDirectory(Root);
            string lockPath = Path.Combine(Root, ".store.lock");
            if (!IsOwnedPath(lockPath)) throw new IOException("Image store lock is linked.");
            using var gate = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite);
            if (gate.Length == 0) { gate.WriteByte(0); gate.Flush(); }
            DateTime deadline = DateTime.UtcNow.AddSeconds(10);
            while (true)
            {
                try { LockStore(gate, unlock: false); break; }
                catch (IOException) when (DateTime.UtcNow < deadline) { Thread.Sleep(25); }
            }
            try
            {
                // Even an absent or damaged PNG cannot erase an alias's declared
                // byte identity. Refuse conflicting replacement before any write.
                if (File.Exists(IndexPath(file)))
                {
                    using var prior = ReadJson(IndexPath(file));
                    if (prior.RootElement.GetProperty("schema").GetString() != Schema
                        || !string.Equals(prior.RootElement.GetProperty("file").GetString(), file, StringComparison.OrdinalIgnoreCase)
                        || !string.Equals(prior.RootElement.GetProperty("sha256").GetString(), sha, StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Image transport filename collision.");
                }
                worldId = string.IsNullOrEmpty(worldId) ? "unscoped" : worldId;
                itemId = string.IsNullOrEmpty(itemId) ? "unscoped" : itemId;
                string world = IdentityDirectory(Path.Combine(Root, "worlds"), worldId, string.IsNullOrEmpty(worldName) ? worldId : worldName, "world");
                string item = IdentityDirectory(world, itemId, string.IsNullOrEmpty(itemName) ? itemId : itemName, "item");
                Entry? existing = ReadEntry(file, requireAvailable: false);
                if (existing is not null)
                {
                    // Never duplicate a locally generated final or overwrite a
                    // different owner merely because it reused a transport token.
                    if (existing.Sha256 != sha) throw new IOException("Image transport filename collision.");
                    if (!File.Exists(existing.Path) || !File.ReadAllBytes(existing.Path).AsSpan().SequenceEqual(bytes))
                        AtomicBytes(existing.Path, bytes); // restore the declared immutable byte identity
                    return existing.Path;
                }
                string roleLabel = Regex.Replace(role.ToLowerInvariant(), "[^a-z0-9_-]+", "_").Trim('_');
                roleLabel = string.IsNullOrEmpty(roleLabel) ? "asset" : roleLabel[..Math.Min(roleLabel.Length, 24)];
                string canonicalFile = Regex.IsMatch(file, "^[a-z0-9_-]{1,24}--[a-f0-9]{64}\\.png$") ? file
                    : roleLabel + "--" + Digest(worldId + "\0" + itemId + "\0" + role + "\0" + file + "\0" + sha) + ".png";
                string destination = Path.Combine(item, "final", canonicalFile);
                if (File.Exists(destination) && !File.ReadAllBytes(destination).AsSpan().SequenceEqual(bytes))
                    throw new IOException("Immutable image content conflict.");
                if (!File.Exists(destination)) AtomicBytes(destination, bytes);
                foreach (string alias in new[] { canonicalFile, file }.Distinct(StringComparer.OrdinalIgnoreCase))
                    AtomicJson(IndexPath(alias), new { schema = Schema, file = alias, path = Path.GetRelativePath(Root, destination).Replace('\\', '/'), sha256 = sha, length = bytes.Length, worldId, itemId, role });
                return destination;
            }
            finally { LockStore(gate, unlock: true); }
        }
    }
}
