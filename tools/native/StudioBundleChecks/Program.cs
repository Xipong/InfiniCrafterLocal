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
    string personal = Path.Combine(installed, "personal-settings.txt");
    File.WriteAllText(personal, "personal bytes");
    Reject<IOException>(() => StudioBundle.Install(payload, spec, runtimes, CancellationToken.None));
    Require(File.ReadAllText(personal) == "personal bytes" && File.Exists(Path.Combine(installed, spec.Python)), "incomplete runtime and extra userdata preserved on refusal");
    Require(!File.Exists(Path.Combine(installed, spec.EntryPoint)), "repair refusal does not silently rewrite runtime");
    // Restore this fixture explicitly for the subsequent independent upgrade cases.
    File.Delete(personal);
    File.WriteAllText(Path.Combine(installed, spec.EntryPoint), "launcher");

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
    // A completed replacement alone does not retire the working version.
    string oldLauncher = Path.Combine(studio, "OPEN_INFINICRAFT.bat");
    StudioBundle.WriteExternalLauncher(studio, spec);
    string launcherBytes = File.ReadAllText(oldLauncher);
    Reject<InvalidDataException>(() => StudioBundle.Install(missing, Spec(missing), runtimes, CancellationToken.None));
    Require(File.ReadAllText(oldLauncher) == launcherBytes && Directory.Exists(installed), "failed replacement preserves opener and working runtime");
    string models = Path.Combine(temporary, "external-models");
    Directory.CreateDirectory(models);
    File.WriteAllText(Path.Combine(models, "weights.gguf"), "external model bytes");
    File.WriteAllText(Path.Combine(data, "config.env"), "INFINI_SDCPP_MODEL=" + Path.Combine(models, "weights.gguf"));
    File.WriteAllText(Path.Combine(data, "custom-presets.json"), "user presets");

    using (var heldFile = new FileStream(Path.Combine(installed, spec.Python), FileMode.Open, FileAccess.Read, OperatingSystem.IsWindows() ? FileShare.Read : FileShare.None))
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
    {
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
        Require(File.Exists(Path.Combine(installed, spec.EntryPoint)), "busy old runtime is retained without partial deletion");
    }
    string extraDirectory = Path.Combine(installed, "user-empty-folder");
    Directory.CreateDirectory(extraDirectory);
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
    Require(Directory.Exists(extraDirectory) && File.Exists(Path.Combine(installed, spec.Python)), "unknown empty folder prevents retirement");
    Directory.Delete(extraDirectory);
    if (!OperatingSystem.IsWindows())
    {
        string link = Path.Combine(installed, "external-model-link");
        Directory.CreateSymbolicLink(link, models);
        using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
            StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
        Require(File.ReadAllText(Path.Combine(models, "weights.gguf")) == "external model bytes" && Directory.Exists(installed), "linked models never followed by cleanup");
        Directory.Delete(link);
    }
    File.WriteAllText(Path.Combine(installed, "user-added-model.gguf"), "do not delete");
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
    Require(File.ReadAllText(Path.Combine(installed, "user-added-model.gguf")) == "do not delete", "extra content prevents retirement");
    File.Delete(Path.Combine(installed, "user-added-model.gguf"));
    File.WriteAllText(Path.Combine(installed, spec.Python), "modified by user");
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
    Require(File.ReadAllText(Path.Combine(installed, spec.Python)) == "modified by user", "modified content prevents retirement");
    File.WriteAllText(Path.Combine(installed, spec.Python), "interpreter");
    string inventoryBytes = File.ReadAllText(Path.Combine(installed, ".owned-files.json"));
    foreach (string invalid in new[] { "{", "../outside", ".complete" })
    {
        var invalidInventory = JsonSerializer.Deserialize<Dictionary<string, string>>(inventoryBytes)!;
        string firstPath = invalidInventory.Keys.First();
        invalidInventory.Remove(firstPath);
        invalidInventory.Add(invalid, "bad");
        File.WriteAllText(Path.Combine(installed, ".owned-files.json"), invalid == "{" ? invalid : JsonSerializer.Serialize(invalidInventory));
        using var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None);
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
        Require(File.Exists(Path.Combine(installed, spec.Python)), "malformed inventory retained without propagating cleanup failure");
    }
    File.Delete(Path.Combine(installed, ".owned-files.json"));
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
    Require(Directory.Exists(installed), "legacy runtime without inventory retained");
    File.WriteAllText(Path.Combine(installed, ".owned-files.json"), inventoryBytes);
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
    {
        StudioBundle.WriteExternalLauncher(studio, Spec(update));
        StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
    }
    Require(!Directory.Exists(installed) && Directory.Exists(updated), "verified previous version retired after replacement readiness boundary");
    Require(StudioBundle.Install(update, Spec(update), runtimes, CancellationToken.None) == updated, "restart reuses surviving replacement");
    Require(File.ReadAllText(Path.Combine(models, "weights.gguf")) == "external model bytes", "external model bytes unchanged");
    Require(File.ReadAllText(Path.Combine(data, "custom-presets.json")) == "user presets", "custom profiles unchanged");
    Require(File.ReadAllText(Path.Combine(data, "config.env")).EndsWith("weights.gguf", StringComparison.Ordinal), "model reference unchanged");
    // Same cross-process lock covers install, readiness and pruning. A contender
    // cannot install while the first launch still owns that critical section.
    using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
    using (var blocked = new CancellationTokenSource())
    using (var entered = new ManualResetEventSlim())
    {
        Task contender = Task.Run(() =>
        {
            entered.Set();
            Reject<OperationCanceledException>(() => StudioBundle.Install(payload, spec, runtimes, blocked.Token));
        });
        Require(entered.Wait(TimeSpan.FromSeconds(5)), "contending launch entered installer");
        blocked.Cancel();
        Require(contender.Wait(TimeSpan.FromSeconds(5)), "contending launch cancellation bounded");
    }
    using (var firstLaunch = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
    {
        var delayedReady = new LockWaitClock(31, firstLaunch.Dispose);
        using FileStream secondLaunch = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None, delayedReady);
        Require(delayedReady.ElapsedObserved, "second launch waits beyond old 30-second cutoff for first readiness");
    }
    using (var firstLaunch = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
        Reject<IOException>(() => StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None, new LockWaitClock(120, () => { })));
    if (OperatingSystem.IsWindows())
    {
        byte[] executable = File.ReadAllBytes(Path.Combine(Environment.SystemDirectory, "cmd.exe"));
        byte[] runnable = ArchiveFiles(("python/python.exe", executable), ("LocalGenerator/scripts/bundled_studio.py", Encoding.UTF8.GetBytes("old")));
        StudioBundleSpec runnableSpec = Spec(runnable);
        string runningDirectory = StudioBundle.Install(runnable, runnableSpec, runtimes, CancellationToken.None);
        var start = new System.Diagnostics.ProcessStartInfo(Path.Combine(runningDirectory, runnableSpec.Python))
        { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
        start.ArgumentList.Add("/d"); start.ArgumentList.Add("/c"); start.ArgumentList.Add("echo READY & set /p IFC_WAIT=");
        using var running = System.Diagnostics.Process.Start(start)!;
        try
        {
            Require((await running.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5)))?.Trim() == "READY", "old executable actually running");
            using var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None);
            StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
            Require(!running.HasExited && File.Exists(Path.Combine(runningDirectory, runnableSpec.EntryPoint)), "running Windows executable and its runtime are retained");
        }
        finally
        {
            if (!running.HasExited) running.Kill(entireProcessTree: true);
            Require(running.WaitForExit(5000), "owned test executable exited");
        }
        using (var guard = StudioBundle.AcquireInstallationLock(runtimes, CancellationToken.None))
            StudioBundle.RetirePreviousRuntimesLocked(runtimes, Spec(update));
        Require(!Directory.Exists(runningDirectory), "closed executable can be retired on next ready launch");
    }
    else Console.WriteLine("NOT RUN: Windows mapped-executable lock; CPU file-lock and upgrade checks ran.");
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
    using (var first = new BundledStudio(new Terraria.ModLoader.Mod(resources), saveDirectory))
    using (var second = new BundledStudio(new Terraria.ModLoader.Mod(resources), saveDirectory))
    {
        Uri[] addresses = await Task.WhenAll(first.StartAsync(), second.StartAsync()).WaitAsync(TimeSpan.FromSeconds(100));
        Require(addresses[0] != addresses[1], "two mod instances own distinct ready Studio processes");
        foreach (Uri address in addresses)
        {
            using HttpResponseMessage response = await client.GetAsync(address);
            Require(response.IsSuccessStatusCode, "concurrent launches retain both live runtimes");
        }
    }
    Require(File.ReadAllText(retained) == "persistent user data", "process shutdown preserves user data");
    Console.WriteLine("PASS: actual packaged Python startup, browser HTTP response, repeated-open reuse, external opener and owned-process shutdown through production C#.");
}

static byte[] Archive(params (string Path, string Contents)[] entries) =>
    ArchiveFiles(entries.Select(entry => (entry.Path, Encoding.UTF8.GetBytes(entry.Contents))).ToArray());

static byte[] ArchiveFiles(params (string Path, byte[] Contents)[] entries)
{
    using var memory = new MemoryStream();
    using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, leaveOpen: true))
        foreach (var entry in entries)
        {
            using Stream target = zip.CreateEntry(entry.Path).Open();
            target.Write(entry.Contents);
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

// Controlled elapsed time at the real OS file-lock retry boundary, not a wall-clock sleep.
sealed class LockWaitClock(long elapsedSeconds, Action onElapsed) : TimeProvider
{
    private bool _started;
    public bool ElapsedObserved { get; private set; }
    public override long TimestampFrequency => 1;
    public override long GetTimestamp()
    {
        if (!_started) { _started = true; return 0; }
        ElapsedObserved = true;
        onElapsed();
        return elapsedSeconds;
    }
}
