using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
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
            new string('a', 1364), new string('a', 1365), new string('a', 4095) + "😀tail",
            new string('a', 4095) + "\ud800X", new string('a', 4095) + "\udfffX",
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

    private static void SourceBuffersHashJsonMatchesRendererAndConcurrency()
    {
        JsonNode[] values = {
            JsonNode.Parse("{\"last\":1.00,\"first\":-0,\"exponent\":2e-3,\"null\":null,\"bool\":true}")!,
            new JsonObject { ["quote\"<>&"] = "Русский\r\n😀\t\u2028", ["big"] = new string('q', 180000) },
            new JsonArray(3, 3, 1, null, new JsonObject { ["a"] = 1.25m, ["b"] = -0.0 }),
            new JsonArray(),
        };
        foreach (JsonNode first in values)
        foreach (JsonNode second in values)
        {
            string originalFirst = first.ToJsonString();
            string originalSecond = second.ToJsonString();
            Equal(SourceBufferHashOracle(originalFirst + "\n" + originalSecond),
                SourceAnalysisBuffers.HashJsonPair(first, second), "JSON pair retains ordering escaping and numeric spelling");
            const string prefix = "method\n日本語\n";
            Equal(SourceBufferHashOracle(prefix + originalFirst),
                SourceAnalysisBuffers.HashUtf8AndJson(prefix, first, default), "projection key retains exact UTF8 prefix and JSON");
            Equal(originalFirst, first.ToJsonString(), "first node remains unchanged");
            Equal(originalSecond, second.ToJsonString(), "second node remains unchanged");
        }
        Parallel.For(0, 32, index => {
            var first = new JsonArray(index, "branch", new string('x', index * 1024));
            var second = new JsonArray("source", index);
            Equal(SourceBufferHashOracle(first.ToJsonString() + "\n" + second.ToJsonString()),
                SourceAnalysisBuffers.HashJsonPair(first, second), "concurrent hashes have independent buffers and state");
        });
    }

    private static void SourceBufferExpect<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException(label + ": expected " + typeof(T).Name);
    }

    private sealed class SourceBufferShortStream : Stream
    {
        private readonly byte[] bytes;
        private readonly Action? onRead;
        private int position;
        internal SourceBufferShortStream(byte[] bytes, Action? onRead = null) { this.bytes = bytes; this.onRead = onRead; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count)
        {
            int read = Math.Min(Math.Min(13, count), bytes.Length - position);
            Array.Copy(bytes, position, buffer, offset, read);
            position += read;
            onRead?.Invoke();
            return read;
        }
        public override int ReadByte()
        {
            int result = position == bytes.Length ? -1 : bytes[position++];
            onRead?.Invoke();
            return result;
        }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    private static void SourceBuffersReadExactKeepsBoundsAndOwnership()
    {
        byte[] bytes = Enumerable.Range(0, 30000).Select(value => (byte)value).ToArray();
        using var firstStream = new SourceBufferShortStream(bytes);
        byte[] first = SourceAnalysisBuffers.ReadExact(firstStream, bytes.Length, bytes.Length, default);
        Equal(true, bytes.SequenceEqual(first), "short nonseekable reads retain exact bytes");
        using var secondStream = new SourceBufferShortStream(bytes);
        byte[] second = SourceAnalysisBuffers.ReadExact(secondStream, bytes.Length, bytes.Length + 1, default);
        first[0] ^= 255;
        Equal(bytes[0], second[0], "entry ownership cannot alias another result");
        foreach (int length in new[] { bytes.Length - 1, bytes.Length + 1 })
        {
            using var stream = new SourceBufferShortStream(bytes);
            SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(stream, length, bytes.Length + 1, default),
                "lying short or long declared entry length");
        }
        using var tooLarge = new SourceBufferShortStream(bytes);
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(tooLarge, bytes.Length, bytes.Length - 1, default), "maximum entry length");
        using var empty = new SourceBufferShortStream(Array.Empty<byte>());
        Equal(0, SourceAnalysisBuffers.ReadExact(empty, 0, 0, default).Length, "zero length at EOF");
        using var extra = new SourceBufferShortStream(new byte[] { 1 });
        SourceBufferExpect<InvalidDataException>(() => SourceAnalysisBuffers.ReadExact(extra, 0, 0, default), "zero advertised length has extra byte");
    }

    private static void SourceBuffersCancellationDoesNotPoisonReuse()
    {
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashUtf8("source", cancelled.Token), "cancelled UTF8 hash");
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashJsonPair(new JsonArray(1), new JsonArray(2), cancelled.Token), "cancelled JSON hash");
        using var midway = new CancellationTokenSource();
        using var stream = new SourceBufferShortStream(new byte[40], () => midway.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(stream, 40, 40, midway.Token), "cancel between short reads");
        using var atEof = new CancellationTokenSource();
        using var shortStream = new SourceBufferShortStream(Array.Empty<byte>(), () => atEof.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(shortStream, 1, 1, atEof.Token), "cancellation precedes truncated EOF refusal");
        using var atProbe = new CancellationTokenSource();
        using var longStream = new SourceBufferShortStream(new byte[] { 1 }, () => atProbe.Cancel());
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.ReadExact(longStream, 0, 0, atProbe.Token), "cancellation precedes extra-byte refusal");
        Equal(SourceBufferHashOracle("[1]\n[2]"), SourceAnalysisBuffers.HashJsonPair(new JsonArray(1), new JsonArray(2)), "retry after cancelled buffer owner");
    }
}
