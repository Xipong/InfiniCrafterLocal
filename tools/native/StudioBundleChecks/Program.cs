using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;

string temporary = Path.Combine(Path.GetTempPath(), "ifc-studio-checks-" + Guid.NewGuid().ToString("N"));
try
{
    string studio = Path.Combine(temporary, "save with spaces", "InfiniCrafterLocal", "Studio");
    string runtimes = Path.Combine(studio, "runtimes");
    string data = Path.Combine(studio, "data");
    Directory.CreateDirectory(data);
    File.WriteAllText(Path.Combine(data, "config.env"), "user configuration");

    byte[] payload = Archive(("python/python.exe", "interpreter"), ("LocalGenerator/scripts/bundled_studio.py", "launcher"), ("LocalGenerator/webui/icon.png", "PNG bytes"));
    StudioBundleSpec spec = Spec(payload);
    byte[] manifest = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        platforms = new Dictionary<string, object>
        {
            ["win-x64"] = new { archive = spec.Archive, sha256 = spec.Sha256, python = spec.Python, entryPoint = spec.EntryPoint },
        },
    });
    Require(StudioBundle.ReadManifest(manifest, "win-x64") == spec, "manifest round trip");
    Reject<PlatformNotSupportedException>(() => StudioBundle.ReadManifest(manifest, "linux-x64"));

    string installed = StudioBundle.Install(payload, spec, runtimes, CancellationToken.None);
    Require(File.ReadAllText(Path.Combine(installed, "LocalGenerator/webui/icon.png")) == "PNG bytes", "asset bytes preserved");
    DateTime modified = File.GetLastWriteTimeUtc(Path.Combine(installed, spec.Python));
    Require(StudioBundle.Install(payload, spec, runtimes, CancellationToken.None) == installed, "completed runtime reused");
    Require(File.GetLastWriteTimeUtc(Path.Combine(installed, spec.Python)) == modified, "reuse does not overwrite installed files");

    File.Delete(Path.Combine(installed, spec.EntryPoint));
    Require(StudioBundle.Install(payload, spec, runtimes, CancellationToken.None) == installed, "incomplete runtime repaired");
    Require(File.Exists(Path.Combine(installed, spec.EntryPoint)), "repaired launcher exists");

    byte[] update = Archive(("python/python.exe", "new interpreter"), ("LocalGenerator/scripts/bundled_studio.py", "new launcher"));
    string updated = StudioBundle.Install(update, Spec(update), runtimes, CancellationToken.None);
    Require(updated != installed && File.Exists(Path.Combine(installed, spec.Python)), "updates have separate runtime directories");
    Require(File.ReadAllText(Path.Combine(data, "config.env")) == "user configuration", "updates preserve user configuration");

    byte[] corrupt = (byte[])payload.Clone();
    corrupt[0] ^= 1;
    Reject<InvalidDataException>(() => StudioBundle.Install(corrupt, spec, runtimes, CancellationToken.None));
    Require(File.ReadAllText(Path.Combine(installed, spec.Python)) == "interpreter", "hash failure leaves complete runtime intact");

    byte[] escaped = Archive(("../outside.txt", "must not escape"));
    Reject<InvalidDataException>(() => StudioBundle.Install(escaped, Spec(escaped), runtimes, CancellationToken.None));
    Require(!File.Exists(Path.Combine(runtimes, "outside.txt")), "archive cannot escape staging directory");
    byte[] aliases = Archive(("python/python.exe", "one"), ("PYTHON/PYTHON.EXE", "two"));
    Reject<InvalidDataException>(() => StudioBundle.Install(aliases, Spec(aliases), runtimes, CancellationToken.None));
    byte[] missing = Archive(("readme.txt", "no interpreter"));
    Reject<InvalidDataException>(() => StudioBundle.Install(missing, Spec(missing), runtimes, CancellationToken.None));
    Require(!Directory.Exists(Path.Combine(runtimes, Spec(missing).Sha256)), "incomplete archive is not published");

    using var cancelled = new CancellationTokenSource();
    cancelled.Cancel();
    Reject<OperationCanceledException>(() => StudioBundle.Install(payload, spec, runtimes, cancelled.Token));
    using (var heldLock = new FileStream(Path.Combine(runtimes, ".install.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
    using (var interruptedWait = new CancellationTokenSource(TimeSpan.FromMilliseconds(200)))
        Reject<OperationCanceledException>(() => StudioBundle.Install(payload, spec, runtimes, interruptedWait.Token));
    Require(File.Exists(Path.Combine(installed, spec.Python)), "contending installer preserves published runtime");
    Require(Directory.GetDirectories(runtimes, ".install-*").Length == 0, "failed installations clean staging directories");
    Console.WriteLine("PASS: Studio manifest, extraction, asset bytes, cache reuse, update preservation, corruption, path safety and cancellation.");

    if (args.Length == 2 && args[0] == "--bundle-root")
        await CheckBundledRuntime(Path.GetFullPath(args[1]), Path.Combine(temporary, "tModLoader с пробелами"));
    else if (args.Length != 0)
        throw new ArgumentException("Usage: StudioBundleChecks [--bundle-root ModSources/InfiniCrafterLocal]");
}
finally
{
    if (Directory.Exists(temporary))
        Directory.Delete(temporary, recursive: true);
}

static StudioBundleSpec Spec(byte[] payload) => new("Studio/runtime-win-x64.zip", Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant(), "python/python.exe", "LocalGenerator/scripts/bundled_studio.py");

static async Task CheckBundledRuntime(string resources, string saveDirectory)
{
    if (!BundledStudio.IsSupported)
        throw new PlatformNotSupportedException("The actual bundled-runtime check requires Windows x64.");
    string studioDirectory = Path.Combine(saveDirectory, "InfiniCrafterLocal", "Studio");
    string dataDirectory = Path.Combine(studioDirectory, "data");
    Directory.CreateDirectory(dataDirectory);
    string retained = Path.Combine(dataDirectory, "keep.txt");
    File.WriteAllText(retained, "persistent user data");

    using var client = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(5) };
    Uri url;
    using (var studio = new BundledStudio(new Terraria.ModLoader.Mod(resources), saveDirectory))
    {
        url = await studio.StartAsync();
        using HttpResponseMessage response = await client.GetAsync(url);
        Require(response.IsSuccessStatusCode && response.Content.Headers.ContentType?.MediaType == "text/html", "production C# launcher serves Studio HTML");
        Require(await studio.StartAsync() == url, "repeated opens reuse the running Studio instance");
        Require(File.Exists(Path.Combine(studioDirectory, "OPEN_INFINICRAFT.bat")), "external opener created beside persistent data");
    }

    try
    {
        using HttpResponseMessage response = await client.GetAsync(url);
        throw new Exception("FAIL: owned Studio listener survived C# disposal");
    }
    catch (HttpRequestException)
    {
        // Expected: graceful shutdown or the bounded process cleanup released the listener.
    }
    Require(File.ReadAllText(retained) == "persistent user data", "process shutdown preserves user data");
    Console.WriteLine("PASS: actual packaged Python startup, browser HTTP response, repeated-open reuse, external opener and owned-process shutdown through production C#.");
}

static byte[] Archive(params (string Path, string Contents)[] entries)
{
    using var memory = new MemoryStream();
    using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, leaveOpen: true))
        foreach (var entry in entries)
        {
            using Stream target = zip.CreateEntry(entry.Path).Open();
            byte[] bytes = Encoding.UTF8.GetBytes(entry.Contents);
            target.Write(bytes);
        }
    return memory.ToArray();
}

static void Require(bool value, string description)
{
    if (!value)
        throw new Exception("FAIL: " + description);
}

static void Reject<T>(Action action) where T : Exception
{
    try { action(); }
    catch (T) { return; }
    throw new Exception("Expected " + typeof(T).Name);
}
