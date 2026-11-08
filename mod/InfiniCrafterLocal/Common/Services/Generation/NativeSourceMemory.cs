#nullable enable
using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace InfiniCrafterLocal.Common.Services;

/// <summary>
/// Bounded, allocation-conscious primitives for immutable native source-pack evidence.
/// This intentionally does not cache or transform source facts.
/// </summary>
internal static class NativeSourceMemory
{
    /// <summary>SHA-256 of the exact UTF-8 representation, without allocating a full UTF-8 byte array.</summary>
    internal static string HashUtf8(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var encoder = Encoding.UTF8.GetEncoder();
        Span<byte> buffer = stackalloc byte[8192];
        int position = 0;
        do
        {
            int count = Math.Min(2048, text.Length - position);
            bool final = position + count == text.Length;
            encoder.Convert(text.AsSpan(position, count), buffer, final,
                out int usedChars, out int usedBytes, out bool completed);
            if (usedChars != count || (final && !completed))
                throw new InvalidOperationException("native_source_utf8_encoding_incomplete");
            if (usedBytes != 0) hash.AppendData(buffer[..usedBytes]);
            position += usedChars;
        } while (position < text.Length);
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    /// <summary>
    /// Read a bounded ZIP entry directly into the result buffer, checking the
    /// decompressed length (including unexpected trailing bytes) and cancellation.
    /// Callers remain responsible for SHA-256 validation before parsing.
    /// </summary>
    internal static byte[] ReadZipEntry(ZipArchiveEntry entry, int maximum, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        if (maximum < 0 || entry.Length < 0 || entry.Length > maximum || entry.Length > int.MaxValue)
            throw new InvalidDataException("native_source_pack_entry_size");
        var result = new byte[(int)entry.Length];
        using var input = entry.Open();
        int offset = 0;
        while (offset < result.Length)
        {
            cancellation.ThrowIfCancellationRequested();
            int count = input.Read(result, offset, result.Length - offset);
            if (count == 0) throw new InvalidDataException("native_source_pack_entry_length");
            offset += count;
        }
        cancellation.ThrowIfCancellationRequested();
        if (input.ReadByte() != -1) throw new InvalidDataException("native_source_pack_entry_length");
        cancellation.ThrowIfCancellationRequested();
        return result;
    }
}
