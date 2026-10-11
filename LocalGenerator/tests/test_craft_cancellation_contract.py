"""Portable source guards only; real transport behavior lives in registered C# checks."""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_csharp_contracts import method_body, stripped

SOURCES = ROOT / "ModSources/InfiniCrafterLocal/Common"


def source(name):
    return (SOURCES / name).read_text(encoding="utf-8")


def test_craft_retirement_signals_request_before_dropping_ownership():
    single = method_body(source("Players/InfiniCraftPlayer.CraftState.cs"), "ClearCraft")
    assert single.index("_request?.Cancel()") < single.index("_request = null")
    multi = source("Players/InfiniCraftPlayer.MultiDev.cs")
    for name in ("TryCancelExtraServerCraft", "AbortMultiDevCraftsForWorldExit"):
        body = method_body(multi, name)
        assert body.index("job.Request.Cancel()") < body.index("_multiDevJobs[slot] = null")
    reset = method_body(multi, "InitializeMultiDevCraftState")
    assert reset.index("job?.Request?.Cancel()") < reset.index("_multiDevJobs[0] = null")


def test_transport_uses_request_lifetime_for_both_posts_and_recovery():
    client = source("Services/GeneratorClient.cs")
    for name in ("GeneratePreparedCacheOnly", "GeneratePreparedBlockingOnce"):
        body = stripped(method_body(client, name))
        assert "CreateLinkedTokenSource(request.CancellationToken)" in body
        assert body.index("ThrowIfCancellationRequested()") < body.index("Http.PostAsync(")
        assert "cts.CancelAfter(" in body
        assert "ReadAsStringAsync(cts.Token)" in body
        assert "!request.CancellationToken.IsCancellationRequested && LocalHttpQuietFailure.IsExpectedOffline(ex)" in body
    recovery = stripped(method_body(client, "PollCacheOnlyUntilReady"))
    assert "Task.Delay(2000, request.CancellationToken)" in recovery
    assert "Thread.Sleep" not in recovery
    entry = stripped(method_body(client, "GeneratePreparedBlocking"))
    assert entry.index("IsCancellationRequested") < entry.index("GeneratePreparedCacheOnly(")
    assert re.search(r"for\s*\([^;]+;[^;]+!request.CancellationToken.IsCancellationRequested;", entry)


def test_native_craft_cancellation_checks_are_registered():
    project = ET.parse(ROOT / "tools/EngineRuntimeChecks.csproj")
    assert any(row.attrib.get("Include") == "EngineRuntimeChecks.CraftCancellation.cs" for row in project.iter("Compile"))
    runner = (ROOT / "tools/EngineRuntimeChecks.cs").read_text(encoding="utf-8")
    checks = (ROOT / "tools/EngineRuntimeChecks.CraftCancellation.cs").read_text(encoding="utf-8")
    for name in ("CraftCancellationRetiresAllOwners", "CraftCancellationInterruptsHttpAndRecovery", "CraftCancellationKeepsLiveRetryAndDelivery", "CraftCancellationRetiresMetadataWaiters"):
        assert re.search(r"private static void " + name + r"\(\)", checks)
        assert re.search(r'\("[^"]+", ' + name + r"\)", runner)


def test_metadata_probe_and_shared_lock_keep_request_cancellation_local():
    client = source("Services/GeneratorClient.cs")
    probe = stripped(method_body(client, "ReadGeneratorAdvertisedAssetBaseUrl"))
    assert "CreateLinkedTokenSource(cancellationToken)" in probe
    assert "EnterAssetPublicBaseUrlLock(cancellationToken)" in probe
    assert "Monitor.Exit(_assetPublicBaseUrlLock)" in probe
    assert "_nextGeneratorAssetPublicBaseUrlProbeUtc = previousProbe" in probe
    assert "catch (Exception error) when (cancellationToken.IsCancellationRequested)" in probe
    guard = stripped(method_body(client, "EnterAssetPublicBaseUrlLock"))
    assert "Monitor.TryEnter(_assetPublicBaseUrlLock, 50)" in guard
    assert "ThrowIfCancellationRequested()" in guard
    for name in ("GeneratePreparedCacheOnly", "GeneratePreparedBlockingOnce"):
        body = stripped(method_body(client, name))
        assert "RefreshAssetTransportMetadata(request.CancellationToken)" in body
        assert "cancellationToken: request.CancellationToken" in body
