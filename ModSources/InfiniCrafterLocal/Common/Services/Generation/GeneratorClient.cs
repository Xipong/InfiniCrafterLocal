#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

// AGENT MAP: C# <-> LocalGenerator HTTP boundary.
// This class prepares a compact request from Terraria items/world/player state,
// posts it to /combine, accepts only deliverable GeneratedItemData, and attaches
// host asset metadata. It must not invent mechanics, parse prose, or become a
// fallback author; Python authors/validates, C# applies supported fields.
public sealed partial class GeneratorClient
{
    private static readonly HttpClient Http = new() { Timeout = Timeout.InfiniteTimeSpan };
    private sealed record AssetTransportSnapshot(string Transport, string BaseUrl);
    private AssetTransportSnapshot? _assetTransportSnapshot; // null means unobserved, not native
    private int _assetMetadataRefreshQueued;
    private readonly object _assetPublicBaseUrlLock = new();
    private string _cachedGeneratorAssetPublicBaseUrl = "";
    private string _cachedGeneratorAssetTransport = "native";
    private DateTime _nextGeneratorAssetPublicBaseUrlProbeUtc = DateTime.MinValue;
    private static readonly JsonSerializerOptions WireJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public string Endpoint { get; set; } = "http://127.0.0.1:5055/combine";

    private string EndpointGuardKey => "combine:" + (Endpoint ?? "").Trim();

    public bool IsEndpointCoolingDown => LocalHttpQuietFailure.ShouldSkip(EndpointGuardKey);

    public string LastEndpointFailure => LocalHttpQuietFailure.LastMessage(EndpointGuardKey);

    public bool LastRecipeFailureIsFatal { get; private set; }

    public string LastRecipeFailureMessage { get; private set; } = "";

    public string LastRecipeFailurePlayerMessage { get; private set; } = "";

    public int LastRecipeFailureStatusCode { get; private set; }

    public string AssetBaseUrlForSharing(string preferred = "", CancellationToken cancellationToken = default)
    {
        string env = NormalizeAssetBaseUrl(Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL") ?? "");
        if (!string.IsNullOrWhiteSpace(env)) return env;
        cancellationToken.ThrowIfCancellationRequested();
        string advertised = Volatile.Read(ref _assetTransportSnapshot)?.BaseUrl ?? "";
        if (!string.IsNullOrWhiteSpace(advertised)) return advertised;
        preferred = NormalizeAssetBaseUrl(preferred);
        if (!string.IsNullOrWhiteSpace(preferred)) return preferred;
        return GeneratedAssetSyncService.GuessLanBaseUrlFromEndpoint(Endpoint);
    }

    // Explicit blocking discovery belongs to generation workers, never update/commit.
    public void RefreshAssetTransportMetadata(CancellationToken cancellationToken = default)
        => _ = ReadGeneratorAdvertisedAssetBaseUrl(cancellationToken, force: true);

    public void QueueAssetTransportMetadataRefresh()
    {
        if (Interlocked.CompareExchange(ref _assetMetadataRefreshQueued, 1, 0) != 0) return;
        _ = System.Threading.Tasks.Task.Run(() =>
        {
            try { _ = ReadGeneratorAdvertisedAssetBaseUrl(); }
            finally { Volatile.Write(ref _assetMetadataRefreshQueued, 0); }
        });
    }

    public void StampAssetTransportMetadata(GeneratedItemData data, bool refreshBaseUrl = false, CancellationToken cancellationToken = default)
    {
        if (data is null) return;
        cancellationToken.ThrowIfCancellationRequested();
        data.RecipeMeta ??= new RecipeMetaSpec();
        AssetTransportSnapshot? snapshot = Volatile.Read(ref _assetTransportSnapshot);
        if (snapshot is null)
        {
            // Preserve accepted routing until discovery actually observes host mode.
            // Validation still applies to retained/foreign URLs; never issue HTTP here.
            QueueAssetTransportMetadataRefresh();
            string configured = NormalizeAssetBaseUrl(Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL") ?? "");
            if (string.Equals(data.RecipeMeta.AssetTransport, "http", StringComparison.Ordinal))
                data.RecipeMeta.AssetBaseUrl = !string.IsNullOrWhiteSpace(configured) ? configured
                    : NormalizeAssetBaseUrl(data.RecipeMeta.AssetBaseUrl);
            else data.RecipeMeta.AssetBaseUrl = "";
            return;
        }
        data.RecipeMeta.AssetTransport = snapshot.Transport;
        if (!string.Equals(data.RecipeMeta.AssetTransport, "http", StringComparison.Ordinal))
        {
            data.RecipeMeta.AssetBaseUrl = "";
            return;
        }
        if (refreshBaseUrl || string.IsNullOrWhiteSpace(data.RecipeMeta.AssetBaseUrl))
        {
            string env = NormalizeAssetBaseUrl(Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL") ?? "");
            data.RecipeMeta.AssetBaseUrl = !string.IsNullOrWhiteSpace(env) ? env
                : !string.IsNullOrWhiteSpace(snapshot.BaseUrl) ? snapshot.BaseUrl
                : AssetBaseUrlForSharing(data.RecipeMeta.AssetBaseUrl, cancellationToken);
        }
    }

    private void EnterAssetPublicBaseUrlLock(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        while (!Monitor.TryEnter(_assetPublicBaseUrlLock, 50))
            cancellationToken.ThrowIfCancellationRequested();
    }

    private string ReadGeneratorAdvertisedAssetBaseUrl(CancellationToken cancellationToken = default, bool force = false)
    {
        EnterAssetPublicBaseUrlLock(cancellationToken);
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            DateTime now = DateTime.UtcNow;
            if (!force && now < _nextGeneratorAssetPublicBaseUrlProbeUtc)
                return _cachedGeneratorAssetPublicBaseUrl;
            DateTime previousProbe = _nextGeneratorAssetPublicBaseUrlProbeUtc;
            _nextGeneratorAssetPublicBaseUrlProbeUtc = now.AddSeconds(15);
            try
            {
                var combineUri = new Uri(Endpoint);
                var connectUri = new Uri(combineUri, "/mp_connect.json");
                using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                cts.CancelAfter(TimeSpan.FromMilliseconds(1200));
                using var response = Http.GetAsync(connectUri, cts.Token).GetAwaiter().GetResult();
                cancellationToken.ThrowIfCancellationRequested();
                if (!response.IsSuccessStatusCode) return _cachedGeneratorAssetPublicBaseUrl;
                string json = response.Content.ReadAsStringAsync(cts.Token).GetAwaiter().GetResult();
                using JsonDocument doc = JsonDocument.Parse(json);
                cancellationToken.ThrowIfCancellationRequested();
                if (doc.RootElement.ValueKind == JsonValueKind.Object
                    && doc.RootElement.TryGetProperty("multiplayer", out JsonElement multiplayer)
                    && multiplayer.ValueKind == JsonValueKind.Object
                    && multiplayer.TryGetProperty("assetTransport", out JsonElement transport)
                    && transport.ValueKind == JsonValueKind.String
                    && (string.Equals(transport.GetString()?.Trim(), "native", StringComparison.OrdinalIgnoreCase)
                        || string.Equals(transport.GetString()?.Trim(), "http", StringComparison.OrdinalIgnoreCase)))
                {
                    _cachedGeneratorAssetPublicBaseUrl = multiplayer.TryGetProperty("assetPublicBaseUrl", out JsonElement url)
                        && url.ValueKind == JsonValueKind.String
                        ? NormalizeAssetBaseUrl(url.GetString() ?? "")
                        : "";
                    _cachedGeneratorAssetTransport = NormalizeAssetTransport(transport.GetString() ?? "");
                }
                else return _cachedGeneratorAssetPublicBaseUrl;
            }
            catch (Exception error) when (cancellationToken.IsCancellationRequested)
            {
                // Retirement did not observe an unavailable provider. Keep the
                // accepted cache, including when a transport error races cancel.
                _nextGeneratorAssetPublicBaseUrlProbeUtc = previousProbe;
                throw new OperationCanceledException("Craft metadata request cancelled.", error, cancellationToken);
            }
            catch
            {
                // Unavailable/malformed discovery observes no transport mode.
                return _cachedGeneratorAssetPublicBaseUrl;
            }
            Volatile.Write(ref _assetTransportSnapshot, new(_cachedGeneratorAssetTransport, _cachedGeneratorAssetPublicBaseUrl));
            return _cachedGeneratorAssetPublicBaseUrl;
        }
        finally { Monitor.Exit(_assetPublicBaseUrlLock); }
    }

    private static string NormalizeAssetBaseUrl(string value)
    {
        value = (value ?? "").Trim().TrimEnd('/');
        if (string.IsNullOrWhiteSpace(value) || value.Contains("x.x.x", StringComparison.OrdinalIgnoreCase))
            return "";
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri) || (uri.Scheme != "http" && uri.Scheme != "https"))
            return "";
        if (IPAddress.TryParse(uri.Host, out IPAddress? ip))
        {
            byte[] bytes = ip.GetAddressBytes();
            if (ip.IsIPv6Multicast || ip.Equals(IPAddress.Any) || ip.Equals(IPAddress.IPv6Any))
                return "";
            if (bytes.Length == 4 && ((bytes[0] == 169 && bytes[1] == 254) || bytes[0] == 0 || bytes[0] >= 224))
                return "";
            if (IPAddress.IsLoopback(ip) && Main.netMode != NetmodeID.SinglePlayer)
                return "";
        }
        return uri.GetLeftPart(UriPartial.Authority);
    }

    private static string NormalizeAssetTransport(string value)
        => string.Equals((value ?? "").Trim(), "http", StringComparison.OrdinalIgnoreCase) ? "http" : "native";

    private enum GenerationFailureKind
    {
        None,
        Transient,
        FatalRecipe
    }

    private sealed class GenerationAttemptResult
    {
        public GeneratedItemData? Data { get; set; }
        public GenerationFailureKind FailureKind { get; set; } = GenerationFailureKind.None;
        public int StatusCode { get; set; }
        public string Message { get; set; } = "";
        public string PlayerMessage { get; set; } = "";

        public bool HasData => Data is not null;
        public bool IsFatalRecipeFailure => FailureKind == GenerationFailureKind.FatalRecipe;
    }

    public sealed class PreparedGenerationRequest
    {
        // A request survives transport retries, but never its owning craft. The
        // token only retires our HTTP work; Python may finish an admitted craft
        // and keep the completed world recipe available for a later request.
        private readonly CancellationTokenSource _lifetime = new();
        public CancellationToken CancellationToken => _lifetime.Token;
        public void Cancel() => _lifetime.Cancel();

        public string PayloadJson { get; set; } = "{}";
        public string ParentA { get; set; } = "Unknown";
        public string ParentB { get; set; } = "Unknown";
        public Item RefundA { get; set; } = new();
        public Item RefundB { get; set; } = new();
        internal ClientTooltipObservation? ClientTooltipA { get; set; }
        internal ClientTooltipObservation? ClientTooltipB { get; set; }
        // Request-local failure state: concurrent multi-dev lanes must never read
        // another lane's shared LastRecipeFailure snapshot.
        public bool FailureIsFatal { get; set; }
        public int FailureStatusCode { get; set; }
        public string FailureMessage { get; set; } = "";
        public string FailurePlayerMessage { get; set; } = "";
    }

    public PreparedGenerationRequest Prepare(Item a, Item b, Player player, string llmProfileId = "", bool multiDevCraft = false)
        => Prepare(a, b, player, llmProfileId, multiDevCraft, null, null);

    internal PreparedGenerationRequest Prepare(Item a, Item b, Player player, string llmProfileId, bool multiDevCraft,
        ClientTooltipObservation? clientTooltipA, ClientTooltipObservation? clientTooltipB)
    {
        var refundA = a.Clone();
        refundA.stack = 1;
        var refundB = b.Clone();
        refundB.stack = 1;

        string parentA = CraftParentName(a);
        string parentB = CraftParentName(b);

        string payload = JsonSerializer.Serialize(new
        {
            itemA = ToWireItem(a, player, clientTooltipA),
            itemB = ToWireItem(b, player, clientTooltipB),
            player = player.name,
            worldId = Main.worldID,
            worldName = Main.worldName,
            modVersion = InfiniCrafterLocalMod.ModVersion,
            multiplayer = Main.netMode != NetmodeID.SinglePlayer,
            craftInputPolicy = "base_item_stats_ignore_prefixes",
            multiDevCraft,
            llmProfileId = multiDevCraft ? (llmProfileId ?? "").Trim().ToLowerInvariant() : ""
        }, WireJsonOptions);

        return new PreparedGenerationRequest
        {
            PayloadJson = payload,
            ParentA = parentA,
            ParentB = parentB,
            RefundA = refundA,
            RefundB = refundB
        };
    }

    public GeneratedItemData? GeneratePreparedBlocking(PreparedGenerationRequest request)
    {
        if (request.CancellationToken.IsCancellationRequested)
            return null;
        LastRecipeFailureIsFatal = false;
        LastRecipeFailureMessage = "";
        LastRecipeFailurePlayerMessage = "";
        LastRecipeFailureStatusCode = 0;
        request.FailureIsFatal = false;
        request.FailureStatusCode = 0;
        request.FailureMessage = "";
        request.FailurePlayerMessage = "";

        if (LocalHttpQuietFailure.ShouldSkip(EndpointGuardKey))
            return null;

        int attempts = Math.Max(1, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS"), out int envAttempts) ? envAttempts : 2);
        int timeoutSeconds = Math.Max(15, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_TIMEOUT_SECONDS"), out int envTimeout) ? envTimeout : 900);
        int cacheTimeoutSeconds = Math.Max(2, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_HTTP_TIMEOUT_SECONDS"), out int envCacheTimeout) ? envCacheTimeout : 12);
        int cacheRecoverySeconds = Math.Max(0, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS"), out int envCacheRecovery) ? envCacheRecovery : 90);

        // Fast cache-first recovery path. If a previous long generation finished after
        // the Terraria client timed out, the world recipe file already exists and should
        // be delivered without starting another generation.
        var cached = GeneratePreparedCacheOnly(request, cacheTimeoutSeconds);
        if (request.CancellationToken.IsCancellationRequested)
            return null;
        if (cached is not null)
            return cached;

        for (int attempt = 1; attempt <= attempts && !request.CancellationToken.IsCancellationRequested; attempt++)
        {
            var result = GeneratePreparedBlockingOnce(request, timeoutSeconds);
            if (request.CancellationToken.IsCancellationRequested)
                return null;
            if (result.HasData)
                return result.Data;

            // Explicit HTTP failure classes are authoritative. Do not turn 422/424
            // validation or visual-delivery failures into a blind cache-poll loop;
            // ingredients should be refunded and the user can manually craft again.
            if (result.IsFatalRecipeFailure)
            {
                LastRecipeFailureIsFatal = true;
                LastRecipeFailureStatusCode = result.StatusCode;
                LastRecipeFailureMessage = result.Message;
                LastRecipeFailurePlayerMessage = result.PlayerMessage;
                request.FailureIsFatal = true;
                request.FailureStatusCode = result.StatusCode;
                request.FailureMessage = result.Message;
                request.FailurePlayerMessage = result.PlayerMessage;
                return null;
            }

            // A local HTTP request can die exactly while the Python side is writing the
            // final JSON response. In that case the generated recipe is already on disk,
            // so do not immediately fail/restart: poll cache-only for a short recovery
            // window and return the completed item if it appears.
            cached = PollCacheOnlyUntilReady(request, cacheTimeoutSeconds, cacheRecoverySeconds);
            if (request.CancellationToken.IsCancellationRequested)
                return null;
            if (cached is not null)
                return cached;
        }
        return null;
    }

    private static string WithCacheOnlyFlag(string payloadJson)
    {
        var payload = System.Text.Json.Nodes.JsonNode.Parse(payloadJson ?? "{}") as System.Text.Json.Nodes.JsonObject
            ?? throw new JsonException("Craft request must be a JSON object");
        payload["cacheOnly"] = true;
        return payload.ToJsonString(WireJsonOptions);
    }

    private GeneratedItemData? PollCacheOnlyUntilReady(PreparedGenerationRequest request, int requestTimeoutSeconds, int totalSeconds)
    {
        if (request.CancellationToken.IsCancellationRequested)
            return null;
        if (totalSeconds <= 0)
            return GeneratePreparedCacheOnly(request, requestTimeoutSeconds);

        DateTime deadline = DateTime.UtcNow.AddSeconds(totalSeconds);
        while (DateTime.UtcNow <= deadline && !request.CancellationToken.IsCancellationRequested)
        {
            var cached = GeneratePreparedCacheOnly(request, requestTimeoutSeconds);
            if (cached is not null)
                return cached;

            try
            {
                System.Threading.Tasks.Task.Delay(2000, request.CancellationToken).GetAwaiter().GetResult();
            }
            catch (OperationCanceledException) when (request.CancellationToken.IsCancellationRequested)
            {
                return null;
            }
        }

        return GeneratePreparedCacheOnly(request, requestTimeoutSeconds);
    }

    private static bool IsDeliverableGeneratedData(GeneratedItemData? data)
    {
        if (data is null || string.IsNullOrWhiteSpace(data.Name) || string.IsNullOrWhiteSpace(data.Id))
            return false;

        string id = (data.Id ?? "").Trim();
        if (string.Equals(id, "placeholder", StringComparison.OrdinalIgnoreCase))
            return false;

        string sourceMode = (data.SourceMode ?? "").Trim().ToLowerInvariant();
        if (sourceMode == "fallback" || sourceMode.StartsWith("fallback_", StringComparison.Ordinal) || sourceMode is "failed" or "placeholder")
            return false;

        return true;
    }

    private GeneratedItemData? GeneratePreparedCacheOnly(PreparedGenerationRequest request, int timeoutSeconds)
    {
        try
        {
            request.CancellationToken.ThrowIfCancellationRequested();
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(request.CancellationToken);
            cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
            using var body = new StringContent(WithCacheOnlyFlag(request.PayloadJson), Encoding.UTF8, "application/json");
            using var response = Http.PostAsync(Endpoint, body, cts.Token).GetAwaiter().GetResult();
            if (!response.IsSuccessStatusCode)
                return null;
            LocalHttpQuietFailure.Clear(EndpointGuardKey);

            var json = response.Content.ReadAsStringAsync(cts.Token).GetAwaiter().GetResult();
            var data = GeneratedItemData.FromJson(json);
            if (data is null || !IsDeliverableGeneratedData(data))
                return null;
            request.CancellationToken.ThrowIfCancellationRequested();
            Normalize(data, request.ParentA, request.ParentB);
            GeneratedItemRegistryService.StampCurrentWorld(data);
            RefreshAssetTransportMetadata(request.CancellationToken);
            StampAssetTransportMetadata(data, refreshBaseUrl: true, cancellationToken: request.CancellationToken);
            request.CancellationToken.ThrowIfCancellationRequested();
            data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
            return data;
        }
        catch (Exception ex)
        {
            if (!request.CancellationToken.IsCancellationRequested && LocalHttpQuietFailure.IsExpectedOffline(ex))
                LocalHttpQuietFailure.Record(EndpointGuardKey, ex, TimeSpan.FromSeconds(45));
            return null;
        }
    }

    private static string ReadErrorMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json ?? "{}");
            var root = doc.RootElement;
            string code = "";
            string message = "";
            if (root.TryGetProperty("error", out var errorProp) && errorProp.ValueKind == JsonValueKind.String)
                code = errorProp.GetString() ?? "";
            if (root.TryGetProperty("status", out var statusProp) && statusProp.ValueKind == JsonValueKind.String && string.IsNullOrWhiteSpace(code))
                code = statusProp.GetString() ?? "";
            if (root.TryGetProperty("message", out var messageProp) && messageProp.ValueKind == JsonValueKind.String)
                message = messageProp.GetString() ?? "";
            if (!string.IsNullOrWhiteSpace(code) && !string.IsNullOrWhiteSpace(message))
                return code + ": " + message;
            if (!string.IsNullOrWhiteSpace(code))
                return code;
            if (!string.IsNullOrWhiteSpace(message))
                return message;
        }
        catch
        {
        }
        return "HTTP combine failure";
    }

    private static string ReadPlayerMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json ?? "{}");
            var root = doc.RootElement;
            if (root.TryGetProperty("playerMessage", out var playerProp) && playerProp.ValueKind == JsonValueKind.String)
                return playerProp.GetString() ?? "";
        }
        catch
        {
        }
        return "";
    }

    private static bool IsFatalRecipeStatusCode(int statusCode)
    {
        // 422 = LLM/authored item plan invalid after repair. 424 = dependency failed
        // (planner/visual delivery). 409 = generator busy. These are explicit server
        // responses, not lost-success races, so the Terraria client should not spam
        // cacheOnly recovery for the same attempt.
        return statusCode is 409 or 422 or 424 or 428 or 500;
    }

    private GenerationAttemptResult GeneratePreparedBlockingOnce(PreparedGenerationRequest request, int timeoutSeconds)
    {
        try
        {
            request.CancellationToken.ThrowIfCancellationRequested();
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(request.CancellationToken);
            cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
            using var body = new StringContent(request.PayloadJson, Encoding.UTF8, "application/json");
            using var response = Http.PostAsync(Endpoint, body, cts.Token).GetAwaiter().GetResult();
            string responseJson = response.Content.ReadAsStringAsync(cts.Token).GetAwaiter().GetResult();
            if (!response.IsSuccessStatusCode)
            {
                int statusCode = (int)response.StatusCode;
                return new GenerationAttemptResult
                {
                    FailureKind = IsFatalRecipeStatusCode(statusCode) ? GenerationFailureKind.FatalRecipe : GenerationFailureKind.Transient,
                    StatusCode = statusCode,
                    Message = ReadErrorMessage(responseJson),
                    PlayerMessage = ReadPlayerMessage(responseJson)
                };
            }
            LocalHttpQuietFailure.Clear(EndpointGuardKey);

            var data = GeneratedItemData.FromJson(responseJson);
            if (data is null || !IsDeliverableGeneratedData(data))
            {
                return new GenerationAttemptResult
                {
                    FailureKind = GenerationFailureKind.FatalRecipe,
                    StatusCode = 200,
                    Message = "LocalGenerator returned a non-deliverable generated item payload",
                    PlayerMessage = "Generation failed: LocalGenerator returned a broken item payload. Try again."
                };
            }
            request.CancellationToken.ThrowIfCancellationRequested();
            Normalize(data, request.ParentA, request.ParentB);
            GeneratedItemRegistryService.StampCurrentWorld(data);
            RefreshAssetTransportMetadata(request.CancellationToken);
            StampAssetTransportMetadata(data, refreshBaseUrl: true, cancellationToken: request.CancellationToken);
            request.CancellationToken.ThrowIfCancellationRequested();
            data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
            return new GenerationAttemptResult { Data = data, FailureKind = GenerationFailureKind.None, StatusCode = 200 };
        }
        catch (OperationCanceledException) when (request.CancellationToken.IsCancellationRequested)
        {
            // Retiring one lane is not an offline endpoint and must not cool
            // down other live crafts sharing the same generator.
            return new GenerationAttemptResult { FailureKind = GenerationFailureKind.Transient };
        }
        catch (OperationCanceledException ex)
        {
            LocalHttpQuietFailure.Record(EndpointGuardKey, ex, TimeSpan.FromSeconds(45));
            return new GenerationAttemptResult { FailureKind = GenerationFailureKind.Transient, Message = ex.Message };
        }
        catch (Exception ex)
        {
            if (!request.CancellationToken.IsCancellationRequested && LocalHttpQuietFailure.IsExpectedOffline(ex))
                LocalHttpQuietFailure.Record(EndpointGuardKey, ex, TimeSpan.FromSeconds(45));
            return new GenerationAttemptResult { FailureKind = GenerationFailureKind.Transient, Message = ex.Message };
        }
    }

    private static void Normalize(GeneratedItemData data, Item a, Item b) => Normalize(data, CraftParentName(a), CraftParentName(b));

    private static void Normalize(GeneratedItemData data, string parentA, string parentB)
    {
        data.Normalize();
        if (data.ParentA == "Unknown") data.ParentA = parentA;
        if (data.ParentB == "Unknown") data.ParentB = parentB;
    }
}
