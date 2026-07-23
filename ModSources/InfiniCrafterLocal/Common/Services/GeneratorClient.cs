#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text.RegularExpressions;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// AGENT MAP: C# <-> LocalGenerator HTTP boundary.
// This class prepares a compact request from Terraria items/world/player state,
// posts it to /combine, accepts only deliverable GeneratedItemData, and attaches
// host asset metadata. It must not invent mechanics, parse prose, or become a
// fallback author; Python authors/validates, C# applies supported fields.
public sealed class GeneratorClient
{
    private static readonly HttpClient Http = new() { Timeout = Timeout.InfiniteTimeSpan };
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

    public string AssetBaseUrlForSharing(string preferred = "")
    {
        string env = NormalizeAssetBaseUrl(Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL") ?? "");
        if (!string.IsNullOrWhiteSpace(env)) return env;
        string advertised = ReadGeneratorAdvertisedAssetBaseUrl();
        if (!string.IsNullOrWhiteSpace(advertised)) return advertised;
        preferred = NormalizeAssetBaseUrl(preferred);
        if (!string.IsNullOrWhiteSpace(preferred)) return preferred;
        return GeneratedAssetSyncService.GuessLanBaseUrlFromEndpoint(Endpoint);
    }

    public string AssetTransportForSharing()
    {
        _ = ReadGeneratorAdvertisedAssetBaseUrl();
        lock (_assetPublicBaseUrlLock)
            return _cachedGeneratorAssetTransport;
    }

    public void RefreshAssetTransportMetadata()
    {
        lock (_assetPublicBaseUrlLock)
            _nextGeneratorAssetPublicBaseUrlProbeUtc = DateTime.MinValue;
        _ = ReadGeneratorAdvertisedAssetBaseUrl();
    }

    public void StampAssetTransportMetadata(GeneratedItemData data, bool refreshBaseUrl = false)
    {
        if (data is null) return;
        data.RecipeMeta ??= new RecipeMetaSpec();
        data.RecipeMeta.AssetTransport = AssetTransportForSharing();
        if (!string.Equals(data.RecipeMeta.AssetTransport, "http", StringComparison.Ordinal))
        {
            data.RecipeMeta.AssetBaseUrl = "";
            return;
        }
        if (refreshBaseUrl || string.IsNullOrWhiteSpace(data.RecipeMeta.AssetBaseUrl))
            data.RecipeMeta.AssetBaseUrl = AssetBaseUrlForSharing(data.RecipeMeta.AssetBaseUrl);
    }

    private string ReadGeneratorAdvertisedAssetBaseUrl()
    {
        lock (_assetPublicBaseUrlLock)
        {
            DateTime now = DateTime.UtcNow;
            if (now < _nextGeneratorAssetPublicBaseUrlProbeUtc)
                return _cachedGeneratorAssetPublicBaseUrl;
            _nextGeneratorAssetPublicBaseUrlProbeUtc = now.AddSeconds(15);
            try
            {
                var combineUri = new Uri(Endpoint);
                var connectUri = new Uri(combineUri, "/mp_connect.json");
                using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(1200));
                using var response = Http.GetAsync(connectUri, cts.Token).GetAwaiter().GetResult();
                if (!response.IsSuccessStatusCode)
                {
                    _cachedGeneratorAssetTransport = "native";
                    return _cachedGeneratorAssetPublicBaseUrl = "";
                }
                string json = response.Content.ReadAsStringAsync(cts.Token).GetAwaiter().GetResult();
                using JsonDocument doc = JsonDocument.Parse(json);
                if (doc.RootElement.ValueKind == JsonValueKind.Object
                    && doc.RootElement.TryGetProperty("multiplayer", out JsonElement multiplayer)
                    && multiplayer.ValueKind == JsonValueKind.Object)
                {
                    _cachedGeneratorAssetPublicBaseUrl = multiplayer.TryGetProperty("assetPublicBaseUrl", out JsonElement url)
                        && url.ValueKind == JsonValueKind.String
                        ? NormalizeAssetBaseUrl(url.GetString() ?? "")
                        : "";
                    _cachedGeneratorAssetTransport = multiplayer.TryGetProperty("assetTransport", out JsonElement transport)
                        && transport.ValueKind == JsonValueKind.String
                        ? NormalizeAssetTransport(transport.GetString() ?? "")
                        : "native";
                }
                else
                {
                    _cachedGeneratorAssetPublicBaseUrl = "";
                    _cachedGeneratorAssetTransport = "native";
                }
            }
            catch
            {
                _cachedGeneratorAssetPublicBaseUrl = "";
                _cachedGeneratorAssetTransport = "native";
            }
            return _cachedGeneratorAssetPublicBaseUrl;
        }
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
        public string PayloadJson { get; set; } = "{}";
        public string ParentA { get; set; } = "Unknown";
        public string ParentB { get; set; } = "Unknown";
        public Item RefundA { get; set; } = new();
        public Item RefundB { get; set; } = new();
    }

    public PreparedGenerationRequest Prepare(Item a, Item b, Player player)
    {
        var refundA = a.Clone();
        refundA.stack = 1;
        var refundB = b.Clone();
        refundB.stack = 1;

        string parentA = CraftParentName(a);
        string parentB = CraftParentName(b);

        string payload = JsonSerializer.Serialize(new
        {
            itemA = ToWireItem(a, player),
            itemB = ToWireItem(b, player),
            player = player.name,
            worldId = Main.worldID,
            worldName = Main.worldName,
            modVersion = InfiniCrafterLocalMod.ModVersion,
            multiplayer = Main.netMode != NetmodeID.SinglePlayer,
            craftInputPolicy = "base_item_stats_ignore_prefixes"
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
        LastRecipeFailureIsFatal = false;
        LastRecipeFailureMessage = "";
        LastRecipeFailurePlayerMessage = "";
        LastRecipeFailureStatusCode = 0;

        if (LocalHttpQuietFailure.ShouldSkip(EndpointGuardKey))
            return null;

        int attempts = Math.Max(1, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS"), out int envAttempts) ? envAttempts : 2);
        int timeoutSeconds = Math.Max(15, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_TIMEOUT_SECONDS"), out int envTimeout) ? envTimeout : 240);
        int cacheTimeoutSeconds = Math.Max(2, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_HTTP_TIMEOUT_SECONDS"), out int envCacheTimeout) ? envCacheTimeout : 12);
        int cacheRecoverySeconds = Math.Max(0, int.TryParse(Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS"), out int envCacheRecovery) ? envCacheRecovery : 90);

        // Fast cache-first recovery path. If a previous long generation finished after
        // the Terraria client timed out, the world recipe file already exists and should
        // be delivered without starting another generation.
        var cached = GeneratePreparedCacheOnly(request, cacheTimeoutSeconds);
        if (cached is not null)
            return cached;

        for (int attempt = 1; attempt <= attempts; attempt++)
        {
            var result = GeneratePreparedBlockingOnce(request, timeoutSeconds);
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
                return null;
            }

            // A local HTTP request can die exactly while the Python side is writing the
            // final JSON response. In that case the generated recipe is already on disk,
            // so do not immediately fail/restart: poll cache-only for a short recovery
            // window and return the completed item if it appears.
            cached = PollCacheOnlyUntilReady(request, cacheTimeoutSeconds, cacheRecoverySeconds);
            if (cached is not null)
                return cached;
        }
        return null;
    }

    private static string WithCacheOnlyFlag(string payloadJson)
    {
        string trimmed = (payloadJson ?? "{}").Trim();
        if (trimmed.EndsWith("}", StringComparison.Ordinal))
            return trimmed[..^1] + ",\"cacheOnly\":true}";
        return "{\"cacheOnly\":true}";
    }

    private GeneratedItemData? PollCacheOnlyUntilReady(PreparedGenerationRequest request, int requestTimeoutSeconds, int totalSeconds)
    {
        if (totalSeconds <= 0)
            return GeneratePreparedCacheOnly(request, requestTimeoutSeconds);

        DateTime deadline = DateTime.UtcNow.AddSeconds(totalSeconds);
        while (DateTime.UtcNow <= deadline)
        {
            var cached = GeneratePreparedCacheOnly(request, requestTimeoutSeconds);
            if (cached is not null)
                return cached;

            Thread.Sleep(2000);
        }

        return GeneratePreparedCacheOnly(request, requestTimeoutSeconds);
    }

    private static bool IsDeliverableGeneratedData(GeneratedItemData? data)
    {
        if (data is null || string.IsNullOrWhiteSpace(data.Name))
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
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
            using var body = new StringContent(WithCacheOnlyFlag(request.PayloadJson), Encoding.UTF8, "application/json");
            using var response = Http.PostAsync(Endpoint, body, cts.Token).GetAwaiter().GetResult();
            if (!response.IsSuccessStatusCode)
                return null;
            LocalHttpQuietFailure.Clear(EndpointGuardKey);

            var json = response.Content.ReadAsStringAsync(cts.Token).GetAwaiter().GetResult();
            var data = GeneratedItemData.FromJson(json);
            if (data is null || !IsDeliverableGeneratedData(data))
                return null;
            Normalize(data, request.ParentA, request.ParentB);
            GeneratedItemRegistryService.StampCurrentWorld(data);
            RefreshAssetTransportMetadata();
            StampAssetTransportMetadata(data, refreshBaseUrl: true);
            data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
            return data;
        }
        catch (Exception ex)
        {
            if (LocalHttpQuietFailure.IsExpectedOffline(ex))
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
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
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
                    PlayerMessage = "Generation failed: LocalGenerator returned a broken item payload. Items were returned; try again."
                };
            }
            Normalize(data, request.ParentA, request.ParentB);
            GeneratedItemRegistryService.StampCurrentWorld(data);
            RefreshAssetTransportMetadata();
            StampAssetTransportMetadata(data, refreshBaseUrl: true);
            data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
            return new GenerationAttemptResult { Data = data, FailureKind = GenerationFailureKind.None, StatusCode = 200 };
        }
        catch (OperationCanceledException ex)
        {
            LocalHttpQuietFailure.Record(EndpointGuardKey, ex, TimeSpan.FromSeconds(45));
            return new GenerationAttemptResult { FailureKind = GenerationFailureKind.Transient, Message = ex.Message };
        }
        catch (Exception ex)
        {
            if (LocalHttpQuietFailure.IsExpectedOffline(ex))
                LocalHttpQuietFailure.Record(EndpointGuardKey, ex, TimeSpan.FromSeconds(45));
            return new GenerationAttemptResult { FailureKind = GenerationFailureKind.Transient, Message = ex.Message };
        }
    }

    public GeneratedItemData? GenerateBlocking(Item a, Item b, Player player)
    {
        return GeneratePreparedBlocking(Prepare(a, b, player));
    }

    private static object ToWireItem(Item item, Player? player = null)
    {
        GeneratedItemData? existing = item.ModItem is GeneratedItem generated ? generated.Data : null;
        Item craftItem = CraftIdentityItem(item, existing);
        int originalPrefix = SafePrefix(item);
        bool prefixIgnored = originalPrefix != InfiniTerrariaSentinels.NoPrefix;
        var autoFeatures = AutoFeaturesFromItem(craftItem).ToArray();
        var nameTokens = NameTokens(craftItem).ToArray();
        string sourceMod = SourceModName(craftItem);
        string internalName = InternalName(craftItem);
        return new
        {
            id = craftItem.type,
            name = existing?.Name ?? craftItem.Name,
            sourceMod,
            internalName,
            fullName = sourceMod + "/" + internalName,
            prefix = InfiniTerrariaSentinels.NoPrefix,
            originalPrefix,
            prefixIgnored,
            damage = craftItem.damage,
            useTime = craftItem.useTime,
            useAnimation = craftItem.useAnimation,
            useStyle = craftItem.useStyle,
            reuseDelay = craftItem.reuseDelay,
            channel = craftItem.channel,
            noMelee = craftItem.noMelee,
            noUseGraphic = craftItem.noUseGraphic,
            autoReuse = craftItem.autoReuse,
            useTurn = craftItem.useTurn,
            rare = craftItem.rare,
            rarityDetails = RarityDetailsFromItem(craftItem),
            value = craftItem.value,
            consumable = craftItem.consumable,
            material = craftItem.material,
            accessory = craftItem.accessory,
            maxStack = craftItem.maxStack,
            stack = item.stack,
            createTile = craftItem.createTile,
            createWall = craftItem.createWall,
            defense = craftItem.defense,
            headSlot = craftItem.headSlot,
            bodySlot = craftItem.bodySlot,
            legSlot = craftItem.legSlot,
            pickPower = craftItem.pick,
            axePower = craftItem.axe,
            hammerPower = craftItem.hammer,
            healLife = craftItem.healLife,
            healMana = craftItem.healMana,
            manaCost = craftItem.mana,
            ammo = craftItem.ammo,
            useAmmo = craftItem.useAmmo,
            shoot = craftItem.shoot,
            shootSpeed = craftItem.shootSpeed,
            knockback = craftItem.knockBack,
            bait = craftItem.bait,
            fishingPole = craftItem.fishingPole,
            damageClass = DamageClassName(craftItem),
            damageClassFullName = DamageClassFullName(craftItem),
            shootProjectileFullName = ProjectileFullName(craftItem.shoot),
            moddedOrigin = sourceMod != "Terraria",
            directProjectileRaw = DirectProjectileRawFromItem(craftItem),
            effectiveProjectileRaw = EffectiveProjectileRawFromItem(craftItem, player),
            ammoRaw = AmmoRawFromItem(craftItem, player),
            // Only generated items carry authored design tags. Vanilla/modded parents do not get fake semantic tags.
            tags = existing?.Tags is { Length: > 0 } ? existing.Tags : Array.Empty<string>(),
            runtimeFacts = RuntimeFactsFromItem(craftItem),
            autoFeatures,
            nameTokens,
            canonical = existing?.Canonical ?? CanonicalFromItem(craftItem, autoFeatures),
            fingerprint = FingerprintFromItem(craftItem, sourceMod, internalName, autoFeatures, nameTokens, existing, originalPrefix),
            generatedData = existing,
            craftInput = new
            {
                prefixIgnored,
                originalPrefix,
                normalizedStats = "base_item_defaults_without_reforge_prefix",
                note = "Terraria reforges/prefixes are intentionally ignored for InfiniCraft recipes; original items/refunds keep their prefix."
            }
        };
    }

    private static void Normalize(GeneratedItemData data, Item a, Item b) => Normalize(data, CraftParentName(a), CraftParentName(b));

    private static string CraftParentName(Item item)
    {
        GeneratedItemData? existing = item.ModItem is GeneratedItem generated ? generated.Data : null;
        if (!string.IsNullOrWhiteSpace(existing?.Name))
            return existing!.Name;
        return CraftIdentityItem(item, existing).Name;
    }

    private static int SafePrefix(Item item)
    {
        try { return item?.prefix ?? InfiniTerrariaSentinels.NoPrefix; } catch { return InfiniTerrariaSentinels.NoPrefix; }
    }

    private static Item CraftIdentityItem(Item item, GeneratedItemData? existing = null)
    {
        // InfiniCraft recipes use the base item identity/stats. Terraria prefixes/reforges
        // (Legendary, Zealous/Пылкий, Godly, etc.) are per-instance modifiers and must not
        // bias the LLM, balance tier, recipe cache key, or parent display name.
        // The real consumed/refunded Item clone is kept elsewhere, so this normalization is
        // request-only and does not delete the player's reforge.
        if (item is null || item.IsAir)
        {
            var air = new Item();
            air.TurnToAir();
            return air;
        }

        if (existing is not null)
        {
            Item clone = item.Clone();
            clone.stack = item.stack;
            try
            {
                if (clone.prefix != InfiniTerrariaSentinels.NoPrefix)
                    clone.Prefix(InfiniTerrariaSentinels.NoPrefix);
            }
            catch { }
            return clone;
        }

        try
        {
            Item baseItem = new();
            baseItem.SetDefaults(item.type);
            baseItem.stack = item.stack;
            return baseItem;
        }
        catch
        {
            Item clone = item.Clone();
            clone.stack = item.stack;
            try
            {
                if (clone.prefix != InfiniTerrariaSentinels.NoPrefix)
                    clone.Prefix(InfiniTerrariaSentinels.NoPrefix);
            }
            catch { }
            return clone;
        }
    }

    private static void Normalize(GeneratedItemData data, string parentA, string parentB)
    {
        data.Normalize();
        if (data.ParentA == "Unknown") data.ParentA = parentA;
        if (data.ParentB == "Unknown") data.ParentB = parentB;
        if (string.IsNullOrWhiteSpace(data.Name)) return;
        if (string.IsNullOrWhiteSpace(data.Id)) data.Id = Guid.NewGuid().ToString("N")[..12];
    }

    private static object FingerprintFromItem(Item item, string sourceMod, string internalName, string[] autoFeatures, string[] nameTokens, GeneratedItemData? existing, int originalPrefix = 0)
    {
        return new
        {
            sourceMod,
            internalName,
            fullName = sourceMod + "/" + internalName,
            isVanilla = item.ModItem is null,
            type = item.type,
            name = existing?.Name ?? item.Name,
            prefix = InfiniTerrariaSentinels.NoPrefix,
            originalPrefix,
            prefixIgnored = originalPrefix != InfiniTerrariaSentinels.NoPrefix,
            damage = item.damage,
            damageClass = DamageClassName(item),
            knockback = item.knockBack,
            useStyle = item.useStyle,
            useTime = item.useTime,
            useAnimation = item.useAnimation,
            rare = item.rare,
            rarityDetails = RarityDetailsFromItem(item),
            value = item.value,
            maxStack = item.maxStack,
            consumable = item.consumable,
            accessory = item.accessory,
            defense = item.defense,
            headSlot = item.headSlot,
            bodySlot = item.bodySlot,
            legSlot = item.legSlot,
            createTile = item.createTile,
            createWall = item.createWall,
            pickPower = item.pick,
            axePower = item.axe,
            hammerPower = item.hammer,
            bait = item.bait,
            fishingPole = item.fishingPole,
            healLife = item.healLife,
            healMana = item.healMana,
            manaCost = item.mana,
            ammo = item.ammo,
            useAmmo = item.useAmmo,
            shoot = item.shoot,
            shootSpeed = item.shootSpeed,
            directProjectileRaw = DirectProjectileRawFromItem(item),
            effectiveProjectileRaw = EffectiveProjectileRawFromItem(item, null),
            ammoRaw = AmmoRawFromItem(item, null),
            buffType = item.buffType,
            buffTime = item.buffTime,
            channel = item.channel,
            noMelee = item.noMelee,
            noUseGraphic = item.noUseGraphic,
            useTurn = item.useTurn,
            autoReuse = item.autoReuse,
            runtimeFacts = RuntimeFactsFromItem(item),
            autoFeatures,
            nameTokens
        };
    }


    private static object RuntimeFactsFromItem(Item item)
    {
        return new
        {
            type = item.type,
            damage = item.damage,
            damageClass = DamageClassName(item),
            damageClassFullName = DamageClassFullName(item),
            shootProjectileFullName = ProjectileFullName(item.shoot),
            useStyle = item.useStyle,
            useTime = item.useTime,
            useAnimation = item.useAnimation,
            reuseDelay = item.reuseDelay,
            channel = item.channel,
            noMelee = item.noMelee,
            noUseGraphic = item.noUseGraphic,
            autoReuse = item.autoReuse,
            useTurn = item.useTurn,
            rare = item.rare,
            rarityDetails = RarityDetailsFromItem(item),
            value = item.value,
            maxStack = item.maxStack,
            consumable = item.consumable,
            accessory = item.accessory,
            defense = item.defense,
            headSlot = item.headSlot,
            bodySlot = item.bodySlot,
            legSlot = item.legSlot,
            createTile = item.createTile,
            createWall = item.createWall,
            pickPower = item.pick,
            axePower = item.axe,
            hammerPower = item.hammer,
            bait = item.bait,
            fishingPole = item.fishingPole,
            healLife = item.healLife,
            healMana = item.healMana,
            manaCost = item.mana,
            ammo = item.ammo,
            useAmmo = item.useAmmo,
            shoot = item.shoot,
            shootSpeed = item.shootSpeed,
            knockback = item.knockBack,
            buffType = item.buffType,
            buffTime = item.buffTime,
            material = item.material
        };
    }

    private static IEnumerable<string> NameTokens(Item item)
    {
        string raw = InternalName(item);
        string spaced = Regex.Replace(raw, "([a-z0-9])([A-Z])", "$1 $2");
        spaced += " " + item.Name;
        foreach (Match m in Regex.Matches(spaced.ToLowerInvariant(), "[a-z0-9]+"))
        {
            string token = m.Value.Trim();
            if (token.Length >= 2) yield return token;
        }
    }

    private static string SourceModName(Item item)
    {
        try { return item.ModItem?.Mod?.Name ?? "Terraria"; }
        catch { return "Terraria"; }
    }

    private static string InternalName(Item item)
    {
        try
        {
            if (item.ModItem is not null)
                return item.ModItem.Name;
            string? name = ItemID.Search.GetName(item.type);
            return string.IsNullOrWhiteSpace(name) ? item.type.ToString() : name;
        }
        catch
        {
            return item.type.ToString();
        }
    }

    private static string DamageClassName(Item item)
    {
        try
        {
            if (item.DamageType == DamageClass.Melee) return "melee";
            if (item.DamageType == DamageClass.Ranged) return "ranged";
            if (item.DamageType == DamageClass.Magic) return "magic";
            if (item.DamageType == DamageClass.Summon) return "summon";
            if (item.damage > 0 && item.DamageType != DamageClass.Default && item.DamageType != DamageClass.Generic)
                return "modded";
        }
        catch { }
        return item.damage > 0 ? "generic" : "none";
    }

    private static string DamageClassFullName(Item item)
    {
        try
        {
            return item.DamageType?.GetType().FullName ?? "Terraria.ModLoader.DamageClass";
        }
        catch
        {
            return "unknown";
        }
    }

    private static string ProjectileFullName(int projectileType)
    {
        if (projectileType <= ProjectileID.None) return "";
        try
        {
            Projectile p = new();
            p.SetDefaults(projectileType);
            if (p.ModProjectile is not null)
                return (p.ModProjectile.Mod?.Name ?? "UnknownMod") + "/" + p.ModProjectile.Name;
            string? vanilla = ProjectileID.Search.GetName(projectileType);
            return string.IsNullOrWhiteSpace(vanilla) ? "Terraria/Projectile_" + projectileType : "Terraria/" + vanilla;
        }
        catch { return ""; }
    }


    private sealed class AmmoCandidate
    {
        public Item Item { get; set; } = new();
        public string Source { get; set; } = "runtime_scan";
        public int InventorySlot { get; set; } = -1;
        public int Score { get; set; } = 0;
    }

    private static object? DirectProjectileRawFromItem(Item item)
    {
        if (item.shoot <= ProjectileID.None)
            return null;
        return ProjectileRawSnapshot(item.shoot, item.shootSpeed, "item.shoot", item, -1);
    }

    private static object? EffectiveProjectileRawFromItem(Item item, Player? player)
    {
        // Effective projectile is no longer allowed to silently replace a weapon's own
        // shoot field with the "best" ammo candidate.  Ammo examples are context, not
        // the parent weapon identity: many Terraria/modded weapons have their own shoot
        // mechanics even when useAmmo is set.
        if (item.ammo > AmmoID.None && item.shoot > ProjectileID.None)
            return ProjectileRawSnapshot(item.shoot, item.shootSpeed, "this_ammo_item.shoot", item, -1);

        if (item.shoot > ProjectileID.None)
            return ProjectileRawSnapshot(item.shoot, item.shootSpeed, item.useAmmo > AmmoID.None ? "weapon_item.shoot_field" : "item.shoot", item, -1);

        if (item.useAmmo > AmmoID.None)
        {
            var fallback = FindPlayerAmmoCandidates(item.useAmmo, player, 1).FirstOrDefault()
                ?? FindRepresentativeAmmoCandidates(item.useAmmo, 1).FirstOrDefault();
            if (fallback is not null && fallback.Item.shoot > ProjectileID.None)
                return ProjectileRawSnapshot(fallback.Item.shoot, fallback.Item.shootSpeed, fallback.Source + ".shoot_fallback_no_weapon_shoot", fallback.Item, fallback.InventorySlot);
        }

        return null;
    }

    private static object? AmmoRawFromItem(Item item, Player? player)
    {
        if (item.ammo > AmmoID.None)
        {
            return new
            {
                mode = "this_item_is_ammo",
                ammoId = item.ammo,
                ammoItemRaw = AmmoItemRawSnapshot(item, "parent_item", -1),
                projectileRaw = item.shoot > ProjectileID.None ? ProjectileRawSnapshot(item.shoot, item.shootSpeed, "this_ammo_item.shoot", item, -1) : null
            };
        }

        if (item.useAmmo <= AmmoID.None)
            return null;

        var inventory = FindPlayerAmmoCandidates(item.useAmmo, player, 3);
        var fallback = FindRepresentativeAmmoCandidates(item.useAmmo, 3);
        return new
        {
            mode = "weapon_uses_ammo",
            ammoId = item.useAmmo,
            // This is the weapon's own shoot field.  It may be a default ammo placeholder,
            // or it may be a custom mechanic.  The LLM gets it separately from ammo candidates.
            weaponShootFieldProjectileRaw = item.shoot > ProjectileID.None ? ProjectileRawSnapshot(item.shoot, item.shootSpeed, "weapon_item.shoot_field", item, -1) : null,
            playerInventoryAmmoRaw = inventory.Select(c => AmmoItemRawSnapshot(c.Item, c.Source, c.InventorySlot)).ToArray(),
            playerInventoryProjectileRaw = inventory.Where(c => c.Item.shoot > ProjectileID.None).Select(c => ProjectileRawSnapshot(c.Item.shoot, c.Item.shootSpeed, c.Source + ".shoot", c.Item, c.InventorySlot)).ToArray(),
            fallbackAmmoRaw = fallback.Select(c => AmmoItemRawSnapshot(c.Item, c.Source, c.InventorySlot)).ToArray(),
            fallbackProjectileRaw = fallback.Where(c => c.Item.shoot > ProjectileID.None).Select(c => ProjectileRawSnapshot(c.Item.shoot, c.Item.shootSpeed, c.Source + ".shoot", c.Item, c.InventorySlot)).ToArray()
        };
    }

    private static List<AmmoCandidate> FindPlayerAmmoCandidates(int ammoId, Player? player, int maxCount)
    {
        var outList = new List<AmmoCandidate>();
        if (player is null || ammoId <= ItemID.None)
            return outList;
        try
        {
            for (int i = 0; i < player.inventory.Length; i++)
            {
                Item ammo = player.inventory[i];
                if (ammo is null || ammo.IsAir || ammo.stack <= 0)
                    continue;
                if (ammo.ammo == ammoId && ammo.shoot > ProjectileID.None)
                {
                    outList.Add(new AmmoCandidate
                    {
                        Item = CraftIdentityItem(ammo),
                        Source = "player_inventory_ammo_candidate_base_no_prefix",
                        InventorySlot = i,
                        Score = i
                    });
                    if (outList.Count >= Math.Max(1, maxCount))
                        break;
                }
            }
        }
        catch { }
        return outList;
    }

    private static AmmoCandidate? FindPlayerAmmoCandidate(int ammoId, Player? player)
        => FindPlayerAmmoCandidates(ammoId, player, 1).FirstOrDefault();

    private static List<AmmoCandidate> FindRepresentativeAmmoCandidates(int ammoId, int maxCount)
    {
        var outList = new List<AmmoCandidate>();
        if (ammoId <= AmmoID.None)
            return outList;
        try
        {
            for (int type = InfiniTerrariaSentinels.FirstValidItemType; type < ItemLoader.ItemCount; type++)
            {
                try
                {
                    Item ammo = new();
                    ammo.SetDefaults(type);
                    if (ammo.IsAir || ammo.ammo != ammoId || ammo.shoot <= ProjectileID.None)
                        continue;
                    outList.Add(new AmmoCandidate
                    {
                        Item = ammo,
                        Source = "fallback_basic_ammo_scan",
                        InventorySlot = -1,
                        Score = AmmoCandidateScore(ammo)
                    });
                }
                catch { }
            }
        }
        catch { }
        return outList.OrderBy(c => c.Score).ThenBy(c => c.Item.type).Take(Math.Max(1, maxCount)).ToList();
    }

    private static int AmmoCandidateScore(Item ammo)
    {
        int score = 0;
        string internalName = InternalName(ammo).ToLowerInvariant();
        string displayName = (ammo.Name ?? "").ToLowerInvariant();
        // Fallback ammo is only a neutral raw example for the LLM, not an "ideal" ammo choice.
        // Prefer simple cheap vanilla ammo; avoid endless/infinite and high-tier/modded examples
        // unless no simpler candidates exist.
        if (internalName.Contains("endless") || internalName.Contains("infinite") || displayName.Contains("endless") || displayName.Contains("infinite")) score += 100000;
        if (ammo.ModItem is not null) score += 5000;
        score += Math.Max(0, ammo.rare) * 1000;
        score += Math.Clamp(ammo.value / 5, 0, 20000);
        score += Math.Max(0, ammo.damage) * 25;
        return score;
    }

    private static object AmmoItemRawSnapshot(Item ammo, string source, int inventorySlot)
    {
        return new
        {
            source,
            inventorySlot,
            type = ammo.type,
            name = ammo.Name,
            internalName = InternalName(ammo),
            sourceMod = SourceModName(ammo),
            fullName = SourceModName(ammo) + "/" + InternalName(ammo),
            damage = ammo.damage,
            damageClass = DamageClassName(ammo),
            damageClassFullName = DamageClassFullName(ammo),
            ammo = ammo.ammo,
            useAmmo = ammo.useAmmo,
            shoot = ammo.shoot,
            shootSpeed = ammo.shootSpeed,
            knockback = ammo.knockBack,
            rare = ammo.rare,
            value = ammo.value,
            maxStack = ammo.maxStack,
            stack = ammo.stack,
            consumable = ammo.consumable,
            material = ammo.material
        };
    }

    private static object? ProjectileRawSnapshot(int projectileType, float itemShootSpeed, string source, Item? sourceItem, int inventorySlot)
    {
        if (projectileType <= ProjectileID.None)
            return null;
        try
        {
            Projectile p = new();
            p.SetDefaults(projectileType);
            string sourceMod = "Terraria";
            string internalName = projectileType.ToString();
            try
            {
                ModProjectile? modProjectile = p.ModProjectile;
                if (modProjectile is not null)
                {
                    sourceMod = modProjectile.Mod?.Name ?? "UnknownMod";
                    internalName = modProjectile.Name;
                }
                else
                {
                    string? vanilla = ProjectileID.Search.GetName(projectileType);
                    if (!string.IsNullOrWhiteSpace(vanilla)) internalName = vanilla;
                }
            }
            catch { }

            return new
            {
                source,
                inventorySlot,
                type = projectileType,
                sourceMod,
                internalName,
                fullName = sourceMod + "/" + internalName,
                sourceItemType = sourceItem?.type ?? ItemID.None,
                sourceItemName = sourceItem?.Name ?? "",
                sourceItemInternalName = sourceItem is null ? "" : InternalName(sourceItem),
                sourceItemSourceMod = sourceItem is null ? "" : SourceModName(sourceItem),
                sourceItemAmmo = sourceItem?.ammo ?? AmmoID.None,
                sourceItemUseAmmo = sourceItem?.useAmmo ?? AmmoID.None,
                sourceItemDamage = sourceItem?.damage ?? 0,
                sourceItemDamageClass = sourceItem is null ? "none" : DamageClassName(sourceItem),
                sourceItemShoot = sourceItem?.shoot ?? ProjectileID.None,
                sourceItemShootSpeed = sourceItem?.shootSpeed ?? 0f,
                sourceItemKnockback = sourceItem?.knockBack ?? 0f,
                itemShootSpeed,
                ai0 = p.ai.Length > 0 ? p.ai[0] : 0f,
                ai1 = p.ai.Length > 1 ? p.ai[1] : 0f,
                ai2 = p.ai.Length > 2 ? p.ai[2] : 0f,
                localAI0 = p.localAI.Length > 0 ? p.localAI[0] : 0f,
                localAI1 = p.localAI.Length > 1 ? p.localAI[1] : 0f,
                width = p.width,
                height = p.height,
                scale = p.scale,
                aiStyle = p.aiStyle,
                penetrate = p.penetrate,
                maxPenetrate = p.maxPenetrate,
                timeLeft = p.timeLeft,
                extraUpdates = p.extraUpdates,
                tileCollide = p.tileCollide,
                ignoreWater = p.ignoreWater,
                friendly = p.friendly,
                hostile = p.hostile,
                arrow = p.arrow,
                minion = p.minion,
                sentry = p.sentry,
                minionSlots = p.minionSlots,
                ownerHitCheck = p.ownerHitCheck,
                usesLocalNPCImmunity = p.usesLocalNPCImmunity,
                localNPCHitCooldown = p.localNPCHitCooldown,
                usesIDStaticNPCImmunity = p.usesIDStaticNPCImmunity,
                idStaticNPCHitCooldown = p.idStaticNPCHitCooldown,
                stopsDealingDamageAfterPenetrateHits = p.stopsDealingDamageAfterPenetrateHits,
                light = p.light,
                alpha = p.alpha,
                netImportant = p.netImportant,
                damageClass = p.DamageType == DamageClass.Melee ? "melee" : p.DamageType == DamageClass.Ranged ? "ranged" : p.DamageType == DamageClass.Magic ? "magic" : p.DamageType == DamageClass.Summon ? "summon" : p.DamageType == DamageClass.Generic ? "generic" : "modded",
                damageClassFullName = p.DamageType?.GetType().FullName ?? "unknown",
                framesRaw = SafeProjFrames(projectileType),
                setsRaw = ProjectileSetsRaw(projectileType)
            };
        }
        catch
        {
            return new
            {
                source,
                inventorySlot,
                type = projectileType,
                itemShootSpeed,
                unavailable = true
            };
        }
    }

    private static object ProjectileSetsRaw(int projectileType)
    {
        return new
        {
            trailCacheLength = SafeArrayValue(ProjectileID.Sets.TrailCacheLength, projectileType, 0),
            trailingMode = SafeArrayValue(ProjectileID.Sets.TrailingMode, projectileType, 0),
            // Reflection keeps this compatible across tModLoader versions and modded sets.
            lightPet = SafeProjectileSetValue("LightPet", projectileType),
            minionSacrificable = SafeProjectileSetValue("MinionSacrificable", projectileType),
            homing = SafeProjectileSetValue("Homing", projectileType),
            dontAttachHideToAlpha = SafeProjectileSetValue("DontAttachHideToAlpha", projectileType),
            usesOldTargeting = SafeProjectileSetValue("UsesOldTargeting", projectileType),
            noLiquidDistortion = SafeProjectileSetValue("NoLiquidDistortion", projectileType)
        };
    }

    private static int SafeProjFrames(int projectileType)
    {
        try
        {
            if (projectileType >= ProjectileID.None && projectileType < Main.projFrames.Length)
                return Main.projFrames[projectileType];
        }
        catch { }
        return 0;
    }

    private static int SafeArrayValue(int[] values, int index, int fallback)
    {
        try
        {
            if (index >= 0 && index < values.Length)
                return values[index];
        }
        catch { }
        return fallback;
    }

    private static object? SafeProjectileSetValue(string fieldName, int index)
    {
        try
        {
            var field = typeof(ProjectileID.Sets).GetField(fieldName, System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
            if (field is null) return null;
            object? value = field.GetValue(null);
            if (value is Array arr && index >= 0 && index < arr.Length)
                return arr.GetValue(index);
        }
        catch { }
        return null;
    }

    private static bool TryCreateProjectileDefaults(int projectileType, out Projectile projectile)
    {
        projectile = new Projectile();
        if (projectileType <= ProjectileID.None) return false;
        try
        {
            projectile.SetDefaults(projectileType);
            return true;
        }
        catch
        {
            projectile = new Projectile();
            return false;
        }
    }

    private static object RarityDetailsFromItem(Item item)
    {
        int raw = item.rare;
        try
        {
            ModRarity? modRarity = RarityLoader.GetRarity(raw);
            if (modRarity is not null)
            {
                Color color = modRarity.RarityColor;
                string modName = "UnknownMod";
                string rarityName = modRarity.GetType().Name;
                try { modName = modRarity.Mod?.Name ?? modName; } catch { }
                try { rarityName = string.IsNullOrWhiteSpace(modRarity.Name) ? rarityName : modRarity.Name; } catch { }
                return new
                {
                    raw,
                    isModded = true,
                    mod = modName,
                    name = rarityName,
                    fullName = modName + "/" + rarityName,
                    colorHex = ColorToHex(color),
                    colorR = color.R,
                    colorG = color.G,
                    colorB = color.B,
                    source = "RarityLoader.GetRarity"
                };
            }
        }
        catch { }

        return new
        {
            raw,
            isModded = false,
            mod = "Terraria",
            name = VanillaRarityName(raw),
            fullName = "Terraria/" + VanillaRarityName(raw),
            colorHex = VanillaRarityHex(raw),
            source = "vanilla numeric rarity"
        };
    }

    private static string ColorToHex(Color color)
    {
        return $"#{color.R:X2}{color.G:X2}{color.B:X2}";
    }

    private static string VanillaRarityName(int rare) => rare switch
    {
        ItemRarityID.Gray => "Gray",
        ItemRarityID.White => "White",
        ItemRarityID.Blue => "Blue",
        ItemRarityID.Green => "Green",
        ItemRarityID.Orange => "Orange",
        ItemRarityID.LightRed => "LightRed",
        ItemRarityID.Pink => "Pink",
        ItemRarityID.LightPurple => "LightPurple",
        ItemRarityID.Lime => "Lime",
        ItemRarityID.Yellow => "Yellow",
        ItemRarityID.Cyan => "Cyan",
        ItemRarityID.Red => "Red",
        ItemRarityID.Purple => "Purple",
        _ => "UnknownVanillaRarity"
    };

    private static string VanillaRarityHex(int rare) => rare switch
    {
        ItemRarityID.Gray => "#828282",
        ItemRarityID.White => "#FFFFFF",
        ItemRarityID.Blue => "#9696FF",
        ItemRarityID.Green => "#96FF96",
        ItemRarityID.Orange => "#FFC896",
        ItemRarityID.LightRed => "#FF9696",
        ItemRarityID.Pink => "#FF96FF",
        ItemRarityID.LightPurple => "#D2A0FF",
        ItemRarityID.Lime => "#96FF0A",
        ItemRarityID.Yellow => "#FFFF0A",
        ItemRarityID.Cyan => "#05C8FF",
        ItemRarityID.Red => "#FF2864",
        ItemRarityID.Purple => "#B428FF",
        _ => "#FFFFFF"
    };

    private static CanonicalSpec CanonicalFromItem(Item item, string[] autoFeatures)
    {
        string head = GuessHead(item.Name, autoFeatures);
        string material = autoFeatures.Contains("placeable_block") ? "block" : "";
        return new CanonicalSpec
        {
            HeadNoun = head,
            Modifiers = Array.Empty<string>(),
            Material = material,
            Class = item.accessory ? "accessory" : item.damage > 0 ? "weapon" : item.consumable ? "consumable" : item.createTile >= TileID.Dirt ? "placeable" : item.material ? "material" : "generic",
            ShapeAnchors = new[] { head },
            VisualAnchors = new[] { item.Name },
            HardTags = autoFeatures.Where(t => t is "weapon" or "tool" or "accessory" or "armor" or "ammo" or "placeable" or "material" or "projectile").Distinct().ToArray(),
            SoftTags = autoFeatures.Except(autoFeatures.Where(t => t is "weapon" or "tool" or "accessory" or "armor" or "ammo" or "placeable" or "material" or "projectile")).Distinct().ToArray()
        };
    }

    private static IEnumerable<string> AutoFeaturesFromItem(Item item)
    {
        // Mechanically derived features only. No hand-authored per-item semantic tags.
        var tags = new HashSet<string>();
        void Add(string tag) => tags.Add(tag);

        if (item.damage > 0) Add("weapon");
        if (item.DamageType == DamageClass.Melee) Add("melee");
        if (item.DamageType == DamageClass.Ranged) Add("ranged");
        if (item.DamageType == DamageClass.Magic) Add("magic");
        if (item.DamageType == DamageClass.Summon) Add("summon");
        if (item.accessory) Add("accessory");
        if (item.defense > 0 || item.headSlot >= 0 || item.bodySlot >= 0 || item.legSlot >= 0) Add("armor");
        if (item.material) Add("material");
        if (item.pick > 0 || item.axe > 0 || item.hammer > 0 || item.fishingPole > 0) Add("tool");
        if (item.pick > 0) Add("pickaxe");
        if (item.axe > 0) Add("axe");
        if (item.hammer > 0) Add("hammer");
        if (item.fishingPole > 0) Add("fishing_pole");
        if (item.healLife > 0 || item.healMana > 0 || item.buffType > InfiniTerrariaSentinels.NoBuffType) Add("potion_like");
        if (item.consumable) Add("consumable");
        if (item.ammo > AmmoID.None) Add("ammo");
        if (item.useAmmo > AmmoID.None) Add("uses_ammo");
        if (item.createTile >= TileID.Dirt || item.createWall >= WallID.None) Add("placeable");
        if (item.createTile >= TileID.Dirt && item.maxStack > 1) Add("placeable_block_or_tile");
        if (item.maxStack > 1) Add("stackable");
        if (item.shoot > ProjectileID.None) Add("projectile");
        if (item.channel) Add("channel");
        if (item.noMelee) Add("no_melee");
        if (item.noUseGraphic) Add("hidden_use_graphic");
        if (item.autoReuse) Add("auto_reuse");

        try
        {
            if (item.shoot > ProjectileID.None)
            {
                if (!TryCreateProjectileDefaults(item.shoot, out Projectile p))
                    return tags;
                if (p.penetrate == -1 || p.penetrate > 1) Add("piercing_projectile");
                if (p.extraUpdates > 0) Add("fast_projectile");
                if (!p.tileCollide) Add("noncolliding_projectile");
                if (p.usesLocalNPCImmunity || p.usesIDStaticNPCImmunity) Add("multi_hit_projectile");
                if (p.ownerHitCheck) Add("melee_projection");
                if (p.minion || p.sentry) Add("summon_projectile");
                if (p.arrow) Add("arrow_projectile");
            }
        }
        catch { }

        return tags;
    }

    private static string GuessHead(string name, string[] autoFeatures)
    {
        if (autoFeatures.Contains("tool")) return "tool";
        if (autoFeatures.Contains("weapon")) return "weapon";
        if (autoFeatures.Contains("accessory")) return "accessory";
        if (autoFeatures.Contains("armor")) return "armor";
        if (autoFeatures.Contains("ammo")) return "ammo";
        if (autoFeatures.Contains("placeable")) return "placeable";
        if (autoFeatures.Contains("material")) return "material";
        var parts = name.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return parts.Length == 0 ? "item" : parts[^1].ToLowerInvariant();
    }


}
