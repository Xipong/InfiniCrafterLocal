using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Analysis;

internal static partial class EngineRuntimeChecks
{
    private static string SourceBufferHashOracle(string text)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();

    private static void SourceBuffersHashUtf8MatchesExactBytes()
    {
        string[] texts = { "", "source\r\nbytes\0", "Исходный код 日本語 😀", "\ud800", "\udfff",
            new string('a', 1364), new string('a', 1365), new string('\uffff', 1364), new string('\uffff', 1365),
            new string('a', 4093) + "😀tail", new string('a', 4095) + "😀tail",
            new string('a', 4095) + "\ud800X", new string('a', 4095) + "\udfffX",
            new string('Ж', 2047) + "😀tail", new string('日', 1365) + "😀tail",
            string.Concat(Enumerable.Repeat("Ж\u2028😀\ud800\0", 16000)) };
        foreach (string text in texts)
            Equal(SourceBufferHashOracle(text), SourceAnalysisBuffers.HashUtf8(text), "exact UTF8 SHA including chunk boundaries");
        var random = new Random(339);
        for (int run = 0; run < 40; run++)
        {
            var chars = new char[random.Next(1, 18000)];
            for (int index = 0; index < chars.Length; index++) chars[index] = (char)random.Next(65536);
            string text = new(chars);
            Equal(SourceBufferHashOracle(text), SourceAnalysisBuffers.HashUtf8(text), "random UTF16 replacement parity");
        }
        string large = new('x', 1024 * 1024);
        string expected = SourceBufferHashOracle(large);
        _ = SourceAnalysisBuffers.HashUtf8(large);
        long before = GC.GetAllocatedBytesForCurrentThread();
        string actual = SourceAnalysisBuffers.HashUtf8(large);
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        Equal(expected, actual, "large source exact SHA");
        Equal(true, allocated < 32768, "large text hashing does not allocate a full UTF8 source copy");
    }

    private static void SourceBuffersHashUtf8ConcurrencyKeepsIndependentState()
    {
        string shared = string.Concat(Enumerable.Repeat("source 日本語 😀\ud800\0", 4096));
        string sharedExpected = SourceBufferHashOracle(shared);
        Parallel.For(0, 32, index => {
            string text = new string('x', index * 1024) + "\ud800" + index + "😀";
            Equal(SourceBufferHashOracle(text), SourceAnalysisBuffers.HashUtf8(text),
                "concurrent distinct UTF8 hashes have independent buffers and encoder state");
            Equal(sharedExpected, SourceAnalysisBuffers.HashUtf8(shared), "concurrent readers keep shared source unchanged");
        });
    }

    private static void SourceBufferExpect<T>(Action action, string label, string? reason = null) where T : Exception
    {
        try { action(); }
        catch (T error)
        {
            if (reason is not null) Equal(reason, error.Message, label + " refusal reason");
            return;
        }
        throw new InvalidOperationException(label + ": expected " + typeof(T).Name);
    }

    private sealed class SourceBufferShortStream : Stream
    {
        private readonly byte[] bytes;
        private readonly Action? onRead;
        private int position;
        private bool disposed;
        internal int ReadCalls { get; private set; }
        internal int ProbeCalls { get; private set; }
        internal SourceBufferShortStream(byte[] bytes, Action? onRead = null) { this.bytes = bytes; this.onRead = onRead; }
        public override bool CanRead => !disposed;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            ReadCalls++;
            int read = Math.Min(Math.Min(13, count), bytes.Length - position);
            Array.Copy(bytes, position, buffer, offset, read);
            position += read;
            onRead?.Invoke();
            return read;
        }
        public override int ReadByte()
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            ProbeCalls++;
            int result = position == bytes.Length ? -1 : bytes[position++];
            onRead?.Invoke();
            return result;
        }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { disposed = true; base.Dispose(disposing); }
    }

    private static void SourceBuffersReadExactKeepsBoundsAndOwnership()
    {
        byte[] bytes = Enumerable.Range(0, 30000).Select(value => (byte)value).ToArray();
        using var firstStream = new SourceBufferShortStream(bytes);
        byte[] first = SourceAnalysisBuffers.ReadExact(firstStream, bytes.Length, bytes.Length, default);
        Equal(true, bytes.SequenceEqual(first), "short nonseekable reads retain exact bytes");
        Equal(true, firstStream.CanRead, "the caller retains ownership of the input stream");
        using var secondStream = new SourceBufferShortStream(bytes);
        byte[] second = SourceAnalysisBuffers.ReadExact(secondStream, bytes.Length, bytes.Length + 1, default);
        first[0] ^= 255;
        Equal(bytes[0], second[0], "entry ownership cannot alias another result");
        foreach (int length in new[] { bytes.Length - 1, bytes.Length + 1 })
        {
            using var stream = new SourceBufferShortStream(bytes);
            SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(stream, length, bytes.Length + 1, default),
                "lying short or long declared entry length", "native_source_pack_entry_length");
        }
        using var tooLarge = new SourceBufferShortStream(bytes);
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(tooLarge, bytes.Length, bytes.Length - 1, default),
            "maximum entry length", "native_source_pack_entry_size");
        Equal(0, tooLarge.ReadCalls + tooLarge.ProbeCalls, "oversized input is rejected before reading");
        using var negativeLength = new SourceBufferShortStream(bytes);
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(negativeLength, -1, bytes.Length, default),
            "negative declared length", "native_source_pack_entry_size");
        Equal(0, negativeLength.ReadCalls + negativeLength.ProbeCalls, "negative length is rejected before reading");
        using var empty = new SourceBufferShortStream(Array.Empty<byte>());
        Equal(0, SourceAnalysisBuffers.ReadExact(empty, 0, 0, default).Length, "zero length at EOF");
        using var extra = new SourceBufferShortStream(new byte[] { 1 });
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(extra, 0, 0, default),
            "zero advertised length has extra byte", "native_source_pack_entry_size");
        using var extraWithinMaximum = new SourceBufferShortStream(new byte[] { 1 });
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(extraWithinMaximum, 0, 1, default),
            "extra byte below maximum still violates exact length", "native_source_pack_entry_length");

        Parallel.For(0, 16, _ => {
            using var input = new SourceBufferShortStream(bytes);
            byte[] result = SourceAnalysisBuffers.ReadExact(input, bytes.Length, bytes.Length, default);
            Equal(true, bytes.SequenceEqual(result), "concurrent reads return independent complete results");
            result[0] ^= 255;
        });
        Equal((byte)0, bytes[0], "mutating a returned buffer cannot change the shared input");
    }

    private static void SourceBuffersReadZipEntryPreservesBytes()
    {
        foreach (int size in new[] { 0, 1, 16383, 16384, 16385, 65536, 1048576 })
        {
            byte[] payload = new byte[size];
            for (int index = 0; index < payload.Length; index++) payload[index] = (byte)(index * 17 + 3);
            using var archiveBytes = new MemoryStream();
            using (var writer = new ZipArchive(archiveBytes, ZipArchiveMode.Create, leaveOpen: true))
            {
                using var output = writer.CreateEntry("payload", CompressionLevel.Optimal).Open();
                output.Write(payload);
            }
            archiveBytes.Position = 0;
            using var archive = new ZipArchive(archiveBytes, ZipArchiveMode.Read, leaveOpen: true);
            ZipArchiveEntry entry = archive.GetEntry("payload")!;
            using var input = entry.Open();
            byte[] actual = SourceAnalysisBuffers.ReadExact(input, checked((int)entry.Length), size, default);
            Equal(true, actual.AsSpan().SequenceEqual(payload), "decompressed ZIP entry retains every byte including read boundaries");
        }
    }

    private static void SourceBuffersCancellationDoesNotPoisonReuse()
    {
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashUtf8("source", cancelled.Token), "cancelled UTF8 hash");
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashUtf8(new string('x', 20000), cancelled.Token), "cancelled large UTF8 hash");
        using var beforeRead = new SourceBufferShortStream(new byte[1]);
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(beforeRead, 1, 1, cancelled.Token), "cancelled before input read");
        Equal(0, beforeRead.ReadCalls + beforeRead.ProbeCalls, "pre-cancelled read never accesses the stream");
        using var midway = new CancellationTokenSource();
        using var stream = new SourceBufferShortStream(new byte[40], () => midway.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(stream, 40, 40, midway.Token), "cancel between short reads");
        using var atEof = new CancellationTokenSource();
        using var shortStream = new SourceBufferShortStream(Array.Empty<byte>(), () => atEof.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(shortStream, 1, 1, atEof.Token), "cancellation precedes truncated EOF refusal");
        using var atProbe = new CancellationTokenSource();
        using var longStream = new SourceBufferShortStream(new byte[] { 1 }, () => atProbe.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(longStream, 0, 0, atProbe.Token), "cancellation precedes extra-byte refusal");
        using var atSuccessfulEof = new CancellationTokenSource();
        using var completedStream = new SourceBufferShortStream(Array.Empty<byte>(), () => atSuccessfulEof.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(completedStream, 0, 0, atSuccessfulEof.Token),
            "cancellation after successful EOF probe precedes returning a result");
        using var atLastRead = new CancellationTokenSource();
        using var lastReadStream = new SourceBufferShortStream(new byte[] { 1 }, () => atLastRead.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(lastReadStream, 1, 1, atLastRead.Token),
            "cancellation after final data read precedes probing");
        Equal(0, lastReadStream.ProbeCalls, "cancelled final data read does not probe input");
        Equal(SourceBufferHashOracle("source\ud800😀"), SourceAnalysisBuffers.HashUtf8("source\ud800😀"), "hash retry after cancellation keeps independent state");
        using var retry = new SourceBufferShortStream(new byte[] { 1, 2, 3 });
        Equal(true, new byte[] { 1, 2, 3 }.SequenceEqual(SourceAnalysisBuffers.ReadExact(retry, 3, 3, default)),
            "read retry after cancellation keeps independent ownership");
    }
}
