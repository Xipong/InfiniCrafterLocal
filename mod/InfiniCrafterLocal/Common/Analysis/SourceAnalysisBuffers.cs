#nullable enable
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace InfiniCrafterLocal.Common.Analysis;

// Source-level .NET 8 primitives. Results belong to the caller; this helper
// retains no buffers, source facts, game state or external dependencies.
internal static class SourceAnalysisBuffers
{
    private const int ChunkBytes = 4096;

    internal static byte[] ReadExact(Stream input, int length, int maximum, CancellationToken cancellation)
    {
        ArgumentNullException.ThrowIfNull(input);
        cancellation.ThrowIfCancellationRequested();
        if (length < 0 || length > maximum) throw new InvalidDataException("native_source_pack_entry_size");
        byte[] result = new byte[length];
        int position = 0;
        while (position < length)
        {
            cancellation.ThrowIfCancellationRequested();
            int count = input.Read(result, position, Math.Min(16 * 1024, length - position));
            // Cancellation takes priority over a simultaneous EOF. Otherwise
            // the pack owner could mistake cancellation for corrupt evidence.
            cancellation.ThrowIfCancellationRequested();
            if (count == 0) throw new InvalidDataException("native_source_pack_entry_length");
            position += count;
        }
        cancellation.ThrowIfCancellationRequested();
        int extra = input.ReadByte();
        cancellation.ThrowIfCancellationRequested();
        if (extra != -1)
            throw new InvalidDataException(length == maximum
                ? "native_source_pack_entry_size" : "native_source_pack_entry_length");
        return result;
    }

    internal static string HashUtf8(string text, CancellationToken cancellation = default)
    {
        ArgumentNullException.ThrowIfNull(text);
        cancellation.ThrowIfCancellationRequested();
        Span<byte> buffer = stackalloc byte[ChunkBytes];
        // Ordinary method keys fit here. Avoid an Encoder and incremental hash
        // for those calls; the worst-case UTF-8 bound includes lone surrogates.
        if (text.Length <= (ChunkBytes - 3) / 3)
        {
            int count = Encoding.UTF8.GetBytes(text.AsSpan(), buffer);
            Span<byte> digest = stackalloc byte[32];
            SHA256.HashData(buffer[..count], digest);
            cancellation.ThrowIfCancellationRequested();
            return Convert.ToHexString(digest).ToLowerInvariant();
        }

        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        Encoder encoder = Encoding.UTF8.GetEncoder();
        ReadOnlySpan<char> remaining = text.AsSpan();
        bool completed;
        do
        {
            cancellation.ThrowIfCancellationRequested();
            // Keep encoder state across UTF-16/UTF-8 chunk boundaries. Flush
            // denotes the end of the complete remaining input, not a substring.
            encoder.Convert(remaining, buffer, flush: true,
                out int chars, out int bytes, out completed);
            hash.AppendData(buffer[..bytes]);
            remaining = remaining[chars..];
        } while (!completed);
        cancellation.ThrowIfCancellationRequested();
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }
}
