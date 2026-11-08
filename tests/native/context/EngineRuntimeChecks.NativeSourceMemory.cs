using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void NativeSourceMemoryPreservesHashAndZipBytes()
    {
        // Verify ASCII, multi-byte Unicode, supplementary scalars and the
        // replacement fallback for malformed UTF-16 at chunk boundaries.
        string[] samples = {
            "", "small", new string('x', 4096),
            new string('a', 2047) + "\ud83d\ude80" + new string('z', 2049),
            new string('a', 2047) + "\ud800" + new string('b', 2050),
            new string('x', 1024 * 1024) + "日本語\ud83c\udf0d"
        };
        foreach (string sample in samples)
        {
            string expected = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sample))).ToLowerInvariant();
            if (NativeSourceMemory.HashUtf8(sample) != expected)
                throw new InvalidDataException("Streaming UTF-8 SHA-256 parity failed.");
        }

        foreach (int size in new[] { 0, 1, 16383, 65536, 1048576 })
        {
            byte[] payload = new byte[size];
            for (int i = 0; i < payload.Length; i++) payload[i] = (byte)(i * 17 + 3);
            using var archiveBytes = new MemoryStream();
            using (var writer = new ZipArchive(archiveBytes, ZipArchiveMode.Create, leaveOpen: true))
            {
                using var output = writer.CreateEntry("payload", CompressionLevel.Optimal).Open();
                output.Write(payload);
            }
            archiveBytes.Position = 0;
            using var archive = new ZipArchive(archiveBytes, ZipArchiveMode.Read, leaveOpen: true);
            var entry = archive.GetEntry("payload")!;
            byte[] actual = NativeSourceMemory.ReadZipEntry(entry, Math.Max(size, 1), CancellationToken.None);
            if (!actual.AsSpan().SequenceEqual(payload))
                throw new InvalidDataException("ZIP direct-buffer reader parity failed.");
            if (size > 0)
            {
                try
                {
                    NativeSourceMemory.ReadZipEntry(entry, size - 1, CancellationToken.None);
                    throw new InvalidDataException("ZIP size bound unexpectedly accepted.");
                }
                catch (InvalidDataException e) when (e.Message == "native_source_pack_entry_size") { }
            }
            using var cancelled = new CancellationTokenSource();
            cancelled.Cancel();
            try
            {
                NativeSourceMemory.ReadZipEntry(entry, Math.Max(size, 1), cancelled.Token);
                throw new InvalidDataException("Cancelled ZIP read unexpectedly accepted.");
            }
            catch (OperationCanceledException) { }
        }
    }
}
