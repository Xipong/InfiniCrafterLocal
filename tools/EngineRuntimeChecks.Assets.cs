using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void DisposedAssetDownloadCannotPublish()
        => CheckDisposedAssetDownloadsAsync().GetAwaiter().GetResult();

    private static async Task CheckDisposedAssetDownloadsAsync()
    {
        // Actual Pillow-produced 2x2 RGBA PNG, not a mocked IsCompletePng result.
        byte[] png = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGMUDJ76n4GBgYGJAQoAHTQB/GtRKAwAAAAASUVORK5CYII=");
        var failures = new System.Collections.Generic.List<string>();
        foreach (bool disposed in new[] { false, true })
        foreach (string outcome in new[] { "png", "invalid_png", "http_error" })
        {
            bool valid = outcome == "png";
            byte[] body = valid ? png : Encoding.ASCII.GetBytes("not a PNG");
            using var service = new GeneratedAssetSyncService();
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            string baseUrl = "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port;
            string file = "asset_lifetime_" + Guid.NewGuid().ToString("N") + ".png";
            string local = Path.Combine(service.CacheRoot, file);
            var headersSent = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var releaseBody = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            Task server = Task.Run(async () =>
            {
                using TcpClient client = await listener.AcceptTcpClientAsync();
                await using NetworkStream stream = client.GetStream();
                using var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, leaveOpen: true);
                string? line;
                do { line = await reader.ReadLineAsync(); } while (!string.IsNullOrEmpty(line));
                if (outcome == "http_error")
                {
                    // Delay the failing status itself until after Dispose, so
                    // this must exercise the worker's exception path afterward.
                    headersSent.TrySetResult(true);
                    await releaseBody.Task;
                }
                string status = outcome == "http_error" ? "500 Internal Server Error" : "200 OK";
                byte[] headers = Encoding.ASCII.GetBytes("HTTP/1.1 " + status + "\r\nContent-Type: image/png\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n");
                if (outcome == "http_error")
                {
                    await stream.WriteAsync(headers.Concat(body).ToArray());
                    return;
                }
                await stream.WriteAsync(headers);
                await stream.FlushAsync();
                headersSent.TrySetResult(true);
                await releaseBody.Task;
                await stream.WriteAsync(body);
            });
            Task? download = null;
            try
            {
                // Await the canonical worker directly: QueueDownloads is fire-and-forget.
                var method = typeof(GeneratedAssetSyncService).GetMethod("DownloadOneAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
                download = (Task)method.Invoke(service, new object?[] { baseUrl, "", file, local, baseUrl + "|" + file, null })!;
                await headersSent.Task.WaitAsync(TimeSpan.FromSeconds(10));
                if (disposed) service.Dispose();
                releaseBody.TrySetResult(true);
                await Task.WhenAll(server, download).WaitAsync(TimeSpan.FromSeconds(10));
                Equal(valid && !disposed, File.Exists(local), "published file: disposed=" + disposed + ", outcome=" + outcome);
                if (valid && !disposed)
                    Equal(true, png.SequenceEqual(File.ReadAllBytes(local)), "active service commits exact verified bytes");
                Equal(!disposed && !valid ? 1 : 0, service.GetDebugSnapshot().KnownMissingCount,
                    "retry state: disposed=" + disposed + ", outcome=" + outcome);
                Equal(false, File.Exists(local + ".part"), "no leftover partial file");
                if (disposed)
                {
                    bool oldDedicated = Terraria.Main.dedServ;
                    try
                    {
                        Terraria.Main.dedServ = false;
                        service.QueueDownloads(baseUrl, new[] { file }, forceRetry: true);
                        Equal(0, service.GetDebugSnapshot().DownloadStartedCount, "disposed service cannot enqueue a new download");
                    }
                    finally { Terraria.Main.dedServ = oldDedicated; }
                }
            }
            catch (Exception error) { failures.Add(error.ToString()); }
            finally
            {
                releaseBody.TrySetResult(true);
                listener.Stop();
                try { await server.WaitAsync(TimeSpan.FromSeconds(15)); } catch { }
                if (download is not null)
                    await download.WaitAsync(TimeSpan.FromSeconds(15));
                service.Dispose();
                File.Delete(local);
                File.Delete(local + ".part");
            }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
