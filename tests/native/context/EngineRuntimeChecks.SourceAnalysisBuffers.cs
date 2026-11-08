using System;
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

    private static void SourceBufferExpect<T>(Action action, string label) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException(label + ": expected " + typeof(T).Name);
    }

    private static void SourceBuffersCancellationDoesNotPoisonReuse()
    {
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashUtf8("source", cancelled.Token), "cancelled UTF8 hash");
        SourceBufferExpect<OperationCanceledException>(() => SourceAnalysisBuffers.HashUtf8(new string('x', 20000), cancelled.Token), "cancelled large UTF8 hash");
        Equal(SourceBufferHashOracle("source\ud800😀"), SourceAnalysisBuffers.HashUtf8("source\ud800😀"), "hash retry after cancellation keeps independent state");
    }
}
