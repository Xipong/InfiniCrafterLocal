#nullable enable
using System;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace InfiniCrafterLocal.Common.Analysis;

// Source-level .NET 8 primitives. Results belong to the caller; this helper
// retains no buffers, source facts, game state or external dependencies.
internal static class SourceAnalysisBuffers
{
    private const int ChunkBytes = 4096;

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
