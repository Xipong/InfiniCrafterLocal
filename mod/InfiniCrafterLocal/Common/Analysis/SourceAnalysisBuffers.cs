#nullable enable
using System;
using System.Buffers;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;

namespace InfiniCrafterLocal.Common.Analysis;

// Source-level .NET 8 primitives: no Terraria state, caches of evidence, or
// external dependencies. Hash the same bytes while avoiding full UTF-8 copies.
internal static class SourceAnalysisBuffers
{
    private const int ChunkBytes = 4096;
    // Unlike the shared pool, this pool has an explicit small retention bound.
    // A single large JSON token may need a larger buffer, which is not retained.
    private static readonly ArrayPool<byte> JsonBuffers = ArrayPool<byte>.Create(64 * 1024, 2);

    internal static byte[] ReadExact(Stream input, int length, int maximum, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        if (length < 0 || length > maximum) throw new InvalidDataException("native_source_pack_entry_size");
        byte[] result = new byte[length];
        int position = 0;
        while (position < length)
        {
            cancellation.ThrowIfCancellationRequested();
            int count = input.Read(result, position, Math.Min(16 * 1024, length - position));
            cancellation.ThrowIfCancellationRequested();
            if (count == 0) throw new InvalidDataException("native_source_pack_entry_length");
            position += count;
        }
        cancellation.ThrowIfCancellationRequested();
        // Do not trust an advertised length: a longer decompressed entry is
        // corruption too. Probe without creating a second input-sized array.
        int extra = input.ReadByte();
        cancellation.ThrowIfCancellationRequested();
        if (extra != -1)
            throw new InvalidDataException(length == maximum
                ? "native_source_pack_entry_size" : "native_source_pack_entry_length");
        return result;
    }

    internal static string HashUtf8(string text, CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        Span<byte> buffer = stackalloc byte[ChunkBytes];
        // Most method identities fit here. Keep their one-shot SHA path and
        // avoid allocating an incremental native hash/encoder for small text.
        if (text.Length <= (ChunkBytes - 3) / 3)
        {
            int count = Encoding.UTF8.GetBytes(text.AsSpan(), buffer);
            Span<byte> digest = stackalloc byte[32];
            SHA256.HashData(buffer[..count], digest);
            cancellation.ThrowIfCancellationRequested();
            return Convert.ToHexString(digest).ToLowerInvariant();
        }
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        AppendUtf8(hash, text, buffer, cancellation);
        cancellation.ThrowIfCancellationRequested();
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    internal static string HashUtf8AndJson(string prefix, JsonNode value, CancellationToken cancellation)
    {
        using var output = new JsonHashWriter(cancellation);
        output.AppendUtf8(prefix);
        using var writer = new Utf8JsonWriter(output);
        value.WriteTo(writer);
        writer.Flush();
        return output.Finish();
    }

    internal static string HashJsonPair(JsonNode first, JsonNode second, CancellationToken cancellation = default)
    {
        using var output = new JsonHashWriter(cancellation);
        using var writer = new Utf8JsonWriter(output);
        first.WriteTo(writer);
        writer.Flush();
        output.AppendNewline();
        writer.Reset(output);
        second.WriteTo(writer);
        writer.Flush();
        return output.Finish();
    }

    private static void AppendUtf8(IncrementalHash hash, string text, Span<byte> buffer, CancellationToken cancellation)
    {
        // Convert owns UTF-16 state across chunks, including a surrogate pair
        // at the boundary and Encoding.UTF8's replacement of lone surrogates.
        Encoder encoder = Encoding.UTF8.GetEncoder();
        ReadOnlySpan<char> remaining = text.AsSpan();
        bool completed;
        do
        {
            cancellation.ThrowIfCancellationRequested();
            encoder.Convert(remaining, buffer, flush: true, out int chars, out int bytes, out completed);
            hash.AppendData(buffer[..bytes]);
            remaining = remaining[chars..];
        } while (!completed);
    }

    private sealed class JsonHashWriter : IBufferWriter<byte>, IDisposable
    {
        private readonly IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        private readonly CancellationToken cancellation;
        private byte[]? buffer;
        private bool disposed;

        internal JsonHashWriter(CancellationToken cancellation)
        {
            this.cancellation = cancellation;
        }

        public void Advance(int count)
        {
            cancellation.ThrowIfCancellationRequested();
            if (disposed) throw new ObjectDisposedException(nameof(JsonHashWriter));
            if (buffer is null || (uint)count > (uint)buffer.Length) throw new ArgumentOutOfRangeException(nameof(count));
            hash.AppendData(buffer.AsSpan(0, count));
        }

        public Memory<byte> GetMemory(int sizeHint = 0) { Ensure(sizeHint); return buffer!; }
        public Span<byte> GetSpan(int sizeHint = 0) { Ensure(sizeHint); return buffer!; }

        private void Ensure(int sizeHint)
        {
            cancellation.ThrowIfCancellationRequested();
            if (disposed) throw new ObjectDisposedException(nameof(JsonHashWriter));
            if (sizeHint < 0) throw new ArgumentOutOfRangeException(nameof(sizeHint));
            int length = Math.Max(ChunkBytes, sizeHint);
            if (buffer is not null && buffer.Length >= length) return;
            byte[] next = JsonBuffers.Rent(length);
            if (buffer is not null) JsonBuffers.Return(buffer);
            buffer = next;
        }

        internal void AppendUtf8(string text)
        {
            Span<byte> bytes = stackalloc byte[ChunkBytes];
            SourceAnalysisBuffers.AppendUtf8(hash, text, bytes, cancellation);
        }

        internal void AppendNewline() => hash.AppendData("\n"u8);

        internal string Finish()
        {
            cancellation.ThrowIfCancellationRequested();
            return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            hash.Dispose();
            if (buffer is not null) { JsonBuffers.Return(buffer); buffer = null; }
        }
    }
}
